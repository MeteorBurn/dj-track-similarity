"""Explicit, read-only validation of persisted library data."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .analysis_config import normalize_sonara_bpm_range
from .analysis_models import CURRENT_EMBEDDING_SPECS, FingerprintOutput
from .db_connection import connect_database_read_only
from .db_embeddings import EmbeddingTrackIdentity, validate_embedding_row_payload
from .db_schema import validate_library_schema
from .sonara_core_validation import SONARA_CORE_COLUMNS, validate_sonara_core_row


ValidationLevel = str


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    level: ValidationLevel
    code: str
    entity: str
    message: str
    table: str | None = None
    track_id: int | None = None
    path: str | None = None


def format_validation_finding(finding: ValidationFinding) -> str:
    """Return the short human-facing form used by the UI, API job and CLI."""
    message = f"[{finding.level.upper()}] {finding.message}"
    details: list[str] = []
    if finding.track_id is not None:
        details.append(f"track {finding.track_id}")
    if finding.path is not None:
        details.append(finding.path)
    return " · ".join((message, *details))


@dataclass(frozen=True, slots=True)
class DatabaseValidationReport:
    findings: tuple[ValidationFinding, ...]
    checked: int
    warning_count: int
    error_count: int
    cancelled: bool = False

    @property
    def status(self) -> str:
        if self.cancelled:
            return "cancelled"
        return "failed" if self.error_count else "completed"


class DatabaseValidator:
    """Stream current persisted rows without changing the library database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).resolve()

    def run(
        self,
        emit: Callable[[ValidationFinding], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> DatabaseValidationReport:
        findings: list[ValidationFinding] = []
        checked = 0
        warning_count = 0
        error_count = 0
        is_cancelled = False

        def record(finding: ValidationFinding) -> None:
            nonlocal checked, warning_count, error_count
            checked += 1
            if finding.level == "warning":
                warning_count += 1
            elif finding.level == "error":
                error_count += 1
            findings.append(finding)
            if emit is not None:
                emit(finding)

        with closing(self._connect_read_only()) as connection:
            for finding in self._database_findings(connection):
                record(finding)
            try:
                catalog_uuid = validate_library_schema(connection)
            except RuntimeError as error:
                record(
                    ValidationFinding(
                        "error",
                        "library_identity_invalid",
                        "library",
                        str(error),
                        table="library",
                    )
                )
                return DatabaseValidationReport(
                    findings=tuple(findings),
                    checked=checked,
                    warning_count=warning_count,
                    error_count=error_count,
                )
            record(
                ValidationFinding(
                    "ok",
                    "library_identity_valid",
                    "library",
                    "library identity row is valid",
                    table="library",
                )
            )
            record(self._library_range_finding(connection))
            tracks: dict[int, EmbeddingTrackIdentity] = {}
            for row in connection.execute(
                "SELECT track_id, track_uuid, file_path FROM tracks ORDER BY track_id"
            ):
                if cancelled is not None and cancelled():
                    is_cancelled = True
                    break
                finding, identity = self._track_finding(row, catalog_uuid)
                if identity is not None:
                    tracks[identity.track_id] = identity
                record(finding)
            if not is_cancelled:
                for family, specification in CURRENT_EMBEDDING_SPECS.items():
                    table = f"{family}_embeddings"
                    for row in connection.execute(
                        f"SELECT track_id, track_uuid, dim, normalization, embedding_blob FROM {table} ORDER BY track_id"
                    ):
                        if cancelled is not None and cancelled():
                            is_cancelled = True
                            break
                        record(self._embedding_finding(family, table, row, tracks))
                    if is_cancelled:
                        break
            if not is_cancelled:
                columns = ", ".join(SONARA_CORE_COLUMNS)
                for row in connection.execute(
                    f"SELECT {columns} FROM sonara_features ORDER BY track_id"
                ):
                    if cancelled is not None and cancelled():
                        is_cancelled = True
                        break
                    record(self._sonara_finding(row, tracks))
            if not is_cancelled:
                for row in connection.execute(
                    "SELECT track_id, track_uuid, fingerprint_version, "
                    "fingerprint_base64, analyzed_at FROM sonara_fingerprints "
                    "ORDER BY track_id"
                ):
                    if cancelled is not None and cancelled():
                        is_cancelled = True
                        break
                    record(self._fingerprint_finding(row, tracks))

        return DatabaseValidationReport(
            findings=tuple(findings),
            checked=checked,
            warning_count=warning_count,
            error_count=error_count,
            cancelled=is_cancelled,
        )

    def _connect_read_only(self) -> sqlite3.Connection:
        return connect_database_read_only(self.database_path)

    @staticmethod
    def _library_range_finding(connection: sqlite3.Connection) -> ValidationFinding:
        row = connection.execute(
            "SELECT sonara_bpm_min, sonara_bpm_max FROM library WHERE singleton_id = 1"
        ).fetchone()
        low, high = row["sonara_bpm_min"], row["sonara_bpm_max"]
        if low is None and high is None:
            return ValidationFinding("ok", "library_sonara_range_unclaimed", "library", "no SONARA BPM range is claimed", table="library")
        if low is None or high is None:
            return ValidationFinding("error", "library_sonara_range_invalid", "library", "the SONARA BPM range is half stored", table="library")
        try:
            normalize_sonara_bpm_range(low, high)
        except (TypeError, ValueError) as error:
            return ValidationFinding("error", "library_sonara_range_invalid", "library", str(error), table="library")
        return ValidationFinding("ok", "library_sonara_range_valid", "library", f"SONARA BPM range {low:g}-{high:g} is valid", table="library")

    @staticmethod
    def _database_findings(connection: sqlite3.Connection) -> Iterator[ValidationFinding]:
        integrity_rows = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
        if integrity_rows == ("ok",):
            yield ValidationFinding("ok", "sqlite_integrity_ok", "database", "SQLite integrity check passed")
        else:
            for detail in integrity_rows:
                yield ValidationFinding("error", "sqlite_integrity_error", "database", detail)
        for row in connection.execute("PRAGMA foreign_key_check"):
            yield ValidationFinding(
                "error",
                "foreign_key_violation",
                "database",
                f"foreign key violation in table {row[0]}",
                table=str(row[0]),
                track_id=int(row[1]) if isinstance(row[1], int) else None,
            )

    @staticmethod
    def _track_finding(
        row: sqlite3.Row,
        catalog_uuid: str,
    ) -> tuple[ValidationFinding, EmbeddingTrackIdentity | None]:
        track_id = row["track_id"]
        track_uuid = row["track_uuid"]
        path_value = row["file_path"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id <= 0:
            return ValidationFinding("error", "track_id_invalid", "track", "track_id must be positive"), None
        if not isinstance(track_uuid, str) or not track_uuid.strip():
            return ValidationFinding("error", "track_uuid_invalid", "track", "track_uuid is missing", track_id=track_id), None
        if not isinstance(path_value, str) or not path_value.strip():
            return ValidationFinding("error", "track_path_invalid", "track", "file_path is missing", track_id=track_id), None
        identity = EmbeddingTrackIdentity(catalog_uuid, track_id, track_uuid)
        if not Path(path_value).is_file():
            return ValidationFinding("warning", "track_path_missing", "track", "stored file path does not exist", table="tracks", track_id=track_id, path=path_value), identity
        return ValidationFinding("ok", "track_valid", "track", "track identity and path are valid", table="tracks", track_id=track_id, path=path_value), identity

    @staticmethod
    def _embedding_finding(
        family: str,
        table: str,
        row: sqlite3.Row,
        tracks: dict[int, EmbeddingTrackIdentity],
    ) -> ValidationFinding:
        track_id = row["track_id"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id not in tracks:
            return ValidationFinding("error", "embedding_orphan", "embedding", "embedding references an unknown track", table=table, track_id=track_id if isinstance(track_id, int) else None)
        valid, reason = validate_embedding_row_payload(family=family, row=row, expected_track=tracks[track_id])
        if not valid:
            return ValidationFinding("error", "embedding_invalid", "embedding", reason or "invalid embedding", table=table, track_id=track_id)
        return ValidationFinding("ok", "embedding_valid", "embedding", "embedding matches current specification", table=table, track_id=track_id)

    @staticmethod
    def _sonara_finding(row: sqlite3.Row, tracks: dict[int, EmbeddingTrackIdentity]) -> ValidationFinding:
        track_id = row["track_id"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id not in tracks:
            return ValidationFinding("error", "sonara_feature_orphan", "sonara_feature", "SONARA features reference an unknown track", table="sonara_features", track_id=track_id if isinstance(track_id, int) else None)
        valid, reason = validate_sonara_core_row(row, expected_track_id=track_id)
        if not valid:
            return ValidationFinding("error", "sonara_feature_invalid", "sonara_feature", reason or "invalid SONARA Core row", table="sonara_features", track_id=track_id)
        return ValidationFinding("ok", "sonara_feature_valid", "sonara_feature", "SONARA Core row is valid", table="sonara_features", track_id=track_id)

    @staticmethod
    def _fingerprint_finding(row: sqlite3.Row, tracks: dict[int, EmbeddingTrackIdentity]) -> ValidationFinding:
        track_id = row["track_id"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id not in tracks:
            return ValidationFinding("error", "sonara_fingerprint_orphan", "sonara_fingerprint", "fingerprint references an unknown track", table="sonara_fingerprints", track_id=track_id if isinstance(track_id, int) else None)
        if row["track_uuid"] != tracks[track_id].track_uuid:
            return ValidationFinding("error", "sonara_fingerprint_invalid", "sonara_fingerprint", "track_uuid mismatch", table="sonara_fingerprints", track_id=track_id)
        try:
            FingerprintOutput(value=row["fingerprint_base64"], version=row["fingerprint_version"], analyzed_at=row["analyzed_at"])
        except (TypeError, ValueError) as error:
            return ValidationFinding("error", "sonara_fingerprint_invalid", "sonara_fingerprint", str(error), table="sonara_fingerprints", track_id=track_id)
        return ValidationFinding("ok", "sonara_fingerprint_valid", "sonara_fingerprint", "fingerprint matches the current specification", table="sonara_fingerprints", track_id=track_id)

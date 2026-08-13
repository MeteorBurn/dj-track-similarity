"""Explicit, read-only validation of persisted library data."""

from __future__ import annotations

import sqlite3
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from .analysis_models import CURRENT_EMBEDDING_SPECS
from .db_embeddings import EmbeddingTrackIdentity, validate_embedding_row_payload


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

        with self._connect_read_only() as connection:
            for finding in self._database_findings(connection):
                record(finding)
            tracks: dict[int, EmbeddingTrackIdentity] = {}
            for row in connection.execute(
                "SELECT track_id, track_uuid, file_path FROM tracks ORDER BY track_id"
            ):
                if cancelled is not None and cancelled():
                    is_cancelled = True
                    break
                finding, identity = self._track_finding(row, connection)
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
                for row in connection.execute(
                    "SELECT track_id, mfcc_mean_blob, chroma_mean_blob, "
                    "spectral_contrast_mean_blob FROM sonara_features ORDER BY track_id"
                ):
                    if cancelled is not None and cancelled():
                        is_cancelled = True
                        break
                    record(self._sonara_finding(row, tracks))
            if not is_cancelled:
                for row in connection.execute(
                    "SELECT track_id, track_uuid, classifier_key, feature_set, "
                    "feature_names_json, positive_label, predicted_class, score_bucket, "
                    "score, confidence, probabilities_json "
                    "FROM classifier_scores ORDER BY track_id, classifier_key"
                ):
                    if cancelled is not None and cancelled():
                        is_cancelled = True
                        break
                    record(self._classifier_finding(row, tracks))

        return DatabaseValidationReport(
            findings=tuple(findings),
            checked=checked,
            warning_count=warning_count,
            error_count=error_count,
            cancelled=is_cancelled,
        )

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        connection = sqlite3.connect(f"{self.database_path.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

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
        connection: sqlite3.Connection,
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
        catalog_row = connection.execute("SELECT catalog_uuid FROM library WHERE singleton_id = 1").fetchone()
        if catalog_row is None or not isinstance(catalog_row[0], str) or not catalog_row[0].strip():
            return ValidationFinding("error", "catalog_uuid_invalid", "track", "library catalog UUID is missing", track_id=track_id), None
        identity = EmbeddingTrackIdentity(str(catalog_row[0]), track_id, track_uuid)
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
        if not isinstance(track_id, int) or track_id not in tracks:
            return ValidationFinding("error", "sonara_feature_orphan", "sonara_feature", "SONARA features reference an unknown track", table="sonara_features", track_id=track_id if isinstance(track_id, int) else None)
        for name, dim in (("mfcc_mean_blob", 13), ("chroma_mean_blob", 12), ("spectral_contrast_mean_blob", 7)):
            blob = row[name]
            if not isinstance(blob, bytes) or len(blob) != dim * 4 or not bool(np.all(np.isfinite(np.frombuffer(blob, dtype="<f4")))):
                return ValidationFinding("error", "sonara_feature_invalid", "sonara_feature", f"{name} must contain {dim} finite float32 values", table="sonara_features", track_id=track_id)
        return ValidationFinding("ok", "sonara_feature_valid", "sonara_feature", "SONARA feature vectors are valid", table="sonara_features", track_id=track_id)

    @staticmethod
    def _classifier_finding(row: sqlite3.Row, tracks: dict[int, EmbeddingTrackIdentity]) -> ValidationFinding:
        track_id = row["track_id"]
        classifier_key = str(row["classifier_key"] or "unknown")
        try:
            expected = tracks[track_id]
            probabilities = json.loads(row["probabilities_json"])
            names = json.loads(row["feature_names_json"])
            numeric = (float(row["score"]), float(row["confidence"]))
            valid = (row["track_uuid"] == expected.track_uuid and isinstance(names, list) and isinstance(probabilities, dict) and bool(probabilities) and all(np.isfinite(float(value)) and 0 <= float(value) <= 1 for value in probabilities.values()) and all(np.isfinite(value) and 0 <= value <= 1 for value in numeric) and all(isinstance(row[name], str) and row[name].strip() for name in ("classifier_key", "feature_set", "positive_label", "predicted_class", "score_bucket")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            valid = False
        if not valid:
            return ValidationFinding("error", "classifier_score_invalid", "classifier_score", f"Classifier «{classifier_key}»: stored values are invalid", table="classifier_scores", track_id=track_id if isinstance(track_id, int) else None)
        return ValidationFinding("ok", "classifier_score_valid", "classifier_score", f"Classifier «{classifier_key}»: stored values are valid", table="classifier_scores", track_id=track_id)

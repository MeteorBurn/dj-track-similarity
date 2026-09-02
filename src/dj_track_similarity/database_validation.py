"""Explicit, read-only validation of persisted library data."""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .analysis_config import normalize_sonara_bpm_range
from .analysis_models import CURRENT_EMBEDDING_SPECS, FingerprintOutput
from .db_connection import connect_database_read_only
from .db_embeddings import EmbeddingTrackIdentity, validate_embedding_row_payload
from .db_schema import validate_library_schema
from .sonara_core_validation import SONARA_CORE_COLUMNS, validate_sonara_core_row


ValidationLevel = str

# How the closing coverage line names each per-track table. A row missing from
# one of them is unfinished analysis rather than damaged data, so the line is
# `info`: a freshly scanned library would otherwise drown in warnings.
_COVERAGE_LABELS: Mapping[str, str] = MappingProxyType(
    {
        **{f"{family}_embeddings": family.upper() for family in CURRENT_EMBEDDING_SPECS},
        "sonara_embeddings": "SONARA vector",
        "sonara_features": "SONARA Core",
        "sonara_fingerprints": "fingerprint",
    }
)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    level: ValidationLevel
    code: str
    entity: str
    message: str
    table: str | None = None
    track_id: int | None = None
    path: str | None = None


def describe_validation_finding(finding: ValidationFinding) -> str:
    """Return the finding with the row it is about, and no level of its own.

    The UI log already prints the level in its own column, so a line there
    reads like an analysis event rather than repeating `[ERROR]`.
    """
    details: list[str] = []
    if finding.track_id is not None:
        details.append(f"track {finding.track_id}")
    if finding.path is not None:
        details.append(finding.path)
    return " · ".join((finding.message, *details))


def format_validation_finding(finding: ValidationFinding) -> str:
    """Return the short human-facing form used by the API job log and CLI."""
    return f"[{finding.level.upper()}] {describe_validation_finding(finding)}"


@dataclass(frozen=True, slots=True)
class TrackValidation:
    """Every finding one track produced, gathered before the next track starts."""

    track_id: int | None
    path: str | None
    findings: tuple[ValidationFinding, ...]

    @property
    def level(self) -> ValidationLevel:
        levels = {finding.level for finding in self.findings}
        if "error" in levels:
            return "error"
        if "warning" in levels:
            return "warning"
        return "ok"

    @property
    def message(self) -> str:
        """One log line per track, worded like the analysis job's track events."""
        problems = sorted(
            (finding for finding in self.findings if finding.level != "ok"),
            key=lambda finding: 0 if finding.level == "error" else 1,
        )
        if not problems:
            return "Track validated"
        prefix = "Track failed" if self.level == "error" else "Track warning"
        more = f" (+{len(problems) - 1})" if len(problems) > 1 else ""
        return f"{prefix}: {problems[0].message}{more}"


@dataclass(frozen=True, slots=True)
class DatabaseValidationReport:
    findings: tuple[ValidationFinding, ...]
    checked: int
    warning_count: int
    error_count: int
    tracks_checked: int = 0
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

    def track_count(self) -> int:
        """Return the number of tracks a run will validate, for progress."""
        with closing(self._connect_read_only()) as connection:
            row = connection.execute("SELECT COUNT(*) FROM tracks").fetchone()
        return int(row[0]) if row is not None else 0

    def run(
        self,
        on_finding: Callable[[ValidationFinding], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        on_track: Callable[[TrackValidation], None] | None = None,
    ) -> DatabaseValidationReport:
        """Validate the library one whole track at a time.

        ``on_finding`` receives the findings that belong to no single track: the
        database and library checks. A track's own findings arrive together
        through ``on_track`` instead, so a caller can log and count by track
        rather than by row.

        A track-driven join cannot see a row left behind by a deleted track, and
        it does not have to: every per-track table declares its foreign key, so
        ``PRAGMA foreign_key_check`` already names each orphan among the database
        findings. Sweeping the tables again for them would re-read every stored
        embedding to repeat a report the run has already made.
        """

        findings: list[ValidationFinding] = []
        checked = 0
        warning_count = 0
        error_count = 0
        tracks_checked = 0
        coverage: Counter[str] = Counter()
        is_cancelled = False

        def count(finding: ValidationFinding) -> None:
            nonlocal checked, warning_count, error_count
            checked += 1
            if finding.level == "warning":
                warning_count += 1
            elif finding.level == "error":
                error_count += 1
            findings.append(finding)

        def record(finding: ValidationFinding) -> None:
            count(finding)
            if on_finding is not None:
                on_finding(finding)

        def deliver(validation: TrackValidation) -> None:
            nonlocal tracks_checked
            for finding in validation.findings:
                count(finding)
                # Every stored row produced exactly one finding naming its
                # table, so coverage falls out of the pass already made.
                if finding.table is not None and finding.table != "tracks":
                    coverage[finding.table] += 1
            tracks_checked += 1
            if on_track is not None:
                on_track(validation)

        def report() -> DatabaseValidationReport:
            return DatabaseValidationReport(
                findings=tuple(findings),
                checked=checked,
                warning_count=warning_count,
                error_count=error_count,
                tracks_checked=tracks_checked,
                cancelled=is_cancelled,
            )

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
                return report()
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
            for row in connection.execute(_TRACK_QUERY.sql):
                if cancelled is not None and cancelled():
                    is_cancelled = True
                    break
                deliver(self._validate_track(row, catalog_uuid))
            if not is_cancelled and tracks_checked:
                record(_coverage_finding(coverage, tracks_checked))

        return report()

    def _connect_read_only(self) -> sqlite3.Connection:
        return connect_database_read_only(self.database_path)

    @classmethod
    def _validate_track(
        cls,
        row: sqlite3.Row,
        catalog_uuid: str,
    ) -> TrackValidation:
        """Check one track and every row the rest of the library stores for it.

        Each table's columns are read as one slice. Looking a column up by name
        walks every name in the row, and a row that carries the whole library
        side of a track is about a hundred columns wide.
        """
        identity_finding, identity = cls._track_finding(row[0:3], catalog_uuid)
        findings = [identity_finding]
        if identity is not None:
            for family, base in _TRACK_QUERY.embedding_bases.items():
                track_uuid, dim, normalization, blob = row[base : base + 4]
                if track_uuid is None:
                    continue
                findings.append(
                    cls._embedding_finding(
                        family,
                        f"{family}_embeddings",
                        {
                            "track_id": identity.track_id,
                            "track_uuid": track_uuid,
                            "dim": dim,
                            "normalization": normalization,
                            "embedding_blob": blob,
                        },
                        identity,
                    )
                )
            sonara_base = _TRACK_QUERY.sonara_base
            sonara_values = row[sonara_base : sonara_base + len(SONARA_CORE_COLUMNS)]
            if sonara_values[_SONARA_TRACK_ID_OFFSET] is not None:
                findings.append(
                    cls._sonara_finding(
                        dict(zip(SONARA_CORE_COLUMNS, sonara_values)),
                        identity,
                    )
                )
            fingerprint_base = _TRACK_QUERY.fingerprint_base
            fingerprint_uuid, version, value, analyzed_at = row[
                fingerprint_base : fingerprint_base + 4
            ]
            if fingerprint_uuid is not None:
                findings.append(
                    cls._fingerprint_finding(
                        identity,
                        track_uuid=fingerprint_uuid,
                        version=version,
                        value=value,
                        analyzed_at=analyzed_at,
                    )
                )
        return TrackValidation(
            track_id=identity_finding.track_id,
            path=identity_finding.path,
            findings=tuple(findings),
        )

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
        row: tuple[object, object, object],
        catalog_uuid: str,
    ) -> tuple[ValidationFinding, EmbeddingTrackIdentity | None]:
        track_id, track_uuid, path_value = row
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
        row: Mapping[str, object],
        track: EmbeddingTrackIdentity,
    ) -> ValidationFinding:
        valid, reason = validate_embedding_row_payload(family=family, row=row, expected_track=track)
        if not valid:
            return ValidationFinding("error", "embedding_invalid", "embedding", reason or "invalid embedding", table=table, track_id=track.track_id)
        return ValidationFinding("ok", "embedding_valid", "embedding", "embedding matches current specification", table=table, track_id=track.track_id)

    @staticmethod
    def _sonara_finding(
        row: Mapping[str, object],
        track: EmbeddingTrackIdentity,
    ) -> ValidationFinding:
        valid, reason = validate_sonara_core_row(row, expected_track_id=track.track_id)
        if not valid:
            return ValidationFinding("error", "sonara_feature_invalid", "sonara_feature", reason or "invalid SONARA Core row", table="sonara_features", track_id=track.track_id)
        return ValidationFinding("ok", "sonara_feature_valid", "sonara_feature", "SONARA Core row is valid", table="sonara_features", track_id=track.track_id)

    @staticmethod
    def _fingerprint_finding(
        track: EmbeddingTrackIdentity,
        *,
        track_uuid: object,
        version: object,
        value: object,
        analyzed_at: object,
    ) -> ValidationFinding:
        if track_uuid != track.track_uuid:
            return ValidationFinding("error", "sonara_fingerprint_invalid", "sonara_fingerprint", "track_uuid mismatch", table="sonara_fingerprints", track_id=track.track_id)
        try:
            FingerprintOutput(value=value, version=version, analyzed_at=analyzed_at)
        except (TypeError, ValueError) as error:
            return ValidationFinding("error", "sonara_fingerprint_invalid", "sonara_fingerprint", str(error), table="sonara_fingerprints", track_id=track.track_id)
        return ValidationFinding("ok", "sonara_fingerprint_valid", "sonara_fingerprint", "fingerprint matches the current specification", table="sonara_fingerprints", track_id=track.track_id)


def _coverage_finding(coverage: Mapping[str, int], tracks: int) -> ValidationFinding:
    """Close the run by saying how much of the library each model has reached.

    A track with no row in a table is unfinished analysis, not damaged data, so
    this is one `info` line rather than a warning per gap.
    """
    parts = [
        f"{label} {coverage.get(table, 0)}/{tracks}"
        for table, label in _COVERAGE_LABELS.items()
    ]
    return ValidationFinding(
        "info",
        "model_coverage",
        "database",
        "coverage: " + " · ".join(parts),
    )


@dataclass(frozen=True, slots=True)
class _TrackQuery:
    """The per-track join, and where each table's columns start in its rows."""

    sql: str
    embedding_bases: Mapping[str, int]
    sonara_base: int
    fingerprint_base: int


def _build_track_query() -> _TrackQuery:
    """One row per track carrying everything the library stores about it."""
    selects = ["t.track_id", "t.track_uuid", "t.file_path"]
    joins: list[str] = []
    embedding_bases: dict[str, int] = {}
    for family in CURRENT_EMBEDDING_SPECS:
        embedding_bases[family] = len(selects)
        selects += [
            f"{family}.track_uuid",
            f"{family}.dim",
            f"{family}.normalization",
            f"{family}.embedding_blob",
        ]
        joins.append(
            f"LEFT JOIN {family}_embeddings AS {family}"
            f" ON {family}.track_id = t.track_id"
        )
    sonara_base = len(selects)
    selects += [f"features.{column}" for column in SONARA_CORE_COLUMNS]
    joins.append("LEFT JOIN sonara_features AS features ON features.track_id = t.track_id")
    fingerprint_base = len(selects)
    selects += [
        "fingerprint.track_uuid",
        "fingerprint.fingerprint_version",
        "fingerprint.fingerprint_base64",
        "fingerprint.analyzed_at",
    ]
    joins.append(
        "LEFT JOIN sonara_fingerprints AS fingerprint"
        " ON fingerprint.track_id = t.track_id"
    )
    return _TrackQuery(
        sql=(
            f"SELECT {', '.join(selects)} FROM tracks AS t "
            + " ".join(joins)
            + " ORDER BY t.track_id"
        ),
        embedding_bases=MappingProxyType(embedding_bases),
        sonara_base=sonara_base,
        fingerprint_base=fingerprint_base,
    )


_TRACK_QUERY = _build_track_query()
_SONARA_TRACK_ID_OFFSET = SONARA_CORE_COLUMNS.index("track_id")

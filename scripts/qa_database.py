"""Read-only structural and data-integrity QA for one library bundle.

Usage:
    python scripts/qa_database.py --db PATH [--artifacts-db PATH]
        [--evaluation-db PATH]

The Artifacts sidecar is required. Its default path is derived with
``storage_database_paths``. The Evaluation sidecar is optional and is inspected
only when its file already exists. This script never creates or changes a
database.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import struct
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dj_track_similarity.db_artifacts import (  # noqa: E402
    ArtifactTrackIdentity,
    validate_artifacts_sidecar_schema,
    validate_embedding_row_payload,
)
from dj_track_similarity.db_evaluation_sidecar import (  # noqa: E402
    validate_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import validate_core_schema  # noqa: E402
from dj_track_similarity.db_storage import storage_database_paths  # noqa: E402
from dj_track_similarity.db_structure import require_current_structure  # noqa: E402


_EMBEDDING_TABLE_FAMILIES: Mapping[str, str] = {
    "maest_embeddings": "maest",
    "mert_embeddings": "mert",
    "muq_embeddings": "muq",
    "clap_embeddings": "clap",
}
_ARTIFACT_TABLES: tuple[str, ...] = tuple(_EMBEDDING_TABLE_FAMILIES)
_SONARA_SHORT_VECTORS: Mapping[str, int] = {
    "mfcc_mean_blob": 13,
    "chroma_mean_blob": 12,
    "spectral_contrast_mean_blob": 7,
}
_CORE_JSON_FIELDS: Mapping[str, tuple[str, ...]] = {
    "tags": ("genres_json",),
    "sonara": ("bpm_candidates_json", "key_candidates_json"),
    "maest_genres": ("genres_json",),
    "pair_feedback": ("reason_tags_json",),
    "transition_feedback": ("risk_tags_json",),
}
_PROBABILITY_TOLERANCE = 1e-6


class QAError(RuntimeError):
    """A user-facing database QA failure."""


def _fail(reason: str) -> int:
    print(f"FAIL: {reason}", flush=True)
    return 1


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _open_read_only(path: Path, label: str) -> sqlite3.Connection:
    if not path.is_file():
        raise QAError(f"{label} database not found: {path}")
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise QAError(f"cannot open {label} database {path}: {error}") from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise QAError(f"{label} database could not enter query-only mode")
    return connection


def _integrity_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    failures = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    if failures or not rows:
        detail = failures[0] if failures else "no result"
        raise QAError(f"{label} integrity_check failed: {detail}")


def _foreign_key_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        row = rows[0]
        raise QAError(
            f"{label} foreign-key violation: "
            f"table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
        )


def _current_structure(
    validator: Callable[..., str],
    connection: sqlite3.Connection,
    label: str,
    *,
    database_path: Path,
    expected_catalog_uuid: str | None = None,
) -> str:
    if validator is validate_core_schema:
        try:
            return require_current_structure(connection, "core", database_path)
        except (RuntimeError, ValueError, sqlite3.Error) as error:
            raise QAError(
                f"{label} structure validation failed: {error}"
            ) from error
    kwargs: dict[str, object] = {}
    if expected_catalog_uuid is not None:
        kwargs["expected_catalog_uuid"] = expected_catalog_uuid
    if validator is not validate_evaluation_sidecar_schema:
        kwargs["database_path"] = str(database_path)
    try:
        return str(validator(connection, **kwargs))
    except (RuntimeError, ValueError, sqlite3.Error) as error:
        raise QAError(f"{label} structure validation failed: {error}") from error


def _track_identities(
    core: sqlite3.Connection,
    *,
    catalog_uuid: str,
) -> dict[int, ArtifactTrackIdentity]:
    tracks: dict[int, ArtifactTrackIdentity] = {}
    for row in core.execute(
        """
        SELECT track_id, track_uuid, content_generation
        FROM tracks
        ORDER BY track_id
        """
    ):
        track_id = row["track_id"]
        track_uuid = row["track_uuid"]
        generation = row["content_generation"]
        if isinstance(track_id, bool) or not isinstance(track_id, int) or track_id < 1:
            raise QAError(f"Core tracks contains invalid track_id={track_id!r}")
        if not isinstance(track_uuid, str) or not track_uuid.strip():
            raise QAError(f"Core tracks track_id={track_id}: invalid track_uuid")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise QAError(
                f"Core tracks track_id={track_id}: invalid content_generation"
            )
        tracks[track_id] = ArtifactTrackIdentity(
            catalog_uuid=catalog_uuid,
            track_id=track_id,
            track_uuid=track_uuid,
            content_generation=generation,
        )
    return tracks


def _require_current_track(
    tracks: Mapping[int, ArtifactTrackIdentity],
    *,
    track_id: object,
    track_uuid: object | None,
    content_generation: object,
    context: str,
) -> ArtifactTrackIdentity:
    if isinstance(track_id, bool) or not isinstance(track_id, int):
        raise QAError(f"{context}: invalid track_id")
    current = tracks.get(track_id)
    if current is None:
        raise QAError(f"{context}: orphan track_id={track_id}")
    if track_uuid is not None and track_uuid != current.track_uuid:
        raise QAError(
            f"{context}: track_uuid mismatch for track_id={track_id}; "
            f"stored={track_uuid!r}, Core={current.track_uuid!r}"
        )
    if (
        isinstance(content_generation, bool)
        or not isinstance(content_generation, int)
        or content_generation != current.content_generation
    ):
        raise QAError(
            f"{context}: content_generation mismatch for track_id={track_id}; "
            f"stored={content_generation!r}, Core={current.content_generation}"
        )
    return current


def _float32_values(blob: object, dim: int, context: str) -> tuple[float, ...]:
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise QAError(f"{context}: BLOB value is not bytes")
    raw = bytes(blob)
    if len(raw) != dim * 4:
        raise QAError(
            f"{context}: BLOB length mismatch; stored={len(raw)}, expected={dim * 4}"
        )
    try:
        values = tuple(value for (value,) in struct.iter_unpack("<f", raw))
    except struct.error as error:
        raise QAError(f"{context}: invalid little-endian float32 BLOB") from error
    if len(values) != dim:
        raise QAError(
            f"{context}: decoded dimension mismatch; "
            f"stored={len(values)}, expected={dim}"
        )
    if not all(math.isfinite(value) for value in values):
        raise QAError(f"{context}: BLOB contains non-finite float32 values")
    return values


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _finite_json(value: object, context: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise QAError(f"{context}: JSON contains a non-finite number")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _finite_json(item, f"{context}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise QAError(f"{context}: JSON object contains a non-text key")
            _finite_json(item, f"{context}.{key}")


def _json_value(
    raw: object,
    context: str,
    *,
    expected_type: type | tuple[type, ...],
    allow_none: bool = False,
) -> object | None:
    if raw is None and allow_none:
        return None
    if not isinstance(raw, str):
        raise QAError(f"{context}: JSON value is not text")
    try:
        value = json.loads(raw, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise QAError(f"{context}: invalid finite JSON") from error
    if not isinstance(value, expected_type):
        expected_name = (
            expected_type.__name__
            if isinstance(expected_type, type)
            else " or ".join(item.__name__ for item in expected_type)
        )
        raise QAError(f"{context}: JSON value must contain {expected_name}")
    _finite_json(value, context)
    return value


def _validate_core_json(core: sqlite3.Connection) -> None:
    for table, fields in _CORE_JSON_FIELDS.items():
        selected = ", ".join(("rowid AS qa_rowid", *fields))
        for row in core.execute(
            f'SELECT {selected} FROM "{table}" ORDER BY rowid'
        ):
            for field in fields:
                _json_value(
                    row[field],
                    f"Core {table} rowid={row['qa_rowid']}.{field}",
                    expected_type=list,
                    allow_none=table == "sonara",
                )


def _validate_core_analysis(
    core: sqlite3.Connection,
    tracks: Mapping[int, ArtifactTrackIdentity],
) -> None:
    for row in core.execute("SELECT * FROM sonara ORDER BY track_id"):
        track_id = row["track_id"]
        context = f"Core sonara track_id={track_id}"
        _require_current_track(
            tracks,
            track_id=track_id,
            track_uuid=None,
            content_generation=row["content_generation"],
            context=context,
        )
        for column, dim in _SONARA_SHORT_VECTORS.items():
            _float32_values(row[column], dim, f"{context}.{column}")

    for row in core.execute("SELECT * FROM maest_genres ORDER BY track_id"):
        track_id = row["track_id"]
        _require_current_track(
            tracks,
            track_id=track_id,
            track_uuid=None,
            content_generation=row["content_generation"],
            context=f"Core maest_genres track_id={track_id}",
        )


def _non_empty_text(row: sqlite3.Row, field: str, context: str) -> str:
    value = row[field]
    if not isinstance(value, str) or not value.strip():
        raise QAError(f"{context}: {field} must be non-empty text")
    return value


def _unit_interval(value: object, field: str, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QAError(f"{context}: {field} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise QAError(f"{context}: {field} is non-finite")
    if not 0.0 <= result <= 1.0:
        raise QAError(f"{context}: {field} is outside [0, 1]")
    return result


def _score_bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _validate_classifier_feature_names(
    raw: object,
    context: str,
) -> tuple[str, ...]:
    values = _json_value(
        raw,
        f"{context}.feature_names_json",
        expected_type=list,
    )
    assert isinstance(values, list)
    if not values:
        raise QAError(f"{context}: feature_names_json must not be empty")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise QAError(
            f"{context}: feature_names_json must contain non-empty text values"
        )
    feature_names = tuple(value.strip() for value in values)
    if len(set(feature_names)) != len(feature_names):
        raise QAError(f"{context}: feature_names_json contains duplicate features")
    for feature_name in feature_names:
        family, separator, name = feature_name.partition(":")
        if not separator or not family.strip() or not name.strip():
            raise QAError(
                f"{context}: feature name {feature_name!r} must use family:name"
            )
    return feature_names


def _validate_classifier_scores(
    core: sqlite3.Connection,
    tracks: Mapping[int, ArtifactTrackIdentity],
) -> None:
    for row in core.execute(
        "SELECT * FROM classifier_scores ORDER BY classifier_key, track_id"
    ):
        track_id = row["track_id"]
        classifier_key = _non_empty_text(
            row,
            "classifier_key",
            f"Core classifier_scores track_id={track_id}",
        )
        context = (
            f"Core classifier_scores track_id={track_id} "
            f"classifier_key={classifier_key!r}"
        )
        _require_current_track(
            tracks,
            track_id=track_id,
            track_uuid=row["track_uuid"],
            content_generation=row["content_generation"],
            context=context,
        )
        for field in (
            "feature_set",
            "positive_label",
            "predicted_class",
            "analyzed_at",
        ):
            _non_empty_text(row, field, context)
        _validate_classifier_feature_names(row["feature_names_json"], context)

        probabilities_value = _json_value(
            row["probabilities_json"],
            f"{context}.probabilities_json",
            expected_type=dict,
        )
        assert isinstance(probabilities_value, dict)
        if not probabilities_value:
            raise QAError(f"{context}: probabilities_json must not be empty")
        probabilities: dict[str, float] = {}
        for label, value in probabilities_value.items():
            if not label.strip():
                raise QAError(
                    f"{context}: probability labels must be non-empty text"
                )
            probabilities[label] = _unit_interval(
                value,
                f"probability[{label!r}]",
                context,
            )
        if not math.isclose(
            math.fsum(probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(f"{context}: probabilities do not sum to 1")

        positive_label = str(row["positive_label"])
        predicted_class = str(row["predicted_class"])
        if positive_label not in probabilities:
            raise QAError(
                f"{context}: positive_label is absent from probabilities_json"
            )
        if predicted_class not in probabilities:
            raise QAError(
                f"{context}: predicted_class is absent from probabilities_json"
            )
        maximum = max(probabilities.values())
        if not math.isclose(
            probabilities[predicted_class],
            maximum,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(f"{context}: predicted_class is not an argmax")

        score = _unit_interval(row["score"], "score", context)
        confidence = _unit_interval(row["confidence"], "confidence", context)
        if not math.isclose(
            score,
            probabilities[positive_label],
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(
                f"{context}: score does not equal the positive-label probability"
            )
        if not math.isclose(
            confidence,
            maximum,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(f"{context}: confidence does not equal max(probabilities)")
        expected_bucket = _score_bucket(score)
        if row["score_bucket"] != expected_bucket:
            raise QAError(
                f"{context}: score_bucket={row['score_bucket']!r}, "
                f"expected={expected_bucket!r}"
            )


def _validate_artifacts(
    artifacts: sqlite3.Connection,
    tracks: Mapping[int, ArtifactTrackIdentity],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _ARTIFACT_TABLES:
        rows = artifacts.execute(
            f'SELECT * FROM "{table}" ORDER BY track_id'
        ).fetchall()
        counts[table] = len(rows)
        for row in rows:
            track_id = row["track_id"]
            context = f"Artifacts {table} track_id={track_id}"
            expected_track = _require_current_track(
                tracks,
                track_id=track_id,
                track_uuid=row["track_uuid"],
                content_generation=row["content_generation"],
                context=context,
            )
            valid, reason = validate_embedding_row_payload(
                family=_EMBEDDING_TABLE_FAMILIES[table],
                row=row,
                expected_track=expected_track,
            )
            if not valid:
                raise QAError(f"{context}: {reason or 'invalid payload'}")
    return counts


def _validate_evaluation_data(
    evaluation: sqlite3.Connection,
    tracks: Mapping[int, ArtifactTrackIdentity],
) -> int:
    for table in ("search_session_seeds", "search_result_events"):
        for row in evaluation.execute(
            f"""
            SELECT rowid AS qa_rowid,
                   track_id, track_uuid, content_generation
            FROM "{table}"
            ORDER BY rowid
            """
        ):
            _require_current_track(
                tracks,
                track_id=row["track_id"],
                track_uuid=row["track_uuid"],
                content_generation=row["content_generation"],
                context=f"Evaluation {table} rowid={row['qa_rowid']}",
            )

    for row in evaluation.execute(
        """
        SELECT rowid AS qa_rowid, total_score
        FROM search_result_events
        ORDER BY rowid
        """
    ):
        total_score = row["total_score"]
        if (
            isinstance(total_score, bool)
            or not isinstance(total_score, (int, float))
            or not math.isfinite(float(total_score))
        ):
            raise QAError(
                "Evaluation search_result_events "
                f"rowid={row['qa_rowid']}.total_score is not finite"
            )

    json_fields: Mapping[str, Mapping[str, type | tuple[type, ...]]] = {
        "search_sessions": {"request_json": dict},
        "search_result_events": {"score_breakdown_json": dict},
        "calibration_runs": {
            "config_json": dict,
            "metrics_json": dict,
        },
        "evaluation_settings": {
            "value_json": (dict, list, str, int, float, bool, type(None)),
        },
    }
    for table, fields in json_fields.items():
        selected = ", ".join(("rowid AS qa_rowid", *fields))
        for row in evaluation.execute(
            f'SELECT {selected} FROM "{table}" ORDER BY rowid'
        ):
            for field in fields:
                _json_value(
                    row[field],
                    f"Evaluation {table} rowid={row['qa_rowid']}.{field}",
                    expected_type=fields[field],
                )
    return int(
        evaluation.execute("SELECT COUNT(*) FROM search_sessions").fetchone()[0]
    )


def _run_qa(
    db_path: Path,
    artifacts_db_path: Path | None,
    evaluation_db_path: Path | None,
) -> int:
    core_path = _resolved(db_path)
    defaults = storage_database_paths(core_path)
    artifacts_path = (
        _resolved(artifacts_db_path)
        if artifacts_db_path is not None
        else defaults.artifacts
    )
    evaluation_path = (
        _resolved(evaluation_db_path)
        if evaluation_db_path is not None
        else defaults.evaluation
    )

    with ExitStack() as stack:
        core = _open_read_only(core_path, "Core")
        stack.callback(core.close)
        _integrity_check(core, "Core")
        catalog_uuid = _current_structure(
            validate_core_schema,
            core,
            "Core",
            database_path=core_path,
        )
        _foreign_key_check(core, "Core")
        tracks = _track_identities(core, catalog_uuid=catalog_uuid)
        _validate_core_json(core)
        _validate_core_analysis(core, tracks)
        _validate_classifier_scores(core, tracks)

        artifacts = _open_read_only(artifacts_path, "required Artifacts")
        stack.callback(artifacts.close)
        _integrity_check(artifacts, "Artifacts")
        _current_structure(
            validate_artifacts_sidecar_schema,
            artifacts,
            "Artifacts",
            database_path=artifacts_path,
            expected_catalog_uuid=catalog_uuid,
        )
        _foreign_key_check(artifacts, "Artifacts")
        artifact_counts = _validate_artifacts(artifacts, tracks)

        evaluation_present = evaluation_path.is_file()
        evaluation_sessions = 0
        if evaluation_path.exists() and not evaluation_present:
            raise QAError(f"Evaluation sidecar path is not a file: {evaluation_path}")
        if evaluation_present:
            evaluation = _open_read_only(evaluation_path, "Evaluation")
            stack.callback(evaluation.close)
            _integrity_check(evaluation, "Evaluation")
            _current_structure(
                validate_evaluation_sidecar_schema,
                evaluation,
                "Evaluation",
                database_path=evaluation_path,
                expected_catalog_uuid=catalog_uuid,
            )
            _foreign_key_check(evaluation, "Evaluation")
            evaluation_sessions = _validate_evaluation_data(evaluation, tracks)

        track_count = len(tracks)

    print("QA PASSED", flush=True)
    print(f"Core: {core_path}, tracks={track_count}", flush=True)
    artifact_summary = ", ".join(
        f"{table}={artifact_counts[table]}" for table in _ARTIFACT_TABLES
    )
    print(f"Artifacts: {artifacts_path}, {artifact_summary}", flush=True)
    if evaluation_present:
        print(
            f"Evaluation: {evaluation_path}, search_sessions={evaluation_sessions}",
            flush=True,
        )
    else:
        print(f"Evaluation: not present ({evaluation_path})", flush=True)
    return 0


def run_qa(
    db_path: Path,
    artifacts_db_path: Path | None,
    evaluation_db_path: Path | None,
) -> int:
    """Run QA without creating or changing any database file."""

    try:
        return _run_qa(db_path, artifacts_db_path, evaluation_db_path)
    except (QAError, sqlite3.Error, OSError, TypeError, ValueError) as error:
        return _fail(str(error))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only structural and data-integrity QA for a library bundle.",
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the Core SQLite database.",
    )
    parser.add_argument(
        "--artifacts-db",
        metavar="PATH",
        default=None,
        help=(
            "Required Artifacts sidecar path. By default, library.sqlite "
            "uses adjacent library.artifacts.sqlite."
        ),
    )
    parser.add_argument(
        "--evaluation-db",
        metavar="PATH",
        default=None,
        help=(
            "Optional Evaluation sidecar path. By default, library.sqlite "
            "uses adjacent library.evaluation.sqlite and absence is allowed."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_qa(
        db_path=Path(args.db),
        artifacts_db_path=(
            Path(args.artifacts_db) if args.artifacts_db is not None else None
        ),
        evaluation_db_path=(
            Path(args.evaluation_db) if args.evaluation_db is not None else None
        ),
    )


if __name__ == "__main__":
    sys.exit(main())

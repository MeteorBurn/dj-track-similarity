"""Read-only QA for one clean v7 library bundle.

Usage:
    python scripts/qa_schema_v7.py --db PATH [--artifacts-db PATH]
        [--evaluation-db PATH]

The Artifacts sidecar is required.  Its canonical default is derived by
``storage_database_paths`` (for example, ``library.sqlite`` binds to
``library.artifacts.sqlite``).  The Evaluation sidecar is optional and is
validated only when its file exists.
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

from dj_track_similarity.analysis_contracts import (  # noqa: E402
    FLOAT32_LE_ENCODING,
    ContractIdentity,
    ContractRegistryError,
    read_registered_contract,
)
from dj_track_similarity.analysis_models import (  # noqa: E402
    ACTIVE_CONTRACT_SETTING_PREFIX,
    AnalysisOutput,
    active_classifier_required_outputs_hashes,
)
from dj_track_similarity.db_artifacts import (  # noqa: E402
    validate_artifacts_sidecar_schema,
)
from dj_track_similarity.db_evaluation_sidecar import (  # noqa: E402
    validate_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import (  # noqa: E402
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    validate_core_schema,
)
from dj_track_similarity.db_storage import storage_database_paths  # noqa: E402


_EMBEDDING_TABLE_FAMILIES: Mapping[str, str] = {
    "maest_embeddings": "maest",
    "mert_embeddings": "mert",
    "muq_embeddings": "muq",
    "clap_embeddings": "clap",
    "sonara_similarity_embeddings": "sonara",
}
_ARTIFACT_TABLE_CONTRACTS: Mapping[str, tuple[str, str]] = {
    **{
        table: (family, "embedding")
        for table, family in _EMBEDDING_TABLE_FAMILIES.items()
    },
    "sonara_timeline": ("sonara", "timeline"),
    "sonara_fingerprints": ("sonara", "fingerprint"),
}
_SONARA_SHORT_VECTORS: Mapping[str, int] = {
    "mfcc_mean_blob": 13,
    "chroma_mean_blob": 12,
    "spectral_contrast_mean_blob": 7,
}
_PROBABILITY_TOLERANCE = 1e-6
_L2_RELATIVE_TOLERANCE = 1e-4
_L2_ABSOLUTE_TOLERANCE = 1e-5


class QAError(RuntimeError):
    """A user-facing v7 QA failure."""


def _fail(reason: str) -> int:
    print(f"FAIL: {reason}", flush=True)
    return 1


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _open_read_only(path: Path, label: str) -> sqlite3.Connection:
    if not path.is_file():
        raise QAError(f"{label} database not found: {path}")
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
        )
    except sqlite3.Error as error:
        raise QAError(f"cannot open {label} database {path}: {error}") from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    return connection


def _quick_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA quick_check").fetchall()
    failures = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    if failures or not rows:
        detail = failures[0] if failures else "no result"
        raise QAError(f"{label} quick_check failed: {detail}")


def _foreign_key_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        row = rows[0]
        raise QAError(
            f"{label} foreign-key violation: "
            f"table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
        )


def _canonical_schema(
    validator: Callable[..., str],
    connection: sqlite3.Connection,
    label: str,
    *,
    expected_catalog_uuid: str | None = None,
) -> str:
    try:
        if expected_catalog_uuid is None:
            result = validator(connection)
        else:
            result = validator(
                connection,
                expected_catalog_uuid=expected_catalog_uuid,
            )
    except (RuntimeError, ValueError, sqlite3.Error) as error:
        raise QAError(f"{label} schema validation failed: {error}") from error
    return str(result)


def _load_contract_registry(
    core: sqlite3.Connection,
) -> dict[str, ContractIdentity]:
    contracts: dict[str, ContractIdentity] = {}
    rows = core.execute(
        "SELECT contract_hash FROM contracts ORDER BY contract_hash"
    ).fetchall()
    for row in rows:
        contract_hash = row["contract_hash"]
        if not isinstance(contract_hash, str) or not contract_hash:
            raise QAError("Core contracts contains an invalid contract_hash")
        try:
            identity = read_registered_contract(core, contract_hash)
        except ContractRegistryError as error:
            raise QAError(f"Core contract registry invalid: {error}") from error
        if identity is None:
            raise QAError(f"Core contract registry lookup failed for {contract_hash!r}")
        contracts[contract_hash] = identity
    return contracts


def _required_contract(
    contracts: Mapping[str, ContractIdentity],
    contract_hash: object,
    *,
    context: str,
    family: str,
    output_kind: str,
) -> ContractIdentity:
    if not isinstance(contract_hash, str):
        raise QAError(f"{context}: contract_hash is not text")
    identity = contracts.get(contract_hash)
    if identity is None:
        raise QAError(f"{context}: unregistered contract_hash {contract_hash!r}")
    if identity.analysis_family != family or identity.output_kind != output_kind:
        raise QAError(
            f"{context}: contract {contract_hash!r} has identity "
            f"{identity.analysis_family}/{identity.output_kind}, expected "
            f"{family}/{output_kind}"
        )
    return identity


def _active_sonara_release(core: sqlite3.Connection) -> str | None:
    row = core.execute(
        """
        SELECT setting_value
        FROM library_settings
        WHERE setting_key = ?
        """,
        (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
    ).fetchone()
    if row is None:
        return None
    value = row["setting_value"]
    if not isinstance(value, str) or not value.strip():
        raise QAError(
            f"Core library_settings[{SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY!r}] "
            "must be non-empty"
        )
    return value.strip()


def _require_active_sonara_contract(
    identity: ContractIdentity,
    active_release: str | None,
    context: str,
) -> None:
    if active_release is None:
        raise QAError(
            f"{context}: SONARA data exists but "
            f"library_settings[{SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY!r}] "
            "is missing"
        )
    if identity.release_hash != active_release:
        raise QAError(
            f"{context}: SONARA release mismatch; "
            f"contract={identity.release_hash!r}, active={active_release!r}"
        )


def _track_identities(
    core: sqlite3.Connection,
) -> dict[int, tuple[str, int]]:
    tracks: dict[int, tuple[str, int]] = {}
    for row in core.execute(
        """
        SELECT track_id, track_uuid, content_generation
        FROM tracks
        ORDER BY track_id
        """
    ):
        track_id = int(row["track_id"])
        track_uuid = row["track_uuid"]
        generation = int(row["content_generation"])
        if not isinstance(track_uuid, str) or not track_uuid.strip():
            raise QAError(f"Core tracks track_id={track_id}: invalid track_uuid")
        if generation < 1:
            raise QAError(
                f"Core tracks track_id={track_id}: invalid content_generation"
            )
        tracks[track_id] = (track_uuid, generation)
    return tracks


def _require_current_track(
    tracks: Mapping[int, tuple[str, int]],
    *,
    track_id: object,
    track_uuid: object | None,
    content_generation: object,
    context: str,
) -> None:
    if isinstance(track_id, bool) or not isinstance(track_id, int):
        raise QAError(f"{context}: invalid track_id")
    current = tracks.get(track_id)
    if current is None:
        raise QAError(f"{context}: orphan track_id={track_id}")
    current_uuid, current_generation = current
    if track_uuid is not None and track_uuid != current_uuid:
        raise QAError(
            f"{context}: track_uuid mismatch for track_id={track_id}; "
            f"artifact={track_uuid!r}, Core={current_uuid!r}"
        )
    if (
        isinstance(content_generation, bool)
        or not isinstance(content_generation, int)
        or content_generation != current_generation
    ):
        raise QAError(
            f"{context}: content_generation mismatch for track_id={track_id}; "
            f"stored={content_generation!r}, Core={current_generation}"
        )


def _float32_values(blob: object, dim: int, context: str) -> list[float]:
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise QAError(f"{context}: BLOB value is not bytes")
    raw = bytes(blob)
    expected_length = dim * 4
    if len(raw) != expected_length:
        raise QAError(
            f"{context}: BLOB length mismatch; "
            f"stored={len(raw)}, expected={expected_length}"
        )
    try:
        values = [value for (value,) in struct.iter_unpack("<f", raw)]
    except struct.error as error:
        raise QAError(f"{context}: invalid float32-le BLOB") from error
    if len(values) != dim:
        raise QAError(
            f"{context}: decoded dimension mismatch; "
            f"stored={len(values)}, expected={dim}"
        )
    if not all(math.isfinite(value) for value in values):
        raise QAError(f"{context}: BLOB contains non-finite float32 values")
    return values


def _validate_core_analysis(
    core: sqlite3.Connection,
    tracks: Mapping[int, tuple[str, int]],
    contracts: Mapping[str, ContractIdentity],
    active_release: str | None,
) -> set[int]:
    current_sonara_tracks: set[int] = set()
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
        identity = _required_contract(
            contracts,
            row["contract_hash"],
            context=context,
            family="sonara",
            output_kind="core",
        )
        _require_active_sonara_contract(identity, active_release, context)
        for column, dim in _SONARA_SHORT_VECTORS.items():
            _float32_values(row[column], dim, f"{context}.{column}")
        current_sonara_tracks.add(int(track_id))

    for row in core.execute("SELECT * FROM maest_scores ORDER BY track_id"):
        track_id = row["track_id"]
        context = f"Core maest_scores track_id={track_id}"
        _require_current_track(
            tracks,
            track_id=track_id,
            track_uuid=None,
            content_generation=row["content_generation"],
            context=context,
        )
        _required_contract(
            contracts,
            row["contract_hash"],
            context=context,
            family="maest",
            output_kind="analysis",
        )
    return current_sonara_tracks


def _non_empty_classifier_text(row: sqlite3.Row, field: str, context: str) -> str:
    value = row[field]
    if not isinstance(value, str) or not value.strip():
        raise QAError(f"{context}: {field} must be non-empty text")
    return value


def _classifier_probability(
    value: object,
    *,
    label: str,
    context: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QAError(f"{context}: probability for {label!r} is not numeric")
    probability = float(value)
    if not math.isfinite(probability):
        raise QAError(f"{context}: probability for {label!r} is non-finite")
    if probability < 0.0 or probability > 1.0:
        raise QAError(f"{context}: probability for {label!r} is outside [0, 1]")
    return probability


def _finite_unit_interval(value: object, field: str, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QAError(f"{context}: {field} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise QAError(f"{context}: {field} is non-finite")
    if result < 0.0 or result > 1.0:
        raise QAError(f"{context}: {field} is outside [0, 1]")
    return result


def _score_bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def _validate_classifier_scores(
    core: sqlite3.Connection,
    tracks: Mapping[int, tuple[str, int]],
    active_release: str | None,
    current_sonara_tracks: set[int],
    active_required_outputs_hashes: frozenset[str],
) -> None:
    identities: dict[str, tuple[object, ...]] = {}
    rows = core.execute(
        "SELECT * FROM classifier_scores ORDER BY classifier_key, track_id"
    ).fetchall()
    for row in rows:
        track_id = row["track_id"]
        classifier_key = _non_empty_classifier_text(
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
            track_uuid=None,
            content_generation=row["content_generation"],
            context=context,
        )
        model_id = _non_empty_classifier_text(row, "model_id", context)
        feature_set = _non_empty_classifier_text(row, "feature_set", context)
        feature_manifest_hash = _non_empty_classifier_text(
            row,
            "feature_manifest_hash",
            context,
        )
        required_outputs_hash = _non_empty_classifier_text(
            row,
            "required_outputs_hash",
            context,
        )
        if required_outputs_hash not in active_required_outputs_hashes:
            raise QAError(
                f"{context}: required_outputs_hash does not match active "
                "analysis contracts"
            )
        positive_label = _non_empty_classifier_text(
            row,
            "positive_label",
            context,
        )
        predicted_class = _non_empty_classifier_text(
            row,
            "predicted_class",
            context,
        )

        uses_sonara = row["uses_sonara"]
        if uses_sonara not in (0, 1):
            raise QAError(f"{context}: uses_sonara must be 0 or 1")
        release_hash = row["sonara_release_hash"]
        if uses_sonara:
            if active_release is None:
                raise QAError(
                    f"{context}: SONARA-dependent score exists without an "
                    "active SONARA release"
                )
            if release_hash != active_release:
                raise QAError(
                    f"{context}: sonara_release_hash mismatch; "
                    f"stored={release_hash!r}, active={active_release!r}"
                )
            if track_id not in current_sonara_tracks:
                raise QAError(
                    f"{context}: SONARA-dependent score has no current SONARA Core row"
                )
        elif release_hash is not None:
            raise QAError(f"{context}: non-SONARA score has sonara_release_hash")

        identity = (
            model_id,
            feature_set,
            feature_manifest_hash,
            required_outputs_hash,
            int(uses_sonara),
            release_hash,
            positive_label,
        )
        previous = identities.setdefault(classifier_key, identity)
        if previous != identity:
            raise QAError(
                f"{context}: mixed classifier identity for one classifier_key"
            )

        try:
            raw_probabilities = json.loads(row["probabilities_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise QAError(f"{context}: invalid probabilities_json") from error
        if not isinstance(raw_probabilities, dict) or not raw_probabilities:
            raise QAError(f"{context}: probabilities_json must be a non-empty object")
        probabilities: dict[str, float] = {}
        for label, value in raw_probabilities.items():
            if not isinstance(label, str) or not label.strip():
                raise QAError(f"{context}: probability labels must be non-empty text")
            probabilities[label] = _classifier_probability(
                value,
                label=label,
                context=context,
            )
        if not math.isclose(
            math.fsum(probabilities.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(f"{context}: probabilities do not sum to 1")

        if positive_label not in probabilities:
            raise QAError(
                f"{context}: positive_label is absent from probabilities_json"
            )
        if predicted_class not in probabilities:
            raise QAError(
                f"{context}: predicted_class is absent from probabilities_json"
            )
        max_probability = max(probabilities.values())
        if not math.isclose(
            probabilities[predicted_class],
            max_probability,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        ):
            raise QAError(f"{context}: predicted_class is not an argmax")

        score = _finite_unit_interval(row["score"], "score", context)
        confidence = _finite_unit_interval(
            row["confidence"],
            "confidence",
            context,
        )
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
            max_probability,
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


def _validate_embedding_row(
    row: sqlite3.Row,
    identity: ContractIdentity,
    context: str,
) -> None:
    dim = row["dim"]
    if isinstance(dim, bool) or not isinstance(dim, int) or dim <= 0:
        raise QAError(f"{context}: dim must be a positive integer")
    if identity.dim != dim:
        raise QAError(f"{context}: dim mismatch; row={dim}, contract={identity.dim}")
    if identity.encoding != FLOAT32_LE_ENCODING:
        raise QAError(f"{context}: contract encoding is not {FLOAT32_LE_ENCODING!r}")
    normalization = row["normalization"]
    if normalization != identity.normalization:
        raise QAError(
            f"{context}: normalization mismatch; "
            f"row={normalization!r}, contract={identity.normalization!r}"
        )
    values = _float32_values(row["embedding_blob"], dim, context)
    if normalization == "l2":
        norm = math.sqrt(math.fsum(value * value for value in values))
        if not math.isclose(
            norm,
            1.0,
            rel_tol=_L2_RELATIVE_TOLERANCE,
            abs_tol=_L2_ABSOLUTE_TOLERANCE,
        ):
            raise QAError(
                f"{context}: l2 embedding is not unit-normalized; norm={norm}"
            )


def _validate_artifacts(
    artifacts: sqlite3.Connection,
    tracks: Mapping[int, tuple[str, int]],
    contracts: Mapping[str, ContractIdentity],
    active_release: str | None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, (family, output_kind) in _ARTIFACT_TABLE_CONTRACTS.items():
        rows = artifacts.execute(
            f'SELECT * FROM "{table}" ORDER BY track_id'
        ).fetchall()
        counts[table] = len(rows)
        for row in rows:
            track_id = row["track_id"]
            context = f"Artifacts {table} track_id={track_id}"
            _require_current_track(
                tracks,
                track_id=track_id,
                track_uuid=row["track_uuid"],
                content_generation=row["content_generation"],
                context=context,
            )
            identity = _required_contract(
                contracts,
                row["contract_hash"],
                context=context,
                family=family,
                output_kind=output_kind,
            )
            if family == "sonara":
                _require_active_sonara_contract(
                    identity,
                    active_release,
                    context,
                )

            if output_kind == "embedding":
                _validate_embedding_row(row, identity, context)
            elif output_kind == "timeline":
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError) as error:
                    raise QAError(f"{context}: invalid payload_json") from error
                if not isinstance(payload, dict):
                    raise QAError(f"{context}: payload_json must contain an object")
            else:
                word_count = row["word_count"]
                if (
                    isinstance(word_count, bool)
                    or not isinstance(word_count, int)
                    or word_count < 0
                ):
                    raise QAError(
                        f"{context}: word_count must be a non-negative integer"
                    )
                if row["byte_order"] != "little":
                    raise QAError(f"{context}: byte_order must be 'little'")
                blob = row["fingerprint_blob"]
                if not isinstance(blob, (bytes, bytearray, memoryview)):
                    raise QAError(f"{context}: fingerprint_blob is not bytes")
                if len(blob) != word_count * 4:
                    raise QAError(f"{context}: fingerprint BLOB length mismatch")
    return counts


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
        _quick_check(core, "Core")
        catalog_uuid = _canonical_schema(
            validate_core_schema,
            core,
            "Core",
        )
        _foreign_key_check(core, "Core")

        tracks = _track_identities(core)
        contracts = _load_contract_registry(core)
        active_release = _active_sonara_release(core)
        active_outputs: list[AnalysisOutput] = []
        for row in core.execute(
            """
            SELECT setting_value
            FROM library_settings
            WHERE setting_key LIKE ?
            ORDER BY setting_key
            """,
            (f"{ACTIVE_CONTRACT_SETTING_PREFIX}.%",),
        ):
            identity = contracts.get(str(row["setting_value"]))
            if identity is None:
                raise QAError("active analysis setting references an unknown contract")
            if (
                identity.analysis_family == "sonara"
                and identity.release_hash != active_release
            ):
                raise QAError(
                    "active SONARA contract release mismatch with active release"
                )
            active_outputs.append(AnalysisOutput(identity))
        active_required_outputs_hashes = active_classifier_required_outputs_hashes(
            active_outputs
        )
        current_sonara_tracks = _validate_core_analysis(
            core,
            tracks,
            contracts,
            active_release,
        )
        _validate_classifier_scores(
            core,
            tracks,
            active_release,
            current_sonara_tracks,
            active_required_outputs_hashes,
        )

        artifacts = _open_read_only(artifacts_path, "required Artifacts")
        stack.callback(artifacts.close)
        _quick_check(artifacts, "Artifacts")
        _canonical_schema(
            validate_artifacts_sidecar_schema,
            artifacts,
            "Artifacts",
            expected_catalog_uuid=catalog_uuid,
        )
        _foreign_key_check(artifacts, "Artifacts")
        artifact_counts = _validate_artifacts(
            artifacts,
            tracks,
            contracts,
            active_release,
        )

        evaluation_present = evaluation_path.is_file()
        evaluation_sessions = 0
        if evaluation_path.exists() and not evaluation_present:
            raise QAError(f"Evaluation sidecar path is not a file: {evaluation_path}")
        if evaluation_present:
            evaluation = _open_read_only(evaluation_path, "Evaluation")
            stack.callback(evaluation.close)
            _quick_check(evaluation, "Evaluation")
            _canonical_schema(
                validate_evaluation_sidecar_schema,
                evaluation,
                "Evaluation",
                expected_catalog_uuid=catalog_uuid,
            )
            _foreign_key_check(evaluation, "Evaluation")
            evaluation_sessions = int(
                evaluation.execute("SELECT COUNT(*) FROM search_sessions").fetchone()[0]
            )

        track_count = len(tracks)
        contract_count = len(contracts)

    print("QA PASSED", flush=True)
    print(
        f"Core: {core_path}, tracks={track_count}, contracts={contract_count}",
        flush=True,
    )
    artifact_summary = ", ".join(
        f"{table}={artifact_counts[table]}" for table in _ARTIFACT_TABLE_CONTRACTS
    )
    print(
        f"Artifacts: {artifacts_path}, {artifact_summary}",
        flush=True,
    )
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
    """Run v7 QA without creating or changing any database file."""

    try:
        return _run_qa(
            db_path,
            artifacts_db_path,
            evaluation_db_path,
        )
    except (QAError, sqlite3.Error, OSError, TypeError, ValueError) as error:
        return _fail(str(error))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only QA for a clean v7 library bundle.",
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the v7 Core SQLite database.",
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

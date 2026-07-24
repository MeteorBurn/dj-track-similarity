"""Canonical v7 AnalysisRepository.

All writes are fenced by the active immutable contract, catalog UUID, track
UUID, and content generation.  Core ``BEGIN IMMEDIATE`` is the coordinator for
each write batch; the required Artifacts database is opened explicitly and
never attached as a legacy sidecar.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import fields
from types import MappingProxyType

import numpy as np

from .analysis_contracts import (
    OUTPUT_KINDS_BY_FAMILY,
    read_registered_contract,
    register_contract,
    utc_timestamp,
)
from .analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisResetResult,
    AnalysisTarget,
    AnalysisVectorRow,
    AnalysisWriteResult,
    ClassifierCandidate,
    ClassifierFeatureRow,
    ClassifierReadiness,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingWrite,
    InactiveAnalysisOutputError,
    MaestWrite,
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    SonaraFeatureRow,
    SonaraWrite,
    StaleAnalysisTargetError,
    active_classifier_required_outputs_hashes,
    active_contract_setting_key,
    validate_production_contract,
)
from .db_analysis_candidates import (
    artifact_table_for_output,
    collect_analysis_candidates,
    missing_outputs_for_target,
    normalize_analysis_outputs,
    read_current_track_rows,
    ready_target_keys_by_output,
    require_active_analysis_outputs,
    target_from_track_row,
)
from .db_artifacts import (
    ArtifactTrackIdentity,
    read_valid_embedding,
    validate_fingerprint_row_payload,
    validate_storage_binding,
    validate_timeline_row_payload,
    write_valid_embedding_in_transaction,
)
from .db_schema_v7 import ClassifierScoreV7
from .maest_analysis_validation import validate_maest_analysis_row
from .sonara_core_validation import (
    SONARA_CORE_COLUMNS,
    SONARA_CORE_VECTOR_DIMS,
    validate_sonara_core_row,
)


_CLASSIFIER_SCORE_COLUMNS = tuple(field.name for field in fields(ClassifierScoreV7))
_SONARA_IDENTITY_COLUMNS = {
    "track_id",
    "content_generation",
    "contract_hash",
}
_CLASSIFIER_PROBABILITY_TOLERANCE = 1e-9


def _catalog_uuid(core_connection: sqlite3.Connection) -> str:
    rows = core_connection.execute(
        "SELECT singleton_id, catalog_uuid FROM library_catalog"
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError("library_catalog must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("library catalog UUID is empty")
    return catalog_uuid


def _artifact_track(target: AnalysisTarget) -> ArtifactTrackIdentity:
    return ArtifactTrackIdentity(
        catalog_uuid=target.catalog_uuid,
        track_id=target.track_id,
        track_uuid=target.track_uuid,
        content_generation=target.content_generation,
    )


def _require_current_target(
    core_connection: sqlite3.Connection,
    target: AnalysisTarget,
    *,
    catalog_uuid: str,
) -> None:
    if target.catalog_uuid != catalog_uuid:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: catalog_uuid mismatch"
        )
    row = core_connection.execute(
        """
        SELECT track_uuid, content_generation, missing_since
        FROM tracks
        WHERE track_id = ?
        """,
        (target.track_id,),
    ).fetchone()
    if row is None:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: unknown track_id"
        )
    if str(row[0]) != target.track_uuid:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: track_uuid mismatch"
        )
    if int(row[1]) != target.content_generation:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: content_generation mismatch"
        )
    if row[2] is not None:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: track is missing"
        )


def _delete_stale_artifact_generation(
    artifacts_connection: sqlite3.Connection,
    *,
    table: str,
    target: AnalysisTarget,
) -> int:
    cursor = artifacts_connection.execute(
        f"""
        DELETE FROM {table}
        WHERE track_id = ?
          AND content_generation <> ?
        """,
        (target.track_id, target.content_generation),
    )
    return max(0, int(cursor.rowcount))


def _savepoint(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection | None,
    index: int,
) -> str:
    name = f"analysis_item_{index}"
    core_connection.execute(f"SAVEPOINT {name}")
    if artifacts_connection is not None:
        artifacts_connection.execute(f"SAVEPOINT {name}")
    return name


def _rollback_savepoint(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection | None,
    name: str,
) -> None:
    if artifacts_connection is not None:
        artifacts_connection.execute(f"ROLLBACK TO {name}")
        artifacts_connection.execute(f"RELEASE {name}")
    core_connection.execute(f"ROLLBACK TO {name}")
    core_connection.execute(f"RELEASE {name}")


def _release_savepoint(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection | None,
    name: str,
) -> None:
    if artifacts_connection is not None:
        artifacts_connection.execute(f"RELEASE {name}")
    core_connection.execute(f"RELEASE {name}")


def _error_result(
    target: AnalysisTarget,
    error: Exception,
) -> AnalysisWriteResult:
    return AnalysisWriteResult(
        target=target,
        error=f"{type(error).__name__}: {error}",
    )


def _commit_coordinated(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection | None,
) -> None:
    # Optional artifacts commit first.  If a process dies between commits, Core
    # remains missing and candidate readiness safely schedules the item again.
    if artifacts_connection is not None:
        artifacts_connection.commit()
    core_connection.commit()


def _rollback_coordinated(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection | None,
) -> None:
    if artifacts_connection is not None and artifacts_connection.in_transaction:
        artifacts_connection.rollback()
    if core_connection.in_transaction:
        core_connection.rollback()


def _upsert_sonara_core(
    core_connection: sqlite3.Connection,
    *,
    write: SonaraWrite,
) -> None:
    row = write.core
    valid, reason = validate_sonara_core_row(
        row,
        expected_contract=write.core_contract,
        expected_track_id=write.target.track_id,
        expected_content_generation=write.target.content_generation,
    )
    if not valid:
        raise ValueError(f"invalid SONARA Core row: {reason}")
    placeholders = ", ".join("?" for _ in SONARA_CORE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in SONARA_CORE_COLUMNS
        if column != "track_id"
    )
    core_connection.execute(
        f"""
        INSERT INTO sonara ({", ".join(SONARA_CORE_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(track_id) DO UPDATE SET {updates}
        """,
        tuple(getattr(row, column) for column in SONARA_CORE_COLUMNS),
    )


def _upsert_maest_analysis(
    core_connection: sqlite3.Connection,
    *,
    write: MaestWrite,
) -> None:
    row = {
        "track_id": write.target.track_id,
        "content_generation": write.target.content_generation,
        "contract_hash": write.analysis_contract.contract_hash,
        "syncopated_rhythm": (
            None if write.syncopated_rhythm is None else int(write.syncopated_rhythm)
        ),
        "genres_json": write.genres_json,
        "analyzed_at": write.analyzed_at,
    }
    valid, reason = validate_maest_analysis_row(
        row,
        expected_contract=write.analysis_contract,
        expected_track_id=write.target.track_id,
        expected_content_generation=write.target.content_generation,
    )
    if not valid:
        raise ValueError(f"invalid MAEST analysis row: {reason}")
    core_connection.execute(
        """
        INSERT INTO maest_scores (
            track_id, content_generation, contract_hash,
            syncopated_rhythm, genres_json, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            content_generation = excluded.content_generation,
            contract_hash = excluded.contract_hash,
            syncopated_rhythm = excluded.syncopated_rhythm,
            genres_json = excluded.genres_json,
            analyzed_at = excluded.analyzed_at
        """,
        tuple(
            row[column]
            for column in (
                "track_id",
                "content_generation",
                "contract_hash",
                "syncopated_rhythm",
                "genres_json",
                "analyzed_at",
            )
        ),
    )


def _upsert_sonara_timeline(
    artifacts_connection: sqlite3.Connection,
    *,
    write: SonaraWrite,
) -> None:
    timeline = write.timeline
    if timeline is None:
        return
    payload_json = timeline.payload_json
    valid, reason = validate_timeline_row_payload(
        row={
            "track_id": write.target.track_id,
            "track_uuid": write.target.track_uuid,
            "content_generation": write.target.content_generation,
            "contract_hash": timeline.contract.contract_hash,
            "payload_json": payload_json,
        },
        expected_contract=timeline.contract,
        expected_track=_artifact_track(write.target),
    )
    if not valid:
        raise ValueError(f"invalid SONARA timeline payload: {reason}")
    _delete_stale_artifact_generation(
        artifacts_connection,
        table="sonara_timeline",
        target=write.target,
    )
    artifacts_connection.execute(
        """
        INSERT INTO sonara_timeline (
            track_id, track_uuid, content_generation, contract_hash,
            payload_json, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            content_generation = excluded.content_generation,
            contract_hash = excluded.contract_hash,
            payload_json = excluded.payload_json,
            analyzed_at = excluded.analyzed_at
        """,
        (
            write.target.track_id,
            write.target.track_uuid,
            write.target.content_generation,
            timeline.contract.contract_hash,
            payload_json,
            timeline.analyzed_at,
        ),
    )


def _upsert_sonara_fingerprint(
    artifacts_connection: sqlite3.Connection,
    *,
    write: SonaraWrite,
) -> None:
    fingerprint = write.fingerprint
    if fingerprint is None:
        return
    word_count = int(fingerprint.words.shape[0])
    fingerprint_blob = fingerprint.fingerprint_blob
    valid, reason = validate_fingerprint_row_payload(
        row={
            "track_id": write.target.track_id,
            "track_uuid": write.target.track_uuid,
            "content_generation": write.target.content_generation,
            "contract_hash": fingerprint.contract.contract_hash,
            "fingerprint_version": fingerprint.fingerprint_version,
            "word_count": word_count,
            "byte_order": "little",
            "fingerprint_blob": fingerprint_blob,
        },
        expected_contract=fingerprint.contract,
        expected_track=_artifact_track(write.target),
    )
    if not valid:
        raise ValueError(f"invalid SONARA fingerprint payload: {reason}")
    _delete_stale_artifact_generation(
        artifacts_connection,
        table="sonara_fingerprints",
        target=write.target,
    )
    artifacts_connection.execute(
        """
        INSERT INTO sonara_fingerprints (
            track_id, track_uuid, content_generation, contract_hash,
            fingerprint_version, word_count, byte_order,
            fingerprint_blob, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'little', ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            content_generation = excluded.content_generation,
            contract_hash = excluded.contract_hash,
            fingerprint_version = excluded.fingerprint_version,
            word_count = excluded.word_count,
            byte_order = excluded.byte_order,
            fingerprint_blob = excluded.fingerprint_blob,
            analyzed_at = excluded.analyzed_at
        """,
        (
            write.target.track_id,
            write.target.track_uuid,
            write.target.content_generation,
            fingerprint.contract.contract_hash,
            fingerprint.fingerprint_version,
            word_count,
            fingerprint_blob,
            fingerprint.analyzed_at,
        ),
    )


def _upsert_classifier_score(
    core_connection: sqlite3.Connection,
    score: ClassifierScoreV7,
) -> None:
    placeholders = ", ".join("?" for _ in _CLASSIFIER_SCORE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in _CLASSIFIER_SCORE_COLUMNS
        if column not in {"track_id", "classifier_key"}
    )
    core_connection.execute(
        f"""
        INSERT INTO classifier_scores (
            {", ".join(_CLASSIFIER_SCORE_COLUMNS)}
        ) VALUES ({placeholders})
        ON CONFLICT(track_id, classifier_key) DO UPDATE SET {updates}
        """,
        tuple(getattr(score, column) for column in _CLASSIFIER_SCORE_COLUMNS),
    )


def _validate_classifier_score(
    score: ClassifierScoreV7,
    specification: ClassifierSpecification,
) -> None:
    for field_name in (
        "classifier_key",
        "model_id",
        "feature_set",
        "feature_manifest_hash",
        "required_outputs_hash",
        "positive_label",
        "predicted_class",
        "analyzed_at",
    ):
        value = getattr(score, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"classifier score {field_name} is required")
    if score.uses_sonara not in {0, 1}:
        raise ValueError("classifier score uses_sonara must be 0 or 1")
    if score.score_bucket not in {"low", "medium", "high"}:
        raise ValueError("classifier score_bucket is invalid")
    for field_name in ("score", "confidence"):
        value = getattr(score, field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"classifier {field_name} must be a finite number between 0 and 1"
            )
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(
                f"classifier {field_name} must be finite and between 0 and 1"
            )
    try:
        probabilities = json.loads(score.probabilities_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("classifier probabilities_json must be valid JSON") from error
    if not isinstance(probabilities, dict):
        raise ValueError("classifier probabilities_json must contain an object")
    if not probabilities:
        raise ValueError("classifier probabilities_json must not be empty")
    normalized_probabilities: dict[str, float] = {}
    for label, value in probabilities.items():
        if not isinstance(label, str) or not label:
            raise ValueError("classifier probability labels must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("classifier probabilities must be finite numbers")
        probability = float(value)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("classifier probabilities must be between 0 and 1")
        normalized_probabilities[label] = probability
    if set(normalized_probabilities) != set(specification.label_order):
        raise ValueError(
            "classifier probability labels do not match canonical label_order"
        )
    if not math.isclose(
        math.fsum(normalized_probabilities.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError("classifier probabilities must sum to 1")
    expected_class = max(
        specification.label_order,
        key=normalized_probabilities.__getitem__,
    )
    if score.predicted_class != expected_class:
        raise ValueError(
            "classifier predicted_class does not match canonical label-order argmax"
        )
    expected_score = normalized_probabilities[specification.positive_label]
    if not math.isclose(
        float(score.score),
        expected_score,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError(
            "classifier score does not equal the positive-label probability"
        )
    expected_confidence = max(normalized_probabilities.values())
    if not math.isclose(
        float(score.confidence),
        expected_confidence,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError("classifier confidence does not equal max(probabilities)")
    expected_bucket = (
        "high"
        if expected_score >= 0.7
        else "medium"
        if expected_score >= 0.3
        else "low"
    )
    if score.score_bucket != expected_bucket:
        raise ValueError("classifier score_bucket does not match the selected score")
    if score.uses_sonara == 1 and not score.sonara_release_hash:
        raise ValueError("SONARA-dependent classifier score requires release hash")
    if score.uses_sonara == 0 and score.sonara_release_hash is not None:
        raise ValueError("non-SONARA classifier score must not carry release hash")


def _active_classifier_hashes(
    core_connection: sqlite3.Connection,
) -> frozenset[str]:
    active_release_row = core_connection.execute(
        """
        SELECT setting_value
        FROM library_settings
        WHERE setting_key = ?
        """,
        (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
    ).fetchone()
    active_release = None if active_release_row is None else str(active_release_row[0])
    outputs: list[AnalysisOutput] = []
    for row in core_connection.execute(
        """
        SELECT setting_value
        FROM library_settings
        WHERE setting_key LIKE ?
        ORDER BY setting_key
        """,
        (f"{ACTIVE_CONTRACT_SETTING_PREFIX}.%",),
    ):
        identity = read_registered_contract(core_connection, str(row[0]))
        if identity is None:
            raise RuntimeError("active analysis setting references an unknown contract")
        validate_production_contract(identity)
        if (
            identity.analysis_family == "sonara"
            and identity.release_hash != active_release
        ):
            raise RuntimeError(
                "active SONARA contract does not match the active release"
            )
        outputs.append(AnalysisOutput(identity))
    return active_classifier_required_outputs_hashes(outputs)


def _delete_scores_with_inactive_required_outputs(
    core_connection: sqlite3.Connection,
) -> int:
    active_hashes = _active_classifier_hashes(core_connection)
    if not active_hashes:
        cursor = core_connection.execute("DELETE FROM classifier_scores")
    else:
        cursor = core_connection.execute(
            """
            DELETE FROM classifier_scores
            WHERE required_outputs_hash NOT IN (
                SELECT CAST(value AS TEXT)
                FROM json_each(?)
            )
            """,
            (
                json.dumps(
                    sorted(active_hashes),
                    separators=(",", ":"),
                ),
            ),
        )
    return max(0, int(cursor.rowcount))


def _selected_targets(
    core_connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    targets: Sequence[AnalysisTarget] | None,
) -> tuple[AnalysisTarget, ...]:
    if targets is None:
        return tuple(
            target_from_track_row(row, catalog_uuid=catalog_uuid)
            for row in read_current_track_rows(core_connection)
        )
    selected = tuple(targets)
    for target in selected:
        if not isinstance(target, AnalysisTarget):
            raise TypeError("targets must contain only AnalysisTarget values")
        _require_current_target(
            core_connection,
            target,
            catalog_uuid=catalog_uuid,
        )
    return selected


def _readonly_copy(vector: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(vector, dtype="<f4").copy()
    copied.setflags(write=False)
    return copied


def _sonara_feature_value(
    values: Mapping[str, object],
    key: str,
) -> float | None:
    field_name, separator, index_text = key.rpartition(":")
    if separator and index_text.isdigit():
        raw = values.get(field_name)
        if isinstance(raw, (tuple, list, np.ndarray)):
            index = int(index_text)
            if 0 <= index < len(raw):
                try:
                    number = float(raw[index])
                except (TypeError, ValueError):
                    return None
                return number if math.isfinite(number) else None
        return None
    raw = values.get(key)
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _vector_value(vector: np.ndarray, key: str) -> float | None:
    if not key.isdigit():
        return None
    index = int(key)
    if not 0 <= index < vector.shape[0]:
        return None
    number = float(vector[index])
    return number if math.isfinite(number) else None


def _canonical_sonara_release_outputs(
    outputs: Sequence[AnalysisOutput],
) -> tuple[AnalysisOutput, ...]:
    normalized = normalize_analysis_outputs(outputs)
    if any(output.contract.analysis_family != "sonara" for output in normalized):
        raise ValueError("SONARA release activation accepts only SONARA outputs")
    by_kind = {output.contract.output_kind: output for output in normalized}
    expected_kinds = ("core", "timeline", "embedding", "fingerprint")
    if set(by_kind) != set(expected_kinds):
        raise ValueError(
            "SONARA release activation requires exactly "
            "core, timeline, embedding, and fingerprint"
        )
    ordered = tuple(by_kind[kind] for kind in expected_kinds)
    for output in ordered:
        validate_production_contract(output.contract)

    from .sonara_contract import (
        SONARA_CORE_REQUESTED_FEATURES,
        SONARA_EMBEDDING_REQUESTED_FEATURES,
        SONARA_FINGERPRINT_REQUESTED_FEATURES,
        SONARA_TIMELINE_REQUESTED_FEATURES,
        SonaraRuntimeIdentity,
        build_sonara_contracts,
    )

    common = dict(by_kind["core"].contract.parameters)
    embedding = dict(by_kind["embedding"].contract.parameters)
    fingerprint = dict(by_kind["fingerprint"].contract.parameters)
    try:
        runtime = SonaraRuntimeIdentity(
            package_version=common["package_version"],
            package_build_id=common["package_build_id"],
            schema_version=common["schema_version"],
            mode=common["mode"],
            sample_rate_hz=common["sample_rate_hz"],
            bpm_min=common["bpm_min"],
            bpm_max=common["bpm_max"],
            project_feature_revision=common["project_feature_revision"],
            decoder_backend=common["decoder_backend"],
            execution_path=common["execution_path"],
            analysis_hop_samples=common["analysis_hop_samples"],
            unit_interval_clamp_policy=common["unit_interval_clamp_policy"],
            unit_interval_clamp_epsilon=common["unit_interval_clamp_epsilon"],
            unit_interval_clamp_fields=tuple(common["unit_interval_clamp_fields"]),
            vocalness_model_id=common["vocalness_model_id"],
            vocalness_model_build_id=common["vocalness_model_build_id"],
            embedding_version=embedding["embedding_version"],
            embedding_dim=embedding["embedding_dim"],
            embedding_normalization=embedding["embedding_normalization"],
            embedding_encoding=embedding["embedding_encoding"],
            fingerprint_version=fingerprint["fingerprint_version"],
            fingerprint_encoding=fingerprint["fingerprint_encoding"],
            fingerprint_byte_order=fingerprint["fingerprint_byte_order"],
            core_requested_features=SONARA_CORE_REQUESTED_FEATURES,
            timeline_requested_features=SONARA_TIMELINE_REQUESTED_FEATURES,
            embedding_requested_features=SONARA_EMBEDDING_REQUESTED_FEATURES,
            fingerprint_requested_features=SONARA_FINGERPRINT_REQUESTED_FEATURES,
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise ValueError(
            "SONARA output contracts do not contain one complete runtime identity"
        ) from error

    canonical = build_sonara_contracts(runtime)
    expected_by_kind = {
        contract.output_kind: contract for contract in canonical.identities
    }
    for output in ordered:
        expected = expected_by_kind[output.contract.output_kind]
        if output.contract.canonical_payload_json != expected.canonical_payload_json:
            raise ValueError(
                "SONARA output contract does not match the internally "
                f"derived canonical release: {output.contract.output_kind}"
            )
    return ordered


class AnalysisRepository:
    """Mixin implemented by :class:`LibraryDatabase`."""

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        family = str(analysis_family).strip().lower()
        kind = str(output_kind).strip().lower()
        if family not in OUTPUT_KINDS_BY_FAMILY:
            raise ValueError(f"unsupported analysis_family: {analysis_family!r}")
        if kind not in OUTPUT_KINDS_BY_FAMILY[family]:
            raise ValueError(
                f"unsupported output_kind {output_kind!r} "
                f"for analysis_family {family!r}"
            )
        setting_key = f"{ACTIVE_CONTRACT_SETTING_PREFIX}.{family}.{kind}"
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                row = core_connection.execute(
                    """
                    SELECT setting_value
                    FROM library_settings
                    WHERE setting_key = ?
                    """,
                    (setting_key,),
                ).fetchone()
                if row is None:
                    return None
                identity = read_registered_contract(
                    core_connection,
                    str(row[0]),
                )
                if identity is None:
                    raise RuntimeError(
                        "active analysis setting references an unknown contract"
                    )
                output = AnalysisOutput(identity)
                validate_production_contract(identity)
                require_active_analysis_outputs(
                    core_connection,
                    (output,),
                )
                return output

    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]:
        normalized = normalize_analysis_outputs(outputs)
        for output in normalized:
            validate_production_contract(output.contract)

        sonara_outputs = tuple(
            output
            for output in normalized
            if output.contract.analysis_family == "sonara"
        )
        if sonara_outputs:
            sonara_outputs = _canonical_sonara_release_outputs(sonara_outputs)

        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    if sonara_outputs:
                        active_release_row = core_connection.execute(
                            """
                            SELECT setting_value
                            FROM library_settings
                            WHERE setting_key = ?
                            """,
                            (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
                        ).fetchone()
                        active_release = (
                            None
                            if active_release_row is None
                            else str(active_release_row[0])
                        )
                        requested_release = sonara_outputs[0].contract.release_hash
                        if active_release is None:
                            raise InactiveAnalysisOutputError(
                                "SONARA release is not active; run "
                                "prepare-sonara-release before analysis"
                            )
                        if active_release != requested_release:
                            raise InactiveAnalysisOutputError(
                                "SONARA release changes require "
                                "activate_sonara_release()"
                            )
                    timestamp = utc_timestamp()
                    for output in normalized:
                        register_contract(
                            core_connection,
                            output.contract,
                            created_at=timestamp,
                        )
                        core_connection.execute(
                            """
                            INSERT INTO library_settings (
                                setting_key, setting_value, updated_at
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(setting_key) DO UPDATE SET
                                setting_value = excluded.setting_value,
                                updated_at = excluded.updated_at
                            """,
                            (
                                active_contract_setting_key(output),
                                output.contract_hash,
                                timestamp,
                            ),
                        )
                    _delete_scores_with_inactive_required_outputs(core_connection)
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return tuple(output.contract_hash for output in normalized)

    def activate_sonara_release(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        preparation_proof: object | None = None,
    ) -> AnalysisResetResult:
        """Activate one canonical SONARA release from an empty SONARA state.

        The higher-level release-preparation workflow must supply its private,
        one-shot proof that confirmation, the exact receipt, and the verified
        Core + Artifacts backup pair all match this database and release.
        """

        from .prepare_sonara_release import (
            _require_sonara_release_activation_proof,
        )

        _require_sonara_release_activation_proof(
            preparation_proof,
            self,
            outputs,
        )
        normalized = _canonical_sonara_release_outputs(outputs)
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    validate_storage_binding(
                        core_connection,
                        artifacts_connection,
                    )
                    active_settings = {
                        str(row[0]): str(row[1])
                        for row in core_connection.execute(
                            """
                            SELECT setting_key, setting_value
                            FROM library_settings
                            WHERE setting_key = ?
                               OR setting_key LIKE ?
                            """,
                            (
                                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                                (f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%"),
                            ),
                        )
                    }
                    requested_release = normalized[0].contract.release_hash
                    exact_active_release = active_settings.get(
                        SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY
                    ) == requested_release and all(
                        active_settings.get(active_contract_setting_key(output))
                        == output.contract_hash
                        for output in normalized
                    )
                    if exact_active_release:
                        require_active_analysis_outputs(
                            core_connection,
                            normalized,
                        )
                        core_connection.commit()
                        return AnalysisResetResult()

                    timestamp = utc_timestamp()
                    for output in normalized:
                        register_contract(
                            core_connection,
                            output.contract,
                            created_at=timestamp,
                        )

                    artifacts_connection.execute("BEGIN IMMEDIATE")
                    artifact_deleted = 0
                    for table in (
                        "sonara_timeline",
                        "sonara_similarity_embeddings",
                        "sonara_fingerprints",
                    ):
                        cursor = artifacts_connection.execute(f"DELETE FROM {table}")
                        artifact_deleted += max(0, int(cursor.rowcount))

                    core_cursor = core_connection.execute("DELETE FROM sonara")
                    core_deleted = max(0, int(core_cursor.rowcount))
                    classifier_cursor = core_connection.execute(
                        """
                        DELETE FROM classifier_scores
                        WHERE uses_sonara = 1
                        """
                    )
                    classifier_deleted = max(
                        0,
                        int(classifier_cursor.rowcount),
                    )

                    for output in normalized:
                        core_connection.execute(
                            """
                            INSERT INTO library_settings (
                                setting_key, setting_value, updated_at
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(setting_key) DO UPDATE SET
                                setting_value = excluded.setting_value,
                                updated_at = excluded.updated_at
                            """,
                            (
                                active_contract_setting_key(output),
                                output.contract_hash,
                                timestamp,
                            ),
                        )
                    release_hash = normalized[0].contract.release_hash
                    core_connection.execute(
                        """
                        INSERT INTO library_settings (
                            setting_key, setting_value, updated_at
                        ) VALUES (?, ?, ?)
                        ON CONFLICT(setting_key) DO UPDATE SET
                            setting_value = excluded.setting_value,
                            updated_at = excluded.updated_at
                        """,
                        (
                            SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                            release_hash,
                            timestamp,
                        ),
                    )
                    _commit_coordinated(
                        core_connection,
                        artifacts_connection,
                    )
                except BaseException:
                    _rollback_coordinated(
                        core_connection,
                        artifacts_connection,
                    )
                    raise
        return AnalysisResetResult(
            core_rows_deleted=core_deleted,
            artifact_rows_deleted=artifact_deleted,
            classifier_rows_deleted=classifier_deleted,
        )

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
    ) -> list[AnalysisCandidate]:
        normalized = normalize_analysis_outputs(outputs)
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                storage_binding = validate_storage_binding(
                    core_connection,
                    artifacts_connection,
                )
                catalog_uuid = storage_binding.catalog_uuid
                return collect_analysis_candidates(
                    core_connection=core_connection,
                    artifacts_connection=artifacts_connection,
                    catalog_uuid=catalog_uuid,
                    outputs=normalized,
                    limit=limit,
                )

    def save_sonara_results(
        self,
        writes: Sequence[SonaraWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, SonaraWrite) for write in selected):
            raise TypeError("writes must contain only SonaraWrite values")
        if not selected:
            return ()
        needs_artifacts = any(
            write.timeline is not None
            or write.similarity_embedding is not None
            or write.fingerprint is not None
            for write in selected
        )
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                coordinated_artifacts = (
                    artifacts_connection if needs_artifacts else None
                )
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    storage_binding = validate_storage_binding(
                        core_connection,
                        artifacts_connection,
                    )
                    catalog_uuid = storage_binding.catalog_uuid
                    if coordinated_artifacts is not None:
                        coordinated_artifacts.execute("BEGIN IMMEDIATE")
                    for index, write in enumerate(selected):
                        name = _savepoint(
                            core_connection,
                            coordinated_artifacts,
                            index,
                        )
                        try:
                            require_active_analysis_outputs(
                                core_connection,
                                write.outputs,
                            )
                            _require_current_target(
                                core_connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            _upsert_sonara_core(
                                core_connection,
                                write=write,
                            )
                            if coordinated_artifacts is not None:
                                _upsert_sonara_timeline(
                                    coordinated_artifacts,
                                    write=write,
                                )
                                if write.similarity_embedding is not None:
                                    _delete_stale_artifact_generation(
                                        coordinated_artifacts,
                                        table=("sonara_similarity_embeddings"),
                                        target=write.target,
                                    )
                                    write_valid_embedding_in_transaction(
                                        core_connection=core_connection,
                                        artifacts_connection=(coordinated_artifacts),
                                        track=_artifact_track(write.target),
                                        contract=(write.similarity_embedding.contract),
                                        embedding=(write.similarity_embedding.vector),
                                        analyzed_at=(
                                            write.similarity_embedding.analyzed_at
                                        ),
                                        storage_binding=storage_binding,
                                    )
                                _upsert_sonara_fingerprint(
                                    coordinated_artifacts,
                                    write=write,
                                )
                        except Exception as error:
                            _rollback_savepoint(
                                core_connection,
                                coordinated_artifacts,
                                name,
                            )
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(
                                core_connection,
                                coordinated_artifacts,
                                name,
                            )
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=write.outputs,
                                )
                            )
                    _commit_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                except BaseException:
                    _rollback_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                    raise
        return tuple(results)

    def save_maest_results(
        self,
        writes: Sequence[MaestWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, MaestWrite) for write in selected):
            raise TypeError("writes must contain only MaestWrite values")
        if not selected:
            return ()
        needs_artifacts = any(write.embedding is not None for write in selected)
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                coordinated_artifacts = (
                    artifacts_connection if needs_artifacts else None
                )
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    storage_binding = validate_storage_binding(
                        core_connection,
                        artifacts_connection,
                    )
                    catalog_uuid = storage_binding.catalog_uuid
                    if coordinated_artifacts is not None:
                        coordinated_artifacts.execute("BEGIN IMMEDIATE")
                    for index, write in enumerate(selected):
                        name = _savepoint(
                            core_connection,
                            coordinated_artifacts,
                            index,
                        )
                        try:
                            require_active_analysis_outputs(
                                core_connection,
                                write.outputs,
                            )
                            _require_current_target(
                                core_connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            _upsert_maest_analysis(
                                core_connection,
                                write=write,
                            )
                            if (
                                coordinated_artifacts is not None
                                and write.embedding is not None
                            ):
                                _delete_stale_artifact_generation(
                                    coordinated_artifacts,
                                    table="maest_embeddings",
                                    target=write.target,
                                )
                                write_valid_embedding_in_transaction(
                                    core_connection=core_connection,
                                    artifacts_connection=(coordinated_artifacts),
                                    track=_artifact_track(write.target),
                                    contract=write.embedding.contract,
                                    embedding=write.embedding.vector,
                                    analyzed_at=write.embedding.analyzed_at,
                                    storage_binding=storage_binding,
                                )
                        except Exception as error:
                            _rollback_savepoint(
                                core_connection,
                                coordinated_artifacts,
                                name,
                            )
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(
                                core_connection,
                                coordinated_artifacts,
                                name,
                            )
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=write.outputs,
                                )
                            )
                    _commit_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                except BaseException:
                    _rollback_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                    raise
        return tuple(results)

    def save_embedding_results(
        self,
        writes: Sequence[EmbeddingWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, EmbeddingWrite) for write in selected):
            raise TypeError("writes must contain only EmbeddingWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    storage_binding = validate_storage_binding(
                        core_connection,
                        artifacts_connection,
                    )
                    catalog_uuid = storage_binding.catalog_uuid
                    artifacts_connection.execute("BEGIN IMMEDIATE")
                    for index, write in enumerate(selected):
                        name = _savepoint(
                            core_connection,
                            artifacts_connection,
                            index,
                        )
                        output = AnalysisOutput(write.output.contract)
                        try:
                            require_active_analysis_outputs(
                                core_connection,
                                (output,),
                            )
                            _require_current_target(
                                core_connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            table = artifact_table_for_output(output)
                            if table is None:
                                raise ValueError(
                                    "embedding output has no artifact table"
                                )
                            _delete_stale_artifact_generation(
                                artifacts_connection,
                                table=table,
                                target=write.target,
                            )
                            write_valid_embedding_in_transaction(
                                core_connection=core_connection,
                                artifacts_connection=artifacts_connection,
                                track=_artifact_track(write.target),
                                contract=write.output.contract,
                                embedding=write.output.vector,
                                analyzed_at=write.output.analyzed_at,
                                storage_binding=storage_binding,
                            )
                        except Exception as error:
                            _rollback_savepoint(
                                core_connection,
                                artifacts_connection,
                                name,
                            )
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(
                                core_connection,
                                artifacts_connection,
                                name,
                            )
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=(output,),
                                )
                            )
                    _commit_coordinated(
                        core_connection,
                        artifacts_connection,
                    )
                except BaseException:
                    _rollback_coordinated(
                        core_connection,
                        artifacts_connection,
                    )
                    raise
        return tuple(results)

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        if output.contract.output_kind != "embedding":
            raise ValueError("vector loading requires an embedding output")
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                storage_binding = validate_storage_binding(
                    core_connection,
                    artifacts_connection,
                )
                catalog_uuid = storage_binding.catalog_uuid
                require_active_analysis_outputs(
                    core_connection,
                    (output,),
                )
                selected = _selected_targets(
                    core_connection,
                    catalog_uuid=catalog_uuid,
                    targets=targets,
                )
                rows: list[AnalysisVectorRow] = []
                for target in selected:
                    vector = read_valid_embedding(
                        family=output.contract.analysis_family,
                        track_id=target.track_id,
                        core_connection=core_connection,
                        artifacts_connection=artifacts_connection,
                        expected_contract=output.contract,
                        storage_binding=storage_binding,
                    )
                    if vector is None:
                        continue
                    rows.append(
                        AnalysisVectorRow(
                            target=target,
                            output=output,
                            vector=_readonly_copy(vector),
                        )
                    )
                return tuple(rows)

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        if output.key != ("sonara", "core"):
            raise ValueError("SONARA feature loading requires a SONARA core output")
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                catalog_uuid = _catalog_uuid(core_connection)
                require_active_analysis_outputs(
                    core_connection,
                    (output,),
                )
                selected = _selected_targets(
                    core_connection,
                    catalog_uuid=catalog_uuid,
                    targets=targets,
                )
                selected_by_id = {target.track_id: target for target in selected}
                if not selected_by_id:
                    return ()
                placeholders = ", ".join("?" for _ in selected_by_id)
                rows = core_connection.execute(
                    f"""
                    SELECT {", ".join(SONARA_CORE_COLUMNS)}
                    FROM sonara
                    WHERE contract_hash = ?
                      AND track_id IN ({placeholders})
                    ORDER BY track_id
                    """,
                    (
                        output.contract_hash,
                        *selected_by_id.keys(),
                    ),
                ).fetchall()
                result: list[SonaraFeatureRow] = []
                for row in rows:
                    target = selected_by_id.get(int(row["track_id"]))
                    if target is None:
                        continue
                    valid, _reason = validate_sonara_core_row(
                        row,
                        expected_contract=output.contract,
                        expected_track_id=target.track_id,
                        expected_content_generation=target.content_generation,
                    )
                    if not valid:
                        continue
                    values: dict[str, object] = {}
                    for column in SONARA_CORE_COLUMNS:
                        if column in _SONARA_IDENTITY_COLUMNS:
                            continue
                        value = row[column]
                        dim = SONARA_CORE_VECTOR_DIMS.get(column)
                        if dim is not None:
                            vector = np.frombuffer(
                                value,
                                dtype="<f4",
                            )
                            values[column] = tuple(float(item) for item in vector)
                        else:
                            values[column] = value
                    result.append(
                        SonaraFeatureRow(
                            target=target,
                            output=output,
                            values=MappingProxyType(values),
                        )
                    )
                return tuple(result)

    def prepare_classifier_rescore(
        self,
        specification: ClassifierSpecification,
    ) -> int:
        """Delete only stale rows for one classifier before a scoring run."""

        if not isinstance(specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        outputs = normalize_analysis_outputs(specification.required_outputs)
        uses_sonara = int(specification.sonara_release_hash is not None)
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    require_active_analysis_outputs(
                        core_connection,
                        outputs,
                    )
                    cursor = core_connection.execute(
                        """
                        DELETE FROM classifier_scores
                        WHERE classifier_key = ?
                          AND (
                              model_id <> ?
                              OR feature_set <> ?
                              OR feature_manifest_hash <> ?
                              OR required_outputs_hash <> ?
                              OR positive_label <> ?
                              OR uses_sonara <> ?
                              OR sonara_release_hash IS NOT ?
                              OR NOT EXISTS (
                                  SELECT 1
                                  FROM tracks
                                  WHERE tracks.track_id =
                                        classifier_scores.track_id
                                    AND tracks.content_generation =
                                        classifier_scores.content_generation
                                    AND tracks.missing_since IS NULL
                              )
                          )
                        """,
                        (
                            specification.classifier_key,
                            specification.model_id,
                            specification.feature_set,
                            specification.feature_manifest_hash,
                            specification.required_outputs_hash,
                            specification.positive_label,
                            uses_sonara,
                            specification.sonara_release_hash,
                        ),
                    )
                    deleted = max(0, int(cursor.rowcount))
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return deleted

    def classifier_candidate_readiness(
        self,
        specification: ClassifierSpecification,
    ) -> ClassifierReadiness:
        state = self._classifier_candidate_state(specification)
        return state[0]

    def list_classifier_candidates(
        self,
        specification: ClassifierSpecification,
        *,
        limit: int | None = None,
    ) -> list[ClassifierCandidate]:
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                raise ValueError("limit must be a non-negative integer or None")
            if limit == 0:
                return []
        _readiness, candidates = self._classifier_candidate_state(specification)
        if limit is not None:
            return candidates[:limit]
        return candidates

    def _classifier_candidate_state(
        self,
        specification: ClassifierSpecification,
    ) -> tuple[ClassifierReadiness, list[ClassifierCandidate]]:
        if not isinstance(specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        outputs = normalize_analysis_outputs(specification.required_outputs)
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                storage_binding = validate_storage_binding(
                    core_connection,
                    artifacts_connection,
                )
                catalog_uuid = storage_binding.catalog_uuid
                ready = ready_target_keys_by_output(
                    core_connection=core_connection,
                    artifacts_connection=artifacts_connection,
                    catalog_uuid=catalog_uuid,
                    outputs=outputs,
                )
                score_rows = {
                    int(row["track_id"]): row
                    for row in core_connection.execute(
                        """
                        SELECT track_id, content_generation, model_id,
                               feature_set, feature_manifest_hash,
                               required_outputs_hash,
                               uses_sonara, sonara_release_hash,
                               positive_label
                        FROM classifier_scores
                        WHERE classifier_key = ?
                        """,
                        (specification.classifier_key,),
                    )
                }
                candidates: list[ClassifierCandidate] = []
                total = 0
                ready_count = 0
                missing_count = 0
                already_count = 0
                missing_by_output = {
                    (
                        f"{output.contract.analysis_family}/"
                        f"{output.contract.output_kind}"
                    ): 0
                    for output in outputs
                }
                for row in read_current_track_rows(core_connection):
                    total += 1
                    target = target_from_track_row(
                        row,
                        catalog_uuid=catalog_uuid,
                    )
                    missing = missing_outputs_for_target(
                        target,
                        outputs,
                        ready,
                    )
                    if missing:
                        missing_count += 1
                        for output in missing:
                            key = (
                                f"{output.contract.analysis_family}/"
                                f"{output.contract.output_kind}"
                            )
                            missing_by_output[key] += 1
                        continue
                    ready_count += 1
                    score = score_rows.get(target.track_id)
                    sonara_hash = specification.sonara_release_hash
                    already_current = (
                        score is not None
                        and int(score["content_generation"])
                        == target.content_generation
                        and str(score["model_id"]) == specification.model_id
                        and str(score["feature_set"]) == specification.feature_set
                        and str(score["feature_manifest_hash"])
                        == specification.feature_manifest_hash
                        and str(score["required_outputs_hash"])
                        == specification.required_outputs_hash
                        and int(score["uses_sonara"]) == int(sonara_hash is not None)
                        and (
                            None
                            if score["sonara_release_hash"] is None
                            else str(score["sonara_release_hash"])
                        )
                        == sonara_hash
                        and str(score["positive_label"]) == specification.positive_label
                    )
                    if already_current:
                        already_count += 1
                        continue
                    candidates.append(
                        ClassifierCandidate(
                            target=target,
                            file_path=str(row["file_path"]),
                            file_size_bytes=int(row["file_size_bytes"]),
                            file_modified_ns=int(row["file_modified_ns"]),
                        )
                    )
                readiness = ClassifierReadiness(
                    total_tracks=total,
                    ready_tracks=ready_count,
                    missing_input_tracks=missing_count,
                    already_scored_tracks=already_count,
                    candidate_tracks=len(candidates),
                    missing_by_output=MappingProxyType(missing_by_output),
                )
                return readiness, candidates

    def load_classifier_feature_rows(
        self,
        specification: ClassifierSpecification,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[ClassifierFeatureRow, ...]:
        if not isinstance(specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        outputs_by_family = {
            output.contract.analysis_family: output
            for output in specification.required_outputs
            if output.contract.output_kind in {"core", "embedding"}
        }
        for feature_name in specification.feature_names:
            family, separator, _key = feature_name.partition(":")
            if not separator or family not in outputs_by_family:
                raise ValueError(
                    f"classifier feature has no required output: {feature_name}"
                )

        with self._write_lock:
            with closing(self.connect()) as core_connection:
                catalog_uuid = _catalog_uuid(core_connection)
                selected = _selected_targets(
                    core_connection,
                    catalog_uuid=catalog_uuid,
                    targets=targets,
                )
        sonara_values: dict[int, Mapping[str, object]] = {}
        sonara_output = outputs_by_family.get("sonara")
        if sonara_output is not None:
            sonara_values = {
                row.target.track_id: row.values
                for row in self.load_sonara_feature_rows(
                    sonara_output,
                    targets=selected,
                )
            }
        vectors: dict[str, dict[int, np.ndarray]] = {}
        for family, output in outputs_by_family.items():
            if output.contract.output_kind != "embedding":
                continue
            vectors[family] = {
                row.target.track_id: row.vector
                for row in self.load_analysis_vectors(
                    output,
                    targets=selected,
                )
            }

        result: list[ClassifierFeatureRow] = []
        for target in selected:
            values: list[float] = []
            complete = True
            for feature_name in specification.feature_names:
                family, _, key = feature_name.partition(":")
                if family == "sonara":
                    value = _sonara_feature_value(
                        sonara_values.get(target.track_id, {}),
                        key,
                    )
                else:
                    vector = vectors.get(family, {}).get(target.track_id)
                    value = None if vector is None else _vector_value(vector, key)
                if value is None:
                    complete = False
                    break
                values.append(value)
            if not complete:
                continue
            vector = np.asarray(values, dtype="<f4")
            if vector.shape != (len(specification.feature_names),) or not bool(
                np.all(np.isfinite(vector))
            ):
                continue
            result.append(
                ClassifierFeatureRow(
                    target=target,
                    specification=specification,
                    vector=_readonly_copy(vector),
                )
            )
        return tuple(result)

    def save_classifier_scores(
        self,
        writes: Sequence[ClassifierScoreWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, ClassifierScoreWrite) for write in selected):
            raise TypeError("writes must contain only ClassifierScoreWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    catalog_uuid = _catalog_uuid(core_connection)
                    active_release_row = core_connection.execute(
                        """
                        SELECT setting_value
                        FROM library_settings
                        WHERE setting_key = ?
                        """,
                        (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
                    ).fetchone()
                    active_release = (
                        None
                        if active_release_row is None
                        else str(active_release_row[0])
                    )
                    for index, write in enumerate(selected):
                        name = _savepoint(
                            core_connection,
                            None,
                            index,
                        )
                        try:
                            _require_current_target(
                                core_connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            require_active_analysis_outputs(
                                core_connection,
                                write.specification.required_outputs,
                            )
                            _validate_classifier_score(
                                write.score,
                                write.specification,
                            )
                            if (
                                write.score.uses_sonara == 1
                                and write.score.sonara_release_hash != active_release
                            ):
                                raise InactiveAnalysisOutputError(
                                    "classifier score uses an inactive SONARA release"
                                )
                            _upsert_classifier_score(
                                core_connection,
                                write.score,
                            )
                        except Exception as error:
                            _rollback_savepoint(
                                core_connection,
                                None,
                                name,
                            )
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(
                                core_connection,
                                None,
                                name,
                            )
                            results.append(AnalysisWriteResult(target=write.target))
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return tuple(results)

    def reset_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> AnalysisResetResult:
        normalized = normalize_analysis_outputs(outputs)
        artifact_outputs = tuple(
            output
            for output in normalized
            if artifact_table_for_output(output) is not None
        )
        with self._write_lock:
            with (
                closing(self.connect()) as core_connection,
                closing(self.connect_artifacts()) as artifacts_connection,
            ):
                coordinated_artifacts = (
                    artifacts_connection if artifact_outputs else None
                )
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    validate_storage_binding(
                        core_connection,
                        artifacts_connection,
                    )
                    require_active_analysis_outputs(
                        core_connection,
                        normalized,
                    )
                    if coordinated_artifacts is not None:
                        coordinated_artifacts.execute("BEGIN IMMEDIATE")
                    core_deleted = 0
                    artifact_deleted = 0
                    for output in normalized:
                        if output.key == ("sonara", "core"):
                            cursor = core_connection.execute(
                                """
                                DELETE FROM sonara
                                WHERE contract_hash = ?
                                """,
                                (output.contract_hash,),
                            )
                            core_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                        elif output.key == ("maest", "analysis"):
                            cursor = core_connection.execute(
                                """
                                DELETE FROM maest_scores
                                WHERE contract_hash = ?
                                """,
                                (output.contract_hash,),
                            )
                            core_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                        else:
                            table = artifact_table_for_output(output)
                            if table is None or coordinated_artifacts is None:
                                raise ValueError("unsupported analysis output reset")
                            cursor = coordinated_artifacts.execute(
                                f"""
                                DELETE FROM {table}
                                WHERE contract_hash = ?
                                """,
                                (output.contract_hash,),
                            )
                            artifact_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                    sonara_releases = {
                        output.contract.release_hash
                        for output in normalized
                        if output.contract.analysis_family == "sonara"
                    }
                    classifier_deleted = 0
                    for release_hash in sonara_releases:
                        cursor = core_connection.execute(
                            """
                            DELETE FROM classifier_scores
                            WHERE uses_sonara = 1
                              AND sonara_release_hash = ?
                            """,
                            (release_hash,),
                        )
                        classifier_deleted += max(
                            0,
                            int(cursor.rowcount),
                        )
                    _commit_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                except BaseException:
                    _rollback_coordinated(
                        core_connection,
                        coordinated_artifacts,
                    )
                    raise
        return AnalysisResetResult(
            core_rows_deleted=core_deleted,
            artifact_rows_deleted=artifact_deleted,
            classifier_rows_deleted=classifier_deleted,
        )

    def reset_classifier_scores(
        self,
        classifier_keys: Sequence[str],
    ) -> AnalysisResetResult:
        keys = tuple(
            dict.fromkeys(
                str(value).strip() for value in classifier_keys if str(value).strip()
            )
        )
        if not keys:
            raise ValueError("at least one classifier key is required")
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    placeholders = ", ".join("?" for _ in keys)
                    cursor = core_connection.execute(
                        f"""
                        DELETE FROM classifier_scores
                        WHERE classifier_key IN ({placeholders})
                        """,
                        keys,
                    )
                    deleted = max(0, int(cursor.rowcount))
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return AnalysisResetResult(classifier_rows_deleted=deleted)

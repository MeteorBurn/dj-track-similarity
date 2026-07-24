from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, TypeAlias
import hashlib
import json
import math
import sqlite3

import numpy as np

from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    read_registered_contract,
)
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    validate_production_contract,
)
from dj_track_similarity.db_artifacts import validate_artifacts_sidecar_schema
from dj_track_similarity.db_connection import connect_database, write_lock_for_path
from dj_track_similarity.db_schema import validate_core_schema
from dj_track_similarity.db_storage import storage_database_paths
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    FileTags,
    MaestAnalysis,
    MaestGenre,
)


EmbeddingFamily: TypeAlias = Literal["maest", "mert", "muq", "clap"]
AnalysisFamily: TypeAlias = Literal["sonara", "maest", "mert", "muq", "clap"]
OutputKind: TypeAlias = Literal["core", "analysis", "embedding"]

_EMBEDDING_TABLES: Mapping[EmbeddingFamily, str] = MappingProxyType(
    {
        "maest": "maest_embeddings",
        "mert": "mert_embeddings",
        "muq": "muq_embeddings",
        "clap": "clap_embeddings",
    }
)
_OUTPUT_KEYS = frozenset(
    {
        ("sonara", "core"),
        ("maest", "analysis"),
        *(family_output for family_output in ((family, "embedding") for family in _EMBEDDING_TABLES)),
    }
)
_READ_CHUNK_SIZE = 800


class SourceDatabaseError(RuntimeError):
    """Base error for a source catalog that cannot be consumed safely."""


class SourceDatabaseIntegrityError(SourceDatabaseError):
    """The selected storage set or one of its registered identities is invalid."""


class SourceDataNotReadyError(SourceDatabaseError):
    """A requested current analysis output is unavailable."""


class SourceTrackNotCurrentError(SourceDatabaseError):
    """A write target no longer identifies the current track content."""


@dataclass(frozen=True)
class SourceOutput:
    analysis_family: AnalysisFamily
    output_kind: OutputKind

    def __post_init__(self) -> None:
        if (self.analysis_family, self.output_kind) not in _OUTPUT_KEYS:
            raise ValueError(
                "Unsupported Rhythm Lab source output: "
                f"{self.analysis_family}/{self.output_kind}"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.analysis_family, self.output_kind


SONARA_CORE_OUTPUT = SourceOutput("sonara", "core")
MAEST_ANALYSIS_OUTPUT = SourceOutput("maest", "analysis")
MAEST_EMBEDDING_OUTPUT = SourceOutput("maest", "embedding")
MERT_EMBEDDING_OUTPUT = SourceOutput("mert", "embedding")
MUQ_EMBEDDING_OUTPUT = SourceOutput("muq", "embedding")
CLAP_EMBEDDING_OUTPUT = SourceOutput("clap", "embedding")

EMBEDDING_OUTPUTS: Mapping[EmbeddingFamily, SourceOutput] = MappingProxyType(
    {
        "maest": MAEST_EMBEDDING_OUTPUT,
        "mert": MERT_EMBEDDING_OUTPUT,
        "muq": MUQ_EMBEDDING_OUTPUT,
        "clap": CLAP_EMBEDDING_OUTPUT,
    }
)
SOURCE_OUTPUTS = (
    SONARA_CORE_OUTPUT,
    MAEST_ANALYSIS_OUTPUT,
    MAEST_EMBEDDING_OUTPUT,
    MERT_EMBEDDING_OUTPUT,
    MUQ_EMBEDDING_OUTPUT,
    CLAP_EMBEDDING_OUTPUT,
)


@dataclass(frozen=True)
class SourceSonaraFeatures:
    """Typed current SONARA Core values used by Rhythm Lab feature recipes."""

    detected_bpm: float | None
    raw_bpm: float | None
    bpm_confidence: float | None
    onset_density_per_second: float | None
    beat_count: int | None
    tempo_variability: float | None
    beat_grid_offset_seconds: float | None
    beat_grid_stability: float | None
    detected_key_name: str | None
    detected_key_camelot: str | None
    key_confidence: float | None
    predominant_chord: str | None
    chord_changes_per_second: float | None
    energy_score: float | None
    energy_level: int | None
    danceability_score: float | None
    valence_score: float | None
    acousticness_score: float | None
    dissonance_score: float | None
    spectral_centroid_hz: float | None
    spectral_bandwidth_hz: float | None
    spectral_rolloff_hz: float | None
    spectral_flatness: float | None
    zero_crossing_rate: float | None
    rms_mean: float | None
    rms_max: float | None
    integrated_loudness_lufs: float | None
    dynamic_range_db: float | None
    true_peak_dbtp: float | None
    replay_gain_db: float | None
    max_momentary_loudness_lufs: float | None
    loudness_range_lu: float | None
    analyzed_duration_seconds: float | None
    intro_end_seconds: float | None
    outro_start_seconds: float | None
    leading_silence_seconds: float | None
    trailing_silence_seconds: float | None
    energy_curve_hop_seconds: float | None
    energy_curve_sample_count: int | None
    energy_curve_min: float | None
    energy_curve_max: float | None
    energy_curve_mean: float | None
    energy_curve_stddev: float | None
    vocal_probability: float | None
    mood_happy_score: float | None
    mood_aggressive_score: float | None
    mood_relaxed_score: float | None
    mood_sad_score: float | None
    mfcc_mean: tuple[float, ...]
    chroma_mean: tuple[float, ...]
    spectral_contrast_mean: tuple[float, ...]
    analyzed_at: str


@dataclass(frozen=True)
class SourceTrack:
    """One current Core track and its exact catalog/content identity."""

    catalog_uuid: str
    track_id: int
    track_uuid: str
    content_generation: int
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    audio_duration_seconds: float | None
    file_tags: FileTags | None
    liked: bool
    sonara_features: SourceSonaraFeatures | None
    sonara_contract: ContractIdentity | None
    maest: MaestAnalysis | None
    maest_contract: ContractIdentity | None
    analysis_coverage: AnalysisCoverage


@dataclass(frozen=True)
class SourceEmbeddingMatrix:
    """One ordered, current-generation embedding matrix and its exact contract."""

    family: EmbeddingFamily
    contract: ContractIdentity
    tracks: tuple[SourceTrack, ...]
    matrix: np.ndarray
    not_ready_track_ids: tuple[int, ...]


class SourceDatabase:
    """Mostly read-only Rhythm Lab view over one bound v7 storage pair."""

    def __init__(
        self,
        path: str | Path,
        *,
        expected_catalog_uuid: str | None = None,
    ) -> None:
        selected = Path(_clean_path_text(path)).expanduser()
        if not str(selected).strip() or not selected.name:
            raise ValueError("Source database path is required")
        if not selected.exists():
            raise FileNotFoundError(f"Source database does not exist: {selected}")
        if not selected.is_file():
            raise ValueError("Source database path must be an existing file")
        self.path = selected.resolve(strict=True)
        self.artifacts_path = storage_database_paths(self.path).artifacts
        if not self.artifacts_path.is_file():
            raise FileNotFoundError(
                f"Required Artifacts database does not exist: {self.artifacts_path}"
            )
        clean_expected = _optional_non_empty_text(
            expected_catalog_uuid,
            "expected_catalog_uuid",
        )
        self.catalog_uuid = self._validate_storage_set(
            expected_catalog_uuid=clean_expected
        )
        self._write_lock = write_lock_for_path(self.path)

    def _validate_storage_set(self, *, expected_catalog_uuid: str | None) -> str:
        with closing(_readonly_connection(self.path)) as core_connection:
            catalog_uuid = validate_core_schema(
                core_connection,
                expected_catalog_uuid=expected_catalog_uuid,
            )
        with closing(_readonly_connection(self.artifacts_path)) as artifacts_connection:
            validate_artifacts_sidecar_schema(
                artifacts_connection,
                expected_catalog_uuid=catalog_uuid,
            )
        return catalog_uuid

    def connect(self) -> sqlite3.Connection:
        """Open an exactly validated, query-only Core connection with Artifacts attached."""

        connection = _readonly_connection(self.path)
        try:
            validate_core_schema(
                connection,
                expected_catalog_uuid=self.catalog_uuid,
            )
            with closing(
                _readonly_connection(self.artifacts_path)
            ) as artifacts_connection:
                validate_artifacts_sidecar_schema(
                    artifacts_connection,
                    expected_catalog_uuid=self.catalog_uuid,
                )
            connection.execute(
                "ATTACH DATABASE ? AS artifacts",
                (_readonly_uri(self.artifacts_path),),
            )
            attached = connection.execute(
                """
                SELECT catalog_uuid
                FROM artifacts.storage_metadata
                WHERE singleton_id = 1
                """
            ).fetchone()
            if attached is None or str(attached[0]) != self.catalog_uuid:
                raise SourceDatabaseIntegrityError(
                    "Core and Artifacts catalog binding changed while opening Rhythm Lab"
                )
            connection.create_function(
                "rhythm_lab_random_rank",
                2,
                _stable_random_rank,
                deterministic=True,
            )
            connection.execute("PRAGMA query_only = ON")
            return connection
        except BaseException:
            connection.close()
            raise

    def active_contracts(self) -> Mapping[SourceOutput, ContractIdentity]:
        with closing(self.connect()) as connection:
            active = _active_contracts(connection)
        return MappingProxyType(
            {
                output: identity
                for output in SOURCE_OUTPUTS
                if (identity := active.get(output.key)) is not None
            }
        )

    def active_contract(self, output: SourceOutput) -> ContractIdentity | None:
        if not isinstance(output, SourceOutput):
            raise TypeError("output must be a SourceOutput")
        return self.active_contracts().get(output)

    def count_tracks(self) -> int:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE missing_since IS NULL"
            ).fetchone()
        assert row is not None
        return int(row[0])

    def count_embeddings(self, family: EmbeddingFamily) -> int:
        return len(self.embedding_track_ids(family))

    def count_sonara_features(self) -> int:
        with closing(self.connect()) as connection:
            active = _active_contracts(connection)
            contract = active.get(SONARA_CORE_OUTPUT.key)
            if contract is None:
                return 0
            rows = connection.execute(
                """
                SELECT s.mfcc_mean_blob, s.chroma_mean_blob,
                       s.spectral_contrast_mean_blob
                FROM sonara AS s
                JOIN tracks AS t
                  ON t.track_id = s.track_id
                 AND t.content_generation = s.content_generation
                WHERE t.missing_since IS NULL
                  AND s.contract_hash = ?
                """,
                (contract.contract_hash,),
            ).fetchall()
        return sum(
            1
            for row in rows
            if _float_tuple(row[0], 13) is not None
            and _float_tuple(row[1], 12) is not None
            and _float_tuple(row[2], 7) is not None
        )

    def count_liked_tracks(self) -> int:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM likes AS l
                JOIN tracks AS t ON t.track_id = l.track_id
                WHERE t.missing_since IS NULL
                """
            ).fetchone()
        assert row is not None
        return int(row[0])

    def get_track(self, track_id: int) -> SourceTrack:
        clean_id = _positive_track_id(track_id)
        track = self.tracks_by_ids((clean_id,)).get(clean_id)
        if track is None:
            raise KeyError(f"Unknown current track id: {clean_id}")
        return track

    def tracks_by_ids(
        self,
        track_ids: Iterable[int],
    ) -> dict[int, SourceTrack]:
        unique_ids = list(
            dict.fromkeys(_positive_track_id(track_id) for track_id in track_ids)
        )
        if not unique_ids:
            return {}
        with closing(self.connect()) as connection:
            tracks = _load_tracks(
                connection,
                catalog_uuid=self.catalog_uuid,
                track_ids=unique_ids,
            )
        return {track.track_id: track for track in tracks}

    def list_tracks(self) -> list[SourceTrack]:
        with closing(self.connect()) as connection:
            return list(
                _load_tracks(
                    connection,
                    catalog_uuid=self.catalog_uuid,
                )
            )

    def embedding_track_ids(self, family: EmbeddingFamily) -> set[int]:
        clean_family = _embedding_family(family)
        with closing(self.connect()) as connection:
            active = _active_contracts(connection)
            contract = active.get(EMBEDDING_OUTPUTS[clean_family].key)
            if contract is None:
                return set()
            vectors = _ready_embedding_vectors(
                connection,
                family=clean_family,
                contract=contract,
            )
        return set(vectors)

    def load_embedding_matrix(
        self,
        family: EmbeddingFamily,
    ) -> SourceEmbeddingMatrix:
        clean_family = _embedding_family(family)
        with closing(self.connect()) as connection:
            active = _active_contracts(connection)
            contract = active.get(EMBEDDING_OUTPUTS[clean_family].key)
            if contract is None:
                raise SourceDataNotReadyError(
                    f"No active {clean_family}/embedding ContractIdentity"
                )
            tracks = tuple(
                sorted(
                    _load_tracks(
                        connection,
                        catalog_uuid=self.catalog_uuid,
                        active=active,
                    ),
                    key=lambda track: track.track_id,
                )
            )
            vectors = _ready_embedding_vectors(
                connection,
                family=clean_family,
                contract=contract,
                track_ids=[track.track_id for track in tracks],
            )

        ready_tracks = tuple(
            track for track in tracks if track.track_id in vectors
        )
        if ready_tracks:
            matrix = np.vstack(
                [vectors[track.track_id] for track in ready_tracks]
            ).astype(np.float32, copy=False)
        else:
            assert contract.dim is not None
            matrix = np.empty((0, contract.dim), dtype=np.float32)
        matrix.setflags(write=False)
        return SourceEmbeddingMatrix(
            family=clean_family,
            contract=contract,
            tracks=ready_tracks,
            matrix=matrix,
            not_ready_track_ids=tuple(
                track.track_id
                for track in tracks
                if track.track_id not in vectors
            ),
        )

    def set_track_liked(
        self,
        *,
        track_uuid: str,
        content_generation: int,
        liked: bool,
    ) -> SourceTrack:
        """Apply the sole narrow Core write after checking exact current identity."""

        clean_uuid = _non_empty_text(track_uuid, "track_uuid")
        clean_generation = _positive_generation(content_generation)
        if not isinstance(liked, bool):
            raise TypeError("liked must be a bool")

        with self._write_lock:
            with closing(
                _readonly_connection(self.artifacts_path)
            ) as artifacts_connection:
                validate_artifacts_sidecar_schema(
                    artifacts_connection,
                    expected_catalog_uuid=self.catalog_uuid,
                )
            with closing(
                connect_database(
                    self.path,
                    expected_catalog_uuid=self.catalog_uuid,
                )
            ) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    row = connection.execute(
                        """
                        SELECT track_id
                        FROM tracks
                        WHERE track_uuid = ?
                          AND content_generation = ?
                          AND missing_since IS NULL
                        """,
                        (clean_uuid, clean_generation),
                    ).fetchone()
                    if row is None:
                        raise SourceTrackNotCurrentError(
                            "Like target is not the current track UUID/generation"
                        )
                    track_id = int(row[0])
                    if liked:
                        connection.execute(
                            """
                            INSERT INTO likes(track_id, liked_at)
                            VALUES (?, CURRENT_TIMESTAMP)
                            ON CONFLICT(track_id) DO UPDATE SET
                                liked_at = excluded.liked_at
                            """,
                            (track_id,),
                        )
                    else:
                        connection.execute(
                            "DELETE FROM likes WHERE track_id = ?",
                            (track_id,),
                        )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return self.get_track(track_id)

    def list_tracks_page(
        self,
        *,
        labels_db_path: str | Path,
        classifier_key: str,
        label_keys: tuple[str, ...] = ("broken", "straight", "ambiguous"),
        training_label_keys: tuple[str, ...] = ("broken", "straight"),
        query: str = "",
        syncopated: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        liked: str = "all",
        label: str = "all",
        collection_id: int | None = None,
        order: str = "normal",
        seed: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        clean_classifier = _non_empty_text(classifier_key, "classifier_key")
        labels_path = _labels_database_path(labels_db_path)
        params: dict[str, object] = {
            "classifier_key": clean_classifier,
            "catalog_uuid": self.catalog_uuid,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "random_seed": _random_seed_value(seed),
        }
        training_placeholders: list[str] = []
        for index, label_key in enumerate(training_label_keys):
            name = f"training_label_{index}"
            training_placeholders.append(f":{name}")
            params[name] = str(label_key)
        trained_members = ", ".join(training_placeholders) or "NULL"
        trained_sql = (
            f"CASE WHEN rl.label IN ({trained_members}) "
            "AND cp.updated_at IS NOT NULL "
            "AND rl.updated_at <= cp.updated_at THEN 1 ELSE 0 END"
        )

        with closing(self.connect()) as connection:
            _attach_labels(connection, labels_path)
            active = _active_contracts(connection)
            params["sonara_contract_hash"] = _contract_hash_or_unavailable(
                active.get(SONARA_CORE_OUTPUT.key)
            )
            params["maest_contract_hash"] = _contract_hash_or_unavailable(
                active.get(MAEST_ANALYSIS_OUTPUT.key)
            )
            collection_join = ""
            if collection_id is not None:
                _require_collection_identity_schema(connection)
                params["collection_id"] = _positive_collection_id(collection_id)
                collection_join = """
                    JOIN labels.review_collection_tracks AS rct
                      ON rct.collection_id = :collection_id
                     AND rct.catalog_uuid = :catalog_uuid
                     AND rct.track_uuid = t.track_uuid
                     AND rct.content_generation = t.content_generation
                    JOIN labels.review_collections AS rc
                      ON rc.id = rct.collection_id
                     AND rc.catalog_uuid = rct.catalog_uuid
                """
            joins = _track_page_joins(collection_join)
            where_parts = _track_page_filters(
                params=params,
                query=query,
                syncopated=syncopated,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                liked=liked,
                label=label,
                label_keys=label_keys,
            )
            where_sql = f"WHERE {' AND '.join(where_parts)}"
            order_sql = _track_page_order_sql(
                order=order,
                liked=liked,
                collection=collection_id is not None,
            )
            total_row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM tracks AS t
                {joins}
                {where_sql}
                """,
                params,
            ).fetchone()
            assert total_row is not None
            rows = connection.execute(
                f"""
                SELECT t.track_id,
                       rl.label AS classifier_label,
                       {trained_sql} AS classifier_label_trained
                FROM tracks AS t
                {joins}
                LEFT JOIN labels.classifier_training_checkpoints AS cp
                  ON cp.classifier_key = :classifier_key
                {where_sql}
                {order_sql}
                LIMIT :limit OFFSET :offset
                """,
                params,
            ).fetchall()
            tracks = {
                track.track_id: track
                for track in _load_tracks(
                    connection,
                    catalog_uuid=self.catalog_uuid,
                    track_ids=[int(row["track_id"]) for row in rows],
                    active=active,
                )
            }

        return {
            "items": [
                _track_page_item(
                    tracks[int(row["track_id"])],
                    label=row["classifier_label"],
                    label_trained=bool(row["classifier_label_trained"]),
                )
                for row in rows
                if int(row["track_id"]) in tracks
            ],
            "total": int(total_row[0]),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def list_predictions_page(
        self,
        *,
        labels_db_path: str | Path,
        classifier_key: str,
        profile_type: str,
        positive_label: str,
        negative_label: str,
        label_keys: tuple[str, ...],
        training_label_keys: tuple[str, ...],
        query: str = "",
        syncopated: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        label: str = "unlabeled",
        predicted: str = "all",
        probability_focus: str = "positive_highest",
        min_positive: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        labels_path = _labels_database_path(labels_db_path)
        params: dict[str, object] = {
            "classifier_key": _non_empty_text(
                classifier_key,
                "classifier_key",
            ),
            "catalog_uuid": self.catalog_uuid,
            "positive_probability_path": _json_probability_path(positive_label),
            "negative_probability_path": _json_probability_path(negative_label),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }
        training_placeholders: list[str] = []
        for index, label_key in enumerate(training_label_keys):
            name = f"training_label_{index}"
            training_placeholders.append(f":{name}")
            params[name] = str(label_key)
        trained_members = ", ".join(training_placeholders) or "NULL"

        with closing(self.connect()) as connection:
            _attach_labels(connection, labels_path)
            active = _active_contracts(connection)
            params["sonara_contract_hash"] = _contract_hash_or_unavailable(
                active.get(SONARA_CORE_OUTPUT.key)
            )
            params["maest_contract_hash"] = _contract_hash_or_unavailable(
                active.get(MAEST_ANALYSIS_OUTPUT.key)
            )
            where_sql = _prediction_page_filter_sql(
                params=params,
                query=query,
                syncopated=syncopated,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                label=label,
                predicted=predicted,
                label_keys=label_keys,
                min_positive=min_positive,
                profile_type=profile_type,
            )
            cte_sql = _prediction_page_cte(trained_members)
            total_row = connection.execute(
                f"{cte_sql} SELECT COUNT(*) FROM candidate_rows {where_sql}",
                params,
            ).fetchone()
            assert total_row is not None
            rows = connection.execute(
                f"""
                {cte_sql}
                SELECT *
                FROM candidate_rows
                {where_sql}
                {_prediction_page_order_sql(probability_focus, profile_type)}
                LIMIT :limit OFFSET :offset
                """,
                params,
            ).fetchall()
            current_ids = [
                int(row["current_track_id"])
                for row in rows
                if row["current_track_id"] is not None
            ]
            tracks = {
                track.track_id: track
                for track in _load_tracks(
                    connection,
                    catalog_uuid=self.catalog_uuid,
                    track_ids=current_ids,
                    active=active,
                )
            }

        return {
            "items": [
                _prediction_page_item(
                    row,
                    track=(
                        tracks.get(int(row["current_track_id"]))
                        if row["current_track_id"] is not None
                        else None
                    ),
                    profile_type=profile_type,
                    positive_label=positive_label,
                    negative_label=negative_label,
                )
                for row in rows
            ],
            "total": int(total_row[0]),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve(strict=False).as_uri()}?mode=ro"


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        _readonly_uri(path),
        timeout=30,
        uri=True,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except BaseException:
        connection.close()
        raise


def _active_contracts(
    connection: sqlite3.Connection,
) -> dict[tuple[str, str], ContractIdentity]:
    settings = {
        str(row["setting_key"]): str(row["setting_value"])
        for row in connection.execute(
            "SELECT setting_key, setting_value FROM library_settings"
        )
    }
    active_release = settings.get(SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY)
    active: dict[tuple[str, str], ContractIdentity] = {}
    for output in SOURCE_OUTPUTS:
        setting_key = (
            f"{ACTIVE_CONTRACT_SETTING_PREFIX}."
            f"{output.analysis_family}.{output.output_kind}"
        )
        contract_hash = settings.get(setting_key)
        if contract_hash is None:
            continue
        try:
            identity = read_registered_contract(connection, contract_hash)
        except Exception as error:
            raise SourceDatabaseIntegrityError(
                f"Active contract registry row is invalid for {output.key}"
            ) from error
        if identity is None:
            raise SourceDatabaseIntegrityError(
                f"Active contract is absent from the registry for {output.key}"
            )
        if (identity.analysis_family, identity.output_kind) != output.key:
            raise SourceDatabaseIntegrityError(
                "Active contract setting points at another family/output: "
                f"{output.key}"
            )
        try:
            validate_production_contract(identity)
        except ValueError as error:
            raise SourceDatabaseIntegrityError(
                f"Active contract is not a complete production identity: {output.key}"
            ) from error
        if (
            identity.output_kind == "embedding"
            and identity.analysis_family in {"maest", "mert", "muq", "clap"}
        ):
            current = current_embedding_analysis_output(identity.analysis_family)
            if (
                identity.contract_hash != current.contract_hash
                or identity.canonical_payload_json
                != current.contract.canonical_payload_json
            ):
                continue
        if identity.analysis_family == "sonara":
            if active_release is None or identity.release_hash != active_release:
                continue
        active[output.key] = identity
    return active


_SONARA_SELECT = """
    s.contract_hash AS sonara_contract_hash,
    s.detected_bpm AS sonara_detected_bpm,
    s.raw_bpm AS sonara_raw_bpm,
    s.bpm_confidence AS sonara_bpm_confidence,
    s.onset_density_per_second AS sonara_onset_density_per_second,
    s.beat_count AS sonara_beat_count,
    s.tempo_variability AS sonara_tempo_variability,
    s.beat_grid_offset_seconds AS sonara_beat_grid_offset_seconds,
    s.beat_grid_stability AS sonara_beat_grid_stability,
    s.detected_key_name AS sonara_detected_key_name,
    s.detected_key_camelot AS sonara_detected_key_camelot,
    s.key_confidence AS sonara_key_confidence,
    s.predominant_chord AS sonara_predominant_chord,
    s.chord_changes_per_second AS sonara_chord_changes_per_second,
    s.energy_score AS sonara_energy_score,
    s.energy_level AS sonara_energy_level,
    s.danceability_score AS sonara_danceability_score,
    s.valence_score AS sonara_valence_score,
    s.acousticness_score AS sonara_acousticness_score,
    s.dissonance_score AS sonara_dissonance_score,
    s.spectral_centroid_hz AS sonara_spectral_centroid_hz,
    s.spectral_bandwidth_hz AS sonara_spectral_bandwidth_hz,
    s.spectral_rolloff_hz AS sonara_spectral_rolloff_hz,
    s.spectral_flatness AS sonara_spectral_flatness,
    s.zero_crossing_rate AS sonara_zero_crossing_rate,
    s.rms_mean AS sonara_rms_mean,
    s.rms_max AS sonara_rms_max,
    s.integrated_loudness_lufs AS sonara_integrated_loudness_lufs,
    s.dynamic_range_db AS sonara_dynamic_range_db,
    s.true_peak_dbtp AS sonara_true_peak_dbtp,
    s.replay_gain_db AS sonara_replay_gain_db,
    s.max_momentary_loudness_lufs AS sonara_max_momentary_loudness_lufs,
    s.loudness_range_lu AS sonara_loudness_range_lu,
    s.analyzed_duration_seconds AS sonara_analyzed_duration_seconds,
    s.intro_end_seconds AS sonara_intro_end_seconds,
    s.outro_start_seconds AS sonara_outro_start_seconds,
    s.leading_silence_seconds AS sonara_leading_silence_seconds,
    s.trailing_silence_seconds AS sonara_trailing_silence_seconds,
    s.energy_curve_hop_seconds AS sonara_energy_curve_hop_seconds,
    s.energy_curve_sample_count AS sonara_energy_curve_sample_count,
    s.energy_curve_min AS sonara_energy_curve_min,
    s.energy_curve_max AS sonara_energy_curve_max,
    s.energy_curve_mean AS sonara_energy_curve_mean,
    s.energy_curve_stddev AS sonara_energy_curve_stddev,
    s.vocal_probability AS sonara_vocal_probability,
    s.mood_happy_score AS sonara_mood_happy_score,
    s.mood_aggressive_score AS sonara_mood_aggressive_score,
    s.mood_relaxed_score AS sonara_mood_relaxed_score,
    s.mood_sad_score AS sonara_mood_sad_score,
    s.mfcc_mean_blob AS sonara_mfcc_mean_blob,
    s.chroma_mean_blob AS sonara_chroma_mean_blob,
    s.spectral_contrast_mean_blob AS sonara_spectral_contrast_mean_blob,
    s.analyzed_at AS sonara_analyzed_at
"""


def _base_track_query(id_clause: str) -> str:
    return f"""
        SELECT
            t.track_id,
            t.track_uuid,
            t.content_generation,
            t.file_path,
            t.file_size_bytes,
            t.file_modified_ns,
            t.audio_duration_seconds,
            ft.title,
            ft.artist,
            ft.album,
            ft.tag_bpm,
            ft.tag_key,
            ft.comment,
            ft.year,
            ft.label,
            ft.catalog_number,
            ft.country,
            ft.isrc,
            ft.track_number,
            ft.disc_number,
            ft.genres_json,
            ft.tags_read_at,
            l.track_id IS NOT NULL AS liked,
            {_SONARA_SELECT},
            ms.contract_hash AS maest_contract_hash,
            ms.syncopated_rhythm AS maest_syncopated_rhythm,
            ms.genres_json AS maest_genres_json,
            ms.analyzed_at AS maest_analyzed_at
        FROM tracks AS t
        LEFT JOIN file_tags AS ft ON ft.track_id = t.track_id
        LEFT JOIN likes AS l ON l.track_id = t.track_id
        LEFT JOIN sonara AS s
          ON s.track_id = t.track_id
         AND s.content_generation = t.content_generation
         AND s.contract_hash = ?
        LEFT JOIN maest_scores AS ms
          ON ms.track_id = t.track_id
         AND ms.content_generation = t.content_generation
         AND ms.contract_hash = ?
        WHERE t.missing_since IS NULL
          {id_clause}
        ORDER BY COALESCE(ft.artist, ''), COALESCE(ft.title, ''), t.file_path,
                 t.track_id
    """


def _load_tracks(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    track_ids: Iterable[int] | None = None,
    active: Mapping[tuple[str, str], ContractIdentity] | None = None,
) -> tuple[SourceTrack, ...]:
    active_contracts = dict(active or _active_contracts(connection))
    sonara_contract = active_contracts.get(SONARA_CORE_OUTPUT.key)
    maest_contract = active_contracts.get(MAEST_ANALYSIS_OUTPUT.key)
    query_params = (
        _contract_hash_or_unavailable(sonara_contract),
        _contract_hash_or_unavailable(maest_contract),
    )
    rows: list[sqlite3.Row] = []
    if track_ids is None:
        rows.extend(connection.execute(_base_track_query(""), query_params))
    else:
        clean_ids = list(dict.fromkeys(_positive_track_id(value) for value in track_ids))
        for start in range(0, len(clean_ids), _READ_CHUNK_SIZE):
            chunk = clean_ids[start : start + _READ_CHUNK_SIZE]
            placeholders = ", ".join("?" for _ in chunk)
            rows.extend(
                connection.execute(
                    _base_track_query(f"AND t.track_id IN ({placeholders})"),
                    (*query_params, *chunk),
                )
            )

    selected_ids = [int(row["track_id"]) for row in rows]
    ready_embeddings = {
        family: set(
            _ready_embedding_vectors(
                connection,
                family=family,
                contract=contract,
                track_ids=selected_ids,
            )
        )
        for family, output in EMBEDDING_OUTPUTS.items()
        if (contract := active_contracts.get(output.key)) is not None
    }
    result = tuple(
        _source_track_from_row(
            row,
            catalog_uuid=catalog_uuid,
            sonara_contract=sonara_contract,
            maest_contract=maest_contract,
            ready_embeddings=ready_embeddings,
        )
        for row in rows
    )
    if track_ids is None:
        return result
    by_id = {track.track_id: track for track in result}
    return tuple(by_id[track_id] for track_id in clean_ids if track_id in by_id)


def _source_track_from_row(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
    sonara_contract: ContractIdentity | None,
    maest_contract: ContractIdentity | None,
    ready_embeddings: Mapping[str, set[int]],
) -> SourceTrack:
    track_id = int(row["track_id"])
    sonara = _sonara_features_from_row(row)
    maest = _maest_from_row(row)
    sonara_identity = sonara_contract if sonara is not None else None
    maest_identity = maest_contract if maest is not None else None
    coverage = AnalysisCoverage(
        sonara_core=sonara is not None,
        maest_analysis=maest is not None,
        maest_embedding=track_id in ready_embeddings.get("maest", set()),
        mert=track_id in ready_embeddings.get("mert", set()),
        muq=track_id in ready_embeddings.get("muq", set()),
        clap=track_id in ready_embeddings.get("clap", set()),
    )
    return SourceTrack(
        catalog_uuid=catalog_uuid,
        track_id=track_id,
        track_uuid=str(row["track_uuid"]),
        content_generation=int(row["content_generation"]),
        file_path=str(row["file_path"]),
        file_size_bytes=int(row["file_size_bytes"]),
        file_modified_ns=int(row["file_modified_ns"]),
        audio_duration_seconds=_optional_finite_float(
            row["audio_duration_seconds"],
            "tracks.audio_duration_seconds",
        ),
        file_tags=_file_tags_from_row(row),
        liked=bool(row["liked"]),
        sonara_features=sonara,
        sonara_contract=sonara_identity,
        maest=maest,
        maest_contract=maest_identity,
        analysis_coverage=coverage,
    )


def _file_tags_from_row(row: sqlite3.Row) -> FileTags | None:
    if row["tags_read_at"] is None:
        return None
    return FileTags(
        title=_optional_text(row["title"]),
        artist=_optional_text(row["artist"]),
        album=_optional_text(row["album"]),
        tag_bpm=_optional_finite_float(row["tag_bpm"], "file_tags.tag_bpm"),
        tag_key=_optional_text(row["tag_key"]),
        comment=_optional_text(row["comment"]),
        year=None if row["year"] is None else int(row["year"]),
        label=_optional_text(row["label"]),
        catalog_number=_optional_text(row["catalog_number"]),
        country=_optional_text(row["country"]),
        isrc=_optional_text(row["isrc"]),
        track_number=_optional_text(row["track_number"]),
        disc_number=_optional_text(row["disc_number"]),
        genres=_file_genres(row["genres_json"]),
        tags_read_at=str(row["tags_read_at"]),
    )


_SONARA_FLOAT_FIELDS = (
    "detected_bpm",
    "raw_bpm",
    "bpm_confidence",
    "onset_density_per_second",
    "tempo_variability",
    "beat_grid_offset_seconds",
    "beat_grid_stability",
    "key_confidence",
    "chord_changes_per_second",
    "energy_score",
    "danceability_score",
    "valence_score",
    "acousticness_score",
    "dissonance_score",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "spectral_rolloff_hz",
    "spectral_flatness",
    "zero_crossing_rate",
    "rms_mean",
    "rms_max",
    "integrated_loudness_lufs",
    "dynamic_range_db",
    "true_peak_dbtp",
    "replay_gain_db",
    "max_momentary_loudness_lufs",
    "loudness_range_lu",
    "analyzed_duration_seconds",
    "intro_end_seconds",
    "outro_start_seconds",
    "leading_silence_seconds",
    "trailing_silence_seconds",
    "energy_curve_hop_seconds",
    "energy_curve_min",
    "energy_curve_max",
    "energy_curve_mean",
    "energy_curve_stddev",
    "vocal_probability",
    "mood_happy_score",
    "mood_aggressive_score",
    "mood_relaxed_score",
    "mood_sad_score",
)


def _sonara_features_from_row(
    row: sqlite3.Row,
) -> SourceSonaraFeatures | None:
    if row["sonara_contract_hash"] is None:
        return None
    mfcc = _float_tuple(row["sonara_mfcc_mean_blob"], 13)
    chroma = _float_tuple(row["sonara_chroma_mean_blob"], 12)
    contrast = _float_tuple(row["sonara_spectral_contrast_mean_blob"], 7)
    if mfcc is None or chroma is None or contrast is None:
        return None
    floats = {
        field: _optional_finite_float(
            row[f"sonara_{field}"],
            f"sonara.{field}",
        )
        for field in _SONARA_FLOAT_FIELDS
    }
    return SourceSonaraFeatures(
        detected_bpm=floats["detected_bpm"],
        raw_bpm=floats["raw_bpm"],
        bpm_confidence=floats["bpm_confidence"],
        onset_density_per_second=floats["onset_density_per_second"],
        beat_count=(
            None
            if row["sonara_beat_count"] is None
            else int(row["sonara_beat_count"])
        ),
        tempo_variability=floats["tempo_variability"],
        beat_grid_offset_seconds=floats["beat_grid_offset_seconds"],
        beat_grid_stability=floats["beat_grid_stability"],
        detected_key_name=_optional_text(row["sonara_detected_key_name"]),
        detected_key_camelot=_optional_text(
            row["sonara_detected_key_camelot"]
        ),
        key_confidence=floats["key_confidence"],
        predominant_chord=_optional_text(row["sonara_predominant_chord"]),
        chord_changes_per_second=floats["chord_changes_per_second"],
        energy_score=floats["energy_score"],
        energy_level=(
            None
            if row["sonara_energy_level"] is None
            else int(row["sonara_energy_level"])
        ),
        danceability_score=floats["danceability_score"],
        valence_score=floats["valence_score"],
        acousticness_score=floats["acousticness_score"],
        dissonance_score=floats["dissonance_score"],
        spectral_centroid_hz=floats["spectral_centroid_hz"],
        spectral_bandwidth_hz=floats["spectral_bandwidth_hz"],
        spectral_rolloff_hz=floats["spectral_rolloff_hz"],
        spectral_flatness=floats["spectral_flatness"],
        zero_crossing_rate=floats["zero_crossing_rate"],
        rms_mean=floats["rms_mean"],
        rms_max=floats["rms_max"],
        integrated_loudness_lufs=floats["integrated_loudness_lufs"],
        dynamic_range_db=floats["dynamic_range_db"],
        true_peak_dbtp=floats["true_peak_dbtp"],
        replay_gain_db=floats["replay_gain_db"],
        max_momentary_loudness_lufs=floats[
            "max_momentary_loudness_lufs"
        ],
        loudness_range_lu=floats["loudness_range_lu"],
        analyzed_duration_seconds=floats["analyzed_duration_seconds"],
        intro_end_seconds=floats["intro_end_seconds"],
        outro_start_seconds=floats["outro_start_seconds"],
        leading_silence_seconds=floats["leading_silence_seconds"],
        trailing_silence_seconds=floats["trailing_silence_seconds"],
        energy_curve_hop_seconds=floats["energy_curve_hop_seconds"],
        energy_curve_sample_count=(
            None
            if row["sonara_energy_curve_sample_count"] is None
            else int(row["sonara_energy_curve_sample_count"])
        ),
        energy_curve_min=floats["energy_curve_min"],
        energy_curve_max=floats["energy_curve_max"],
        energy_curve_mean=floats["energy_curve_mean"],
        energy_curve_stddev=floats["energy_curve_stddev"],
        vocal_probability=floats["vocal_probability"],
        mood_happy_score=floats["mood_happy_score"],
        mood_aggressive_score=floats["mood_aggressive_score"],
        mood_relaxed_score=floats["mood_relaxed_score"],
        mood_sad_score=floats["mood_sad_score"],
        mfcc_mean=mfcc,
        chroma_mean=chroma,
        spectral_contrast_mean=contrast,
        analyzed_at=str(row["sonara_analyzed_at"]),
    )


def _maest_from_row(row: sqlite3.Row) -> MaestAnalysis | None:
    if row["maest_contract_hash"] is None:
        return None
    raw_syncopated = row["maest_syncopated_rhythm"]
    return MaestAnalysis(
        syncopated_rhythm=(
            None if raw_syncopated is None else bool(raw_syncopated)
        ),
        genres=_maest_genres(row["maest_genres_json"]),
        analyzed_at=str(row["maest_analyzed_at"]),
    )


def _ready_embedding_vectors(
    connection: sqlite3.Connection,
    *,
    family: EmbeddingFamily,
    contract: ContractIdentity,
    track_ids: Iterable[int] | None = None,
) -> dict[int, np.ndarray]:
    table = _EMBEDDING_TABLES[family]
    clauses = [
        "t.missing_since IS NULL",
        "a.contract_hash = ?",
        "a.track_uuid = t.track_uuid",
        "a.content_generation = t.content_generation",
    ]
    params: list[object] = [contract.contract_hash]
    if track_ids is not None:
        clean_ids = list(dict.fromkeys(_positive_track_id(value) for value in track_ids))
        if not clean_ids:
            return {}
        placeholders = ", ".join("?" for _ in clean_ids)
        clauses.append(f"a.track_id IN ({placeholders})")
        params.extend(clean_ids)
    rows = connection.execute(
        f"""
        SELECT a.track_id, a.track_uuid, a.content_generation,
               a.contract_hash, a.dim, a.normalization, a.embedding_blob
        FROM artifacts.{table} AS a
        JOIN tracks AS t ON t.track_id = a.track_id
        WHERE {' AND '.join(clauses)}
        ORDER BY a.track_id
        """,
        params,
    ).fetchall()
    vectors: dict[int, np.ndarray] = {}
    for row in rows:
        vector = _embedding_vector(row, contract=contract)
        if vector is not None:
            vectors[int(row["track_id"])] = vector
    return vectors


def _embedding_vector(
    row: sqlite3.Row,
    *,
    contract: ContractIdentity,
) -> np.ndarray | None:
    if contract.dim is None or contract.normalization is None:
        return None
    if int(row["dim"]) != contract.dim:
        return None
    if str(row["normalization"]) != contract.normalization:
        return None
    blob = row["embedding_blob"]
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        return None
    if len(blob) != contract.dim * 4:
        return None
    vector = np.frombuffer(blob, dtype="<f4")
    if vector.shape != (contract.dim,) or not bool(np.all(np.isfinite(vector))):
        return None
    if contract.normalization == "l2":
        norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
        if not math.isfinite(norm) or not np.isclose(
            norm,
            1.0,
            rtol=1e-4,
            atol=1e-5,
        ):
            return None
    return vector.astype(np.float32, copy=True)


def _track_page_joins(collection_join: str) -> str:
    return f"""
        LEFT JOIN file_tags AS ft ON ft.track_id = t.track_id
        LEFT JOIN likes AS l ON l.track_id = t.track_id
        LEFT JOIN sonara AS s
          ON s.track_id = t.track_id
         AND s.content_generation = t.content_generation
         AND s.contract_hash = :sonara_contract_hash
        LEFT JOIN maest_scores AS ms
          ON ms.track_id = t.track_id
         AND ms.content_generation = t.content_generation
         AND ms.contract_hash = :maest_contract_hash
        {collection_join}
        LEFT JOIN labels.classifier_labels AS rl
          ON rl.classifier_key = :classifier_key
         AND rl.catalog_uuid = :catalog_uuid
         AND rl.track_uuid = t.track_uuid
         AND rl.content_generation = t.content_generation
         AND rl.selected_path = t.file_path
    """


def _track_page_filters(
    *,
    params: dict[str, object],
    query: str,
    syncopated: str,
    bpm_min: float | None,
    bpm_max: float | None,
    liked: str,
    label: str,
    label_keys: tuple[str, ...],
) -> list[str]:
    where = ["t.missing_since IS NULL"]
    needle = query.strip().casefold()
    if needle:
        params["query_like"] = f"%{needle}%"
        where.append(
            """
            (
                LOWER(COALESCE(ft.artist, '')) LIKE :query_like
                OR LOWER(COALESCE(ft.title, '')) LIKE :query_like
                OR LOWER(COALESCE(ft.album, '')) LIKE :query_like
                OR LOWER(t.file_path) LIKE :query_like
                OR LOWER(COALESCE(ft.genres_json, '')) LIKE :query_like
            )
            """
        )
    if syncopated == "yes":
        where.append(
            "ms.track_id IS NOT NULL AND ms.syncopated_rhythm = 1"
        )
    elif syncopated == "no":
        where.append(
            "ms.track_id IS NOT NULL AND ms.syncopated_rhythm = 0"
        )
    elif syncopated != "all":
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    if bpm_min is not None:
        params["bpm_min"] = float(bpm_min)
        where.append("s.detected_bpm >= :bpm_min")
    if bpm_max is not None:
        params["bpm_max"] = float(bpm_max)
        where.append("s.detected_bpm <= :bpm_max")
    if liked == "yes":
        where.append("l.track_id IS NOT NULL")
    elif liked == "no":
        where.append("l.track_id IS NULL")
    elif liked != "all":
        raise ValueError(f"Unknown liked filter: {liked}")
    if label == "unlabeled":
        where.append("rl.label IS NULL")
    elif label in set(label_keys):
        params["label_filter"] = label
        where.append("rl.label = :label_filter")
    elif label != "all":
        raise ValueError(f"Unknown label filter: {label}")
    return where


def _track_page_order_sql(
    *,
    order: str,
    liked: str,
    collection: bool,
) -> str:
    path_order = (
        "COALESCE(ft.artist, ''), COALESCE(ft.title, ''), t.file_path, "
        "t.track_id"
    )
    if collection:
        return "ORDER BY rct.position, t.track_id"
    if liked == "yes":
        return f"ORDER BY l.liked_at, {path_order}"
    if order == "normal":
        return f"ORDER BY {path_order}"
    if order == "random":
        return (
            "ORDER BY rhythm_lab_random_rank(:random_seed, t.track_id), "
            f"{path_order}"
        )
    raise ValueError(f"Unknown library order: {order}")


def _track_page_item(
    track: SourceTrack,
    *,
    label: object,
    label_trained: bool,
) -> dict[str, object]:
    tags = track.file_tags
    maest_genres = track.maest.genres if track.maest is not None else ()
    return {
        "catalog_uuid": track.catalog_uuid,
        "track_id": track.track_id,
        "track_uuid": track.track_uuid,
        "content_generation": track.content_generation,
        "file_path": track.file_path,
        "artist": tags.artist if tags is not None else None,
        "title": tags.title if tags is not None else None,
        "album": tags.album if tags is not None else None,
        "tag_bpm": tags.tag_bpm if tags is not None else None,
        "sonara_bpm": (
            track.sonara_features.detected_bpm
            if track.sonara_features is not None
            else None
        ),
        "tag_key": tags.tag_key if tags is not None else None,
        "genres": list(tags.genres) if tags is not None else [],
        "maest_genre_scores": {
            genre.genre_name: genre.score for genre in maest_genres
        },
        "liked": track.liked,
        "label": label,
        "label_trained": label_trained,
        "maest_syncopated_rhythm": (
            track.maest.syncopated_rhythm
            if track.maest is not None
            else None
        ),
        "feature_status": _feature_status(track.analysis_coverage),
    }


def _prediction_page_cte(trained_members: str) -> str:
    return f"""
        WITH ranked_predictions AS (
            SELECT
                p.rowid AS prediction_rowid,
                p.catalog_uuid,
                p.track_uuid,
                p.content_generation,
                p.selected_path,
                p.artist AS prediction_artist,
                p.title AS prediction_title,
                p.feature_set,
                p.model_artifact,
                p.label AS predicted_label,
                p.confidence,
                p.probabilities_json,
                p.updated_at,
                CAST(
                    json_extract(
                        p.probabilities_json,
                        :positive_probability_path
                    ) AS REAL
                ) AS positive_probability,
                CAST(
                    json_extract(
                        p.probabilities_json,
                        :negative_probability_path
                    ) AS REAL
                ) AS negative_probability,
                ROW_NUMBER() OVER (
                    PARTITION BY p.catalog_uuid, p.track_uuid,
                                 p.content_generation, p.selected_path
                    ORDER BY COALESCE(p.updated_at, '') DESC,
                             p.rowid DESC,
                             p.model_artifact DESC
                ) AS prediction_rank
            FROM labels.classifier_predictions AS p
            WHERE p.classifier_key = :classifier_key
              AND p.catalog_uuid = :catalog_uuid
        ),
        latest_predictions AS (
            SELECT *
            FROM ranked_predictions
            WHERE prediction_rank = 1
        ),
        candidate_rows AS (
            SELECT
                p.*,
                t.track_id AS current_track_id,
                t.track_uuid AS current_track_uuid,
                t.content_generation AS current_content_generation,
                t.file_path AS current_file_path,
                ft.artist AS current_artist,
                ft.title AS current_title,
                ft.album AS current_album,
                s.detected_bpm AS current_sonara_bpm,
                ms.syncopated_rhythm AS current_syncopated_rhythm,
                rl.label AS classifier_label,
                CASE WHEN rl.label IN ({trained_members})
                     AND cp.updated_at IS NOT NULL
                     AND rl.updated_at <= cp.updated_at
                     THEN 1 ELSE 0 END AS classifier_label_trained
            FROM latest_predictions AS p
            LEFT JOIN tracks AS t
              ON p.catalog_uuid = :catalog_uuid
             AND t.track_uuid = p.track_uuid
             AND t.content_generation = p.content_generation
             AND t.file_path = p.selected_path
             AND t.missing_since IS NULL
            LEFT JOIN file_tags AS ft ON ft.track_id = t.track_id
            LEFT JOIN sonara AS s
              ON s.track_id = t.track_id
             AND s.content_generation = t.content_generation
             AND s.contract_hash = :sonara_contract_hash
            LEFT JOIN maest_scores AS ms
              ON ms.track_id = t.track_id
             AND ms.content_generation = t.content_generation
             AND ms.contract_hash = :maest_contract_hash
            LEFT JOIN labels.classifier_labels AS rl
              ON rl.classifier_key = :classifier_key
             AND rl.catalog_uuid = p.catalog_uuid
             AND rl.track_uuid = p.track_uuid
             AND rl.content_generation = p.content_generation
             AND rl.selected_path = p.selected_path
            LEFT JOIN labels.classifier_training_checkpoints AS cp
              ON cp.classifier_key = :classifier_key
        )
    """


def _prediction_page_filter_sql(
    *,
    params: dict[str, object],
    query: str,
    syncopated: str,
    bpm_min: float | None,
    bpm_max: float | None,
    label: str,
    predicted: str,
    label_keys: tuple[str, ...],
    min_positive: float,
    profile_type: str,
) -> str:
    where: list[str] = []
    needle = query.strip().casefold()
    if needle:
        params["query_like"] = f"%{needle}%"
        where.extend(
            (
                "current_track_id IS NOT NULL",
                """
                (
                    LOWER(COALESCE(current_artist, '')) LIKE :query_like
                    OR LOWER(COALESCE(current_title, '')) LIKE :query_like
                    OR LOWER(COALESCE(current_album, '')) LIKE :query_like
                    OR LOWER(COALESCE(current_file_path, '')) LIKE :query_like
                )
                """,
            )
        )
    if syncopated == "yes":
        where.extend(
            (
                "current_track_id IS NOT NULL",
                "current_syncopated_rhythm = 1",
            )
        )
    elif syncopated == "no":
        where.extend(
            (
                "current_track_id IS NOT NULL",
                "current_syncopated_rhythm = 0",
            )
        )
    elif syncopated != "all":
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    if bpm_min is not None:
        params["bpm_min"] = float(bpm_min)
        where.extend(
            (
                "current_track_id IS NOT NULL",
                "current_sonara_bpm >= :bpm_min",
            )
        )
    if bpm_max is not None:
        params["bpm_max"] = float(bpm_max)
        where.extend(
            (
                "current_track_id IS NOT NULL",
                "current_sonara_bpm <= :bpm_max",
            )
        )
    if label == "unlabeled":
        where.append("classifier_label IS NULL")
    elif label in set(label_keys):
        params["label_filter"] = label
        where.append("classifier_label = :label_filter")
    elif label != "all":
        raise ValueError(f"Unknown label filter: {label}")
    if predicted != "all":
        params["predicted_filter"] = predicted
        where.append("predicted_label = :predicted_filter")
    threshold_column = (
        "confidence" if profile_type == "multiclass" else "positive_probability"
    )
    if min_positive > 0.0:
        params["min_positive"] = float(min_positive)
        where.append(f"{threshold_column} >= :min_positive")
    return f"WHERE {' AND '.join(where)}" if where else ""


def _prediction_page_order_sql(
    probability_focus: str,
    profile_type: str,
) -> str:
    path_order = "LOWER(COALESCE(current_file_path, selected_path, ''))"
    if profile_type == "multiclass":
        if probability_focus == "balanced":
            return f"ORDER BY confidence, {path_order}"
        return f"ORDER BY confidence DESC, {path_order}"
    if probability_focus == "negative_highest":
        return (
            "ORDER BY negative_probability DESC, confidence DESC, "
            f"{path_order}"
        )
    if probability_focus == "balanced":
        return (
            "ORDER BY ABS(positive_probability - negative_probability), "
            f"confidence DESC, {path_order}"
        )
    return (
        "ORDER BY positive_probability DESC, confidence DESC, "
        f"{path_order}"
    )


def _prediction_page_item(
    row: sqlite3.Row,
    *,
    track: SourceTrack | None,
    profile_type: str,
    positive_label: str,
    negative_label: str,
) -> dict[str, object]:
    tags = track.file_tags if track is not None else None
    probabilities = _probabilities_from_json(row["probabilities_json"])
    positive_probability = probabilities.get(positive_label)
    negative_probability = probabilities.get(negative_label)
    return {
        "catalog_uuid": str(row["catalog_uuid"]),
        "track_id": track.track_id if track is not None else None,
        "track_uuid": str(row["track_uuid"]),
        "content_generation": int(row["content_generation"]),
        "selected_path": (
            track.file_path if track is not None else str(row["selected_path"])
        ),
        "file_path": (
            track.file_path if track is not None else str(row["selected_path"])
        ),
        "artist": (
            tags.artist
            if tags is not None
            else row["prediction_artist"]
        ),
        "title": (
            tags.title
            if tags is not None
            else row["prediction_title"]
        ),
        "sonara_bpm": (
            track.sonara_features.detected_bpm
            if track is not None and track.sonara_features is not None
            else None
        ),
        "liked": track.liked if track is not None else False,
        "label": row["classifier_label"],
        "label_trained": bool(row["classifier_label_trained"]),
        "predicted_label": row["predicted_label"],
        "confidence": float(row["confidence"]),
        "profile_type": profile_type,
        "positive_probability": positive_probability,
        "negative_probability": negative_probability,
        "positive_label": positive_label,
        "negative_label": negative_label,
        "probabilities": probabilities,
        "feature_set": row["feature_set"],
        "model_artifact": row["model_artifact"],
        "genres": list(tags.genres) if tags is not None else [],
        "maest_genre_scores": (
            {
                genre.genre_name: genre.score
                for genre in track.maest.genres
            }
            if track is not None and track.maest is not None
            else {}
        ),
        "maest_syncopated_rhythm": (
            track.maest.syncopated_rhythm
            if track is not None and track.maest is not None
            else None
        ),
        "feature_status": (
            _feature_status(track.analysis_coverage)
            if track is not None
            else _feature_status(AnalysisCoverage())
        ),
    }


def _feature_status(coverage: AnalysisCoverage) -> dict[str, bool]:
    return {
        "sonara": coverage.sonara_core,
        "mert": coverage.mert,
        "maest": coverage.maest_embedding,
        "clap": coverage.clap,
        "muq": coverage.muq,
    }


def _attach_labels(
    connection: sqlite3.Connection,
    labels_path: Path,
) -> None:
    connection.execute(
        "ATTACH DATABASE ? AS labels",
        (_readonly_uri(labels_path),),
    )


_COLLECTION_COLUMNS = {
    "collection_id",
    "catalog_uuid",
    "track_uuid",
    "content_generation",
    "selected_path",
    "position",
    "score",
    "note",
    "added_at",
}


def _require_collection_identity_schema(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA labels.table_info(review_collection_tracks)"
        )
    }
    if columns != _COLLECTION_COLUMNS:
        raise SourceDatabaseIntegrityError(
            "Review collection rows do not use the exact v7 source identity"
        )
    collection_columns = {
        str(row["name"])
        for row in connection.execute(
            "PRAGMA labels.table_info(review_collections)"
        )
    }
    if "catalog_uuid" not in collection_columns:
        raise SourceDatabaseIntegrityError(
            "Review collections are not bound to a source catalog"
        )


def _file_genres(payload: object) -> tuple[str, ...]:
    values = _json_array(payload, "file_tags.genres_json")
    if any(not isinstance(value, str) for value in values):
        raise SourceDatabaseIntegrityError(
            "file_tags.genres_json must contain only strings"
        )
    return tuple(str(value) for value in values)


def _maest_genres(payload: object) -> tuple[MaestGenre, ...]:
    values = _json_array(payload, "maest_scores.genres_json")
    result: list[MaestGenre] = []
    for rank, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            continue
        label = value.get("label")
        score = value.get("score")
        if not isinstance(label, str) or not label.strip():
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        number = float(score)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            continue
        result.append(
            MaestGenre(
                rank=rank,
                genre_name=label.strip(),
                score=number,
            )
        )
    return tuple(result)


def _json_array(payload: object, field_name: str) -> list[object]:
    try:
        values = json.loads(str(payload))
    except (TypeError, json.JSONDecodeError) as error:
        raise SourceDatabaseIntegrityError(
            f"{field_name} is not valid JSON"
        ) from error
    if not isinstance(values, list):
        raise SourceDatabaseIntegrityError(
            f"{field_name} must contain a JSON array"
        )
    return values


def _probabilities_from_json(payload: object) -> dict[str, float]:
    try:
        values = json.loads(str(payload))
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(values, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in values.items():
        if (
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            return {}
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            return {}
        result[key] = number
    return result


def _float_tuple(payload: object, dim: int) -> tuple[float, ...] | None:
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        return None
    if len(payload) != dim * 4:
        return None
    vector = np.frombuffer(payload, dtype="<f4")
    if vector.shape != (dim,) or not bool(np.all(np.isfinite(vector))):
        return None
    return tuple(float(value) for value in vector)


def _contract_hash_or_unavailable(
    contract: ContractIdentity | None,
) -> str:
    return contract.contract_hash if contract is not None else "__not_active__"


def _embedding_family(value: object) -> EmbeddingFamily:
    clean = str(value).strip().lower()
    if clean not in _EMBEDDING_TABLES:
        raise ValueError(
            "Embedding family must be one of: "
            + ", ".join(sorted(_EMBEDDING_TABLES))
        )
    return clean  # type: ignore[return-value]


def _labels_database_path(path: str | Path) -> Path:
    selected = Path(_clean_path_text(path)).expanduser().resolve(strict=False)
    if not selected.is_file():
        raise FileNotFoundError(f"Rhythm Lab database does not exist: {selected}")
    return selected


def _clean_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_non_empty_text(
    value: object,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _non_empty_text(value, field_name)


def _optional_finite_float(
    value: object,
    field_name: str,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise SourceDatabaseIntegrityError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SourceDatabaseIntegrityError(
            f"{field_name} must be finite"
        ) from error
    if not math.isfinite(number):
        raise SourceDatabaseIntegrityError(f"{field_name} must be finite")
    return number


def _positive_track_id(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("track_id must be a positive integer")
    try:
        clean = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("track_id must be a positive integer") from error
    if clean <= 0:
        raise ValueError("track_id must be a positive integer")
    return clean


def _positive_generation(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("content_generation must be a positive integer")
    try:
        clean = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "content_generation must be a positive integer"
        ) from error
    if clean <= 0:
        raise ValueError("content_generation must be a positive integer")
    return clean


def _positive_collection_id(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("collection_id must be a positive integer")
    try:
        clean = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("collection_id must be a positive integer") from error
    if clean <= 0:
        raise ValueError("collection_id must be a positive integer")
    return clean


def _json_probability_path(label: str) -> str:
    clean = _non_empty_text(label, "probability label")
    return f"$.{clean}"


def _random_seed_value(seed: object) -> int:
    try:
        value = int(seed)
    except (TypeError, ValueError) as error:
        raise ValueError("Library random seed must be an integer") from error
    return max(0, value)


def _stable_random_rank(seed: object, track_id: object) -> int:
    payload = f"{int(seed)}:{int(track_id)}".encode("ascii")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return (
        int.from_bytes(digest, byteorder="big", signed=False)
        & 0x7FFFFFFFFFFFFFFF
    )

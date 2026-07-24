from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    SonaraWrite,
    StaleAnalysisTargetError,
)
from dj_track_similarity.db_analysis import AnalysisRepository
from dj_track_similarity.db_artifacts import (
    create_artifacts_sidecar_schema,
)
from dj_track_similarity.db_schema_v7 import (
    SonaraRowV7,
    create_v7_schema,
)
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    prepare_sonara_release,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    SonaraContractSet,
    sonara_runtime_contracts,
)
from dj_track_similarity.sonara_similarity import (
    SonaraSimilaritySearch,
)
from dj_track_similarity.sonara_similarity_scoring import (
    _scaled_weighted_euclidean_distance,
)


_NOW = "2026-07-24T10:00:00.000000Z"


class _FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "5" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness"
    __sonara_vocalness_model_build_id__ = "sha256:" + "6" * 64


class _Repository(AnalysisRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.artifacts_path = root / "library.artifacts.sqlite"
        self.catalog_uuid = str(uuid.uuid4())
        self._write_lock = threading.RLock()

        core = sqlite3.connect(self.path)
        try:
            create_v7_schema(core)
            core.execute(
                """
                INSERT INTO library_catalog (
                    singleton_id, catalog_uuid, created_at, updated_at
                ) VALUES (1, ?, ?, ?)
                """,
                (self.catalog_uuid, _NOW, _NOW),
            )
            core.commit()
        finally:
            core.close()

        artifacts = sqlite3.connect(self.artifacts_path)
        try:
            create_artifacts_sidecar_schema(
                artifacts,
                catalog_uuid=self.catalog_uuid,
            )
            artifacts.commit()
        finally:
            artifacts.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def connect_artifacts(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.artifacts_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _insert_track(
    repository: _Repository,
    track_uuid: str,
) -> AnalysisTarget:
    with repository.connect() as core:
        cursor = core.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                _NOW,
                _NOW,
                _NOW,
            ),
        )
    return AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=int(cursor.lastrowid),
        track_uuid=track_uuid,
        content_generation=1,
    )


def _contracts() -> SonaraContractSet:
    return sonara_runtime_contracts(_FakeSonara)


def _prepare_release(repository: _Repository) -> SonaraContractSet:
    backup_dir = repository.path.parent / "sonara-backups"
    backup_dir.mkdir()
    prepare_sonara_release(
        repository,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=_FakeSonara,
    )
    return _contracts()


def _core_row(
    target: AnalysisTarget,
    contracts: SonaraContractSet,
    *,
    energy: float,
    danceability: float,
    valence: float,
    acousticness: float,
    bpm: float,
) -> SonaraRowV7:
    values = {field.name: None for field in fields(SonaraRowV7)}
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "contract_hash": contracts.core.contract_hash,
            "detected_bpm": bpm,
            "bpm_confidence": 0.95,
            "beat_grid_stability": 0.95,
            "onset_density_per_second": danceability * 4.0,
            "detected_key_name": "A minor",
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "predominant_chord": "Am",
            "chord_changes_per_second": danceability,
            "energy_score": energy,
            "energy_level": max(1, round(energy * 10.0)),
            "danceability_score": danceability,
            "valence_score": valence,
            "acousticness_score": acousticness,
            "dissonance_score": 0.2,
            "spectral_centroid_hz": 2_000.0 + energy * 500.0,
            "spectral_bandwidth_hz": 1_000.0 + energy * 200.0,
            "spectral_rolloff_hz": 4_000.0 + energy * 500.0,
            "spectral_flatness": 0.2,
            "zero_crossing_rate": 0.1,
            "rms_mean": energy,
            "rms_max": min(1.0, energy + 0.05),
            "integrated_loudness_lufs": -18.0 + energy * 10.0,
            "dynamic_range_db": 8.0,
            "max_momentary_loudness_lufs": -12.0 + energy * 8.0,
            "loudness_range_lu": 6.0,
            "vocal_probability": 0.4,
            "mfcc_mean_blob": np.full(
                13,
                energy,
                dtype="<f4",
            ).tobytes(),
            "chroma_mean_blob": np.full(
                12,
                valence,
                dtype="<f4",
            ).tobytes(),
            "spectral_contrast_mean_blob": np.full(
                7,
                acousticness,
                dtype="<f4",
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    return SonaraRowV7(**values)


def _save_core(
    repository: _Repository,
    contracts: SonaraContractSet,
    target: AnalysisTarget,
    *,
    energy: float,
    danceability: float,
    valence: float,
    acousticness: float,
    bpm: float,
) -> None:
    result = repository.save_sonara_results(
        (
            SonaraWrite(
                target=target,
                core_contract=contracts.core,
                core=_core_row(
                    target,
                    contracts,
                    energy=energy,
                    danceability=danceability,
                    valence=valence,
                    acousticness=acousticness,
                    bpm=bpm,
                ),
            ),
        )
    )[0]
    assert result.ok, result.error


def test_sonara_modes_read_active_typed_core_and_return_full_targets(
    tmp_path: Path,
) -> None:
    repository = _Repository(tmp_path)
    contracts = _prepare_release(repository)
    seed = _insert_track(repository, "00000000-0000-4000-8000-000000000101")
    close = _insert_track(repository, "00000000-0000-4000-8000-000000000102")
    far = _insert_track(repository, "00000000-0000-4000-8000-000000000103")
    _save_core(
        repository,
        contracts,
        seed,
        energy=0.9,
        danceability=0.9,
        valence=0.8,
        acousticness=0.2,
        bpm=128.0,
    )
    _save_core(
        repository,
        contracts,
        close,
        energy=0.8,
        danceability=0.8,
        valence=0.7,
        acousticness=0.25,
        bpm=127.0,
    )
    _save_core(
        repository,
        contracts,
        far,
        energy=0.1,
        danceability=0.1,
        valence=0.2,
        acousticness=0.9,
        bpm=90.0,
    )

    searcher = SonaraSimilaritySearch(repository)
    assert searcher.active_output().contract == contracts.core
    assert searcher.resolve_targets([seed.track_id, close.track_id]) == (seed, close)

    results = searcher.search(
        (seed,),
        mode="balanced",
        limit=10,
    )
    assert [result.target for result in results] == [close, far]
    assert results[0].score > results[1].score
    assert all(
        result.target.catalog_uuid == repository.catalog_uuid
        and result.target.track_uuid
        and result.target.content_generation == 1
        for result in results
    )

    custom = searcher.search(
        (seed,),
        candidate_targets=(close,),
        mode="custom",
        mixer_weights={"dynamics": 1.0},
        limit=10,
    )
    assert [result.target for result in custom] == [close]
    assert custom[0].score_breakdown is not None
    assert "dynamics" in custom[0].score_breakdown


def test_sonara_search_rejects_stale_full_target(
    tmp_path: Path,
) -> None:
    repository = _Repository(tmp_path)
    contracts = _prepare_release(repository)
    seed = _insert_track(repository, "00000000-0000-4000-8000-000000000104")
    _save_core(
        repository,
        contracts,
        seed,
        energy=0.9,
        danceability=0.9,
        valence=0.8,
        acousticness=0.2,
        bpm=128.0,
    )
    with repository.connect() as core:
        core.execute(
            """
            UPDATE tracks
            SET content_generation = 2, updated_at = ?
            WHERE track_id = ?
            """,
            (_NOW, seed.track_id),
        )

    with pytest.raises(
        StaleAnalysisTargetError,
        match="content_generation mismatch",
    ):
        SonaraSimilaritySearch(repository).search((seed,))


def test_sonara_data_only_embedding_distance_is_scaled_euclidean() -> None:
    left = np.zeros(48, dtype=np.float32)
    right = np.zeros(48, dtype=np.float32)
    left[0] = 10.0
    right[0] = 20.0
    scales = np.ones(48, dtype=np.float32)
    scales[0] = 2.0
    weights = np.zeros(48, dtype=np.float32)
    weights[0] = 3.0

    distance = _scaled_weighted_euclidean_distance(
        left,
        right,
        scales=scales,
        weights=weights,
    )
    assert distance == pytest.approx(5.0)
    assert float(np.dot(left, right)) > 0.0
    assert float(
        np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right))
    ) == pytest.approx(1.0)

    with pytest.raises(ValueError, match="scales must be positive"):
        _scaled_weighted_euclidean_distance(
            left,
            right,
            scales=np.zeros(48, dtype=np.float32),
            weights=np.ones(48, dtype=np.float32),
        )

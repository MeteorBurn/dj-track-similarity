from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    SonaraWrite,
)
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow
from dj_track_similarity.library_models import TrackSummary
from dj_track_similarity.reference_compare import (
    ReferenceCompareQuery,
    build_reference_compare,
)
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T10:00:00.000000Z"


def _insert_track(
    database: LibraryDatabase,
    root: Path,
    name: str,
) -> AnalysisTarget:
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(root / f"{name}.wav"),
            file_size_bytes=1024,
            file_modified_ns=123456789,
            audio_format="wav",
            sample_rate_hz=44_100,
            channel_count=2,
            audio_duration_seconds=180.0,
        ),
        tags=FileTags(
            title=name,
            artist="Test Artist",
            tag_bpm=128.0,
            tag_key="8A",
        ),
        scanned_at=_NOW,
    )
    identity = mutation.identity
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
    )


def _mert_output():
    return current_embedding_analysis_output("mert")


def _mert_vector(first: float, second: float) -> np.ndarray:
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = first
    vector[1] = second
    return vector


def _sonara_row(
    target: AnalysisTarget,
    *,
    energy: float,
    danceability: float,
) -> SonaraRow:
    values = {field.name: None for field in fields(SonaraRow)}
    values.update(
        {
            "track_id": target.track_id,
            "detected_bpm": 128.0,
            "bpm_confidence": 0.95,
            "beat_grid_stability": 0.95,
            "onset_density_per_second": danceability * 4.0,
            "detected_key_name": "A minor",
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "predominant_chord": "Am",
            "chord_changes_per_second": danceability,
            "energy_score": energy,
            "danceability_score": danceability,
            "valence_score": energy,
            "acousticness_score": 1.0 - energy,
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
                energy,
                dtype="<f4",
            ).tobytes(),
            "spectral_contrast_mean_blob": np.full(
                7,
                1.0 - energy,
                dtype="<f4",
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    return SonaraRow(**values)


def test_reference_compare_uses_current_outputs_and_current_summaries(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _insert_track(database, tmp_path, "seed")
    mert_top = _insert_track(database, tmp_path, "mert-top")
    sonara_top = _insert_track(database, tmp_path, "sonara-top")
    mert_output = _mert_output()
    database.register_analysis_outputs(
        (mert_output, AnalysisOutput("sonara", "core"))
    )
    assert all(
        result.ok
        for result in database.save_embedding_results(
            (
                EmbeddingWrite(
                    target=seed,
                    output=EmbeddingOutput(
                        family="mert",
                        vector=_mert_vector(1.0, 0.0),
                        analyzed_at=_NOW,
                    ),
                ),
                EmbeddingWrite(
                    target=mert_top,
                    output=EmbeddingOutput(
                        family="mert",
                        vector=_mert_vector(0.8, 0.6),
                        analyzed_at=_NOW,
                    ),
                ),
            )
        )
    )
    for target, energy, danceability in (
        (seed, 0.9, 0.9),
        (sonara_top, 0.8, 0.8),
        (mert_top, 0.1, 0.1),
    ):
        result = database.save_sonara_results(
            (
                SonaraWrite(
                    target=target,
                    core=_sonara_row(
                        target,
                        energy=energy,
                        danceability=danceability,
                    ),
                ),
            )
        )[0]
        assert result.ok, result.error

    response = build_reference_compare(
        database,
        ReferenceCompareQuery(
            seed_track_id=seed.track_id,
            models=("mert", "clap", "sonara"),
            limit=2,
        ),
    )
    groups = {group.model: group for group in response.groups}
    assert groups["mert"].available
    assert groups["mert"].results[0].target == mert_top
    assert isinstance(groups["mert"].results[0].track, TrackSummary)
    assert groups["mert"].results[0].track.track_id == mert_top.track_id
    assert not groups["clap"].available
    assert groups["clap"].results == ()
    assert "missing CLAP embedding" in str(groups["clap"].reason)
    assert groups["sonara"].available
    assert groups["sonara"].results[0].target == sonara_top
    assert not database.evaluation_path.exists()

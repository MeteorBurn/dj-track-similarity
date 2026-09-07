from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    SonaraWrite,
)
from dj_track_similarity.analysis.model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.ddl import SonaraRow
from dj_track_similarity.library_models import TrackSummary
from dj_track_similarity.search.reference_compare import (
    ReferenceCompareQuery,
    build_reference_compare,
)
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


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
            "analysis_schema_version": 6,
            "analyzed_at": _NOW,
        }
    )
    return SonaraRow(**values)


def test_reference_compare_uses_current_outputs_and_current_summaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _insert_track(database, tmp_path, "seed")
    mert_top = _insert_track(database, tmp_path, "mert-top")
    sonara_top = _insert_track(database, tmp_path, "sonara-top")
    unrelated = _insert_track(database, tmp_path, "unrelated")
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

    for candidate, source, tags in (
        (mert_top, "reference_compare:mert", ("groove",)),
        (mert_top, "reference_compare:sonara", ("palette",)),
        (sonara_top, "reference_compare:sonara", ("mood", "palette")),
        (unrelated, "reference_compare:mert", ("miss",)),
        (sonara_top, "manual", ("transition",)),
    ):
        database.upsert_track_pair_feedback(
            seed.track_id,
            candidate.track_id,
            2,
            reason_tags=tags,
            source=source,
        )

    selected_ids: set[int] = set()
    expected_ids = {seed.track_id, mert_top.track_id, sonara_top.track_id}
    changed_summary_id: int | None = None
    get_summaries = database.get_track_summaries
    get_feedback = database.get_track_pair_feedback_tags_exact
    feedback_reads: list[tuple[TrackIdentity, tuple[TrackIdentity, ...]]] = []

    def selected_summaries(track_ids, *, include_missing=False):
        selected_ids.update(track_ids)
        assert set(track_ids) <= expected_ids
        summaries = get_summaries(track_ids, include_missing=include_missing)
        return tuple(
            replace(summary, track_uuid="changed-track")
            if summary.track_id == changed_summary_id and len(track_ids) > 1
            else summary
            for summary in summaries
        )

    def reject_full_library_hydration(*, include_missing=False):
        pytest.fail("LAB must hydrate only its seed and ranked candidates")

    def selected_feedback(reference, candidates, sources):
        assert reference == TrackIdentity(
            seed.catalog_uuid, seed.track_id, seed.track_uuid
        )
        assert {candidate.track_id for candidate in candidates} == {
            mert_top.track_id, sonara_top.track_id,
        }
        assert set(sources) == {"reference_compare:mert", "reference_compare:sonara"}
        feedback_reads.append((reference, tuple(candidates)))
        return get_feedback(reference, candidates, sources)

    def reject_full_feedback_map():
        pytest.fail("LAB must read feedback only for its seed and ranked candidates")

    monkeypatch.setattr(database, "get_track_summaries", selected_summaries)
    monkeypatch.setattr(database, "list_track_summaries", reject_full_library_hydration)
    monkeypatch.setattr(database, "get_track_pair_feedback_tags_exact", selected_feedback)
    monkeypatch.setattr(database, "get_pair_feedback_map", reject_full_feedback_map)
    query = ReferenceCompareQuery(
        seed_track_id=seed.track_id,
        models=("mert", "clap", "sonara"),
        limit=2,
    )
    response = build_reference_compare(
        database,
        query,
    )
    assert selected_ids == expected_ids
    groups = {group.model: group for group in response.groups}
    assert groups["mert"].available
    assert groups["mert"].results[0].target == mert_top
    assert isinstance(groups["mert"].results[0].track, TrackSummary)
    assert groups["mert"].results[0].track.track_id == mert_top.track_id
    assert groups["mert"].results[0].score == pytest.approx(0.8)
    assert groups["mert"].results[0].saved_verdict == "groove"
    assert not groups["clap"].available
    assert groups["clap"].results == ()
    assert "missing CLAP embedding" in str(groups["clap"].reason)
    assert groups["sonara"].available
    assert groups["sonara"].results[0].target == sonara_top
    assert [result.target for result in groups["sonara"].results] == [
        sonara_top,
        mert_top,
    ]
    assert [result.saved_verdict for result in groups["sonara"].results] == [
        None,
        "palette",
    ]
    assert len(feedback_reads) == 1
    for group in response.groups:
        for result in group.results:
            assert result.track.catalog_uuid == result.target.catalog_uuid
            assert result.track.track_uuid == result.target.track_uuid

    for changed_summary_id in (seed.track_id, mert_top.track_id):
        with pytest.raises(RuntimeError, match="identity changed"):
            build_reference_compare(database, query)

    reference, candidates = feedback_reads[0]
    for stale_reference, stale_candidates in (
        (replace(reference, track_uuid="stale-seed"), candidates),
        (reference, (replace(candidates[0], track_uuid="stale-candidate"),)),
        (reference, (replace(candidates[0], catalog_uuid="another-catalog"),)),
    ):
        with pytest.raises(RuntimeError, match="identity is stale"):
            get_feedback(
                stale_reference, stale_candidates, ("reference_compare:mert",)
            )
    assert not database.evaluation_path.exists()

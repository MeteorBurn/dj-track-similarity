from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

import dj_track_similarity.db.analysis as db_analysis_module
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.ddl import SonaraRow
from sonara_test_support import complete_sonara_write
from dj_track_similarity.search.sonara import SonaraSimilaritySearch
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"


def _library(tmp_path: Path) -> LibraryDatabase:
    return LibraryDatabase(tmp_path / "library.sqlite")


def _feature_value(features: dict[str, object], name: str) -> object:
    return features.get(name)


def _text_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _vector_blob(value: object, *, dim: int) -> bytes:
    raw = value if isinstance(value, (list, tuple)) else ()
    values = [float(item) for item in raw[:dim]]
    values.extend([0.0] * (dim - len(values)))
    return np.asarray(values, dtype="<f4").tobytes()


def _core_row(
    target: AnalysisTarget,
    features: dict[str, object],
) -> SonaraRow:
    values = {field.name: None for field in fields(SonaraRow)}
    energy = _float_or_none(_feature_value(features, "energy"))
    values.update(
        {
            "track_id": target.track_id,
            "detected_bpm": _float_or_none(_feature_value(features, "bpm")),
            "bpm_confidence": _float_or_none(
                _feature_value(features, "bpm_confidence")
            ),
            "onset_density_per_second": _float_or_none(
                _feature_value(features, "onset_density")
            ),
            "detected_key_name": _text_or_none(_feature_value(features, "key")),
            "detected_key_camelot": _text_or_none(
                _feature_value(features, "key_camelot")
                or _feature_value(features, "camelot_key")
            ),
            "key_confidence": _float_or_none(
                _feature_value(features, "key_confidence")
            ),
            "predominant_chord": _text_or_none(
                _feature_value(features, "predominant_chord")
            ),
            "chord_changes_per_second": _float_or_none(
                _feature_value(features, "chord_change_rate")
            ),
            "energy_score": energy,
            "energy_level": _int_or_none(_feature_value(features, "energy_level")),
            "danceability_score": _float_or_none(
                _feature_value(features, "danceability")
            ),
            "valence_score": _float_or_none(_feature_value(features, "valence")),
            "acousticness_score": _float_or_none(
                _feature_value(features, "acousticness")
            ),
            "dissonance_score": _float_or_none(_feature_value(features, "dissonance")),
            "spectral_centroid_hz": _float_or_none(
                _feature_value(features, "spectral_centroid_mean")
            ),
            "spectral_bandwidth_hz": _float_or_none(
                _feature_value(features, "spectral_bandwidth_mean")
            ),
            "spectral_rolloff_hz": _float_or_none(
                _feature_value(features, "spectral_rolloff_mean")
            ),
            "spectral_flatness": _float_or_none(
                _feature_value(features, "spectral_flatness_mean")
            ),
            "zero_crossing_rate": _float_or_none(
                _feature_value(features, "zero_crossing_rate")
            ),
            "rms_mean": _float_or_none(_feature_value(features, "rms_mean")),
            "rms_max": _float_or_none(_feature_value(features, "rms_max")),
            "integrated_loudness_lufs": _float_or_none(
                _feature_value(features, "loudness_lufs")
            ),
            "dynamic_range_db": _float_or_none(
                _feature_value(features, "dynamic_range_db")
            ),
            "true_peak_dbtp": _float_or_none(_feature_value(features, "true_peak_db")),
            "replay_gain_db": _float_or_none(_feature_value(features, "replaygain_db")),
            "max_momentary_loudness_lufs": _float_or_none(
                _feature_value(features, "loudness_momentary_max_db")
            ),
            "loudness_range_lu": _float_or_none(
                _feature_value(features, "loudness_range_lu")
            ),
            "analyzed_duration_seconds": _float_or_none(
                _feature_value(features, "duration_seconds")
            ),
            "intro_end_seconds": _float_or_none(
                _feature_value(features, "intro_end_seconds")
            ),
            "outro_start_seconds": _float_or_none(
                _feature_value(features, "outro_start_seconds")
            ),
            "energy_curve_hop_seconds": _float_or_none(
                _feature_value(features, "energy_curve_hop_seconds")
            ),
            "energy_curve_sample_count": _int_or_none(
                _feature_value(features, "energy_curve_sample_count")
            ),
            "energy_curve_min": _float_or_none(
                _feature_value(features, "energy_curve_min")
            ),
            "energy_curve_max": _float_or_none(
                _feature_value(features, "energy_curve_max")
            ),
            "energy_curve_mean": _float_or_none(
                _feature_value(features, "energy_curve_mean")
            ),
            "energy_curve_stddev": _float_or_none(
                _feature_value(features, "energy_curve_stddev")
            ),
            "vocal_probability": _float_or_none(_feature_value(features, "vocalness")),
            "mood_happy_score": _float_or_none(_feature_value(features, "mood_happy")),
            "mood_aggressive_score": _float_or_none(
                _feature_value(features, "mood_aggressive")
            ),
            "mood_relaxed_score": _float_or_none(
                _feature_value(features, "mood_relaxed")
            ),
            "mood_sad_score": _float_or_none(_feature_value(features, "mood_sad")),
            "aggression_score": _float_or_none(_feature_value(features, "aggression")),
            "aggression_confidence": _float_or_none(
                _feature_value(features, "aggression_confidence")
            ),
            "mfcc_mean_blob": _vector_blob(
                _feature_value(features, "mfcc_mean"), dim=13
            ),
            "chroma_mean_blob": _vector_blob(
                _feature_value(features, "chroma_mean"), dim=12
            ),
            "spectral_contrast_mean_blob": _vector_blob(
                _feature_value(features, "spectral_contrast_mean"), dim=7
            ),
            "analysis_schema_version": 6,
            "analyzed_at": _NOW,
        }
    )
    return SonaraRow(**values)


def _add_sonara_track(
    database: LibraryDatabase,
    name: str,
    features: dict[str, object],
) -> AnalysisTarget:
    path = database.path.parent / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
        ),
        tags=FileTags(title=name),
        scanned_at=_NOW,
    )
    target = AnalysisTarget(
        catalog_uuid=mutation.identity.catalog_uuid,
        track_id=mutation.identity.track_id,
        track_uuid=mutation.identity.track_uuid,
    )
    result = database.save_sonara_results(
        (
            complete_sonara_write(target, _core_row(target, features)),
        )
    )[0]
    assert result.ok, result.error
    return target


def _add_track_without_sonara(
    database: LibraryDatabase,
    name: str,
) -> AnalysisTarget:
    path = database.path.parent / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
        ),
        tags=FileTags(title=name),
        scanned_at=_NOW,
    )
    return AnalysisTarget(
        catalog_uuid=mutation.identity.catalog_uuid,
        track_id=mutation.identity.track_id,
        track_uuid=mutation.identity.track_uuid,
    )


def _target_ids(*targets: AnalysisTarget) -> list[int]:
    return [target.track_id for target in targets]


def test_archival_sonara_fields_do_not_change_similarity_scores(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "energy": 0.5,
            "danceability": 0.4,
            "instrumentalness": 0.1,
            "mood_happy": 0.9,
            "mood_aggressive": 0.2,
            "mood_relaxed": 0.8,
            "mood_sad": 0.1,
            "true_peak_db": -0.2,
            "replaygain_db": -7.0,
        },
    )
    same_archival_values = _add_sonara_track(
        db,
        "same-archival-values.wav",
        {
            "energy": 0.6,
            "danceability": 0.5,
            "instrumentalness": 0.1,
            "mood_happy": 0.9,
            "mood_aggressive": 0.2,
            "mood_relaxed": 0.8,
            "mood_sad": 0.1,
            "true_peak_db": -0.2,
            "replaygain_db": -7.0,
        },
    )
    opposite_archival_values = _add_sonara_track(
        db,
        "opposite-archival-values.wav",
        {
            "energy": 0.6,
            "danceability": 0.5,
            "instrumentalness": 0.9,
            "mood_happy": 0.1,
            "mood_aggressive": 0.9,
            "mood_relaxed": 0.1,
            "mood_sad": 0.9,
            "true_peak_db": -8.0,
            "replaygain_db": 3.0,
        },
    )

    results = SonaraSimilaritySearch(db).search((seed,), mixer_weights={"dynamics": 1.0}, limit=5)
    scores = {result.target.track_id: result.score for result in results}

    assert scores[same_archival_values.track_id] == pytest.approx(
        scores[opposite_archival_values.track_id]
    )


def test_low_tempo_confidence_pulls_a_mismatch_toward_neutral(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(db, "seed.wav", {"bpm": 128.0, "bpm_confidence": 1.0})
    uncertain = _add_sonara_track(
        db, "uncertain.wav", {"bpm": 160.0, "bpm_confidence": 0.04}
    )
    reliable = _add_sonara_track(
        db, "reliable.wav", {"bpm": 160.0, "bpm_confidence": 1.0}
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 1.0,
        },
        limit=5,
    )
    scores = {result.target.track_id: result.score for result in results}

    assert scores[uncertain.track_id] == pytest.approx(0.4)
    assert scores[reliable.track_id] == 0.0


def test_multi_seed_tempo_is_pairwise_instead_of_an_arithmetic_bpm_centroid(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed_half = _add_sonara_track(
        db, "seed-half.wav", {"bpm": 80.0, "bpm_confidence": 1.0}
    )
    seed_full = _add_sonara_track(
        db, "seed-full.wav", {"bpm": 160.0, "bpm_confidence": 1.0}
    )
    compatible = _add_sonara_track(
        db, "compatible.wav", {"bpm": 80.0, "bpm_confidence": 1.0}
    )
    arithmetic_midpoint = _add_sonara_track(
        db, "midpoint.wav", {"bpm": 120.0, "bpm_confidence": 1.0}
    )

    results = SonaraSimilaritySearch(db).search(
        (seed_half, seed_full),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 1.0,
        },
        limit=5,
    )
    scores = {result.target.track_id: result.score for result in results}

    assert scores[compatible.track_id] == 1.0
    assert scores[arithmetic_midpoint.track_id] == 0.0


def test_sonara_search_excludes_tracks_without_features(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "energy": 0.8,
            "danceability": 0.8,
            "valence": 0.2,
            "acousticness": 0.1,
            "camelot_key": "8A",
        },
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {
            "energy": 0.78,
            "danceability": 0.79,
            "valence": 0.22,
            "acousticness": 0.12,
            "camelot_key": "1B",
        },
    )
    missing = _add_track_without_sonara(db, "missing.wav")

    results = SonaraSimilaritySearch(db).search((seed,), mixer_weights={"dynamics": 1.0}, limit=5)

    assert [result.target.track_id for result in results] == _target_ids(close)
    assert missing.track_id not in {result.target.track_id for result in results}


def test_mixer_can_prioritize_rhythm_texture_over_dynamics(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "onset_density": 5.0,
            "zero_crossing_rate": 0.05,
            "danceability": 0.8,
            "energy": 0.78,
            "rms_mean": 0.2,
            "loudness_lufs": -9.0,
        },
    )
    rhythm_close = _add_sonara_track(
        db,
        "rhythm-close.wav",
        {
            "onset_density": 5.1,
            "zero_crossing_rate": 0.052,
            "danceability": 0.78,
            "energy": 0.22,
            "rms_mean": 0.06,
            "loudness_lufs": -19.0,
        },
    )
    dynamics_close = _add_sonara_track(
        db,
        "dynamics-close.wav",
        {
            "onset_density": 1.2,
            "zero_crossing_rate": 0.18,
            "danceability": 0.28,
            "energy": 0.77,
            "rms_mean": 0.19,
            "loudness_lufs": -9.2,
        },
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 3.0,
            "dynamics": 0.2,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    assert [result.target.track_id for result in results] == _target_ids(
        rhythm_close, dynamics_close
    )
    first_breakdown = results[0].score_breakdown
    second_breakdown = results[1].score_breakdown
    assert first_breakdown is not None
    assert second_breakdown is not None
    assert first_breakdown["rhythm"] > second_breakdown["rhythm"]


def test_vector_field_does_not_drown_scalar_mixer_fields(tmp_path: Path) -> None:
    # mfcc_mean expands into many dimensions. Its weight is split across components so it contributes
    # its intended field weight once, letting the scalar timbre fields still influence the ranking.
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "mfcc_mean": [0.0] * 13,
            "spectral_centroid_mean": 1600,
            "spectral_bandwidth_mean": 1500,
            "spectral_rolloff_mean": 3200,
            "spectral_flatness_mean": 0.2,
            "spectral_contrast_mean": [1.0] * 7,
        },
    )
    # Same mfcc as seed, but far on every scalar timbre field.
    scalar_far = _add_sonara_track(
        db,
        "scalar-far.wav",
        {
            "mfcc_mean": [0.0] * 13,
            "spectral_centroid_mean": 5000,
            "spectral_bandwidth_mean": 4200,
            "spectral_rolloff_mean": 9000,
            "spectral_flatness_mean": 0.02,
            "spectral_contrast_mean": [8.0] * 7,
        },
    )
    # Different mfcc, but close on every scalar timbre field.
    scalar_close = _add_sonara_track(
        db,
        "scalar-close.wav",
        {
            "mfcc_mean": [3.0] * 13,
            "spectral_centroid_mean": 1620,
            "spectral_bandwidth_mean": 1520,
            "spectral_rolloff_mean": 3250,
            "spectral_flatness_mean": 0.21,
            "spectral_contrast_mean": [1.1] * 7,
        },
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    # If mfcc dominated (weight * 13), scalar_far would win. With the per-dimension split, the track
    # that matches the scalar timbre fields ranks first.
    assert [result.target.track_id for result in results] == _target_ids(
        scalar_close, scalar_far
    )


def test_modifier_on_group_shared_field_still_biases_direction(
    tmp_path: Path,
) -> None:
    # energy is both a dynamics-group field and the Energy modifier field. The modifier must win the
    # direction instead of being canceled by the group pulling toward the seed.
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "energy": 0.5,
            "rms_mean": 0.2,
            "rms_max": 0.5,
            "loudness_lufs": -10.0,
            "dynamic_range_db": 8.0,
        },
    )
    higher = _add_sonara_track(
        db,
        "higher.wav",
        {
            "energy": 0.9,
            "rms_mean": 0.2,
            "rms_max": 0.5,
            "loudness_lufs": -10.0,
            "dynamic_range_db": 8.0,
        },
    )
    lower = _add_sonara_track(
        db,
        "lower.wav",
        {
            "energy": 0.1,
            "rms_mean": 0.2,
            "rms_max": 0.5,
            "loudness_lufs": -10.0,
            "dynamic_range_db": 8.0,
        },
    )

    higher_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 1.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"energy": 1.0},
        limit=5,
    )
    lower_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 1.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"energy": -1.0},
        limit=5,
    )

    assert higher_results[0].target.track_id == higher.track_id
    assert lower_results[0].target.track_id == lower.track_id
    assert higher_results[0].score == pytest.approx(0.82142857)
    assert lower_results[0].score == pytest.approx(0.82142857)
    assert higher_results[0].score_breakdown == {
        "dynamics": 1.0,
        "modifier_energy": 0.75,
    }
    assert lower_results[0].score_breakdown == {
        "dynamics": 1.0,
        "modifier_energy": 0.75,
    }


def test_aggression_modifier_uses_evidence_confidence(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "mfcc_mean": [0.2, 0.4],
            "aggression": 0.5,
            "aggression_confidence": 1.0,
        },
    )
    high_confidence = _add_sonara_track(
        db,
        "high-confidence.wav",
        {
            "mfcc_mean": [0.21, 0.41],
            "aggression": 0.9,
            "aggression_confidence": 1.0,
        },
    )
    low_confidence = _add_sonara_track(
        db,
        "low-confidence.wav",
        {
            "mfcc_mean": [0.21, 0.41],
            "aggression": 0.9,
            "aggression_confidence": 0.1,
        },
    )
    low_aggression = _add_sonara_track(
        db,
        "low-aggression.wav",
        {
            "mfcc_mean": [0.21, 0.41],
            "aggression": 0.1,
            "aggression_confidence": 1.0,
        },
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"aggression": 1.0},
        limit=5,
    )

    assert [result.target.track_id for result in results] == _target_ids(
        high_confidence,
        low_confidence,
        low_aggression,
    )
    assert results[0].score_breakdown is not None
    assert results[0].score_breakdown["modifier_aggression_confidence"] == 1.0
    assert results[1].score_breakdown is not None
    assert results[1].score_breakdown["modifier_aggression_confidence"] == 0.1
    assert results[2].score_breakdown is not None
    assert (
        results[0].score_breakdown["modifier_aggression"]
        > results[1].score_breakdown["modifier_aggression"]
        > results[2].score_breakdown["modifier_aggression"]
    )


def test_harmonic_knob_is_not_a_hard_exact_key_gate(tmp_path: Path) -> None:
    # The Harmonic knob should reflect harmonic color, so a track with very close chroma/dissonance
    # but a different key should still be able to outrank a same-key track that is harmonically far.
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "chroma_mean": [0.5] * 12,
            "dissonance": 0.1,
            "chord_change_rate": 0.3,
            "key_confidence": 0.8,
            "key": "A minor",
            "predominant_chord": "Am",
        },
    )
    color_close_diff_key = _add_sonara_track(
        db,
        "color-close.wav",
        {
            "chroma_mean": [0.5] * 12,
            "dissonance": 0.11,
            "chord_change_rate": 0.31,
            "key_confidence": 0.79,
            "key": "F# major",
            "predominant_chord": "F#",
        },
    )
    _same_key_color_far = _add_sonara_track(
        db,
        "same-key-far.wav",
        {
            "chroma_mean": [0.02] * 12,
            "dissonance": 0.9,
            "chord_change_rate": 0.95,
            "key_confidence": 0.1,
            "key": "A minor",
            "predominant_chord": "Am",
        },
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 1.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    assert results[0].target.track_id == color_close_diff_key.track_id


def test_sonara_feature_rows_refresh_after_typed_core_write(tmp_path: Path) -> None:
    db = _library(tmp_path)
    target = _add_sonara_track(
        db,
        "track.wav",
        {"energy": 0.2, "danceability": 0.3, "valence": 0.4, "acousticness": 0.5},
    )
    output = db.active_analysis_output("sonara", "core")
    assert output is not None
    first_rows = db.load_sonara_feature_rows(output, targets=(target,))
    result = db.save_sonara_results(
        (
            complete_sonara_write(
                target,
                _core_row(
                    target,
                    {
                        "energy": 0.9,
                        "danceability": 0.8,
                        "valence": 0.7,
                        "acousticness": 0.1,
                    },
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    refreshed_rows = db.load_sonara_feature_rows(output, targets=(target,))

    assert first_rows[0].values["energy_score"] == 0.2
    assert refreshed_rows[0].values["energy_score"] == 0.9


def test_sonara_feature_rows_handle_full_library_and_large_selections(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    targets = tuple(
        _add_sonara_track(
            db,
            f"track-{index}.wav",
            {"energy": 0.1 * index},
        )
        for index in range(6)
    )
    output = db.active_analysis_output("sonara", "core")
    assert output is not None
    selected = (
        *(
            AnalysisTarget(
                catalog_uuid=targets[0].catalog_uuid,
                track_id=track_id,
                track_uuid=f"synthetic-{track_id}",
            )
            for track_id in range(7, 33_001)
        ),
        *targets,
    )
    monkeypatch.setattr(
        db_analysis_module,
        "_selected_targets",
        lambda *_args, **_kwargs: selected,
    )

    full_library_rows = db.load_sonara_feature_rows(output)
    targeted_rows = db.load_sonara_feature_rows(output, targets=targets)

    assert [row.target for row in full_library_rows] == list(targets)
    assert [row.target for row in targeted_rows] == list(targets)


def test_sonara_search_reports_context_tracks_without_features(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_track_without_sonara(db, "seed.wav")

    with pytest.raises(ValueError, match="missing active SONARA Core features"):
        SonaraSimilaritySearch(db).search((seed,), mixer_weights={"dynamics": 1.0}, limit=5)


def _float_or_none(value: object) -> float | None:
    if not isinstance(value, (str, bytes, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

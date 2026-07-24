from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    SonaraWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import SonaraRowV7
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    prepare_sonara_release,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    SonaraContractSet,
    sonara_runtime_contracts,
)
from dj_track_similarity.sonara_similarity import SonaraSimilaritySearch
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"
_CONTRACTS_BY_DATABASE: dict[Path, SonaraContractSet] = {}


class _FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "5" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness"
    __sonara_vocalness_model_build_id__ = "sha256:" + "6" * 64


def _contracts() -> SonaraContractSet:
    return sonara_runtime_contracts(_FakeSonara)


def _library(tmp_path: Path) -> LibraryDatabase:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    backup_dir = tmp_path / "sonara-backups"
    backup_dir.mkdir()
    prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=_FakeSonara,
    )
    contracts = _contracts()
    _CONTRACTS_BY_DATABASE[database.path] = contracts
    return database


def _feature_value(features: dict[str, object], name: str) -> object:
    return features.get(name)


def _text_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _vector_blob(value: object, *, dim: int) -> bytes:
    raw = value if isinstance(value, (list, tuple)) else ()
    values = [float(item) for item in raw[:dim]]
    values.extend([0.0] * (dim - len(values)))
    return np.asarray(values, dtype="<f4").tobytes()


def _core_row(
    target: AnalysisTarget,
    contracts: SonaraContractSet,
    features: dict[str, object],
) -> SonaraRowV7:
    values = {field.name: None for field in fields(SonaraRowV7)}
    energy = _float_or_none(_feature_value(features, "energy"))
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "contract_hash": contracts.core.contract_hash,
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
            "energy_level": None,
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
            "vocal_probability": _float_or_none(_feature_value(features, "vocalness")),
            "mood_happy_score": _float_or_none(_feature_value(features, "mood_happy")),
            "mood_aggressive_score": _float_or_none(
                _feature_value(features, "mood_aggressive")
            ),
            "mood_relaxed_score": _float_or_none(
                _feature_value(features, "mood_relaxed")
            ),
            "mood_sad_score": _float_or_none(_feature_value(features, "mood_sad")),
            "mfcc_mean_blob": _vector_blob(
                _feature_value(features, "mfcc_mean"), dim=13
            ),
            "chroma_mean_blob": _vector_blob(
                _feature_value(features, "chroma_mean"), dim=12
            ),
            "spectral_contrast_mean_blob": _vector_blob(
                _feature_value(features, "spectral_contrast_mean"), dim=7
            ),
            "analyzed_at": _NOW,
        }
    )
    return SonaraRowV7(**values)


def _add_sonara_track(
    database: LibraryDatabase,
    name: str,
    features: dict[str, object],
) -> AnalysisTarget:
    contracts = _CONTRACTS_BY_DATABASE[database.path]
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
        content_generation=mutation.identity.content_generation,
    )
    result = database.save_sonara_results(
        (
            SonaraWrite(
                target=target,
                core_contract=contracts.core,
                core=_core_row(target, contracts, features),
            ),
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
        content_generation=mutation.identity.content_generation,
    )


def _target_ids(*targets: AnalysisTarget) -> list[int]:
    return [target.track_id for target in targets]


def test_vibe_mode_ranks_energy_danceability_valence_and_acousticness(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "energy": 0.82,
            "danceability": 0.78,
            "valence": 0.36,
            "acousticness": 0.1,
            "loudness_lufs": -8.5,
            "dynamic_range_db": 7.0,
        },
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {
            "energy": 0.8,
            "danceability": 0.76,
            "valence": 0.34,
            "acousticness": 0.12,
            "loudness_lufs": -8.7,
            "dynamic_range_db": 7.1,
        },
    )
    far = _add_sonara_track(
        db,
        "far.wav",
        {
            "energy": 0.18,
            "danceability": 0.28,
            "valence": 0.82,
            "acousticness": 0.7,
            "loudness_lufs": -18.0,
            "dynamic_range_db": 13.5,
        },
    )

    results = SonaraSimilaritySearch(db).search((seed,), mode="vibe", limit=5)

    assert [result.target.track_id for result in results] == _target_ids(close, far)
    assert results[0].score > results[1].score


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

    results = SonaraSimilaritySearch(db).search((seed,), mode="vibe", limit=5)
    scores = {result.target.track_id: result.score for result in results}

    assert scores[same_archival_values.track_id] == pytest.approx(
        scores[opposite_archival_values.track_id]
    )


def test_sound_mode_ranks_mfcc_and_spectral_summaries(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "mfcc_mean": [1.0, 0.4, -0.2],
            "spectral_centroid_mean": 2100,
            "spectral_bandwidth_mean": 1600,
            "spectral_flatness_mean": 0.18,
            "zero_crossing_rate": 0.08,
            "rms_mean": 0.21,
        },
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {
            "mfcc_mean": [0.95, 0.45, -0.18],
            "spectral_centroid_mean": 2200,
            "spectral_bandwidth_mean": 1580,
            "spectral_flatness_mean": 0.19,
            "zero_crossing_rate": 0.082,
            "rms_mean": 0.22,
        },
    )
    far = _add_sonara_track(
        db,
        "far.wav",
        {
            "mfcc_mean": [-1.0, -0.4, 0.8],
            "spectral_centroid_mean": 5200,
            "spectral_bandwidth_mean": 4200,
            "spectral_flatness_mean": 0.55,
            "zero_crossing_rate": 0.22,
            "rms_mean": 0.06,
        },
    )

    results = SonaraSimilaritySearch(db).search((seed,), mode="sound", limit=5)

    assert [result.target.track_id for result in results] == _target_ids(close, far)
    assert results[0].score > results[1].score


def test_dj_transition_mode_ranks_bpm_onset_and_raw_tonal_data(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "bpm": 128,
            "onset_density": 5.8,
            "energy": 0.74,
            "danceability": 0.81,
            "key": "A minor",
            "key_confidence": 0.9,
            "predominant_chord": "Am",
            "chord_change_rate": 0.28,
            "dissonance": 0.15,
        },
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {
            "bpm": 129,
            "onset_density": 5.6,
            "energy": 0.72,
            "danceability": 0.79,
            "key": "A minor",
            "key_confidence": 0.82,
            "predominant_chord": "Am",
            "chord_change_rate": 0.3,
            "dissonance": 0.16,
        },
    )
    wrong_key = _add_sonara_track(
        db,
        "wrong-key.wav",
        {
            "bpm": 128,
            "onset_density": 5.8,
            "energy": 0.74,
            "danceability": 0.8,
            "key": "F# major",
            "key_confidence": 0.95,
            "predominant_chord": "F#",
            "chord_change_rate": 0.28,
            "dissonance": 0.15,
        },
    )

    results = SonaraSimilaritySearch(db).search((seed,), mode="dj_transition", limit=5)

    assert [result.target.track_id for result in results] == _target_ids(
        close, wrong_key
    )
    assert results[0].score > results[1].score


def test_custom_tempo_uses_confidence_as_reliability_not_similarity_dimension(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(db, "seed.wav", {"bpm": 128.0, "bpm_confidence": 1.0})
    low_confidence = _add_sonara_track(
        db, "low.wav", {"bpm": 136.0, "bpm_confidence": 0.1}
    )
    high_confidence = _add_sonara_track(
        db, "high.wav", {"bpm": 136.0, "bpm_confidence": 0.9}
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
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

    # At a measured tempo match of exactly 0.5, reliability interpolation stays neutral. Merely
    # having a similar or higher confidence therefore cannot create a similarity bonus.
    assert scores[low_confidence.track_id] == pytest.approx(0.5)
    assert scores[high_confidence.track_id] == pytest.approx(0.5)


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
        mode="custom",
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
        mode="custom",
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


def test_sonara_search_ignores_camelot_key_and_excludes_missing_features(
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

    results = SonaraSimilaritySearch(db).search((seed,), mode="balanced", limit=5)

    assert [result.target.track_id for result in results] == _target_ids(close)
    assert missing.track_id not in {result.target.track_id for result in results}


def test_sonara_search_uses_only_seed_tracks_as_context(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"energy": 1.0, "danceability": 0.2, "valence": 0.2, "acousticness": 0.0},
    )
    bridge = _add_sonara_track(
        db,
        "bridge.wav",
        {"energy": 0.6, "danceability": 0.6, "valence": 0.22, "acousticness": 0.02},
    )
    seed_clone = _add_sonara_track(
        db,
        "seed-clone.wav",
        {"energy": 1.0, "danceability": 0.2, "valence": 0.2, "acousticness": 0.0},
    )

    results = SonaraSimilaritySearch(db).search((seed,), mode="vibe", limit=5)

    assert [result.target.track_id for result in results[:2]] == _target_ids(
        seed_clone, bridge
    )


def test_custom_mixer_can_prioritize_rhythm_texture_over_dynamics(
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
        mode="custom",
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


def test_custom_modifiers_bias_direction_without_hardcoded_mood(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {
            "mfcc_mean": [0.2, 0.4],
            "spectral_centroid_mean": 1600,
            "valence": 0.4,
            "acousticness": 0.6,
            "energy": 0.5,
        },
    )
    brighter = _add_sonara_track(
        db,
        "brighter.wav",
        {
            "mfcc_mean": [0.22, 0.41],
            "spectral_centroid_mean": 1620,
            "valence": 0.68,
            "acousticness": 0.58,
            "energy": 0.5,
        },
    )
    darker = _add_sonara_track(
        db,
        "darker.wav",
        {
            "mfcc_mean": [0.21, 0.39],
            "spectral_centroid_mean": 1580,
            "valence": 0.18,
            "acousticness": 0.62,
            "energy": 0.5,
        },
    )

    brighter_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"valence": 1.0},
        limit=5,
    )
    darker_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"valence": -1.0},
        limit=5,
    )

    assert [result.target.track_id for result in brighter_results] == _target_ids(
        brighter, darker
    )
    assert [result.target.track_id for result in darker_results] == _target_ids(
        darker, brighter
    )
    assert brighter_results[0].score_breakdown
    assert "modifier_valence" in brighter_results[0].score_breakdown


def test_custom_vector_field_does_not_drown_scalar_mixer_fields(tmp_path: Path) -> None:
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
        mode="custom",
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


def test_custom_modifier_on_group_shared_field_still_biases_direction(
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
        mode="custom",
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
        mode="custom",
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


def test_custom_dynamics_group_uses_sonara_20_loudness_fields(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"loudness_range_lu": 5.0, "loudness_momentary_max_db": -8.0},
    )
    loudness_close = _add_sonara_track(
        db,
        "loudness-close.wav",
        {"loudness_range_lu": 5.2, "loudness_momentary_max_db": -8.2},
    )
    loudness_far = _add_sonara_track(
        db,
        "loudness-far.wav",
        {"loudness_range_lu": 14.0, "loudness_momentary_max_db": -3.5},
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 1.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    assert [result.target.track_id for result in results] == _target_ids(
        loudness_close, loudness_far
    )
    first_breakdown = results[0].score_breakdown
    second_breakdown = results[1].score_breakdown
    assert first_breakdown is not None
    assert second_breakdown is not None
    assert first_breakdown["dynamics"] > second_breakdown["dynamics"]


def test_custom_harmonic_group_uses_sonara_20_camelot_key(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(db, "seed.wav", {"key_camelot": "8A", "dissonance": 0.2})
    camelot_close = _add_sonara_track(
        db, "camelot-close.wav", {"key_camelot": "8A", "dissonance": 0.22}
    )
    camelot_far = _add_sonara_track(
        db, "camelot-far.wav", {"key_camelot": "3B", "dissonance": 0.22}
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 1.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    assert [result.target.track_id for result in results] == _target_ids(
        camelot_close, camelot_far
    )
    assert results[0].score > results[1].score


def test_custom_vocalness_modifier_biases_vocal_or_instrumental_tracks(
    tmp_path: Path,
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db, "seed.wav", {"mfcc_mean": [0.2, 0.4], "vocalness": 0.5}
    )
    vocal = _add_sonara_track(
        db, "vocal.wav", {"mfcc_mean": [0.21, 0.41], "vocalness": 0.9}
    )
    instrumental = _add_sonara_track(
        db, "instrumental.wav", {"mfcc_mean": [0.21, 0.41], "vocalness": 0.1}
    )

    vocal_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"vocalness": 1.0},
        limit=5,
    )
    instrumental_results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 1.0,
            "rhythm": 0.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        modifiers={"vocalness": -1.0},
        limit=5,
    )

    assert [result.target.track_id for result in vocal_results] == _target_ids(
        vocal, instrumental
    )
    assert [result.target.track_id for result in instrumental_results] == _target_ids(
        instrumental, vocal
    )
    assert vocal_results[0].score_breakdown
    assert "modifier_vocalness" in vocal_results[0].score_breakdown


def test_custom_harmonic_knob_is_not_a_hard_exact_key_gate(tmp_path: Path) -> None:
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
        mode="custom",
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


def test_custom_mixer_reads_typed_sonara_core_values(tmp_path: Path) -> None:
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
            "key": "A minor",
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
            "key": "C minor",
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
            "key": "F major",
        },
    )

    results = SonaraSimilaritySearch(db).search(
        (seed,),
        mode="custom",
        mixer_weights={
            "timbre": 0.0,
            "rhythm": 3.0,
            "dynamics": 0.0,
            "harmonic": 0.0,
            "tempo": 0.0,
        },
        limit=5,
    )

    assert [result.target.track_id for result in results] == _target_ids(
        rhythm_close, dynamics_close
    )


def test_sonara_search_reads_active_rows_without_summary_scan(
    monkeypatch, tmp_path: Path
) -> None:
    db = _library(tmp_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"energy": 0.8, "danceability": 0.8, "valence": 0.2, "acousticness": 0.1},
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {"energy": 0.78, "danceability": 0.79, "valence": 0.22, "acousticness": 0.12},
    )
    far = _add_sonara_track(
        db,
        "far.wav",
        {"energy": 0.2, "danceability": 0.3, "valence": 0.8, "acousticness": 0.7},
    )

    searcher = SonaraSimilaritySearch(db)
    cold_results = searcher.search((seed,), mode="vibe", limit=5)

    def fail_full_track_scan(*_args, **_kwargs):
        raise AssertionError(
            "SONARA search must read active feature rows without a summary scan"
        )

    monkeypatch.setattr(db, "list_track_summaries", fail_full_track_scan)
    warm_results = searcher.search((seed,), mode="vibe", limit=5)

    assert [result.target.track_id for result in cold_results] == _target_ids(
        close, far
    )
    assert [result.target.track_id for result in warm_results] == _target_ids(
        close, far
    )
    assert [result.score for result in warm_results] == [
        result.score for result in cold_results
    ]


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
    contracts = _CONTRACTS_BY_DATABASE[db.path]
    result = db.save_sonara_results(
        (
            SonaraWrite(
                target=target,
                core_contract=contracts.core,
                core=_core_row(
                    target,
                    contracts,
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


def test_sonara_search_reports_context_tracks_without_features(tmp_path: Path) -> None:
    db = _library(tmp_path)
    seed = _add_track_without_sonara(db, "seed.wav")

    with pytest.raises(ValueError, match="missing active SONARA Core features"):
        SonaraSimilaritySearch(db).search((seed,), mode="vibe", limit=5)


def _float_or_none(value: object) -> float | None:
    if not isinstance(value, (str, bytes, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

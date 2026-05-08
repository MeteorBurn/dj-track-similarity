from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_similarity import SonaraSimilaritySearch


def _add_sonara_track(db: LibraryDatabase, name: str, features: dict[str, object]) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    db.save_sonara_features(
        track_id,
        features,
        bpm=_float_or_none(features.get("bpm")),
        musical_key=str(features["key"]) if features.get("key") else None,
        energy=_float_or_none(features.get("energy")),
        duration=_float_or_none(features.get("duration_sec")),
    )
    return track_id


def test_vibe_mode_ranks_energy_danceability_valence_and_acousticness(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"energy": 0.82, "danceability": 0.78, "valence": 0.36, "acousticness": 0.1, "loudness_lufs": -8.5, "dynamic_range_db": 7.0},
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {"energy": 0.8, "danceability": 0.76, "valence": 0.34, "acousticness": 0.12, "loudness_lufs": -8.7, "dynamic_range_db": 7.1},
    )
    far = _add_sonara_track(
        db,
        "far.wav",
        {"energy": 0.18, "danceability": 0.28, "valence": 0.82, "acousticness": 0.7, "loudness_lufs": -18.0, "dynamic_range_db": 13.5},
    )

    results = SonaraSimilaritySearch(db).search([seed], mode="vibe", limit=5)

    assert [result.track.id for result in results] == [close, far]
    assert results[0].score > results[1].score


def test_sound_mode_ranks_mfcc_and_spectral_summaries(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"mfcc_mean": [1.0, 0.4, -0.2], "spectral_centroid_mean": 2100, "spectral_bandwidth_mean": 1600, "spectral_flatness_mean": 0.18, "zero_crossing_rate": 0.08, "rms_mean": 0.21},
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {"mfcc_mean": [0.95, 0.45, -0.18], "spectral_centroid_mean": 2200, "spectral_bandwidth_mean": 1580, "spectral_flatness_mean": 0.19, "zero_crossing_rate": 0.082, "rms_mean": 0.22},
    )
    far = _add_sonara_track(
        db,
        "far.wav",
        {"mfcc_mean": [-1.0, -0.4, 0.8], "spectral_centroid_mean": 5200, "spectral_bandwidth_mean": 4200, "spectral_flatness_mean": 0.55, "zero_crossing_rate": 0.22, "rms_mean": 0.06},
    )

    results = SonaraSimilaritySearch(db).search([seed], mode="sound", limit=5)

    assert [result.track.id for result in results] == [close, far]
    assert results[0].score > results[1].score


def test_dj_transition_mode_ranks_bpm_onset_and_raw_tonal_data(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"bpm": 128, "onset_density": 5.8, "energy": 0.74, "danceability": 0.81, "key": "A minor", "key_confidence": 0.9, "predominant_chord": "Am", "chord_change_rate": 0.28, "dissonance": 0.15},
    )
    close = _add_sonara_track(
        db,
        "close.wav",
        {"bpm": 129, "onset_density": 5.6, "energy": 0.72, "danceability": 0.79, "key": "A minor", "key_confidence": 0.82, "predominant_chord": "Am", "chord_change_rate": 0.3, "dissonance": 0.16},
    )
    wrong_key = _add_sonara_track(
        db,
        "wrong-key.wav",
        {"bpm": 128, "onset_density": 5.8, "energy": 0.74, "danceability": 0.8, "key": "F# major", "key_confidence": 0.95, "predominant_chord": "F#", "chord_change_rate": 0.28, "dissonance": 0.15},
    )

    results = SonaraSimilaritySearch(db).search([seed], mode="dj_transition", limit=5)

    assert [result.track.id for result in results] == [close, wrong_key]
    assert results[0].score > results[1].score


def test_sonara_search_ignores_camelot_key_and_excludes_missing_features(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_sonara_track(db, "seed.wav", {"energy": 0.8, "danceability": 0.8, "valence": 0.2, "acousticness": 0.1, "camelot_key": "8A"})
    close = _add_sonara_track(db, "close.wav", {"energy": 0.78, "danceability": 0.79, "valence": 0.22, "acousticness": 0.12, "camelot_key": "1B"})
    missing = db.upsert_track(path=Path("C:/music/missing.wav"), size=100, mtime=1, metadata={"title": "missing"})

    results = SonaraSimilaritySearch(db).search([seed], mode="balanced", limit=5)

    assert [result.track.id for result in results] == [close]
    assert missing not in {result.track.id for result in results}


def test_seed_and_lookback_build_shared_centroid(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_sonara_track(db, "seed.wav", {"energy": 1.0, "danceability": 0.2, "valence": 0.2, "acousticness": 0.0})
    lookback = _add_sonara_track(db, "lookback.wav", {"energy": 0.2, "danceability": 1.0, "valence": 0.2, "acousticness": 0.0})
    bridge = _add_sonara_track(db, "bridge.wav", {"energy": 0.6, "danceability": 0.6, "valence": 0.22, "acousticness": 0.02})
    seed_clone = _add_sonara_track(db, "seed-clone.wav", {"energy": 1.0, "danceability": 0.2, "valence": 0.2, "acousticness": 0.0})

    results = SonaraSimilaritySearch(db).search([seed], lookback_track_ids=[lookback], mode="vibe", limit=5)

    assert [result.track.id for result in results[:2]] == [bridge, seed_clone]


def test_sonara_search_reports_context_tracks_without_features(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = db.upsert_track(path=Path("C:/music/seed.wav"), size=100, mtime=1, metadata={"title": "seed"})

    with pytest.raises(ValueError, match="missing SONARA features"):
        SonaraSimilaritySearch(db).search([seed], mode="vibe", limit=5)


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

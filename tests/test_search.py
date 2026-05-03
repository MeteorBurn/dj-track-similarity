from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search import SearchFilters, SimilaritySearch


def _add_track(db: LibraryDatabase, name: str, embedding: list[float], bpm: float | None = None, key: str | None = None, energy: float | None = None) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(
        path=path,
        size=100,
        mtime=1,
        metadata={"title": name, "artist": "Test"},
        bpm=bpm,
        musical_key=key,
        energy=energy,
    )
    db.save_embedding(track_id, np.array(embedding, dtype=np.float32), "fake-model", 3)
    return track_id


def test_search_uses_multi_seed_centroid_and_excludes_seed_tracks(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_a = _add_track(db, "seed-a.wav", [1.0, 0.0, 0.0])
    seed_b = _add_track(db, "seed-b.wav", [0.0, 1.0, 0.0])
    bridge = _add_track(db, "bridge.wav", [0.7, 0.7, 0.0])
    far = _add_track(db, "far.wav", [0.0, 0.0, 1.0])

    results = SimilaritySearch(db).search([seed_a, seed_b], limit=5)

    assert [result.track.id for result in results] == [bridge, far]
    assert results[0].score > results[1].score


def test_search_applies_bpm_half_double_key_energy_and_threshold_filters(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_track(db, "seed.wav", [1.0, 0.0, 0.0], bpm=128, key="8A", energy=0.5)
    compatible_half_time = _add_track(db, "half.wav", [0.99, 0.01, 0.0], bpm=64, key="8B", energy=0.52)
    incompatible_key = _add_track(db, "bad-key.wav", [0.98, 0.02, 0.0], bpm=128, key="2A", energy=0.51)
    too_low = _add_track(db, "low.wav", [0.1, 0.9, 0.0], bpm=128, key="8A", energy=0.5)

    results = SimilaritySearch(db).search(
        [seed],
        filters=SearchFilters(
            bpm_tolerance=2,
            key_compatibility="compatible",
            energy_min=0.45,
            energy_max=0.6,
            min_similarity=0.7,
        ),
        limit=10,
    )

    assert [result.track.id for result in results] == [compatible_half_time]
    assert incompatible_key not in {result.track.id for result in results}
    assert too_low not in {result.track.id for result in results}


def test_search_epsilon_keeps_only_candidates_near_the_best_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_track(db, "seed.wav", [1.0, 0.0, 0.0])
    near = _add_track(db, "near.wav", [0.99, 0.01, 0.0])
    far = _add_track(db, "far.wav", [0.7, 0.3, 0.0])

    results = SimilaritySearch(db).search([seed], filters=SearchFilters(epsilon=0.02), limit=10)

    assert [result.track.id for result in results] == [near]
    assert far not in {result.track.id for result in results}


def test_search_uses_lookback_tracks_as_additional_context(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_track(db, "seed.wav", [1.0, 0.0, 0.0])
    lookback = _add_track(db, "lookback.wav", [0.0, 1.0, 0.0])
    bridge = _add_track(db, "bridge.wav", [0.7, 0.7, 0.0])
    seed_clone = _add_track(db, "seed-clone.wav", [1.0, 0.0, 0.0])

    results = SimilaritySearch(db).search([seed], lookback_track_ids=[lookback], limit=10)

    assert [result.track.id for result in results[:2]] == [bridge, seed_clone]


def test_search_noise_changes_near_tie_ranking_but_keeps_similarity_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_track(db, "seed.wav", [1.0, 0.0, 0.0])
    first = _add_track(db, "first.wav", [0.99, 0.01, 0.0])
    second = _add_track(db, "second.wav", [0.98, 0.02, 0.0])

    plain = SimilaritySearch(db).search([seed], limit=2)
    noisy = SimilaritySearch(db).search([seed], filters=SearchFilters(noise=0.2), limit=2)

    assert [result.track.id for result in plain] == [first, second]
    assert [result.track.id for result in noisy] == [second, first]
    assert noisy[0].score < plain[0].score

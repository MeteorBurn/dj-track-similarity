from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.database import LibraryDatabase
import dj_track_similarity.set_builder as set_builder_module
from dj_track_similarity.set_builder import SetBuilderConfig, SmartSetBuilder


def test_manual_set_builder_includes_seed_and_uses_broad_sonara_when_embeddings_tie(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        metadata={"title": "Seed", "bpm": 128, "key": "8A"},
        features=_features(energy=0.80, danceability=0.78, onset_density=0.52, spectral_centroid=1400),
        vectors={"mert": [1, 0, 0], "maest": [1, 0, 0], "clap": [1, 0, 0]},
    )
    close_id = _complete_track(
        db,
        tmp_path,
        "close.wav",
        metadata={"title": "Close", "bpm": 129, "key": "9A"},
        features=_features(energy=0.79, danceability=0.77, onset_density=0.51, spectral_centroid=1410),
        vectors={"mert": [1, 0, 0], "maest": [1, 0, 0], "clap": [1, 0, 0]},
    )
    far_id = _complete_track(
        db,
        tmp_path,
        "far.wav",
        metadata={"title": "Far", "bpm": 132, "key": "12B"},
        features=_features(energy=0.20, danceability=0.30, onset_density=0.10, spectral_centroid=2500),
        vectors={"mert": [1, 0, 0], "maest": [1, 0, 0], "clap": [1, 0, 0]},
    )

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=3))

    assert [item["track"].id for item in result["items"]] == [seed_id, close_id, far_id]
    assert result["items"][0]["reason"] == "seed_anchor"
    assert result["items"][1]["score_breakdown"]["sonara_broad"] > result["items"][2]["score_breakdown"]["sonara_broad"]
    assert result["items"][1]["sonara_groups"]["dynamics"] > result["items"][2]["sonara_groups"]["dynamics"]


def test_set_builder_expands_sonara_array_summaries_and_ignores_maest_genres(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        features=_features(mfcc_mean=0.20, mfcc_std=0.04, chroma_mean=0.70, chroma_std=0.10),
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    close_id = _complete_track(
        db,
        tmp_path,
        "close-summary.wav",
        features=_features(mfcc_mean=0.21, mfcc_std=0.04, chroma_mean=0.69, chroma_std=0.11),
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    genre_match_far_id = _complete_track(
        db,
        tmp_path,
        "genre-match-far.wav",
        features=_features(mfcc_mean=0.82, mfcc_std=0.30, chroma_mean=0.10, chroma_std=0.35),
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    db.save_genres(seed_id, [{"label": "Electronic---Dub Techno", "score": 0.99}], model_name="maest-test")
    db.save_genres(genre_match_far_id, [{"label": "Electronic---Dub Techno", "score": 0.99}], model_name="maest-test")

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=3))

    assert [item["track"].id for item in result["items"]] == [seed_id, close_id, genre_match_far_id]
    assert result["items"][1]["sonara_groups"]["timbre"] > result["items"][2]["sonara_groups"]["timbre"]


def test_set_builder_classifier_targets_avoid_curves_and_missing_scores_are_soft(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(db, tmp_path, "seed.wav", vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]})
    target_id = _complete_track(db, tmp_path, "target.wav", vectors={"mert": [0.99, 0.01], "maest": [0.99, 0.01], "clap": [0.99, 0.01]})
    missing_id = _complete_track(db, tmp_path, "missing-classifier.wav", vectors={"mert": [0.99, 0.01], "maest": [0.99, 0.01], "clap": [0.99, 0.01]})
    avoided_id = _complete_track(db, tmp_path, "avoided.wav", vectors={"mert": [0.99, 0.01], "maest": [0.99, 0.01], "clap": [0.99, 0.01]})
    _score(db, target_id, "break_energy", 0.95)
    _score(db, target_id, "voice_presence", 0.10)
    _score(db, avoided_id, "break_energy", 0.40)
    _score(db, avoided_id, "voice_presence", 0.90)

    result = SmartSetBuilder(db).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[seed_id],
            limit=4,
            classifier_targets={"break_energy": 0.8},
            classifier_avoid={"voice_presence": 0.6},
            classifier_curves={"break_energy": {"start": 0.4, "end": 0.9}},
            random_seed=2,
        )
    )

    ordered_ids = [item["track"].id for item in result["items"]]
    assert ordered_ids[0] == seed_id
    assert target_id in ordered_ids
    assert missing_id in ordered_ids
    assert ordered_ids.index(target_id) < ordered_ids.index(avoided_id)
    target_item = next(item for item in result["items"] if item["track"].id == target_id)
    assert target_item["score_breakdown"]["classifier_target"] > 0
    assert target_item["classifier_scores"]["break_energy"] == 0.95
    missing_item = next(item for item in result["items"] if item["track"].id == missing_id)
    assert missing_item["score_breakdown"]["classifier_confidence"] < target_item["score_breakdown"]["classifier_confidence"]


def test_auto_mode_uses_random_seed_and_excludes_feature_incomplete_tracks(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    ids = [
        _complete_track(
            db,
            tmp_path,
            f"complete-{index}.wav",
            metadata={"artist": f"Artist {index}", "title": f"Complete {index}"},
            features=_features(energy=0.35 + index / 100, onset_density=0.25 + index / 100),
            vectors={"mert": [1, index / 20], "maest": [1, index / 20], "clap": [1, index / 20]},
        )
        for index in range(1, 13)
    ]
    incomplete_id = _track(db, tmp_path, "missing-clap.wav", metadata={"title": "Missing CLAP"})
    db.save_sonara_features(incomplete_id, _features(), bpm=128, musical_key="8A", energy=0.5)
    db.save_embedding(incomplete_id, np.asarray([1.0, 0.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(incomplete_id, np.asarray([1.0, 0.0], dtype=np.float32), "maest-test", embedding_key="maest")

    builder = SmartSetBuilder(db)
    first = builder.generate(SetBuilderConfig(seed_mode="auto", auto_seed_count=3, limit=5, random_seed=11))
    second = builder.generate(SetBuilderConfig(seed_mode="auto", auto_seed_count=3, limit=5, random_seed=11))
    different_seed = builder.generate(SetBuilderConfig(seed_mode="auto", auto_seed_count=3, limit=5, random_seed=12))

    assert [item["track"].id for item in first["items"]] == [item["track"].id for item in second["items"]]
    assert first["seed_track_ids"] != different_seed["seed_track_ids"]
    assert incomplete_id not in [item["track"].id for item in first["items"]]
    assert set(first["seed_track_ids"]).issubset(ids)
    assert len(first["seed_track_ids"]) == 3


def test_auto_mode_computes_global_sonara_centrality_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    ids = [
        _complete_track(
            db,
            tmp_path,
            f"complete-{index}.wav",
            features=_features(energy=0.35 + index / 100, onset_density=0.25 + index / 100),
            vectors={"mert": [1, index / 20], "maest": [1, index / 20], "clap": [1, index / 20]},
        )
        for index in range(8)
    ]
    original_sonara_centroid = set_builder_module._sonara_centroid
    global_centroid_calls = 0

    def counting_sonara_centroid(seeds, ranges):
        nonlocal global_centroid_calls
        if len(seeds) == len(ids):
            global_centroid_calls += 1
        return original_sonara_centroid(seeds, ranges)

    monkeypatch.setattr(set_builder_module, "_sonara_centroid", counting_sonara_centroid)

    SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="auto", auto_seed_count=3, limit=3))

    assert global_centroid_calls == 1


def test_ordering_uses_bounded_candidate_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(db, tmp_path, "seed.wav", vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]})
    for index in range(80):
        _complete_track(
            db,
            tmp_path,
            f"candidate-{index:02d}.wav",
            features=_features(energy=0.25 + index / 200, onset_density=0.20 + index / 300),
            vectors={"mert": [1, index / 100], "maest": [1, index / 100], "clap": [1, index / 100]},
        )
    monkeypatch.setattr(set_builder_module, "SEQUENCE_POOL_MIN", 12, raising=False)
    monkeypatch.setattr(set_builder_module, "SEQUENCE_POOL_FACTOR", 2, raising=False)
    monkeypatch.setattr(set_builder_module, "SEQUENCE_POOL_MAX", 12, raising=False)
    original_sequence_score = SmartSetBuilder._sequence_score
    sequence_score_calls = 0

    def counting_sequence_score(self, *args, **kwargs):
        nonlocal sequence_score_calls
        sequence_score_calls += 1
        return original_sequence_score(self, *args, **kwargs)

    monkeypatch.setattr(SmartSetBuilder, "_sequence_score", counting_sequence_score)

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=6))

    assert len(result["items"]) == 6
    assert sequence_score_calls <= 84


def test_ordering_diversity_does_not_recompute_full_sonara_similarity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(db, tmp_path, "seed.wav", vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]})
    candidate_count = 10
    for index in range(candidate_count):
        _complete_track(
            db,
            tmp_path,
            f"candidate-{index:02d}.wav",
            features=_features(energy=0.3 + index / 100, onset_density=0.2 + index / 100),
            vectors={"mert": [1, index / 50], "maest": [1, index / 50], "clap": [1, index / 50]},
        )
    original_sonara_similarity = set_builder_module._sonara_similarity
    sonara_similarity_calls = 0

    def counting_sonara_similarity(*args, **kwargs):
        nonlocal sonara_similarity_calls
        sonara_similarity_calls += 1
        return original_sonara_similarity(*args, **kwargs)

    monkeypatch.setattr(set_builder_module, "_sonara_similarity", counting_sonara_similarity)

    SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=5))

    assert sonara_similarity_calls == candidate_count


def test_set_builder_ordering_uses_random_seed_for_candidate_sequence(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        metadata={"artist": "Seed Artist", "title": "Seed"},
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    for index in range(12):
        _complete_track(
            db,
            tmp_path,
            f"candidate-{index:02d}.wav",
            metadata={"artist": f"Candidate Artist {index}", "title": f"Candidate {index}"},
            features=_features(energy=0.50, onset_density=0.40, spectral_centroid=1500.0),
            vectors={"mert": [1, 0.01], "maest": [1, 0.01], "clap": [1, 0.01]},
        )

    first = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=8, random_seed=21))
    second = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=8, random_seed=22))

    first_ids = [item["track"].id for item in first["items"]]
    second_ids = [item["track"].id for item in second["items"]]
    assert first_ids[0] == second_ids[0] == seed_id
    assert first_ids != second_ids


def test_set_builder_uses_each_known_artist_once_in_sequence(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        metadata={"artist": "Seed Artist", "title": "Seed"},
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    for index in range(3):
        _complete_track(
            db,
            tmp_path,
            f"repeat-{index}.wav",
            metadata={"artist": "Repeat Artist", "title": f"Repeat {index}"},
            features=_features(energy=0.50 + index / 100),
            vectors={"mert": [1, index / 100], "maest": [1, index / 100], "clap": [1, index / 100]},
        )
    for index in range(2):
        _complete_track(
            db,
            tmp_path,
            f"other-{index}.wav",
            metadata={"artist": f"Other Artist {index}", "title": f"Other {index}"},
            features=_features(energy=0.45 - index / 100, spectral_centroid=1700 + index * 10),
            vectors={"mert": [0.96, 0.04 + index / 100], "maest": [0.96, 0.04 + index / 100], "clap": [0.96, 0.04 + index / 100]},
        )

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=4, random_seed=2))
    artists = [item["track"].artist for item in result["items"]]

    assert len(artists) == 4
    assert len(artists) == len(set(artists))


def test_manual_same_artist_seeds_are_rejected(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_seed_id = _complete_track(
        db,
        tmp_path,
        "seed-a.wav",
        metadata={"artist": "Repeat Artist", "title": "Seed A"},
        features=_features(energy=0.60),
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    second_seed_id = _complete_track(
        db,
        tmp_path,
        "seed-b.wav",
        metadata={"artist": "Repeat Artist", "title": "Seed B"},
        features=_features(energy=0.61),
        vectors={"mert": [0.99, 0.01], "maest": [0.99, 0.01], "clap": [0.99, 0.01]},
    )
    for index in range(3):
        _complete_track(
            db,
            tmp_path,
            f"separator-{index}.wav",
            metadata={"artist": f"Other Artist {index}", "title": f"Separator {index}"},
            features=_features(energy=0.55 - index / 100),
            vectors={"mert": [0.97, 0.03 + index / 100], "maest": [0.97, 0.03 + index / 100], "clap": [0.97, 0.03 + index / 100]},
        )

    with pytest.raises(ValueError):
        SmartSetBuilder(db).generate(
            SetBuilderConfig(seed_mode="manual", seed_track_ids=[first_seed_id, second_seed_id], limit=4, random_seed=7)
        )


def test_set_builder_skips_repeat_artist_candidates(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        metadata={"artist": "Repeat Artist", "title": "Seed"},
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    for index in range(6):
        _complete_track(
            db,
            tmp_path,
            f"repeat-{index}.wav",
            metadata={"artist": "Repeat Artist", "title": f"Repeat {index}"},
            features=_features(energy=0.50 + index / 100),
            vectors={"mert": [1, index / 100], "maest": [1, index / 100], "clap": [1, index / 100]},
        )
    for index in range(4):
        _complete_track(
            db,
            tmp_path,
            f"other-{index}.wav",
            metadata={"artist": f"Other Artist {index}", "title": f"Other {index}"},
            features=_features(energy=0.40 - index / 100, spectral_centroid=1800 + index * 10),
            vectors={"mert": [0.94, 0.06 + index / 100], "maest": [0.94, 0.06 + index / 100], "clap": [0.94, 0.06 + index / 100]},
        )

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=5, random_seed=2))
    artists = [item["track"].artist for item in result["items"]]

    assert len(artists) == 5
    assert artists.count("Repeat Artist") == 1
    assert len(artists) == len(set(artists))


def test_auto_mode_anchors_use_each_known_artist_once(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for index in range(7):
        _complete_track(
            db,
            tmp_path,
            f"dominant-{index}.wav",
            metadata={"artist": "Dominant Artist", "title": f"Dominant {index}"},
            features=_features(energy=0.50 + index / 100, onset_density=0.40 + index / 100),
            vectors={"mert": [1, index / 4], "maest": [1, index / 4], "clap": [1, index / 4]},
        )
    for index in range(5):
        _complete_track(
            db,
            tmp_path,
            f"other-{index}.wav",
            metadata={"artist": f"Other Artist {index}", "title": f"Other {index}"},
            features=_features(energy=0.45 - index / 100, onset_density=0.35 - index / 100),
            vectors={"mert": [0.9, 0.2 + index / 6], "maest": [0.9, 0.2 + index / 6], "clap": [0.9, 0.2 + index / 6]},
        )

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="auto", auto_seed_count=5, limit=8))
    seed_artists = [item["track"].artist for item in result["items"] if item["reason"] == "seed_anchor"]

    assert len(seed_artists) == 5
    assert seed_artists.count("Dominant Artist") <= 1
    assert len(seed_artists) == len(set(seed_artists))


def test_set_builder_prefilters_before_loading_embedding_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(db, tmp_path, "seed.wav", vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]})
    for index in range(30):
        _complete_track(
            db,
            tmp_path,
            f"candidate-{index:02d}.wav",
            features=_features(energy=0.3 + index / 100, onset_density=0.2 + index / 100),
            vectors={"mert": [1, index / 50], "maest": [1, index / 50], "clap": [1, index / 50]},
        )
    monkeypatch.setattr(set_builder_module, "PREFILTER_POOL_MIN", 8, raising=False)
    monkeypatch.setattr(set_builder_module, "PREFILTER_POOL_FACTOR", 2, raising=False)
    monkeypatch.setattr(set_builder_module, "PREFILTER_POOL_MAX", 8, raising=False)

    def fail_full_embedding_matrix(_embedding_key: str):
        raise AssertionError("set builder must not load the full embedding matrix")

    monkeypatch.setattr(db, "load_embedding_matrix", fail_full_embedding_matrix)

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=5))

    assert len(result["items"]) == 5


def test_set_builder_loads_light_candidates_without_full_sonara_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(db, tmp_path, "seed.wav", vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]})
    for index in range(12):
        _complete_track(
            db,
            tmp_path,
            f"candidate-{index:02d}.wav",
            features=_features(energy=0.25 + index / 100, onset_density=0.18 + index / 100),
            vectors={"mert": [1, index / 40], "maest": [1, index / 40], "clap": [1, index / 40]},
        )

    def fail_full_sonara_rows():
        raise AssertionError("set builder must not load full SONARA feature rows")

    monkeypatch.setattr(db, "load_sonara_feature_rows", fail_full_sonara_rows)

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], limit=5))

    assert len(result["items"]) == 5


def test_balanced_mode_prefers_soft_bpm_key_transition_when_scores_are_close(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _complete_track(
        db,
        tmp_path,
        "seed.wav",
        metadata={"title": "Seed", "bpm": 128, "key": "8A"},
        features=_features(energy=0.6),
        vectors={"mert": [1, 0], "maest": [1, 0], "clap": [1, 0]},
    )
    compatible_id = _complete_track(
        db,
        tmp_path,
        "compatible.wav",
        metadata={"title": "Compatible", "bpm": 129, "key": "9A"},
        features=_features(energy=0.62),
        vectors={"mert": [0.98, 0.02], "maest": [0.98, 0.02], "clap": [0.98, 0.02]},
    )
    clash_id = _complete_track(
        db,
        tmp_path,
        "clash.wav",
        metadata={"title": "Clash", "bpm": 145, "key": "3B"},
        features=_features(energy=0.62),
        vectors={"mert": [0.99, 0.01], "maest": [0.99, 0.01], "clap": [0.99, 0.01]},
    )

    result = SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[seed_id], mode="balanced_set", limit=3))

    assert [item["track"].id for item in result["items"]] == [seed_id, compatible_id, clash_id]
    assert result["items"][1]["transition"]["key_relation"] == "adjacent"
    assert result["items"][1]["score_breakdown"]["transition"] > result["items"][2]["score_breakdown"]["transition"]


def test_manual_mode_rejects_invalid_seed_counts(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    with pytest.raises(ValueError, match="Manual set builder requires 1-5 seed tracks"):
        SmartSetBuilder(db).generate(SetBuilderConfig(seed_mode="manual", seed_track_ids=[]))


def _track(db: LibraryDatabase, tmp_path: Path, filename: str, *, metadata: dict[str, object] | None = None) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata=metadata or {"title": filename})


def _complete_track(
    db: LibraryDatabase,
    tmp_path: Path,
    filename: str,
    *,
    metadata: dict[str, object] | None = None,
    features: dict[str, object] | None = None,
    vectors: dict[str, list[float]] | None = None,
) -> int:
    track_id = _track(db, tmp_path, filename, metadata=metadata)
    feature_payload = features or _features()
    db.save_sonara_features(
        track_id,
        feature_payload,
        bpm=_feature_number(feature_payload, "bpm"),
        musical_key=str(feature_payload.get("key", {}).get("value")) if isinstance(feature_payload.get("key"), dict) else None,
        energy=_feature_number(feature_payload, "energy"),
        duration=_feature_number(feature_payload, "duration_sec"),
        model_name="sonara-test",
    )
    for key, values in (vectors or {"mert": [1.0, 0.0], "maest": [1.0, 0.0], "clap": [1.0, 0.0]}).items():
        db.save_embedding(track_id, np.asarray(values, dtype=np.float32), f"{key}-test", embedding_key=key)
    return track_id


def _features(
    *,
    bpm: float = 128.0,
    energy: float = 0.5,
    danceability: float = 0.5,
    valence: float = 0.4,
    acousticness: float = 0.2,
    onset_density: float = 0.4,
    spectral_centroid: float = 1500.0,
    mfcc_mean: float = 0.3,
    mfcc_std: float = 0.05,
    chroma_mean: float = 0.4,
    chroma_std: float = 0.08,
) -> dict[str, object]:
    scalar_values = {
        "bpm": bpm,
        "n_beats": 300,
        "onset_density": onset_density,
        "rms_mean": 0.2 + energy / 10,
        "rms_max": 0.6 + energy / 10,
        "loudness_lufs": -14 + energy,
        "dynamic_range_db": 8 + energy,
        "energy": energy,
        "danceability": danceability,
        "valence": valence,
        "acousticness": acousticness,
        "key_confidence": 0.8,
        "chord_change_rate": 0.2,
        "dissonance": 0.3,
        "spectral_centroid_mean": spectral_centroid,
        "spectral_bandwidth_mean": 2200,
        "spectral_rolloff_mean": 3800,
        "spectral_flatness_mean": 0.12,
        "spectral_contrast_mean": 0.4,
        "zero_crossing_rate": 0.08,
        "duration_sec": 360,
    }
    payload: dict[str, object] = {key: {"type": "float", "value": value} for key, value in scalar_values.items()}
    payload["key"] = {"type": "str", "value": "8A"}
    payload["predominant_chord"] = {"type": "str", "value": "Am"}
    payload["beats"] = {"type": "ndarray", "value": None, "summary": {"min": 0.0, "max": 360.0, "mean": 180.0, "std": 102.0}}
    payload["onset_frames"] = {"type": "ndarray", "value": None, "summary": {"min": 1.0, "max": 1200.0, "mean": 600.0, "std": 250.0}}
    payload["mfcc_mean"] = {"type": "ndarray", "value": None, "summary": {"min": mfcc_mean - 0.1, "max": mfcc_mean + 0.1, "mean": mfcc_mean, "std": mfcc_std}}
    payload["chroma_mean"] = {"type": "ndarray", "value": None, "summary": {"min": chroma_mean - 0.1, "max": chroma_mean + 0.1, "mean": chroma_mean, "std": chroma_std}}
    return payload


def _feature_number(features: dict[str, object], key: str) -> float | None:
    raw = features.get(key)
    if isinstance(raw, dict):
        value = raw.get("value")
        return float(value) if isinstance(value, (int, float)) else None
    return float(raw) if isinstance(raw, (int, float)) else None


def _score(db: LibraryDatabase, track_id: int, classifier: str, score: float) -> None:
    db.save_classifier_score(
        track_id,
        classifier=classifier,
        score=score,
        label="high" if score >= 0.8 else "low",
        confidence=score,
        probabilities={"positive": score, "negative": 1.0 - score},
        feature_set="combined",
        model_id="model.joblib",
    )

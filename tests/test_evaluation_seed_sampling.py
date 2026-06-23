from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.seed_sampling import SEED_SAMPLE_COLUMNS, export_seed_sample, write_seed_sample_csv


def test_seed_sample_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    db = _seed_sample_library(tmp_path)

    first = export_seed_sample(db, count=5, random_seed=42)
    second = export_seed_sample(db, count=5, random_seed=42)

    assert first.eligible_count == 8
    assert first.selected_count == 5
    assert first.bucket_mode == "stratified"
    assert _track_ids(first.rows) == _track_ids(second.rows)


def test_seed_sample_complete_analysis_filter_can_be_relaxed(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete_id = _track(db, tmp_path, "complete", artist="Complete Artist", bpm=120.0, energy=0.5)
    partial_id = _track(db, tmp_path, "partial", artist="Partial Artist", bpm=124.0, energy=0.6)
    _save_complete_analysis(db, complete_id, vector=[1.0, 0.0])
    db.save_sonara_features(partial_id, {"bpm": 124.0, "energy": 0.6}, bpm=124.0, energy=0.6)

    complete_result = export_seed_sample(db, count=5, random_seed=7, require_complete_analysis=True)
    partial_result = export_seed_sample(db, count=5, random_seed=7, require_complete_analysis=False)

    assert complete_result.eligible_count == 1
    assert _track_ids(complete_result.rows) == [complete_id]
    assert partial_result.eligible_count == 2
    assert set(_track_ids(partial_result.rows)) == {complete_id, partial_id}


def test_seed_sample_prefers_distinct_known_artists(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_artist_ids = [
        _track(db, tmp_path, "same_a", artist="Same Artist", bpm=120.0, energy=0.5),
        _track(db, tmp_path, "same_b", artist="same  artist", bpm=121.0, energy=0.5),
    ]
    unique_ids = [
        _track(db, tmp_path, "unique_a", artist="Unique A", bpm=122.0, energy=0.5),
        _track(db, tmp_path, "unique_b", artist="Unique B", bpm=123.0, energy=0.5),
    ]
    for offset, track_id in enumerate([*first_artist_ids, *unique_ids]):
        _save_complete_analysis(db, track_id, vector=[1.0, float(offset + 1)])

    result = export_seed_sample(db, count=3, random_seed=4)

    artist_keys = [row.known_artist_key for row in result.rows]
    assert len(set(artist_keys)) == 3
    assert set(_track_ids(result.rows)).issubset({*first_artist_ids, *unique_ids})


def test_write_seed_sample_csv_has_expected_columns(tmp_path: Path) -> None:
    db = _seed_sample_library(tmp_path)
    output_path = tmp_path / "seed_sample.csv"
    result = export_seed_sample(db, count=3, random_seed=11)

    write_seed_sample_csv(output_path, result.rows)

    with output_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == list(SEED_SAMPLE_COLUMNS)
    assert len(rows) == 3
    assert all(row["track_id"] for row in rows)
    assert all(row["bucket"] for row in rows)


def _seed_sample_library(tmp_path: Path) -> LibraryDatabase:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for index, (bpm, energy) in enumerate(
        (
            (96.0, 0.2),
            (104.0, 0.4),
            (112.0, 0.7),
            (124.0, 0.3),
            (128.0, 0.8),
            (136.0, 0.5),
            (142.0, 0.9),
            (150.0, 0.6),
        ),
        start=1,
    ):
        track_id = _track(db, tmp_path, f"track_{index}", artist=f"Artist {index}", bpm=bpm, energy=energy)
        _save_complete_analysis(db, track_id, vector=[1.0, float(index)])
    return db


def _track(db: LibraryDatabase, tmp_path: Path, stem: str, *, artist: str, bpm: float, energy: float) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": artist, "title": stem.replace("_", " ").title(), "album": "Seed Tests"},
        bpm=bpm,
        musical_key="1A",
        energy=energy,
    )


def _save_complete_analysis(db: LibraryDatabase, track_id: int, *, vector: list[float]) -> None:
    normalized = np.asarray(vector, dtype=np.float32)
    db.save_embedding(track_id, normalized, "test-mert", embedding_key="mert")
    db.save_embedding(track_id, normalized, "test-clap", embedding_key="clap")
    db.save_embedding(track_id, normalized, "test-maest", embedding_key="maest")
    db.save_sonara_features(track_id, {"bpm": 120.0, "energy": 0.5})


def _track_ids(rows: tuple[object, ...]) -> list[int]:
    return [int(getattr(row, "track_id")) for row in rows]

from __future__ import annotations

import csv
from dataclasses import fields
from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    SonaraWrite,
    current_embedding_spec,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow
from dj_track_similarity.evaluation.seed_sampling import (
    SEED_SAMPLE_COLUMNS,
    export_seed_sample,
    write_seed_sample_csv,
)
from dj_track_similarity.track_models import (
    FileTags,
    ScannedFile,
    TrackIdentity,
)


_NOW = "2026-07-24T10:00:00.000000Z"


def test_seed_sample_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    db = _seed_sample_library(tmp_path)

    first = export_seed_sample(db, count=5, random_seed=42)
    second = export_seed_sample(db, count=5, random_seed=42)

    assert first.eligible_count == 8
    assert first.selected_count == 5
    assert first.bucket_mode == "stratified"
    assert _track_ids(first.rows) == _track_ids(second.rows)


def test_seed_sample_complete_analysis_filter_can_be_relaxed(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete = _track(
        db,
        tmp_path,
        "complete",
        artist="Complete Artist",
        bpm=120.0,
    )
    partial = _track(
        db,
        tmp_path,
        "partial",
        artist="Partial Artist",
        bpm=124.0,
    )
    _save_complete_analysis(db, complete, bpm=120.0, energy=0.5, axis=0)
    _save_sonara_core(db, partial, bpm=124.0, energy=0.6)

    complete_result = export_seed_sample(
        db,
        count=5,
        random_seed=7,
        require_complete_analysis=True,
    )
    partial_result = export_seed_sample(
        db,
        count=5,
        random_seed=7,
        require_complete_analysis=False,
    )

    assert complete_result.eligible_count == 1
    assert _track_ids(complete_result.rows) == [complete.track_id]
    assert partial_result.eligible_count == 2
    assert set(_track_ids(partial_result.rows)) == {
        complete.track_id,
        partial.track_id,
    }


def test_seed_sample_keeps_saved_analysis_after_track_scan_update(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    original = _track(
        db,
        tmp_path,
        "stale",
        artist="Stale",
        bpm=123.0,
        musical_key="D minor",
    )
    _save_complete_analysis(db, original, bpm=90.0, energy=0.9, axis=0)

    current = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "stale.wav"),
            file_size_bytes=11,
            file_modified_ns=2,
        ),
        tags=FileTags(
            artist="Stale",
            title="Stale",
            tag_bpm=123.0,
            tag_key="D minor",
        ),
        scanned_at=_NOW,
    ).identity
    _save_ml_embeddings(db, current, axis=1)

    complete = export_seed_sample(
        db,
        count=5,
        require_complete_analysis=True,
    )
    relaxed = export_seed_sample(
        db,
        count=5,
        require_complete_analysis=False,
    )

    assert complete.eligible_count == 1
    assert relaxed.eligible_count == 1
    row = complete.rows[0]
    assert row.sonara_core is True
    assert row.bpm == 90.0
    assert row.energy == 0.9


def test_seed_sample_does_not_reuse_old_columns_after_empty_reanalysis(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(
        db,
        tmp_path,
        "reanalyzed",
        artist="Current",
        bpm=123.0,
        musical_key="D minor",
    )
    _save_complete_analysis(db, identity, bpm=90.0, energy=0.9, axis=0)
    _save_sonara_core(db, identity, bpm=None, energy=None, musical_key=None)

    result = export_seed_sample(
        db,
        count=1,
        require_complete_analysis=True,
    )

    assert result.eligible_count == 1
    row = result.rows[0]
    assert row.sonara_core is True
    assert row.bpm == 123.0
    assert row.musical_key == "D minor"
    assert row.energy is None


def test_seed_sample_prefers_distinct_known_artists(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_artist = [
        _track(db, tmp_path, "same_a", artist="Same Artist", bpm=120.0),
        _track(db, tmp_path, "same_b", artist="same  artist", bpm=121.0),
    ]
    unique = [
        _track(db, tmp_path, "unique_a", artist="Unique A", bpm=122.0),
        _track(db, tmp_path, "unique_b", artist="Unique B", bpm=123.0),
    ]
    for offset, identity in enumerate([*first_artist, *unique]):
        _save_complete_analysis(
            db,
            identity,
            bpm=120.0 + offset,
            energy=0.5,
            axis=offset,
        )

    result = export_seed_sample(db, count=3, random_seed=4)

    artist_keys = [row.known_artist_key for row in result.rows]
    assert len(set(artist_keys)) == 3
    expected_ids = {item.track_id for item in (*first_artist, *unique)}
    assert set(_track_ids(result.rows)).issubset(expected_ids)


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
        identity = _track(
            db,
            tmp_path,
            f"track_{index}",
            artist=f"Artist {index}",
            bpm=bpm,
        )
        _save_complete_analysis(
            db,
            identity,
            bpm=bpm,
            energy=energy,
            axis=index,
        )
    return db


def _track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    *,
    artist: str,
    bpm: float,
    musical_key: str = "1A",
) -> TrackIdentity:
    mutation = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / f"{stem}.wav"),
            file_size_bytes=10,
            file_modified_ns=1,
        ),
        tags=FileTags(
            artist=artist,
            title=stem.replace("_", " ").title(),
            album="Seed Tests",
            tag_bpm=bpm,
            tag_key=musical_key,
        ),
        scanned_at=_NOW,
    )
    return mutation.identity


def _target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
    )


def _save_complete_analysis(
    db: LibraryDatabase,
    identity: TrackIdentity,
    *,
    bpm: float,
    energy: float,
    axis: int,
) -> None:
    _save_ml_embeddings(db, identity, axis=axis)
    _save_sonara_core(db, identity, bpm=bpm, energy=energy)


def _save_ml_embeddings(
    db: LibraryDatabase,
    identity: TrackIdentity,
    *,
    axis: int,
) -> None:
    target = _target(identity)
    mert, muq, clap, maest_analysis, maest_embedding = _ml_outputs()
    db.register_analysis_outputs(
        (mert, muq, clap, maest_analysis, maest_embedding)
    )
    embedding_results = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="mert",
                    vector=_unit_vector(
                        current_embedding_spec("mert").dimension, axis
                    ),
                    analyzed_at=_NOW,
                ),
            ),
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="muq",
                    vector=_unit_vector(
                        current_embedding_spec("muq").dimension, axis
                    ),
                    analyzed_at=_NOW,
                ),
            ),
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="clap",
                    vector=_unit_vector(
                        current_embedding_spec("clap").dimension, axis
                    ),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert all(result.ok for result in embedding_results)
    maest_result = db.save_maest_results(
        (
            MaestWrite(
                target=target,
                genres=(MaestGenreScore(label="Techno", score=0.9),),
                syncopated_rhythm=None,
                analyzed_at=_NOW,
                embedding=EmbeddingOutput(
                    family="maest",
                    vector=_unit_vector(
                        current_embedding_spec("maest").dimension,
                        axis,
                    ),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert maest_result[0].ok


def _save_sonara_core(
    db: LibraryDatabase,
    identity: TrackIdentity,
    *,
    bpm: float | None,
    energy: float | None,
    musical_key: str | None = "1A",
) -> None:
    target = _target(identity)
    db.register_analysis_outputs((AnalysisOutput("sonara", "core"),))
    values = {field.name: None for field in fields(SonaraRow)}
    values.update(
        {
            "track_id": target.track_id,
            "detected_bpm": bpm,
            "detected_key_camelot": musical_key,
            "energy_score": energy,
            "mfcc_mean_blob": bytes(13 * 4),
            "chroma_mean_blob": bytes(12 * 4),
            "spectral_contrast_mean_blob": bytes(7 * 4),
            "analyzed_at": _NOW,
        }
    )
    result = db.save_sonara_results(
        (
            SonaraWrite(
                target=target,
                core=SonaraRow(**values),
            ),
        )
    )
    assert result[0].ok


def _ml_outputs() -> tuple[
    AnalysisOutput,
    AnalysisOutput,
    AnalysisOutput,
    AnalysisOutput,
    AnalysisOutput,
]:
    mert = current_embedding_analysis_output("mert")
    muq = current_embedding_analysis_output("muq")
    clap = current_embedding_analysis_output("clap")
    maest_analysis = AnalysisOutput("maest", "analysis")
    maest_embedding = current_embedding_analysis_output("maest")
    return mert, muq, clap, maest_analysis, maest_embedding


def _unit_vector(dim: int, axis: int) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    vector[axis % dim] = 1.0
    return vector


def _track_ids(rows: tuple[object, ...]) -> list[int]:
    return [int(getattr(row, "track_id")) for row in rows]

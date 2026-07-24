from __future__ import annotations

import os
import wave
from dataclasses import replace
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import TALB, TBPM, TCON, TIT2, TKEY, TPE1

from dj_track_similarity import tags
from dj_track_similarity.analysis_model_runners import MaestModelRunner
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import scan_audio_file
from dj_track_similarity.tags import (
    GenreTagJobManager,
    apply_genre_tags_to_tracks,
)


_ANALYZED_AT = "2026-07-24T00:00:00.000000Z"


def _make_tagged_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(path)
    audio.add_tags()
    audio.tags.add(TPE1(encoding=3, text=["Existing Artist"]))
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    audio.tags.add(TALB(encoding=3, text=["Existing Album"]))
    audio.tags.add(TBPM(encoding=3, text=["128"]))
    audio.tags.add(TKEY(encoding=3, text=["8A"]))
    audio.tags.add(TCON(encoding=3, text=["Old Genre"]))
    audio.save()


def _library_with_maest_candidate(
    tmp_path: Path,
) -> tuple[LibraryDatabase, Path, int, int]:
    path = tmp_path / "track.wav"
    _make_tagged_wave(path)
    database = LibraryDatabase(tmp_path / "library.sqlite")
    mutation = scan_audio_file(database, path)
    identity = mutation.identity
    output = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    ).active_outputs[0]
    database.register_analysis_outputs((output,))
    result = database.save_maest_results(
        (
            MaestWrite(
                target=AnalysisTarget(
                    catalog_uuid=database.catalog_uuid,
                    track_id=identity.track_id,
                    track_uuid=identity.track_uuid,
                    content_generation=identity.content_generation,
                ),
                analysis_contract=output.contract,
                genres=(
                    MaestGenreScore(
                        label="Electronic---Tech House",
                        score=0.91,
                    ),
                    MaestGenreScore(label="Minimal", score=0.72),
                ),
                syncopated_rhythm=True,
                analyzed_at=_ANALYZED_AT,
            ),
        )
    )[0]
    assert result.ok
    return (
        database,
        path,
        identity.track_id,
        identity.content_generation,
    )


def test_genre_tag_job_uses_v7_candidate_and_preserves_generation_and_tags(
    tmp_path: Path,
) -> None:
    database, path, track_id, generation = _library_with_maest_candidate(
        tmp_path
    )

    status = GenreTagJobManager(database).run_sync()

    assert status.state == "completed"
    assert (status.total, status.applied, status.skipped, status.failed) == (
        1,
        1,
        0,
        0,
    )
    saved = MutagenFile(path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert saved.tags["TPE1"].text == ["Existing Artist"]
    assert saved.tags["TIT2"].text == ["Existing Title"]
    assert saved.tags["TALB"].text == ["Existing Album"]
    assert saved.tags["TBPM"].text == ["128"]
    assert saved.tags["TKEY"].text == ["8A"]

    current = database.get_track_file_state(path)
    assert current is not None
    assert current.track_id == track_id
    assert current.content_generation == generation
    assert current.file_size_bytes == path.stat().st_size
    assert current.file_modified_ns == path.stat().st_mtime_ns
    detail = database.get_track_detail(track_id)
    assert detail.file_tags is not None
    assert detail.file_tags.title == "Existing Title"
    assert detail.file_tags.artist == "Existing Artist"
    assert detail.file_tags.album == "Existing Album"
    assert detail.file_tags.tag_bpm == 128.0
    assert detail.file_tags.tag_key == "8A"
    assert detail.file_tags.genres == ("Tech House; Minimal",)
    assert detail.maest is not None
    candidates = database.list_genre_tag_candidates()
    assert len(candidates) == 1
    assert candidates[0].catalog_uuid == database.catalog_uuid


def test_genre_tag_apply_rejects_stale_files_before_source_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database, path, _track_id, generation = _library_with_maest_candidate(
        tmp_path
    )
    candidates = database.list_genre_tag_candidates()
    original = path.stat()
    os.utime(
        path,
        ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000),
    )
    writes: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        tags,
        "_write_genre_tag",
        lambda audio_path, genre: writes.append((audio_path, genre)),
    )

    results = apply_genre_tags_to_tracks(database, candidates)

    assert writes == []
    assert [result.status for result in results] == ["failed"]
    assert "Source file changed" in (results[0].error or "")
    current = database.get_track_file_state(path)
    assert current is not None
    assert current.content_generation == generation
    assert current.file_modified_ns == candidates[0].expected_file_modified_ns


def test_genre_tag_apply_rejects_stale_content_generation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database, path, _track_id, generation = _library_with_maest_candidate(
        tmp_path
    )
    candidates = database.list_genre_tag_candidates()
    original = path.stat()
    os.utime(
        path,
        ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000),
    )
    rescanned = scan_audio_file(database, path)
    assert rescanned.identity.content_generation == generation + 1
    writes: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        tags,
        "_write_genre_tag",
        lambda audio_path, genre: writes.append((audio_path, genre)),
    )

    results = apply_genre_tags_to_tracks(database, candidates)

    assert writes == []
    assert [result.status for result in results] == ["failed"]
    assert "content generation changed" in (results[0].error or "")


def test_genre_tag_apply_requires_readback_before_recording_self_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database, path, _track_id, generation = _library_with_maest_candidate(
        tmp_path
    )
    candidates = database.list_genre_tag_candidates()
    monkeypatch.setattr(tags, "_write_genre_tag", lambda _path, _genre: None)

    results = apply_genre_tags_to_tracks(database, candidates)

    assert [result.status for result in results] == ["failed"]
    assert "readback mismatch" in (results[0].error or "")
    saved = MutagenFile(path)
    assert saved.tags["TCON"].text == ["Old Genre"]
    current = database.get_track_file_state(path)
    assert current is not None
    assert current.content_generation == generation


def test_genre_tag_apply_rejects_cross_catalog_candidate_before_source_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database, _path, _track_id, _generation = (
        _library_with_maest_candidate(tmp_path)
    )
    candidate = replace(
        database.list_genre_tag_candidates()[0],
        catalog_uuid="wrong-catalog",
    )
    writes: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        tags,
        "_write_genre_tag",
        lambda audio_path, genre: writes.append((audio_path, genre)),
    )

    results = apply_genre_tags_to_tracks(database, (candidate,))

    assert writes == []
    assert [result.status for result in results] == ["failed"]
    assert "different catalog" in (results[0].error or "")

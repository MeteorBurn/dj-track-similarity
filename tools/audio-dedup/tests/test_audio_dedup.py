from __future__ import annotations

import base64
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import sys
import types
from pathlib import Path
import uuid
import zipfile

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.audio_dedup_jobs import AudioDedupJobManager
from dj_track_similarity.db.search_fts import upsert_track_search_fts
from dj_track_similarity.db.tracks import resolved_file_path
from dj_track_similarity.rhythm_lab_collections import sonara_content_key

TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup import cli as cli_module  # noqa: E402

from audio_dedup import config as config_module  # noqa: E402

from audio_dedup import core as core_module  # noqa: E402

from audio_dedup import deletion as deletion_module  # noqa: E402

from audio_dedup import fingerprints as fingerprints_module  # noqa: E402

from audio_dedup import keeper as keeper_module  # noqa: E402

from audio_dedup import models as models_module  # noqa: E402

from audio_dedup import report_files as report_files_module  # noqa: E402

from audio_dedup import report_payload as report_payload_module  # noqa: E402

from audio_dedup import scoring as scoring_module  # noqa: E402

from audio_dedup import track_loading as track_loading_module  # noqa: E402


DUPLICATE_FINGERPRINT = base64.b64encode(bytes(range(4)) * 64).decode("ascii")


def _exact_fingerprint_match(left: str, right: str) -> float:
    """Stand in for the native SONARA comparison with an exact-bytes rule.

    The real matcher decodes audio fingerprints through the sonara extension;
    the tool only ever asks it for a number, so the fixtures pair copies by
    storing the same fingerprint value.
    """
    return 1.0 if left == right else 0.0


@pytest.fixture(autouse=True)
def _isolate_external_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    monkeypatch.setattr(core_module, "decoder_available", lambda: False)
    monkeypatch.setattr(fingerprints_module, "_native_fingerprint_match", _exact_fingerprint_match)


def _create_library_db(path: Path) -> None:
    LibraryDatabase(path)


def _insert_track(
    db_path: Path,
    *,
    track_id: int,
    path: str,
    size: int = 10_000_000,
    mtime: float = 100.0,
    artist: str = "Artist",
    title: str = "Title",
    album: str | None = "Album",
    bpm: float | None = 128.0,
    musical_key: str | None = "8A",
    duration: float = 300.0,
    fingerprint: str | None = None,
) -> None:
    # Paths, sizes and times here are report data, not files on disk, and the
    # scan write path stores only a file it can stat. So the fixture writes
    # the rows a scan would have written.
    database = LibraryDatabase(db_path)
    track_uuid = str(uuid.uuid4())
    scanned_at = "2026-07-24T00:00:00.000000Z"
    with closing(database.connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO tracks(
                track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
                audio_duration_seconds, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id, track_uuid, resolved_file_path(path), size,
                int(mtime * 1_000_000_000), duration, scanned_at, scanned_at, scanned_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO tags(
                track_id, title, artist, album, tag_key, tag_bpm, genres_json, tags_read_at
            ) VALUES (?, ?, ?, ?, ?, ?, '["Test"]', ?)
            """,
            (track_id, title, artist, album, musical_key, bpm, scanned_at),
        )
        upsert_track_search_fts(connection, track_id)
        if fingerprint is not None:
            connection.execute(
                """
                INSERT INTO sonara_fingerprints(
                    track_id, track_uuid, fingerprint_version,
                    fingerprint_base64, analyzed_at
                ) VALUES(?, ?, 1, ?, '2026-07-24T00:00:00.000000Z')
                """,
                (track_id, track_uuid, fingerprint),
            )


def _record(
    track_id: int,
    path: str,
    *,
    size: int = 10_000_000,
    mtime: float = 100.0,
) -> models_module.TrackRecord:
    return models_module.TrackRecord(
        track_id=track_id,
        path=path,
        size=size,
        mtime=mtime,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
    )


def test_path_contains_filters_the_scanned_tracks(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/Keep/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/Other/two.flac")
    _insert_track(db_path, track_id=3, path="N:/Volumes/Elsewhere/three.flac")

    tracks = track_loading_module.load_tracks(db_path, path_contains=["keep"])

    assert [track.track_id for track in tracks] == [1]


def test_report_only_main_does_not_delete_files_or_mutate_database(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    first_path = audio_dir / "first.flac"
    second_path = audio_dir / "second.mp3"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path=str(first_path), size=20_000_000, mtime=100, fingerprint=DUPLICATE_FINGERPRINT)
    _insert_track(db_path, track_id=2, path=str(second_path), size=8_000_000, mtime=200, fingerprint=DUPLICATE_FINGERPRINT)

    exit_code = cli_module.main(["--db", str(db_path), "--out-dir", str(out_dir)])

    assert exit_code == 0
    assert first_path.exists()
    assert second_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2
    finally:
        connection.close()
    db_path.rename(tmp_path / "library-renamed.sqlite")
    report_paths = sorted(out_dir.glob("audio_dedup_report_*/audio_dedup_report_*.json"))
    assert len(report_paths) == 1
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert payload["search_mode"] == config_module.MODE_FINGERPRINT_SCAN
    assert payload["groups"][0]["suggested_keeper"]["track_id"] == 1
    assert [
        candidate["track_id"] for candidate in payload["groups"][0]["candidate_deletes"]
    ] == [2]


def test_keeper_selection_ignores_lossless_packing_and_file_size() -> None:
    tagged = replace(
        _record(1, "M:/Volumes/Abstracted/tagged.flac", size=10_000_000),
        metadata={"bit_rate_bps": 700_000, "bit_depth": 16, "sample_rate_hz": 44_100},
    )
    larger = replace(
        tagged, track_id=2, path="M:/Volumes/Abstracted/larger.flac",
        size=20_000_000, mtime=200.0, artist=None, title=None, album=None,
        bpm=None, musical_key=None,
    )
    higher_bitrate = replace(
        larger, size=tagged.size,
        metadata={**tagged.metadata, "bit_rate_bps": 1_200_000},
    )
    higher_resolution = replace(
        tagged, track_id=3, path="M:/Volumes/Abstracted/resolution.flac",
        metadata={**tagged.metadata, "bit_depth": 24},
    )
    mp3 = replace(
        larger, track_id=4, path="M:/Volumes/Abstracted/copy.mp3",
        metadata={"bit_rate_bps": 320_000, "bit_depth": 24, "sample_rate_hz": 96_000},
    )
    cases = (
        ([tagged, higher_bitrate], tagged),
        ([tagged, larger], tagged),
        ([higher_resolution, higher_bitrate], higher_resolution),
        ([tagged, mp3], tagged),
    )
    # Packing and padding cannot buy a recommendation; input order cannot
    # change it either. Lossless resolution and compression class still count.
    actual = [
        keeper_module.choose_keeper(order).track_id
        for tracks, _ in cases
        for order in (tracks, list(reversed(tracks)))
    ]
    assert actual == [expected.track_id for _, expected in cases for _ in range(2)]


def test_cancellation_during_processing_does_not_publish_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    _create_library_db(db_path)
    for track_id, name in enumerate(("first.flac", "last.flac"), start=1):
        path = tmp_path / name
        path.write_bytes(b"decoder fixture")
        _insert_track(
            db_path, track_id=track_id, path=str(path),
            fingerprint=DUPLICATE_FINGERPRINT,
        )
    manager = AudioDedupJobManager(LibraryDatabase(db_path), out_dir=out_dir)
    analyzed: list[str] = []

    def analyze(path: str, **_kwargs: object) -> core_module.SpectralResult:
        analyzed.append(Path(path).name)
        if len(analyzed) == 2:
            job = manager.latest()
            assert job is not None
            manager.cancel(job.job_id)
        return core_module.skipped_result("stubbed decode")

    monkeypatch.setattr(core_module, "decoder_available", lambda: True)
    monkeypatch.setattr(core_module, "analyze_file", analyze)

    status = manager.run_sync(detect_fake_bitrate=True)

    assert analyzed == ["first.flac", "last.flac"]
    assert status.state == "cancelled"
    assert status.cancel_requested is True
    assert status.report_id is None
    assert not out_dir.exists()

    pending: list[Future] = []
    pool_closed: list[bool] = []

    class CancelWhileWaiting(Future):
        def result(self, timeout=None):
            assert timeout is not None
            job = manager.latest()
            assert job is not None
            # A second wait means the cancellation hook was not checked after
            # the worker timeout. Fail immediately rather than hanging the run.
            assert not job.cancel_requested
            manager.cancel(job.job_id)
            raise FutureTimeoutError

    class PendingPool:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            pool_closed.append(True)

        def submit(self, *_args: object) -> Future:
            future = CancelWhileWaiting()
            pending.append(future)
            return future

    monkeypatch.setattr(fingerprints_module, "ProcessPoolExecutor", PendingPool)
    monkeypatch.setattr(fingerprints_module.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(fingerprints_module, "_PARALLEL_MIN_CANDIDATES", 1)
    monkeypatch.setattr(fingerprints_module, "_PARALLEL_MIN_TRACKS", 1)
    monkeypatch.setattr(fingerprints_module, "_PARALLEL_MIN_FINGERPRINT_CHARS", 1)
    analyzed.clear()
    status = manager.run_sync(detect_fake_bitrate=True)

    assert status.state == "cancelled"
    assert status.cancel_requested is True
    assert status.report_id is None
    assert pending and all(future.cancelled() for future in pending)
    assert pool_closed
    assert analyzed == []
    assert not out_dir.exists()


def test_ambiguous_chain_group_is_flagged_for_review() -> None:
    """A copy joined through another copy is never presented as a keeper match.

    Connected components put every fingerprint-linked file in one group, but a
    file that never matched the keeper itself has no measured evidence against
    the copy the reviewer would keep, and the report has to say so.
    """
    tracks = [
        _record(1, "M:/Volumes/Abstracted/one.flac", size=30_000_000),
        _record(2, "M:/Volumes/Abstracted/two.flac", size=20_000_000),
        _record(3, "M:/Volumes/Abstracted/three.flac", size=10_000_000),
    ]

    groups = scoring_module.groups_from_fingerprint_pairs(
        tracks,
        {(1, 2): 0.9, (2, 3): 0.9},
    )
    payload = report_payload_module.build_report(
        groups,
        tracks,
        mode=config_module.MODE_FINGERPRINT_LSH,
        path_contains=[],
    )

    group = payload["groups"][0]
    assert group["suggested_keeper"]["track_id"] == 1
    candidates = {candidate["track_id"]: candidate for candidate in group["candidate_deletes"]}
    assert set(candidates) == {2, 3}
    assert "ambiguous chain" in " ".join(group["review_reasons"])
    assert candidates[2]["fingerprint_vs_keeper"] == pytest.approx(0.9)
    assert candidates[3]["fingerprint_vs_keeper"] is None
    assert any(
        "no direct fingerprint match" in reason
        for reason in candidates[3]["review_reasons"]
    )


def test_json_and_xlsx_reports_include_fingerprint_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        fingerprint=DUPLICATE_FINGERPRINT,
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.mp3",
        size=8_000_000,
        fingerprint=DUPLICATE_FINGERPRINT,
    )
    _insert_track(db_path, track_id=3, path="N:/Volumes/Other/three.flac", size=20_000_000)

    result = core_module.run_report(
        db_path=db_path,
        path_contains=[],
        limit_groups=None,
        out_dir=out_dir,
        mode=config_module.MODE_FINGERPRINT_SCAN,
    )

    json_payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert json_payload["database_path"] == str(db_path.resolve())
    assert json_payload["search_mode"] == config_module.MODE_FINGERPRINT_SCAN
    # The scan reads the whole library now, so the third track is in scope even
    # though it lives on another volume and joins no group.
    assert json_payload["database_track_count"] == 3
    assert json_payload["scoped_track_count"] == 3
    assert json_payload["track_count"] == 3
    assert list(json_payload["score_semantics"]) == ["fingerprint_similarity"]
    assert json_payload["fingerprint_retrieval"]["valid_stored_fingerprint_count"] == 2
    assert json_payload["fingerprint_retrieval"]["fingerprint_review_min_similarity"] == (
        config_module.SONARA_DUPLICATE_MIN_SIMILARITY
    )
    assert json_payload["statistics"]["candidate_count"] == 1
    assert json_payload["statistics"]["confidence_counts"]["high"] == 1

    group = json_payload["groups"][0]
    assert group["fingerprint_similarity"] == pytest.approx(1.0)
    assert group["confidence"] == "high"
    assert group["possible_different_master"] is False
    assert group["review_reasons"] == []
    evidence = group["pairwise_evidence"][0]
    assert evidence["left_track_id"] == 1
    assert evidence["right_track_id"] == 2
    assert evidence["fingerprint_similarity"] == pytest.approx(1.0)
    assert evidence["candidate_sources"] == ["fingerprint_scan"]
    assert evidence["duration_diff_seconds"] == pytest.approx(0.0)
    keeper = group["suggested_keeper"]
    assert keeper["role"] == "KEEP"
    assert keeper["track_id"] == 1
    assert keeper["why_keep"]
    assert "keeper_reasons" in keeper
    candidate = group["candidate_deletes"][0]
    assert candidate["role"] == "DUPLICATE"
    assert candidate["track_id"] == 2
    assert candidate["fingerprint_vs_keeper"] == pytest.approx(1.0)
    assert candidate["review_reasons"] == []
    assert {entry["role"] for entry in group["tracks"]} == {"KEEP", "DUPLICATE"}

    assert result.xlsx_path.exists()
    with zipfile.ZipFile(result.xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        groups_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        candidates_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        pair_evidence_xml = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")
    assert "sheet5.xml" not in workbook_xml
    for sheet_name in ("Summary", "Groups", "Candidates", "Pair Evidence"):
        assert sheet_name in workbook_xml
    assert "Audio Dedup Report" in summary_xml
    assert str(db_path.resolve()) in summary_xml
    assert "Total tracks in database" in summary_xml
    assert "Tracks after the path filter" in summary_xml
    assert "fingerprint_similarity" in groups_xml
    assert "fingerprint_vs_keeper" in candidates_xml
    assert "one.flac" in candidates_xml
    assert "candidate_sources" in pair_evidence_xml
    log_text = result.log_path.read_text(encoding="utf-8")
    assert f"search_mode={config_module.MODE_FINGERPRINT_SCAN}" in log_text
    assert "no files deleted; no databases mutated" in log_text


def test_apply_log_lists_deleted_files(tmp_path: Path) -> None:
    log_path = tmp_path / "audio_dedup_report.log"
    deleted_path = tmp_path / "Abstracted" / "duplicate.mp3"
    payload = {
        "generated_at": "2026-05-29T06:00:00",
        "database_path": str(tmp_path / "library.sqlite"),
        "search_mode": config_module.MODE_FINGERPRINT_SCAN,
        "database_track_count": 2,
        "track_count": 2,
        "scoped_track_count": 2,
        "group_count": 1,
    }
    apply_result = models_module.ApplyResult(
        deleted_track_ids=(2,),
        deleted_paths=(str(deleted_path),),
        skipped=(),
        failed=(),
        rhythm_lab_deleted_rows=0,
    )

    report_files_module.write_text_log(log_path, payload, apply_result=apply_result)

    log_text = log_path.read_text(encoding="utf-8")
    assert "deleted_files:" in log_text
    assert f"deleted_file={deleted_path}" in log_text


def _two_copy_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "library.sqlite"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, fingerprint=DUPLICATE_FINGERPRINT)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, fingerprint=DUPLICATE_FINGERPRINT)
    result = core_module.run_report(
        db_path=db_path,
        path_contains=[],
        limit_groups=None,
        out_dir=tmp_path / "reports",
        mode=config_module.MODE_FINGERPRINT_SCAN,
    )
    assert result.groups == 1
    return db_path, audio_dir, keeper_path, duplicate_path, result


def test_apply_duplicate_deletions_deletes_the_reviewer_selection_including_the_keeper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )
    keeper_track_id = int(result.payload["groups"][0]["suggested_keeper"]["track_id"])
    assert keeper_track_id == 1

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        payload=result.payload,
        selected_track_ids=[keeper_track_id],
    )

    assert apply_result.deleted_track_ids == (keeper_track_id,)
    assert not keeper_path.exists()
    assert duplicate_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(2,)]
    finally:
        connection.close()


def test_apply_duplicate_deletions_refuses_a_selection_that_empties_the_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        payload=result.payload,
        selected_track_ids=[1, 2],
    )

    assert apply_result.deleted_track_ids == ()
    assert keeper_path.exists()
    assert duplicate_path.exists()
    assert all("group would lose every copy" in reason for reason in apply_result.skipped)


def test_apply_duplicate_deletions_never_deletes_permanently_when_the_recycle_bin_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )
    module = types.ModuleType("send2trash")

    def refuse(_path: str) -> None:
        raise OSError("recycle bin unavailable")

    module.send2trash = refuse
    monkeypatch.setitem(sys.modules, "send2trash", module)

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        payload=result.payload,
        selected_track_ids=[2],
        deletion_mode=config_module.DELETION_MODE_TRASH,
    )

    assert apply_result.deleted_track_ids == ()
    assert duplicate_path.exists()
    assert keeper_path.exists()
    assert any("recycle bin unavailable" in reason for reason in apply_result.failed)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(1,), (2,)]
    finally:
        connection.close()


def test_apply_duplicate_deletions_drops_only_rhythm_lab_rows_naming_deleted_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lab_root = TOOL_ROOT.parent / "rhythm-lab"
    sys.path.insert(0, str(lab_root))
    try:
        from rhythm_lab.lab_db import RhythmLabDatabase
    finally:
        sys.path.remove(str(lab_root))

    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    same_path = audio_dir / "same.mp3"
    other_path = audio_dir / "other.mp3"
    for path in (keeper_path, same_path, other_path):
        path.write_bytes(path.name.encode("ascii"))
    other_fingerprint = base64.b64encode(bytes(range(4, 8)) * 64).decode("ascii")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    # The group also admits the copy with a different fingerprint.
    monkeypatch.setattr(fingerprints_module, "_native_fingerprint_match", lambda left, right: 1.0)
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, fingerprint=DUPLICATE_FINGERPRINT)
    _insert_track(db_path, track_id=2, path=str(same_path), size=8_000_000, mtime=200, fingerprint=DUPLICATE_FINGERPRINT)
    _insert_track(db_path, track_id=3, path=str(other_path), size=8_000_000, mtime=300, fingerprint=other_fingerprint)
    result = core_module.run_report(
        db_path=db_path,
        path_contains=[],
        limit_groups=None,
        out_dir=tmp_path / "reports",
        mode=config_module.MODE_FINGERPRINT_SCAN,
    )
    assert result.groups == 1
    files = {
        state.track_id: state
        for state in LibraryDatabase(db_path).get_track_file_states_by_ids((1, 2, 3))
    }
    shared_key = sonara_content_key(1, DUPLICATE_FINGERPRINT)
    other_key = sonara_content_key(1, other_fingerprint)
    stale_key = sonara_content_key(1, base64.b64encode(bytes(range(8, 12)) * 64).decode("ascii"))

    def snapshot(content_key: str, track_id: int) -> tuple[str, str, str, str]:
        file = files[track_id]
        return (content_key, file.catalog_uuid, file.track_uuid, file.file_path)

    # Another library that sighted the same files at the same paths.
    def elsewhere(content_key: str, track_uuid: str, track_id: int) -> tuple[str, str, str, str]:
        return (content_key, "second-catalog-uuid", track_uuid, files[track_id].file_path)

    lab = RhythmLabDatabase(rhythm_lab_db)
    lab.create_profile(
        classifier_key="break_energy",
        name="Break energy",
        artifact_dir=tmp_path / "profile",
        labels=[
            {"key": "broken", "role": "positive"},
            {"key": "straight", "role": "negative"},
        ],
    )
    # The shared key labels and queues the byte-identical copy that is deleted,
    # while its prediction and collection membership name the keeper. The other
    # key was labeled in the second library, and a stale sighting there saw
    # different content at the deleted path.
    with closing(lab.connect()) as connection, connection:
        connection.executemany(
            """
            INSERT INTO track_sightings(
                content_key, catalog_uuid, track_uuid, selected_path, track_id,
                file_size_bytes, file_modified_ns, fingerprint_version,
                fingerprint_analyzed_at
            ) VALUES (?, ?, ?, ?, ?, 1, 1, 1, '2026-07-24T00:00:00.000000Z')
            """,
            [
                (*snapshot(shared_key, 1), 1),
                (*snapshot(shared_key, 2), 2),
                (*snapshot(other_key, 3), 3),
                (*elsewhere(shared_key, "second-same", 2), 12),
                (*elsewhere(stale_key, "second-stale", 2), 13),
            ],
        )
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, content_key, label,
                last_catalog_uuid, last_track_uuid, last_selected_path
            ) VALUES ('break_energy', ?, 'broken', ?, ?, ?)
            """,
            [snapshot(shared_key, 2), elsewhere(other_key, "second-other", 3)],
        )
        connection.execute(
            """
            INSERT INTO classifier_training_checkpoints(classifier_key, counts_json, model_artifact)
            VALUES ('break_energy', '{"broken": 3, "straight": 4}', 'model.joblib')
            """
        )
        connection.executemany(
            """
            INSERT INTO classifier_label_queue(
                classifier_key, content_key, catalog_uuid, track_uuid,
                selected_path, mode, priority, reason_json
            ) VALUES ('break_energy', ?, ?, ?, ?, 'uncertainty', 1.0, '{}')
            """,
            [snapshot(shared_key, 2), snapshot(other_key, 3)],
        )
        connection.executemany(
            """
            INSERT INTO classifier_predictions(
                classifier_key, content_key, catalog_uuid, track_uuid,
                selected_path, feature_set, model_artifact, label,
                confidence, probabilities_json
            ) VALUES (
                'break_energy', ?, ?, ?, ?,
                'combined', 'model.joblib', 'broken', 0.9, '{}'
            )
            """,
            [snapshot(shared_key, 1), snapshot(other_key, 3)],
        )
        collection_id = connection.execute(
            "INSERT INTO review_collections(catalog_uuid, name) VALUES (?, 'Breaks')",
            (files[1].catalog_uuid,),
        ).lastrowid
        connection.executemany(
            """
            INSERT INTO review_collection_tracks(
                collection_id, content_key, catalog_uuid, track_uuid,
                selected_path, position
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (collection_id, *snapshot(shared_key, 1), 1),
                (collection_id, *snapshot(other_key, 3), 2),
            ],
        )
    lab_tables = (
        "track_sightings",
        "classifier_labels",
        "classifier_label_queue",
        "classifier_predictions",
        "review_collection_tracks",
        "review_collections",
    )

    def lab_rows() -> dict[str, list[tuple[object, ...]]]:
        with closing(sqlite3.connect(rhythm_lab_db)) as connection:
            return {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
                for table in lab_tables
            }

    def checkpoint() -> tuple[dict[str, int], str]:
        with closing(sqlite3.connect(rhythm_lab_db)) as connection:
            counts_json, updated_at = connection.execute(
                "SELECT counts_json, updated_at FROM classifier_training_checkpoints"
            ).fetchone()
        return json.loads(counts_json), updated_at

    def text_cells_containing(path: Path, needles: set[str]) -> list[tuple[str, str, str]]:
        found = []
        with closing(sqlite3.connect(path)) as connection:
            for (table,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall():
                for column in [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]:
                    for needle in sorted(needles):
                        if connection.execute(
                            f'SELECT 1 FROM "{table}" WHERE typeof("{column}") = \'text\''
                            f' AND instr("{column}", ?) > 0 LIMIT 1',
                            (needle,),
                        ).fetchone():
                            found.append((table, column, needle))
        return found

    before = lab_rows()
    _, trained_at = checkpoint()

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        payload=result.payload,
        selected_track_ids=[2, 3],
    )

    after = lab_rows()
    assert apply_result.deleted_track_ids == (2, 3)
    assert keeper_path.exists()
    assert {table: len(rows) for table, rows in after.items()} == {
        "track_sightings": 2,
        "classifier_labels": 0,
        "classifier_label_queue": 0,
        "classifier_predictions": 1,
        "review_collection_tracks": 1,
        "review_collections": 1,
    }
    # Rows naming the keeper, or other content at a deleted path, are untouched.
    assert after == {
        table: [
            row for row in rows
            if table == "review_collections" or {files[1].track_uuid, "second-stale"} & set(row)
        ]
        for table, rows in before.items()
    }
    assert apply_result.rhythm_lab_deleted_rows == 9
    # Both deleted labels come off the trained count; the training time stays.
    assert checkpoint() == ({"broken": 1, "straight": 4}, trained_at)
    deleted_file_facts = {
        value for track_id in (2, 3) for value in (files[track_id].file_path, files[track_id].track_uuid)
    }
    assert text_cells_containing(rhythm_lab_db, deleted_file_facts) == [
        ("track_sightings", "selected_path", files[2].file_path),
    ]
    assert text_cells_containing(db_path, deleted_file_facts) == []

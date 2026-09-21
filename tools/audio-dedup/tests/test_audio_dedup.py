from __future__ import annotations

import base64
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
import json
import sqlite3
import sys
import types
from pathlib import Path
import zipfile

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.audio_dedup_jobs import AudioDedupJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile

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


def _create_rhythm_lab_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                label TEXT NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid
                )
            );

            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                artist TEXT,
                title TEXT,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid
                )
            );

            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL
            );
            """
        )


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
    database = LibraryDatabase(db_path)
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=path,
            file_size_bytes=size,
            file_modified_ns=int(mtime * 1_000_000_000),
            audio_duration_seconds=duration,
        ),
        tags=FileTags(
            artist=artist,
            title=title,
            album=album,
            tag_bpm=bpm,
            tag_key=musical_key,
            genres=("Test",),
        ),
        scanned_at="2026-07-24T00:00:00.000000Z",
    )
    identity = mutation.identity
    assert identity.track_id == track_id

    if fingerprint is not None:
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sonara_fingerprints(
                    track_id, track_uuid, fingerprint_version,
                    fingerprint_base64, analyzed_at
                ) VALUES(?, ?, 1, ?, '2026-07-24T00:00:00.000000Z')
                """,
                (identity.track_id, identity.track_uuid, fingerprint),
            )
            connection.commit()


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


def _identity_tuple(
    db_path: Path,
    track_id: int,
) -> tuple[str, str, int]:
    identity = LibraryDatabase(db_path).get_track_identity(track_id)
    assert identity is not None
    return (
        identity.catalog_uuid,
        identity.track_uuid,
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


def test_keeper_selection_prefers_lossless_then_bitrate_proxy() -> None:
    low_bitrate_flac = _record(1, "M:/Volumes/Abstracted/a.flac", size=10_000_000, mtime=100.0)
    high_bitrate_flac = _record(2, "M:/Volumes/Abstracted/b.flac", size=20_000_000, mtime=50.0)
    mp3 = _record(3, "M:/Volumes/Abstracted/c.mp3", size=30_000_000, mtime=300.0)

    assert keeper_module.choose_keeper([low_bitrate_flac, high_bitrate_flac, mp3]).track_id == 2


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


def test_apply_duplicate_deletions_removes_deleted_tracks_from_default_rhythm_lab_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, fingerprint=DUPLICATE_FINGERPRINT)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, fingerprint=DUPLICATE_FINGERPRINT)
    keeper_identity = _identity_tuple(db_path, 1)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid, selected_path, label
            ) VALUES ('break_energy', ?, ?, ?, 'broken')
            """,
            [
                (*keeper_identity, str(keeper_path)),
                (*duplicate_identity, str(duplicate_path)),
            ],
        )
        connection.executemany(
            """
                INSERT INTO classifier_predictions(
                    classifier_key, catalog_uuid, track_uuid, selected_path,
                    feature_set, model_artifact, label, confidence, probabilities_json
                )
                VALUES(
                    'break_energy', ?, ?, ?,
                    'combined', 'model.joblib', 'broken', 0.9, '{}'
            )
            """,
            [
                (*keeper_identity, str(keeper_path)),
                (*duplicate_identity, str(duplicate_path)),
            ],
        )
        connection.execute(
            "INSERT INTO classifier_training_checkpoints(classifier_key, counts_json) VALUES ('break_energy', '{}')"
        )
    result = core_module.run_report(
        db_path=db_path,
        path_contains=[],
        limit_groups=None,
        out_dir=out_dir,
        mode=config_module.MODE_FINGERPRINT_SCAN,
    )

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        payload=result.payload,
        selected_track_ids=[2],
    )

    assert apply_result.deleted_track_ids == (2,)
    assert apply_result.rhythm_lab_deleted_rows == 2
    with sqlite3.connect(rhythm_lab_db) as connection:
        assert connection.execute(
            "SELECT track_uuid FROM classifier_labels"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute(
            "SELECT track_uuid FROM classifier_predictions"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute("SELECT classifier_key FROM classifier_training_checkpoints").fetchall() == [("break_energy",)]

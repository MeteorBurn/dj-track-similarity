from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_routes_rhythm_lab as rhythm_lab_routes
import dj_track_similarity.rhythm_lab_launcher as rhythm_lab_launcher
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.rhythm_lab_collections import (
    RhythmLabCollections,
    build_rhythm_lab_collection_selection,
)
from dj_track_similarity.rhythm_lab_launcher import RhythmLabSourceBinding
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


def test_rhythm_lab_launch_endpoint_uses_selected_database(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    calls: list[RhythmLabSourceBinding | None] = []

    def fake_launcher(
        source: RhythmLabSourceBinding | None = None,
    ) -> dict[str, object]:
        calls.append(source)
        return {
            "url": "http://127.0.0.1:8777/",
            "already_running": False,
            "source": None if source is None else source.as_payload(),
        }

    monkeypatch.setattr(api, "launch_rhythm_lab", fake_launcher, raising=False)
    client = TestClient(create_app(db_path))

    response = client.post("/api/rhythm-lab/launch")

    assert response.status_code == 200
    assert response.json()["url"] == "http://127.0.0.1:8777/"
    assert calls == [
        RhythmLabSourceBinding(
            source_db=database.path,
            catalog_uuid=database.catalog_uuid,
        )
    ]


def test_rhythm_lab_launch_endpoint_allows_no_selected_database(monkeypatch) -> None:
    calls: list[RhythmLabSourceBinding | None] = []

    def fake_launcher(
        source: RhythmLabSourceBinding | None = None,
    ) -> dict[str, object]:
        calls.append(source)
        return {
            "url": "http://127.0.0.1:8777/",
            "already_running": True,
            "source": None,
        }

    monkeypatch.setattr(api, "launch_rhythm_lab", fake_launcher, raising=False)
    client = TestClient(create_app())

    response = client.post("/api/rhythm-lab/launch")

    assert response.status_code == 200
    assert response.json()["already_running"] is True
    assert calls == [None]


def test_rhythm_lab_stop_endpoint_uses_managed_launcher(monkeypatch) -> None:
    monkeypatch.setattr(api, "stop_rhythm_lab", lambda: {"running": False, "stopped": True}, raising=False)
    client = TestClient(create_app())

    response = client.post("/api/rhythm-lab/stop")

    assert response.status_code == 200
    assert response.json() == {"running": False, "stopped": True}


def test_rhythm_lab_status_endpoint_returns_launcher_status(monkeypatch) -> None:
    monkeypatch.setattr(api, "rhythm_lab_status", lambda: {"running": True, "managed": True, "url": "http://127.0.0.1:8777/"}, raising=False)
    client = TestClient(create_app())

    response = client.get("/api/rhythm-lab/status")

    assert response.status_code == 200
    assert response.json()["running"] is True
    assert response.json()["managed"] is True


def test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(monkeypatch, tmp_path: Path) -> None:
    labels_path = tmp_path / "rhythm_lab.sqlite"
    monkeypatch.setattr(rhythm_lab_routes, "default_rhythm_lab_labels_path", lambda: labels_path)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first = _add_track(db, tmp_path, "first.wav", "Artist", "First")
    second = _add_track(db, tmp_path, "second.wav", "Artist", "Second")
    client = TestClient(create_app(db_path))

    response = client.post(
        "/api/rhythm-lab/collections",
        json={
            "name": "Main UI set",
            "track_ids": [first.track_id, second.track_id],
            "source": "main_ui_playlist",
            "mode": "replace",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Main UI set"
    assert response.json()["track_count"] == 2
    stored = RhythmLabCollections(labels_path).collection_by_name("Main UI set")
    expected = build_rhythm_lab_collection_selection(
        db,
        [first.track_id, second.track_id],
    )
    assert stored is not None
    assert stored.catalog_uuid == db.catalog_uuid
    assert [track.track_uuid for track in stored.tracks] == [
        first.track_uuid,
        second.track_uuid,
    ]
    assert [track.content_generation for track in stored.tracks] == [1, 1]
    assert [track.selected_path for track in stored.tracks] == [
        track.selected_path for track in expected.tracks
    ]


def _add_track(
    db: LibraryDatabase,
    tmp_path: Path,
    filename: str,
    artist: str,
    title: str,
) -> TrackIdentity:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    stat = path.stat()
    return db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            bit_rate_bps=1_411_200,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(
            title=title,
            artist=artist,
            album="API Rhythm Lab",
            tag_bpm=128.0,
            tag_key="8A",
            comment=None,
            genres=("House",),
        ),
    ).identity


def test_rhythm_lab_launcher_uses_project_python_and_source(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []
    popen_kwargs: list[dict[str, object]] = []
    mirrors: list[tuple[Path, int, object | None]] = []
    log_path = tmp_path / "logs" / "rhythm-lab.log"
    pid_path = tmp_path / "rhythm_lab.pid"

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
    monkeypatch.setattr(rhythm_lab_launcher, "_log_path", lambda: log_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_start_log_mirror", lambda path, offset, process: mirrors.append((path, offset, process)))
    monkeypatch.setattr(
        rhythm_lab_launcher.subprocess,
        "Popen",
        lambda command, **kwargs: commands.append(command) or popen_kwargs.append(kwargs) or FakeProcess(),
    )
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)

    binding = RhythmLabSourceBinding(
        source_db=tmp_path / "library.sqlite",
        catalog_uuid="catalog-launch",
    )
    result = rhythm_lab_launcher.launch_rhythm_lab(binding)
    repo_root = Path(rhythm_lab_launcher.__file__).resolve().parents[2]
    repo_python_candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    expected_python = next(
        (candidate for candidate in repo_python_candidates if candidate.exists()),
        Path(rhythm_lab_launcher.sys.executable),
    )

    assert result["pid"] == 12345
    assert commands
    assert Path(commands[0][0]) == expected_python
    assert "--source" in commands[0]
    assert str(binding.source_db) in commands[0]
    assert "--source-catalog-uuid" in commands[0]
    assert binding.catalog_uuid in commands[0]
    assert result["source"] == binding.as_payload()
    assert popen_kwargs[0]["env"]["PYTHONUNBUFFERED"] == "1"
    assert log_path.parent.exists()
    assert len(mirrors) == 1
    assert mirrors[0][0] == log_path
    assert mirrors[0][1] == 0
    assert mirrors[0][2].pid == 12345
    if rhythm_lab_launcher.sys.platform == "win32":
        creationflags = int(popen_kwargs[0]["creationflags"])
        assert creationflags & rhythm_lab_launcher.subprocess.CREATE_NEW_PROCESS_GROUP
        assert creationflags & rhythm_lab_launcher.subprocess.CREATE_NO_WINDOW
        assert not creationflags & rhythm_lab_launcher.subprocess.DETACHED_PROCESS
        assert popen_kwargs[0]["startupinfo"].wShowWindow == rhythm_lab_launcher.subprocess.SW_HIDE


def test_rhythm_lab_launcher_writes_pid_and_stops_managed_process(monkeypatch, tmp_path: Path) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    terminated: list[int] = []

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
    monkeypatch.setattr(rhythm_lab_launcher, "_start_log_mirror", lambda *_args: None)
    monkeypatch.setattr(rhythm_lab_launcher.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(rhythm_lab_launcher, "_is_rhythm_lab_process", lambda pid: pid == 12345)
    monkeypatch.setattr(rhythm_lab_launcher, "_terminate_process", lambda pid: terminated.append(pid))

    rhythm_lab_launcher.launch_rhythm_lab()
    result = rhythm_lab_launcher.stop_rhythm_lab()

    assert pid_path.exists() is False
    assert terminated == [12345]
    assert result == {"running": False, "stopped": True, "managed": True, "url": "http://127.0.0.1:8777/"}


def test_rhythm_lab_launcher_stops_valid_listener_when_pid_file_is_stale(monkeypatch, tmp_path: Path) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    pid_path.write_text("30912", encoding="utf-8")
    terminated: list[int] = []

    def fake_port_is_open(*_: object) -> bool:
        return terminated != [29280]

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", fake_port_is_open)
    monkeypatch.setattr(rhythm_lab_launcher, "_listener_process_id", lambda *_: 29280, raising=False)
    monkeypatch.setattr(rhythm_lab_launcher, "_is_rhythm_lab_process", lambda pid: pid == 29280, raising=False)
    monkeypatch.setattr(rhythm_lab_launcher, "_terminate_process", lambda pid: terminated.append(pid))
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)

    result = rhythm_lab_launcher.stop_rhythm_lab()

    assert pid_path.exists() is False
    assert terminated == [29280]
    assert result == {"running": False, "stopped": True, "managed": True, "url": "http://127.0.0.1:8777/"}


def test_rhythm_lab_launcher_clears_pid_when_launch_process_exits(monkeypatch, tmp_path: Path) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"

    class FakeProcess:
        pid = 4242

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
    monkeypatch.setattr(rhythm_lab_launcher, "_start_log_mirror", lambda *_args: None)
    monkeypatch.setattr(rhythm_lab_launcher.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)

    try:
        rhythm_lab_launcher.launch_rhythm_lab()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected launch_rhythm_lab to fail")

    assert pid_path.exists() is False


def test_rhythm_lab_launcher_restores_existing_pid_when_launch_process_exits(monkeypatch, tmp_path: Path) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    pid_path.write_text("11111", encoding="utf-8")

    class FakeProcess:
        pid = 4242

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
    monkeypatch.setattr(rhythm_lab_launcher, "_is_rhythm_lab_process", lambda pid: pid == 11111)
    monkeypatch.setattr(rhythm_lab_launcher, "_start_log_mirror", lambda *_args: None)
    monkeypatch.setattr(rhythm_lab_launcher.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)

    try:
        rhythm_lab_launcher.launch_rhythm_lab()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected launch_rhythm_lab to fail")

    assert pid_path.read_text(encoding="utf-8") == "11111"


def test_rhythm_lab_launcher_reuses_running_server(monkeypatch, tmp_path: Path) -> None:
    mirrors: list[tuple[Path, int, object | None]] = []
    log_path = tmp_path / "rhythm_lab.log"
    log_path.write_text("old log\n", encoding="utf-8")
    pid_path = tmp_path / "rhythm_lab.pid"
    pid_path.write_text("12345", encoding="utf-8")
    binding = RhythmLabSourceBinding(
        source_db=tmp_path / "library.sqlite",
        catalog_uuid="catalog-reuse",
    )
    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_log_path", lambda: log_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_start_log_mirror", lambda path, offset, process: mirrors.append((path, offset, process)))
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: True)
    monkeypatch.setattr(
        rhythm_lab_launcher,
        "_managed_process_id",
        lambda pid: pid if pid == 12345 else None,
    )
    rhythm_lab_launcher._write_source_binding(binding)
    monkeypatch.setattr(
        rhythm_lab_launcher.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Rhythm Lab should not be launched twice")),
    )

    result = rhythm_lab_launcher.launch_rhythm_lab(binding)

    assert result["already_running"] is True
    assert result["managed"] is True
    assert result["source"] == binding.as_payload()
    assert mirrors == [(log_path, log_path.stat().st_size, None)]


def test_rhythm_lab_log_mirror_prints_new_lines_with_prefix(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "rhythm_lab.log"
    old_text = b"old line\n"
    log_path.write_bytes(old_text + b"new line\n")

    class FinishedProcess:
        def poll(self) -> int:
            return 0

    rhythm_lab_launcher._mirror_log_to_console(log_path, len(old_text), FinishedProcess())

    captured = capsys.readouterr()
    assert captured.out == "[Rhythm Lab] new line\n"


def test_rhythm_lab_default_log_path_uses_logs_directory() -> None:
    log_path = rhythm_lab_launcher._log_path()

    assert log_path.name == "rhythm-lab.log"
    assert log_path.parent.name == "logs"

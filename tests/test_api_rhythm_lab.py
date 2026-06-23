from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.rhythm_lab_launcher as rhythm_lab_launcher
from dj_track_similarity.api import create_app


def test_rhythm_lab_launch_endpoint_uses_selected_database(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    calls: list[Path | None] = []

    def fake_launcher(source_db: Path | None = None) -> dict[str, object]:
        calls.append(source_db)
        return {"url": "http://127.0.0.1:8777/", "already_running": False, "source_db": str(source_db)}

    monkeypatch.setattr(api, "launch_rhythm_lab", fake_launcher, raising=False)
    client = TestClient(create_app(db_path))

    response = client.post("/api/rhythm-lab/launch")

    assert response.status_code == 200
    assert response.json()["url"] == "http://127.0.0.1:8777/"
    assert calls == [db_path.resolve()]


def test_rhythm_lab_launch_endpoint_allows_no_selected_database(monkeypatch) -> None:
    calls: list[Path | None] = []

    def fake_launcher(source_db: Path | None = None) -> dict[str, object]:
        calls.append(source_db)
        return {"url": "http://127.0.0.1:8777/", "already_running": True, "source_db": None}

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


def test_rhythm_lab_launcher_uses_project_python_and_source(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []
    pid_path = tmp_path / "rhythm_lab.pid"

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
    monkeypatch.setattr(rhythm_lab_launcher.subprocess, "Popen", lambda command, **_: commands.append(command) or FakeProcess())
    monkeypatch.setattr(rhythm_lab_launcher.time, "sleep", lambda _: None)

    result = rhythm_lab_launcher.launch_rhythm_lab(tmp_path / "library.sqlite")
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
    assert str(tmp_path / "library.sqlite") in commands[0]


def test_rhythm_lab_launcher_writes_pid_and_stops_managed_process(monkeypatch, tmp_path: Path) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    terminated: list[int] = []

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: False)
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
    monkeypatch.setattr(rhythm_lab_launcher, "_pid_path", lambda: tmp_path / "rhythm_lab.pid")
    monkeypatch.setattr(rhythm_lab_launcher, "_port_is_open", lambda *_: True)

    result = rhythm_lab_launcher.launch_rhythm_lab(tmp_path / "library.sqlite")

    assert result["already_running"] is True
    assert result["source_db"] == str(tmp_path / "library.sqlite")

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


RHYTHM_LAB_HOST = "127.0.0.1"
RHYTHM_LAB_PORT = 8777
RHYTHM_LAB_URL = f"http://{RHYTHM_LAB_HOST}:{RHYTHM_LAB_PORT}/"


def launch_rhythm_lab(source_db: Path | None = None) -> dict[str, Any]:
    if _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
        return {
            "url": RHYTHM_LAB_URL,
            "already_running": True,
            "managed": _read_pid() is not None,
            "source_db": str(source_db) if source_db else None,
        }

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools" / "rhythm-lab" / "rhythm_lab_cli.py"
    labels = repo_root / "tools" / "rhythm-lab" / "data" / "rhythm_lab.sqlite"
    log_path = repo_root / "dj-track-similarity-rhythm-lab.log"
    if not script.exists():
        raise RuntimeError(f"Rhythm Lab CLI not found: {script}")
    labels.parent.mkdir(parents=True, exist_ok=True)

    command = [
        str(_project_python(repo_root)),
        str(script),
        "serve",
        "--labels",
        str(labels),
        "--host",
        RHYTHM_LAB_HOST,
        "--port",
        str(RHYTHM_LAB_PORT),
    ]
    if source_db is not None:
        command.extend(["--source", str(source_db)])

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    _pid_path().write_text(str(process.pid), encoding="utf-8")
    for _ in range(20):
        if _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
            break
        exit_code = process.poll()
        if exit_code is not None:
            detail = _tail_text(log_path)
            raise RuntimeError(f"Rhythm Lab server exited with code {exit_code}. See {log_path}. {detail}")
        time.sleep(0.25)
    return {
        "url": RHYTHM_LAB_URL,
        "already_running": False,
        "managed": True,
        "pid": process.pid,
        "source_db": str(source_db) if source_db else None,
    }


def rhythm_lab_status() -> dict[str, Any]:
    running = _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT)
    return {"running": running, "managed": _read_pid() is not None, "url": RHYTHM_LAB_URL}


def stop_rhythm_lab() -> dict[str, Any]:
    pid = _read_pid()
    if pid is None:
        return {"running": _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT), "stopped": False, "managed": False, "url": RHYTHM_LAB_URL}

    _terminate_process(pid)
    for _ in range(20):
        if not _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
            _clear_pid()
            return {"running": False, "stopped": True, "managed": True, "url": RHYTHM_LAB_URL}
        time.sleep(0.25)
    raise RuntimeError(f"Rhythm Lab process {pid} did not stop")


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((host, port)) == 0


def _pid_path() -> Path:
    return Path(__file__).resolve().parents[2] / "tools" / "rhythm-lab" / "data" / "rhythm_lab.pid"


def _read_pid() -> int | None:
    try:
        text = _pid_path().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        _clear_pid()
        return None


def _clear_pid() -> None:
    try:
        _pid_path().unlink()
    except FileNotFoundError:
        pass


def _terminate_process(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    os.kill(pid, signal.SIGTERM)


def _project_python(repo_root: Path) -> Path:
    windows_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if windows_python.exists():
        return windows_python
    posix_python = repo_root / ".venv" / "bin" / "python"
    if posix_python.exists():
        return posix_python
    return Path(sys.executable)


def _tail_text(path: Path, limit: int = 1200) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-limit:].decode("utf-8", errors="replace").strip()

from __future__ import annotations

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
        return {"url": RHYTHM_LAB_URL, "already_running": True, "source_db": str(source_db) if source_db else None}

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
        "pid": process.pid,
        "source_db": str(source_db) if source_db else None,
    }


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((host, port)) == 0


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

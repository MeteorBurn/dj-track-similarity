from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


RHYTHM_LAB_HOST = "127.0.0.1"
RHYTHM_LAB_PORT = 8777
RHYTHM_LAB_URL = f"http://{RHYTHM_LAB_HOST}:{RHYTHM_LAB_PORT}/"
_LOG_MIRROR_LOCK = threading.Lock()
_LOG_MIRROR_THREADS: dict[Path, threading.Thread] = {}


def launch_rhythm_lab(source_db: Path | None = None) -> dict[str, Any]:
    log_path = _log_path()
    if _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
        _start_log_mirror(log_path, _file_size(log_path), None)
        return {
            "url": RHYTHM_LAB_URL,
            "already_running": True,
            "managed": _read_pid() is not None,
            "source_db": str(source_db) if source_db else None,
        }

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools" / "rhythm-lab" / "rhythm_lab_cli.py"
    labels = repo_root / "tools" / "rhythm-lab" / "data" / "rhythm_lab.sqlite"
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

    previous_pid = _read_pid()
    log_start_offset = _file_size(log_path)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
            env=env,
        )
    _start_log_mirror(log_path, log_start_offset, process)
    _write_pid(process.pid)
    for _ in range(20):
        if _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
            break
        exit_code = process.poll()
        if exit_code is not None:
            _restore_or_clear_pid(previous_pid)
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
    pid = _read_pid()
    managed = running and pid is not None and _managed_process_id(pid) is not None
    if not running and pid is not None:
        _clear_pid()
    return {"running": running, "managed": managed, "url": RHYTHM_LAB_URL}


def stop_rhythm_lab() -> dict[str, Any]:
    pid = _read_pid()
    if pid is None:
        return {"running": _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT), "stopped": False, "managed": False, "url": RHYTHM_LAB_URL}

    stop_pid = _managed_process_id(pid)
    if stop_pid is None:
        _clear_pid()
        return {"running": _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT), "stopped": False, "managed": False, "url": RHYTHM_LAB_URL}

    _terminate_process(stop_pid)
    for _ in range(20):
        if not _port_is_open(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT):
            _clear_pid()
            return {"running": False, "stopped": True, "managed": True, "url": RHYTHM_LAB_URL}
        time.sleep(0.25)
    raise RuntimeError(f"Rhythm Lab process {stop_pid} did not stop")


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((host, port)) == 0


def _pid_path() -> Path:
    return Path(__file__).resolve().parents[2] / "tools" / "rhythm-lab" / "data" / "rhythm_lab.pid"


def _log_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logs" / "rhythm-lab.log"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _start_log_mirror(log_path: Path, start_offset: int, process: Any | None) -> None:
    log_path = log_path.resolve()
    with _LOG_MIRROR_LOCK:
        existing_thread = _LOG_MIRROR_THREADS.get(log_path)
        if existing_thread is not None and existing_thread.is_alive():
            return
        thread = threading.Thread(
            target=_mirror_log_to_console,
            args=(log_path, start_offset, process),
            name="rhythm-lab-log-mirror",
            daemon=True,
        )
        _LOG_MIRROR_THREADS[log_path] = thread
        thread.start()


def _mirror_log_to_console(log_path: Path, start_offset: int, process: Any | None) -> None:
    try:
        with log_path.open("rb") as log_file:
            log_file.seek(start_offset)
            while True:
                line = log_file.readline()
                if line:
                    text = line.decode("utf-8", errors="replace")
                    print(f"[Rhythm Lab] {text}", end="", flush=True)
                    continue
                if process is not None and process.poll() is not None:
                    return
                time.sleep(0.25)
    except FileNotFoundError:
        return
    except OSError as error:
        print(f"[Rhythm Lab] log mirror stopped: {error}", file=sys.stderr, flush=True)
    finally:
        with _LOG_MIRROR_LOCK:
            if _LOG_MIRROR_THREADS.get(log_path) is threading.current_thread():
                _LOG_MIRROR_THREADS.pop(log_path, None)


def _write_pid(pid: int) -> None:
    _pid_path().write_text(str(pid), encoding="utf-8")


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


def _restore_or_clear_pid(pid: int | None) -> None:
    if pid is None:
        _clear_pid()
        return
    managed_pid = _managed_process_id(pid)
    if managed_pid is None:
        _clear_pid()
        return
    _write_pid(managed_pid)


def _managed_process_id(pid: int) -> int | None:
    if _is_rhythm_lab_process(pid):
        return pid
    listener_pid = _listener_process_id(RHYTHM_LAB_HOST, RHYTHM_LAB_PORT)
    if listener_pid is not None and _is_rhythm_lab_process(listener_pid):
        return listener_pid
    return None


def _listener_process_id(host: str, port: int) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    host_port = f"{host}:{port}"
    any_host_port = f"0.0.0.0:{port}"
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "TCP":
            continue
        local_address, state, pid_text = fields[1], fields[3], fields[4]
        if state != "LISTENING" or local_address not in {host_port, any_host_port}:
            continue
        try:
            return int(pid_text)
        except ValueError:
            return None
    return None


def _is_rhythm_lab_process(pid: int) -> bool:
    command_line = _process_command_line(pid)
    if not command_line:
        return False
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools" / "rhythm-lab" / "rhythm_lab_cli.py"
    normalized_command = command_line.lower().replace("\\", "/")
    normalized_script = str(script).lower().replace("\\", "/")
    return normalized_script in normalized_command and " serve " in f" {normalized_command} "


def _process_command_line(pid: int) -> str | None:
    if sys.platform == "win32":
        return _windows_process_command_line(pid)
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        data = proc_cmdline.read_bytes()
    except OSError:
        return None
    return data.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _windows_process_command_line(pid: int) -> str | None:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = completed.stdout.strip()
    return text or None


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

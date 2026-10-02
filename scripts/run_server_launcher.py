from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import shutil
import subprocess
import sys

from dj_track_similarity._shutdown import defer_keyboard_interrupt
from dj_track_similarity.windows_process_job import bind_process_to_job


_MODE_ALIASES = frozenset(
    {
        "local",
        "localhost",
        "127.0.0.1",
        "--local",
        "lan",
        "network",
        "0.0.0.0",
        "--lan",
    }
)
_HOST_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_HOST"
_PORT_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_PORT"
_DATABASE_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE"
_CREATE_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_CREATE"
_FRONTEND_DEV_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_DEV"
_FRONTEND_HOST_ENV = "DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_HOST"
# Never close this handle in Python: the launcher itself belongs to the job.
# Windows closes it on process exit and stops all remaining owned descendants.
_launcher_lifetime_job: int | None = None


def build_server_command(
    arguments: Sequence[str],
    *,
    host: str,
    port: str,
    database_path: str | None,
    create: bool = False,
) -> list[str]:
    forwarded_arguments = list(arguments)
    if forwarded_arguments and forwarded_arguments[0].casefold() in _MODE_ALIASES:
        del forwarded_arguments[0]

    command = ["dj-sim", "serve"]
    command.extend(forwarded_arguments)
    command.extend(("--host", host, "--port", port))
    if database_path:
        command.extend(("--db", database_path))
        if create:
            command.append("--create")
    return command


def resolve_npm_executable() -> str:
    npm_name = "npm.cmd" if os.name == "nt" else "npm"
    executable = shutil.which(npm_name) or shutil.which("npm")
    if executable is None:
        raise FileNotFoundError("npm was not found on PATH")
    return executable


def build_frontend_command(*, host: str, npm_executable: str | None = None) -> list[str]:
    script = "dev:lan" if host == "0.0.0.0" else "dev"
    return [npm_executable or resolve_npm_executable(), "run", script]


def frontend_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "frontend"


def stop_process(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main(arguments: Sequence[str] | None = None) -> int:
    global _launcher_lifetime_job
    host = os.environ.get(_HOST_ENV)
    port = os.environ.get(_PORT_ENV)
    if not host or not port:
        print("Launcher host and port were not configured.", file=sys.stderr)
        return 2

    command = build_server_command(
        sys.argv[1:] if arguments is None else arguments,
        host=host,
        port=port,
        database_path=os.environ.get(_DATABASE_ENV),
        create=os.environ.get(_CREATE_ENV) == "1",
    )
    frontend_process: subprocess.Popen[object] | None = None
    if os.environ.get(_FRONTEND_DEV_ENV) == "1":
        frontend_host = os.environ.get(_FRONTEND_HOST_ENV, "127.0.0.1")
        try:
            if os.name == "nt" and _launcher_lifetime_job is None:
                # Bind before Popen so even very short-lived npm wrappers cannot
                # create descendants outside the launcher's lifetime.
                _launcher_lifetime_job = bind_process_to_job(-1)
            frontend_process = subprocess.Popen(
                build_frontend_command(host=frontend_host),
                cwd=frontend_directory(),
                shell=False,
            )
        except OSError as error:
            print(f"Cannot start managed Vite frontend: {error}", file=sys.stderr)
            return 1
    try:
        with subprocess.Popen(command, shell=False) as server_process:
            # Ctrl+C reaches the API through the same console. Keep the owner
            # alive while the API drains jobs and closes its database resources.
            with defer_keyboard_interrupt() as finish:
                finish(server_process.wait)
            return server_process.returncode
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(f"Cannot start dj-sim: {error}", file=sys.stderr)
        return 1
    finally:
        if frontend_process is not None:
            stop_process(frontend_process)


if __name__ == "__main__":
    raise SystemExit(main())

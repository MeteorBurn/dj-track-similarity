from __future__ import annotations

from collections.abc import Sequence
import os
import subprocess
import sys


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


def build_server_command(
    arguments: Sequence[str],
    *,
    host: str,
    port: str,
    database_path: str | None,
) -> list[str]:
    forwarded_arguments = list(arguments)
    if forwarded_arguments and forwarded_arguments[0].casefold() in _MODE_ALIASES:
        del forwarded_arguments[0]

    command = ["dj-sim", "serve", "--host", host, "--port", port]
    if database_path:
        command.extend(("--db", database_path))
    command.extend(forwarded_arguments)
    return command


def main(arguments: Sequence[str] | None = None) -> int:
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
    )
    try:
        completed = subprocess.run(command, check=False, shell=False)
    except OSError as error:
        print(f"Cannot start dj-sim: {error}", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

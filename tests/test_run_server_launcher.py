from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def _run_isolated_launcher(
    tmp_path: Path,
    *,
    stdin: str,
    arguments: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "run_server.cmd"
    shutil.copyfile(root / "run_server.cmd", script)

    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "activate.bat").write_text(
        "@echo off\r\nexit /b 0\r\n", encoding="utf-8"
    )

    capture_path = tmp_path / "captured-args.txt"
    launcher_dir = tmp_path / "scripts"
    launcher_dir.mkdir()
    (launcher_dir / "run_server_launcher.py").write_text(
        "\n".join(
            (
                "import json",
                "import os",
                "from pathlib import Path",
                "import sys",
                "",
                "payload = {",
                '    "arguments": sys.argv[1:],',
                '    "host": os.environ["DJ_TRACK_SIMILARITY_LAUNCHER_HOST"],',
                '    "port": os.environ["DJ_TRACK_SIMILARITY_LAUNCHER_PORT"],',
                '    "database_path": os.environ.get(',
                '        "DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE",',
                '        "",',
                "    ),",
                "}",
                'Path(os.environ["DJ_SIM_CAPTURE"]).write_text(',
                "    json.dumps(payload),",
                '    encoding="utf-8",',
                ")",
                "",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "dj-sim.cmd").write_text(
        "@echo off\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    (tmp_path / "npm.cmd").write_text(
        "@echo off\r\nexit /b 0\r\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["DJ_SIM_CAPTURE"] = str(capture_path)
    environment["MODE_CHOICE"] = "network"
    environment["PATH"] = f"{tmp_path}{os.pathsep}{environment['PATH']}"
    input_path = tmp_path / "launcher-input.txt"
    input_path.write_text(stdin, encoding="utf-8")
    with input_path.open(encoding="utf-8") as input_stream:
        completed = subprocess.run(
            ("cmd.exe", "/d", "/c", str(script), *arguments),
            cwd=tmp_path,
            env=environment,
            stdin=input_stream,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    # No capture means the launcher never started the server.
    captured_launch = (
        json.loads(capture_path.read_text(encoding="utf-8"))
        if capture_path.exists()
        else None
    )
    return completed, captured_launch


@pytest.mark.skipif(os.name != "nt", reason="run_server.cmd requires Windows")
def test_no_argument_launcher_requires_an_explicit_database_before_mode(
    tmp_path: Path,
) -> None:
    def run(
        case: str,
        stdin: str,
    ) -> tuple[Path, subprocess.CompletedProcess[str], dict[str, object] | None]:
        case_dir = tmp_path / case
        (case_dir / "database").mkdir(parents=True)
        (case_dir / "database" / "library.sqlite").write_bytes(b"")
        return case_dir, *_run_isolated_launcher(case_dir, stdin=stdin)

    case_dir, completed, captured_launch = run("listed", "1\n\n")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.index("Database [1-1, or a path]") < (
        completed.stdout.index("Choose server mode")
    )
    assert captured_launch == {
        "arguments": [],
        "host": "127.0.0.1",
        "port": "8765",
        "database_path": str(case_dir / "database" / "library.sqlite"),
    }

    typed_path = str(tmp_path / "elsewhere" / "typed.sqlite")
    _, completed, captured_launch = run("typed", f"{typed_path}\n\n")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert captured_launch is not None
    assert captured_launch["database_path"] == typed_path

    _, completed, captured_launch = run("empty", "\n\n")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "No database selected" in completed.stdout
    assert "Choose server mode" not in completed.stdout
    assert captured_launch is None


@pytest.mark.skipif(os.name != "nt", reason="run_server.cmd requires Windows")
def test_explicit_local_mode_does_not_inject_a_database(tmp_path: Path) -> None:
    completed, captured_launch = _run_isolated_launcher(
        tmp_path,
        stdin="",
        arguments=("local",),
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Database path [" not in completed.stdout
    assert "Choose server mode" not in completed.stdout
    assert captured_launch == {
        "arguments": ["local"],
        "host": "127.0.0.1",
        "port": "8765",
        "database_path": "",
    }


def test_python_launcher_builds_argument_list_without_shell_reparsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "run_server_launcher.py"
    spec = importlib.util.spec_from_file_location("run_server_launcher", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    explicit_path = r"D:\Explicit!DJ & Techno\library.sqlite"
    assert module.build_server_command(
        ("lan", "--db", explicit_path),
        host="0.0.0.0",
        port="8765",
        database_path=None,
    ) == [
        "dj-sim",
        "serve",
        "--db",
        explicit_path,
        "--host",
        "0.0.0.0",
        "--port",
        "8765",
    ]
    assert module.build_server_command(
        (),
        host="127.0.0.1",
        port="8765",
        database_path=r"C:\db\volumes.sqlite",
    ) == [
        "dj-sim",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--db",
        r"C:\db\volumes.sqlite",
    ]
    assert module.build_server_command(
        ("local", "--host", "0.0.0.0", "--port", "9999"),
        host="127.0.0.1",
        port="8765",
        database_path=None,
    ) == [
        "dj-sim",
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "9999",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert module.build_frontend_command(
        host="127.0.0.1",
        npm_executable="npm.cmd",
    ) == ["npm.cmd", "run", "dev"]
    assert module.build_frontend_command(
        host="0.0.0.0",
        npm_executable="npm.cmd",
    ) == ["npm.cmd", "run", "dev:lan"]

    captured_run: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured_run.update(command=command, check=check, shell=shell)
        return subprocess.CompletedProcess(command, 23)

    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_HOST", "0.0.0.0")
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_PORT", "8765")
    monkeypatch.delenv("DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE", raising=False)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.main(("lan", "--db", explicit_path)) == 23
    assert captured_run == {
        "command": [
            "dj-sim",
            "serve",
            "--db",
            explicit_path,
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
        ],
        "check": False,
        "shell": False,
    }

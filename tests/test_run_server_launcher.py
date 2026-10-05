from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import time

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
                '    "create": os.environ.get(',
                '        "DJ_TRACK_SIMILARITY_LAUNCHER_CREATE",',
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
    assert completed.stdout.index("Database [1-1, a name or a path]") < (
        completed.stdout.index("Choose server mode")
    )
    assert captured_launch == {
        "arguments": [],
        "host": "127.0.0.1",
        "port": "8765",
        "database_path": str(case_dir / "database" / "library.sqlite"),
        "create": "",
    }

    typed_path = tmp_path / "elsewhere" / "typed.sqlite"
    typed_path.parent.mkdir()
    typed_path.write_bytes(b"")
    _, completed, captured_launch = run("typed", f"{typed_path}\n\n")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Database not found" not in completed.stdout
    assert captured_launch is not None
    assert captured_launch["database_path"] == str(typed_path)
    assert captured_launch["create"] == ""

    # A typed path that does not exist is created only after an explicit "y".
    new_path = str(tmp_path / "elsewhere" / "New!DJ & Techno.sqlite")
    prompt = f'Database not found: "{new_path}". Create a new library there? [y/N]: '
    _, completed, captured_launch = run("declined", f"{new_path}\nn\n\n")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert prompt in completed.stdout
    assert "No database selected" in completed.stdout
    assert "Choose server mode" not in completed.stdout
    assert captured_launch is None

    _, completed, captured_launch = run("confirmed", f"{new_path}\ny\n\n")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert prompt in completed.stdout
    assert captured_launch is not None
    assert captured_launch["database_path"] == new_path
    assert captured_launch["create"] == "1"

    # A bare name is a library in the project's database folder, not in the
    # console's working directory, and gets .sqlite when it has no extension.
    case_dir, completed, captured_launch = run("named", "fresh\ny\n\n")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert captured_launch is not None
    assert captured_launch["database_path"] == str(case_dir / "database" / "fresh.sqlite")
    assert captured_launch["create"] == "1"

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
        "create": "",
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

    class FakeServer:
        returncode = 23

        def __init__(self, command: list[str], *, shell: bool) -> None:
            captured_run.update(command=command, shell=shell)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def wait(self) -> int:
            return self.returncode

    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_HOST", "0.0.0.0")
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_PORT", "8765")
    monkeypatch.delenv("DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE", raising=False)
    monkeypatch.delenv("DJ_TRACK_SIMILARITY_LAUNCHER_CREATE", raising=False)
    monkeypatch.setattr(module.subprocess, "Popen", FakeServer)

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
        "shell": False,
    }

    # The interactive launcher confirmed a new library at a typed path.
    new_path = r"D:\New!DJ & Techno\library.sqlite"
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE", new_path)
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LAUNCHER_CREATE", "1")

    assert module.main(()) == 23
    assert captured_run["command"] == [
        "dj-sim",
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "8765",
        "--db",
        new_path,
        "--create",
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree lifetime")
def test_launcher_shutdown_ends_frontend_descendants_when_taskkill_fails(
    tmp_path: Path,
) -> None:
    import _winapi

    root = Path(__file__).resolve().parents[1]
    ready = tmp_path / "frontend.json"
    release = tmp_path / "backend-exit"
    frontend = textwrap.dedent("""
        import json, os, subprocess, sys, time
        from pathlib import Path
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        ready = Path(sys.argv[1])
        pending = ready.with_suffix(".tmp")
        pending.write_text(json.dumps([os.getpid(), child.pid]))
        pending.replace(ready)
        time.sleep(60)
    """)
    backend = textwrap.dedent("""
        import sys, time
        from pathlib import Path
        while not Path(sys.argv[1]).exists():
            time.sleep(0.02)
        sys.exit(23)
    """)
    driver = textwrap.dedent("""
        import importlib.util, os, subprocess, sys
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("launcher", sys.argv[1])
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        os.environ["DJ_TRACK_SIMILARITY_LAUNCHER_HOST"] = "127.0.0.1"
        os.environ["DJ_TRACK_SIMILARITY_LAUNCHER_PORT"] = "8765"
        os.environ["DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_DEV"] = "1"
        launcher.build_frontend_command = lambda **_: [sys._base_executable, "-c", sys.argv[2], sys.argv[3]]
        launcher.frontend_directory = lambda: Path(sys.argv[3]).parent
        launcher.build_server_command = lambda *_, **__: [sys._base_executable, "-c", sys.argv[4], sys.argv[5]]
        real_run = subprocess.run
        def run(command, **kwargs):
            if command[0] == "taskkill":
                return subprocess.CompletedProcess(command, 1)
            return real_run(command, **kwargs)
        subprocess.run = run
        sys.exit(launcher.main([]))
    """)
    # A sibling must remain alive: ownership must not become a global kill.
    with subprocess.Popen(
        [sys._base_executable, "-c", "import time; time.sleep(60)"],
    ) as sibling, (tmp_path / "launcher.log").open("w+") as log, subprocess.Popen(
        [sys.executable, "-c", driver, str(root / "scripts/run_server_launcher.py"),
         frontend, str(ready), backend, str(release)],
        stdout=log,
        stderr=log,
    ) as owner:
        handles: list[int] = []
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and owner.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            log.flush()
            log.seek(0)
            assert ready.exists(), log.read()
            for pid in json.loads(ready.read_text()):
                handles.append(_winapi.OpenProcess(_winapi.PROCESS_ALL_ACCESS, False, pid))
            release.touch()
            assert owner.wait(timeout=15) == 23
            assert [
                _winapi.WaitForSingleObject(handle, 5000) for handle in handles
            ] == [_winapi.WAIT_OBJECT_0] * len(handles)
            assert sibling.poll() is None
        finally:
            release.touch()
            for handle in handles:
                if _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_OBJECT_0:
                    _winapi.TerminateProcess(handle, 1)
                _winapi.CloseHandle(handle)
            owner.kill()
            sibling.kill()

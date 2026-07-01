from __future__ import annotations

from pathlib import Path


def test_root_server_script_prompts_supports_modes_and_forwards_args() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "run_server.cmd"

    text = script.read_text(encoding="utf-8")

    assert 'call "%PROJECT_ROOT%\\.venv\\Scripts\\activate.bat"' in text
    assert "where dj-sim" in text
    assert "dj-sim serve" in text
    assert "python -m uvicorn" not in text
    assert "Local virtual environment was not found" in text
    assert "dj-sim is not available" in text
    assert "Choose server mode" in text
    assert 'if /I "%~1"=="local"' in text
    assert 'if /I "%~1"=="lan"' in text
    assert 'set "HOST=127.0.0.1"' in text
    assert 'set "HOST=0.0.0.0"' in text
    assert "--host %HOST%" in text
    assert 'set "PORT=8765"' in text
    assert 'set "FORWARDED_ARGS=' in text
    assert ":collect_args" in text
    assert "shift /1" in text
    assert "dj-sim serve --host %HOST% --port %PORT% %FORWARDED_ARGS%" in text


def test_lan_server_script_was_removed_to_keep_one_main_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]

    assert not (root / "run_server_lan.cmd").exists()
    assert not (root / "scripts" / "run_server_lan.cmd").exists()


def test_scripts_server_script_was_removed_to_keep_one_main_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]

    assert not (root / "scripts" / "run_server.cmd").exists()

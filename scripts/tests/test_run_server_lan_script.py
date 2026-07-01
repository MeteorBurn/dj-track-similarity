from __future__ import annotations

from pathlib import Path


def test_local_server_script_uses_cli_logging_path() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "run_server.cmd"

    text = script.read_text(encoding="utf-8")

    assert 'call ".venv\\Scripts\\activate.bat"' in text
    assert "where dj-sim" in text
    assert "dj-sim serve" in text
    assert "python -m uvicorn" not in text
    assert "Local virtual environment was not found" in text
    assert "dj-sim is not available" in text


def test_lan_server_script_activates_venv_and_binds_to_network() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "run_server_lan.cmd"

    text = script.read_text(encoding="utf-8")

    assert 'call "%PROJECT_ROOT%\\.venv\\Scripts\\activate.bat"' in text
    assert "dj-sim serve" in text
    assert "--host %HOST%" in text
    assert 'set "HOST=0.0.0.0"' in text
    assert 'set "PORT=8765"' in text
    assert "%*" in text
    assert "pause" in text.lower()
    assert not (root / "scripts" / "run_server_lan.cmd").exists()

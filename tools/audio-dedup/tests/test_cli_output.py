from __future__ import annotations

from pathlib import Path
import sys

TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup import cli as cli_module  # noqa: E402

from audio_dedup import core as core_module  # noqa: E402

from audio_dedup import models as models_module  # noqa: E402


def test_main_prints_absolute_report_paths(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_module, "configure_stdio", lambda: None)
    result = models_module.ReportResult(
        json_path=Path("reports/dedup.json"),
        xlsx_path=Path("reports/dedup.xlsx"),
        log_path=Path("reports/dedup.log"),
        payload={"statistics": {}, "rhythm_lab": {}},
        groups=0,
    )
    monkeypatch.setattr(core_module, "run_report", lambda **_kwargs: result)

    assert cli_module.main(["--root", "C:/music"]) == 0

    output = capsys.readouterr().out
    assert f"json={result.json_path.resolve()}" in output
    assert f"xlsx={result.xlsx_path.resolve()}" in output
    assert f"log={result.log_path.resolve()}" in output

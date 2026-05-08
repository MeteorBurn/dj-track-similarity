from typer.testing import CliRunner

import dj_track_similarity.cli as cli


def test_serve_reports_missing_ffmpeg_without_traceback(monkeypatch):
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("ffmpeg is required")))

    result = CliRunner().invoke(cli.app, ["serve"])

    assert result.exit_code == 1
    assert "ffmpeg is required" in result.output
    assert "Traceback" not in result.output

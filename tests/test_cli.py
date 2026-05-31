from typer.testing import CliRunner
import pytest

import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.logging_config import set_analysis_diagnostics_enabled


class _FakeStatus:
    state = "completed"
    total = 3
    processed = 3
    analyzed = 2
    failed = 1
    embedding_key = "multi"
    models = ["sonara", "maest", "mert", "clap"]
    current_model = None
    model_progress = {}
    device = "cpu"
    batch_size = 4
    top_k = 3
    avg_seconds_per_track = 0.5


class _FakeAnalysisManager:
    last_kwargs = {}

    def __init__(self, db):
        self.status = _FakeStatus()

    def create_job(self, **_kwargs):
        type(self).last_kwargs = _kwargs
        return "job-1"

    def run_job(self, _job_id):
        return self.status

    def get(self, _job_id):
        return self.status


class _FakeGenreManager(_FakeAnalysisManager):
    def __init__(self, db):
        self.status = _FakeStatus()
        self.status.embedding_key = "maest"


def test_serve_reports_missing_ffmpeg_without_traceback(monkeypatch):
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("ffmpeg is required")))

    result = CliRunner().invoke(cli.app, ["serve"])

    assert result.exit_code == 1
    assert "ffmpeg is required" in result.output
    assert "Traceback" not in result.output


def test_relocate_library_cli_applies_path_updates(tmp_path):
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "track.wav"
    new_file = new_root / "track.wav"
    old_file.write_bytes(b"audio")
    new_file.write_bytes(b"audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(path=old_file, size=old_file.stat().st_size, mtime=old_file.stat().st_mtime)

    result = CliRunner().invoke(
        cli.app,
        ["relocate-library", str(old_root), str(new_root), "--apply", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert "dry_run=False" in result.output
    assert "tracks_updated=1" in result.output
    assert LibraryDatabase(db_path).get_track(track_id).path == new_file.as_posix()


def test_analyze_cli_does_not_expose_removed_fake_option():
    result = CliRunner().invoke(cli.app, ["analyze", "--fake"])

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_analyze_cli_prints_live_progress_for_default_models(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    db_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(cli.app, ["analyze", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Starting sonara,maest,mert,clap analysis" in result.output
    assert "processed=3/3" in result.output
    assert "tracks/s" in result.output
    assert "eta=" in result.output
    assert "state=completed" in result.output
    assert "models=sonara,maest,mert,clap" in result.output


def test_analyze_cli_accepts_selected_models_and_diagnostics_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    db_path = tmp_path / "library.sqlite"

    try:
        result = CliRunner().invoke(cli.app, ["analyze", "--models", "maest,mert", "--diagnostics", "--db", str(db_path)])
    finally:
        set_analysis_diagnostics_enabled(None)

    assert result.exit_code == 0
    assert "Starting maest,mert analysis" in result.output
    assert _FakeAnalysisManager.last_kwargs["models"] == ["maest", "mert"]


@pytest.mark.parametrize("command", [["analyze", "--adapter", "mert"], ["analyze-genres"], ["analyze-sonara"]])
def test_removed_individual_analysis_cli_paths_are_not_available(command):
    result = CliRunner().invoke(cli.app, command)

    assert result.exit_code != 0
    assert "No such" in result.output

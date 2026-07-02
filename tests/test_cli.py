import logging
import sys
from pathlib import Path

import numpy as np
from typer.testing import CliRunner
import pytest

import dj_track_similarity.api as api
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
    models = ["sonara", "maest", "mert", "muq", "clap"]
    current_model = None
    model_progress = {}
    device = "cpu"
    track_batch_size = 4
    inference_batch_size = 24
    top_k = 3
    avg_seconds_per_track = 0.5


class _FakeAnalysisManager:
    last_kwargs = {}

    def __init__(self, db):
        self.status = _FakeStatus()

    def create_job(self, **_kwargs):
        type(self).last_kwargs = _kwargs
        if "track_batch_size" in _kwargs:
            self.status.track_batch_size = _kwargs["track_batch_size"]
        if "inference_batch_size" in _kwargs:
            self.status.inference_batch_size = _kwargs["inference_batch_size"]
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


def test_serve_passes_bracketed_log_config_to_uvicorn(monkeypatch):
    import uvicorn

    captured = {}
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(api, "create_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "configure_logging", lambda **_kwargs: "app.log")

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = CliRunner().invoke(cli.app, ["serve", "--log-level", "warning"])

    assert result.exit_code == 0
    log_config = captured["kwargs"]["log_config"]
    assert log_config["formatters"]["default"]["format"] == "[%(asctime)s] [%(levelname)s] %(message)s"
    assert log_config["formatters"]["default"]["datefmt"] == "%Y-%m-%d] [%H:%M:%S"
    assert log_config["loggers"]["uvicorn"]["level"] == "WARNING"
    assert log_config["handlers"]["file"]["filename"] == str(Path("app.log").resolve())
    assert log_config["loggers"]["uvicorn.access"]["handlers"] == ["access", "file"]


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


def test_analyze_cli_does_not_accept_legacy_batch_size():
    result = CliRunner().invoke(cli.app, ["analyze", "--batch-size", "4"])

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_analyze_cli_rejects_unknown_device_before_starting_job(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    _FakeAnalysisManager.last_kwargs = {}
    db_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(cli.app, ["analyze", "--device", "gpu", "--db", str(db_path)])

    assert result.exit_code != 0
    assert "Unknown torch device: gpu" in result.output
    assert _FakeAnalysisManager.last_kwargs == {}


def test_analyze_cli_prints_live_progress_for_default_models(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    db_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(cli.app, ["analyze", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Starting sonara,maest,mert,muq,clap analysis" in result.output
    assert "processed=3/3" in result.output
    assert "tracks/s" in result.output
    assert "eta=" in result.output
    assert "state=completed" in result.output
    assert "models=sonara,maest,mert,muq,clap" in result.output


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
    assert _FakeAnalysisManager.last_kwargs["track_batch_size"] == 4
    assert _FakeAnalysisManager.last_kwargs["inference_batch_size"] == 24


def test_analyze_cli_accepts_separate_track_and_inference_batch_sizes(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    db_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze",
            "--models",
            "maest,mert",
            "--track-batch-size",
            "3",
            "--inference-batch-size",
            "12",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert _FakeAnalysisManager.last_kwargs["track_batch_size"] == 3
    assert _FakeAnalysisManager.last_kwargs["inference_batch_size"] == 12
    assert "track_batch_size=3 inference_batch_size=12" in result.output


def test_text_search_cli_rejects_unknown_device_before_loading_adapter(monkeypatch, tmp_path):
    def fail_adapter(**_kwargs):
        raise AssertionError("adapter should not be constructed for invalid device")

    monkeypatch.setattr(cli, "ClapEmbeddingAdapter", fail_adapter)

    result = CliRunner().invoke(cli.app, ["text-search", "dark techno", "--device", "gpu", "--db", str(tmp_path / "library.sqlite")])

    assert result.exit_code != 0
    assert "Unknown torch device: gpu" in result.output


def test_text_search_cli_writes_adapter_stderr_to_app_log(monkeypatch, tmp_path):
    log_path = tmp_path / "app.log"
    db_path = tmp_path / "library.sqlite"
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LOG", str(log_path))

    class FakeClapAdapter:
        embedding_key = "clap"

        def __init__(self, **_kwargs):
            print("CLAP CLI adapter stderr", file=sys.stderr)

        def embed_text(self, _query):
            return np.array([1.0, 0.0], dtype=np.float32)

    monkeypatch.setattr(cli, "ClapEmbeddingAdapter", FakeClapAdapter)

    result = CliRunner().invoke(cli.app, ["text-search", "dark techno", "--db", str(db_path)])

    assert result.exit_code == 0
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()
    assert "CLAP CLI adapter stderr" in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", [["analyze", "--adapter", "mert"], ["analyze-genres"], ["analyze-sonara"]])
def test_removed_individual_analysis_cli_paths_are_not_available(command):
    result = CliRunner().invoke(cli.app, command)

    assert result.exit_code != 0
    assert "No such" in result.output

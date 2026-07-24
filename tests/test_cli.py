from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from typer.testing import CliRunner

import dj_track_similarity.api as api
import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile


class _FakeAnalysisManager:
    last_kwargs: dict[str, object] = {}
    preflight_calls = 0

    def __init__(self, _database: LibraryDatabase) -> None:
        self.status = SimpleNamespace(
            state="completed",
            total=3,
            processed=3,
            analyzed=2,
            failed=1,
            models=["maest", "mert", "muq", "clap"],
            current_model=None,
            model_progress={},
            device="cpu",
            track_batch_size=8,
            inference_batch_size=16,
            sonara_batch_size=8,
            sonara_outputs=[],
            top_k=3,
            avg_seconds_per_track=0.5,
        )

    def validate_sonara_preflight(self) -> None:
        type(self).preflight_calls += 1

    def create_job(self, **kwargs: object) -> str:
        type(self).last_kwargs = dict(kwargs)
        self.status.models = list(kwargs["models"])
        self.status.track_batch_size = int(kwargs["track_batch_size"])
        self.status.inference_batch_size = int(kwargs["inference_batch_size"])
        self.status.sonara_batch_size = int(kwargs["sonara_batch_size"])
        self.status.sonara_outputs = list(kwargs["sonara_outputs"])
        return "job-1"

    def run_job(self, _job_id: str):
        return self.status

    def get(self, _job_id: str):
        return self.status


def _typed_track(database: LibraryDatabase, path: Path):
    path.write_bytes(b"audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="WAV",
        ),
        tags=FileTags(title="Typed CLI Track"),
    ).identity


def test_serve_reports_missing_ffmpeg_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "require_ffmpeg",
        lambda: (_ for _ in ()).throw(RuntimeError("ffmpeg is required")),
    )

    result = CliRunner().invoke(cli.app, ["serve"])

    assert result.exit_code == 1
    assert "ffmpeg is required" in result.output
    assert "Traceback" not in result.output


def test_serve_opens_selected_v7_database_and_passes_log_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import uvicorn

    db_path = tmp_path / "library.sqlite"
    log_path = tmp_path / "app.log"
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda **_kwargs: log_path,
    )
    monkeypatch.setattr(api, "create_app", lambda *args, **kwargs: object())

    def fake_run(application: object, **kwargs: object) -> None:
        captured["application"] = application
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["serve", "--db", str(db_path), "--port", "8877", "--log-level", "warning"],
    )

    assert result.exit_code == 0
    assert LibraryDatabase(db_path).path == db_path.resolve()
    kwargs = captured["kwargs"]
    assert kwargs["port"] == 8877
    log_config = kwargs["log_config"]
    assert log_config["formatters"]["default"]["format"] == "[%(asctime)s] [%(levelname)s] %(message)s"
    assert log_config["handlers"]["file"]["filename"] == str(log_path.resolve())


def test_relocate_library_cli_applies_typed_v7_path_update(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "track.wav"
    new_file = new_root / "track.wav"
    new_file.write_bytes(b"audio")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _typed_track(database, old_file)

    result = CliRunner().invoke(
        cli.app,
        [
            "relocate-library",
            str(old_root),
            str(new_root),
            "--apply",
            "--db",
            str(database.path),
        ],
    )

    assert result.exit_code == 0
    assert "dry_run=False" in result.output
    assert "tracks_updated=1" in result.output
    state = database.get_track_file_state(new_file)
    assert state is not None
    assert (state.track_id, state.track_uuid, state.content_generation) == (
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )


def test_analyze_cli_does_not_expose_removed_fake_or_legacy_batch_options() -> None:
    for arguments in (["analyze", "--fake"], ["analyze", "--batch-size", "4"]):
        result = CliRunner().invoke(cli.app, arguments)

        assert result.exit_code != 0
        assert "No such option" in result.output


def test_analyze_cli_rejects_unknown_device_before_opening_manager(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    _FakeAnalysisManager.last_kwargs = {}

    result = CliRunner().invoke(
        cli.app,
        ["analyze", "--device", "gpu", "--db", str(tmp_path / "library.sqlite")],
    )

    assert result.exit_code != 0
    assert "Unknown torch device: gpu" in result.output
    assert _FakeAnalysisManager.last_kwargs == {}


def test_analyze_cli_prints_default_ml_progress_and_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    _FakeAnalysisManager.last_kwargs = {}

    result = CliRunner().invoke(
        cli.app,
        ["analyze", "--db", str(tmp_path / "library.sqlite")],
    )

    assert result.exit_code == 0
    assert "Starting maest,mert,muq,clap analysis" in result.output
    assert "processed=3/3" in result.output
    assert "tracks/s" in result.output
    assert "eta=" in result.output
    assert "state=completed" in result.output
    assert "models=maest,mert,muq,clap" in result.output
    assert "sonara_batch_size" not in result.output
    assert _FakeAnalysisManager.last_kwargs["sonara_outputs"] == []


def test_analyze_cli_uses_exact_sonara_outputs_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)
    _FakeAnalysisManager.last_kwargs = {}
    _FakeAnalysisManager.preflight_calls = 0

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze",
            "--models",
            "sonara",
            "--sonara-outputs",
            "timeline,embedding,fingerprint",
            "--db",
            str(tmp_path / "library.sqlite"),
        ],
    )

    assert result.exit_code == 0
    assert _FakeAnalysisManager.preflight_calls == 1
    assert _FakeAnalysisManager.last_kwargs["sonara_outputs"] == [
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    ]
    assert "sonara_outputs=core,timeline,embedding,fingerprint sonara_batch_size=8" in result.output
    assert "representations" not in result.output


def test_analyze_cli_rejects_removed_representations_before_opening_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze",
            "--models",
            "sonara",
            "--sonara-outputs",
            "representations",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "representations" in result.output
    assert not db_path.exists()


def test_analyze_cli_passes_separate_ml_batch_sizes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "AnalysisJobManager", _FakeAnalysisManager)

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
            str(tmp_path / "library.sqlite"),
        ],
    )

    assert result.exit_code == 0
    assert _FakeAnalysisManager.last_kwargs["track_batch_size"] == 3
    assert _FakeAnalysisManager.last_kwargs["inference_batch_size"] == 12
    assert "track_batch_size=3 inference_batch_size=12" in result.output


def test_text_search_cli_rejects_unknown_device_before_loading_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cli,
        "ClapEmbeddingAdapter",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("adapter should not be constructed")
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        ["text-search", "dark techno", "--device", "gpu", "--db", str(tmp_path / "library.sqlite")],
    )

    assert result.exit_code != 0
    assert "Unknown torch device: gpu" in result.output


def test_text_search_cli_writes_adapter_stderr_to_app_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "app.log"
    db_path = tmp_path / "library.sqlite"
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LOG", str(log_path))

    class FakeClapAdapter:
        embedding_key = "clap"

        def __init__(self, **_kwargs: object) -> None:
            print("CLAP CLI adapter stderr", file=sys.stderr)

        def embed_text(self, _query: str) -> np.ndarray:
            return np.array([1.0, 0.0], dtype=np.float32)

    class FakeSearch:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def search_vector(self, *_args: object, **_kwargs: object) -> list[object]:
            return []

    monkeypatch.setattr(cli, "ClapEmbeddingAdapter", FakeClapAdapter)
    monkeypatch.setattr(cli, "embedding_analysis_output", lambda *_args: object())
    monkeypatch.setattr(cli, "SimilaritySearch", FakeSearch)

    result = CliRunner().invoke(
        cli.app,
        ["text-search", "dark techno", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()
    assert "CLAP CLI adapter stderr" in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "command",
    [
        ["analyze", "--adapter", "mert"],
        ["analyze-genres"],
        ["analyze-sonara"],
    ],
)
def test_removed_individual_analysis_cli_paths_are_not_available(
    command: list[str],
) -> None:
    result = CliRunner().invoke(cli.app, command)

    assert result.exit_code != 0
    assert "No such" in result.output

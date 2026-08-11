from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.db_structure import inspect_database_structure


def _artifacts_path(core_path: Path) -> Path:
    return core_path.with_suffix(".artifacts.sqlite")


def _assert_database_bundle(core_path: Path) -> None:
    artifacts_path = _artifacts_path(core_path)
    assert core_path.is_file()
    assert artifacts_path.is_file()
    with sqlite3.connect(core_path) as core_connection:
        assert inspect_database_structure(core_connection, "core").is_current
    with sqlite3.connect(artifacts_path) as artifacts_connection:
        assert inspect_database_structure(
            artifacts_connection,
            "artifacts",
        ).is_current
    assert not core_path.with_suffix(".timeline.sqlite").exists()
    assert not core_path.with_suffix(".representations.sqlite").exists()


def test_root_help_exposes_current_commands() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "current library bundles" in result.output
    for command in (
        "scan",
        "analyze",
        "analyze-classifier",
        "analyze-pipeline",
        "text-search",
        "serve",
        "eval",
        "index",
        "relocate-library",
        "doctor",
        "migrate-database",
    ):
        assert command in result.output
    assert "analyze-classifiers" not in result.output


def test_scan_bootstraps_bound_current_bundle(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    core_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(
        cli.app,
        ["scan", str(music_root), "--db", str(core_path)],
    )

    assert result.exit_code == 0
    assert "added=0 updated=0 unchanged=0 skipped=0" in result.output
    _assert_database_bundle(core_path)


def test_scan_rejects_incomplete_database_without_creating_artifacts(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    core_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(core_path) as connection:
        connection.executescript(
            """
            CREATE TABLE sentinel(value TEXT NOT NULL);
            INSERT INTO sentinel(value) VALUES ('preserve-me');
            """
        )
        connection.commit()

    result = CliRunner().invoke(
        cli.app,
        ["scan", str(music_root), "--db", str(core_path)],
    )

    assert result.exit_code == 1
    assert "Cannot open library database bundle" in result.output
    assert "migrate-database" in result.output
    assert not _artifacts_path(core_path).exists()
    with sqlite3.connect(core_path) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )


def test_analyze_opens_current_bundle_for_sonara_core_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    captured: dict[str, object] = {}

    class FakeAnalysisManager:
        def __init__(self, database) -> None:
            captured["database"] = database

        def create_job(self, **kwargs: object) -> str:
            captured["kwargs"] = kwargs
            return "analysis-job"

        def run_job(self, job_id: str):
            assert job_id == "analysis-job"
            return SimpleNamespace(
                state="completed",
                total=0,
                processed=0,
                analyzed=0,
                failed=0,
                models=["sonara"],
                device=None,
                top_k=3,
                track_batch_size=8,
                inference_batch_size=16,
                sonara_batch_size=8,
            )

        def get(self, job_id: str):
            return self.run_job(job_id)

    monkeypatch.setattr(cli, "AnalysisJobManager", FakeAnalysisManager)

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze",
            "--models",
            "sonara",
            "--db",
            str(core_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["database"].path == core_path.resolve()
    assert "sonara_outputs" not in captured["kwargs"]
    _assert_database_bundle(core_path)


def test_index_help_uses_model_family_not_embedding_key() -> None:
    for command in ("build", "verify", "benchmark", "clear"):
        result = CliRunner().invoke(cli.app, ["index", command, "--help"])

        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--embedding-key" not in result.output
        assert "--adapter" not in result.output


def test_index_clear_opens_selected_current_bundle(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    index_dir = tmp_path / "indexes"

    result = CliRunner().invoke(
        cli.app,
        [
            "index",
            "clear",
            "--model",
            "clap",
            "--db",
            str(core_path),
            "--index-dir",
            str(index_dir),
        ],
    )

    assert result.exit_code == 0
    assert "status=ok model=clap deleted=0" in result.output
    _assert_database_bundle(core_path)


def test_serve_preflights_selected_current_bundle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import uvicorn

    from dj_track_similarity import api as api_module

    core_path = tmp_path / "library.sqlite"
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        cli,
        "configure_logging",
        lambda **_kwargs: tmp_path / "app.log",
    )

    def fake_create_app(db_path: Path, **kwargs: object) -> object:
        captured["db_path"] = db_path
        captured["app_kwargs"] = kwargs
        return object()

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured["run_kwargs"] = kwargs

    monkeypatch.setattr(api_module, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["serve", "--db", str(core_path), "--port", "8877"],
    )

    assert result.exit_code == 0
    assert captured["db_path"] == core_path.resolve()
    assert captured["run_kwargs"]["port"] == 8877
    _assert_database_bundle(core_path)

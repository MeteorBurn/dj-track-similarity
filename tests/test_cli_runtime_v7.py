from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import dj_track_similarity.cli as cli


CORE_SCHEMA_VERSION = 7
ARTIFACTS_SCHEMA_VERSION = 1


def _artifacts_path(core_path: Path) -> Path:
    return core_path.with_suffix(".artifacts.sqlite")


def _schema_version(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _assert_v7_bundle(core_path: Path) -> None:
    artifacts_path = _artifacts_path(core_path)
    assert core_path.is_file()
    assert artifacts_path.is_file()
    assert _schema_version(core_path) == CORE_SCHEMA_VERSION
    assert _schema_version(artifacts_path) == ARTIFACTS_SCHEMA_VERSION
    assert not core_path.with_suffix(".timeline.sqlite").exists()
    assert not core_path.with_suffix(".representations.sqlite").exists()


def test_root_help_exposes_v7_commands_without_migration() -> None:
    result = CliRunner().invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "greenfield v7 library bundles" in result.output
    for command in (
        "scan",
        "analyze",
        "analyze-classifiers",
        "analyze-classifier",
        "analyze-pipeline",
        "text-search",
        "serve",
        "prepare-sonara-release",
        "eval",
        "index",
        "relocate-library",
        "doctor",
    ):
        assert command in result.output
    assert "migrate-schema-v7" not in result.output
    assert "v6" not in result.output.lower()


def test_scan_bootstraps_bound_v7_bundle(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    core_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(
        cli.app,
        ["scan", str(music_root), "--db", str(core_path)],
    )

    assert result.exit_code == 0
    assert "added=0 updated=0 unchanged=0 skipped=0" in result.output
    _assert_v7_bundle(core_path)


def test_scan_rejects_legacy_database_without_creating_artifacts(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    core_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(core_path) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 6;
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
    assert "Cannot open v7 library database bundle" in result.output
    assert not _artifacts_path(core_path).exists()
    with sqlite3.connect(core_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )


def test_analyze_opens_v7_bundle_and_uses_canonical_output_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    captured: dict[str, object] = {}

    class FakeAnalysisManager:
        def __init__(self, database) -> None:
            captured["database"] = database

        def validate_sonara_preflight(self) -> None:
            captured["preflight"] = True

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
                sonara_outputs=[
                    "core",
                    "timeline",
                    "embedding",
                    "fingerprint",
                ],
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
            "--sonara-outputs",
            "core,timeline,embedding,fingerprint",
            "--db",
            str(core_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["database"].path == core_path.resolve()
    assert captured["preflight"] is True
    assert captured["kwargs"]["sonara_outputs"] == [
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    ]
    assert "representations" not in result.output
    _assert_v7_bundle(core_path)


def test_analyze_rejects_removed_representations_output_before_opening_database(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze",
            "--models",
            "sonara",
            "--sonara-outputs",
            "representations",
            "--db",
            str(core_path),
        ],
    )

    assert result.exit_code != 0
    assert "representations" in result.output
    assert not core_path.exists()
    assert not _artifacts_path(core_path).exists()


def test_prepare_sonara_release_help_has_no_raw_identity_options() -> None:
    result = CliRunner().invoke(
        cli.app,
        ["prepare-sonara-release", "--help"],
    )

    assert result.exit_code == 0
    assert "--db" in result.output
    assert "--backup-dir" in result.output
    assert "--confirm" in result.output
    assert "--new-release-hash" not in result.output
    assert "--previous-release-hash" not in result.output
    assert "--sonara-outputs" not in result.output


def test_prepare_sonara_release_uses_selected_v7_database(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from dj_track_similarity import prepare_sonara_release as prepare_module

    core_path = tmp_path / "library.sqlite"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    captured: dict[str, object] = {}

    def fake_prepare(database, *, backup_dir: Path, confirm: str):
        captured["database"] = database
        captured["backup_dir"] = backup_dir
        captured["confirm"] = confirm
        return {
            "stage": "completed",
            "release_hash": "sha256:" + ("a" * 64),
            "completed_at": "2026-07-24T00:00:00.000000Z",
        }

    monkeypatch.setattr(
        prepare_module,
        "prepare_sonara_release",
        fake_prepare,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "prepare-sonara-release",
            "--db",
            str(core_path),
            "--backup-dir",
            str(backup_dir),
            "--confirm",
            "PREPARE SONARA RELEASE",
        ],
    )

    assert result.exit_code == 0
    assert captured["database"].path == core_path.resolve()
    assert captured["backup_dir"] == backup_dir
    assert captured["confirm"] == "PREPARE SONARA RELEASE"
    assert "status=ok stage=completed" in result.output
    _assert_v7_bundle(core_path)


def test_index_help_uses_model_family_not_embedding_key() -> None:
    for command in ("build", "verify", "benchmark", "clear"):
        result = CliRunner().invoke(cli.app, ["index", command, "--help"])

        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--embedding-key" not in result.output
        assert "--adapter" not in result.output


def test_index_clear_opens_selected_v7_bundle(tmp_path: Path) -> None:
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
    _assert_v7_bundle(core_path)


def test_serve_preflights_selected_v7_bundle(
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
    _assert_v7_bundle(core_path)

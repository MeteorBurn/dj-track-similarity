from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase


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

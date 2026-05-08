import pytest

from dj_track_similarity.dependencies import require_ffmpeg


def test_require_ffmpeg_raises_clear_error_when_missing(monkeypatch):
    monkeypatch.setattr("dj_track_similarity.dependencies.shutil.which", lambda name: None)

    with pytest.raises(RuntimeError, match="ffmpeg is required"):
        require_ffmpeg()


def test_require_ffmpeg_accepts_path_from_lookup(monkeypatch):
    monkeypatch.setattr("dj_track_similarity.dependencies.shutil.which", lambda name: "/tools/ffmpeg")

    assert require_ffmpeg() == "/tools/ffmpeg"

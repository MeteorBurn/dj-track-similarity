from __future__ import annotations

import os
from pathlib import Path

import pytest

import dj_track_similarity.ffmpeg_runtime as ffmpeg_runtime
from dj_track_similarity.ffmpeg_runtime import (
    FFMPEG_SHARED_DIR_ENV_VAR,
    configure_shared_ffmpeg_runtime,
)


def _write_required_libraries(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for component, major in ffmpeg_runtime.REQUIRED_FFMPEG_LIBRARIES.items():
        (directory / f"{component}-{major}.dll").touch()


def test_configure_shared_runtime_prefers_explicit_environment_over_path(
    monkeypatch, tmp_path: Path
) -> None:
    explicit_runtime = tmp_path / "explicit"
    _write_required_libraries(explicit_runtime)
    path_runtime = tmp_path / "path"
    _write_required_libraries(path_runtime)
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(explicit_runtime))
    monkeypatch.setenv("PATH", str(path_runtime))
    monkeypatch.setattr(
        ffmpeg_runtime,
        "_ffmpeg_release_version",
        lambda directory: ffmpeg_runtime.REQUIRED_FFMPEG_VERSION,
    )
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == explicit_runtime
    assert registered == [str(explicit_runtime)]


def test_configure_shared_runtime_registers_path_dll_directory(monkeypatch, tmp_path: Path) -> None:
    _write_required_libraries(tmp_path)
    monkeypatch.delenv(FFMPEG_SHARED_DIR_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(
        ffmpeg_runtime,
        "_ffmpeg_release_version",
        lambda directory: ffmpeg_runtime.REQUIRED_FFMPEG_VERSION,
    )
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == tmp_path
    assert registered == [str(tmp_path)]


def test_configure_shared_runtime_rejects_explicit_directory_without_ffmpeg_dlls(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(tmp_path))

    with pytest.raises(RuntimeError, match="FFmpeg 8.1.1 full shared build is required"):
        configure_shared_ffmpeg_runtime()

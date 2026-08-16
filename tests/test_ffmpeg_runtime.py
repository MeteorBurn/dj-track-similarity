from __future__ import annotations

import os
from pathlib import Path

import pytest

import dj_track_similarity.ffmpeg_runtime as ffmpeg_runtime
from dj_track_similarity.ffmpeg_runtime import (
    FFMPEG_SHARED_DIR_ENV_VAR,
    configure_shared_ffmpeg_runtime,
)


def test_configure_shared_runtime_prefers_project_libs_over_environment(
    monkeypatch, tmp_path: Path
) -> None:
    project_runtime = tmp_path / "libs" / "ffmpeg"
    project_runtime.mkdir(parents=True)
    (project_runtime / "avcodec-63.dll").touch()
    environment_runtime = tmp_path / "environment"
    environment_runtime.mkdir()
    (environment_runtime / "avcodec-62.dll").touch()
    monkeypatch.setattr(ffmpeg_runtime, "PROJECT_FFMPEG_SHARED_DIR", project_runtime)
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(environment_runtime))
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == project_runtime
    assert registered == [str(project_runtime)]


def test_configure_shared_runtime_registers_explicit_dll_directory(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "avcodec-63.dll").touch()
    monkeypatch.setattr(ffmpeg_runtime, "PROJECT_FFMPEG_SHARED_DIR", tmp_path / "missing")
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(tmp_path))
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == tmp_path
    assert registered == [str(tmp_path)]


def test_configure_shared_runtime_rejects_explicit_directory_without_ffmpeg_dlls(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg_runtime, "PROJECT_FFMPEG_SHARED_DIR", tmp_path / "missing")
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(tmp_path))

    with pytest.raises(RuntimeError, match="shared FFmpeg"):
        configure_shared_ffmpeg_runtime()

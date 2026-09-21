from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import dj_track_similarity.audio.ffmpeg_runtime as ffmpeg_runtime
from dj_track_similarity.audio.ffmpeg_runtime import (
    FFMPEG_SHARED_DIR_ENV_VAR,
    configure_shared_ffmpeg_runtime,
)


def _write_required_libraries(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for component, major in ffmpeg_runtime.REQUIRED_FFMPEG_LIBRARIES.items():
        (directory / f"{component}-{major}.dll").touch()


@pytest.fixture(autouse=True)
def _no_executable_probe(monkeypatch, tmp_path: Path):
    def forbidden_process(*_args, **_kwargs):
        pytest.fail("FFmpeg runtime validation must use shared libraries, not an executable")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    monkeypatch.setattr(ffmpeg_runtime, "_PROJECT_FFMPEG_DIRECTORY", tmp_path / "project")
    monkeypatch.setattr(ffmpeg_runtime, "_DLL_DIRECTORY_HANDLES", {})
    monkeypatch.setattr(ffmpeg_runtime, "_RESOLVED_DIRECTORIES", {})


def _mock_avutil(monkeypatch, version: bytes = b"8.1.1-full_build") -> list[Path]:
    loaded = []

    def version_info():
        return version

    def load_library(path):
        loaded.append(Path(path))
        return SimpleNamespace(av_version_info=version_info)

    monkeypatch.setattr(ffmpeg_runtime.ctypes, "CDLL", load_library)
    return loaded


def test_configure_shared_runtime_prefers_explicit_environment_over_path(
    monkeypatch, tmp_path: Path
) -> None:
    explicit_runtime = tmp_path / "explicit"
    _write_required_libraries(explicit_runtime)
    path_runtime = tmp_path / "path"
    _write_required_libraries(path_runtime)
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(explicit_runtime))
    monkeypatch.setenv("PATH", str(path_runtime))
    loaded = _mock_avutil(monkeypatch)
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == explicit_runtime
    assert registered == [str(explicit_runtime)]
    assert loaded == [explicit_runtime / "avutil-60.dll"]


def test_configure_shared_runtime_prefers_the_libraries_shipped_with_the_project(
    monkeypatch, tmp_path: Path
) -> None:
    _write_required_libraries(tmp_path)
    project_runtime = ffmpeg_runtime._PROJECT_FFMPEG_DIRECTORY
    _write_required_libraries(project_runtime)
    monkeypatch.delenv(FFMPEG_SHARED_DIR_ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    loaded = _mock_avutil(monkeypatch)
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == project_runtime
    assert registered == [str(project_runtime)]
    assert loaded == [project_runtime / "avutil-60.dll"]

    # The resolution is cached against the environment, so a runtime that leaves
    # the disk is only noticed by a fresh resolution.
    shutil.rmtree(project_runtime)
    ffmpeg_runtime._RESOLVED_DIRECTORIES.clear()
    assert configure_shared_ffmpeg_runtime() == tmp_path
    assert registered == [str(project_runtime), str(tmp_path)]
    assert loaded == [project_runtime / "avutil-60.dll", tmp_path / "avutil-60.dll"]


@pytest.mark.parametrize("failure", ["missing", "wrong-version", "unloadable"])
def test_configure_shared_runtime_rejects_invalid_explicit_shared_libraries(
    monkeypatch, tmp_path: Path, failure: str,
) -> None:
    monkeypatch.setenv(FFMPEG_SHARED_DIR_ENV_VAR, str(tmp_path))
    if failure != "missing":
        _write_required_libraries(tmp_path)
    if failure == "wrong-version":
        _mock_avutil(monkeypatch, b"8.1.0-full_build")

    with pytest.raises(RuntimeError, match="FFmpeg 8.1.1 shared libraries are required"):
        configure_shared_ffmpeg_runtime()

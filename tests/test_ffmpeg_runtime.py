from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import dj_track_similarity.audio.ffmpeg_runtime as ffmpeg_runtime
from dj_track_similarity.audio.ffmpeg_runtime import configure_shared_ffmpeg_runtime


def _write_required_libraries(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for component, major in ffmpeg_runtime.REQUIRED_FFMPEG_LIBRARIES.items():
        (directory / f"{component}-{major}.dll").touch()


@pytest.fixture(autouse=True)
def _no_executable_probe(monkeypatch, tmp_path: Path):
    def forbidden_process(*_args, **_kwargs):
        pytest.fail("FFmpeg runtime validation must use shared libraries, not an executable")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    monkeypatch.delenv("DJTS_FFMPEG", raising=False)
    monkeypatch.setattr(ffmpeg_runtime, "_PROJECT_FFMPEG_DIRECTORY", tmp_path / "project")
    monkeypatch.setattr(ffmpeg_runtime, "_DLL_DIRECTORY_HANDLES", {})
    monkeypatch.setattr(ffmpeg_runtime, "_DLL_LIBRARY_HANDLES", {})
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


@pytest.mark.parametrize("with_avdevice", [False, True])
def test_configure_shared_runtime_preloads_libraries_once(
    monkeypatch, with_avdevice: bool,
) -> None:
    project_runtime = ffmpeg_runtime._PROJECT_FFMPEG_DIRECTORY
    _write_required_libraries(project_runtime)
    avdevice_path = project_runtime / "avdevice-62.dll"
    if with_avdevice:
        avdevice_path.touch()
    else:
        avdevice_path.unlink(missing_ok=True)
    monkeypatch.setenv("PATH", "")
    loaded = _mock_avutil(monkeypatch)
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == project_runtime
    assert registered == [str(project_runtime)]
    expected_libraries = {
        project_runtime / name
        for name in (
            "avutil-60.dll", "swresample-6.dll", "swscale-9.dll", "avcodec-62.dll",
            "avformat-62.dll", "avfilter-11.dll",
        )
    }
    if with_avdevice:
        expected_libraries.add(avdevice_path)
    assert set(loaded) == expected_libraries
    # Later consumers may register a competing DLL directory (TorchCodec does
    # this for ffmpeg.exe on PATH); our whole runtime must already be loaded.
    loaded_before_repeat = loaded.copy()
    assert configure_shared_ffmpeg_runtime() == project_runtime
    assert registered == [str(project_runtime)]
    assert loaded == loaded_before_repeat


def test_configure_shared_runtime_prefers_project_then_environment_then_path(
    monkeypatch, tmp_path: Path
) -> None:
    _write_required_libraries(tmp_path)
    project_runtime = ffmpeg_runtime._PROJECT_FFMPEG_DIRECTORY
    _write_required_libraries(project_runtime)
    configured_runtime = tmp_path / "configured"
    _write_required_libraries(configured_runtime)
    monkeypatch.setenv("DJTS_FFMPEG", str(configured_runtime))
    monkeypatch.setenv("PATH", str(tmp_path))
    loaded = _mock_avutil(monkeypatch)
    registered: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", registered.append)

    assert configure_shared_ffmpeg_runtime() == project_runtime
    assert registered == [str(project_runtime)]
    assert set(loaded) == {
        project_runtime / f"{component}-{major}.dll"
        for component, major in ffmpeg_runtime.REQUIRED_FFMPEG_LIBRARIES.items()
    }

    # The resolution is cached against the environment, so a runtime that leaves
    # the disk is only noticed by a fresh resolution.
    shutil.rmtree(project_runtime)
    ffmpeg_runtime._RESOLVED_DIRECTORIES.clear()
    assert configure_shared_ffmpeg_runtime() == configured_runtime
    assert registered == [str(project_runtime), str(configured_runtime)]

    # A changed setting must invalidate resolution, and an unavailable directory
    # must leave the PATH fallback usable.
    monkeypatch.setenv("DJTS_FFMPEG", str(tmp_path / "unavailable"))
    assert configure_shared_ffmpeg_runtime() == tmp_path
    assert registered == [str(project_runtime), str(configured_runtime), str(tmp_path)]
    assert set(loaded) == {
        directory / f"{component}-{major}.dll"
        for directory in (project_runtime, configured_runtime, tmp_path)
        for component, major in ffmpeg_runtime.REQUIRED_FFMPEG_LIBRARIES.items()
    }


@pytest.mark.parametrize("failure", ["missing", "wrong-version", "unloadable"])
def test_configure_shared_runtime_rejects_invalid_path_shared_libraries(
    monkeypatch, tmp_path: Path, failure: str,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    if failure != "missing":
        _write_required_libraries(tmp_path)
    if failure == "wrong-version":
        _mock_avutil(monkeypatch, b"8.1.0-full_build")

    with pytest.raises(RuntimeError, match="FFmpeg 8.1.1 shared libraries are required"):
        configure_shared_ffmpeg_runtime()

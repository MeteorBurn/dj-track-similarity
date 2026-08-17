from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType


FFMPEG_SHARED_DIR_ENV_VAR = "DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR"
PROJECT_FFMPEG_SHARED_DIR = Path(__file__).resolve().parents[2] / "libs" / "ffmpeg" / "bin"
PROJECT_PYAV_SITE_PACKAGES = (
    Path(__file__).resolve().parents[2] / "libs" / "pyav" / "Lib" / "site-packages"
)
_DLL_DIRECTORY_HANDLES: list[object] = []
_AVCODEC_LIBRARY_PATTERNS = ("avcodec-*.dll", "libavcodec.so*", "libavcodec.*.dylib")


def configure_shared_ffmpeg_runtime() -> Path:
    """Find and register a shared FFmpeg directory for this Python process."""

    directory = _configured_or_path_shared_directory()
    if directory is None:
        raise RuntimeError(
            "A shared FFmpeg runtime is required. Install a shared FFmpeg build and add its "
            f"library directory to PATH, or set {FFMPEG_SHARED_DIR_ENV_VAR} to that directory. "
            "ffmpeg.exe alone is not sufficient."
        )
    if os.name == "nt":
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
    return directory


def load_project_pyav() -> ModuleType:
    """Load the project-bundled PyAV binding against the registered FFmpeg DLLs."""

    configure_shared_ffmpeg_runtime()
    if not PROJECT_PYAV_SITE_PACKAGES.is_dir():
        raise RuntimeError(
            "The project PyAV runtime is required at "
            f"{PROJECT_PYAV_SITE_PACKAGES}"
        )
    site_packages = str(PROJECT_PYAV_SITE_PACKAGES)
    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)
    return import_module("av")


def _configured_or_path_shared_directory() -> Path | None:
    if _contains_avcodec_library(PROJECT_FFMPEG_SHARED_DIR):
        return PROJECT_FFMPEG_SHARED_DIR

    configured = os.environ.get(FFMPEG_SHARED_DIR_ENV_VAR)
    if configured:
        directory = Path(configured)
        if _contains_avcodec_library(directory):
            return directory
        raise RuntimeError(
            f"{FFMPEG_SHARED_DIR_ENV_VAR} must point to a directory containing shared FFmpeg "
            f"libraries, but it does not: {configured}"
        )

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        directory = Path(entry)
        if _contains_avcodec_library(directory):
            return directory
    return None


def _contains_avcodec_library(directory: Path) -> bool:
    return directory.is_dir() and any(
        any(directory.glob(pattern)) for pattern in _AVCODEC_LIBRARY_PATTERNS
    )

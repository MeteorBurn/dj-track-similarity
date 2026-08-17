from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType


FFMPEG_SHARED_DIR_ENV_VAR = "DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR"
REQUIRED_FFMPEG_VERSION = "8.1.1"
REQUIRED_FFMPEG_LIBRARIES = {
    "avcodec": 62,
    "avformat": 62,
    "avutil": 60,
    "avfilter": 11,
    "swresample": 6,
    "swscale": 9,
}
REQUIRED_PYAV_VERSION = "17.1.0"
_DLL_DIRECTORY_HANDLES: list[object] = []


@dataclass(frozen=True)
class AudioRuntimeInfo:
    ffmpeg_directory: Path
    ffmpeg_version: str
    ffmpeg_libraries: tuple[tuple[str, str], ...]
    pyav_version: str
    pyav_module_path: Path
    pyav_avcodec_version: tuple[int, ...]


def configure_shared_ffmpeg_runtime() -> Path:
    """Find and register the required FFmpeg 8.1.1 full shared runtime."""

    directory = _configured_or_path_shared_directory()
    if os.name == "nt":
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
    return directory


def inspect_audio_runtime() -> AudioRuntimeInfo:
    """Validate the FFmpeg and PyAV runtime used by audio recovery."""

    directory = configure_shared_ffmpeg_runtime()
    av = load_project_pyav()
    module_path = Path(str(getattr(av, "__file__", ""))).resolve()
    environment_root = Path(sys.prefix).resolve()
    if not module_path.is_relative_to(environment_root):
        raise RuntimeError(
            "PyAV must be imported from the active Python environment, but loaded from "
            f"{module_path}"
        )

    actual_version = str(getattr(av, "__version__", "unknown"))
    if actual_version != REQUIRED_PYAV_VERSION:
        raise RuntimeError(
            f"PyAV {REQUIRED_PYAV_VERSION} is required, but found {actual_version} at {module_path}"
        )

    library_versions = getattr(av, "library_versions", {})
    avcodec_version = tuple(int(part) for part in library_versions.get("libavcodec", ()))
    expected_avcodec = REQUIRED_FFMPEG_LIBRARIES["avcodec"]
    if not avcodec_version or avcodec_version[0] != expected_avcodec:
        raise RuntimeError(
            "PyAV must use FFmpeg 8.1.1 (libavcodec "
            f"{expected_avcodec}), but reported {avcodec_version or 'unknown'}"
        )

    return AudioRuntimeInfo(
        ffmpeg_directory=directory,
        ffmpeg_version=_ffmpeg_release_version(directory),
        ffmpeg_libraries=tuple(_required_library_paths(directory).items()),
        pyav_version=actual_version,
        pyav_module_path=module_path,
        pyav_avcodec_version=avcodec_version,
    )


def load_project_pyav() -> ModuleType:
    """Load the pinned PyAV package from the active Python environment."""

    configure_shared_ffmpeg_runtime()
    try:
        return import_module("av")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            f"PyAV {REQUIRED_PYAV_VERSION} is required in the active Python environment. "
            "Install the project dependencies."
        ) from error


def _configured_or_path_shared_directory() -> Path:
    rejected: list[str] = []
    configured = os.environ.get(FFMPEG_SHARED_DIR_ENV_VAR)
    if configured:
        configured_runtime = _validated_candidate(
            Path(configured),
            FFMPEG_SHARED_DIR_ENV_VAR,
            rejected,
        )
        if configured_runtime is not None:
            return configured_runtime
        raise RuntimeError(_missing_runtime_message(rejected))

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        path_runtime = _validated_candidate(Path(entry), "PATH", rejected)
        if path_runtime is not None:
            return path_runtime
    raise RuntimeError(_missing_runtime_message(rejected))


def _validated_candidate(directory: Path, source: str, rejected: list[str]) -> Path | None:
    if not directory.is_dir():
        return None
    library_paths = _required_library_paths(directory)
    if len(library_paths) != len(REQUIRED_FFMPEG_LIBRARIES):
        if _contains_any_ffmpeg_library(directory):
            missing = sorted(set(REQUIRED_FFMPEG_LIBRARIES) - set(library_paths))
            rejected.append(f"{source}={directory} missing {', '.join(missing)}")
        return None
    try:
        version = _ffmpeg_release_version(directory)
    except RuntimeError as error:
        rejected.append(f"{source}={directory} {error}")
        return None
    if version != REQUIRED_FFMPEG_VERSION:
        rejected.append(f"{source}={directory} version {version}")
        return None
    return directory


def _missing_runtime_message(rejected: list[str]) -> str:
    required = ", ".join(
        f"{component} {major}" for component, major in REQUIRED_FFMPEG_LIBRARIES.items()
    )
    detail = f" Rejected candidates: {'; '.join(rejected)}." if rejected else ""
    return (
        f"FFmpeg {REQUIRED_FFMPEG_VERSION} full shared build is required "
        f"({required}). Put its library directory on PATH, set "
        f"{FFMPEG_SHARED_DIR_ENV_VAR}. "
        f"ffmpeg.exe alone is not sufficient.{detail}"
    )


def _ffmpeg_release_version(directory: Path) -> str:
    executable = directory / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not executable.is_file():
        raise RuntimeError("does not contain ffmpeg executable for version verification")
    completed = subprocess.run(
        [str(executable), "-version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("ffmpeg -version failed")
    match = re.search(r"^ffmpeg version ([^\s]+)", completed.stdout, re.MULTILINE)
    if match is None:
        raise RuntimeError("ffmpeg -version did not report a version")
    version = match.group(1)
    return version.split("-", maxsplit=1)[0]


def _required_library_paths(directory: Path) -> dict[str, str]:
    paths: dict[str, str] = {}
    for component, major in REQUIRED_FFMPEG_LIBRARIES.items():
        library_path = directory / _shared_library_name(component, major)
        if library_path.is_file():
            paths[component] = str(library_path)
    return paths


def _shared_library_name(component: str, major: int) -> str:
    if os.name == "nt":
        return f"{component}-{major}.dll"
    if sys.platform == "darwin":
        return f"lib{component}.{major}.dylib"
    return f"lib{component}.so.{major}"


def _contains_any_ffmpeg_library(directory: Path) -> bool:
    if os.name == "nt":
        return any(directory.glob("avcodec-*.dll"))
    if sys.platform == "darwin":
        return any(directory.glob("libavcodec.*.dylib"))
    return any(directory.glob("libavcodec.so*"))

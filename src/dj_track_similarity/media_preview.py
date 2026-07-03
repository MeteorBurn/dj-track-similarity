from __future__ import annotations

import logging
import subprocess
import tempfile
import wave
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}
BROWSER_PREVIEW_TRANSCODE_SUFFIXES = AIFF_PREVIEW_SUFFIXES | {
    ".dff",
    ".dsd",
    ".dsf",
    ".flac",
    ".ape",
    ".wv",
    ".m4b",
    ".m4r",
    ".tak",
    ".tta",
    ".wma",
}
BROWSER_SAFE_WAV_SAMPLE_WIDTH = 2


class AudioPreviewError(RuntimeError):
    """Raised when an audio preview response cannot be prepared."""


def requires_browser_preview_transcode(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BROWSER_PREVIEW_TRANSCODE_SUFFIXES:
        return True
    if suffix == ".wav":
        return not _is_browser_safe_wav(path)
    return False


def transcoded_wav_file_response(path: Path, ffmpeg_path: str) -> FileResponse:
    with tempfile.NamedTemporaryFile(prefix="dj-sim-preview-", suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    command = [
        ffmpeg_path,
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "wav",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(temp_path),
    ]
    try:
        subprocess.run(command, stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        _delete_temp_file(temp_path)
        message = _preview_error_message(error)
        LOGGER.warning("ffmpeg preview transcode failed path=%s error=%s", path, message)
        raise AudioPreviewError(message) from error
    return FileResponse(
        temp_path,
        media_type="audio/wav",
        filename=f"{path.stem}.wav",
        content_disposition_type="inline",
        background=BackgroundTask(_delete_temp_file, temp_path),
    )


def _preview_error_message(error: OSError | subprocess.CalledProcessError) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        stderr = _decode_stderr(error.stderr)
        detail = stderr or f"ffmpeg exited with status {error.returncode}"
        return f"Audio preview failed: {detail}"
    return f"Audio preview failed: {error}"


def _decode_stderr(stderr: object) -> str:
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    if isinstance(stderr, str):
        return stderr.strip()
    return ""


def _is_browser_safe_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as audio:
            return (
                audio.getsampwidth() == BROWSER_SAFE_WAV_SAMPLE_WIDTH
                and audio.getnchannels() > 0
                and audio.getframerate() > 0
            )
    except (EOFError, OSError, wave.Error):
        return False


def _delete_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Failed to delete temporary preview file: %s", path)

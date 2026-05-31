from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


LOGGER = logging.getLogger(__name__)


class AudioPreviewError(RuntimeError):
    """Raised when an audio preview response cannot be prepared."""


def transcoded_wav_file_response(path: Path, ffmpeg_path: str) -> FileResponse:
    with tempfile.NamedTemporaryFile(prefix="dj-sim-preview-", suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
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


def _delete_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Failed to delete temporary preview file: %s", path)

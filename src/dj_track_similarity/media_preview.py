from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


LOGGER = logging.getLogger(__name__)


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
        LOGGER.warning("ffmpeg preview transcode failed path=%s error=%s", path, error)
        raise RuntimeError("AIFF preview transcode failed") from error
    return FileResponse(
        temp_path,
        media_type="audio/wav",
        filename=f"{path.stem}.wav",
        content_disposition_type="inline",
        background=BackgroundTask(_delete_temp_file, temp_path),
    )


def _delete_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Failed to delete temporary preview file: %s", path)

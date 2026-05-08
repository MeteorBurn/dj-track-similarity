from __future__ import annotations

import os
from pathlib import Path
import shutil


FFMPEG_ENV_VAR = "DJ_TRACK_SIMILARITY_FFMPEG"


def require_ffmpeg() -> str:
    configured = os.environ.get(FFMPEG_ENV_VAR)
    if configured:
        path = Path(configured)
        if path.exists():
            return str(path)
        raise RuntimeError(
            f"ffmpeg is required but {FFMPEG_ENV_VAR} points to a missing file: {configured}. "
            "Install ffmpeg and add it to PATH, or set DJ_TRACK_SIMILARITY_FFMPEG to ffmpeg.exe."
        )

    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError(
        "ffmpeg is required for robust audio decoding. Install ffmpeg and add it to PATH, "
        "or set DJ_TRACK_SIMILARITY_FFMPEG to the full path of ffmpeg.exe."
    )

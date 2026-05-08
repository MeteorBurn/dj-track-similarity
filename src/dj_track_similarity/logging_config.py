from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG"
DEFAULT_LOG_PATH = Path("dj-track-similarity.log")
FILE_HANDLER_NAME = "dj_track_similarity_file"


def configure_logging(log_path: str | Path | None = None, *, level: int = logging.INFO) -> Path:
    path = Path(log_path or os.environ.get(LOG_ENV_VAR) or DEFAULT_LOG_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("dj_track_similarity")
    logger.setLevel(level)
    logger.propagate = True

    for handler in list(logger.handlers):
        if getattr(handler, "name", "") != FILE_HANDLER_NAME:
            continue
        if Path(getattr(handler, "baseFilename", "")).resolve() == path:
            handler.setLevel(level)
            return path
        logger.removeHandler(handler)
        handler.close()

    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.name = FILE_HANDLER_NAME
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    logger.info("File logging configured path=%s", path)
    return path


def event_log_level(level: str) -> int:
    normalized = level.lower()
    if normalized == "error":
        return logging.ERROR
    if normalized in {"warn", "warning"}:
        return logging.WARNING
    return logging.INFO


def exception_summary(error: Exception) -> str:
    message = str(error).strip()
    return message or type(error).__name__

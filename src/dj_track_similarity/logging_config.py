from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG"
LOG_LEVEL_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG_LEVEL"
DEFAULT_LOG_PATH = Path("dj-track-similarity.log")
FILE_HANDLER_NAME = "dj_track_similarity_file"


def configure_logging(log_path: str | Path | None = None, *, level: int | str | None = None) -> Path:
    path = Path(log_path or os.environ.get(LOG_ENV_VAR) or DEFAULT_LOG_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = parse_log_level(level or os.environ.get(LOG_LEVEL_ENV_VAR) or "warning")

    logger = logging.getLogger("dj_track_similarity")
    logger.setLevel(numeric_level)
    logger.propagate = True

    for handler in list(logger.handlers):
        if getattr(handler, "name", "") != FILE_HANDLER_NAME:
            continue
        if Path(getattr(handler, "baseFilename", "")).resolve() == path:
            handler.setLevel(numeric_level)
            return path
        logger.removeHandler(handler)
        handler.close()

    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.name = FILE_HANDLER_NAME
    handler.setLevel(numeric_level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    logger.info("File logging configured path=%s", path)
    return path


def parse_log_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    normalized = str(level).strip().lower()
    levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    try:
        return levels[normalized]
    except KeyError as error:
        raise ValueError("Unsupported log level. Use debug, info, warning, error, or critical.") from error


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

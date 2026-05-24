from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG"
LOG_LEVEL_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG_LEVEL"
LOG_TRACK_EVENTS_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS"
ANALYSIS_DIAGNOSTICS_ENV_VAR = "DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS"
DEFAULT_LOG_PATH = Path("dj-track-similarity.log")
FILE_HANDLER_NAME = "dj_track_similarity_file"
_LOG_TRACK_EVENTS: bool | None = None
_ANALYSIS_DIAGNOSTICS: bool | None = None


def configure_logging(
    log_path: str | Path | None = None,
    *,
    level: int | str | None = None,
    log_track_events: bool | None = None,
) -> Path:
    global _LOG_TRACK_EVENTS
    if log_track_events is not None:
        _LOG_TRACK_EVENTS = bool(log_track_events)

    path = Path(log_path or os.environ.get(LOG_ENV_VAR) or DEFAULT_LOG_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = parse_log_level(level or os.environ.get(LOG_LEVEL_ENV_VAR) or "info")

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

    handler = TimedRotatingFileHandler(path, when="midnight", interval=1, backupCount=1, encoding="utf-8")
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


def track_event_logging_enabled() -> bool:
    if _LOG_TRACK_EVENTS is not None:
        return _LOG_TRACK_EVENTS
    value = os.environ.get(LOG_TRACK_EVENTS_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def set_analysis_diagnostics_enabled(enabled: bool | None) -> None:
    global _ANALYSIS_DIAGNOSTICS
    _ANALYSIS_DIAGNOSTICS = None if enabled is None else bool(enabled)


def analysis_diagnostics_enabled() -> bool:
    if _ANALYSIS_DIAGNOSTICS is not None:
        return _ANALYSIS_DIAGNOSTICS
    value = os.environ.get(ANALYSIS_DIAGNOSTICS_ENV_VAR)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def log_job_event(
    logger: logging.Logger,
    level: str,
    message: str,
    *args: object,
    track_event: bool = False,
    **kwargs: object,
) -> None:
    if track_event and event_log_level(level) < logging.WARNING and not track_event_logging_enabled():
        return
    logger.log(event_log_level(level), message, *args, **kwargs)


def exception_summary(error: Exception) -> str:
    message = str(error).strip()
    return message or type(error).__name__


def log_failure(logger: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
    logger.error(message, *args, **kwargs)
    logger.debug(message, *args, exc_info=True, **kwargs)

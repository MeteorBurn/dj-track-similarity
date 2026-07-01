from __future__ import annotations

import asyncio
import errno
import logging
import os
import time
from collections.abc import Callable
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG"
LOG_LEVEL_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG_LEVEL"
LOG_TRACK_EVENTS_ENV_VAR = "DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS"
ANALYSIS_DIAGNOSTICS_ENV_VAR = "DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS"
DEFAULT_LOG_PATH = Path("logs") / "dj-track-similarity.log"
FILE_HANDLER_NAME = "dj_track_similarity_file"
LOG_DATE_FORMAT = "%Y-%m-%d] [%H:%M:%S"
FILE_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s %(message)s"
CONSOLE_LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
_LOG_TRACK_EVENTS: bool | None = None
_ANALYSIS_DIAGNOSTICS: bool | None = None
_ASYNCIO_HANDLER_MARKER = "_dj_track_similarity_asyncio_exception_logging"


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

    handler = project_file_handler(path)
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(FILE_LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    logger.addHandler(handler)
    logger.info("File logging configured path=%s", path)
    return path


def project_file_handler(filename: str | Path) -> ProjectTimedRotatingFileHandler:
    path = Path(filename).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = ProjectTimedRotatingFileHandler(path, when="midnight", interval=1, backupCount=1, encoding="utf-8")
    handler.name = FILE_HANDLER_NAME
    return handler


def uvicorn_log_config(level: int | str = "info", log_path: str | Path | None = None) -> dict[str, object]:
    normalized_level = logging.getLevelName(parse_log_level(level))
    config: dict[str, object] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "class": "logging.Formatter",
                "format": CONSOLE_LOG_FORMAT,
                "datefmt": LOG_DATE_FORMAT,
            },
            "access": {
                "class": "logging.Formatter",
                "format": CONSOLE_LOG_FORMAT,
                "datefmt": LOG_DATE_FORMAT,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": normalized_level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": normalized_level, "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": normalized_level, "propagate": False},
            "rhythm_lab": {"handlers": ["default"], "level": normalized_level, "propagate": False},
        },
    }
    if log_path is not None:
        resolved_log_path = Path(log_path).resolve()
        formatters = config["formatters"]
        handlers = config["handlers"]
        loggers = config["loggers"]
        assert isinstance(formatters, dict)
        assert isinstance(handlers, dict)
        assert isinstance(loggers, dict)
        formatters["file"] = {
            "class": "logging.Formatter",
            "format": FILE_LOG_FORMAT,
            "datefmt": LOG_DATE_FORMAT,
        }
        handlers["file"] = {
            "()": "dj_track_similarity.logging_config.project_file_handler",
            "filename": str(resolved_log_path),
            "formatter": "file",
            "level": normalized_level,
        }
        loggers["uvicorn"] = {"handlers": ["default", "file"], "level": normalized_level, "propagate": False}
        loggers["uvicorn.error"] = {"handlers": ["default", "file"], "level": normalized_level, "propagate": False}
        loggers["uvicorn.access"] = {"handlers": ["access", "file"], "level": normalized_level, "propagate": False}
        loggers["dj_track_similarity"] = {"handlers": ["file"], "level": normalized_level, "propagate": True}
    return config


def install_asyncio_exception_logging(logger_name: str = "dj_track_similarity.asyncio") -> None:
    loop = asyncio.get_running_loop()
    if getattr(loop, _ASYNCIO_HANDLER_MARKER, False):
        return

    logger = logging.getLogger(logger_name)
    previous_handler = loop.get_exception_handler()

    def exception_handler(event_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        handle_asyncio_exception_context(
            event_loop,
            context,
            logger=logger,
            previous_handler=previous_handler,
        )

    setattr(exception_handler, _ASYNCIO_HANDLER_MARKER, True)
    loop.set_exception_handler(exception_handler)
    setattr(loop, _ASYNCIO_HANDLER_MARKER, True)


def handle_asyncio_exception_context(
    loop: asyncio.AbstractEventLoop,
    context: dict[str, object],
    *,
    logger: logging.Logger,
    previous_handler: Callable[[asyncio.AbstractEventLoop, dict[str, object]], None] | None,
) -> None:
    error = context.get("exception")
    message = str(context.get("message") or "Unhandled asyncio exception")
    if _is_windows_transport_reset(context):
        summary = exception_summary(error) if isinstance(error, Exception) else repr(error)
        logger.info(
            "Client disconnected during asyncio transport cleanup message=%s error=%s",
            message,
            summary,
        )
        return

    if isinstance(error, BaseException):
        logger.error(
            "Asyncio event loop exception message=%s",
            message,
            exc_info=(type(error), error, error.__traceback__),
        )
    else:
        logger.error(
            "Asyncio event loop exception message=%s context=%s",
            message,
            _safe_asyncio_context(context),
        )
    if previous_handler is not None:
        previous_handler(loop, context)
    else:
        loop.default_exception_handler(context)


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


def _is_windows_transport_reset(context: dict[str, object]) -> bool:
    error = context.get("exception")
    if not isinstance(error, ConnectionResetError):
        return False
    if _connection_reset_code(error) not in {10054, errno.ECONNRESET}:
        return False
    handle_text = str(context.get("handle") or "")
    message = str(context.get("message") or "")
    return "_ProactorBasePipeTransport._call_connection_lost" in f"{message} {handle_text}"


def _connection_reset_code(error: ConnectionResetError) -> int | None:
    winerror = getattr(error, "winerror", None)
    if isinstance(winerror, int):
        return winerror
    if isinstance(error.errno, int):
        return error.errno
    for arg in error.args:
        if isinstance(arg, int):
            return arg
    return None


def _safe_asyncio_context(context: dict[str, object]) -> dict[str, str]:
    return {key: repr(value) for key, value in context.items() if key != "exception"}


def log_failure(logger: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
    logger.error(message, *args, **kwargs)
    logger.debug(message, *args, exc_info=True, **kwargs)


class ProjectTimedRotatingFileHandler(TimedRotatingFileHandler):
    def doRollover(self) -> None:
        active_path = Path(self.baseFilename).resolve()
        sibling_logs = [
            path
            for path in active_path.parent.glob("*.log")
            if path.resolve() != active_path
        ]
        if self.utc:
            time_tuple = time.gmtime(self.rolloverAt - self.interval)
        else:
            time_tuple = time.localtime(self.rolloverAt - self.interval)
        suffix = time.strftime(self.suffix, time_tuple)

        super().doRollover()
        _rollover_project_sibling_logs(sibling_logs, suffix, self.backupCount)


def _rollover_project_sibling_logs(log_paths: list[Path], suffix: str, backup_count: int) -> None:
    for log_path in log_paths:
        if not log_path.exists() or not log_path.is_file():
            continue
        rotated_path = log_path.with_name(f"{log_path.name}.{suffix}")
        try:
            content = log_path.read_bytes()
            if rotated_path.exists():
                rotated_path.unlink()
            if content:
                rotated_path.write_bytes(content)
            log_path.write_bytes(b"")
            _delete_old_log_backups(log_path, backup_count)
        except OSError as error:
            logging.getLogger("dj_track_similarity").warning(
                "Could not rotate project log path=%s error=%s",
                log_path,
                error,
            )


def _delete_old_log_backups(active_path: Path, backup_count: int) -> None:
    backups = sorted(active_path.parent.glob(f"{active_path.name}.*"))
    if backup_count <= 0:
        old_backups = backups
    else:
        old_backups = backups[:-backup_count]
    for backup_path in old_backups:
        try:
            backup_path.unlink()
        except OSError as error:
            logging.getLogger("dj_track_similarity").warning(
                "Could not delete old project log backup path=%s error=%s",
                backup_path,
                error,
            )

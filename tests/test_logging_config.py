from __future__ import annotations

import asyncio
import logging
import re
import time

import dj_track_similarity.logging_config as logging_config
from dj_track_similarity.logging_config import (
    LOG_ENV_VAR,
    handle_asyncio_exception_context,
    install_asyncio_exception_logging,
    configure_logging,
    exception_summary,
    log_failure,
    log_job_event,
    parse_log_level,
)


def test_configure_logging_writes_file(tmp_path):
    log_path = tmp_path / "app.log"
    configured = configure_logging(log_path, level=logging.INFO)

    logger = logging.getLogger("dj_track_similarity.test")
    logger.info("hello file log")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    assert configured == log_path.resolve()
    assert log_path.exists()
    assert "hello file log" in log_path.read_text(encoding="utf-8")


def test_file_log_records_wrap_date_time_and_level_in_brackets(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path, level=logging.INFO)

    logger = logging.getLogger("dj_track_similarity.test")
    logger.warning("bracketed status")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert re.search(
        r"^\[\d{4}-\d{2}-\d{2}\] \[\d{2}:\d{2}:\d{2}\] \[WARNING\] dj_track_similarity\.test bracketed status$",
        contents,
        flags=re.MULTILINE,
    )


def test_uvicorn_log_config_wraps_console_date_time_and_level_in_brackets():
    config = logging_config.uvicorn_log_config("warning")

    assert config["formatters"]["default"]["format"] == "[%(asctime)s] [%(levelname)s] %(message)s"
    assert config["formatters"]["default"]["datefmt"] == "%Y-%m-%d] [%H:%M:%S"
    assert config["formatters"]["access"]["format"] == "[%(asctime)s] [%(levelname)s] %(message)s"
    assert config["loggers"]["uvicorn"]["level"] == "WARNING"
    assert config["loggers"]["uvicorn.access"]["level"] == "WARNING"
    assert config["loggers"]["rhythm_lab"] == {"handlers": ["default"], "level": "WARNING", "propagate": False}


def test_uvicorn_log_config_writes_server_and_access_logs_to_file(tmp_path):
    log_path = tmp_path / "app.log"

    config = logging_config.uvicorn_log_config("info", log_path=log_path)

    assert config["formatters"]["file"]["format"] == "[%(asctime)s] [%(levelname)s] %(name)s %(message)s"
    assert config["handlers"]["file"]["filename"] == str(log_path.resolve())
    assert config["loggers"]["uvicorn"]["handlers"] == ["default", "file"]
    assert config["loggers"]["uvicorn.error"]["handlers"] == ["default", "file"]
    assert config["loggers"]["uvicorn.access"]["handlers"] == ["access", "file"]
    assert config["loggers"]["dj_track_similarity"]["handlers"] == ["file"]


def test_asyncio_transport_reset_is_logged_without_default_traceback(caplog):
    class FakeLoop:
        default_called = False

        def default_exception_handler(self, _context):
            self.default_called = True

    logger = logging.getLogger("dj_track_similarity.asyncio")
    context = {
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
        "exception": ConnectionResetError(10054, "remote host closed connection"),
        "handle": "_ProactorBasePipeTransport._call_connection_lost(None)",
    }
    loop = FakeLoop()

    with caplog.at_level(logging.INFO, logger="dj_track_similarity"):
        handle_asyncio_exception_context(loop, context, logger=logger, previous_handler=None)

    assert "Client disconnected during asyncio transport cleanup" in caplog.text
    assert "Traceback" not in caplog.text
    assert loop.default_called is False


def test_unknown_asyncio_exception_is_logged_and_forwarded(caplog):
    class FakeLoop:
        default_called = False

        def default_exception_handler(self, _context):
            self.default_called = True

    logger = logging.getLogger("dj_track_similarity.asyncio")
    context = {
        "message": "Exception in callback scheduled-work",
        "exception": RuntimeError("scheduler exploded"),
    }
    forwarded: list[dict[str, object]] = []

    def previous_handler(_loop, forwarded_context):
        forwarded.append(forwarded_context)

    with caplog.at_level(logging.ERROR, logger="dj_track_similarity"):
        handle_asyncio_exception_context(FakeLoop(), context, logger=logger, previous_handler=previous_handler)

    assert "Asyncio event loop exception message=Exception in callback scheduled-work" in caplog.text
    assert "RuntimeError: scheduler exploded" in caplog.text
    assert forwarded == [context]


def test_install_asyncio_exception_logging_is_idempotent():
    async def run_check() -> None:
        loop = asyncio.get_running_loop()

        install_asyncio_exception_logging()
        first_handler = loop.get_exception_handler()
        install_asyncio_exception_logging()

        assert first_handler is not None
        assert loop.get_exception_handler() is first_handler

    asyncio.run(run_check())


def test_configure_logging_defaults_to_logs_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(LOG_ENV_VAR, raising=False)

    configured = configure_logging(level=logging.INFO)

    assert configured == (tmp_path / "logs" / "dj-track-similarity.log").resolve()
    assert configured.exists()


def test_configure_logging_defaults_to_info_and_higher(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path)

    logger = logging.getLogger("dj_track_similarity.test")
    logger.debug("debug track line")
    logger.info("normal progress")
    logger.warning("important warning")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert "debug track line" not in contents
    assert "normal progress" in contents
    assert "important warning" in contents


def test_configure_logging_does_not_roll_over_active_log_during_emit(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path)

    handler = next(
        handler
        for handler in logging.getLogger("dj_track_similarity").handlers
        if getattr(handler, "name", "") == "dj_track_similarity_file"
    )
    handler.rolloverAt = int(time.time())

    logger = logging.getLogger("dj_track_similarity.test")
    logger.info("same process after midnight")
    for active_handler in logging.getLogger("dj_track_similarity").handlers:
        active_handler.flush()

    assert "same process after midnight" in log_path.read_text(encoding="utf-8")
    assert list(tmp_path.glob("app.log.*")) == []


def test_configure_logging_archives_previous_day_project_logs_on_startup(tmp_path):
    logs_dir = tmp_path / "logs"
    main_log = logs_dir / "dj-track-similarity.log"
    rhythm_log = logs_dir / "rhythm-lab.log"
    future_log = logs_dir / "future-worker.log"
    old_main_backup = logs_dir / "dj-track-similarity.log.1999-12-31"
    old_rhythm_backup = logs_dir / "rhythm-lab.log.2000-01-01"
    old_future_backup = logs_dir / "future-worker.log.2000-01-01"
    logs_dir.mkdir()
    main_log.write_text("[2000-01-02] [12:00:00] [INFO] previous launch\n", encoding="utf-8")
    rhythm_log.write_text("rhythm before startup rollover\n", encoding="utf-8")
    future_log.write_text("future before startup rollover\n", encoding="utf-8")
    old_main_backup.write_text("old main backup\n", encoding="utf-8")
    old_rhythm_backup.write_text("old rhythm backup\n", encoding="utf-8")
    old_future_backup.write_text("old future backup\n", encoding="utf-8")

    configured = configure_logging(main_log)

    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    assert configured == main_log.resolve()
    assert "File logging configured" in main_log.read_text(encoding="utf-8")
    assert (logs_dir / "dj-track-similarity.log.2000-01-02").read_text(
        encoding="utf-8"
    ) == "[2000-01-02] [12:00:00] [INFO] previous launch\n"
    assert rhythm_log.read_text(encoding="utf-8") == ""
    assert future_log.read_text(encoding="utf-8") == ""
    main_backups = list(logs_dir.glob("dj-track-similarity.log.*"))
    rhythm_backups = list(logs_dir.glob("rhythm-lab.log.*"))
    future_backups = list(logs_dir.glob("future-worker.log.*"))
    assert len(main_backups) == 1
    assert len(rhythm_backups) == 1
    assert len(future_backups) == 1
    assert rhythm_backups[0].read_text(encoding="utf-8") == "rhythm before startup rollover\n"
    assert future_backups[0].read_text(encoding="utf-8") == "future before startup rollover\n"
    assert old_main_backup.exists() is False
    assert old_rhythm_backup.exists() is False
    assert old_future_backup.exists() is False


def test_parse_log_level_accepts_named_levels():
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO
    assert parse_log_level("warning") == logging.WARNING
    assert parse_log_level("error") == logging.ERROR


def test_parse_log_level_rejects_unknown_level():
    try:
        parse_log_level("chatty")
    except ValueError as error:
        assert "Unsupported log level" in str(error)
    else:
        raise AssertionError("parse_log_level should reject unknown levels")


def test_exception_summary_uses_exception_type_for_empty_message():
    assert exception_summary(RuntimeError()) == "RuntimeError"
    assert exception_summary(ValueError("bad file")) == "bad file"


def test_log_failure_puts_traceback_only_in_debug(caplog):
    logger = logging.getLogger("dj_track_similarity.test")

    try:
        raise ValueError("bad wav")
    except ValueError:
        with caplog.at_level(logging.ERROR, logger="dj_track_similarity"):
            log_failure(logger, "Track failed path=%s error=%s", "track.wav", "bad wav")

    assert "Track failed path=track.wav error=bad wav" in caplog.text
    assert "Traceback" not in caplog.text

    caplog.clear()
    try:
        raise ValueError("bad wav")
    except ValueError:
        with caplog.at_level(logging.DEBUG, logger="dj_track_similarity"):
            log_failure(logger, "Track failed path=%s error=%s", "track.wav", "bad wav")

    assert "Track failed path=track.wav error=bad wav" in caplog.text
    assert "Traceback" in caplog.text


def test_log_job_event_aggregates_track_success_by_default(caplog, tmp_path):
    configure_logging(tmp_path / "app.log", log_track_events=False)
    logger = logging.getLogger("dj_track_similarity.test")

    with caplog.at_level(logging.INFO, logger="dj_track_similarity"):
        log_job_event(logger, "ok", "Track analyzed path=%s", "track.wav", track_event=True)
        log_job_event(logger, "info", "Track unchanged path=%s", "track.wav", track_event=True)
        log_job_event(logger, "error", "Track failed path=%s", "track.wav", track_event=True)
        log_job_event(logger, "info", "Analysis completed total=%s", 10)

    assert "Track analyzed" not in caplog.text
    assert "Track unchanged" not in caplog.text
    assert "Track failed path=track.wav" in caplog.text
    assert "Analysis completed total=10" in caplog.text


def test_log_job_event_can_emit_track_success_details(caplog, tmp_path):
    configure_logging(tmp_path / "app.log", log_track_events=True)
    logger = logging.getLogger("dj_track_similarity.test")

    with caplog.at_level(logging.INFO, logger="dj_track_similarity"):
        log_job_event(logger, "ok", "Track analyzed path=%s", "track.wav", track_event=True)

    assert "Track analyzed path=track.wav" in caplog.text

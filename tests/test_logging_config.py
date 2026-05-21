from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from dj_track_similarity.logging_config import configure_logging, exception_summary, log_failure, log_job_event, parse_log_level


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


def test_configure_logging_rotates_daily_and_keeps_one_day(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path)

    handlers = [
        handler
        for handler in logging.getLogger("dj_track_similarity").handlers
        if getattr(handler, "name", "") == "dj_track_similarity_file"
    ]

    assert len(handlers) == 1
    assert isinstance(handlers[0], TimedRotatingFileHandler)
    assert handlers[0].when == "MIDNIGHT"
    assert handlers[0].interval == 24 * 60 * 60
    assert handlers[0].backupCount == 1


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

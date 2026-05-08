from __future__ import annotations

import logging

from dj_track_similarity.logging_config import configure_logging, exception_summary, parse_log_level


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


def test_configure_logging_defaults_to_warnings_and_errors(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path)

    logger = logging.getLogger("dj_track_similarity.test")
    logger.info("noisy track line")
    logger.warning("important warning")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert "noisy track line" not in contents
    assert "important warning" in contents


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

from __future__ import annotations

import logging

from dj_track_similarity.logging_config import configure_logging, exception_summary


def test_configure_logging_writes_file(tmp_path):
    log_path = tmp_path / "app.log"
    configured = configure_logging(log_path)

    logger = logging.getLogger("dj_track_similarity.test")
    logger.info("hello file log")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    assert configured == log_path.resolve()
    assert log_path.exists()
    assert "hello file log" in log_path.read_text(encoding="utf-8")


def test_exception_summary_uses_exception_type_for_empty_message():
    assert exception_summary(RuntimeError()) == "RuntimeError"
    assert exception_summary(ValueError("bad file")) == "bad file"

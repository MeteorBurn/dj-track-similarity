from __future__ import annotations

import logging
import logging.config
import sys
import time

import dj_track_similarity.logging_config as logging_config
from dj_track_similarity.logging_config import (
    LOG_ENV_VAR,
    handle_asyncio_exception_context,
    configure_logging,
    parse_log_level,
)


def test_serve_logging_writes_every_record_to_the_file_once(tmp_path):
    log_path = tmp_path / "app.log"
    configure_logging(log_path, level=logging.INFO)

    # The server applies the uvicorn log config and mirrors the streams on startup.
    logging.config.dictConfig(logging_config.uvicorn_log_config("info"))
    logging_config.install_standard_stream_logging(logging.INFO)

    logging.warning("third-party root record")
    logging.getLogger("dj_track_similarity.test").info("project serve record")
    logging.getLogger("uvicorn.error").info("backend started")
    logging.getLogger("uvicorn.access").info("routine API polling")
    print("third-party progress 42%", file=sys.stderr)
    sys.stderr.flush()
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert contents.count("project serve record") == 1
    assert contents.count("third-party root record") == 1
    assert contents.count("third-party progress 42%") == 1
    assert contents.count("backend started") == 1
    assert "routine API polling" not in contents

    configure_logging(log_path, level=logging.WARNING)
    logging.config.dictConfig(logging_config.uvicorn_log_config("warning"))
    logging_config.install_standard_stream_logging(logging.WARNING)
    logging.getLogger("uvicorn.error").error("backend port is occupied")
    logging.getLogger("rhythm_lab").error("dependent server failed")
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert contents.count("backend port is occupied") == 1
    assert "[ERROR] uvicorn.error backend port is occupied" in contents
    assert contents.count("dependent server failed") == 1
    assert "[ERROR] rhythm_lab dependent server failed" in contents


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


def test_configure_logging_defaults_to_logs_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(LOG_ENV_VAR, raising=False)

    configured = configure_logging(level=logging.INFO)

    assert configured == (tmp_path / "logs" / "dj-track-similarity.log").resolve()
    assert configured.exists()


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

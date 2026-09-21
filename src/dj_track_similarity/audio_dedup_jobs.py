"""Background lifecycle for one Audio Dedup scan.

A scan is report-first: it never deletes anything. It streams the active track
table, retrieves candidates, verifies them, and writes the JSON, XLSX, and log
artifacts that both the review UI and the CLI read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import threading
import time
from typing import Callable
import uuid

from .audio_dedup_bridge import load_audio_dedup_module
from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDedupEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None


@dataclass
class AudioDedupJobStatus:
    job_id: str
    state: str
    search_mode: str
    path_contains: list[str] = field(default_factory=list)
    limit_groups: int | None = None
    detect_fake_bitrate: bool = False
    total: int = 0
    processed: int = 0
    groups: int = 0
    duplicate_copies: int = 0
    valid_fingerprints: int = 0
    current_step: str | None = None
    step_started_at: float | None = None
    step_seconds_per_unit: float | None = None
    report_id: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    events: list[AudioDedupEvent] = field(default_factory=list)
    cancel_requested: bool = False


@dataclass(frozen=True)
class AudioDedupJobPayload:
    path_contains: list[str]
    search_mode: str
    limit_groups: int | None
    detect_fake_bitrate: bool
    out_dir: Path


class AudioDedupJobManager:
    def __init__(self, db: LibraryDatabase, *, out_dir: Path | None = None) -> None:
        self.db = db
        config_module = load_audio_dedup_module("config")
        self.out_dir = Path(out_dir) if out_dir is not None else Path(config_module.DEFAULT_OUT_DIR)
        self._store: JobStore[AudioDedupJobStatus] = JobStore(
            self._copy,
            unknown_label="audio dedup job",
        )
        # The core tests for cancellation once per candidate pair. Reading a flag
        # is cheap where copying the whole status out of the store would not be.
        self._cancel_flags: dict[str, threading.Event] = {}

    def start(self, **options: object) -> AudioDedupJobStatus:
        job_id = self._queue_job(**options)
        threading.Thread(target=self.run_job, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def run_sync(self, **options: object) -> AudioDedupJobStatus:
        job_id = self._queue_job(**options)
        return self.run_job(job_id)

    def _queue_job(
        self,
        *,
        path_contains: list[str] | None = None,
        search_mode: str | None = None,
        limit_groups: int | None = None,
        detect_fake_bitrate: bool = False,
        out_dir: str | Path | None = None,
    ) -> str:
        config_module = load_audio_dedup_module("config")
        selected_mode = search_mode or config_module.MODE_FINGERPRINT_SCAN
        # Validate before queueing so a bad mode is a request error instead of a
        # job that dies inside its own thread.
        if selected_mode not in config_module.SEARCH_MODES:
            raise ValueError(f"Unsupported search mode: {selected_mode}")
        if limit_groups is not None and limit_groups < 1:
            raise ValueError("limit_groups must be greater than zero")
        selected_path_contains = [item.strip() for item in (path_contains or []) if item.strip()]
        selected_out_dir = Path(out_dir) if out_dir is not None else self.out_dir

        job_id = str(uuid.uuid4())
        status = AudioDedupJobStatus(
            job_id=job_id,
            state="queued",
            search_mode=selected_mode,
            path_contains=selected_path_contains,
            limit_groups=limit_groups,
            detect_fake_bitrate=detect_fake_bitrate,
        )
        payload = AudioDedupJobPayload(
            path_contains=selected_path_contains,
            search_mode=selected_mode,
            limit_groups=limit_groups,
            detect_fake_bitrate=detect_fake_bitrate,
            out_dir=selected_out_dir,
        )
        self._cancel_flags[job_id] = threading.Event()
        self._store.add(job_id, status, payload=payload)
        self._append_event(job_id, "info", "Audio dedup queued over the whole library")
        return job_id

    def run_job(self, job_id: str) -> AudioDedupJobStatus:
        core_module = load_audio_dedup_module("core")
        models_module = load_audio_dedup_module("models")
        payload = self._store.payload(job_id)
        if not isinstance(payload, AudioDedupJobPayload):
            raise KeyError(f"Unknown audio dedup job: {job_id}")
        cancelled = self._cancel_flags.get(job_id, threading.Event())
        self._store.update(job_id, state="running", started_at=time.time())
        LOGGER.info("Audio dedup started job_id=%s mode=%s", job_id, payload.search_mode)
        try:
            result = core_module.run_report(
                database=self.db,
                path_contains=list(payload.path_contains),
                limit_groups=payload.limit_groups,
                out_dir=payload.out_dir,
                mode=payload.search_mode,
                detect_fake_bitrate=payload.detect_fake_bitrate,
                progress_callback=self._progress_reporter(job_id),
                should_cancel=cancelled.is_set,
            )
        except models_module.AudioDedupCancelled:
            self._store.update(
                job_id,
                state="cancelled",
                finished_at=time.time(),
                current_step=None,
                step_started_at=None,
                step_seconds_per_unit=None,
            )
            self._append_event(job_id, "warn", "Audio dedup cancelled")
            LOGGER.info("Audio dedup cancelled job_id=%s", job_id)
            return self.get(job_id)
        except Exception as error:
            summary = exception_summary(error)
            self._store.update(
                job_id,
                state="failed",
                finished_at=time.time(),
                current_step=None,
                step_started_at=None,
                step_seconds_per_unit=None,
                error=summary,
            )
            self._append_event(job_id, "error", f"Audio dedup failed: {summary}")
            log_failure(
                LOGGER,
                "Audio dedup failed job_id=%s mode=%s error=%s",
                job_id,
                payload.search_mode,
                summary,
            )
            return self.get(job_id)

        statistics = result.payload.get("statistics")
        statistics = statistics if isinstance(statistics, dict) else {}
        retrieval = result.payload.get("fingerprint_retrieval")
        retrieval = retrieval if isinstance(retrieval, dict) else {}
        report_id = Path(result.json_path).stem
        self._store.update(
            job_id,
            state="completed",
            finished_at=time.time(),
            current_step=None,
            step_started_at=None,
            step_seconds_per_unit=None,
            groups=result.groups,
            duplicate_copies=int(statistics.get("candidate_count", 0) or 0),
            valid_fingerprints=int(retrieval.get("valid_stored_fingerprint_count", 0) or 0),
            report_id=report_id,
        )
        self._append_event(
            job_id,
            "info",
            f"Audio dedup finished: {result.groups} groups",
            path=str(result.json_path),
        )
        LOGGER.info(
            "Audio dedup completed job_id=%s groups=%s report_id=%s",
            job_id,
            result.groups,
            report_id,
        )
        return self.get(job_id)

    def _progress_reporter(self, job_id: str) -> Callable[[int, int, str], None]:
        """Publish progress together with how fast the current step is moving.

        Steps count different things - tracks, candidate pairs, clusters - and
        a step that has just started has no rate at all, so the measurement
        restarts whenever the step changes. The UI turns the rate into the time
        still owed by the step in flight; the whole run has no honest estimate
        because the steps that follow are not the same kind of work.
        """
        step_message: str | None = None
        step_started_at = 0.0
        step_base_processed = 0

        def report(processed: int, total: int, message: str) -> None:
            nonlocal step_message, step_started_at, step_base_processed
            now = time.time()
            if message != step_message or processed < step_base_processed:
                step_message = message
                step_started_at = now
                step_base_processed = processed
            done = processed - step_base_processed
            elapsed = now - step_started_at
            self._store.update(
                job_id,
                processed=processed,
                total=total,
                current_step=message,
                step_started_at=step_started_at,
                step_seconds_per_unit=elapsed / done if done > 0 and elapsed > 0 else None,
            )

        return report

    def get(self, job_id: str) -> AudioDedupJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AudioDedupJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AudioDedupJobStatus:
        # Touch the store first so an unknown id raises before any flag is set.
        self.get(job_id)
        flag = self._cancel_flags.get(job_id)
        if flag is not None:
            flag.set()
        self._store.update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _append_event(
        self,
        job_id: str,
        level: str,
        message: str,
        *,
        path: str | None = None,
    ) -> None:
        self._store.append_event(job_id, AudioDedupEvent(time.time(), level, message, path))

    @staticmethod
    def _copy(value: AudioDedupJobStatus) -> AudioDedupJobStatus:
        return AudioDedupJobStatus(
            **{
                **value.__dict__,
                "path_contains": list(value.path_contains),
                "events": list(value.events),
            }
        )

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
from typing import Mapping
import uuid

from .audio_dedup_bridge import load_audio_dedup_core
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
    root: str
    search_mode: str
    preset: str
    path_contains: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    min_score: float | None = None
    min_similarity: float | None = None
    limit_groups: int | None = None
    skip_spectral: bool = False
    total: int = 0
    processed: int = 0
    groups: int = 0
    review_candidates: int = 0
    safe_candidates: int = 0
    valid_fingerprints: int = 0
    current_step: str | None = None
    report_id: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    events: list[AudioDedupEvent] = field(default_factory=list)
    cancel_requested: bool = False


@dataclass(frozen=True)
class AudioDedupJobPayload:
    root: Path
    path_contains: list[str]
    search_mode: str
    preset: str
    min_score: float | None
    min_similarity: float | None
    limit_groups: int | None
    sources: list[str]
    weights: dict[str, float]
    skip_spectral: bool
    out_dir: Path


class AudioDedupJobManager:
    def __init__(self, db: LibraryDatabase, *, out_dir: Path | None = None) -> None:
        self.db = db
        core = load_audio_dedup_core()
        self.out_dir = Path(out_dir) if out_dir is not None else Path(core.DEFAULT_OUT_DIR)
        self._store: JobStore[AudioDedupJobStatus] = JobStore(
            self._copy,
            unknown_label="audio dedup job",
        )
        self._start_lock = threading.Lock()
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
        root: str | Path,
        path_contains: list[str] | None = None,
        search_mode: str | None = None,
        preset: str = "safe",
        min_score: float | None = None,
        min_similarity: float | None = None,
        limit_groups: int | None = None,
        sources: list[str] | None = None,
        weights: Mapping[str, float] | None = None,
        skip_spectral: bool = False,
        out_dir: str | Path | None = None,
    ) -> str:
        core = load_audio_dedup_core()
        root_text = str(root).strip()
        if not root_text:
            raise ValueError("Root path is required")
        selected_mode = search_mode or core.MODE_FINGERPRINT
        if selected_mode not in core.SEARCH_MODES:
            raise ValueError(f"Unsupported search mode: {selected_mode}")
        if limit_groups is not None and limit_groups < 1:
            raise ValueError("limit_groups must be greater than zero")
        # Validate before queueing so a bad preset, source, or weight is a request
        # error instead of a job that dies inside its own thread.
        core.resolve_preset(preset, min_score=min_score, min_similarity=min_similarity)
        if selected_mode == core.MODE_FINGERPRINT:
            if sources or weights:
                raise ValueError("Sources and weights require the embedding search mode")
            selected_sources: list[str] = []
            selected_weights: dict[str, float] = {}
        else:
            source_config = core.resolve_source_config(sources=sources, weights=weights)
            selected_sources = list(source_config.sources)
            selected_weights = dict(source_config.weights)
        selected_path_contains = [item.strip() for item in (path_contains or []) if item.strip()]
        selected_out_dir = Path(out_dir) if out_dir is not None else self.out_dir

        with self._start_lock:
            latest = self.latest()
            if latest is not None and latest.state in {"queued", "running"}:
                raise RuntimeError("An Audio Dedup scan is already running")
            job_id = str(uuid.uuid4())
            status = AudioDedupJobStatus(
                job_id=job_id,
                state="queued",
                root=root_text,
                search_mode=selected_mode,
                preset=preset,
                path_contains=selected_path_contains,
                sources=selected_sources,
                weights=selected_weights,
                min_score=min_score,
                min_similarity=min_similarity,
                limit_groups=limit_groups,
                skip_spectral=skip_spectral,
            )
            payload = AudioDedupJobPayload(
                root=Path(root_text),
                path_contains=selected_path_contains,
                search_mode=selected_mode,
                preset=preset,
                min_score=min_score,
                min_similarity=min_similarity,
                limit_groups=limit_groups,
                sources=selected_sources,
                weights=selected_weights,
                skip_spectral=skip_spectral,
                out_dir=selected_out_dir,
            )
            self._cancel_flags[job_id] = threading.Event()
            self._store.add(job_id, status, payload=payload)
        self._append_event(job_id, "info", f"Audio dedup queued: {root_text}")
        return job_id

    def run_job(self, job_id: str) -> AudioDedupJobStatus:
        core = load_audio_dedup_core()
        payload = self._store.payload(job_id)
        if not isinstance(payload, AudioDedupJobPayload):
            raise KeyError(f"Unknown audio dedup job: {job_id}")
        cancelled = self._cancel_flags.get(job_id, threading.Event())
        self._store.update(job_id, state="running", started_at=time.time())
        LOGGER.info("Audio dedup started job_id=%s root=%s", job_id, payload.root)
        try:
            result = core.run_report(
                database=self.db,
                root=payload.root,
                path_contains=list(payload.path_contains),
                preset_name=payload.preset,
                min_score=payload.min_score,
                min_similarity=payload.min_similarity,
                limit_groups=payload.limit_groups,
                out_dir=payload.out_dir,
                sources=payload.sources or None,
                weights=payload.weights or None,
                mode=payload.search_mode,
                skip_spectral=payload.skip_spectral,
                progress_callback=lambda processed, total, message: self._store.update(
                    job_id,
                    processed=processed,
                    total=total,
                    current_step=message,
                ),
                should_cancel=cancelled.is_set,
            )
        except core.AudioDedupCancelled:
            self._store.update(
                job_id,
                state="cancelled",
                finished_at=time.time(),
                current_step=None,
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
                error=summary,
            )
            self._append_event(job_id, "error", f"Audio dedup failed: {summary}")
            log_failure(
                LOGGER,
                "Audio dedup failed job_id=%s root=%s error=%s",
                job_id,
                payload.root,
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
            groups=result.groups,
            safe_candidates=int(statistics.get("safe_candidate_count", 0) or 0),
            review_candidates=int(statistics.get("review_candidate_count", 0) or 0),
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
                "sources": list(value.sources),
                "weights": dict(value.weights),
                "events": list(value.events),
            }
        )

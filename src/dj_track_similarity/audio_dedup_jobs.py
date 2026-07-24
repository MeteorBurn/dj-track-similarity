from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import json
import logging
from pathlib import Path
import sys
import threading
import time
import uuid
from types import ModuleType

from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event


LOGGER = logging.getLogger(__name__)
APPLY_CONFIRMATION = "APPLY DELETE"


@dataclass(frozen=True)
class AudioDedupLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class AudioDedupError:
    error: str


@dataclass
class AudioDedupJobStatus:
    job_id: str
    state: str
    root: str
    path_contains: list[str] = field(default_factory=list)
    preset: str = "safe"
    min_score: float | None = None
    min_similarity: float | None = None
    limit_groups: int | None = None
    apply: bool = False
    total: int = 0
    processed: int = 0
    groups: int = 0
    safe_candidates: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    current_path: str | None = None
    current_step: str | None = None
    json_path: str | None = None
    xlsx_path: str | None = None
    log_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_item: float | None = None
    errors: list[AudioDedupError] = field(default_factory=list)
    events: list[AudioDedupLogEvent] = field(default_factory=list)
    cancel_requested: bool = False


@dataclass
class AudioDedupJobPayload:
    db_path: Path
    root: Path
    path_contains: list[str]
    preset: str
    min_score: float | None
    min_similarity: float | None
    limit_groups: int | None
    out_dir: Path | None
    apply: bool
    last_progress_message: str | None = None


class AudioDedupJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._store = JobStore(self._copy_status, unknown_label="audio dedup job")

    def create_job(
        self,
        *,
        root: str | Path,
        path_contains: list[str] | None = None,
        preset: str = "safe",
        min_score: float | None = None,
        min_similarity: float | None = None,
        limit_groups: int | None = None,
        out_dir: str | Path | None = None,
        apply: bool = False,
        confirmation: str | None = None,
    ) -> str:
        if apply and confirmation != APPLY_CONFIRMATION:
            raise ValueError(f'Type exactly "{APPLY_CONFIRMATION}" to run apply mode')
        root_text = str(root).strip()
        if not root_text:
            raise ValueError("Root path is required")
        root_path = Path(root_text)
        if limit_groups is not None and limit_groups < 1:
            raise ValueError("limit_groups must be greater than zero")
        selected_path_contains = [item.strip() for item in (path_contains or []) if item.strip()]
        selected_out_dir = Path(out_dir).expanduser().resolve(strict=False) if out_dir else None
        job_id = str(uuid.uuid4())
        status = AudioDedupJobStatus(
            job_id=job_id,
            state="queued",
            root=str(root_path),
            path_contains=selected_path_contains,
            preset=preset,
            min_score=min_score,
            min_similarity=min_similarity,
            limit_groups=limit_groups,
            apply=apply,
        )
        payload = AudioDedupJobPayload(
            db_path=self.db.path,
            root=root_path,
            path_contains=selected_path_contains,
            preset=preset,
            min_score=min_score,
            min_similarity=min_similarity,
            limit_groups=limit_groups,
            out_dir=selected_out_dir,
            apply=apply,
        )
        self._store.add(job_id, status, payload=payload)
        self._append_event(job_id, "info", "Audio dedup queued", path=str(root_path))
        return job_id

    def start(
        self,
        *,
        root: str | Path,
        path_contains: list[str] | None = None,
        preset: str = "safe",
        min_score: float | None = None,
        min_similarity: float | None = None,
        limit_groups: int | None = None,
        out_dir: str | Path | None = None,
        apply: bool = False,
        confirmation: str | None = None,
    ) -> AudioDedupJobStatus:
        job_id = self.create_job(
            root=root,
            path_contains=path_contains,
            preset=preset,
            min_score=min_score,
            min_similarity=min_similarity,
            limit_groups=limit_groups,
            out_dir=out_dir,
            apply=apply,
            confirmation=confirmation,
        )
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(
        self,
        *,
        root: str | Path,
        path_contains: list[str] | None = None,
        preset: str = "safe",
        min_score: float | None = None,
        min_similarity: float | None = None,
        limit_groups: int | None = None,
        out_dir: str | Path | None = None,
        apply: bool = False,
        confirmation: str | None = None,
    ) -> AudioDedupJobStatus:
        job_id = self.create_job(
            root=root,
            path_contains=path_contains,
            preset=preset,
            min_score=min_score,
            min_similarity=min_similarity,
            limit_groups=limit_groups,
            out_dir=out_dir,
            apply=apply,
            confirmation=confirmation,
        )
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> AudioDedupJobStatus:
        payload = self._payload(job_id)
        if self.get(job_id).cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Audio dedup cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started, current_step="Starting")
        self._append_event(job_id, "info", "Audio dedup started", path=str(payload.root))
        core = _load_audio_dedup_core()
        try:
            out_dir = payload.out_dir or Path(core.DEFAULT_OUT_DIR)
            result = core.run_report(
                database=self.db,
                root=payload.root,
                path_contains=payload.path_contains,
                preset_name=payload.preset,
                min_score=payload.min_score,
                min_similarity=payload.min_similarity,
                limit_groups=payload.limit_groups,
                out_dir=out_dir,
                progress_callback=lambda processed, total, message: self._record_progress(job_id, processed, total, message),
                should_cancel=lambda: self.get(job_id).cancel_requested,
            )
            if self.get(job_id).cancel_requested:
                raise core.AudioDedupCancelled("Audio dedup job cancelled")
            safe_candidates = core.safe_delete_candidates(result.payload)
            deleted = skipped = failed = 0
            if payload.apply:
                self._append_event(job_id, "warn", f"Apply mode started for {len(safe_candidates)} safe candidates")
                apply_result = core.apply_duplicate_deletions(
                    database=self.db,
                    root=payload.root,
                    payload=result.payload,
                )
                result.payload["mode"] = "apply"
                result.payload["apply_result"] = core.apply_result_payload(apply_result)
                result.json_path.write_text(json.dumps(result.payload, indent=2, ensure_ascii=False), encoding="utf-8")
                core.write_text_log(result.log_path, result.payload, apply_result=apply_result)
                deleted = len(apply_result.deleted_track_ids)
                skipped = len(apply_result.skipped)
                failed = len(apply_result.failed)
                self._append_event(job_id, "ok", f"Apply mode completed; deleted {deleted}")
            finished = time.time()
            processed = max(1, self.get(job_id).processed)
            self._update(
                job_id,
                state="completed",
                finished_at=finished,
                current_step="Completed",
                current_path=None,
                groups=result.groups,
                safe_candidates=len(safe_candidates),
                deleted=deleted,
                skipped=skipped,
                failed=failed,
                json_path=str(result.json_path),
                xlsx_path=str(result.xlsx_path),
                log_path=str(result.log_path),
                avg_seconds_per_item=(finished - started) / processed,
            )
            self._append_event(job_id, "ok", "Audio dedup completed", path=str(result.xlsx_path))
        except core.AudioDedupCancelled:
            self._update(job_id, state="cancelled", finished_at=time.time(), current_step="Cancelled", current_path=None)
            self._append_event(job_id, "warn", "Audio dedup cancelled")
        except Exception as error:
            error_text = exception_summary(error)
            log_failure(LOGGER, "Audio dedup failed job_id=%s error=%s", job_id, error_text)
            self._update(
                job_id,
                state="failed",
                finished_at=time.time(),
                current_step="Failed",
                current_path=None,
                errors=[AudioDedupError(error_text)],
                failed=1,
            )
            self._append_event(job_id, "error", f"Audio dedup failed: {error_text}")
        return self.get(job_id)

    def get(self, job_id: str) -> AudioDedupJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AudioDedupJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AudioDedupJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _payload(self, job_id: str) -> AudioDedupJobPayload:
        return self._store.payload(job_id)  # type: ignore[return-value]

    def _record_progress(self, job_id: str, processed: int, total: int, message: str) -> None:
        with self._store.locked(job_id) as status:
            status.processed = processed
            status.total = total
            status.current_step = message
            if status.started_at and processed:
                status.avg_seconds_per_item = (time.time() - status.started_at) / max(1, processed)
        payload = self._payload(job_id)
        if payload.last_progress_message != message:
            payload.last_progress_message = message
            self._append_event(job_id, "info", message)

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    def _append_event(self, job_id: str, level: str, message: str, *, path: str | None = None) -> None:
        log_job_event(LOGGER, level, "%s job_id=%s path=%s", message, job_id, path, track_event=False)
        self._store.append_event(job_id, AudioDedupLogEvent(time.time(), level, message, path))

    @staticmethod
    def _copy_status(status: AudioDedupJobStatus) -> AudioDedupJobStatus:
        return AudioDedupJobStatus(
            job_id=status.job_id,
            state=status.state,
            root=status.root,
            path_contains=list(status.path_contains),
            preset=status.preset,
            min_score=status.min_score,
            min_similarity=status.min_similarity,
            limit_groups=status.limit_groups,
            apply=status.apply,
            total=status.total,
            processed=status.processed,
            groups=status.groups,
            safe_candidates=status.safe_candidates,
            deleted=status.deleted,
            skipped=status.skipped,
            failed=status.failed,
            current_path=status.current_path,
            current_step=status.current_step,
            json_path=status.json_path,
            xlsx_path=status.xlsx_path,
            log_path=status.log_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_item=status.avg_seconds_per_item,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
        )


def _load_audio_dedup_core() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    core_path = repo_root / "tools" / "audio-dedup" / "audio_dedup" / "core.py"
    module_name = "dj_track_similarity_audio_dedup_core"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, core_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Audio dedup tool is unavailable: {core_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

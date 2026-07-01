from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
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
APPLY_CONFIRMATION = "APPLY REPAIR"


@dataclass(frozen=True)
class AudioDoctorLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class AudioDoctorError:
    error: str


@dataclass
class AudioDoctorJobStatus:
    job_id: str
    state: str
    source_mode: str
    db_path: str
    folder: str | None = None
    db_roots: list[str] = field(default_factory=list)
    file_root: str | None = None
    keep_id3: str = "first"
    limit: int | None = None
    workers: int = 1
    reasons: list[str] = field(default_factory=list)
    apply: bool = False
    total: int = 0
    processed: int = 0
    ok: int = 0
    notice: int = 0
    repairable: int = 0
    repaired: int = 0
    suspicious: int = 0
    tag_error: int = 0
    failed: int = 0
    skipped_state: int = 0
    skipped_reason: int = 0
    missing_db_files: int = 0
    current_path: str | None = None
    current_step: str | None = None
    json_path: str | None = None
    xlsx_path: str | None = None
    log_path: str | None = None
    state_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_item: float | None = None
    errors: list[AudioDoctorError] = field(default_factory=list)
    events: list[AudioDoctorLogEvent] = field(default_factory=list)
    cancel_requested: bool = False


@dataclass
class AudioDoctorJobPayload:
    db_path: Path
    source_mode: str
    folder: Path | None
    db_roots: list[Path]
    file_root: Path | None
    keep_id3: str
    limit: int | None
    workers: int
    reasons: list[str]
    out_dir: Path | None
    state_path: Path | None
    apply: bool
    last_progress_message: str | None = None


class AudioDoctorJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._store = JobStore(self._copy_status, unknown_label="audio doctor job")

    def create_job(
        self,
        *,
        source_mode: str,
        folder: str | Path | None = None,
        db_roots: list[str] | None = None,
        file_root: str | Path | None = None,
        keep_id3: str = "first",
        limit: int | None = None,
        workers: int = 1,
        reasons: list[str] | None = None,
        out_dir: str | Path | None = None,
        state_path: str | Path | None = None,
        apply: bool = False,
        confirmation: str | None = None,
    ) -> str:
        if source_mode not in {"db", "folder"}:
            raise ValueError("source_mode must be db or folder")
        if keep_id3 not in {"first", "last", "none"}:
            raise ValueError("keep_id3 must be first, last, or none")
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")
        if workers < 1:
            raise ValueError("workers must be greater than zero")
        if apply and confirmation != APPLY_CONFIRMATION:
            raise ValueError(f'Type exactly "{APPLY_CONFIRMATION}" to run apply mode')

        selected_folder = Path(str(folder).strip()).expanduser().resolve(strict=False) if folder else None
        if source_mode == "folder" and selected_folder is None:
            raise ValueError("Folder is required")
        selected_db_roots = [Path(item).expanduser() for item in (db_roots or []) if str(item).strip()]
        selected_file_root = Path(file_root).expanduser().resolve(strict=False) if file_root else None
        if selected_file_root is not None and not selected_db_roots:
            raise ValueError("file_root requires at least one db_root")
        selected_reasons = [item.strip().upper() for item in (reasons or []) if item.strip()]
        selected_out_dir = Path(out_dir).expanduser().resolve(strict=False) if out_dir else None
        selected_state_path = Path(state_path).expanduser().resolve(strict=False) if state_path else None
        if apply:
            expected_state_path = selected_state_path or self._default_state_path(
                source_mode=source_mode,
                folder=selected_folder,
            )
            if not expected_state_path.exists():
                raise ValueError("Run a dry-run first so Audio Doctor has state to apply from")

        job_id = str(uuid.uuid4())
        status = AudioDoctorJobStatus(
            job_id=job_id,
            state="queued",
            source_mode=source_mode,
            db_path=str(self.db.path),
            folder=str(selected_folder) if selected_folder is not None else None,
            db_roots=[str(path) for path in selected_db_roots],
            file_root=str(selected_file_root) if selected_file_root is not None else None,
            keep_id3=keep_id3,
            limit=limit,
            workers=workers,
            reasons=selected_reasons,
            apply=apply,
            state_path=str(selected_state_path) if selected_state_path is not None else None,
        )
        payload = AudioDoctorJobPayload(
            db_path=self.db.path,
            source_mode=source_mode,
            folder=selected_folder,
            db_roots=selected_db_roots,
            file_root=selected_file_root,
            keep_id3=keep_id3,
            limit=limit,
            workers=workers,
            reasons=selected_reasons,
            out_dir=selected_out_dir,
            state_path=selected_state_path,
            apply=apply,
        )
        self._store.add(job_id, status, payload=payload)
        self._append_event(job_id, "info", "Audio Doctor queued", path=status.folder or status.db_path)
        return job_id

    def start(self, **kwargs: object) -> AudioDoctorJobStatus:
        job_id = self.create_job(**kwargs)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, **kwargs: object) -> AudioDoctorJobStatus:
        job_id = self.create_job(**kwargs)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> AudioDoctorJobStatus:
        payload = self._payload(job_id)
        if self.get(job_id).cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Audio Doctor cancelled")
            return self.get(job_id)

        core = _load_audio_doctor_core()
        started = time.time()
        self._update(job_id, state="running", started_at=started, current_step="Starting")
        self._append_event(job_id, "info", "Audio Doctor started", path=str(payload.folder or payload.db_path))
        try:
            folders = [payload.folder] if payload.source_mode == "folder" and payload.folder is not None else []
            dbs = [payload.db_path] if payload.source_mode == "db" else []
            db_paths, missing_db_files = core.collect_db_paths(
                dbs,
                db_roots=payload.db_roots,
                file_root=payload.file_root,
            )
            all_paths = core.collect_paths([], [], folders=folders, db_paths=db_paths, since=None, until=None)
            if not all_paths:
                raise ValueError("No audio paths found")
            sources = core.state_sources(folders, dbs)
            state_path = payload.state_path or core.resolve_state_path(None, sources)
            state = core.load_state(state_path, sources)
            reason_filters = {core.normalize_reason_filter(reason) for reason in payload.reasons}
            pending_paths: list[Path] = []
            skipped_state_results = []
            skipped_from_state = 0
            skipped_by_reason = 0
            for path in all_paths:
                if reason_filters and not core.state_entry_reason_matches(state, path, reason_filters):
                    skipped_by_reason += 1
                    continue
                if core.state_entry_current(state, path, apply_changes=payload.apply):
                    skipped_from_state += 1
                    entry = core.state_entry_for_path(state, path)
                    if entry is not None:
                        skipped_state_results.append(core.StateRepairResult(path=path, entry=dict(entry)))
                else:
                    pending_paths.append(path)
            if payload.limit is not None:
                pending_paths = pending_paths[: payload.limit]
            out_dir = payload.out_dir or Path(core.DEFAULT_OUT_DIR)
            self._update(
                job_id,
                total=len(all_paths),
                missing_db_files=missing_db_files,
                skipped_state=skipped_from_state,
                skipped_reason=skipped_by_reason,
                state_path=str(state_path),
                current_step="Inspecting files",
            )
            run_result = core.run_paths(
                pending_paths,
                all_paths=all_paths,
                skipped_from_state=skipped_from_state,
                reporter=_QuietReporter(),
                use_color=False,
                apply_changes=payload.apply,
                backup_dir=None,
                no_backup=False,
                keep_id3=payload.keep_id3,
                state=state,
                state_path=state_path,
                state_mode=True,
                summary_only=True,
                workers=1 if payload.apply else payload.workers,
                skipped_by_reason=skipped_by_reason,
                missing_db_files=missing_db_files,
                skipped_state_results=skipped_state_results,
                progress_callback=lambda processed, total, path, result: self._record_progress(
                    job_id, processed, total, path, result
                ),
                should_cancel=lambda: self.get(job_id).cancel_requested,
            )
            report = core.write_report_bundle(
                out_dir=out_dir,
                run_result=run_result,
                sources=sources,
                folders=folders,
                dbs=dbs,
                logs=[],
                explicit_paths=[],
                reason_filters=sorted(reason_filters),
            )
            counts = report.payload.get("status_counts") if isinstance(report.payload, dict) else {}
            finished = time.time()
            processed = max(1, run_result.total_collected - run_result.skipped_from_state - run_result.skipped_by_reason)
            self._update(
                job_id,
                state="completed",
                finished_at=finished,
                current_step="Completed",
                current_path=None,
                json_path=str(report.json_path),
                xlsx_path=str(report.xlsx_path),
                log_path=str(report.log_path),
                processed=run_result.total_collected,
                ok=int(counts.get("ok", 0)) if isinstance(counts, dict) else 0,
                notice=int(counts.get("notice", 0)) if isinstance(counts, dict) else 0,
                repairable=int(counts.get("repairable", 0)) if isinstance(counts, dict) else 0,
                repaired=int(counts.get("repaired", 0)) if isinstance(counts, dict) else 0,
                suspicious=int(counts.get("suspicious", 0)) if isinstance(counts, dict) else 0,
                tag_error=int(counts.get("tag-error", 0)) if isinstance(counts, dict) else 0,
                failed=int(counts.get("failed", 0)) if isinstance(counts, dict) else 0,
                avg_seconds_per_item=(finished - started) / processed,
            )
            self._append_event(job_id, "ok", "Audio Doctor completed", path=str(report.xlsx_path))
        except core.AudioDoctorCancelled:
            self._update(job_id, state="cancelled", finished_at=time.time(), current_step="Cancelled", current_path=None)
            self._append_event(job_id, "warn", "Audio Doctor cancelled")
        except Exception as error:
            error_text = exception_summary(error)
            log_failure(LOGGER, "Audio Doctor failed job_id=%s error=%s", job_id, error_text)
            self._update(
                job_id,
                state="failed",
                finished_at=time.time(),
                current_step="Failed",
                current_path=None,
                errors=[AudioDoctorError(error_text)],
                failed=1,
            )
            self._append_event(job_id, "error", f"Audio Doctor failed: {error_text}")
        return self.get(job_id)

    def get(self, job_id: str) -> AudioDoctorJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AudioDoctorJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AudioDoctorJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _default_state_path(self, *, source_mode: str, folder: Path | None) -> Path:
        core = _load_audio_doctor_core()
        folders = [folder] if source_mode == "folder" and folder is not None else []
        dbs = [self.db.path] if source_mode == "db" else []
        return core.resolve_state_path(None, core.state_sources(folders, dbs))

    def _payload(self, job_id: str) -> AudioDoctorJobPayload:
        return self._store.payload(job_id)  # type: ignore[return-value]

    def _record_progress(self, job_id: str, processed: int, total: int, path: Path, result: object) -> None:
        status_name = getattr(result, "status", "")
        status_key = "tag_error" if status_name == "tag-error" else str(status_name).replace("-", "_")
        with self._store.locked(job_id) as status:
            status.processed = processed
            status.total = max(status.total, total)
            status.current_path = str(path)
            status.current_step = f"{status_name or 'checked'}: {path.name}"
            if hasattr(status, status_key):
                setattr(status, status_key, getattr(status, status_key) + 1)
            if status.started_at and processed:
                status.avg_seconds_per_item = (time.time() - status.started_at) / max(1, processed)
        payload = self._payload(job_id)
        message = f"{status_name or 'checked'}: {path.name}"
        if payload.last_progress_message != message:
            payload.last_progress_message = message
            self._append_event(job_id, "info", message, path=str(path))

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    def _append_event(self, job_id: str, level: str, message: str, *, path: str | None = None) -> None:
        log_job_event(LOGGER, level, "%s job_id=%s path=%s", message, job_id, path, track_event=False)
        self._store.append_event(job_id, AudioDoctorLogEvent(time.time(), level, message, path))

    @staticmethod
    def _copy_status(status: AudioDoctorJobStatus) -> AudioDoctorJobStatus:
        return AudioDoctorJobStatus(
            job_id=status.job_id,
            state=status.state,
            source_mode=status.source_mode,
            db_path=status.db_path,
            folder=status.folder,
            db_roots=list(status.db_roots),
            file_root=status.file_root,
            keep_id3=status.keep_id3,
            limit=status.limit,
            workers=status.workers,
            reasons=list(status.reasons),
            apply=status.apply,
            total=status.total,
            processed=status.processed,
            ok=status.ok,
            notice=status.notice,
            repairable=status.repairable,
            repaired=status.repaired,
            suspicious=status.suspicious,
            tag_error=status.tag_error,
            failed=status.failed,
            skipped_state=status.skipped_state,
            skipped_reason=status.skipped_reason,
            missing_db_files=status.missing_db_files,
            current_path=status.current_path,
            current_step=status.current_step,
            json_path=status.json_path,
            xlsx_path=status.xlsx_path,
            log_path=status.log_path,
            state_path=status.state_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_item=status.avg_seconds_per_item,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
        )


def _load_audio_doctor_core() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    core_path = repo_root / "tools" / "audio-doctor" / "audio_doctor" / "core.py"
    module_name = "dj_track_similarity_audio_doctor_core"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, core_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Audio Doctor tool is unavailable: {core_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _QuietReporter:
    def line(self, _text: str = "") -> None:
        return None

    def close(self) -> None:
        return None

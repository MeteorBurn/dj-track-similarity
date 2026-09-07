from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..analysis.jobs import AnalysisJobManager
from ..analysis.pipeline import AnalysisPipelineManager
from ..analysis.queue import AnalysisStageQueue
from ..audio_dedup_jobs import AudioDedupJobManager
from ..classifier.jobs import ClassifierJobManager
from ..database import LibraryDatabase
from ..db.optimization_jobs import DatabaseOptimizationJobManager
from ..db.validation_jobs import DatabaseValidationJobManager
from ..scan_jobs import ScanJobManager
from ..tags import GenreTagJobManager


LOGGER = logging.getLogger(__name__)

ACTIVE_JOB_STATES = {"queued", "running"}


class DatabaseNotSelected(RuntimeError):
    pass


class DatabaseBusy(RuntimeError):
    pass


class AppDatabaseState:
    def __init__(self, db_path: str | Path | None) -> None:
        self._lock = threading.RLock()
        self._lifecycle = threading.Condition(self._lock)
        self._closing = False
        self._closed = False
        self._closing_thread: int | None = None
        self._closing_owners: tuple[AnalysisStageQueue | None, AnalysisJobManager | None] | None = None
        self._replacement_owners: dict[
            object, tuple[AnalysisStageQueue | None, AnalysisJobManager | None, int]
        ] = {}
        self._exclusive_operation: str | None = None
        self.db_path: Path | None = None
        self.db: LibraryDatabase | None = None
        self.analysis_jobs: AnalysisJobManager | None = None
        self.analysis_pipeline_jobs: AnalysisPipelineManager | None = None
        self.analysis_queue: AnalysisStageQueue | None = None
        self.classifier_jobs: ClassifierJobManager | None = None
        self.scan_jobs: ScanJobManager | None = None
        self.genre_tag_jobs: GenreTagJobManager | None = None
        self.database_validation_jobs: DatabaseValidationJobManager | None = None
        self.database_optimization_jobs: DatabaseOptimizationJobManager | None = None
        self.audio_dedup_jobs: AudioDedupJobManager | None = None
        if db_path is not None:
            self.switch(db_path)

    def current(self) -> dict[str, object]:
        with self._lock:
            db = self.db
            return {
                "path": str(self.db_path) if self.db_path is not None else None,
                "evaluation_path": str(db.evaluation_path) if db is not None else None,
                "catalog_uuid": db.catalog_uuid if db is not None else None,
                "selected": db is not None,
            }

    def switch(self, path: str | Path) -> dict[str, object]:
        selected = Path(path).expanduser()
        if not str(selected).strip() or not selected.name:
            raise ValueError("Database path is required")
        if selected.exists() and selected.is_dir():
            raise ValueError("Database path must be a file")
        selected = selected.resolve(strict=False)
        cleanup_queue: AnalysisStageQueue | None = None
        cleanup_jobs: AnalysisJobManager | None = None
        cleanup_token = object()
        cleanup_thread = threading.get_ident()
        try:
            with self._lock:
                self._require_open()
                if self._exclusive_operation is not None:
                    raise DatabaseBusy(
                        "Cannot switch database while "
                        f"{self._exclusive_operation} is running"
                    )
                if self._has_active_jobs():
                    raise DatabaseBusy("Cannot switch database while jobs are running")
                self._replacement_owners[cleanup_token] = (None, None, cleanup_thread)
                db = LibraryDatabase(selected)
                rebuilt = db.ensure_search_index_current()
                if rebuilt:
                    LOGGER.info(
                        "Search index rebuilt for MAEST genres rows=%s path=%s",
                        rebuilt,
                        db.path,
                    )
                analysis_queue = cleanup_queue = AnalysisStageQueue()
                self._replacement_owners[cleanup_token] = (cleanup_queue, None, cleanup_thread)
                analysis_jobs = cleanup_jobs = AnalysisJobManager(db, stage_queue=analysis_queue)
                self._replacement_owners[cleanup_token] = (cleanup_queue, cleanup_jobs, cleanup_thread)
                classifier_jobs = ClassifierJobManager(db, stage_queue=analysis_queue)
                analysis_pipeline_jobs = AnalysisPipelineManager(
                    analysis_jobs,
                    analysis_queue,
                )
                scan_jobs = ScanJobManager(db)
                genre_tag_jobs = GenreTagJobManager(db)
                database_validation_jobs = DatabaseValidationJobManager(str(db.path))
                database_optimization_jobs = DatabaseOptimizationJobManager(db.path)
                audio_dedup_jobs = AudioDedupJobManager(db)

                cleanup_queue = self.analysis_queue
                cleanup_jobs = self.analysis_jobs
                self._replacement_owners[cleanup_token] = (cleanup_queue, cleanup_jobs, cleanup_thread)
                self.db_path = db.path
                self.db = db
                self.analysis_queue = analysis_queue
                self.analysis_jobs = analysis_jobs
                self.classifier_jobs = classifier_jobs
                self.analysis_pipeline_jobs = analysis_pipeline_jobs
                self.scan_jobs = scan_jobs
                self.genre_tag_jobs = genre_tag_jobs
                self.database_validation_jobs = database_validation_jobs
                self.database_optimization_jobs = database_optimization_jobs
                self.audio_dedup_jobs = audio_dedup_jobs
                return self.current()
        finally:
            try:
                self._close_analysis(cleanup_queue, cleanup_jobs)
            finally:
                with self._lifecycle:
                    self._replacement_owners.pop(cleanup_token, None)
                    self._lifecycle.notify_all()

    @staticmethod
    def _close_analysis(
        stage_queue: AnalysisStageQueue | None,
        manager: AnalysisJobManager | None,
    ) -> None:
        if stage_queue is not None:
            stage_queue.close()
        if manager is not None:
            manager.close()

    def _require_open(self) -> None:
        if self._closing:
            raise DatabaseBusy("Database state is closed")

    def close(self) -> None:
        """Drain database-owned analysis resources without holding the state lock."""
        with self._lifecycle:
            stage_queue, manager = self._closing_owners or (self.analysis_queue, self.analysis_jobs)
            for owned_queue, owned_manager, cleanup_thread in self._replacement_owners.values():
                if cleanup_thread == threading.get_ident():
                    raise RuntimeError("Database state cannot close from replacement cleanup")
                if owned_queue is not None:
                    owned_queue.check_close_allowed()
                if owned_manager is not None:
                    owned_manager.check_close_allowed()
            if stage_queue is not None:
                stage_queue.check_close_allowed()
            if manager is not None:
                manager.check_close_allowed()
            if self._closing:
                if self._closing_thread == threading.get_ident():
                    return
                self._lifecycle.wait_for(lambda: self._closed)
                return
            self._closing = True
            self._closing_thread = threading.get_ident()
            self._closing_owners = stage_queue, manager
            self.analysis_queue = None
            self.analysis_jobs = None
            self.analysis_pipeline_jobs = None
            self.classifier_jobs = None
        try:
            self._close_analysis(stage_queue, manager)
        finally:
            with self._lifecycle:
                self._lifecycle.wait_for(lambda: not self._replacement_owners)
                self._closing_owners = None
                self._closed = True
                self._lifecycle.notify_all()

    def require_db(self) -> LibraryDatabase:
        with self._lock:
            self._require_open()
            if self.db is None:
                raise DatabaseNotSelected("Database is not selected")
            return self.db

    def require_idle_db(self, operation: str) -> LibraryDatabase:
        """Return the selected database only when no background job is active."""

        with self._lock:
            database = self.require_db()
            if self._has_active_jobs():
                raise DatabaseBusy(
                    f"Cannot {operation} while jobs are running"
                )
            return database

    @contextmanager
    def exclusive_db(
        self,
        operation: str,
    ) -> Iterator[LibraryDatabase]:
        """Reserve the selected database for one synchronous maintenance task."""

        with self._lock:
            database = self.require_idle_db(operation)
            if self._exclusive_operation is not None:
                raise DatabaseBusy(
                    f"Cannot {operation} while "
                    f"{self._exclusive_operation} is running"
                )
            self._exclusive_operation = operation
        try:
            yield database
        finally:
            with self._lock:
                self._exclusive_operation = None

    @contextmanager
    def job_start(self) -> Iterator[None]:
        """Keep selection and exclusivity stable until a job is queued.

        Manager lookup followed by ``start()`` is otherwise a check-then-act
        race: an exclusive database operation can begin after the lookup but
        before the manager records its queued job.
        """

        with self._lock:
            self._require_jobs_available()
            yield

    def _require_jobs_available(self) -> None:
        with self._lock:
            self.require_db()
            if self._exclusive_operation is not None:
                raise DatabaseBusy(
                    "Cannot start or inspect jobs while "
                    f"{self._exclusive_operation} is running"
                )

    def require_analysis_jobs(self) -> AnalysisJobManager:
        self._require_jobs_available()
        assert self.analysis_jobs is not None
        return self.analysis_jobs

    def require_classifier_jobs(self) -> ClassifierJobManager:
        self._require_jobs_available()
        assert self.classifier_jobs is not None
        return self.classifier_jobs

    def require_analysis_pipeline_jobs(self) -> AnalysisPipelineManager:
        self._require_jobs_available()
        assert self.analysis_pipeline_jobs is not None
        return self.analysis_pipeline_jobs

    def require_scan_jobs(self) -> ScanJobManager:
        self._require_jobs_available()
        assert self.scan_jobs is not None
        return self.scan_jobs

    def require_genre_tag_jobs(self) -> GenreTagJobManager:
        self._require_jobs_available()
        assert self.genre_tag_jobs is not None
        return self.genre_tag_jobs

    def require_database_validation_jobs(self) -> DatabaseValidationJobManager:
        self._require_jobs_available()
        assert self.database_validation_jobs is not None
        return self.database_validation_jobs

    def require_database_optimization_jobs(self) -> DatabaseOptimizationJobManager:
        self._require_jobs_available()
        assert self.database_optimization_jobs is not None
        return self.database_optimization_jobs

    def require_audio_dedup_jobs(self) -> AudioDedupJobManager:
        self._require_jobs_available()
        assert self.audio_dedup_jobs is not None
        return self.audio_dedup_jobs

    def _has_active_jobs(self) -> bool:
        managers = [
            self.analysis_jobs,
            self.analysis_pipeline_jobs,
            self.classifier_jobs,
            self.scan_jobs,
            self.genre_tag_jobs,
            self.database_validation_jobs,
            self.database_optimization_jobs,
            self.audio_dedup_jobs,
        ]
        for manager in managers:
            if manager is None:
                continue
            latest = manager.latest()
            if latest is not None and getattr(latest, "state", None) in ACTIVE_JOB_STATES:
                return True
        return False

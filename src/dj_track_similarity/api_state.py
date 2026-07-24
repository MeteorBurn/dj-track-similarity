from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .analysis_jobs import AnalysisJobManager
from .analysis_pipeline import AnalysisPipelineManager
from .analysis_queue import AnalysisStageQueue
from .audio_dedup_jobs import AudioDedupJobManager
from .audio_doctor_jobs import AudioDoctorJobManager
from .classifier_jobs import ClassifierJobManager
from .database import LibraryDatabase
from .scan_jobs import ScanJobManager
from .tags import GenreTagJobManager


ACTIVE_JOB_STATES = {"queued", "running"}


class DatabaseNotSelected(RuntimeError):
    pass


class DatabaseBusy(RuntimeError):
    pass


class AppDatabaseState:
    def __init__(self, db_path: str | Path | None) -> None:
        self._lock = threading.RLock()
        self._exclusive_operation: str | None = None
        self.db_path: Path | None = None
        self.db: LibraryDatabase | None = None
        self.analysis_jobs: AnalysisJobManager | None = None
        self.analysis_pipeline_jobs: AnalysisPipelineManager | None = None
        self.analysis_queue: AnalysisStageQueue | None = None
        self.audio_dedup_jobs: AudioDedupJobManager | None = None
        self.audio_doctor_jobs: AudioDoctorJobManager | None = None
        self.classifier_jobs: ClassifierJobManager | None = None
        self.scan_jobs: ScanJobManager | None = None
        self.genre_tag_jobs: GenreTagJobManager | None = None
        if db_path is not None:
            self.switch(db_path)

    def current(self) -> dict[str, object]:
        with self._lock:
            db = self.db
            return {
                "path": str(self.db_path) if self.db_path is not None else None,
                "artifacts_path": str(db.artifacts_path) if db is not None else None,
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
        with self._lock:
            if self._exclusive_operation is not None:
                raise DatabaseBusy(
                    "Cannot switch database while "
                    f"{self._exclusive_operation} is running"
                )
            if self._has_active_jobs():
                raise DatabaseBusy("Cannot switch database while jobs are running")
            db = LibraryDatabase(selected)
            analysis_queue = AnalysisStageQueue()
            analysis_jobs = AnalysisJobManager(db, stage_queue=analysis_queue)
            audio_dedup_jobs = AudioDedupJobManager(db)
            audio_doctor_jobs = AudioDoctorJobManager(db)
            classifier_jobs = ClassifierJobManager(db, stage_queue=analysis_queue)
            analysis_pipeline_jobs = AnalysisPipelineManager(
                analysis_jobs,
                classifier_jobs,
                analysis_queue,
            )
            scan_jobs = ScanJobManager(db)
            genre_tag_jobs = GenreTagJobManager(db)

            self.db_path = db.path
            self.db = db
            self.analysis_queue = analysis_queue
            self.analysis_jobs = analysis_jobs
            self.audio_dedup_jobs = audio_dedup_jobs
            self.audio_doctor_jobs = audio_doctor_jobs
            self.classifier_jobs = classifier_jobs
            self.analysis_pipeline_jobs = analysis_pipeline_jobs
            self.scan_jobs = scan_jobs
            self.genre_tag_jobs = genre_tag_jobs
            return self.current()

    def require_db(self) -> LibraryDatabase:
        with self._lock:
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

    def require_audio_dedup_jobs(self) -> AudioDedupJobManager:
        self._require_jobs_available()
        assert self.audio_dedup_jobs is not None
        return self.audio_dedup_jobs

    def require_audio_doctor_jobs(self) -> AudioDoctorJobManager:
        self._require_jobs_available()
        assert self.audio_doctor_jobs is not None
        return self.audio_doctor_jobs

    def require_scan_jobs(self) -> ScanJobManager:
        self._require_jobs_available()
        assert self.scan_jobs is not None
        return self.scan_jobs

    def require_genre_tag_jobs(self) -> GenreTagJobManager:
        self._require_jobs_available()
        assert self.genre_tag_jobs is not None
        return self.genre_tag_jobs

    def _has_active_jobs(self) -> bool:
        managers = [
            self.analysis_jobs,
            self.analysis_pipeline_jobs,
            self.audio_dedup_jobs,
            self.audio_doctor_jobs,
            self.classifier_jobs,
            self.scan_jobs,
            self.genre_tag_jobs,
        ]
        for manager in managers:
            if manager is None:
                continue
            latest = manager.latest()
            if latest is not None and getattr(latest, "state", None) in ACTIVE_JOB_STATES:
                return True
        return False

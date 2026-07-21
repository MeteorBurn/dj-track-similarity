from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from .analysis_job_state import AnalysisModelProgress
from .analysis_queue import AnalysisStageQueue
from .classifier_scoring import (
    ClassifierRequirements,
    ClassifierScorer,
    load_classifier_requirements,
)
from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event
from .models import Track


LOGGER = logging.getLogger(__name__)


class _Scorer(Protocol):
    model_name: str
    manifest_warnings: Sequence[str]

    def score_track(self, track: Track) -> dict[str, float] | None:
        ...

    def save_score(self, track: Track, probabilities: dict[str, float]) -> None:
        ...


@dataclass(frozen=True)
class ClassifierTrackError:
    track_id: int
    path: str
    error: str
    model: str


@dataclass(frozen=True)
class ClassifierLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None
    model: str | None = None


@dataclass
class ClassifierJobStatus:
    job_id: str
    state: str
    adapter_name: str = "classifiers"
    embedding_key: str = "classifiers"
    classifier_keys: list[str] = field(default_factory=list)
    current_model: str | None = None
    model_progress: dict[str, AnalysisModelProgress] = field(default_factory=dict)
    readiness: dict[str, dict[str, int]] = field(default_factory=dict)
    blockers: dict[str, list[str]] = field(default_factory=dict)
    model_name: str | None = None
    device: str | None = "cpu"
    device_requested: str = "cpu"
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    skipped: int = 0
    failed: int = 0
    not_ready: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[ClassifierTrackError] = field(default_factory=list)
    events: list[ClassifierLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = 1
    batch_size: int = 1


@dataclass(frozen=True)
class _ClassifierPayload:
    tracks_by_classifier: dict[str, list[Track]]
    requirements: dict[str, ClassifierRequirements]


class ClassifierJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        *,
        stage_queue: AnalysisStageQueue | None = None,
        scorer_factory: Callable[[str, Path], _Scorer] | None = None,
        requirements_loader: Callable[[str], ClassifierRequirements] | None = None,
    ) -> None:
        self.db = db
        self._stage_queue = stage_queue
        self._scorer_factory = scorer_factory
        self._requirements_loader = requirements_loader
        self._store = JobStore(self._copy_status, unknown_label="classifier job")

    def create_job(
        self,
        *,
        classifiers: Sequence[str] | None = None,
        classifier: str | None = None,
        limit: int | None = None,
        model_path: str | Path | None = None,
    ) -> str:
        keys = _clean_classifier_keys([*(classifiers or ()), *([classifier] if classifier else [])])
        if not keys:
            raise ValueError("At least one scoring-compatible promoted classifier must be selected")
        if model_path is not None and len(keys) != 1:
            raise ValueError("A custom classifier model path can only be used with one classifier")

        requirements: dict[str, ClassifierRequirements] = {}
        tracks_by_classifier: dict[str, list[Track]] = {}
        readiness: dict[str, dict[str, int]] = {}
        progress: dict[str, AnalysisModelProgress] = {}
        remaining = None if limit is None else max(0, int(limit))
        for key in keys:
            requirement = (
                load_classifier_requirements(key, model_path=model_path)
                if model_path is not None
                else self._load_requirements(key)
            )
            requirements[key] = requirement
            counts = self.db.classifier_candidate_readiness(
                key,
                model_id=requirement.model_id,
                required_inputs=requirement.required_inputs,
                sonara_signature=requirement.sonara_analysis_signature,
                feature_names=requirement.feature_names,
            )
            tracks = (
                []
                if remaining == 0
                else self.db.list_classifier_candidates(
                    key,
                    model_id=requirement.model_id,
                    required_inputs=requirement.required_inputs,
                    sonara_signature=requirement.sonara_analysis_signature,
                    feature_names=requirement.feature_names,
                    limit=remaining,
                )
            )
            if remaining is not None:
                remaining -= len(tracks)
            readiness[key] = {**counts, "selected": len(tracks)}
            tracks_by_classifier[key] = tracks
            progress[key] = AnalysisModelProgress(total=len(tracks))

        job_id = str(uuid.uuid4())
        total = sum(len(tracks) for tracks in tracks_by_classifier.values())
        status = ClassifierJobStatus(
            job_id=job_id,
            state="queued",
            adapter_name=keys[0] if len(keys) == 1 else "classifiers",
            embedding_key=keys[0] if len(keys) == 1 else "classifiers",
            classifier_keys=list(keys),
            model_progress=progress,
            readiness=readiness,
            total=total,
            not_ready=sum(counts["not_ready"] for counts in readiness.values()),
        )
        self._store.add(
            job_id,
            status,
            payload=_ClassifierPayload(tracks_by_classifier=tracks_by_classifier, requirements=requirements),
        )
        self._append_event(job_id, "info", "CLASSIFIERS queued")
        return job_id

    def readiness(self, classifiers: Sequence[str]) -> dict[str, dict[str, int | list[str]]]:
        result: dict[str, dict[str, int | list[str]]] = {}
        for key in _clean_classifier_keys(classifiers):
            try:
                requirement = self._load_requirements(key)
                counts = self.db.classifier_candidate_readiness(
                    key,
                    model_id=requirement.model_id,
                    required_inputs=requirement.required_inputs,
                    sonara_signature=requirement.sonara_analysis_signature,
                    feature_names=requirement.feature_names,
                )
                result[key] = {**counts, "blockers": []}
            except (FileNotFoundError, RuntimeError, ValueError) as error:
                result[key] = {"candidates": 0, "ready": 0, "not_ready": 0, "blockers": [str(error)]}
        return result

    def start(self, **kwargs: object) -> ClassifierJobStatus:
        job_id = self.create_job(**kwargs)
        if self._stage_queue is not None:
            self._stage_queue.submit(lambda: self.run_job(job_id))
        else:
            threading.Thread(target=self.run_job, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def run_job(
        self,
        job_id: str,
        classifier: str | None = None,
        model_path: str | Path | None = None,
    ) -> ClassifierJobStatus:
        del classifier, model_path
        status = self.get(job_id)
        payload = cast(_ClassifierPayload, self._store.payload(job_id))
        if status.cancel_requested:
            return self._finish_cancelled(job_id)
        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "CLASSIFIERS started")

        for key in status.classifier_keys:
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(job_id)
            if not payload.tracks_by_classifier[key]:
                continue
            requirement = payload.requirements[key]
            self._update(job_id, current_model=key, model_name=str(requirement.model_path))
            try:
                scorer = self._make_scorer(key, requirement.model_path)
            except Exception as error:
                error_text = exception_summary(error)
                self._update(job_id, state="failed", finished_at=time.time(), current_model=None, current_path=None)
                self._append_event(job_id, "error", f"{key} initialization failed: {error_text}", model=key)
                return self.get(job_id)
            for warning in getattr(scorer, "manifest_warnings", ()):
                self._append_event(job_id, "warn", str(warning), model=key)
            for track in payload.tracks_by_classifier[key]:
                if self.get(job_id).cancel_requested:
                    return self._finish_cancelled(job_id)
                self._score_one(job_id, key, scorer, track)

        finished = time.time()
        final = self.get(job_id)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            current_model=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / max(1, final.processed),
        )
        self._append_event(job_id, "info", "CLASSIFIERS completed")
        return self.get(job_id)

    def _score_one(self, job_id: str, classifier: str, scorer: _Scorer, track: Track) -> None:
        self._update(job_id, current_path=track.path)
        try:
            result = scorer.score_track(track)
            if result is None:
                self._update_progress(job_id, classifier, skipped=1)
                return
            scorer.save_score(track, result)
            self._update_progress(job_id, classifier, analyzed=1)
        except Exception as error:
            self._save_failure(job_id, classifier, track, error)

    def _update_progress(self, job_id: str, classifier: str, *, analyzed: int = 0, skipped: int = 0) -> None:
        with self._store.locked(job_id) as status:
            status.processed += 1
            status.analyzed += analyzed
            status.skipped += skipped
            progress = status.model_progress[classifier]
            progress.processed += 1
            progress.analyzed += analyzed
            progress.skipped += skipped
            if status.started_at:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed

    def _save_failure(self, job_id: str, classifier: str, track: Track, error: Exception) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Classifier track failed job_id=%s classifier=%s track_id=%s path=%s error=%s",
            job_id,
            classifier,
            track.id,
            track.path,
            error_text,
        )
        with self._store.locked(job_id) as status:
            status.current_path = track.path
            status.processed += 1
            status.failed += 1
            progress = status.model_progress[classifier]
            progress.processed += 1
            progress.failed += 1
            status.errors.append(ClassifierTrackError(track.id, track.path, error_text, classifier))
        self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id, model=classifier)

    def _load_requirements(self, classifier: str) -> ClassifierRequirements:
        if self._requirements_loader is not None:
            return self._requirements_loader(classifier)
        return load_classifier_requirements(classifier)

    def _make_scorer(self, classifier: str, path: Path) -> _Scorer:
        if self._scorer_factory is not None:
            return self._scorer_factory(classifier, path)
        return ClassifierScorer(self.db, classifier=classifier, model_path=path)

    def get(self, job_id: str, *, classifier: str | None = None) -> ClassifierJobStatus:
        status = self._store.get(job_id)
        if classifier is not None and classifier not in status.classifier_keys:
            raise KeyError(f"Unknown classifier job for {classifier}: {job_id}")
        return status

    def latest(self, *, classifier: str | None = None) -> ClassifierJobStatus | None:
        if classifier is None:
            return self._store.latest()
        return self._store.latest_matching(lambda status: classifier in status.classifier_keys)

    def cancel(self, job_id: str, *, classifier: str | None = None) -> ClassifierJobStatus:
        self.get(job_id, classifier=classifier)
        self._update(job_id, cancel_requested=True)
        return self.get(job_id, classifier=classifier)

    def _finish_cancelled(self, job_id: str) -> ClassifierJobStatus:
        self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
        self._append_event(job_id, "warn", "CLASSIFIERS cancelled")
        return self.get(job_id)

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    def _append_event(
        self,
        job_id: str,
        level: str,
        message: str,
        *,
        path: str | None = None,
        track_id: int | None = None,
        model: str | None = None,
    ) -> None:
        log_job_event(
            LOGGER,
            level,
            "%s job_id=%s classifier=%s track_id=%s path=%s",
            message,
            job_id,
            model,
            track_id,
            path,
            track_event=False,
        )
        self._store.append_event(job_id, ClassifierLogEvent(time.time(), level, message, path, track_id, model))

    @staticmethod
    def _copy_status(status: ClassifierJobStatus) -> ClassifierJobStatus:
        return ClassifierJobStatus(
            job_id=status.job_id,
            state=status.state,
            adapter_name=status.adapter_name,
            embedding_key=status.embedding_key,
            classifier_keys=list(status.classifier_keys),
            current_model=status.current_model,
            model_progress={
                key: AnalysisModelProgress(
                    total=value.total,
                    processed=value.processed,
                    analyzed=value.analyzed,
                    failed=value.failed,
                    skipped=value.skipped,
                )
                for key, value in status.model_progress.items()
            },
            readiness={key: dict(value) for key, value in status.readiness.items()},
            blockers={key: list(value) for key, value in status.blockers.items()},
            model_name=status.model_name,
            device=status.device,
            device_requested=status.device_requested,
            total=status.total,
            processed=status.processed,
            analyzed=status.analyzed,
            skipped=status.skipped,
            failed=status.failed,
            not_ready=status.not_ready,
            current_path=status.current_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_track=status.avg_seconds_per_track,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
            workers=status.workers,
            batch_size=status.batch_size,
        )


def _clean_classifier_keys(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))

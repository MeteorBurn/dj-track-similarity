from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from .analysis_job_state import AnalysisModelProgress
from .analysis_models import (
    ClassifierCandidate,
    ClassifierFeatureRow,
    ClassifierReadiness,
    ClassifierScoreWrite,
    ClassifierSpecification,
)
from .analysis_queue import AnalysisStageQueue
from .classifier_scoring import (
    ClassifierRequirements,
    ClassifierScorer,
    load_classifier_requirements,
    require_current_classifier_output,
)
from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event


LOGGER = logging.getLogger(__name__)


class _Scorer(Protocol):
    model_name: str
    manifest_warnings: Sequence[str]
    specification: ClassifierSpecification

    def score_row(self, row: ClassifierFeatureRow) -> ClassifierScoreWrite: ...


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
    required_families: tuple[str, ...] = ()
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
class _ClassifierWorkItem:
    candidate: ClassifierCandidate
    row: ClassifierFeatureRow


@dataclass(frozen=True)
class _ClassifierPayload:
    work_by_classifier: dict[str, tuple[_ClassifierWorkItem, ...]]
    requirements: dict[str, ClassifierRequirements]
    scorers: dict[str, _Scorer]


class ClassifierJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        *,
        stage_queue: AnalysisStageQueue | None = None,
        scorer_factory: Callable[[ClassifierRequirements], _Scorer] | None = None,
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
        keys = _clean_classifier_keys(
            [*(classifiers or ()), *([classifier] if classifier else [])]
        )
        if not keys:
            raise ValueError(
                "At least one scoring-compatible promoted classifier must be selected"
            )
        if model_path is not None and len(keys) != 1:
            raise ValueError(
                "A custom classifier model path can only be used with one classifier"
            )

        requirements = {
            key: (
                load_classifier_requirements(
                    self.db,
                    key,
                    model_path=model_path,
                )
                if model_path is not None
                else self._load_requirements(key)
            )
            for key in keys
        }
        for key, requirement in requirements.items():
            if requirement.specification.classifier_key != key:
                raise ValueError(
                    "Classifier requirements key mismatch: "
                    f"expected {key!r}, got "
                    f"{requirement.specification.classifier_key!r}"
                )

        # Construct every scorer before the first cleanup. ClassifierScorer
        # re-verifies the artifact digest and validates the deserialized model,
        # so a bad artifact can never trigger score deletion.
        scorers = {
            key: self._make_scorer(requirement)
            for key, requirement in requirements.items()
        }
        for key, scorer in scorers.items():
            expected = requirements[key].specification
            if scorer.specification != expected:
                raise ValueError(
                    f"{key} scorer specification does not match its manifest"
                )

        # Preflight every immutable input identity before the first mutation.
        # prepare_classifier_rescore() repeats this check transactionally.
        self._require_active_outputs(requirements.values())

        for requirement in requirements.values():
            self.db.prepare_classifier_rescore(requirement.specification)

        work_by_classifier: dict[str, tuple[_ClassifierWorkItem, ...]] = {}
        readiness: dict[str, dict[str, int]] = {}
        progress: dict[str, AnalysisModelProgress] = {}
        remaining = None if limit is None else max(0, int(limit))
        for key in keys:
            specification = requirements[key].specification
            counts = self.db.classifier_candidate_readiness(specification)
            candidates = self.db.list_classifier_candidates(specification)
            rows = self.db.load_classifier_feature_rows(
                specification,
                targets=tuple(candidate.target for candidate in candidates),
            )
            rows_by_target = {row.target: row for row in rows}
            complete = tuple(
                _ClassifierWorkItem(candidate, rows_by_target[candidate.target])
                for candidate in candidates
                if candidate.target in rows_by_target
            )
            selected = (
                ()
                if remaining == 0
                else complete
                if remaining is None
                else complete[:remaining]
            )
            if remaining is not None:
                remaining -= len(selected)
            feature_not_ready = len(candidates) - len(complete)
            readiness[key] = _readiness_payload(
                counts,
                feature_not_ready=feature_not_ready,
                selected=len(selected),
            )
            work_by_classifier[key] = selected
            progress[key] = AnalysisModelProgress(total=len(selected))

        job_id = str(uuid.uuid4())
        total = sum(len(items) for items in work_by_classifier.values())
        status = ClassifierJobStatus(
            job_id=job_id,
            state="queued",
            adapter_name=keys[0] if len(keys) == 1 else "classifiers",
            required_families=tuple(
                dict.fromkeys(
                    output.contract.analysis_family
                    for requirement in requirements.values()
                    for output in requirement.specification.required_outputs
                )
            ),
            classifier_keys=list(keys),
            model_progress=progress,
            readiness=readiness,
            total=total,
            not_ready=sum(counts["not_ready"] for counts in readiness.values()),
        )
        self._store.add(
            job_id,
            status,
            payload=_ClassifierPayload(
                work_by_classifier=work_by_classifier,
                requirements=requirements,
                scorers=scorers,
            ),
        )
        self._append_event(job_id, "info", f"CLASSIFIERS queued · profiles {len(keys)}")
        return job_id

    def readiness(
        self, classifiers: Sequence[str]
    ) -> dict[str, dict[str, int | list[str]]]:
        result: dict[str, dict[str, int | list[str]]] = {}
        for key in _clean_classifier_keys(classifiers):
            try:
                requirement = self._load_requirements(key)
                specification = requirement.specification
                counts = self.db.classifier_candidate_readiness(specification)
                candidates = self.db.list_classifier_candidates(specification)
                rows = self.db.load_classifier_feature_rows(
                    specification,
                    targets=tuple(candidate.target for candidate in candidates),
                )
                feature_not_ready = len(candidates) - len(rows)
                result[key] = {
                    **_readiness_payload(
                        counts,
                        feature_not_ready=feature_not_ready,
                    ),
                    "blockers": [],
                }
            except (FileNotFoundError, RuntimeError, ValueError) as error:
                result[key] = {
                    "candidates": 0,
                    "ready": 0,
                    "not_ready": 0,
                    "blockers": [str(error)],
                }
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
            if not payload.work_by_classifier[key]:
                continue
            requirement = payload.requirements[key]
            self._update(
                job_id, current_model=key, model_name=str(requirement.model_path)
            )
            scorer = payload.scorers[key]
            for warning in getattr(scorer, "manifest_warnings", ()):
                self._append_event(job_id, "warn", str(warning), model=key)
            for item in payload.work_by_classifier[key]:
                if self.get(job_id).cancel_requested:
                    return self._finish_cancelled(job_id)
                self._score_one(job_id, key, scorer, item)

        finished = time.time()
        final = self.get(job_id)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            current_model=None,
            avg_seconds_per_track=(finished - (final.started_at or started))
            / max(1, final.processed),
        )
        self._append_event(job_id, "info", "CLASSIFIERS completed")
        return self.get(job_id)

    def _score_one(
        self,
        job_id: str,
        classifier: str,
        scorer: _Scorer,
        item: _ClassifierWorkItem,
    ) -> None:
        candidate = item.candidate
        self._update(job_id, current_path=candidate.file_path)
        try:
            write = scorer.score_row(item.row)
            if write.target != candidate.target:
                raise ValueError(
                    "classifier scorer returned a different analysis target"
                )
            results = self.db.save_classifier_scores((write,))
            if len(results) != 1 or not results[0].ok:
                error = results[0].error if results else None
                raise RuntimeError(error or "classifier score write failed")
            self._update_progress(job_id, classifier, analyzed=1)
        except Exception as error:
            self._save_failure(job_id, classifier, candidate, error)

    def _update_progress(
        self, job_id: str, classifier: str, *, analyzed: int = 0, skipped: int = 0
    ) -> None:
        with self._store.locked(job_id) as status:
            status.processed += 1
            status.analyzed += analyzed
            status.skipped += skipped
            progress = status.model_progress[classifier]
            progress.processed += 1
            progress.analyzed += analyzed
            progress.skipped += skipped
            if status.started_at:
                status.avg_seconds_per_track = (
                    time.time() - status.started_at
                ) / status.processed

    def _save_failure(
        self,
        job_id: str,
        classifier: str,
        candidate: ClassifierCandidate,
        error: Exception,
    ) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Classifier track failed job_id=%s classifier=%s track_id=%s path=%s error=%s",
            job_id,
            classifier,
            candidate.target.track_id,
            candidate.file_path,
            error_text,
        )
        with self._store.locked(job_id) as status:
            status.current_path = candidate.file_path
            status.processed += 1
            status.failed += 1
            progress = status.model_progress[classifier]
            progress.processed += 1
            progress.failed += 1
            status.errors.append(
                ClassifierTrackError(
                    candidate.target.track_id,
                    candidate.file_path,
                    error_text,
                    classifier,
                )
            )
        self._append_event(
            job_id,
            "error",
            f"Track failed: {error_text}",
            path=candidate.file_path,
            track_id=candidate.target.track_id,
            model=classifier,
        )

    def _load_requirements(self, classifier: str) -> ClassifierRequirements:
        if self._requirements_loader is not None:
            return self._requirements_loader(classifier)
        return load_classifier_requirements(self.db, classifier)

    def _make_scorer(self, requirement: ClassifierRequirements) -> _Scorer:
        if self._scorer_factory is not None:
            return self._scorer_factory(requirement)
        return ClassifierScorer(requirement)

    def _require_active_outputs(
        self,
        requirements: Iterable[ClassifierRequirements],
    ) -> None:
        for requirement in requirements:
            for output in requirement.specification.required_outputs:
                try:
                    require_current_classifier_output(output)
                except ValueError as error:
                    family, kind = output.key
                    raise RuntimeError(
                        "required classifier output contract does not match "
                        f"the current adapter identity: {family}/{kind}"
                    ) from error
                active = self.db.active_analysis_output(*output.key)
                if active is None:
                    family, kind = output.key
                    raise RuntimeError(
                        f"required classifier output is not active: {family}/{kind}"
                    )
                if (
                    active.contract_hash != output.contract_hash
                    or active.contract.canonical_payload_json
                    != output.contract.canonical_payload_json
                ):
                    family, kind = output.key
                    raise RuntimeError(
                        "required classifier output contract is not current: "
                        f"{family}/{kind}"
                    )

    def get(self, job_id: str, *, classifier: str | None = None) -> ClassifierJobStatus:
        status = self._store.get(job_id)
        if classifier is not None and classifier not in status.classifier_keys:
            raise KeyError(f"Unknown classifier job for {classifier}: {job_id}")
        return status

    def latest(self, *, classifier: str | None = None) -> ClassifierJobStatus | None:
        if classifier is None:
            return self._store.latest()
        return self._store.latest_matching(
            lambda status: classifier in status.classifier_keys
        )

    def cancel(
        self, job_id: str, *, classifier: str | None = None
    ) -> ClassifierJobStatus:
        self.get(job_id, classifier=classifier)
        self._update(job_id, cancel_requested=True)
        return self.get(job_id, classifier=classifier)

    def _finish_cancelled(self, job_id: str) -> ClassifierJobStatus:
        self._update(
            job_id,
            state="cancelled",
            finished_at=time.time(),
            current_path=None,
            current_model=None,
        )
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
        self._store.append_event(
            job_id,
            ClassifierLogEvent(time.time(), level, message, path, track_id, model),
        )

    @staticmethod
    def _copy_status(status: ClassifierJobStatus) -> ClassifierJobStatus:
        return ClassifierJobStatus(
            job_id=status.job_id,
            state=status.state,
            adapter_name=status.adapter_name,
            required_families=tuple(status.required_families),
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
    return tuple(
        dict.fromkeys(value.strip() for value in values if value and value.strip())
    )


def _readiness_payload(
    readiness: ClassifierReadiness,
    *,
    feature_not_ready: int = 0,
    selected: int | None = None,
) -> dict[str, int]:
    feature_missing = max(0, int(feature_not_ready))
    payload = {
        "candidates": readiness.total_tracks,
        "ready": max(0, readiness.ready_tracks - feature_missing),
        "not_ready": readiness.missing_input_tracks + feature_missing,
    }
    if selected is not None:
        payload["selected"] = selected
    return payload

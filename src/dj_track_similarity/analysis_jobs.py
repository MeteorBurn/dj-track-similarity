from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence, cast

from .analysis_job_batch import AnalysisBatchItem, DecodeAudio, decode_analysis_batch
from .analysis_job_state import (
    AnalysisJobStatus,
    AnalysisLogEvent,
    AnalysisModelProgress,
    AnalysisTrackError,
    AnalysisTrackOutcome,
    copy_analysis_status,
    initial_model_progress,
    initial_track_outcomes,
    mark_track_processed as apply_track_processed,
    record_model_failure as apply_model_failure,
    record_model_success as apply_model_success,
    record_track_model_result as apply_track_model_result,
)
from .analysis_model_runners import (
    AnalysisModelRunner,
    EmbeddingModelRunner,
    MaestModelRunner,
    RunnerFactory,
    SonaraModelRunner,
    _default_model_runners,
)
from .audio_loader import load_decoded_audio
from .classifier_scoring import ClassifierScorer
from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    normalize_analysis_models,
)
from .database import LibraryDatabase
from .job_runtime import JobStore, chunks
from .logging_config import exception_summary, log_failure, log_job_event
from .models import AnalysisCandidate, Track


LOGGER = logging.getLogger(__name__)
CLASSIFIER_REQUIRED_MODELS = ("sonara", "maest", "mert")


__all__ = [
    "AnalysisBatchItem",
    "AnalysisJobManager",
    "AnalysisJobStatus",
    "AnalysisLogEvent",
    "AnalysisModelProgress",
    "AnalysisModelRunner",
    "AnalysisTrackError",
    "AnalysisTrackOutcome",
    "DecodeAudio",
    "EmbeddingModelRunner",
    "MaestModelRunner",
    "RunnerFactory",
    "SonaraModelRunner",
]


@dataclass(frozen=True)
class _AnalysisWork:
    tracks: list[Track]
    audio_targets_by_track: dict[int, tuple[str, ...]]
    classifier_targets_by_track: dict[int, tuple[str, ...]]
    model_progress: dict[str, AnalysisModelProgress]
    track_outcomes: dict[int, AnalysisTrackOutcome]
    models: tuple[str, ...]


class AnalysisJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        model_runners: Mapping[str, AnalysisModelRunner] | None = None,
        *,
        decode_audio: DecodeAudio = load_decoded_audio,
        runner_factory: RunnerFactory | None = None,
        classifier_scorer_factory: Callable[[str], Any] | None = None,
        track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
        inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    ) -> None:
        self.db = db
        self._model_runners = dict(model_runners) if model_runners is not None else None
        self._runner_factory = runner_factory or _default_model_runners
        self._classifier_scorer_factory = classifier_scorer_factory
        self._decode_audio = decode_audio
        self.track_batch_size = max(1, int(track_batch_size))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._store = JobStore(self._copy_status, unknown_label="analysis job")

    def create_job(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
        classifier_keys: Sequence[str] | None = None,
    ) -> str:
        selected_classifier_keys = self._clean_classifier_keys(classifier_keys)
        selected = _normalize_job_models(models, allow_empty=bool(selected_classifier_keys))
        work = self._analysis_work(selected, selected_classifier_keys, limit=limit)
        job_id = str(uuid.uuid4())
        effective_track_batch_size = max(1, int(track_batch_size if track_batch_size is not None else self.track_batch_size))
        effective_inference_batch_size = max(
            1,
            int(inference_batch_size if inference_batch_size is not None else self.inference_batch_size),
        )
        status = AnalysisJobStatus(
            job_id=job_id,
            state="queued",
            models=list(work.models),
            classifier_keys=list(selected_classifier_keys),
            model_progress=work.model_progress,
            total=len(work.tracks),
            device_requested=device,
            workers=effective_track_batch_size,
            track_batch_size=effective_track_batch_size,
            inference_batch_size=effective_inference_batch_size,
            top_k=max(1, int(top_k)),
        )
        self._store.add(
            job_id,
            status,
            payload={
                "tracks": work.tracks,
                "targets_by_track": work.audio_targets_by_track,
                "classifier_targets_by_track": work.classifier_targets_by_track,
                "track_outcomes": work.track_outcomes,
            },
        )
        self._append_event(job_id, "info", "Analysis queued")
        return job_id

    def _analysis_work(
        self,
        selected: tuple[str, ...],
        classifier_keys: tuple[str, ...],
        *,
        limit: int | None,
    ) -> _AnalysisWork:
        candidates_by_id: dict[int, AnalysisCandidate] = {}
        for candidate in self.db.list_analysis_candidates(selected, limit=limit):
            candidates_by_id[candidate.id] = candidate

        classifier_targets: dict[int, list[str]] = {}
        for classifier in classifier_keys:
            for track in self.db.list_tracks_missing_classifier(classifier, limit=limit):
                classifier_targets.setdefault(track.id, []).append(classifier)
                candidates_by_id.setdefault(track.id, _candidate_from_track(track))

        effective_models = tuple(model for model in ANALYSIS_MODEL_ORDER if model in selected)
        candidates: list[AnalysisCandidate] = []
        audio_targets_by_track: dict[int, tuple[str, ...]] = {}
        classifier_targets_by_track: dict[int, tuple[str, ...]] = {}
        combined_targets_by_track: dict[int, tuple[str, ...]] = {}

        for candidate in candidates_by_id.values():
            classifiers_for_track = tuple(classifier_targets.get(candidate.id, ()))
            audio_targets = _audio_targets_for_candidate(candidate, selected, classifiers_for_track)
            if not audio_targets and not classifiers_for_track:
                continue
            candidates.append(candidate)
            audio_targets_by_track[candidate.id] = audio_targets
            if classifiers_for_track:
                classifier_targets_by_track[candidate.id] = classifiers_for_track
            combined_targets_by_track[candidate.id] = (*audio_targets, *classifiers_for_track)

        candidates.sort(key=lambda candidate: (candidate.artist or "", candidate.title or "", candidate.path))
        if limit is not None:
            candidates = candidates[: max(0, int(limit))]
            candidate_ids = {candidate.id for candidate in candidates}
            audio_targets_by_track = {
                track_id: targets for track_id, targets in audio_targets_by_track.items() if track_id in candidate_ids
            }
            classifier_targets_by_track = {
                track_id: targets for track_id, targets in classifier_targets_by_track.items() if track_id in candidate_ids
            }
            combined_targets_by_track = {
                track_id: targets for track_id, targets in combined_targets_by_track.items() if track_id in candidate_ids
            }

        tracks = [candidate.to_track() for candidate in candidates]
        progress_keys = (*effective_models, *classifier_keys)
        return _AnalysisWork(
            tracks=tracks,
            audio_targets_by_track=audio_targets_by_track,
            classifier_targets_by_track=classifier_targets_by_track,
            model_progress=initial_model_progress(progress_keys, combined_targets_by_track),
            track_outcomes=initial_track_outcomes(tracks, combined_targets_by_track),
            models=effective_models,
        )

    def start(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
        classifier_keys: Sequence[str] | None = None,
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            models=models,
            limit=limit,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            device=device,
            top_k=top_k,
            classifier_keys=classifier_keys,
        )
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
        classifier_keys: Sequence[str] | None = None,
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            models=models,
            limit=limit,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            device=device,
            top_k=top_k,
            classifier_keys=classifier_keys,
        )
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> AnalysisJobStatus:
        status = self.get(job_id)
        payload = cast(dict[str, object], self._store.payload(job_id) or {})
        tracks = cast(list[Track], payload.get("tracks") or [])
        targets_by_track = cast(dict[int, tuple[str, ...]], payload.get("targets_by_track") or {})
        classifier_targets_by_track = cast(dict[int, tuple[str, ...]], payload.get("classifier_targets_by_track") or {})
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Analysis cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Analysis started")
        runners: dict[str, AnalysisModelRunner] = {}
        failed_model_inits: dict[str, str] = {}
        scorers: dict[str, Any] = {}

        for batch in chunks(tracks, max(1, status.track_batch_size)):
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
                self._append_event(job_id, "warn", "Analysis cancelled")
                return self.get(job_id)
            self._process_batch(job_id, runners, failed_model_inits, batch, targets_by_track, classifier_targets_by_track)
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
                self._append_event(job_id, "warn", "Analysis cancelled")
                return self.get(job_id)
            batch_classifier_targets = {
                track.id: classifier_targets_by_track[track.id]
                for track in batch
                if track.id in classifier_targets_by_track
            }
            if batch_classifier_targets and not self._run_classifier_stage(job_id, batch_classifier_targets, scorers):
                return self.get(job_id)

        finished = time.time()
        final = self.get(job_id)
        processed = max(1, final.processed)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            current_model=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / processed,
        )
        self._append_event(job_id, "info", "Analysis completed")
        return self.get(job_id)

    def _run_classifier_stage(
        self,
        job_id: str,
        classifier_targets_by_track: Mapping[int, tuple[str, ...]],
        scorers: dict[str, Any],
    ) -> bool:
        for track_id, classifier_keys in classifier_targets_by_track.items():
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
                self._append_event(job_id, "warn", "Analysis cancelled")
                return False

            try:
                track = self.db.get_track(track_id)
            except Exception as error:
                for classifier in classifier_keys:
                    self._record_classifier_failure(job_id, classifier, None, error)
                continue

            for classifier in classifier_keys:
                if self.get(job_id).cancel_requested:
                    self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
                    self._append_event(job_id, "warn", f"{classifier} classification cancelled", model=classifier)
                    return False
                self._update(job_id, current_model=classifier, model_name=classifier, device="cpu", current_path=track.path)
                self._append_event(job_id, "info", f"{classifier} classification started", path=track.path, track_id=track.id, model=classifier)
                try:
                    scorer = scorers.get(classifier)
                    if scorer is None:
                        scorer = self._classifier_scorer(classifier)
                        scorers[classifier] = scorer
                    self._update(job_id, model_name=str(getattr(scorer, "model_name", classifier)))
                except Exception as error:
                    error_text = exception_summary(error)
                    self._update(job_id, state="failed", finished_at=time.time(), current_path=None, current_model=None)
                    self._append_event(job_id, "error", f"{classifier} classification failed: {error_text}", model=classifier)
                    return False
                self._score_classifier_track(job_id, classifier, scorer, track)
                self._append_event(job_id, "info", f"{classifier} classification completed", path=track.path, track_id=track.id, model=classifier)
            self._mark_track_processed(job_id, track)
        return True

    def _classifier_scorer(self, classifier: str) -> Any:
        if self._classifier_scorer_factory is not None:
            return self._classifier_scorer_factory(classifier)
        return ClassifierScorer(self.db, classifier=classifier)

    def _score_classifier_track(self, job_id: str, classifier: str, scorer: Any, track: Track) -> None:
        self._update(job_id, current_path=track.path)
        try:
            result = scorer.score_track(track)
            if result is None:
                self._record_classifier_skip(job_id, classifier)
                return
            scorer.save_score(track, result)
            self._record_classifier_success(job_id, classifier, track)
            self._append_event(job_id, "ok", "Classifier analyzed", path=track.path, track_id=track.id, model=classifier)
        except Exception as error:
            self._record_classifier_failure(job_id, classifier, track, error)

    def _record_classifier_success(self, job_id: str, classifier: str, track: Track) -> None:
        self._record_track_model_result(job_id, track.id, failed=False)
        with self._store.locked(job_id) as status:
            apply_model_success(status, classifier)

    def _record_classifier_skip(self, job_id: str, classifier: str) -> None:
        with self._store.locked(job_id) as status:
            progress = status.model_progress[classifier]
            progress.processed += 1
            progress.skipped += 1

    def _record_classifier_failure(self, job_id: str, classifier: str, track: Track | None, error: Exception) -> None:
        error_text = exception_summary(error)
        path = track.path if track is not None else ""
        track_id = track.id if track is not None else -1
        log_failure(
            LOGGER,
            "Classifier track failed job_id=%s classifier=%s track_id=%s path=%s error=%s",
            job_id,
            classifier,
            track_id,
            path,
            error_text,
        )
        if track is not None:
            self._record_track_model_result(job_id, track.id, failed=True)
        with self._store.locked(job_id) as status:
            apply_model_failure(
                status,
                classifier,
                AnalysisTrackError(track_id=track_id, path=path, error=error_text, model=classifier),
            )
        self._append_event(job_id, "error", f"Classifier failed: {error_text}", path=path or None, track_id=track_id if track is not None else None, model=classifier)

    def get(self, job_id: str) -> AnalysisJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AnalysisJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _process_batch(
        self,
        job_id: str,
        runners: dict[str, AnalysisModelRunner],
        failed_model_inits: dict[str, str],
        batch: list[Track],
        targets_by_track: Mapping[int, tuple[str, ...]],
        classifier_targets_by_track: Mapping[int, tuple[str, ...]],
    ) -> None:
        decoded_items = decode_analysis_batch(
            batch,
            targets_by_track,
            self._decode_audio,
            set_current_path=lambda path: self._update(job_id, current_path=path),
            record_decode_failure=lambda track, targets, error: self._record_decode_failure(job_id, track, targets, error),
            mark_track_processed=lambda track: self._mark_track_processed(job_id, track),
            should_defer_processed=lambda track: bool(classifier_targets_by_track.get(track.id)),
        )

        for model in ANALYSIS_MODEL_ORDER:
            model_items = [item for item in decoded_items if model in item.models]
            if not model_items:
                continue
            if self.get(job_id).cancel_requested:
                return
            if model in failed_model_inits:
                for item in model_items:
                    self._record_model_failure(job_id, model, item.track, RuntimeError(failed_model_inits[model]))
                continue
            try:
                runner = runners.get(model)
                if runner is None:
                    runner = self._runner_for_model(model, self.get(job_id))
                    runners[model] = runner
            except Exception as error:
                error_text = exception_summary(error)
                failed_model_inits[model] = error_text
                self._append_event(job_id, "error", f"{model} initialization failed: {error_text}", model=model)
                for item in model_items:
                    self._record_model_failure(job_id, model, item.track, RuntimeError(error_text))
                continue
            self._update(job_id, current_model=model, model_name=getattr(runner, "model_name", model), device=getattr(runner, "device", None))
            self._run_model_batch(job_id, model, runner, model_items)

        for item in decoded_items:
            if not classifier_targets_by_track.get(item.track.id):
                self._mark_track_processed(job_id, item.track)

    def _record_decode_failure(self, job_id: str, track: Track, targets: tuple[str, ...], error: Exception) -> None:
        for model in targets:
            self._record_model_failure(job_id, model, track, error, emit_event=False)
        self._append_event(
            job_id,
            "error",
            f"Track decode failed: {exception_summary(error)}",
            path=track.path,
            track_id=track.id,
        )

    def _runner_for_model(self, model: str, status: AnalysisJobStatus) -> AnalysisModelRunner:
        if self._model_runners is not None:
            try:
                return self._model_runners[model]
            except KeyError as error:
                raise ValueError(f"No analysis runner configured for: {model}") from error
        return self._runner_factory(model, status.device_requested, status.inference_batch_size, status.top_k)

    def _run_model_batch(
        self,
        job_id: str,
        model: str,
        runner: AnalysisModelRunner,
        items: list[AnalysisBatchItem],
    ) -> None:
        try:
            runner.analyze_batch(self.db, items)
            for item in items:
                self._record_model_success(job_id, model, item.track)
            return
        except Exception as error:
            if len(items) <= 1:
                self._record_model_failure(job_id, model, items[0].track, error)
                return
            LOGGER.warning(
                "Analysis model batch failed; retrying tracks individually job_id=%s model=%s batch_size=%s error=%s",
                job_id,
                model,
                len(items),
                exception_summary(error),
            )
            self._append_event(job_id, "warn", f"{model} batch failed; retrying tracks individually", model=model)

        for item in items:
            try:
                runner.analyze_batch(self.db, [item])
                self._record_model_success(job_id, model, item.track)
            except Exception as error:
                self._record_model_failure(job_id, model, item.track, error)

    def _record_model_success(self, job_id: str, model: str, track: Track) -> None:
        self._record_track_model_result(job_id, track.id, failed=False)
        with self._store.locked(job_id) as status:
            apply_model_success(status, model)

    def _record_model_failure(self, job_id: str, model: str, track: Track, error: Exception, *, emit_event: bool = True) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Analysis model failed job_id=%s model=%s track_id=%s path=%s error=%s",
            job_id,
            model,
            track.id,
            track.path,
            error_text,
        )
        self._record_track_model_result(job_id, track.id, failed=True)
        with self._store.locked(job_id) as status:
            apply_model_failure(
                status,
                model,
                AnalysisTrackError(track_id=track.id, path=track.path, error=error_text, model=model),
            )
        if emit_event:
            self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id, model=model)

    def _mark_track_processed(self, job_id: str, track: Track) -> None:
        outcome = self._track_outcome(job_id, track.id)
        analyzed = False
        with self._store.locked(job_id) as status:
            analyzed = apply_track_processed(status, track_path=track.path, outcome=outcome, now=time.time())
        if analyzed:
            self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)

    def _record_track_model_result(self, job_id: str, track_id: int, *, failed: bool) -> None:
        apply_track_model_result(self._track_outcome(job_id, track_id), failed=failed)

    def _track_outcome(self, job_id: str, track_id: int) -> AnalysisTrackOutcome | None:
        payload = cast(dict[str, object], self._store.payload(job_id) or {})
        outcomes = cast(dict[int, AnalysisTrackOutcome], payload.get("track_outcomes") or {})
        return outcomes.get(track_id)

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
            "%s job_id=%s model=%s track_id=%s path=%s",
            message,
            job_id,
            model,
            track_id,
            path,
            track_event=level == "ok",
        )
        self._store.append_event(job_id, AnalysisLogEvent(time.time(), level, message, path, track_id, model))

    @staticmethod
    def _clean_classifier_keys(classifier_keys: Sequence[str] | None) -> tuple[str, ...]:
        if classifier_keys is None:
            return ()
        return tuple(dict.fromkeys(key.strip() for key in classifier_keys if key.strip()))

    @staticmethod
    def _copy_status(status: AnalysisJobStatus) -> AnalysisJobStatus:
        return copy_analysis_status(status)


def _candidate_from_track(track: Track) -> AnalysisCandidate:
    return AnalysisCandidate(
        id=track.id,
        path=track.path,
        size=track.size,
        mtime=track.mtime,
        artist=track.artist,
        title=track.title,
        album=track.album,
        bpm=track.bpm,
        musical_key=track.musical_key,
        energy=track.energy,
        duration=track.duration,
        analyses=tuple(track.analyses or ()),
    )


def _audio_targets_for_candidate(
    candidate: AnalysisCandidate,
    selected: Sequence[str],
    classifier_targets: Sequence[str],
) -> tuple[str, ...]:
    analyses = set(candidate.analyses)
    if classifier_targets:
        missing_required = tuple(
            model for model in CLASSIFIER_REQUIRED_MODELS if model not in analyses and model not in selected
        )
        if missing_required:
            missing = ", ".join(model.upper() for model in missing_required)
            raise ValueError(
                "CLASSIFIERS require SONARA, MAEST, and MERT data; "
                f"select missing models in the same run or analyze them first. Missing: {missing}"
            )
    required = set(selected)
    return tuple(model for model in ANALYSIS_MODEL_ORDER if model in required and model not in analyses)


def _normalize_job_models(models: Sequence[str] | None, *, allow_empty: bool) -> tuple[str, ...]:
    if allow_empty and models is not None and not models:
        return ()
    return normalize_analysis_models(models)

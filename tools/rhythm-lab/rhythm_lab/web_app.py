from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from dj_track_similarity.classifier.manifest import load_classifier_manifest_summary
from dj_track_similarity.audio.ffmpeg_runtime import configure_shared_ffmpeg_runtime
from dj_track_similarity.logging_config import install_asyncio_exception_logging
from dj_track_similarity.api.media_preview import requires_browser_preview_transcode, transcoded_wav_file_response
from dj_track_similarity.rhythm_lab_collections import (
    RhythmLabCollectionSelection,
    RhythmLabCollections,
    RhythmLabTrackSelection,
)

from .ablation import (
    DEFAULT_BENCHMARK_STRATEGY,
    benchmark_plan,
    planned_run_count,
    run_ablation_benchmark,
)
from .cli import (
    DEFAULT_CLASSIFIER_TARGET_ROOT,
    PromotionError,
    artifact_feature_set,
    canonical_artifact_feature_set,
    promote_profile_model,
)
from .features import (
    SUPPORTED_FEATURE_SOURCES,
    artifact_feature_compatibility,
    artifact_source_readiness,
    available_feature_sources,
    build_labeled_feature_matrix_from_sources,
    canonical_feature_set,
    default_feature_set,
    feature_recipe_readiness,
    feature_sources,
    split_feature_source,
    stored_mert_v2_layers,
)
from .lab_db import DEFAULT_TRAINING_MIN_LABELS, ClassifierProfile, RhythmLabDatabase
from .predictions import apply_model_to_lab
from .source_db import (
    MERT_V2_DEFAULT_LAYER,
    SourceDatabase,
    SourceDatabaseError,
    SourceTrackNotCurrentError,
)
from .training import (
    MIN_CALIBRATION_LABELS,
    MIN_CALIBRATION_NEGATIVE,
    MIN_CALIBRATION_POSITIVE,
    benchmark_lab_database,
)


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")
FAVICON_PATH = STATIC_DIR / "favicon.svg"
TRAIN_REFRESH_MIN_ADDED = 50
MIN_TRAINING_ROWS_PER_LABEL = 2
KEEP_JOBLIB_PER_FEATURE = 3
KEEP_METRICS_PER_FEATURE = 10
_NO_SOURCE_DATA_DETAIL = (
    "The selected library has no stored feature sources; "
    "run analysis in the main app, then reload the library."
)


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class TrackLikedRequest(BaseModel):
    catalog_uuid: str
    track_uuid: str
    liked: bool


class CollectionSaveRequest(BaseModel):
    name: str
    track_ids: list[int] = []
    source: str = "manual"
    note: str | None = None
    mode: str = "append"


class CollectionTracksRequest(BaseModel):
    track_ids: list[int]
    mode: str = "append"


class SourceSwitchRequest(BaseModel):
    path: str


class ProfileLabelRequest(BaseModel):
    key: str
    name: str | None = None
    description: str = ""
    role: str


class ProfileRequest(BaseModel):
    classifier_key: str
    profile_type: str = "binary"
    name: str
    description: str = ""
    artifact_prefix: str | None = None
    training_min_added: int = TRAIN_REFRESH_MIN_ADDED
    training_min_labels: int = DEFAULT_TRAINING_MIN_LABELS
    labels: list[ProfileLabelRequest]


class ProfilePatchRequest(BaseModel):
    profile_type: str | None = None
    name: str | None = None
    description: str | None = None
    artifact_prefix: str | None = None
    training_min_added: int | None = None
    training_min_labels: int | None = None
    labels: list[ProfileLabelRequest] | None = None


class ProfileDeleteRequest(BaseModel):
    confirm: str


class LabelRenameRequest(BaseModel):
    new_key: str
    name: str | None = None
    description: str | None = None


class PromoteRequest(BaseModel):
    feature_set: str | None = None
    allow_uncalibrated: bool = False


class CalibrateRequest(BaseModel):
    feature_set: str | None = None


class TrainRefreshRequest(BaseModel):
    feature_set: str | None = None


class BenchmarkRequest(BaseModel):
    strategy: str = DEFAULT_BENCHMARK_STRATEGY
    feature_sets: list[str] = []


class PredictionRefreshRequest(BaseModel):
    feature_set: str | None = None


class SourceDatabaseState:
    def __init__(
        self,
        source_path: str | Path | None = None,
        *,
        expected_catalog_uuid: str | None = None,
        labels_db: RhythmLabDatabase,
        busy_check: Callable[[], str | None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._labels_db = labels_db
        self._busy_check = busy_check
        # The launcher's catalog pin applies to the initial open only; later
        # switches are user choices validated as libraries, not as this catalog.
        self.launched_catalog_uuid = (
            str(expected_catalog_uuid).strip()
            if expected_catalog_uuid is not None
            else None
        )
        self.path: Path | None = None
        self._source: SourceDatabase | None = None
        if source_path is None:
            return
        if Path(source_path).expanduser().exists():
            self._open(source_path, expected_catalog_uuid=self.launched_catalog_uuid)
        else:
            LOGGER.warning(
                "Source database does not exist; starting without a source: %s",
                source_path,
            )

    @property
    def source(self) -> SourceDatabase | None:
        """The selected library, with its track sightings re-synced when its file changed."""

        with self._lock:
            if self._source is not None:
                self._labels_db.sync_track_sightings(self._source)
            return self._source

    def current(self) -> dict[str, object]:
        with self._lock:
            source = self._source
            inventory = _SourceInventory.load(source)
            available = inventory.available
            return {
                "path": str(self.path) if self.path is not None else None,
                "selected": source is not None,
                "catalog_uuid": source.catalog_uuid if source is not None else None,
                "launched_catalog_uuid": self.launched_catalog_uuid,
                "track_count": inventory.track_count,
                "feature_sources": inventory.features_payload(),
                "available_feature_sources": list(available),
                "default_feature_set": default_feature_set(available),
                "mert_v2_layers": list(inventory.mert_v2_layers),
            }

    def switch(self, path: str | Path) -> dict[str, object]:
        """Open another library for the user; refused while a profile operation runs."""

        with self._lock:
            running = self._busy_check() if self._busy_check is not None else None
            if running is not None:
                raise RuntimeError(
                    f"Cannot switch libraries while the {running} operation is running"
                )
            return self._open(path, expected_catalog_uuid=None)

    def _open(
        self,
        path: str | Path,
        *,
        expected_catalog_uuid: str | None,
    ) -> dict[str, object]:
        selected = SourceDatabase(path, expected_catalog_uuid=expected_catalog_uuid)
        self._labels_db.sync_track_sightings(selected)
        with self._lock:
            self.path = selected.path
            self._source = selected
            return self.current()

    def require_source(self) -> SourceDatabase:
        source = self.source
        if source is None:
            raise ValueError("No library is open")
        return source


class TrainingProgress:
    """Small in-process progress registry for an active profile workflow."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, dict[str, object]] = {}

    def start(self, profile_key: str, *, operation: str, stage: str) -> None:
        with self._lock:
            existing = self._states.get(profile_key)
            if existing is not None and existing.get("status") == "running":
                raise RuntimeError("Another operation is already running for this profile")
            self._states[profile_key] = {
                "operation": operation,
                "status": "running",
                "stage": stage,
                "percent": 0,
                "error": None,
            }

    def update(self, profile_key: str, *, stage: str, percent: int) -> None:
        with self._lock:
            state = self._states.get(profile_key)
            if state is None or state.get("status") != "running":
                return
            state["stage"] = stage
            state["percent"] = min(99, max(int(state.get("percent", 0)), int(percent)))

    def complete(self, profile_key: str, *, stage: str) -> None:
        with self._lock:
            state = self._states.get(profile_key)
            if state is None:
                return
            state.update({"status": "completed", "stage": stage, "percent": 100, "error": None})

    def fail(self, profile_key: str, *, error: Exception) -> None:
        with self._lock:
            state = self._states.get(profile_key)
            if state is None:
                return
            state.update({"status": "failed", "stage": "Operation failed", "error": str(error)})

    def snapshot(self, profile_key: str) -> dict[str, object]:
        with self._lock:
            state = self._states.get(profile_key)
            if state is None:
                return {
                    "operation": None,
                    "status": "idle",
                    "stage": None,
                    "percent": 0,
                    "error": None,
                }
            return dict(state)

    def running_operation(self) -> str | None:
        """Operation currently running for any profile, or ``None`` when idle."""

        with self._lock:
            for state in self._states.values():
                if state.get("status") == "running":
                    return str(state.get("operation"))
            return None


def open_existing_database_file_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("The system file dialog is unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose existing SQLite database",
            filetypes=[("SQLite database", "*.sqlite"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


def create_app(
    source_db_path: str | Path | None = None,
    *,
    labels_db_path: str | Path,
    classifier_target_root: str | Path | None = None,
    shutdown_callback: Callable[[], None] | None = None,
    source_catalog_uuid: str | None = None,
) -> FastAPI:
    labels_path = Path(labels_db_path)
    labels_db = RhythmLabDatabase(labels_path)
    collections_repository = RhythmLabCollections(labels_path)
    training_progress = TrainingProgress()
    source_state = SourceDatabaseState(
        source_db_path,
        expected_catalog_uuid=source_catalog_uuid,
        labels_db=labels_db,
        busy_check=training_progress.running_operation,
    )
    target_root = Path(classifier_target_root) if classifier_target_root is not None else DEFAULT_CLASSIFIER_TARGET_ROOT
    app = FastAPI(title="Rhythm Lab")
    app.router.on_startup.append(install_rhythm_lab_asyncio_exception_logging)

    @app.middleware("http")
    async def log_http_error_responses(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("HTTP request crashed method=%s path=%s", request.method, request.url.path)
            raise
        if response.status_code >= 400:
            LOGGER.warning(
                "HTTP request returned error method=%s path=%s status=%s",
                request.method,
                request.url.path,
                response.status_code,
            )
        return response

    def profile_db(profile_key: str) -> RhythmLabDatabase:
        return labels_db.scoped(profile_key)

    def collections_db() -> RhythmLabCollections:
        return collections_repository

    def collection_selection(track_ids: list[int]) -> RhythmLabCollectionSelection:
        source = source_state.require_source()
        tracks_by_id = source.tracks_by_ids(track_ids)
        if len(tracks_by_id) != len(set(track_ids)):
            missing = sorted(set(track_ids) - set(tracks_by_id))
            raise ValueError(f"No current tracks with ids: {missing}")
        unfingerprinted = sorted(
            track_id for track_id, track in tracks_by_id.items() if track.content_key is None
        )
        if unfingerprinted:
            raise ValueError(
                "Tracks without a SONARA fingerprint cannot join a collection; "
                f"analyze them in the main app first: {unfingerprinted}"
            )
        return RhythmLabCollectionSelection(
            catalog_uuid=source.catalog_uuid,
            tracks=tuple(
                RhythmLabTrackSelection(
                    catalog_uuid=track.catalog_uuid,
                    track_uuid=track.track_uuid,
                    selected_path=track.file_path,
                    content_key=str(track.content_key),
                )
                for track_id in track_ids
                for track in (tracks_by_id[track_id],)
            ),
        )

    def profile_or_404(profile_key: str) -> ClassifierProfile:
        try:
            return profile_db(profile_key).get_profile(profile_key)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    def page_required_sources(feature_set: str | None) -> tuple[str, ...] | None:
        """Sources a page must have stored; ``None`` means every family stored here."""

        if feature_set is None or not feature_set.strip():
            return None
        try:
            return feature_sources(feature_set)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/")
    def index():
        return HTMLResponse(_index_html())

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

    @app.get("/static/{asset_path:path}")
    def static_asset(asset_path: str):
        target = (STATIC_DIR / asset_path).resolve(strict=False)
        static_root = STATIC_DIR.resolve(strict=False)
        if static_root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Static file not found")
        return FileResponse(target)

    @app.post("/api/shutdown")
    def shutdown_lab():
        callback = shutdown_callback or _schedule_process_shutdown
        return JSONResponse({"stopping": True}, background=BackgroundTask(callback))

    @app.get("/api/source/current")
    def current_source():
        return source_state.current()

    @app.post("/api/source/switch")
    def switch_source(request: SourceSwitchRequest):
        try:
            return source_state.switch(request.path)
        except SourceDatabaseError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (FileNotFoundError, ValueError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/source/dialog")
    def source_dialog():
        try:
            selected = open_existing_database_file_dialog()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if selected is None:
            return source_state.current()
        return {"path": str(selected.resolve(strict=False)), "selected": False}

    @app.get("/api/profiles")
    def profiles(include_archived: bool = False):
        return {
            "items": [
                _profile_payload(profile)
                for profile in labels_db.list_profiles(include_archived=include_archived)
            ]
        }

    @app.get("/api/collections")
    def review_collections():
        return {"items": [_collection_payload(collection) for collection in collections_db().list_collections()]}

    @app.post("/api/collections")
    def save_review_collection(request: CollectionSaveRequest):
        try:
            collection = collections_db().save_collection(
                request.name,
                collection_selection(request.track_ids),
                source=request.source,
                note=request.note,
                mode=request.mode,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.get("/api/collections/{collection_id}")
    def get_review_collection(collection_id: int):
        try:
            collection = collections_db().get_collection(collection_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.post("/api/collections/{collection_id}/tracks")
    def append_review_collection_tracks(collection_id: int, request: CollectionTracksRequest):
        try:
            if request.mode == "replace":
                collection = collections_db().replace_tracks(
                    collection_id,
                    collection_selection(request.track_ids),
                )
            else:
                collection = collections_db().append_tracks(
                    collection_id,
                    collection_selection(request.track_ids),
                )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.put("/api/collections/{collection_id}/tracks")
    def replace_review_collection_tracks(collection_id: int, request: CollectionTracksRequest):
        try:
            collection = collections_db().replace_tracks(
                collection_id,
                collection_selection(request.track_ids),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.delete("/api/collections/{collection_id}")
    def delete_review_collection(collection_id: int):
        deleted = collections_db().delete_collection(collection_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Collection not found: {collection_id}")
        return {"id": collection_id, "deleted": True}

    @app.post("/api/profiles")
    def create_profile(request: ProfileRequest):
        try:
            profile = labels_db.create_profile(
                classifier_key=request.classifier_key,
                profile_type=request.profile_type,
                name=request.name,
                description=request.description,
                artifact_prefix=request.artifact_prefix,
                training_min_added=request.training_min_added,
                training_min_labels=request.training_min_labels,
                labels=[label.model_dump() for label in request.labels],
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _profile_payload(profile)

    @app.patch("/api/profiles/{profile_key}")
    def update_profile(profile_key: str, request: ProfilePatchRequest):
        try:
            profile = labels_db.update_profile(
                profile_key,
                profile_type=request.profile_type,
                name=request.name,
                description=request.description,
                artifact_prefix=request.artifact_prefix,
                training_min_added=request.training_min_added,
                training_min_labels=request.training_min_labels,
                labels=[label.model_dump() for label in request.labels] if request.labels is not None else None,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _profile_payload(profile)

    @app.post("/api/profiles/{profile_key}/archive")
    def archive_profile(profile_key: str):
        try:
            return _profile_payload(labels_db.archive_profile(profile_key))
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.delete("/api/profiles/{profile_key}")
    def delete_profile(profile_key: str, request: ProfileDeleteRequest):
        try:
            profile = profile_or_404(profile_key)
            confirmation = request.confirm.strip()
            if confirmation not in {profile.classifier_key, profile.name}:
                raise HTTPException(
                    status_code=400,
                    detail="Delete confirmation must exactly match the profile key or name.",
                )
            deleted = labels_db.delete_profile(classifier_key=profile.classifier_key)
            artifact_cleanup = delete_profile_artifacts(
                Path(deleted.artifact_dir),
                artifact_prefix=deleted.artifact_prefix,
            )
        except HTTPException:
            raise
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "deleted": True,
            "classifier_key": deleted.classifier_key,
            "name": deleted.name,
            "artifact_cleanup": artifact_cleanup,
        }

    @app.post("/api/profiles/{profile_key}/labels/{old_key}/rename")
    def rename_profile_label(profile_key: str, old_key: str, request: LabelRenameRequest):
        try:
            profile = labels_db.rename_label_key(
                profile_key,
                old_key,
                request.new_key,
                display_name=request.name,
                description=request.description,
            )
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _profile_payload(profile)

    @app.get("/api/profiles/{profile_key}/summary")
    def profile_summary(profile_key: str):
        profile = profile_or_404(profile_key)
        scoped = profile_db(profile_key)
        source = source_state.source
        base = {
            "profile": _profile_payload(profile),
            "tracks": 0,
            "labels": scoped.label_counts(
                catalog_uuid=str(source.catalog_uuid) if source is not None else None
            ),
            **{source_name: 0 for source_name in SUPPORTED_FEATURE_SOURCES},
            "feature_states": {
                source_name: {
                    "status": "missing",
                    "reason": "No library is open.",
                }
                for source_name in SUPPORTED_FEATURE_SOURCES
            },
            "liked": 0,
            "source": source_state.current(),
        }
        if source is None:
            return base
        feature_counts = source.feature_counts()
        return {
            **base,
            "tracks": len(source.rhythm_lab_track_ids()),
            **feature_counts,
            "feature_states": {
                source_name: state.payload()
                for source_name, state in source.feature_states().items()
            },
            "liked": source.count_liked_tracks(),
        }

    @app.get("/api/profiles/{profile_key}/tracks")
    def profile_tracks(
        profile_key: str,
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        bpm_min: str = "",
        bpm_max: str = "",
        liked: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = "all",
        collection_id: int | None = Query(default=None, ge=1),
        order: str = Query(default="normal", pattern="^(normal|random)$"),
        seed: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        feature_set: str | None = None,
    ):
        profile = profile_or_404(profile_key)
        required_sources = page_required_sources(feature_set)
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            bpm_min_value = _bpm_bound_value(bpm_min, "BPM from")
            bpm_max_value = _bpm_bound_value(bpm_max, "BPM to")
            return source.list_tracks_page(
                labels_db_path=labels_path,
                classifier_key=profile.classifier_key,
                label_keys=profile.label_keys,
                training_label_keys=profile.training_label_keys,
                query=q,
                syncopated=syncopated,
                bpm_min=bpm_min_value,
                bpm_max=bpm_max_value,
                liked=liked,
                label=label,
                collection_id=collection_id,
                order=order,
                seed=seed,
                limit=limit,
                offset=offset,
                required_sources=required_sources,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/tracks/{track_id}/liked")
    def set_track_liked(track_id: int, request: TrackLikedRequest):
        try:
            source = source_state.require_source()
            if request.catalog_uuid != source.catalog_uuid:
                raise SourceTrackNotCurrentError(
                    "Like target belongs to another library: catalog UUID does not match the open library"
                )
            updated = source.set_track_liked(
                track_id=track_id,
                track_uuid=request.track_uuid,
                liked=request.liked,
            )
        except SourceTrackNotCurrentError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "catalog_uuid": updated.catalog_uuid,
            "track_id": updated.track_id,
            "track_uuid": updated.track_uuid,
            "file_path": updated.file_path,
            "liked": updated.liked,
        }

    @app.post("/api/profiles/{profile_key}/tracks/{track_id}/label")
    def set_profile_label(profile_key: str, track_id: int, request: LabelRequest):
        profile_or_404(profile_key)
        try:
            track = source_state.require_source().get_track(track_id)
            label = profile_db(profile_key).set_label(track, request.label, note=request.note)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"track_id": track_id, "label": label.label if label else None}

    @app.get("/api/profiles/{profile_key}/predictions")
    def profile_predictions(
        profile_key: str,
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        bpm_min: str = "",
        bpm_max: str = "",
        label: str = "unlabeled",
        predicted: str = "all",
        probability_focus: str = Query(default="positive_highest", pattern="^(positive_highest|negative_highest|balanced)$"),
        min_positive: str = "0",
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        feature_set: str | None = None,
    ):
        profile = profile_or_404(profile_key)
        required_sources = page_required_sources(feature_set)
        if label not in {"all", "unlabeled", *profile.label_keys}:
            raise HTTPException(status_code=400, detail=f"Unknown label filter: {label}")
        if predicted not in {"all", *profile.training_label_keys}:
            raise HTTPException(status_code=400, detail=f"Unknown predicted label filter: {predicted}")
        try:
            min_positive_value = _probability_filter_value(min_positive)
            bpm_min_value = _bpm_bound_value(bpm_min, "BPM from")
            bpm_max_value = _bpm_bound_value(bpm_max, "BPM to")
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            return source.list_predictions_page(
                labels_db_path=labels_path,
                classifier_key=profile.classifier_key,
                profile_type=profile.profile_type,
                positive_label=profile.positive_label,
                negative_label=profile.negative_label,
                label_keys=profile.label_keys,
                training_label_keys=profile.training_label_keys,
                query=q,
                syncopated=syncopated,
                bpm_min=bpm_min_value,
                bpm_max=bpm_max_value,
                label=label,
                predicted=predicted,
                probability_focus=probability_focus,
                min_positive=min_positive_value,
                limit=limit,
                offset=offset,
                required_sources=required_sources,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/profiles/{profile_key}/predictions/refresh")
    def refresh_profile_predictions(
        profile_key: str,
        request: PredictionRefreshRequest | None = None,
    ):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="No library is open")
        scoped = profile_db(profile.classifier_key)
        requested_feature_set = request.feature_set if request is not None else None
        try:
            readiness = _training_readiness(
                scoped,
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source,
                feature_set=requested_feature_set,
            )
            selected_feature_set, selected_option = _selected_artifact_option(
                readiness,
                requested_feature_set,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if selected_option is None or not selected_option.get("latest_model"):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Profile {profile.name} has no model artifact for recipe "
                    f"{selected_feature_set} in {profile.artifact_dir}"
                ),
            )
        if selected_option.get("source_data_ready") is not True:
            raise HTTPException(
                status_code=409,
                detail=str(
                    selected_option.get("source_data_reason")
                    or (
                        f"The {selected_feature_set} artifact is not ready for "
                        "the open library's data."
                    )
                ),
            )
        artifact = Path(str(selected_option["latest_model"]))
        try:
            training_progress.start(
                profile.classifier_key,
                operation="refresh",
                stage="Preparing candidate refresh",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        def report_prediction_progress(completed: int, total: int) -> None:
            if total <= 0:
                stage = "Refreshing candidates"
                percent = 5
            else:
                stage = f"Refreshing candidates: {completed:,}/{total:,}"
                percent = 5 + round(90 * completed / total)
            training_progress.update(
                profile.classifier_key,
                stage=stage,
                percent=percent,
            )

        try:
            result = apply_model_to_lab(
                source_state.path,
                labels_path,
                artifact,
                classifier_key=profile.classifier_key,
                progress_callback=report_prediction_progress,
            )
            training_progress.update(
                profile.classifier_key,
                stage="Publishing refreshed candidates",
                percent=97,
            )
            deleted = int(result.get("deleted_old_predictions", 0))
        except Exception as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s predictions refresh failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        training_progress.complete(
            profile.classifier_key,
            stage="Candidate refresh complete",
        )
        return {**result, "artifact": str(artifact), "deleted_old_predictions": deleted}

    @app.get("/api/profiles/{profile_key}/training/readiness")
    def profile_training_readiness(
        profile_key: str,
        feature_set: str | None = None,
    ):
        profile = profile_or_404(profile_key)
        try:
            readiness = _training_readiness(
                profile_db(profile.classifier_key),
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source_state.source,
                feature_set=feature_set,
            )
            return {
                **readiness,
                "promoted_model": _promoted_model_summary(profile, target_root),
            }
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/profiles/{profile_key}/training/progress")
    def profile_training_progress(profile_key: str):
        profile_or_404(profile_key)
        return training_progress.snapshot(profile_key)

    @app.post("/api/profiles/{profile_key}/training/train-refresh")
    def profile_train_refresh(
        profile_key: str,
        request: TrainRefreshRequest | None = None,
    ):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="No library is open")
        requested_feature_set = request.feature_set if request is not None else None
        scoped = profile_db(profile.classifier_key)
        try:
            readiness = _training_readiness(
                scoped,
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source,
                feature_set=requested_feature_set,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if requested_feature_set is None and readiness["default_feature_set"] is None:
            raise HTTPException(status_code=409, detail=_NO_SOURCE_DATA_DETAIL)
        _require_label_threshold(readiness)
        selected_feature_set = str(readiness["feature_recipe"]["feature_set"])
        if readiness["ready"] is not True:
            recipe = readiness["feature_recipe"]
            if recipe["ready"] is not True:
                blocking = ", ".join(
                    f"{item['source']}: {item['reason']}"
                    for item in recipe["blocking"]
                )
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Feature recipe {selected_feature_set} is not ready. "
                        f"{blocking}"
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail=_training_readiness_error(
                    profile,
                    readiness["missing_training_rows"],
                ),
            )
        counts = dict(readiness["total"])
        artifact_dir = Path(profile.artifact_dir)
        try:
            training_progress.start(
                profile.classifier_key,
                operation="train-refresh",
                stage="Preparing training data",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        def report_training_progress(stage: str, completed: int, total: int) -> None:
            training_progress.update(
                profile.classifier_key,
                stage=stage,
                percent=round(70 * completed / max(1, total)),
            )

        def report_prediction_progress(completed: int, total: int) -> None:
            training_progress.update(
                profile.classifier_key,
                stage=f"Refreshing candidates: {completed:,}/{total:,}",
                percent=70 + round(28 * completed / max(1, total)),
            )

        try:
            training = benchmark_lab_database(
                source_state.path,
                labels_path,
                artifact_dir,
                classifier_key=profile.classifier_key,
                feature_sets=(selected_feature_set,),
                progress_callback=report_training_progress,
            )
            trained = training.get(selected_feature_set)
            if not isinstance(trained, dict) or trained.get("status") != "trained":
                error = (
                    trained.get("error")
                    if isinstance(trained, dict)
                    else "the feature recipe was not trained"
                )
                raise RuntimeError(str(error))
            artifact = _trained_artifact_path(
                trained,
                artifact_dir,
                profile.artifact_prefix,
                selected_feature_set,
            )
            training_progress.update(
                profile.classifier_key,
                stage="Refreshing candidate predictions",
                percent=70,
            )
            result = apply_model_to_lab(
                source_state.path,
                labels_path,
                artifact,
                classifier_key=profile.classifier_key,
                progress_callback=report_prediction_progress,
            )
            deleted = int(result.get("deleted_old_predictions", 0))
            scoped.record_training_checkpoint(counts, model_artifact=artifact)
            cleanup = cleanup_training_artifacts(
                artifact_dir,
                protected_artifact=artifact,
                artifact_prefix=profile.artifact_prefix,
            )
        except Exception as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s train + refresh failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        training_progress.complete(
            profile.classifier_key,
            stage="Training complete",
        )
        return {
            "training": training,
            "feature_set": selected_feature_set,
            "artifact": str(artifact),
            "training_counts": counts,
            **result,
            "deleted_old_predictions": deleted,
            "artifact_cleanup": cleanup,
        }

    @app.post("/api/profiles/{profile_key}/training/benchmark")
    def profile_training_benchmark(profile_key: str, request: BenchmarkRequest | None = None):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="No library is open")
        strategy = request.strategy if request is not None else DEFAULT_BENCHMARK_STRATEGY
        feature_sets = tuple(request.feature_sets) if request is not None else ()
        available = available_feature_sources(source.feature_states())
        layers = stored_mert_v2_layers(source)
        try:
            plan = benchmark_plan(available, strategy, feature_sets, mert_v2_layers=layers)
            planned_runs = planned_run_count(available, strategy, feature_sets, mert_v2_layers=layers)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if not plan:
            raise HTTPException(status_code=409, detail=_NO_SOURCE_DATA_DETAIL)
        try:
            readiness = _training_readiness(
                profile_db(profile.classifier_key),
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        _require_label_threshold(readiness)
        try:
            training_progress.start(
                profile.classifier_key,
                operation="benchmark",
                stage="Preparing benchmark",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        def report_benchmark_progress(stage: str, completed: int, total: int) -> None:
            training_progress.update(
                profile.classifier_key,
                stage=stage,
                percent=round(100 * completed / max(1, total)),
            )

        try:
            report = run_ablation_benchmark(
                source_state.path,
                labels_path,
                profile_keys=(profile.classifier_key,),
                strategy=strategy,
                feature_sets=feature_sets,
                artifacts_root=None,
                progress_callback=report_benchmark_progress,
            )
        except Exception as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s benchmark failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        training_progress.complete(profile.classifier_key, stage="Benchmark complete")
        profile_report = next(
            (
                row
                for row in report.get("profiles", [])
                if isinstance(row, dict) and row.get("classifier_key") == profile.classifier_key
            ),
            None,
        )
        return {
            "classifier_key": profile.classifier_key,
            "strategy": report.get("strategy", strategy),
            "feature_sets": list(report.get("feature_sets", plan)),
            "planned_runs": int(report.get("planned_runs", planned_runs)),
            "output_path": report.get("output_path"),
            "winner": profile_report.get("winner") if isinstance(profile_report, dict) else None,
            "profile": profile_report,
        }

    @app.post("/api/profiles/{profile_key}/training/calibrate")
    def profile_training_calibrate(profile_key: str, request: CalibrateRequest | None = None):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="No library is open")
        scoped = profile_db(profile.classifier_key)
        requested_feature_set = request.feature_set if request is not None else None
        try:
            readiness = _training_readiness(
                scoped,
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source,
                feature_set=requested_feature_set,
            )
            selected_feature_set, selected_option = _selected_artifact_option(
                readiness,
                requested_feature_set,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        _require_label_threshold(readiness)
        if readiness["calibration_ready"] is not True:
            calibration_readiness = readiness["calibration_readiness"]
            raise HTTPException(
                status_code=409,
                detail=str(
                    calibration_readiness.get("reason")
                    if isinstance(calibration_readiness, Mapping)
                    else "Calibration requirements are not met."
                ),
            )
        if readiness["labels_ready"] is not True:
            raise HTTPException(
                status_code=400,
                detail=_training_readiness_error(
                    profile,
                    readiness["missing_training_rows"],
                ),
            )
        if selected_option is None or not selected_option.get("latest_model"):
            raise HTTPException(
                status_code=400,
                detail=f"Train a {selected_feature_set} model for {profile.name} before calibrating.",
            )
        if selected_option.get("source_data_ready") is not True:
            raise HTTPException(
                status_code=409,
                detail=str(
                    selected_option.get("source_data_reason")
                    or (
                        f"The {selected_feature_set} artifact is not ready for "
                        "the open library's data."
                    )
                ),
            )
        try:
            training_progress.start(
                profile.classifier_key,
                operation="calibrate",
                stage="Preparing calibration",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        def report_calibration_progress(
            stage: str, completed: int, total: int
        ) -> None:
            training_progress.update(
                profile.classifier_key,
                stage=stage,
                percent=round(95 * completed / max(1, total)),
            )

        try:
            training = benchmark_lab_database(
                source_state.path,
                labels_path,
                Path(profile.artifact_dir),
                classifier_key=profile.classifier_key,
                feature_sets=(selected_feature_set,),
                calibrate=True,
                progress_callback=report_calibration_progress,
            )
        except Exception as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s calibration failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        trained = training.get(selected_feature_set)
        if not isinstance(trained, dict) or trained.get("status") != "trained":
            error = (
                trained.get("error")
                if isinstance(trained, dict)
                else "the feature recipe was not calibrated"
            )
            training_progress.fail(
                profile.classifier_key, error=RuntimeError(str(error))
            )
            raise HTTPException(status_code=409, detail=str(error))
        try:
            artifact = _trained_artifact_path(
                trained,
                Path(profile.artifact_dir),
                profile.artifact_prefix,
                selected_feature_set,
            )
        except RuntimeError as error:
            training_progress.fail(profile.classifier_key, error=error)
            raise HTTPException(
                status_code=500,
                detail=str(error),
            ) from error
        metrics_value = trained.get("metrics_path")
        metrics_path = (
            Path(str(metrics_value))
            if metrics_value
            else _artifact_metrics_path(artifact)
        )
        metrics = _read_metrics(metrics_path)
        calibration_status = _metric_summary(metrics).get("calibration_status")
        if calibration_status != "calibrated":
            reason = _metric_summary(metrics).get("calibration_reason") or "the calibration gate was not met"
            detail = f"Calibration did not produce a calibrated artifact: {reason}"
            training_progress.fail(
                profile.classifier_key, error=RuntimeError(detail)
            )
            raise HTTPException(
                status_code=409,
                detail=detail,
            )
        scoped.record_training_checkpoint(
            dict(readiness["total"]),
            model_artifact=artifact,
        )
        try:
            cleanup = cleanup_training_artifacts(
                Path(profile.artifact_dir),
                protected_artifact=artifact,
                artifact_prefix=profile.artifact_prefix,
            )
        except Exception as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s calibration cleanup failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        training_progress.complete(
            profile.classifier_key,
            stage="Calibration complete",
        )
        return {
            "classifier_key": profile.classifier_key,
            "feature_set": selected_feature_set,
            "training": training,
            "artifact": str(artifact),
            "metrics": str(metrics_path),
            "calibration_status": calibration_status,
            "artifact_cleanup": cleanup,
        }

    @app.post("/api/profiles/{profile_key}/promote")
    def promote_profile(profile_key: str, request: PromoteRequest | None = None):
        profile = profile_or_404(profile_key)
        source = source_state.source
        requested_feature_set = request.feature_set if request is not None else None
        allow_uncalibrated = bool(request.allow_uncalibrated) if request is not None else False
        try:
            readiness = _training_readiness(
                profile_db(profile.classifier_key),
                artifact_dir=Path(profile.artifact_dir),
                profile=profile,
                source=source,
                feature_set=requested_feature_set,
            )
            selected_feature_set, selected_option = _selected_artifact_option(
                readiness,
                requested_feature_set,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if selected_option is None or not selected_option.get("latest_model"):
            raise HTTPException(
                status_code=400,
                detail=f"Train a {selected_feature_set} model for {profile.name} before promoting.",
            )
        if selected_option.get("spec_compatible") is not True:
            raise HTTPException(
                status_code=409,
                detail=str(
                    selected_option.get("spec_reason")
                    or (
                        f"The {selected_feature_set} artifact does not match "
                        "the current feature spec."
                    )
                ),
            )
        if (
            not allow_uncalibrated
            and selected_option.get("calibration_status") != "calibrated"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Calibrate the {selected_feature_set} model for "
                    f"{profile.name} before promoting."
                ),
            )
        try:
            training_progress.start(
                profile.classifier_key,
                operation="promote",
                stage="Preparing promotion",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        def report_promotion_progress(stage: str, percent: int) -> None:
            training_progress.update(
                profile.classifier_key,
                stage=stage,
                percent=percent,
            )

        try:
            result = promote_profile_model(
                labels_path,
                profile.classifier_key,
                artifact_path=Path(str(selected_option["latest_model"])),
                feature_set=selected_feature_set,
                target_root=target_root,
                require_calibration=not allow_uncalibrated,
                allow_uncalibrated=allow_uncalibrated,
                progress_callback=report_promotion_progress,
            )
        except PromotionError as error:
            training_progress.fail(profile.classifier_key, error=error)
            LOGGER.exception("%s promotion failed", profile.name)
            raise HTTPException(status_code=400, detail=str(error)) from error
        training_progress.complete(
            profile.classifier_key,
            stage="Promotion complete",
        )
        return {
            "classifier_key": profile.classifier_key,
            "feature_set": selected_feature_set,
            "model_path": str(result["model_path"]),
            "metadata_path": str(result["metadata_path"]),
            "source_artifact": str(result["source_artifact"]),
        }

    @app.get("/media/{track_id}")
    def media(track_id: int):
        try:
            track = source_state.require_source().get_track(track_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        path = Path(track.file_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        if requires_browser_preview_transcode(path):
            try:
                configure_shared_ffmpeg_runtime()
                return transcoded_wav_file_response(path)
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(path)

    return app


def _require_label_threshold(readiness: Mapping[str, object]) -> None:
    """409 for train-refresh, benchmark and calibrate when the open library holds too few labels."""

    if readiness.get("label_threshold_ready") is not True:
        raise HTTPException(status_code=409, detail=str(readiness.get("label_threshold_reason")))


def _selected_artifact_option(
    readiness: Mapping[str, object],
    requested_feature_set: str | None,
) -> tuple[str, dict[str, object] | None]:
    """Pick the artifact row for the requested recipe, else the latest promotable, else the readiness recipe."""

    artifact_summary = readiness.get("artifact_summary")
    selected_feature_set = (
        canonical_feature_set(feature_sources(requested_feature_set))
        if requested_feature_set is not None and requested_feature_set.strip()
        else None
    )
    if selected_feature_set is None and isinstance(artifact_summary, dict):
        latest = artifact_summary.get("latest_promotable")
        if isinstance(latest, dict) and latest.get("feature_set"):
            selected_feature_set = str(latest["feature_set"])
    if selected_feature_set is None:
        recipe = readiness.get("feature_recipe")
        selected_feature_set = str(recipe["feature_set"]) if isinstance(recipe, Mapping) else ""
    options = (
        artifact_summary.get("promotion_options")
        if isinstance(artifact_summary, dict)
        else None
    )
    selected_option = next(
        (
            option
            for option in options or []
            if isinstance(option, dict)
            and option.get("feature_set") == selected_feature_set
        ),
        None,
    )
    return selected_feature_set, selected_option


def install_rhythm_lab_asyncio_exception_logging() -> None:
    install_asyncio_exception_logging(logger_name="rhythm_lab")


def _profile_payload(profile: ClassifierProfile) -> dict[str, object]:
    return {
        "classifier_key": profile.classifier_key,
        "profile_type": profile.profile_type,
        "name": profile.name,
        "description": profile.description,
        "artifact_dir": profile.artifact_dir,
        "artifact_prefix": profile.artifact_prefix,
        "training_min_added": profile.training_min_added,
        "training_min_labels": profile.training_min_labels,
        "positive_label": profile.positive_label,
        "negative_label": profile.negative_label,
        "archived_at": profile.archived_at,
        "labels": [
            {
                "key": label.key,
                "name": label.name,
                "description": label.description,
                "role": label.role,
                "position": label.position,
            }
            for label in profile.labels
        ],
    }


def _collection_payload(collection: object, *, include_tracks: bool = False) -> dict[str, object]:
    payload = {
        "id": collection.id,
        "name": collection.name,
        "source": collection.source,
        "note": collection.note,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
        "track_count": collection.track_count,
    }
    if include_tracks:
        payload["tracks"] = [
            {
                "content_key": track.content_key,
                "catalog_uuid": track.catalog_uuid,
                "track_uuid": track.track_uuid,
                "selected_path": track.selected_path,
                "position": track.position,
                "score": track.score,
                "note": track.note,
                "added_at": track.added_at,
            }
            for track in collection.tracks
        ]
    return payload


def _latest_feature_artifact(artifact_dir: Path, artifact_prefix: str, feature_set: str) -> Path | None:
    files = _artifact_groups(artifact_dir, suffix=".joblib", artifact_prefix=artifact_prefix).get(feature_set)
    return files[0] if files else None


def cleanup_training_artifacts(
    artifact_dir: Path,
    *,
    protected_artifact: Path,
    artifact_prefix: str,
    keep_joblib_per_feature: int = KEEP_JOBLIB_PER_FEATURE,
    keep_metrics_per_feature: int = KEEP_METRICS_PER_FEATURE,
) -> dict[str, int]:
    protected = protected_artifact.resolve(strict=False)
    deleted = {"deleted_joblib": 0, "deleted_metrics": 0}
    for suffix, keep_count, key in (
        (".joblib", keep_joblib_per_feature, "deleted_joblib"),
        (".metrics.json", keep_metrics_per_feature, "deleted_metrics"),
    ):
        for files in _artifact_groups(artifact_dir, suffix=suffix, artifact_prefix=artifact_prefix).values():
            for path in files[keep_count:]:
                if path.resolve(strict=False) == protected:
                    continue
                path.unlink()
                deleted[key] += 1
    return deleted


def delete_profile_artifacts(
    artifact_dir: Path,
    *,
    artifact_prefix: str,
) -> dict[str, object]:
    root = artifact_dir.expanduser().resolve(strict=False)
    deleted_files = 0
    removed_dirs = 0
    deleted_names: list[str] = []
    if not root.exists() or not root.is_dir():
        return {
            "artifact_dir": str(root),
            "artifact_prefix": artifact_prefix,
            "deleted_files": 0,
            "removed_dirs": 0,
            "deleted_names": [],
        }

    targets: list[Path] = []
    seen: set[Path] = set()
    for pattern in (f"{artifact_prefix}-*.joblib", f"{artifact_prefix}-*.metrics.json"):
        for path in root.glob(pattern):
            resolved = path.resolve(strict=False)
            if resolved in seen or not resolved.is_file() or resolved.parent != root:
                continue
            seen.add(resolved)
            targets.append(path)

    for path in sorted(targets, key=lambda item: item.name):
        path.unlink()
        deleted_files += 1
        deleted_names.append(path.name)

    try:
        root.rmdir()
        removed_dirs = 1
    except OSError:
        removed_dirs = 0

    return {
        "artifact_dir": str(root),
        "artifact_prefix": artifact_prefix,
        "deleted_files": deleted_files,
        "removed_dirs": removed_dirs,
        "deleted_names": deleted_names,
    }


def _artifact_groups(
    artifact_dir: Path,
    *,
    suffix: str,
    artifact_prefix: str,
) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in artifact_dir.glob(f"{artifact_prefix}-*{suffix}"):
        # Group by canonical recipe: files named under an older family order join it.
        feature = canonical_artifact_feature_set(path.name, suffix=suffix, artifact_prefix=artifact_prefix)
        if feature is None:
            continue
        groups.setdefault(feature, []).append(path)
    for files in groups.values():
        files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return groups


def _trained_artifact_path(
    trained: Mapping[str, object],
    artifact_dir: Path,
    artifact_prefix: str,
    feature_set: str,
) -> Path:
    artifact_value = trained.get("artifact_path")
    if not artifact_value:
        raise RuntimeError(
            f"Training did not return the {feature_set} artifact path."
        )
    try:
        artifact = Path(str(artifact_value)).expanduser().resolve(strict=True)
    except OSError as error:
        raise RuntimeError(
            f"Training returned a missing {feature_set} artifact: "
            f"{artifact_value}"
        ) from error
    root = artifact_dir.expanduser().resolve(strict=False)
    if artifact.parent != root:
        raise RuntimeError(
            f"Training returned an artifact outside {root}: {artifact}"
        )
    artifact_feature = artifact_feature_set(
        artifact.name,
        suffix=".joblib",
        artifact_prefix=artifact_prefix,
    )
    if artifact_feature != feature_set:
        raise RuntimeError(
            f"Training returned an artifact for recipe {artifact_feature or '<unrecognized>'} "
            f"instead of the requested {feature_set}."
        )
    return artifact


def _calibration_readiness(
    profile: ClassifierProfile,
    counts: Mapping[str, object],
) -> dict[str, object]:
    positive_count = int(counts.get(profile.positive_label, 0))
    negative_count = sum(
        int(counts.get(label, 0))
        for label in profile.training_label_keys
        if label != profile.positive_label
    )
    total_count = positive_count + negative_count
    reason: str | None = None
    if profile.profile_type != "binary":
        reason = "Probability calibration is available only for binary profiles."
    elif total_count < MIN_CALIBRATION_LABELS:
        reason = (
            f"Calibration needs at least {MIN_CALIBRATION_LABELS} training "
            f"labels; now {total_count}."
        )
    elif positive_count < MIN_CALIBRATION_POSITIVE:
        reason = (
            f"Calibration needs at least {MIN_CALIBRATION_POSITIVE} "
            f"{profile.positive_label} labels; now {positive_count}."
        )
    elif negative_count < MIN_CALIBRATION_NEGATIVE:
        reason = (
            f"Calibration needs at least {MIN_CALIBRATION_NEGATIVE} labels "
            f"other than {profile.positive_label}; now {negative_count}."
        )
    return {
        "ready": reason is None,
        "reason": reason,
        "minimum_total": MIN_CALIBRATION_LABELS,
        "minimum_positive": MIN_CALIBRATION_POSITIVE,
        "minimum_negative": MIN_CALIBRATION_NEGATIVE,
        "actual_total": total_count,
        "actual_positive": positive_count,
        "actual_negative": negative_count,
    }


@dataclass(frozen=True)
class _SourceInventory:
    """Stored-family availability of one library, shared by readiness and ``/api/source/current``."""

    states: Mapping[str, object]
    counts: Mapping[str, int]
    track_count: int
    mert_v2_layers: tuple[int, ...]

    @classmethod
    def load(cls, source: SourceDatabase | None) -> _SourceInventory:
        if source is None:
            return cls(
                states={
                    source_name: {
                        "status": "missing",
                        "reason": "No library is open.",
                    }
                    for source_name in SUPPORTED_FEATURE_SOURCES
                },
                counts={},
                track_count=0,
                mert_v2_layers=(),
            )
        states: dict[str, object] = dict(source.feature_states())
        counts = dict(source.feature_counts())
        for source_name, count in counts.items():
            state = states[source_name]
            if state.status == "current" and count == 0:
                states[source_name] = {
                    "status": "missing",
                    "reason": (
                        f"No track has a current {source_name.upper()} "
                        "output."
                    ),
                }
        return cls(
            states=states,
            counts=counts,
            track_count=source.count_tracks(),
            mert_v2_layers=stored_mert_v2_layers(source),
        )

    @property
    def available(self) -> tuple[str, ...]:
        return available_feature_sources(self.states)

    def features_payload(self) -> dict[str, dict[str, object]]:
        return {
            source_name: {
                **_feature_state_payload(self.states.get(source_name)),
                "count": int(self.counts.get(source_name, 0)),
                "track_count": self.track_count,
            }
            for source_name in SUPPORTED_FEATURE_SOURCES
        }


def _training_readiness(
    labels_db: RhythmLabDatabase,
    *,
    artifact_dir: Path,
    profile: ClassifierProfile | None = None,
    source: SourceDatabase | None = None,
    feature_set: str | None = None,
) -> dict[str, object]:
    profile = profile or labels_db.get_profile()
    if source is not None:
        # "current" counts are scoped to content sighted in this library;
        # "total" counts and the training checkpoint are global across catalogs.
        labels_db.sync_track_sightings(source)
    inventory = _SourceInventory.load(source)
    source_states = inventory.states
    available = inventory.available
    default_recipe = default_feature_set(available)
    if feature_set is not None and feature_set.strip():
        feature_set = canonical_feature_set(feature_sources(feature_set))
    else:
        # With nothing stored, report every family as blocking rather than nothing.
        feature_set = default_recipe or canonical_feature_set(SUPPORTED_FEATURE_SOURCES)
    counts = _training_label_counts(
        labels_db.label_counts(
            catalog_uuid=str(source.catalog_uuid) if source is not None else None
        ),
        profile=profile,
    )
    total_counts = _training_label_counts(labels_db.label_counts(), profile=profile)
    checkpoint = labels_db.training_checkpoint()
    checkpoint_counts = dict(checkpoint["counts"])
    checkpoint_artifact = checkpoint["model_artifact"]
    latest_artifact = _latest_feature_artifact(
        artifact_dir,
        profile.artifact_prefix,
        feature_set,
    )
    if checkpoint_artifact is None and latest_artifact is not None:
        labels_db.record_training_checkpoint(total_counts, model_artifact=latest_artifact)
        checkpoint = labels_db.training_checkpoint()
        checkpoint_counts = dict(total_counts)
        checkpoint_artifact = str(latest_artifact)
    added = {
        label: max(0, total_counts[label] - int(checkpoint_counts.get(label, 0)))
        for label in profile.training_label_keys
    }
    minimum_training_rows = {
        label: MIN_TRAINING_ROWS_PER_LABEL
        for label in profile.training_label_keys
    }
    checkpoint_feature_set = (
        canonical_artifact_feature_set(
            Path(str(checkpoint_artifact)).name,
            suffix=".joblib",
            artifact_prefix=profile.artifact_prefix,
        )
        if checkpoint_artifact is not None
        else None
    )
    recipe_changed = (
        checkpoint_feature_set is not None
        and checkpoint_feature_set != feature_set
    )
    retrain_recommended = (
        checkpoint_artifact is None
        or recipe_changed
        or all(
            added[label] >= profile.training_min_added
            for label in profile.training_label_keys
        )
    )
    recipe = feature_recipe_readiness(feature_set, source_states)
    usable_counts = dict(counts)
    skipped_training_rows = 0
    usable_rows_evaluated = False
    if source is not None and recipe["ready"] is True:
        feature_matrix = build_labeled_feature_matrix_from_sources(
            source,
            labels_db,
            feature_set,
        )
        usable_counts = _training_label_counts(
            {
                label: feature_matrix.labels.count(label)
                for label in profile.training_label_keys
            },
            profile=profile,
        )
        skipped_training_rows = len(feature_matrix.skipped_identities)
        usable_rows_evaluated = True
    unusable_counts = {
        label: max(0, counts[label] - usable_counts[label])
        for label in profile.training_label_keys
    }
    calibration_readiness = _calibration_readiness(profile, usable_counts)
    missing_training_rows = {
        label: max(
            0,
            minimum_training_rows[label] - usable_counts[label],
        )
        for label in profile.training_label_keys
    }
    labels_ready = all(
        missing_training_rows[label] == 0
        for label in profile.training_label_keys
    )
    label_threshold_ready, label_threshold_reason = _label_threshold_readiness(
        profile, counts, total_counts
    )
    ready = labels_ready and label_threshold_ready and recipe["ready"] is True
    artifact_summary = _bind_artifact_source_readiness(
        _artifact_summary(artifact_dir, profile.artifact_prefix),
        source_states,
    )
    return {
        "ready": ready,
        "labels_ready": labels_ready,
        "label_threshold": profile.training_min_labels,
        "label_threshold_ready": label_threshold_ready,
        "label_threshold_reason": label_threshold_reason,
        "calibration_ready": calibration_readiness["ready"],
        "calibration_readiness": calibration_readiness,
        "features_ready": recipe["ready"],
        "feature_recipe": recipe,
        "available_feature_sources": list(available),
        "default_feature_set": default_recipe,
        "source_features": inventory.features_payload(),
        "mert_v2_layers": list(inventory.mert_v2_layers),
        "current": counts,
        "total": total_counts,
        "usable": usable_counts,
        "unusable": unusable_counts,
        "usable_rows_evaluated": usable_rows_evaluated,
        "skipped_training_rows": skipped_training_rows,
        "minimum_training_rows": minimum_training_rows,
        "missing_training_rows": missing_training_rows,
        "last_trained": {label: int(checkpoint_counts.get(label, 0)) for label in profile.training_label_keys},
        "last_trained_at": checkpoint["updated_at"],
        "added": added,
        "required_added": {label: profile.training_min_added for label in profile.training_label_keys},
        "retrain_recommended": retrain_recommended,
        "recipe_changed": recipe_changed,
        "model_artifact": checkpoint_artifact,
        "trained_model": {
            "artifact": checkpoint_artifact,
            "feature_set": checkpoint_feature_set,
            "trained_at": checkpoint["updated_at"],
            "label_counts": {
                label: int(checkpoint_counts.get(label, 0))
                for label in profile.training_label_keys
            },
        },
        "artifact_summary": artifact_summary,
        "metrics_history": _metrics_history(
            artifact_dir,
            profile.artifact_prefix,
            feature_set=str(recipe["feature_set"]),
        ),
    }


def _label_threshold_readiness(
    profile: ClassifierProfile,
    counts: Mapping[str, int],
    total_counts: Mapping[str, int],
) -> tuple[bool, str | None]:
    """The profile's per-class label minimum, checked against labels resolvable in the open library."""

    threshold = profile.training_min_labels
    if all(int(counts.get(label, 0)) >= threshold for label in profile.training_label_keys):
        return True, None
    current = ", ".join(
        f"{label} — {int(counts.get(label, 0))} ({int(total_counts.get(label, 0))} total)"
        for label in profile.training_label_keys
    )
    return (
        False,
        f"Training needs at least {threshold} labels per class in the open "
        f"library. Now: {current}. Open the library where this profile is "
        "labeled, or lower the threshold in profile settings.",
    )


def _promoted_model_summary(
    profile: ClassifierProfile,
    classifier_target_root: Path,
) -> dict[str, object]:
    target = classifier_target_root / profile.artifact_prefix
    model_path = target / "model.joblib"
    metadata_path = target / "model.json"
    if not model_path.is_file():
        return {
            "status": "not_promoted",
            "model_path": str(model_path),
            "metadata_path": str(metadata_path),
        }
    manifest = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key=profile.classifier_key,
        metadata_path=metadata_path,
    )
    return {
        "status": "ready" if manifest.is_scoring_compatible else "invalid",
        **manifest.to_api_dict(),
    }


def _artifact_summary(artifact_dir: Path, artifact_prefix: str) -> dict[str, object]:
    model_groups = _artifact_groups(artifact_dir, suffix=".joblib", artifact_prefix=artifact_prefix)
    metrics_groups = _artifact_groups(artifact_dir, suffix=".metrics.json", artifact_prefix=artifact_prefix)
    by_feature = [
        _artifact_feature_summary(
            feature,
            latest_model=(model_groups.get(feature) or [None])[0],
            latest_metrics=(metrics_groups.get(feature) or [None])[0],
        )
        for feature in sorted(set(model_groups) | set(metrics_groups))
    ]
    promotion_options = _promotion_options(by_feature)
    benchmark_winner = promotion_options[0] if promotion_options else None
    return {
        "artifact_dir": str(artifact_dir),
        "artifact_prefix": artifact_prefix,
        "model_count": sum(len(files) for files in model_groups.values()),
        "metrics_count": sum(len(files) for files in metrics_groups.values()),
        "benchmark_winner": benchmark_winner,
        "latest_promotable": promotion_options[0] if promotion_options else None,
        "promotion_options": promotion_options,
        "by_feature": by_feature,
    }


def _bind_artifact_source_readiness(
    summary: dict[str, object],
    source_states: Mapping[str, object],
) -> dict[str, object]:
    """Annotate artifact rows with spec compatibility (promotion) and source data readiness (refresh).

    ``source_catalog_uuid`` on a row is provenance only; artifacts are gated by
    their feature spec, never by the library they were trained on.
    """

    annotated: list[dict[str, object]] = []
    raw_rows = summary.get("by_feature")
    if isinstance(raw_rows, list):
        for value in raw_rows:
            if not isinstance(value, dict):
                continue
            row = dict(value)
            feature_set = str(row.get("feature_set") or "")
            compatible, reason = artifact_feature_compatibility(
                feature_set=feature_set,
                feature_names=row.get("feature_names"),
            )
            if compatible:
                compatible, reason = _main_app_spec_compatibility(feature_set)
            row["spec_compatible"] = compatible
            row["spec_reason"] = reason
            ready, data_reason = artifact_source_readiness(
                feature_set=feature_set,
                feature_names=row.get("feature_names"),
                feature_states=source_states,
            )
            row["source_data_ready"] = ready
            row["source_data_reason"] = data_reason
            annotated.append(row)
    promotion_options = _promotion_options(annotated)
    promotable = [
        row
        for row in promotion_options
        if row.get("spec_compatible") is True
    ]
    return {
        **summary,
        "by_feature": annotated,
        "benchmark_winner": (
            promotion_options[0] if promotion_options else None
        ),
        "latest_promotable": promotable[0] if promotable else None,
        "promotion_options": promotion_options,
    }


def _main_app_spec_compatibility(feature_set: str) -> tuple[bool, str | None]:
    """The main app scores only the stored default MERT-v2 layer (db/classifier_storage.py)."""

    for token in feature_sources(feature_set):
        family, layer = split_feature_source(token)
        if family == "mert_v2" and layer is not None:
            return (
                False,
                f"The main app scores only MERT-v2 layer {MERT_V2_DEFAULT_LAYER}; "
                f"layer {layer} artifacts stay in the lab",
            )
    return True, None


def _feature_state_payload(state: object) -> dict[str, object]:
    if isinstance(state, Mapping):
        return {"status": str(state.get("status") or "missing"), "reason": state.get("reason")}
    return {
        "status": str(getattr(state, "status", "missing")),
        "reason": getattr(state, "reason", None),
    }


def _artifact_feature_summary(feature_set: str, *, latest_model: Path | None, latest_metrics: Path | None) -> dict[str, object]:
    if latest_model is not None:
        paired_metrics = _artifact_metrics_path(latest_model)
        if paired_metrics.exists():
            latest_metrics = paired_metrics
    metrics = _read_metrics(latest_metrics)
    return {
        "feature_set": feature_set,
        "latest_model": str(latest_model) if latest_model is not None else None,
        "latest_metrics": str(latest_metrics) if latest_metrics is not None else None,
        "created_at": _metric_created_at(metrics, latest_metrics or latest_model),
        "model_bytes": _file_size(latest_model),
        "metrics_bytes": _file_size(latest_metrics),
        **_metric_summary(metrics),
    }


def _metrics_history(
    artifact_dir: Path,
    artifact_prefix: str,
    *,
    feature_set: str,
    limit: int = 8,
) -> list[dict[str, object]]:
    metrics_paths = _artifact_groups(artifact_dir, suffix=".metrics.json", artifact_prefix=artifact_prefix).get(feature_set, [])
    rows = [_metrics_history_row(path, feature_set=feature_set) for path in metrics_paths]
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("metrics_path") or "")), reverse=True)
    return rows[:limit]


def _promotion_options(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = [row for row in rows if row.get("latest_model")]
    ranked = sorted(candidates, key=_promotion_sort_key, reverse=True)
    ranked_with_ranks: list[dict[str, object]] = []
    for index, row in enumerate(ranked, start=1):
        ranked_with_ranks.append({**row, "rank": index})
    return ranked_with_ranks


def _promotion_sort_key(row: dict[str, object]) -> tuple[float, float, float, str]:
    return (
        _metric_sort_value(row.get("macro_f1_mean")),
        _metric_sort_value(row.get("positive_recall_mean")),
        _metric_sort_value(row.get("positive_precision_mean")),
        str(row.get("created_at") or ""),
    )


def _metric_sort_value(value: object) -> float:
    number = _optional_float(value)
    return number if number is not None else -1.0


def _metrics_history_row(path: Path, *, feature_set: str) -> dict[str, object]:
    metrics = _read_metrics(path)
    return {
        "feature_set": str(metrics.get("feature_set") or feature_set),
        "metrics_path": str(path),
        "created_at": _metric_created_at(metrics, path),
        **_metric_summary(metrics),
    }


def _read_metrics(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"metrics_error": str(error)}
    return payload if isinstance(payload, dict) else {}


def _artifact_metrics_path(path: Path) -> Path:
    return path.with_suffix(".metrics.json")




def _metric_summary(metrics: dict[str, object]) -> dict[str, object]:
    cross_validation = metrics.get("cross_validation")
    if not isinstance(cross_validation, dict):
        cross_validation = {}
    production_calibration = metrics.get("production_calibration")
    if not isinstance(production_calibration, dict):
        production_calibration = {}
    return {
        "trained_rows": _optional_int(metrics.get("trained_rows")),
        "test_rows": _optional_int(metrics.get("test_rows")),
        "skipped_rows": _optional_int(metrics.get("skipped_rows")),
        "feature_count": _optional_int(metrics.get("feature_count")),
        "positive_label": metrics.get("positive_label"),
        "label_order": metrics.get("label_order") if isinstance(metrics.get("label_order"), list) else None,
        "feature_names": (
            metrics.get("feature_names")
            if isinstance(metrics.get("feature_names"), list)
            else None
        ),
        "source_catalog_uuid": metrics.get("source_catalog_uuid"),
        "feature_group_weights": (
            metrics.get("feature_group_weights")
            if isinstance(metrics.get("feature_group_weights"), dict)
            else None
        ),
        "accuracy_mean": _optional_float(cross_validation.get("accuracy_mean")),
        "macro_f1_mean": _optional_float(cross_validation.get("macro_f1_mean")),
        "positive_precision_mean": _optional_float(cross_validation.get("positive_precision_mean")),
        "positive_recall_mean": _optional_float(cross_validation.get("positive_recall_mean")),
        "calibration_status": production_calibration.get("status"),
        "calibration_method": production_calibration.get("method"),
        "calibration_reason": production_calibration.get("reason"),
    }


def _metric_created_at(metrics: dict[str, object], fallback_path: Path | None) -> str | None:
    created_at = metrics.get("created_at")
    if created_at is not None:
        return str(created_at)
    if fallback_path is None or not fallback_path.exists():
        return None
    return _utc_file_time(fallback_path)


def _utc_file_time(path: Path) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _file_size(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    return int(path.stat().st_size)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _probability_filter_value(value: object) -> float:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        probability = float(text)
    except ValueError as error:
        raise ValueError("Minimum probability must be a number between 0 and 1") from error
    if probability < 0.0 or probability > 1.0:
        raise ValueError("Minimum probability must be a number between 0 and 1")
    return probability


def _bpm_bound_value(value: object, label: str) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        bpm = float(text)
    except ValueError as error:
        raise ValueError(f"{label} must be a positive number") from error
    if bpm <= 0:
        raise ValueError(f"{label} must be a positive number")
    return bpm


def _training_label_counts(counts: dict[str, int], *, profile: ClassifierProfile) -> dict[str, int]:
    return {label: int(counts.get(label, 0)) for label in profile.training_label_keys}


def _training_readiness_error(
    profile: ClassifierProfile,
    missing: Mapping[str, object],
) -> str:
    if profile.profile_type == "multiclass":
        counts = ", ".join(
            f"{label} {int(missing.get(label, 0))}"
            for label in profile.training_label_keys
        )
        return (
            "Each class needs at least two labeled tracks. "
            f"Missing: {counts}."
        )
    return (
        f"Need at least two {profile.positive_label} and two "
        f"{profile.negative_label} labeled tracks. Missing: "
        f"{profile.positive_label} {int(missing.get(profile.positive_label, 0))}, "
        f"{profile.negative_label} {int(missing.get(profile.negative_label, 0))}."
    )


def _index_html() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def _schedule_process_shutdown() -> None:
    timer = threading.Timer(0.2, lambda: os._exit(0))
    timer.daemon = True
    timer.start()

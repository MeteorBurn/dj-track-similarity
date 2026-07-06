from __future__ import annotations

from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.dependencies import require_ffmpeg
from dj_track_similarity.logging_config import install_asyncio_exception_logging
from dj_track_similarity.media_preview import requires_browser_preview_transcode, transcoded_wav_file_response
from dj_track_similarity.rhythm_lab_collections import RhythmLabCollections

from .ablation import ABLATION_FEATURE_SETS, run_ablation_benchmark
from .cli import DEFAULT_CLASSIFIER_TARGET_ROOT, PromotionError, promote_profile_model
from .lab_db import ClassifierProfile, RhythmLabDatabase
from .predictions import apply_model_to_lab
from .source_db import SourceDatabase
from .training import benchmark_lab_database


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("static")
FAVICON_PATH = STATIC_DIR / "favicon.svg"
TRAIN_REFRESH_MIN_ADDED = 50
KEEP_JOBLIB_PER_FEATURE = 3
KEEP_METRICS_PER_FEATURE = 10


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class TrackLikedRequest(BaseModel):
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
    artifact_dir: str | None = None
    artifact_prefix: str | None = None
    training_min_added: int = TRAIN_REFRESH_MIN_ADDED
    labels: list[ProfileLabelRequest]


class ProfilePatchRequest(BaseModel):
    profile_type: str | None = None
    name: str | None = None
    description: str | None = None
    artifact_dir: str | None = None
    artifact_prefix: str | None = None
    training_min_added: int | None = None
    labels: list[ProfileLabelRequest] | None = None


class ProfileDeleteRequest(BaseModel):
    confirm: str


class LabelRenameRequest(BaseModel):
    new_key: str
    name: str | None = None
    description: str | None = None


class PromoteRequest(BaseModel):
    feature_set: str | None = None


class CalibrateRequest(BaseModel):
    feature_set: str | None = None


class SourceDatabaseState:
    def __init__(self, source_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self.path: Path | None = None
        self.source: SourceDatabase | None = None
        if source_path is not None and Path(source_path).expanduser().exists():
            self.switch(source_path)

    def current(self) -> dict[str, object]:
        with self._lock:
            return {
                "path": str(self.path) if self.path is not None else None,
                "selected": self.source is not None,
            }

    def switch(self, path: str | Path) -> dict[str, object]:
        selected = SourceDatabase(path)
        with self._lock:
            self.path = selected.path
            self.source = selected
            return self.current()

    def require_source(self) -> SourceDatabase:
        with self._lock:
            if self.source is None:
                raise ValueError("Source database is not selected")
            return self.source


def open_existing_database_file_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("Native database file dialog is unavailable") from error

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
) -> FastAPI:
    labels_path = Path(labels_db_path)
    labels_db = RhythmLabDatabase(labels_path)
    source_state = SourceDatabaseState(source_db_path)
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
        return RhythmLabDatabase(labels_path, classifier_key=profile_key)

    def collections_db() -> RhythmLabCollections:
        return RhythmLabCollections(labels_path)

    def profile_or_404(profile_key: str) -> ClassifierProfile:
        try:
            return profile_db(profile_key).get_profile(profile_key)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

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
            raise HTTPException(status_code=404, detail="Static asset not found")
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
                request.track_ids,
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
                collection = collections_db().replace_tracks(collection_id, request.track_ids)
            else:
                collection = collections_db().append_tracks(collection_id, request.track_ids)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.put("/api/collections/{collection_id}/tracks")
    def replace_review_collection_tracks(collection_id: int, request: CollectionTracksRequest):
        try:
            collection = collections_db().replace_tracks(collection_id, request.track_ids)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _collection_payload(collection, include_tracks=True)

    @app.delete("/api/collections/{collection_id}")
    def delete_review_collection(collection_id: int):
        deleted = collections_db().delete_collection(collection_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Review collection not found: {collection_id}")
        return {"id": collection_id, "deleted": True}

    @app.post("/api/profiles")
    def create_profile(request: ProfileRequest):
        try:
            profile = labels_db.create_profile(
                classifier_key=request.classifier_key,
                profile_type=request.profile_type,
                name=request.name,
                description=request.description,
                artifact_dir=request.artifact_dir,
                artifact_prefix=request.artifact_prefix,
                training_min_added=request.training_min_added,
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
                artifact_dir=request.artifact_dir,
                artifact_prefix=request.artifact_prefix,
                training_min_added=request.training_min_added,
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
                    detail="Delete confirmation must exactly match the profile key or profile name.",
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
            "labels": scoped.label_counts(),
            "sonara": 0,
            "mert": 0,
            "maest": 0,
            "liked": 0,
            "source": source_state.current(),
        }
        if source is None:
            return base
        return {
            **base,
            "tracks": source.count_tracks(),
            "sonara": source.count_sonara_features(),
            "mert": source.count_embeddings("mert"),
            "maest": source.count_embeddings("maest"),
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
    ):
        profile = profile_or_404(profile_key)
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
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/tracks/{track_id}/liked")
    def set_track_liked(track_id: int, request: TrackLikedRequest):
        if source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        try:
            updated = LibraryDatabase(source_state.path).set_track_liked(track_id, request.liked)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"track_id": updated.id, "liked": updated.liked}

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
    ):
        profile = profile_or_404(profile_key)
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
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/profiles/{profile_key}/predictions/refresh")
    def refresh_profile_predictions(profile_key: str):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        artifact_dir = Path(profile.artifact_dir)
        artifact = _latest_combined_artifact(artifact_dir, profile.artifact_prefix)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"No combined {profile.name} model artifact found in {artifact_dir}")
        scoped = profile_db(profile.classifier_key)
        try:
            result = apply_model_to_lab(
                source_state.path,
                labels_path,
                artifact,
                classifier_key=profile.classifier_key,
            )
            deleted = scoped.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
        except Exception as error:
            LOGGER.exception("%s predictions refresh failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {**result, "artifact": str(artifact), "deleted_old_predictions": deleted}

    @app.get("/api/profiles/{profile_key}/training/readiness")
    def profile_training_readiness(profile_key: str):
        profile = profile_or_404(profile_key)
        return _training_readiness(profile_db(profile.classifier_key), artifact_dir=Path(profile.artifact_dir), profile=profile)

    @app.post("/api/profiles/{profile_key}/training/train-refresh")
    def profile_train_refresh(profile_key: str):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        scoped = profile_db(profile.classifier_key)
        readiness = _training_readiness(scoped, artifact_dir=Path(profile.artifact_dir), profile=profile)
        if readiness["ready"] is not True:
            added = readiness["added"]
            raise HTTPException(
                status_code=400,
                detail=_training_readiness_error(profile, added),
            )
        counts = dict(readiness["current"])
        artifact_dir = Path(profile.artifact_dir)
        try:
            training = benchmark_lab_database(
                source_state.path,
                labels_path,
                artifact_dir,
                classifier_key=profile.classifier_key,
            )
            artifact = _latest_combined_artifact(artifact_dir, profile.artifact_prefix)
            if artifact is None:
                raise RuntimeError(f"No combined {profile.name} model artifact found in {artifact_dir}")
            result = apply_model_to_lab(
                source_state.path,
                labels_path,
                artifact,
                classifier_key=profile.classifier_key,
            )
            deleted = scoped.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
            scoped.record_training_checkpoint(counts, model_artifact=artifact)
            cleanup = cleanup_training_artifacts(
                artifact_dir,
                protected_artifact=artifact,
                artifact_prefix=profile.artifact_prefix,
            )
        except Exception as error:
            LOGGER.exception("%s train + refresh failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "training": training,
            "artifact": str(artifact),
            "training_counts": counts,
            **result,
            "deleted_old_predictions": deleted,
            "artifact_cleanup": cleanup,
        }

    @app.post("/api/profiles/{profile_key}/training/benchmark")
    def profile_training_benchmark(profile_key: str):
        profile = profile_or_404(profile_key)
        if source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        try:
            report = run_ablation_benchmark(
                source_state.path,
                labels_path,
                profile_keys=(profile.classifier_key,),
                feature_sets=ABLATION_FEATURE_SETS,
                artifacts_root=None,
            )
        except Exception as error:
            LOGGER.exception("%s benchmark failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
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
            "output_path": report.get("output_path"),
            "winner": profile_report.get("winner") if isinstance(profile_report, dict) else None,
            "profile": profile_report,
        }

    @app.post("/api/profiles/{profile_key}/training/calibrate")
    def profile_training_calibrate(profile_key: str, request: CalibrateRequest | None = None):
        profile = profile_or_404(profile_key)
        if source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        readiness = _training_readiness(profile_db(profile.classifier_key), artifact_dir=Path(profile.artifact_dir), profile=profile)
        artifact_summary = readiness.get("artifact_summary")
        selected_feature_set = (request.feature_set if request is not None else None) or _default_promotion_feature_set(artifact_summary)
        promotion_options = artifact_summary.get("promotion_options") if isinstance(artifact_summary, dict) else []
        selected_option = next(
            (
                option
                for option in promotion_options
                if isinstance(option, dict) and option.get("feature_set") == selected_feature_set
            ),
            None,
        )
        if selected_option is None or not selected_option.get("latest_model"):
            raise HTTPException(
                status_code=400,
                detail=f"Train a {selected_feature_set} model before calibrating {profile.name}.",
            )
        try:
            training = benchmark_lab_database(
                source_state.path,
                labels_path,
                Path(profile.artifact_dir),
                classifier_key=profile.classifier_key,
                feature_sets=(selected_feature_set,),
                calibrate=True,
            )
        except Exception as error:
            LOGGER.exception("%s calibration failed", profile.name)
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "classifier_key": profile.classifier_key,
            "feature_set": selected_feature_set,
            "training": training,
        }

    @app.post("/api/profiles/{profile_key}/promote")
    def promote_profile(profile_key: str, request: PromoteRequest | None = None):
        profile = profile_or_404(profile_key)
        readiness = _training_readiness(profile_db(profile.classifier_key), artifact_dir=Path(profile.artifact_dir), profile=profile)
        artifact_summary = readiness.get("artifact_summary")
        selected_feature_set = (request.feature_set if request is not None else None) or "combined"
        promotion_options = artifact_summary.get("promotion_options") if isinstance(artifact_summary, dict) else []
        selected_option = next(
            (
                option
                for option in promotion_options
                if isinstance(option, dict) and option.get("feature_set") == selected_feature_set
            ),
            None,
        )
        if selected_option is None or not selected_option.get("latest_model"):
            raise HTTPException(
                status_code=400,
                detail=f"Train a {selected_feature_set} model before promoting {profile.name}.",
            )
        try:
            result = promote_profile_model(
                labels_path,
                profile.classifier_key,
                artifact_path=Path(str(selected_option["latest_model"])),
                feature_set=selected_feature_set,
                target_root=target_root,
            )
        except PromotionError as error:
            LOGGER.exception("%s promotion failed", profile.name)
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "classifier_key": profile.classifier_key,
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
        path = Path(track.path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        if requires_browser_preview_transcode(path):
            try:
                return transcoded_wav_file_response(path, require_ffmpeg())
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(path)

    return app


def _default_promotion_feature_set(artifact_summary: object) -> str:
    if isinstance(artifact_summary, dict):
        latest = artifact_summary.get("latest_promotable")
        if isinstance(latest, dict) and latest.get("feature_set"):
            return str(latest["feature_set"])
    return "combined"


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
                "track_id": track.source_track_id,
                "position": track.position,
                "score": track.score,
                "note": track.note,
                "added_at": track.added_at,
            }
            for track in collection.tracks
        ]
    return payload


def _latest_combined_artifact(artifact_dir: Path, artifact_prefix: str) -> Path | None:
    return _latest_feature_artifact(artifact_dir, artifact_prefix, "combined")


def _latest_feature_artifact(artifact_dir: Path, artifact_prefix: str, feature_set: str) -> Path | None:
    artifacts = list(artifact_dir.glob(f"{artifact_prefix}-{feature_set}-*.joblib"))
    artifacts.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    for artifact in artifacts:
        if not _artifact_has_calibrated_metrics(artifact):
            return artifact
    return None


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
        feature = _artifact_feature(path.name, suffix=suffix, artifact_prefix=artifact_prefix)
        if feature is None:
            continue
        groups.setdefault(feature, []).append(path)
    for files in groups.values():
        files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return groups


def _artifact_feature(name: str, *, suffix: str, artifact_prefix: str) -> str | None:
    prefix = f"{artifact_prefix}-"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    stem = name[len(prefix) : -len(suffix)]
    parts = stem.split("-")
    if len(parts) < 2:
        return None
    return parts[0]


def _training_readiness(
    labels_db: RhythmLabDatabase,
    *,
    artifact_dir: Path,
    profile: ClassifierProfile | None = None,
) -> dict[str, object]:
    profile = profile or labels_db.get_profile()
    counts = _training_label_counts(labels_db.label_counts(), profile=profile)
    checkpoint = labels_db.training_checkpoint()
    checkpoint_counts = dict(checkpoint["counts"])
    checkpoint_artifact = checkpoint["model_artifact"]
    latest_artifact = _latest_combined_artifact(artifact_dir, profile.artifact_prefix)
    if checkpoint_artifact is None and latest_artifact is not None:
        labels_db.record_training_checkpoint(counts, model_artifact=latest_artifact)
        checkpoint = labels_db.training_checkpoint()
        checkpoint_counts = dict(counts)
        checkpoint_artifact = str(latest_artifact)
    added = {
        label: max(0, counts[label] - int(checkpoint_counts.get(label, 0)))
        for label in profile.training_label_keys
    }
    ready = all(added[label] >= profile.training_min_added for label in profile.training_label_keys)
    return {
        "ready": ready,
        "current": counts,
        "last_trained": {label: int(checkpoint_counts.get(label, 0)) for label in profile.training_label_keys},
        "last_trained_at": checkpoint["updated_at"],
        "added": added,
        "required_added": {label: profile.training_min_added for label in profile.training_label_keys},
        "model_artifact": checkpoint_artifact,
        "artifact_summary": _artifact_summary(artifact_dir, profile.artifact_prefix),
        "metrics_history": _metrics_history(artifact_dir, profile.artifact_prefix, feature_set="combined"),
    }


def _artifact_summary(artifact_dir: Path, artifact_prefix: str) -> dict[str, object]:
    model_groups = _artifact_groups(artifact_dir, suffix=".joblib", artifact_prefix=artifact_prefix)
    metrics_groups = _artifact_groups(artifact_dir, suffix=".metrics.json", artifact_prefix=artifact_prefix)
    latest_combined = _latest_combined_artifact(artifact_dir, artifact_prefix)
    by_feature = [
        _artifact_feature_summary(
            feature,
            latest_model=_latest_uncalibrated_artifact(model_groups.get(feature, [])),
            latest_metrics=_latest_uncalibrated_metrics(metrics_groups.get(feature, [])),
        )
        for feature in sorted(set(model_groups) | set(metrics_groups))
    ]
    promotion_options = _promotion_options(by_feature)
    benchmark_winner = promotion_options[0] if promotion_options else None
    return {
        "artifact_dir": str(artifact_dir),
        "artifact_prefix": artifact_prefix,
        "latest_combined": str(latest_combined) if latest_combined is not None else None,
        "model_count": sum(len(files) for files in model_groups.values()),
        "metrics_count": sum(len(files) for files in metrics_groups.values()),
        "benchmark_winner": benchmark_winner,
        "latest_promotable": promotion_options[0] if promotion_options else None,
        "promotion_options": promotion_options,
        "by_feature": by_feature,
    }


def _artifact_feature_summary(feature_set: str, *, latest_model: Path | None, latest_metrics: Path | None) -> dict[str, object]:
    if latest_model is not None:
        paired_metrics = _artifact_metrics_path(latest_model)
        if paired_metrics.exists() and not _metrics_are_calibrated(_read_metrics(paired_metrics)):
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
    by_feature = {str(row.get("feature_set")): row for row in ranked_with_ranks}
    ordered: list[dict[str, object]] = []
    if ranked_with_ranks:
        ordered.append(ranked_with_ranks[0])
    combined = by_feature.get("combined")
    if combined is not None and combined not in ordered:
        ordered.append(combined)
    for row in ranked_with_ranks:
        if row not in ordered:
            ordered.append(row)
    return ordered


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


def _latest_uncalibrated_artifact(paths: list[Path]) -> Path | None:
    for path in paths:
        if not _artifact_has_calibrated_metrics(path):
            return path
    return None


def _latest_uncalibrated_metrics(paths: list[Path]) -> Path | None:
    for path in paths:
        if not _metrics_are_calibrated(_read_metrics(path)):
            return path
    return None


def _artifact_has_calibrated_metrics(path: Path) -> bool:
    metrics_path = _artifact_metrics_path(path)
    return metrics_path.exists() and _metrics_are_calibrated(_read_metrics(metrics_path))


def _artifact_metrics_path(path: Path) -> Path:
    return path.with_suffix(".metrics.json")


def _metrics_are_calibrated(metrics: dict[str, object]) -> bool:
    calibration = metrics.get("production_calibration")
    return isinstance(calibration, dict) and calibration.get("status") == "calibrated"


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


def _training_readiness_error(profile: ClassifierProfile, added: dict[str, int]) -> str:
    if profile.profile_type == "multiclass":
        counts = ", ".join(f"{label} {int(added.get(label, 0))}" for label in profile.training_label_keys)
        return (
            f"Need {profile.training_min_added} new labels for each multiclass training class since the last "
            f"training checkpoint. Added: {counts}."
        )
    return (
        f"Need {profile.training_min_added} new {profile.positive_label} and "
        f"{profile.training_min_added} new {profile.negative_label} labels since the last training checkpoint. "
        f"Added: {profile.positive_label} {added[profile.positive_label]}, "
        f"{profile.negative_label} {added[profile.negative_label]}."
    )


def _index_html() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def _schedule_process_shutdown() -> None:
    timer = threading.Timer(0.2, lambda: os._exit(0))
    timer.daemon = True
    timer.start()

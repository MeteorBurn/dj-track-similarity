from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.dependencies import require_ffmpeg

from .cli import DEFAULT_CLASSIFIER_TARGET_ROOT, PromotionError, promote_profile_model
from .lab_db import ClassifierProfile, RhythmLabDatabase
from .predictions import apply_model_to_lab
from .source_db import SourceDatabase
from .training import benchmark_lab_database


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}
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


class LabelRenameRequest(BaseModel):
    new_key: str
    name: str | None = None
    description: str | None = None


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
) -> FastAPI:
    labels_path = Path(labels_db_path)
    labels_db = RhythmLabDatabase(labels_path)
    source_state = SourceDatabaseState(source_db_path)
    target_root = Path(classifier_target_root) if classifier_target_root is not None else DEFAULT_CLASSIFIER_TARGET_ROOT
    app = FastAPI(title="Rhythm Lab")

    def profile_db(profile_key: str) -> RhythmLabDatabase:
        return RhythmLabDatabase(labels_path, classifier_key=profile_key)

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
        liked: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = "all",
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        profile = profile_or_404(profile_key)
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            return source.list_tracks_page(
                labels_db_path=labels_path,
                classifier_key=profile.classifier_key,
                label_keys=profile.label_keys,
                training_label_keys=profile.training_label_keys,
                query=q,
                syncopated=syncopated,
                liked=liked,
                label=label,
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

    @app.post("/api/profiles/{profile_key}/promote")
    def promote_profile(profile_key: str):
        profile = profile_or_404(profile_key)
        readiness = _training_readiness(profile_db(profile.classifier_key), artifact_dir=Path(profile.artifact_dir), profile=profile)
        artifact_summary = readiness.get("artifact_summary")
        latest_combined = artifact_summary.get("latest_combined") if isinstance(artifact_summary, dict) else None
        if not latest_combined:
            raise HTTPException(
                status_code=400,
                detail=f"Train a combined model before promoting {profile.name}.",
            )
        try:
            result = promote_profile_model(
                labels_path,
                profile.classifier_key,
                artifact_path=Path(str(latest_combined)),
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
        if path.suffix.lower() in AIFF_PREVIEW_SUFFIXES:
            try:
                return _transcoded_wav_file_response(path, require_ffmpeg())
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(path)

    return app


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


def _latest_combined_artifact(artifact_dir: Path, artifact_prefix: str) -> Path | None:
    artifacts = list(artifact_dir.glob(f"{artifact_prefix}-combined-*.joblib"))
    if not artifacts:
        return None
    return max(artifacts, key=lambda path: (path.stat().st_mtime, path.name))


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
    return {
        "artifact_dir": str(artifact_dir),
        "artifact_prefix": artifact_prefix,
        "latest_combined": str(latest_combined) if latest_combined is not None else None,
        "model_count": sum(len(files) for files in model_groups.values()),
        "metrics_count": sum(len(files) for files in metrics_groups.values()),
        "by_feature": [
            _artifact_feature_summary(
                feature,
                latest_model=(model_groups.get(feature) or [None])[0],
                latest_metrics=(metrics_groups.get(feature) or [None])[0],
            )
            for feature in sorted(set(model_groups) | set(metrics_groups))
        ],
    }


def _artifact_feature_summary(feature_set: str, *, latest_model: Path | None, latest_metrics: Path | None) -> dict[str, object]:
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


def _metric_summary(metrics: dict[str, object]) -> dict[str, object]:
    cross_validation = metrics.get("cross_validation")
    if not isinstance(cross_validation, dict):
        cross_validation = {}
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


def _transcoded_wav_file_response(path: Path, ffmpeg_path: str) -> FileResponse:
    with tempfile.NamedTemporaryFile(prefix="rhythm-lab-preview-", suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
        "pcm_s16le",
        "-y",
        str(temp_path),
    ]
    try:
        subprocess.run(command, stderr=subprocess.PIPE, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        _delete_temp_file(temp_path)
        LOGGER.warning("ffmpeg preview transcode failed path=%s error=%s", path, error)
        raise RuntimeError("AIFF preview transcode failed") from error
    return FileResponse(
        temp_path,
        media_type="audio/wav",
        filename=f"{path.stem}.wav",
        content_disposition_type="inline",
        background=BackgroundTask(_delete_temp_file, temp_path),
    )


def _delete_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Failed to delete temporary Rhythm Lab preview file: %s", path)


def _index_html() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

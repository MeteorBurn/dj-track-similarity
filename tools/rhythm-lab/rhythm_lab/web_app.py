from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import tempfile
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from dj_track_similarity.dependencies import require_ffmpeg

from .lab_db import BREAK_ENERGY_CLASSIFIER_KEY, ClassifierProfile, RhythmLabDatabase
from .predictions import apply_model_to_lab, latest_predictions_by_track
from .source_db import SourceDatabase
from .training import benchmark_lab_database


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}
STATIC_DIR = Path(__file__).with_name("static")
FAVICON_PATH = STATIC_DIR / "favicon.svg"
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "break-energy"
ARTIFACT_PREFIX = "break-energy"
TRAIN_REFRESH_MIN_ADDED = 100
KEEP_JOBLIB_PER_FEATURE = 3
KEEP_METRICS_PER_FEATURE = 10


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class SourceSwitchRequest(BaseModel):
    path: str


class ProfileLabelRequest(BaseModel):
    key: str
    name: str | None = None
    description: str = ""
    role: str


class ProfileRequest(BaseModel):
    classifier_key: str
    name: str
    description: str = ""
    artifact_dir: str | None = None
    artifact_prefix: str | None = None
    labels: list[ProfileLabelRequest]


class ProfilePatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    artifact_dir: str | None = None
    artifact_prefix: str | None = None
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


def create_app(source_db_path: str | Path | None = None, *, labels_db_path: str | Path) -> FastAPI:
    labels_path = Path(labels_db_path)
    labels_db = RhythmLabDatabase(labels_path)
    source_state = SourceDatabaseState(source_db_path)
    app = FastAPI(title="Rhythm Lab")

    def profile_db(profile_key: str = BREAK_ENERGY_CLASSIFIER_KEY) -> RhythmLabDatabase:
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
                name=request.name,
                description=request.description,
                artifact_dir=request.artifact_dir,
                artifact_prefix=request.artifact_prefix,
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
                name=request.name,
                description=request.description,
                artifact_dir=request.artifact_dir,
                artifact_prefix=request.artifact_prefix,
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
            "mert": 0,
            "maest": 0,
            "source": source_state.current(),
        }
        if source is None:
            return base
        return {
            **base,
            "tracks": source.count_tracks(),
            "mert": source.count_embeddings("mert"),
            "maest": source.count_embeddings("maest"),
        }

    @app.get("/api/profiles/{profile_key}/tracks")
    def profile_tracks(
        profile_key: str,
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
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
                query=q,
                syncopated=syncopated,
                label=label,
                limit=limit,
                offset=offset,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

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
        min_positive: float = Query(default=0.0, ge=0.0, le=1.0),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        profile = profile_or_404(profile_key)
        if label not in {"all", "unlabeled", *profile.label_keys}:
            raise HTTPException(status_code=400, detail=f"Unknown label filter: {label}")
        if predicted not in {"all", *profile.training_label_keys}:
            raise HTTPException(status_code=400, detail=f"Unknown predicted label filter: {predicted}")
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        scoped = profile_db(profile.classifier_key)
        labels_by_track = scoped.labels_by_track()
        rows: list[tuple[dict[str, object], str | None, float, float]] = []
        for row in latest_predictions_by_track(scoped.predictions()):
            manual_label = labels_by_track.get(int(row["source_track_id"]))
            manual_label_value = manual_label.label if manual_label is not None else None
            positive_probability = _prediction_probability(row, profile.positive_label)
            negative_probability = _prediction_probability(row, profile.negative_label)
            if positive_probability < min_positive:
                continue
            if predicted != "all" and row["label"] != predicted:
                continue
            if label == "unlabeled" and manual_label_value is not None:
                continue
            if label not in {"all", "unlabeled"} and manual_label_value != label:
                continue
            rows.append((row, manual_label_value, positive_probability, negative_probability))
        common_filters_active = bool(q.strip()) or syncopated != "all"
        source_tracks = (
            source.tracks_by_ids(int(row["source_track_id"]) for row, _, _, _ in rows)
            if common_filters_active
            else {}
        )
        items = []
        for row, manual_label_value, positive_probability, negative_probability in rows:
            track = source_tracks.get(int(row["source_track_id"]))
            if common_filters_active and (
                track is None or not _candidate_matches_common_filters(track, query=q, syncopated=syncopated)
            ):
                continue
            items.append(
                _profile_prediction_item(
                    row,
                    manual_label_value,
                    positive_probability,
                    negative_probability,
                    profile=profile,
                )
            )
        items.sort(key=lambda item: _profile_candidate_sort_key(item, probability_focus=probability_focus))
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        page_items = items[bounded_offset : bounded_offset + bounded_limit]
        if page_items:
            page_tracks = source_tracks if common_filters_active else source.tracks_by_ids(int(item["id"]) for item in page_items)
            mert_track_ids = source.embedding_track_ids("mert")
            maest_track_ids = source.embedding_track_ids("maest")
            for item in page_items:
                track = page_tracks.get(int(item["id"]))
                if track is not None:
                    item.update(_candidate_source_fields(track, mert_track_ids=mert_track_ids, maest_track_ids=maest_track_ids))
        return {
            "items": page_items,
            "total": len(items),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

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
                detail=(
                    f"Need {TRAIN_REFRESH_MIN_ADDED} new {profile.positive_label} and "
                    f"{TRAIN_REFRESH_MIN_ADDED} new {profile.negative_label} labels since the last training checkpoint. "
                    f"Added: {profile.positive_label} {added[profile.positive_label]}, "
                    f"{profile.negative_label} {added[profile.negative_label]}."
                ),
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

    @app.get("/api/summary")
    def summary():
        source = source_state.source
        if source is None:
            return {"tracks": 0, "labels": labels_db.label_counts(), "mert": 0, "maest": 0, "source": source_state.current()}
        return {
            "tracks": source.count_tracks(),
            "labels": labels_db.label_counts(),
            "mert": source.count_embeddings("mert"),
            "maest": source.count_embeddings("maest"),
            "source": source_state.current(),
        }

    @app.get("/api/tracks")
    def tracks(
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = Query(default="all", pattern="^(all|unlabeled|broken|straight|ambiguous)$"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            return source.list_tracks_page(
                labels_db_path=labels_db.path,
                query=q,
                syncopated=syncopated,
                label=label,
                limit=limit,
                offset=offset,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/predictions")
    def predictions(
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = Query(default="unlabeled", pattern="^(all|unlabeled|broken|straight|ambiguous)$"),
        predicted: str = Query(default="all", pattern="^(all|broken|straight)$"),
        probability_focus: str = Query(default="broken_highest", pattern="^(broken_highest|straight_highest|balanced)$"),
        min_broken: float = Query(default=0.0, ge=0.0, le=1.0),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        labels_by_track = labels_db.labels_by_track()
        rows: list[tuple[dict[str, object], str | None, float]] = []
        for row in latest_predictions_by_track(labels_db.predictions()):
            manual_label = labels_by_track.get(int(row["source_track_id"]))
            manual_label_value = manual_label.label if manual_label is not None else None
            broken_probability = _prediction_probability(row, "broken")
            if broken_probability < min_broken:
                continue
            if predicted != "all" and row["label"] != predicted:
                continue
            if label == "unlabeled" and manual_label_value is not None:
                continue
            if label not in {"all", "unlabeled"} and manual_label_value != label:
                continue
            rows.append((row, manual_label_value, broken_probability))
        common_filters_active = bool(q.strip()) or syncopated != "all"
        source_tracks = (
            source.tracks_by_ids(int(row["source_track_id"]) for row, _, _ in rows) if common_filters_active else {}
        )
        items = []
        for row, manual_label_value, broken_probability in rows:
            track = source_tracks.get(int(row["source_track_id"]))
            if common_filters_active and (
                track is None or not _candidate_matches_common_filters(track, query=q, syncopated=syncopated)
            ):
                continue
            items.append(_prediction_item(row, manual_label_value, broken_probability))
        items.sort(key=lambda item: _candidate_sort_key(item, probability_focus=probability_focus))
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        page_items = items[bounded_offset : bounded_offset + bounded_limit]
        if page_items:
            page_tracks = source_tracks if common_filters_active else source.tracks_by_ids(int(item["id"]) for item in page_items)
            mert_track_ids = source.embedding_track_ids("mert")
            maest_track_ids = source.embedding_track_ids("maest")
            for item in page_items:
                track = page_tracks.get(int(item["id"]))
                if track is not None:
                    item.update(_candidate_source_fields(track, mert_track_ids=mert_track_ids, maest_track_ids=maest_track_ids))
        return {
            "items": page_items,
            "total": len(items),
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    @app.post("/api/predictions/refresh")
    def refresh_predictions():
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        artifact = _latest_combined_artifact(ARTIFACT_DIR)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"No combined Break Energy model artifact found in {ARTIFACT_DIR}")
        try:
            result = apply_model_to_lab(source_state.path, labels_db.path, artifact)
            deleted = labels_db.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
        except Exception as error:
            LOGGER.exception("Break Energy predictions refresh failed")
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {**result, "artifact": str(artifact), "deleted_old_predictions": deleted}

    @app.get("/api/training/readiness")
    def training_readiness():
        return _training_readiness(labels_db, artifact_dir=ARTIFACT_DIR)

    @app.post("/api/training/train-refresh")
    def train_refresh():
        source = source_state.source
        if source is None or source_state.path is None:
            raise HTTPException(status_code=400, detail="Source database is not selected")
        readiness = _training_readiness(labels_db, artifact_dir=ARTIFACT_DIR)
        if readiness["ready"] is not True:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Need 100 new broken and 100 new straight Break Energy labels since the last training checkpoint. "
                    f"Added: broken {readiness['added']['broken']}, straight {readiness['added']['straight']}."
                ),
            )
        counts = dict(readiness["current"])
        try:
            training = benchmark_lab_database(source_state.path, labels_db.path, ARTIFACT_DIR)
            artifact = _latest_combined_artifact(ARTIFACT_DIR)
            if artifact is None:
                raise RuntimeError(f"No combined Break Energy model artifact found in {ARTIFACT_DIR}")
            result = apply_model_to_lab(source_state.path, labels_db.path, artifact)
            deleted = labels_db.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
            labels_db.record_training_checkpoint(counts, model_artifact=artifact)
            cleanup = cleanup_training_artifacts(ARTIFACT_DIR, protected_artifact=artifact)
        except Exception as error:
            LOGGER.exception("Break Energy train + refresh failed")
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {
            "training": training,
            "artifact": str(artifact),
            "training_counts": counts,
            **result,
            "deleted_old_predictions": deleted,
            "artifact_cleanup": cleanup,
        }

    @app.post("/api/tracks/{track_id}/label")
    def set_label(track_id: int, request: LabelRequest):
        try:
            track = source_state.require_source().get_track(track_id)
            label = labels_db.set_label(track, request.label, note=request.note)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"track_id": track_id, "label": label.label if label else None}

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
        "name": profile.name,
        "description": profile.description,
        "artifact_dir": profile.artifact_dir,
        "artifact_prefix": profile.artifact_prefix,
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


def _prediction_probability(row: dict[str, object], label: str) -> float:
    probabilities = row.get("probabilities")
    if not isinstance(probabilities, dict):
        return 0.0
    try:
        return float(probabilities.get(label, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _latest_combined_artifact(artifact_dir: Path, artifact_prefix: str = ARTIFACT_PREFIX) -> Path | None:
    artifacts = list(artifact_dir.glob(f"{artifact_prefix}-combined-*.joblib"))
    if not artifacts:
        return None
    return max(artifacts, key=lambda path: (path.stat().st_mtime, path.name))


def cleanup_training_artifacts(
    artifact_dir: Path,
    *,
    protected_artifact: Path,
    artifact_prefix: str = ARTIFACT_PREFIX,
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
    artifact_prefix: str = ARTIFACT_PREFIX,
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


def _artifact_feature(name: str, *, suffix: str, artifact_prefix: str = ARTIFACT_PREFIX) -> str | None:
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
        checkpoint_counts = dict(counts)
        checkpoint_artifact = str(latest_artifact)
    added = {
        label: max(0, counts[label] - int(checkpoint_counts.get(label, 0)))
        for label in profile.training_label_keys
    }
    ready = all(added[label] >= TRAIN_REFRESH_MIN_ADDED for label in profile.training_label_keys)
    return {
        "ready": ready,
        "current": counts,
        "last_trained": {label: int(checkpoint_counts.get(label, 0)) for label in profile.training_label_keys},
        "added": added,
        "required_added": {label: TRAIN_REFRESH_MIN_ADDED for label in profile.training_label_keys},
        "model_artifact": checkpoint_artifact,
    }


def _training_label_counts(counts: dict[str, int], *, profile: ClassifierProfile) -> dict[str, int]:
    return {label: int(counts.get(label, 0)) for label in profile.training_label_keys}


def _prediction_item(row: dict[str, object], manual_label: str | None, broken_probability: float) -> dict[str, object]:
    return {
        "id": int(row["source_track_id"]),
        "source_track_id": int(row["source_track_id"]),
        "path": row["path"],
        "artist": row["artist"],
        "title": row["title"],
        "label": manual_label,
        "predicted_label": row["label"],
        "confidence": float(row["confidence"]),
        "broken_probability": float(broken_probability),
        "straight_probability": _prediction_probability(row, "straight"),
        "feature_set": row["feature_set"],
        "model_artifact": row["model_artifact"],
        "genres": [],
        "maest_syncopated_rhythm": False,
        "feature_status": {"sonara": False, "mert": False, "maest": False},
    }


def _profile_prediction_item(
    row: dict[str, object],
    manual_label: str | None,
    positive_probability: float,
    negative_probability: float,
    *,
    profile: ClassifierProfile,
) -> dict[str, object]:
    return {
        "id": int(row["source_track_id"]),
        "source_track_id": int(row["source_track_id"]),
        "path": row["path"],
        "artist": row["artist"],
        "title": row["title"],
        "label": manual_label,
        "predicted_label": row["label"],
        "confidence": float(row["confidence"]),
        "positive_probability": float(positive_probability),
        "negative_probability": float(negative_probability),
        "positive_label": profile.positive_label,
        "negative_label": profile.negative_label,
        "probabilities": row.get("probabilities") if isinstance(row.get("probabilities"), dict) else {},
        "feature_set": row["feature_set"],
        "model_artifact": row["model_artifact"],
        "genres": [],
        "maest_syncopated_rhythm": False,
        "feature_status": {"sonara": False, "mert": False, "maest": False},
    }


def _candidate_sort_key(item: dict[str, object], *, probability_focus: str) -> tuple[float, float, str]:
    broken_probability = float(item["broken_probability"])
    straight_probability = float(item["straight_probability"])
    confidence = float(item["confidence"])
    path = str(item["path"])
    if probability_focus == "straight_highest":
        return (-straight_probability, -confidence, path)
    if probability_focus == "balanced":
        return (abs(broken_probability - straight_probability), -confidence, path)
    return (-broken_probability, -confidence, path)


def _profile_candidate_sort_key(item: dict[str, object], *, probability_focus: str) -> tuple[float, float, str]:
    positive_probability = float(item["positive_probability"])
    negative_probability = float(item["negative_probability"])
    confidence = float(item["confidence"])
    path = str(item["path"])
    if probability_focus == "negative_highest":
        return (-negative_probability, -confidence, path)
    if probability_focus == "balanced":
        return (abs(positive_probability - negative_probability), -confidence, path)
    return (-positive_probability, -confidence, path)


def _candidate_source_fields(track, *, mert_track_ids: set[int], maest_track_ids: set[int]) -> dict[str, object]:
    metadata = track.metadata or {}
    return {
        "artist": track.artist,
        "title": track.title,
        "path": track.path,
        "genres": track.genres,
        "genre_scores": track.genre_scores,
        "maest_syncopated_rhythm": metadata.get("maest_syncopated_rhythm") is True,
        "feature_status": {
            "sonara": isinstance(metadata.get("sonara_features"), dict),
            "mert": track.id in mert_track_ids,
            "maest": track.id in maest_track_ids,
        },
    }


def _candidate_matches_common_filters(track, *, query: str, syncopated: str) -> bool:
    metadata = track.metadata or {}
    is_syncopated = metadata.get("maest_syncopated_rhythm") is True
    if syncopated == "yes" and not is_syncopated:
        return False
    if syncopated == "no" and is_syncopated:
        return False
    if syncopated != "all" and syncopated not in {"yes", "no"}:
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    needle = query.strip().casefold()
    if not needle:
        return True
    haystack = " ".join(
        str(value or "")
        for value in (
            track.artist,
            track.title,
            track.album,
            track.path,
            metadata,
        )
    ).casefold()
    return needle in haystack


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

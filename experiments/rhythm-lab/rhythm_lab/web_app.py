from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from dj_track_similarity.dependencies import require_ffmpeg

from .lab_db import RHYTHM_LABELS, RhythmLabDatabase
from .predictions import apply_model_to_lab, latest_predictions_by_track
from .source_db import SourceDatabase
from .training import benchmark_lab_database


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}
FAVICON_PATH = Path(__file__).with_name("static") / "favicon.svg"
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"
TRAIN_REFRESH_MIN_ADDED = 100
KEEP_JOBLIB_PER_FEATURE = 3
KEEP_METRICS_PER_FEATURE = 10


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class SourceSwitchRequest(BaseModel):
    path: str


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
    labels_db = RhythmLabDatabase(labels_db_path)
    source_state = SourceDatabaseState(source_db_path)
    app = FastAPI(title="Rhythm Lab")

    @app.get("/")
    def index():
        return HTMLResponse(_index_html())

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(FAVICON_PATH, media_type="image/svg+xml")

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
            raise HTTPException(status_code=404, detail=f"No combined rhythm model artifact found in {ARTIFACT_DIR}")
        try:
            result = apply_model_to_lab(source_state.path, labels_db.path, artifact)
            deleted = labels_db.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
        except Exception as error:
            LOGGER.exception("Rhythm predictions refresh failed")
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
                    "Need 100 new broken and 100 new straight labels since the last training checkpoint. "
                    f"Added: broken {readiness['added']['broken']}, straight {readiness['added']['straight']}."
                ),
            )
        counts = dict(readiness["current"])
        try:
            training = benchmark_lab_database(source_state.path, labels_db.path, ARTIFACT_DIR)
            artifact = _latest_combined_artifact(ARTIFACT_DIR)
            if artifact is None:
                raise RuntimeError(f"No combined rhythm model artifact found in {ARTIFACT_DIR}")
            result = apply_model_to_lab(source_state.path, labels_db.path, artifact)
            deleted = labels_db.prune_predictions(
                feature_set=str(result["feature_set"]),
                keep_model_artifact=artifact,
            )
            labels_db.record_training_checkpoint(counts, model_artifact=artifact)
            cleanup = cleanup_training_artifacts(ARTIFACT_DIR, protected_artifact=artifact)
        except Exception as error:
            LOGGER.exception("Rhythm train + refresh failed")
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
                return _transcoded_wav_response(path, require_ffmpeg())
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(path)

    return app


def _prediction_probability(row: dict[str, object], label: str) -> float:
    probabilities = row.get("probabilities")
    if not isinstance(probabilities, dict):
        return 0.0
    try:
        return float(probabilities.get(label, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _latest_combined_artifact(artifact_dir: Path) -> Path | None:
    artifacts = list(artifact_dir.glob("rhythm-combined-*.joblib"))
    if not artifacts:
        return None
    return max(artifacts, key=lambda path: (path.stat().st_mtime, path.name))


def cleanup_training_artifacts(
    artifact_dir: Path,
    *,
    protected_artifact: Path,
    keep_joblib_per_feature: int = KEEP_JOBLIB_PER_FEATURE,
    keep_metrics_per_feature: int = KEEP_METRICS_PER_FEATURE,
) -> dict[str, int]:
    protected = protected_artifact.resolve(strict=False)
    deleted = {"deleted_joblib": 0, "deleted_metrics": 0}
    for suffix, keep_count, key in (
        (".joblib", keep_joblib_per_feature, "deleted_joblib"),
        (".metrics.json", keep_metrics_per_feature, "deleted_metrics"),
    ):
        for files in _artifact_groups(artifact_dir, suffix=suffix).values():
            for path in files[keep_count:]:
                if path.resolve(strict=False) == protected:
                    continue
                path.unlink()
                deleted[key] += 1
    return deleted


def _artifact_groups(artifact_dir: Path, *, suffix: str) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in artifact_dir.glob(f"rhythm-*{suffix}"):
        feature = _artifact_feature(path.name, suffix=suffix)
        if feature is None:
            continue
        groups.setdefault(feature, []).append(path)
    for files in groups.values():
        files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return groups


def _artifact_feature(name: str, *, suffix: str) -> str | None:
    if not name.startswith("rhythm-") or not name.endswith(suffix):
        return None
    stem = name[: -len(suffix)]
    parts = stem.split("-")
    if len(parts) < 3:
        return None
    return parts[1]


def _training_readiness(labels_db: RhythmLabDatabase, *, artifact_dir: Path) -> dict[str, object]:
    counts = _training_label_counts(labels_db.label_counts())
    checkpoint = labels_db.training_checkpoint()
    checkpoint_counts = dict(checkpoint["counts"])
    checkpoint_artifact = checkpoint["model_artifact"]
    latest_artifact = _latest_combined_artifact(artifact_dir)
    if checkpoint_artifact is None and latest_artifact is not None:
        labels_db.record_training_checkpoint(counts, model_artifact=latest_artifact)
        checkpoint_counts = dict(counts)
        checkpoint_artifact = str(latest_artifact)
    added = {
        "broken": max(0, counts["broken"] - int(checkpoint_counts.get("broken", 0))),
        "straight": max(0, counts["straight"] - int(checkpoint_counts.get("straight", 0))),
    }
    ready = added["broken"] >= TRAIN_REFRESH_MIN_ADDED and added["straight"] >= TRAIN_REFRESH_MIN_ADDED
    return {
        "ready": ready,
        "current": counts,
        "last_trained": {
            "broken": int(checkpoint_counts.get("broken", 0)),
            "straight": int(checkpoint_counts.get("straight", 0)),
        },
        "added": added,
        "required_added": {"broken": TRAIN_REFRESH_MIN_ADDED, "straight": TRAIN_REFRESH_MIN_ADDED},
        "model_artifact": checkpoint_artifact,
    }


def _training_label_counts(counts: dict[str, int]) -> dict[str, int]:
    return {"broken": int(counts.get("broken", 0)), "straight": int(counts.get("straight", 0))}


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


def _transcoded_wav_response(path: Path, ffmpeg_path: str) -> StreamingResponse:
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
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def iter_wav_chunks():
        try:
            if process.stdout is None:
                return
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
            return_code = process.wait()
            if return_code != 0:
                LOGGER.warning("ffmpeg preview transcode failed path=%s return_code=%s", path, return_code)
        finally:
            if process.poll() is None:
                process.kill()

    return StreamingResponse(iter_wav_chunks(), media_type="audio/wav")


def _index_html() -> str:
    labels = ", ".join(RHYTHM_LABELS)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  <title>Rhythm Lab</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #111; color: #eee; }}
    header, main {{ max-width: 1200px; margin: 0 auto; padding: 16px; }}
    header {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; border-bottom: 1px solid #333; }}
    input, select, button {{ background: #1e1e1e; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 8px; }}
    input.source-path {{ min-width: min(520px, 100%); flex: 1 1 360px; }}
    button {{ cursor: pointer; }}
    button:hover {{ border-color: #888; }}
    button:disabled {{ cursor: default; opacity: 0.45; }}
    .active {{ outline: 2px solid #e0b84b; }}
    .tabs {{ display: flex; gap: 6px; flex: 1 1 100%; }}
    .tabs button.active {{ background: #e0b84b; color: #141414; outline: none; }}
    .refresh-candidates {{ padding: 5px 9px; font-size: 12px; border-color: #5f8dd3; background: #17345f; color: #eaf2ff; }}
    .refresh-candidates:hover {{ border-color: #8eb8f4; background: #214674; }}
    .train-refresh {{ padding: 5px 9px; font-size: 12px; border-color: #9a7a39; background: #342715; color: #ffe6ad; }}
    .train-refresh:hover:not(:disabled) {{ border-color: #e0b84b; background: #47371d; }}
    .filters {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .filters[hidden] {{ display: none; }}
    .source-row {{ display: flex; gap: 6px; align-items: center; flex: 1 1 100%; }}
    .source-status {{ color: #aaa; font-size: 13px; min-width: 160px; }}
    .source-status.error {{ color: #ff8f8f; }}
    .pager {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
    .track {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; padding: 12px 0; border-bottom: 1px solid #2b2b2b; }}
    .track-main {{ display: flex; flex-direction: column; gap: 3px; }}
    .meta {{ color: #aaa; font-size: 13px; line-height: 1.42; }}
    .track-number {{ color: #888; font-variant-numeric: tabular-nums; margin-right: 6px; }}
    .feature-line {{ margin-top: 1px; }}
    .genres-line {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 5px 0 0; }}
    .rhythm-media-block {{ margin-top: 7px; }}
    .genres {{ color: #e0b84b; font-size: 13px; font-weight: 700; }}
    .badge-row {{ display: inline-flex; gap: 6px; align-items: center; }}
    .syncopated-badge,
    .rhythm-label-badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 12px; line-height: 1.35; font-weight: 700; }}
    .syncopated-badge {{ background: #d7aa32; color: #141414; }}
    .rhythm-label-badge {{ background: #7d5cff; color: #fff; }}
    .rhythm-label-badge.broken {{ background: #dc2626; color: #fff; }}
    .rhythm-label-badge.straight {{ background: #2563eb; color: #fff; }}
    .rhythm-label-badge.ambiguous {{ background: #7d5cff; color: #fff; }}
    .badge-separator {{ color: #777; font-size: 12px; }}
    .actions {{ display: flex; gap: 6px; align-items: start; flex-wrap: wrap; justify-content: end; }}
    audio {{ width: min(520px, 100%); height: 34px; margin-top: 6px; }}
  </style>
</head>
<body>
  <header>
    <strong>Rhythm Lab</strong>
    <div class="source-row">
      <input id="sourcePath" class="source-path" placeholder="C:\\db\\abstracted.sqlite" title="Existing dj-track-similarity SQLite database. Opened read-only." />
      <button id="chooseSource" title="Choose existing SQLite database">Browse</button>
      <button id="loadSource" title="Load selected source database">Load database</button>
      <span id="sourceStatus" class="source-status"></span>
    </div>
    <div class="tabs">
      <button id="libraryTab" class="active">Library</button>
      <button id="candidatesTab">Candidates</button>
      <button id="refreshCandidates" class="refresh-candidates" title="Recompute candidates from the latest combined Rhythm Lab model">Refresh candidates</button>
      <button id="trainRefresh" class="train-refresh" title="Train a new model only after 100 new broken and 100 new straight labels, then refresh candidates">Train + refresh</button>
      <span id="refreshCandidatesStatus" class="meta"></span>
    </div>
    <div id="commonFilters" class="filters">
      <input id="query" placeholder="search path/title/artist" />
      <select id="syncopated">
        <option value="all">all rhythm</option>
        <option value="yes">syncopated rhythm</option>
        <option value="no">no syncopated rhythm</option>
      </select>
      <select id="label">
        <option value="all">all</option>
        <option value="unlabeled">unlabeled</option>
        <option value="broken">broken</option>
        <option value="straight">straight</option>
        <option value="ambiguous">ambiguous</option>
      </select>
    </div>
    <div id="candidateFilters" class="filters" hidden>
      <select id="candidatePredicted">
        <option value="all" selected>all predictions</option>
        <option value="broken">predicted broken</option>
        <option value="straight">predicted straight</option>
      </select>
      <select id="candidateMinBroken">
        <option value="broken_highest" selected>highest P(broken)</option>
        <option value="straight_highest">highest P(straight)</option>
        <option value="balanced">P(broken) near P(straight)</option>
      </select>
    </div>
    <button id="load">Load</button>
    <div class="pager">
      <button id="prevPage">Prev</button>
      <select id="pageSize">
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="200">200</option>
        <option value="500">500</option>
      </select>
      <button id="nextPage">Next</button>
      <span id="pageInfo" class="meta"></span>
    </div>
    <span id="summary"></span>
  </header>
  <main>
    <p class="meta">Labels: {labels}. Keyboard on focused row: 1 broken, 2 straight, 3 ambiguous, 0 clear.</p>
    <div id="tracks"></div>
  </main>
  <script>
    const tracksEl = document.getElementById("tracks");
    const queryEl = document.getElementById("query");
    const sourcePathEl = document.getElementById("sourcePath");
    const sourceStatusEl = document.getElementById("sourceStatus");
    const libraryTabEl = document.getElementById("libraryTab");
    const candidatesTabEl = document.getElementById("candidatesTab");
    const candidateFiltersEl = document.getElementById("candidateFilters");
    const syncopatedEl = document.getElementById("syncopated");
    const labelEl = document.getElementById("label");
    const candidatePredictedEl = document.getElementById("candidatePredicted");
    const candidateMinBrokenEl = document.getElementById("candidateMinBroken");
    const refreshCandidatesEl = document.getElementById("refreshCandidates");
    const trainRefreshEl = document.getElementById("trainRefresh");
    const refreshCandidatesStatusEl = document.getElementById("refreshCandidatesStatus");
    const summaryEl = document.getElementById("summary");
    const pageSizeEl = document.getElementById("pageSize");
    const prevPageEl = document.getElementById("prevPage");
    const nextPageEl = document.getElementById("nextPage");
    const pageInfoEl = document.getElementById("pageInfo");
    let offset = 0;
    let total = 0;
    let activeAudio = null;
    let activeView = "library";
    const viewOffsets = {{ library: 0, candidates: 0 }};
    let loadSequence = 0;
    document.getElementById("load").addEventListener("click", () => loadActive({{ reset: true }}));
    libraryTabEl.addEventListener("click", () => switchView("library"));
    candidatesTabEl.addEventListener("click", () => switchView("candidates"));
    document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(console.error));
    document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(console.error));
    sourcePathEl.addEventListener("keydown", event => {{ if (event.key === "Enter") switchSource(sourcePathEl.value).catch(console.error); }});
    queryEl.addEventListener("keydown", event => {{ if (event.key === "Enter") loadActive({{ reset: true }}); }});
    syncopatedEl.addEventListener("change", () => loadActive({{ reset: true }}));
    labelEl.addEventListener("change", () => loadActive({{ reset: true }}));
    candidatePredictedEl.addEventListener("change", () => loadActive({{ reset: true }}));
    candidateMinBrokenEl.addEventListener("change", () => loadActive({{ reset: true }}));
    refreshCandidatesEl.addEventListener("click", () => refreshCandidates().catch(console.error));
    trainRefreshEl.addEventListener("click", () => trainRefresh().catch(console.error));
    pageSizeEl.addEventListener("change", () => loadActive({{ reset: true }}));
    prevPageEl.addEventListener("click", () => {{
      offset = Math.max(0, offset - pageLimit());
      loadActive();
    }});
    nextPageEl.addEventListener("click", () => {{
      offset = Math.min(Math.max(0, total - 1), offset + pageLimit());
      loadActive();
    }});

    async function switchView(view) {{
      viewOffsets[activeView] = offset;
      activeView = view;
      offset = viewOffsets[view] || 0;
      libraryTabEl.classList.toggle("active", view === "library");
      candidatesTabEl.classList.toggle("active", view === "candidates");
      candidateFiltersEl.hidden = view !== "candidates";
      await loadActive();
    }}

    async function loadActive(options = {{}}) {{
      if (activeView === "candidates") return loadCandidates(options);
      return loadTracks(options);
    }}

    async function loadSourceState() {{
      const data = await fetch("/api/source/current").then(r => r.json());
      applySourceState(data);
    }}

    async function chooseSource() {{
      clearSourceError();
      sourceStatusEl.textContent = "opening picker...";
      const response = await fetch("/api/source/dialog", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{}}) }});
      const data = await parseJsonResponse(response);
      sourcePathEl.value = data.path || sourcePathEl.value || "";
      sourceStatusEl.textContent = data.path ? "path selected" : "no source database";
      sourceStatusEl.classList.remove("error");
    }}

    async function switchSource(path) {{
      clearSourceError();
      sourceStatusEl.textContent = "loading...";
      const response = await fetch("/api/source/switch", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ path }})
      }});
      const data = await parseJsonResponse(response);
      applySourceState(data);
      await loadActive({{ reset: true }});
    }}

    function applySourceState(data) {{
      sourcePathEl.value = data.path || sourcePathEl.value || "";
      sourceStatusEl.textContent = data.selected ? "loaded read-only" : "no source database";
      sourceStatusEl.classList.remove("error");
    }}

    function clearSourceError() {{
      sourceStatusEl.classList.remove("error");
    }}

    async function parseJsonResponse(response) {{
      const data = await response.json();
      if (!response.ok) {{
        sourceStatusEl.textContent = data.detail || response.statusText;
        sourceStatusEl.classList.add("error");
        throw new Error(data.detail || response.statusText);
      }}
      return data;
    }}

    async function loadSummary(sequence = loadSequence) {{
      const data = await fetch("/api/summary").then(r => r.json());
      if (sequence !== loadSequence) return;
      summaryEl.textContent = `${{data.tracks}} tracks | MAEST ${{data.maest}} | MERT ${{data.mert}} – Labels: ${{formatLabelCounts(data.labels)}}`;
    }}

    function formatLabelCounts(labels) {{
      const counts = labels || {{}};
      return [
        `broken ${{counts.broken || 0}}`,
        `straight ${{counts.straight || 0}}`,
        `ambiguous ${{counts.ambiguous || 0}}`
      ].join(" · ");
    }}

    async function loadTracks(options = {{}}) {{
      const sequence = ++loadSequence;
      if (options.reset) offset = 0;
      viewOffsets.library = offset;
      const limit = pageLimit();
      const params = new URLSearchParams({{
        q: queryEl.value,
        syncopated: syncopatedEl.value,
        label: labelEl.value,
        limit: String(limit),
        offset: String(offset)
      }});
      const data = await fetch(`/api/tracks?${{params}}`).then(r => r.json());
      if (sequence !== loadSequence || activeView !== "library") return;
      total = data.total;
      offset = data.offset;
      viewOffsets.library = offset;
      tracksEl.innerHTML = "";
      data.items.forEach((track, index) => {{
        track.rowNumber = data.offset + index + 1;
        tracksEl.appendChild(renderTrack(track));
      }});
      updatePager(data);
      await loadSummary(sequence);
      await loadTrainingReadiness();
    }}

    async function loadCandidates(options = {{}}) {{
      const sequence = ++loadSequence;
      if (options.reset) offset = 0;
      viewOffsets.candidates = offset;
      const limit = pageLimit();
      const params = new URLSearchParams({{
        q: queryEl.value,
        syncopated: syncopatedEl.value,
        label: labelEl.value,
        predicted: candidatePredictedEl.value,
        probability_focus: candidateMinBrokenEl.value,
        limit: String(limit),
        offset: String(offset)
      }});
      const data = await fetch(`/api/predictions?${{params}}`).then(r => r.json());
      if (sequence !== loadSequence || activeView !== "candidates") return;
      total = data.total;
      offset = data.offset;
      viewOffsets.candidates = offset;
      tracksEl.innerHTML = "";
      data.items.forEach((track, index) => {{
        track.rowNumber = data.offset + index + 1;
        tracksEl.appendChild(renderCandidate(track));
      }});
      updatePager(data);
      await loadSummary(sequence);
      await loadTrainingReadiness();
    }}

    async function refreshCandidates() {{
      refreshCandidatesEl.disabled = true;
      refreshCandidatesStatusEl.textContent = "refreshing...";
      try {{
        const response = await fetch("/api/predictions/refresh", {{ method: "POST" }});
        const data = await parseRefreshResponse(response);
        refreshCandidatesStatusEl.textContent = `updated ${{data.predicted}} · skipped ${{data.skipped}} · removed old ${{data.deleted_old_predictions}}`;
        await loadCandidates({{ reset: true }});
      }} finally {{
        refreshCandidatesEl.disabled = false;
      }}
    }}

    async function trainRefresh() {{
      if (trainRefreshEl.disabled) return;
      if (!window.confirm("Train a new Rhythm Lab model from current broken/straight labels, then refresh candidates?")) return;
      trainRefreshEl.disabled = true;
      refreshCandidatesEl.disabled = true;
      refreshCandidatesStatusEl.textContent = "training...";
      try {{
        const response = await fetch("/api/training/train-refresh", {{ method: "POST" }});
        const data = await parseRefreshResponse(response);
        refreshCandidatesStatusEl.textContent = `trained ${{data.training_counts.broken}}/${{data.training_counts.straight}} · updated ${{data.predicted}} · skipped ${{data.skipped}}`;
        await loadCandidates({{ reset: true }});
      }} finally {{
        refreshCandidatesEl.disabled = false;
        await loadTrainingReadiness();
      }}
    }}

    async function loadTrainingReadiness() {{
      const response = await fetch("/api/training/readiness");
      const data = await response.json();
      if (!response.ok) {{
        trainRefreshEl.disabled = true;
        return;
      }}
      trainRefreshEl.disabled = !data.ready;
      trainRefreshEl.title = data.ready
        ? "Train a new model, then refresh candidates"
        : `Need +${{data.required_added.broken}} broken and +${{data.required_added.straight}} straight since last train. Added: broken ${{data.added.broken}}, straight ${{data.added.straight}}.`;
    }}

    async function parseRefreshResponse(response) {{
      const data = await response.json();
      if (!response.ok) {{
        refreshCandidatesStatusEl.textContent = data.detail || response.statusText;
        throw new Error(data.detail || response.statusText);
      }}
      return data;
    }}

    function pageLimit() {{
      return Number(pageSizeEl.value || 100);
    }}

    function updatePager(data) {{
      const shown = data.items.length;
      const first = shown ? data.offset + 1 : 0;
      const last = shown ? data.offset + shown : 0;
      pageInfoEl.textContent = `${{first}}-${{last}} / ${{data.total}}`;
      prevPageEl.disabled = data.offset <= 0;
      nextPageEl.disabled = data.offset + data.limit >= data.total;
    }}

    function renderTrack(track) {{
      const row = document.createElement("section");
      row.className = "track";
      row.tabIndex = 0;
      row.innerHTML = `
        <div>
          <div class="track-main">
            <strong><span class="track-number">#${{track.rowNumber}}</span>${{escapeHtml(displayTrackTitle(track))}}</strong>
          <div class="meta track-path">${{escapeHtml(track.path)}}</div>
          <div class="meta feature-line">SONARA ${{mark(track.feature_status.sonara)}} · MERT ${{mark(track.feature_status.mert)}} · MAEST ${{mark(track.feature_status.maest)}} · label <b>${{track.label || "none"}}</b></div>
          </div>
          <div class="rhythm-media-block">
            <div class="genres-line"><span class="genres">${{(track.genres || []).map(escapeHtml).join(" · ")}}</span>${{badgeRow(track)}}</div>
            <audio controls preload="none" src="/media/${{track.id}}"></audio>
          </div>
        </div>
        <div class="actions">
          <button data-label="broken">Broken</button>
          <button data-label="straight">Straight</button>
          <button data-label="ambiguous">Ambiguous</button>
          <button data-label="">Clear</button>
        </div>`;
      row.querySelectorAll("button").forEach(button => {{
        button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
        if ((button.dataset.label || null) === track.label) {{
          button.classList.add("active");
        }}
      }});
      row.addEventListener("keydown", event => {{
        const keys = {{ "1": "broken", "2": "straight", "3": "ambiguous", "0": "" }};
        if (keys[event.key] !== undefined) setLabel(track.id, keys[event.key]);
      }});
      wireAudioPreview(row.querySelector("audio"));
      return row;
    }}

    function renderCandidate(track) {{
      const row = document.createElement("section");
      row.className = "track";
      row.tabIndex = 0;
      row.innerHTML = `
        <div>
          <div class="track-main">
            <strong><span class="track-number">#${{track.rowNumber}}</span>${{escapeHtml(displayTrackTitle(track))}}</strong>
            <div class="meta track-path">${{escapeHtml(track.path)}}</div>
            <div class="meta feature-line">SONARA ${{mark(track.feature_status.sonara)}} · MERT ${{mark(track.feature_status.mert)}} · MAEST ${{mark(track.feature_status.maest)}} · label <b>${{track.label || "none"}}</b></div>
            <div class="meta feature-line">P(broken) ${{formatProbability(track.broken_probability)}} · P(straight) ${{formatProbability(track.straight_probability)}} · predicted <b>${{escapeHtml(track.predicted_label)}}</b> · ${{escapeHtml(track.feature_set)}}</div>
          </div>
          <div class="rhythm-media-block">
            <div class="genres-line"><span class="genres">${{(track.genres || []).map(escapeHtml).join(" · ")}}</span>${{badgeRow(track)}}</div>
            <audio controls preload="none" src="/media/${{track.id}}"></audio>
          </div>
        </div>
        <div class="actions">
          <button data-label="broken">Broken</button>
          <button data-label="straight">Straight</button>
          <button data-label="ambiguous">Ambiguous</button>
          <button data-label="">Clear</button>
        </div>`;
      row.querySelectorAll("button").forEach(button => {{
        button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
        if ((button.dataset.label || null) === track.label) {{
          button.classList.add("active");
        }}
      }});
      row.addEventListener("keydown", event => {{
        const keys = {{ "1": "broken", "2": "straight", "3": "ambiguous", "0": "" }};
        if (keys[event.key] !== undefined) setLabel(track.id, keys[event.key]);
      }});
      wireAudioPreview(row.querySelector("audio"));
      return row;
    }}

    function wireAudioPreview(audio) {{
      if (!audio) return;
      audio.addEventListener("play", () => {{
        if (activeAudio && activeAudio !== audio) {{
          activeAudio.pause();
          activeAudio.currentTime = 0;
        }}
        activeAudio = audio;
      }});
      audio.addEventListener("ended", () => {{
        if (activeAudio === audio) activeAudio = null;
      }});
      audio.addEventListener("pause", () => {{
        if (activeAudio === audio && audio.currentTime === 0) activeAudio = null;
      }});
    }}

    async function setLabel(trackId, label) {{
      await fetch(`/api/tracks/${{trackId}}/label`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ label }})
      }});
      await loadActive();
    }}

    function formatProbability(value) {{ return Number(value || 0).toFixed(3); }}
    function mark(value) {{ return value ? "yes" : "no"; }}
    function badgeRow(track) {{
      const badges = [syncopatedBadge(track), rhythmLabelBadge(track)].filter(Boolean);
      return badges.length ? `<div class="badge-row">${{badges.join('<span class="badge-separator">·</span>')}}</div>` : "";
    }}
    function syncopatedBadge(track) {{ return track.maest_syncopated_rhythm === true ? '<span class="syncopated-badge">syncopated rhythm</span>' : ""; }}
    function rhythmLabelBadge(track) {{ return track.label ? `<span class="rhythm-label-badge ${{escapeHtml(track.label)}} label-${{escapeHtml(track.label)}}">${{escapeHtml(track.label)}}</span>` : ""; }}
    function displayTrackTitle(track) {{
      const title = track.title || track.path;
      return track.artist ? `${{track.artist}} - ${{title}}` : title;
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}
    loadSourceState().then(() => loadActive({{ reset: true }}));
  </script>
</body>
</html>"""

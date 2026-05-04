from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .analysis_jobs import AnalysisJobManager
from .database import LibraryDatabase
from .embedding import FakeEmbeddingAdapter, MertEmbeddingAdapter
from .exporter import export_playlist
from .scan_jobs import ScanJobManager
from .search import SearchFilters, SimilaritySearch
from .tags import apply_custom_tags, build_tag_preview


class ScanRequest(BaseModel):
    root: str
    workers: int = Field(default=1, ge=1, le=64)


class AnalyzeRequest(BaseModel):
    limit: int | None = None
    adapter: str = Field(default="mert", pattern="^(mert|fake)$")
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    batch_size: int = Field(default=4, ge=1, le=64)
    workers: int | None = Field(default=None, ge=1, le=64)


class SearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seed_track_ids: list[int]
    lookback_track_ids: list[int] = Field(default_factory=list)
    limit: int = 50
    bpm_tolerance: float | None = None
    key_compatibility: str | None = None
    energy_min: float | None = None
    energy_max: float | None = None
    min_similarity: float | None = None
    epsilon: float | None = Field(default=None, alias="Epsilon")
    noise: float = 0.0


class PlaylistRequest(BaseModel):
    name: str
    track_ids: list[int]


class ExportRequest(BaseModel):
    playlist_id: int
    output_dir: str
    format: str = Field(default="m3u", pattern="^(m3u|csv)$")


class TagRequest(BaseModel):
    track_ids: list[int]


def open_folder_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("Native folder dialog is unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askdirectory(parent=root, title="Выберите папку с музыкой", mustexist=True)
    finally:
        root.destroy()
    return Path(selected) if selected else None


def create_app(db_path: str | Path = "dj-track-similarity.sqlite") -> FastAPI:
    db = LibraryDatabase(db_path)
    analysis_jobs = AnalysisJobManager(db)
    scan_jobs = ScanJobManager(db)
    app = FastAPI(title="dj-track-similarity Utility")

    @app.post("/api/library/scan")
    def scan(request: ScanRequest):
        return scan_jobs.start(request.root, workers=request.workers)

    @app.get("/api/library/scan/jobs/latest")
    def latest_scan_job():
        return scan_jobs.latest()

    @app.get("/api/library/scan/jobs/{job_id}")
    def scan_job(job_id: str):
        try:
            return scan_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/library/scan/jobs/{job_id}/cancel")
    def cancel_scan_job(job_id: str):
        try:
            return scan_jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/tracks")
    def tracks():
        return db.list_tracks()

    @app.post("/api/analyze")
    def analyze(request: AnalyzeRequest):
        return analysis_jobs.start(
            adapter_name=request.adapter,
            limit=request.limit,
            batch_size=request.batch_size,
            workers=request.workers,
            device=request.device,
        )

    @app.get("/api/analyze/jobs/latest")
    def latest_analyze_job():
        return analysis_jobs.latest()

    @app.get("/api/analyze/jobs/{job_id}")
    def analyze_job(job_id: str):
        try:
            return analysis_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analyze/jobs/{job_id}/cancel")
    def cancel_analyze_job(job_id: str):
        try:
            return analysis_jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/search")
    def search(request: SearchRequest):
        filters = SearchFilters(
            bpm_tolerance=request.bpm_tolerance,
            key_compatibility=request.key_compatibility,
            energy_min=request.energy_min,
            energy_max=request.energy_max,
            min_similarity=request.min_similarity,
            epsilon=request.epsilon,
            noise=request.noise,
        )
        try:
            return SimilaritySearch(db).search(
                request.seed_track_ids,
                lookback_track_ids=request.lookback_track_ids,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/playlists")
    def playlists(request: PlaylistRequest):
        playlist_id = db.create_playlist(request.name, request.track_ids)
        return {"id": playlist_id, "name": request.name, "track_ids": request.track_ids}

    @app.post("/api/export")
    def export(request: ExportRequest):
        path = export_playlist(db, request.playlist_id, request.output_dir, request.format)
        return {"path": str(path)}

    @app.post("/api/tags/preview")
    def tags_preview(request: TagRequest):
        return build_tag_preview(db, request.track_ids)

    @app.post("/api/tags/apply")
    def tags_apply(request: TagRequest):
        return apply_custom_tags(db, request.track_ids)

    @app.post("/api/dialog/folder")
    def folder_dialog():
        try:
            selected = open_folder_dialog()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"path": str(selected) if selected else None}

    @app.get("/media/{track_id}")
    def media(track_id: int):
        track = db.get_track(track_id)
        path = Path(track.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        return FileResponse(path)

    package_path = Path(__file__).resolve()
    static_candidates = [
        package_path.parents[2] / "frontend" / "dist",
        package_path.parent.parent / "frontend" / "dist",
    ]
    static_dir = next((candidate for candidate in static_candidates if candidate.exists()), None)
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app

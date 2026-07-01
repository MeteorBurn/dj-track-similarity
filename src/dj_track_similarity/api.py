from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api_routes_audio_dedup import register_audio_dedup_routes
from .api_routes_audio_doctor import register_audio_doctor_routes
from .api_routes_docs import register_docs_routes
from .api_routes_analysis import register_analysis_routes
from .api_routes_database import register_database_routes
from .api_routes_evaluation import register_evaluation_routes
from .api_routes_library import register_library_routes
from .api_routes_rhythm_lab import register_rhythm_lab_routes
from .api_routes_search import register_search_routes
from .api_routes_set_builder import register_set_builder_routes
from .api_routes_tags_export import register_tags_export_routes
from .api_state import AppDatabaseState, DatabaseBusy, DatabaseNotSelected
from .classifier_scoring import promoted_classifiers
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .logging_config import configure_logging
from .rhythm_lab_launcher import launch_rhythm_lab, rhythm_lab_status, stop_rhythm_lab


LOGGER = logging.getLogger(__name__)


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


def open_database_file_dialog() -> Path | None:
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
        selected = filedialog.asksaveasfilename(
            parent=root,
            title="Выберите SQLite базу",
            defaultextension=".sqlite",
            filetypes=[("SQLite database", "*.sqlite"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
    finally:
        root.destroy()
    if not selected:
        return None
    path = Path(selected)
    return path.with_suffix(".sqlite") if not path.suffix else path


def create_app(
    db_path: str | Path | None = None,
    *,
    log_level: int | str | None = None,
    log_track_events: bool | None = None,
) -> FastAPI:
    log_path = configure_logging(level=log_level, log_track_events=log_track_events)
    ffmpeg_path = require_ffmpeg()
    LOGGER.info("API app created db_path=%s log_path=%s", db_path, log_path)
    LOGGER.debug("ffmpeg available path=%s", ffmpeg_path)
    state = AppDatabaseState(db_path)
    app = FastAPI(title="dj-track-similarity Utility")

    @app.exception_handler(DatabaseNotSelected)
    async def database_not_selected(_: Request, error: DatabaseNotSelected):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(DatabaseBusy)
    async def database_busy(_: Request, error: DatabaseBusy):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    register_database_routes(app, state, open_database_file_dialog=open_database_file_dialog)
    register_library_routes(app, state, ffmpeg_path=ffmpeg_path, promoted_classifiers=promoted_classifiers)
    register_analysis_routes(app, state, promoted_classifiers=promoted_classifiers)
    register_audio_dedup_routes(app, state)
    register_audio_doctor_routes(app, state)
    register_evaluation_routes(app, state)
    register_search_routes(app, state, clap_embedding_adapter=ClapEmbeddingAdapter)
    register_set_builder_routes(app, state, promoted_classifiers=promoted_classifiers)
    register_tags_export_routes(app, state, open_folder_dialog=open_folder_dialog)
    register_rhythm_lab_routes(
        app,
        state,
        launch_rhythm_lab=launch_rhythm_lab,
        stop_rhythm_lab=stop_rhythm_lab,
        rhythm_lab_status=rhythm_lab_status,
    )

    package_path = Path(__file__).resolve()
    register_docs_routes(app, package_path)

    static_candidates = [
        package_path.parents[2] / "frontend" / "dist",
        package_path.parent.parent / "frontend" / "dist",
    ]
    static_dir = next((candidate for candidate in static_candidates if candidate.exists()), None)
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app

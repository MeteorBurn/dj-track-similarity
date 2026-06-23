from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api_schemas import AudioDedupJobRequest
from .api_state import AppDatabaseState
from .audio_dedup_jobs import APPLY_CONFIRMATION


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def register_audio_dedup_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.post("/api/audio-dedup/jobs")
    def start_audio_dedup_job(request: AudioDedupJobRequest):
        if request.apply and request.confirmation != APPLY_CONFIRMATION:
            raise HTTPException(status_code=400, detail=f'Type exactly "{APPLY_CONFIRMATION}" to run apply mode')
        try:
            return state.require_audio_dedup_jobs().start(
                root=request.root,
                path_contains=request.path_contains,
                preset=request.preset,
                min_score=request.min_score,
                min_similarity=request.min_similarity,
                limit_groups=request.limit_groups,
                out_dir=request.out_dir,
                apply=request.apply,
                confirmation=request.confirmation,
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/audio-dedup/jobs/latest")
    def latest_audio_dedup_job():
        return state.require_audio_dedup_jobs().latest()

    @app.get("/api/audio-dedup/jobs/{job_id}")
    def audio_dedup_job(job_id: str):
        try:
            return state.require_audio_dedup_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/audio-dedup/jobs/{job_id}/cancel")
    def cancel_audio_dedup_job(job_id: str):
        try:
            return state.require_audio_dedup_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/audio-dedup/jobs/{job_id}/report/xlsx")
    def audio_dedup_xlsx_report(job_id: str):
        try:
            job = state.require_audio_dedup_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if not job.xlsx_path:
            raise HTTPException(status_code=404, detail="Audio dedup XLSX report is not ready")
        path = Path(job.xlsx_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Audio dedup XLSX report is missing")
        return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=path.name)

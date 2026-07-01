from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .api_schemas import AudioDoctorJobRequest
from .api_state import AppDatabaseState
from .audio_doctor_jobs import APPLY_CONFIRMATION


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def register_audio_doctor_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.post("/api/audio-doctor/jobs")
    def start_audio_doctor_job(request: AudioDoctorJobRequest):
        if request.apply and request.confirmation != APPLY_CONFIRMATION:
            raise HTTPException(status_code=400, detail=f'Type exactly "{APPLY_CONFIRMATION}" to run apply mode')
        try:
            return state.require_audio_doctor_jobs().start(
                source_mode=request.source_mode,
                folder=request.folder,
                db_roots=request.db_roots,
                file_root=request.file_root,
                keep_id3=request.keep_id3,
                limit=request.limit,
                workers=request.workers,
                reasons=request.reasons,
                out_dir=request.out_dir,
                state_path=request.state_path,
                apply=request.apply,
                confirmation=request.confirmation,
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/audio-doctor/jobs/latest")
    def latest_audio_doctor_job():
        return state.require_audio_doctor_jobs().latest()

    @app.get("/api/audio-doctor/jobs/{job_id}")
    def audio_doctor_job(job_id: str):
        try:
            return state.require_audio_doctor_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/audio-doctor/jobs/{job_id}/cancel")
    def cancel_audio_doctor_job(job_id: str):
        try:
            return state.require_audio_doctor_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/audio-doctor/jobs/{job_id}/report/xlsx")
    def audio_doctor_xlsx_report(job_id: str):
        try:
            job = state.require_audio_doctor_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        xlsx_path = job.get("xlsx_path") if isinstance(job, dict) else job.xlsx_path
        if not xlsx_path:
            raise HTTPException(status_code=404, detail="Audio Doctor XLSX report is not ready")
        path = Path(xlsx_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Audio Doctor XLSX report is missing")
        return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=path.name)

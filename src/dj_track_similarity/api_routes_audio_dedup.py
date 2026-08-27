from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .api_schemas import AudioDedupDeleteRequest, AudioDedupScanRequest
from .api_state import AppDatabaseState
from .audio_dedup_bridge import load_audio_dedup_core
from .audio_dedup_reports import (
    DEFAULT_GROUP_PAGE_LIMIT,
    group_page,
    list_reports,
    load_report_payload,
    report_summary,
    report_xlsx_path,
)

APPLY_CONFIRMATION = "APPLY DELETE"


def register_audio_dedup_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.post("/api/audio-dedup/jobs")
    def start_audio_dedup(request: AudioDedupScanRequest):
        try:
            with state.job_start():
                return state.require_audio_dedup_jobs().start(
                    root=request.root,
                    path_contains=list(request.path_contains),
                    search_mode=request.search_mode,
                    preset=request.preset,
                    min_score=request.min_score,
                    min_similarity=request.min_similarity,
                    limit_groups=request.limit_groups,
                    sources=list(request.sources) if request.sources else None,
                    weights=dict(request.weights) if request.weights else None,
                    skip_spectral=request.skip_spectral,
                )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/audio-dedup/jobs/latest")
    def latest_audio_dedup():
        return state.require_audio_dedup_jobs().latest()

    @app.get("/api/audio-dedup/jobs/{job_id}")
    def audio_dedup_job(job_id: str):
        try:
            return state.require_audio_dedup_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/audio-dedup/jobs/{job_id}/cancel")
    def cancel_audio_dedup(job_id: str):
        try:
            return state.require_audio_dedup_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/audio-dedup/reports")
    def audio_dedup_reports():
        return list_reports(state.require_audio_dedup_jobs().out_dir)

    @app.get("/api/audio-dedup/reports/{report_id}")
    def audio_dedup_report(report_id: str):
        manager = state.require_audio_dedup_jobs()
        try:
            return report_summary(manager.out_dir, report_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/audio-dedup/reports/{report_id}/groups")
    def audio_dedup_report_groups(
        report_id: str,
        offset: int = 0,
        limit: int = DEFAULT_GROUP_PAGE_LIMIT,
        confidence: list[str] = Query(default=[]),
        min_fingerprint: float | None = None,
        fake_bitrate_only: bool = False,
        path_contains: str = "",
    ):
        manager = state.require_audio_dedup_jobs()
        try:
            payload = load_report_payload(manager.out_dir, report_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return group_page(
            payload,
            database=state.require_db(),
            report_id=report_id,
            offset=offset,
            limit=limit,
            confidence=tuple(confidence),
            min_fingerprint=min_fingerprint,
            fake_bitrate_only=fake_bitrate_only,
            path_contains=path_contains,
        )

    @app.get("/api/audio-dedup/reports/{report_id}/xlsx")
    def audio_dedup_report_xlsx(report_id: str):
        manager = state.require_audio_dedup_jobs()
        try:
            xlsx_path = report_xlsx_path(manager.out_dir, report_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return FileResponse(
            xlsx_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=xlsx_path.name,
        )

    @app.post("/api/audio-dedup/reports/{report_id}/delete")
    def delete_audio_dedup_duplicates(report_id: str, request: AudioDedupDeleteRequest):
        if request.confirmation != APPLY_CONFIRMATION:
            raise HTTPException(
                status_code=400,
                detail=f'Type exactly "{APPLY_CONFIRMATION}" to delete duplicates',
            )
        manager = state.require_audio_dedup_jobs()
        try:
            payload = load_report_payload(manager.out_dir, report_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            selected_track_ids = _validated_selection(payload, request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        core = load_audio_dedup_core()
        root = str(payload.get("root", ""))
        if not root:
            raise HTTPException(status_code=400, detail="Report has no root to delete inside")
        try:
            with state.exclusive_db("delete duplicate files") as database:
                _require_matching_database(payload, database.path)
                result = core.apply_duplicate_deletions(
                    database=database,
                    root=Path(root),
                    payload=payload,
                    selected_track_ids=selected_track_ids,
                    deletion_mode=request.deletion_mode,
                )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "report_id": report_id,
            "deletion_mode": request.deletion_mode,
            "requested": len(selected_track_ids),
            "deleted_track_ids": list(result.deleted_track_ids),
            "deleted_paths": list(result.deleted_paths),
            "skipped": list(result.skipped),
            "failed": list(result.failed),
            "rhythm_lab_deleted_rows": result.rhythm_lab_deleted_rows,
        }

    _ = start_audio_dedup
    _ = latest_audio_dedup
    _ = audio_dedup_job
    _ = cancel_audio_dedup
    _ = audio_dedup_reports
    _ = audio_dedup_report
    _ = audio_dedup_report_groups
    _ = audio_dedup_report_xlsx
    _ = delete_audio_dedup_duplicates


def _validated_selection(payload: dict, request: AudioDedupDeleteRequest) -> list[int]:
    """Flatten the reviewer's per-group choices, rejecting ids of another group.

    The core needs only track ids, but carrying the group makes a client that
    mixes up a row an explicit request error instead of a silent deletion in the
    wrong place.
    """
    members_by_group: dict[int, set[int]] = {}
    for group in payload.get("groups", []):
        if not isinstance(group, dict):
            continue
        group_id = _int(group.get("group_id"))
        members_by_group[group_id] = {
            _int(entry.get("track_id")) for entry in _group_members(group)
        }
    selected: list[int] = []
    seen: set[int] = set()
    for selection in request.selections:
        members = members_by_group.get(selection.group_id)
        if members is None:
            raise ValueError(f"Unknown group in report: {selection.group_id}")
        for track_id in selection.track_ids:
            if track_id not in members:
                raise ValueError(
                    f"Track {track_id} does not belong to group {selection.group_id}"
                )
            if track_id in seen:
                continue
            seen.add(track_id)
            selected.append(track_id)
    return selected


def _require_matching_database(payload: dict, database_path: Path) -> None:
    """Refuse a report written against another library.

    Identity rechecks would skip every candidate anyway, but saying so up front
    beats reporting a batch where nothing could be deleted.
    """
    reported = payload.get("database_path")
    if not reported:
        return
    if Path(str(reported)).resolve(strict=False) != Path(database_path).resolve(strict=False):
        raise ValueError("Report was written against a different database")


def _group_members(group: dict) -> list[dict]:
    tracks = group.get("tracks")
    if isinstance(tracks, list):
        members = [entry for entry in tracks if isinstance(entry, dict)]
        if members:
            return members
    keeper = group.get("suggested_keeper")
    candidates = group.get("candidate_deletes")
    members = [keeper] if isinstance(keeper, dict) else []
    if isinstance(candidates, list):
        members += [entry for entry in candidates if isinstance(entry, dict)]
    return members


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException

from .api_schemas import (
    EvaluationApplyScoreProfileRequest,
    EvaluationPairFeedbackRequest,
    EvaluationSourceProfileRunRequest,
    EvaluationTransitionFeedbackRequest,
    EvaluationWeightedCandidatesRunRequest,
)
from .api_state import AppDatabaseState
from .database import LibraryDatabase
from .db_schema import CURRENT_SCHEMA_VERSION
from .evaluation.score_profiles import (
    DEFAULT_LIMITATIONS,
    PROFILE_KIND,
    SCORE_PROFILE_VERSION,
    WEIGHT_KIND,
    ScoreProfile,
    build_score_profile_application_report,
    build_score_profile_from_source_report,
    score_profile_from_dict,
    score_profile_to_dict,
)
from .evaluation.seed_sampling import export_seed_sample
from .evaluation.source_profile import build_source_profile
from .evaluation.weighted_candidates import build_weighted_candidate_pool, limit_weighted_candidate_rows_per_seed


def register_evaluation_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.get("/api/evaluation/summary")
    def evaluation_summary():
        db = _require_current_evaluation_db(state)
        try:
            return {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "counts": db.count_evaluation_rows(),
            }
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error

    @app.post("/api/evaluation/feedback/pair")
    def record_pair_feedback(request: EvaluationPairFeedbackRequest):
        db = _require_current_evaluation_db(state)
        try:
            feedback_id = db.upsert_track_pair_feedback(
                request.seed_track_id,
                request.candidate_track_id,
                request.rating,
                reason_tags=request.reason_tags,
                notes=request.notes,
                source=request.source,
            )
        except (ValueError, TypeError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error
        return {
            "id": feedback_id,
            "seed_track_id": request.seed_track_id,
            "candidate_track_id": request.candidate_track_id,
            "rating": request.rating,
            "reason_tags": request.reason_tags,
            "notes": request.notes,
            "source": request.source,
        }

    @app.post("/api/evaluation/feedback/transition")
    def record_transition_feedback(request: EvaluationTransitionFeedbackRequest):
        db = _require_current_evaluation_db(state)
        try:
            feedback_id = db.add_transition_feedback(
                request.outgoing_track_id,
                request.incoming_track_id,
                request.rating,
                risk_tags=request.risk_tags,
                notes=request.notes,
                source=request.source,
            )
        except (ValueError, TypeError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error
        return {
            "id": feedback_id,
            "outgoing_track_id": request.outgoing_track_id,
            "incoming_track_id": request.incoming_track_id,
            "rating": request.rating,
            "risk_tags": request.risk_tags,
            "notes": request.notes,
            "source": request.source,
        }

    @app.post("/api/evaluation/run/source-profile")
    def run_source_profile(request: EvaluationSourceProfileRunRequest):
        db = _require_current_evaluation_db(state)
        try:
            source_profile = build_source_profile(
                db,
                seed_track_ids=request.seed_track_ids,
                sample_count=request.sample_count,
                sources=request.sources,
                per_source=request.per_source,
                top_k_values=request.top_k,
                random_seed=request.random_seed,
            )
            score_profile = _score_profile_from_source_profile(source_profile, request.profile_name, request.include_profile)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error
        return {
            "source_profile": source_profile,
            "score_profile": score_profile,
        }

    @app.post("/api/evaluation/run/apply-score-profile")
    def apply_score_profile(request: EvaluationApplyScoreProfileRequest):
        db = _require_current_evaluation_db(state)
        try:
            score_profile = _score_profile_from_request(request)
            return build_score_profile_application_report(db, score_profile, k_values=request.k, rrf_k=request.rrf_k)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error

    @app.post("/api/evaluation/run/weighted-candidates")
    def run_weighted_candidates(request: EvaluationWeightedCandidatesRunRequest):
        db = _require_current_evaluation_db(state)
        try:
            score_profile = _score_profile_from_request(request)
            seed_track_ids = _weighted_candidate_seed_track_ids(
                db,
                seed_track_ids=request.seed_track_ids,
                sample_count=request.sample_count,
                random_seed=request.random_seed,
            )
            result = build_weighted_candidate_pool(
                db,
                seed_track_ids=seed_track_ids,
                profile=score_profile,
                sources=request.sources,
                per_source=request.per_source,
                random_seed=request.random_seed,
                record_session=request.record_session,
                rrf_k=request.rrf_k,
                transition_risk_weight=request.transition_risk_weight,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error

        preview_rows = limit_weighted_candidate_rows_per_seed(result.rows, request.limit_per_seed)
        return {
            "score_profile": score_profile_to_dict(score_profile),
            "seed_track_ids": list(result.seed_track_ids),
            "sources": list(result.sources),
            "per_source": request.per_source,
            "random_seed": request.random_seed,
            "rrf_k": request.rrf_k,
            "transition_risk_weight": request.transition_risk_weight,
            "limit_per_seed": request.limit_per_seed,
            "rows_total": len(result.rows),
            "rows_returned": len(preview_rows),
            "rows": [row.api_row() for row in preview_rows],
            "warnings": list(result.warnings),
            "session_ids": list(result.session_ids),
            "record_session": request.record_session,
        }

    @app.get("/api/evaluation/reports/latest")
    def latest_evaluation_reports():
        db = _require_current_evaluation_db(state)
        try:
            calibration_runs = _latest_calibration_runs(db)
        except (RuntimeError, sqlite3.OperationalError) as error:
            raise _evaluation_schema_error(error) from error
        if not calibration_runs:
            return {
                "status": "no_persisted_reports",
                "summary": "No persisted evaluation reports were found. CLI JSON report directories are not scanned by the API.",
                "calibration_runs": [],
            }
        return {
            "status": "ok",
            "summary": "Latest persisted calibration_runs rows from the selected SQLite database.",
            "calibration_runs": calibration_runs,
        }


def _require_current_evaluation_db(state: AppDatabaseState) -> LibraryDatabase:
    db = state.require_db()
    try:
        with db.connect() as connection:
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    except RuntimeError as error:
        raise _evaluation_schema_error(error) from error
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise HTTPException(
            status_code=409,
            detail=f"Evaluation API requires SQLite schema v{CURRENT_SCHEMA_VERSION}; found v{schema_version}.",
        )
    return db


def _score_profile_from_source_profile(source_profile: dict[str, Any], profile_name: str | None, include_profile: bool) -> dict[str, Any] | None:
    if not include_profile:
        return None
    if source_profile.get("status") != "ok":
        return None
    score_profile = build_score_profile_from_source_report(source_profile, name=_score_profile_name(profile_name))
    return score_profile_to_dict(score_profile)


def _score_profile_from_request(request: EvaluationApplyScoreProfileRequest | EvaluationWeightedCandidatesRunRequest) -> ScoreProfile:
    if request.profile is not None:
        return score_profile_from_dict(request.profile)
    if request.weights is None:
        raise ValueError("Provide exactly one of profile or weights")
    return score_profile_from_dict(_inline_score_profile_payload(request.weights, request.name))


def _weighted_candidate_seed_track_ids(
    db: LibraryDatabase,
    *,
    seed_track_ids: list[int] | None,
    sample_count: int,
    random_seed: int,
) -> tuple[int, ...]:
    if seed_track_ids is not None:
        return tuple(seed_track_ids)
    sample = export_seed_sample(db, count=sample_count, random_seed=random_seed, require_complete_analysis=True)
    if not sample.rows:
        raise ValueError("No eligible seed tracks were found; provide seed_track_ids or check complete analysis coverage")
    return tuple(row.track_id for row in sample.rows)


def _inline_score_profile_payload(weights: dict[str, float], name: str | None) -> dict[str, Any]:
    sources = list(weights)
    return {
        "name": _score_profile_name(name),
        "profile_kind": PROFILE_KIND,
        "weight_kind": WEIGHT_KIND,
        "sources": sources,
        "weights": weights,
        "created_at": _utc_timestamp(),
        "source_report_summary": {
            "status": "inline_weights",
            "profile_kind": PROFILE_KIND,
            "weight_kind": WEIGHT_KIND,
            "sources": sources,
        },
        "limitations": list(DEFAULT_LIMITATIONS),
        "version": SCORE_PROFILE_VERSION,
    }


def _score_profile_name(value: str | None) -> str:
    if value is None:
        return "api-source-profile"
    text = value.strip()
    if not text:
        raise ValueError("score profile name must not be empty")
    return text


def _latest_calibration_runs(db: LibraryDatabase) -> list[dict[str, Any]]:
    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, profile_name, search_mode, config_json, metrics_json, created_at
            FROM calibration_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """,
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "profile_name": str(row["profile_name"]),
            "search_mode": str(row["search_mode"]),
            "config": json.loads(row["config_json"]),
            "metrics": json.loads(row["metrics_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _evaluation_schema_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"Evaluation API requires SQLite schema v{CURRENT_SCHEMA_VERSION}. {error}",
    )


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

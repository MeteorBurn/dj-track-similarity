from __future__ import annotations

from collections.abc import Sequence
import logging

from fastapi import FastAPI, HTTPException

from .schemas import DjSetBuildRequest, DjSetBuildResponse, DjSetPresetResponse
from .state import AppDatabaseState
from ..djset.builder import (
    PRESETS,
    SetDirection,
    SetRecipe,
    SetReference,
    SetStage,
    build_set,
)
from ..search.vector_index import VectorIndexUnavailable


LOGGER = logging.getLogger(__name__)


def _stage_payload(stages: Sequence[SetStage]) -> list[dict[str, object]]:
    return [
        {
            "key": stage.key,
            "share": stage.share,
            "intensity_start": stage.intensity_start,
            "intensity_end": stage.intensity_end,
            "bpm_start": stage.bpm_start,
            "bpm_end": stage.bpm_end,
            "key_step": stage.key_step,
            "key_flip": stage.key_flip,
            "classifiers": [
                {"classifier_key": classifier, "low": low, "high": high}
                for classifier, low, high in stage.classifiers
            ],
        }
        for stage in stages
    ]


def register_djset_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.get("/api/djset/presets", response_model=list[DjSetPresetResponse])
    def dj_set_presets():
        """Every way a set can develop, with the numbers a build uses for it."""

        return [{"key": key, "stages": _stage_payload(stages)} for key, stages in PRESETS.items()]

    @app.post("/api/djset/build", response_model=DjSetBuildResponse)
    def build_dj_set(request: DjSetBuildRequest):
        """Build one ordered set from the recipe; nothing is written."""

        database = state.require_db()
        try:
            build = build_set(
                database,
                SetRecipe(
                    tracks=request.tracks,
                    preset=request.preset,
                    stages=(
                        None
                        if request.stages is None
                        else tuple(
                            SetStage(
                                stage.key,
                                stage.share,
                                stage.intensity_start,
                                stage.intensity_end,
                                stage.bpm_start,
                                stage.bpm_end,
                                stage.key_step,
                                stage.key_flip,
                                tuple(
                                    (classifier.classifier_key, classifier.low, classifier.high)
                                    for classifier in stage.classifiers
                                ),
                            )
                            for stage in request.stages
                        )
                    ),
                    references=tuple(
                        SetReference(reference.track_id, reference.role, reference.slot)
                        for reference in request.references
                    ),
                    pool_model=request.pool_model,
                    pool_size=request.pool_size,
                    direction=(
                        None
                        if request.direction is None
                        else SetDirection(
                            request.direction.axis,
                            request.direction.relation,
                            request.direction.margin,
                        )
                    ),
                    variety=request.variety,
                    seed=request.seed,
                ),
            )
            tracks = database.get_track_summaries([slot.target.track_id for slot in build.slots])
        except VectorIndexUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (KeyError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        slots: list[dict[str, object]] = []
        for slot, track in zip(build.slots, tracks, strict=True):
            if track.catalog_uuid != slot.target.catalog_uuid or track.track_uuid != slot.target.track_uuid:
                raise HTTPException(
                    status_code=409,
                    detail=f"Set track became stale before response assembly: track_id={slot.target.track_id}",
                )
            slots.append(
                {
                    "slot": slot.slot,
                    "stage": slot.stage,
                    "drop_entry": slot.drop_entry,
                    "pinned": slot.pinned,
                    "track": track,
                    "score": slot.score,
                    "score_breakdown": dict(slot.score_breakdown),
                    "out_of_tolerance": slot.out_of_tolerance,
                }
            )
        LOGGER.info(
            "DJ set built preset=%s seed=%s slots=%s out_of_tolerance=%s failure=%s seconds=%.1f funnel=%s",
            build.preset,
            build.seed,
            len(slots),
            build.audit.out_of_tolerance,
            build.failure,
            build.elapsed_seconds,
            ",".join(f"{stage.key}:{stage.remaining}" for stage in build.funnel),
        )
        return {
            "seed": build.seed,
            "preset": build.preset,
            "stages": _stage_payload(build.stages),
            "funnel": [{"key": stage.key, "remaining": stage.remaining} for stage in build.funnel],
            "failure": build.failure,
            "slots": slots,
            "audit": {
                "transitions": build.audit.transitions,
                "out_of_tolerance": build.audit.out_of_tolerance,
                "worst_slot": build.audit.worst_slot,
            },
            "elapsed_seconds": build.elapsed_seconds,
        }

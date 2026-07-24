from __future__ import annotations

from dj_track_similarity.hybrid_explanation import MATCH_CHARACTER_AXES
from dj_track_similarity.hybrid_search import HybridSearchResultRow
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary


RISK_BREAKDOWN_KEYS = {
    "bpm",
    "tonal",
    "energy_jump",
    "density_jump",
    "texture_clash",
    "mood_clash",
    "vocal_conflict",
    "grid_instability",
    "structure_transition",
    "source_disagreement",
    "confidence_missingness",
}


def _summary() -> TrackSummary:
    return TrackSummary(
        track_id=2,
        catalog_uuid="00000000-0000-4000-8000-000000000001",
        track_uuid="00000000-0000-4000-8000-000000000002",
        content_generation=1,
        file_path="C:/music/candidate.wav",
        title="Candidate",
        artist="Artist",
        album=None,
        tag_bpm=124.0,
        tag_key="8A",
        audio_duration_seconds=240.0,
        liked=False,
        analysis_coverage=AnalysisCoverage(mert=True),
        classifier_scores=(),
    )


def test_hybrid_result_rows_expose_explanation_contract() -> None:
    row = HybridSearchResultRow(
        track=_summary(),
        score=0.8,
        total_score=0.8,
        calibrated_score=None,
        adjusted_score=0.8,
        transition_risk=0.2,
        transition_risk_penalty=0.0,
        transition_risk_weight=0.0,
        raw_rrf_score=0.8,
        rank=1,
        score_breakdown={
            "mert": {
                "rank": 1,
                "weight": 1.0,
                "contribution": 0.8,
                "score": 0.9,
            }
        },
        risk_breakdown={key: 0.0 for key in RISK_BREAKDOWN_KEYS},
        source_support={
            "mert": {
                "available": True,
                "rank": 1,
                "score": 0.9,
            }
        },
        classifier_support={},
        match_character={axis: 0.5 for axis in MATCH_CHARACTER_AXES},
        warnings=(),
        explanation=("MERT supports this candidate.",),
        transition_diagnostics={"supporting_seed_count": 1},
        diagnostics={"method": "weighted_rrf"},
        feedback=None,
    )

    payload = row.api_row(include_diagnostics=True)

    assert row.total_score == row.score
    assert row.calibrated_score is None
    assert tuple(row.match_character) == MATCH_CHARACTER_AXES
    assert set(row.risk_breakdown) == RISK_BREAKDOWN_KEYS
    assert row.source_support["mert"]["available"] is True
    assert row.classifier_support == {}
    assert row.explanation
    assert payload["track"]["track_id"] == 2
    assert payload["transition_diagnostics"]["supporting_seed_count"] == 1

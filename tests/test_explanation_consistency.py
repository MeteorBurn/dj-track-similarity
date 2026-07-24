from __future__ import annotations

from types import SimpleNamespace

from dj_track_similarity.analysis_models import AnalysisTarget
from dj_track_similarity.hybrid_explanation import build_hybrid_explanation
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.track_models import TrackIdentity
from dj_track_similarity.transition_diagnostics import TransitionTrack


def _transition_track(track_id: int) -> TransitionTrack:
    identity = TrackIdentity(
        catalog_uuid="00000000-0000-4000-8000-000000000001",
        track_id=track_id,
        track_uuid=f"00000000-0000-4000-8000-{track_id:012d}",
        content_generation=1,
    )
    summary = TrackSummary(
        track_id=track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/{track_id}.wav",
        title=f"Track {track_id}",
        artist=f"Artist {track_id}",
        album=None,
        tag_bpm=124.0,
        tag_key="8A",
        audio_duration_seconds=240.0,
        liked=False,
        analysis_coverage=AnalysisCoverage(),
        classifier_scores=(),
    )
    target = AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )
    assert target.track_id == summary.track_id
    return TransitionTrack(identity, summary, None)


def test_hybrid_explanation_source_support_matches_score_breakdown() -> None:
    score_breakdown = {
        "mert": {
            "rank": 1,
            "score": 0.9,
            "weight": 0.5,
            "contribution": 0.5 / 61.0,
        },
        "maest": {
            "rank": 3,
            "score": 0.7,
            "weight": 0.5,
            "contribution": 0.5 / 63.0,
        },
    }
    explanation = build_hybrid_explanation(
        candidate_track=_transition_track(2),
        seed_tracks=(_transition_track(1),),
        source_contributions={
            "mert": SimpleNamespace(rank=1, score=0.9),
            "maest": SimpleNamespace(rank=3, score=0.7),
        },
        source_seed_diagnostics={
            "mert": {
                "best_seed_track_id": 1,
                "best_rank": 1,
                "supporting_seed_track_ids": [1],
            },
            "maest": {
                "best_seed_track_id": 1,
                "best_rank": 3,
                "supporting_seed_track_ids": [1],
            },
        },
        score_breakdown=score_breakdown,
        transition_diagnostics={"components": {}},
        sources=("mert", "maest", "clap"),
        total_score=0.8,
    )

    assert set(explanation.score_breakdown) == {"mert", "maest"}
    assert (
        explanation.source_support["mert"]["rank"]
        == explanation.score_breakdown["mert"]["rank"]
    )
    assert (
        explanation.source_support["maest"]["score"]
        == explanation.score_breakdown["maest"]["score"]
    )
    assert explanation.source_support["clap"]["available"] is False
    assert "MERT" in " ".join(explanation.explanation)
    assert "MAEST" in " ".join(explanation.explanation)

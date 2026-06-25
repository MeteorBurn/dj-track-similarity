from __future__ import annotations

import math

from dj_track_similarity.hybrid_explanation import MATCH_CHARACTER_AXES, build_hybrid_explanation
from dj_track_similarity.models import Track


FORBIDDEN_COPY = ("confidence", "probability", "guaranteed", "perfect transition")
RISK_BREAKDOWN_KEYS = {
    "bpm",
    "tonal",
    "energy_jump",
    "density_jump",
    "texture_clash",
    "mood_clash",
    "vocal_conflict",
    "source_disagreement",
    "confidence_missingness",
}


def test_match_character_axes_are_finite_unit_values() -> None:
    seed = _track(1, bpm=124.0, energy=0.45, features={"bpm": 124.0, "onset_density": 0.6, "danceability": 0.8, "energy": 0.45})
    candidate = _track(2, bpm=126.0, energy=0.5, features={"bpm": 126.0, "onset_density": 0.58, "danceability": 0.75, "energy": 0.5})

    explanation = build_hybrid_explanation(
        candidate_track=candidate,
        seed_tracks=[seed],
        source_contributions={"mert": object(), "sonara": object()},
        source_seed_diagnostics={"mert": {"supporting_seed_track_ids": [1]}, "sonara": {"supporting_seed_track_ids": [1]}},
        score_breakdown={
            "mert": {"rank": 1, "score": 0.9, "weight": 0.5, "contribution": 0.008},
            "sonara": {"rank": 2, "score": 0.86, "weight": 0.5, "contribution": 0.007},
        },
        transition_diagnostics={"components": {"bpm_risk": 0.05, "key_risk": 0.0, "energy_jump_risk": 0.05, "source_disagreement_risk": 0.0}, "warnings": []},
        sources=["mert", "sonara"],
        total_score=0.95,
    )

    assert tuple(explanation.match_character) == MATCH_CHARACTER_AXES
    for value in explanation.match_character.values():
        assert math.isfinite(value)
        assert 0.0 <= value <= 1.0
    assert explanation.calibrated_score is None
    assert explanation.source_support["mert"]["available"] is True
    assert set(explanation.risk_breakdown) == RISK_BREAKDOWN_KEYS
    assert explanation.risk_breakdown["bpm"] == 0.05
    assert explanation.risk_breakdown["tonal"] == 0.0
    assert explanation.risk_breakdown["energy_jump"] == 0.05
    assert explanation.risk_breakdown["source_disagreement"] == 0.0


def test_missing_axis_data_is_neutral_and_marked_unavailable() -> None:
    seed = _track(1)
    candidate = _track(2)

    explanation = build_hybrid_explanation(
        candidate_track=candidate,
        seed_tracks=[seed],
        source_contributions={"mert": object()},
        source_seed_diagnostics={"mert": {"supporting_seed_track_ids": [1]}},
        score_breakdown={"mert": {"rank": 1, "score": 0.8, "weight": 1.0, "contribution": 0.02}},
        transition_diagnostics={"components": {"bpm_risk": None, "key_risk": None, "energy_jump_risk": None, "source_disagreement_risk": 0.0}, "warnings": ["missing_bpm"]},
        sources=["mert", "maest", "sonara", "clap"],
        total_score=1.0,
    )

    assert explanation.match_character["vocalness"] == 0.5
    assert explanation.source_support["clap"]["available"] is False
    assert explanation.risk_breakdown["bpm"] is None
    assert any("unavailable bpm data kept neutral" in warning for warning in explanation.warnings)


def test_warnings_are_severity_sorted_and_avoid_forbidden_copy() -> None:
    explanation = build_hybrid_explanation(
        candidate_track=_track(2),
        seed_tracks=[_track(1)],
        source_contributions={"mert": object()},
        source_seed_diagnostics={"mert": {"supporting_seed_track_ids": [1]}},
        score_breakdown={"mert": {"rank": 1, "score": 0.8, "weight": 1.0, "contribution": 0.02}},
        transition_diagnostics={"components": {"bpm_risk": 0.9, "key_risk": 0.5, "energy_jump_risk": 0.1, "source_disagreement_risk": 0.0}, "warnings": []},
        sources=["mert"],
        total_score=1.0,
    )

    assert explanation.warnings[0] == "Risk estimate: BPM risk is elevated."
    assert explanation.warnings[1] == "Risk estimate: tonal needs a listening check."
    copy = " ".join([*explanation.warnings, *explanation.explanation]).casefold()
    assert not any(forbidden in copy for forbidden in FORBIDDEN_COPY)


def _track(track_id: int, *, bpm: float | None = None, energy: float | None = None, features: dict[str, object] | None = None) -> Track:
    metadata: dict[str, object] = {"artist": f"Artist {track_id}", "title": f"Track {track_id}"}
    if features is not None:
        metadata["sonara_features"] = features
    return Track(
        id=track_id,
        path=f"/tmp/{track_id}.wav",
        size=10,
        mtime=1.0,
        artist=f"Artist {track_id}",
        title=f"Track {track_id}",
        bpm=bpm,
        energy=energy,
        metadata=metadata,
    )

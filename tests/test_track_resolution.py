from __future__ import annotations

import pytest

from dj_track_similarity.models import Track
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature
from dj_track_similarity.track_resolution import (
    attenuate_harmonic_score,
    camelot_compatibility,
    key_name_to_camelot,
    resolve_track_camelot,
    resolve_track_energy,
    resolve_track_key_confidence,
)


def test_resolve_track_camelot_prefers_valid_tag_then_sonara_then_key_name() -> None:
    assert resolve_track_camelot(
        {
            "metadata": {
                "key": "10B",
                "sonara_features": {"key_camelot": {"value": "8A"}, "key": {"value": "F major"}},
            }
        }
    ) == "10B"
    assert resolve_track_camelot(
        {
            "metadata": {
                "key": "F major",
                "sonara_features": {"key_camelot": {"value": "8A"}, "key": {"value": "C minor"}},
            }
        }
    ) == "8A"
    assert resolve_track_camelot(
        {
            "metadata": {
                "key": ["F# minor", "8A"],
                "sonara_features": {"key_camelot": {"value": "9A"}},
            }
        }
    ) == "8A"
    assert resolve_track_camelot({"metadata": {"initialkey": ["F# minor"]}}) == "11A"
    assert resolve_track_camelot(
        {"musical_key": "7B", "metadata": {"sonara_features": {"key_camelot": {"value": "8A"}}}}
    ) == "8A"
    assert resolve_track_camelot(
        {
            "metadata": {
                "key": "F# minor",
                "initialkey": "8A",
                "sonara_features": {"key_camelot": {"value": "9A"}},
            }
        }
    ) == "8A"


@pytest.mark.parametrize(
    ("key_name", "camelot"),
    [("A minor", "8A"), ("Am", "8A"), ("C major", "8B"), ("F# major", "2B"), ("D♭ minor", "12A")],
)
def test_key_name_to_camelot_handles_common_names(key_name: str, camelot: str) -> None:
    assert key_name_to_camelot(key_name) == camelot


def test_camelot_compatibility_is_graded_for_names_and_codes() -> None:
    same = camelot_compatibility("A minor", "8A")
    relative = camelot_compatibility("C major", "8A")
    adjacent = camelot_compatibility("E minor", "8A")
    clash = camelot_compatibility("F# major", "8A")

    assert [relation for relation, _score in (same, relative, adjacent, clash)] == [
        "same",
        "relative",
        "adjacent",
        "clash",
    ]
    assert same[1] > adjacent[1] > relative[1] > clash[1]


def test_key_confidence_is_only_returned_for_sonara_resolved_key() -> None:
    sonara_track = {
        "metadata": {
            "key": "A minor",
            "sonara_features": {"key_camelot": {"value": "8A"}, "key_confidence": {"value": 0.2}},
        }
    }
    tagged_track = {
        "metadata": {
            "key": "8A",
            "sonara_features": {"key_camelot": {"value": "2B"}, "key_confidence": {"value": 0.2}},
        }
    }

    assert resolve_track_key_confidence(sonara_track) == 0.2
    assert resolve_track_key_confidence(tagged_track) is None
    assert attenuate_harmonic_score(1.0, 0.2, 0.2) == pytest.approx(0.75)
    assert attenuate_harmonic_score(0.2, 0.2, 0.2) == pytest.approx(0.3944444444)

    ordinary_tag_wins = {
        "metadata": {
            "key": "F# minor",
            "sonara_features": {"key": {"value": "A minor"}, "key_confidence": {"value": 0.1}},
        }
    }
    assert resolve_track_camelot(ordinary_tag_wins) == "11A"
    assert resolve_track_key_confidence(ordinary_tag_wins) is None


def test_persisted_camelot_ignores_unsigned_sonara_but_accepts_current_signature() -> None:
    metadata = {
        "key": "F major",
        "sonara_features": {"key_camelot": {"value": "8A"}, "key_confidence": {"value": 0.9}},
    }
    stale = Track(id=1, path="stale.wav", size=1, mtime=1.0, musical_key="F major", metadata=dict(metadata))
    current = Track(
        id=2,
        path="current.wav",
        size=1,
        mtime=1.0,
        musical_key="F major",
        metadata={**metadata, "sonara_analysis_signature": expected_sonara_analysis_signature([])},
    )

    assert resolve_track_camelot(stale) == "7B"
    assert resolve_track_key_confidence(stale) is None
    assert resolve_track_camelot(current) == "8A"
    assert resolve_track_key_confidence(current) == pytest.approx(0.9)

    no_tag = Track(
        id=3,
        path="stale-no-tag.wav",
        size=1,
        mtime=1.0,
        musical_key="8A",
        energy=0.9,
        metadata={"sonara_features": {"key_camelot": {"value": "8A"}, "energy": {"value": 0.9}}},
    )
    assert resolve_track_camelot(no_tag) is None
    assert resolve_track_energy(no_tag) is None
    assert resolve_track_key_confidence(no_tag) is None

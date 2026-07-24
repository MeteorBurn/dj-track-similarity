from __future__ import annotations

import pytest

from dj_track_similarity.analysis_contracts import ContractIdentity
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    SonaraFeatureRow,
)
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.track_models import TrackIdentity
from dj_track_similarity.track_resolution import (
    attenuate_harmonic_score,
    camelot_compatibility,
    key_name_to_camelot,
    resolve_track_camelot,
    resolve_track_energy,
    resolve_track_key_confidence,
)


_CORE_OUTPUT = AnalysisOutput(
    ContractIdentity(
        analysis_family="sonara",
        output_kind="core",
        model_name="test-sonara",
        model_version="1",
        release_hash="sha256:" + "1" * 64,
        checkpoint_id="test-checkpoint",
        preprocessing="test-preprocessing",
        parameters={"fixture": "track-resolution"},
    )
)


def _track(
    track_id: int,
    *,
    tag_key: str | None = None,
    sonara_values: dict[str, object] | None = None,
) -> tuple[TrackIdentity, TrackSummary, SonaraFeatureRow | None]:
    identity = TrackIdentity(
        catalog_uuid="fixture-catalog",
        track_id=track_id,
        track_uuid=f"fixture-track-{track_id}",
        content_generation=1,
    )
    summary = TrackSummary(
        track_id=identity.track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/fixture/{track_id}.wav",
        title=f"Track {track_id}",
        artist="Fixture Artist",
        album=None,
        tag_bpm=None,
        tag_key=tag_key,
        audio_duration_seconds=None,
        liked=False,
        analysis_coverage=AnalysisCoverage(sonara_core=sonara_values is not None),
        classifier_scores=(),
    )
    sonara = None
    if sonara_values is not None:
        sonara = SonaraFeatureRow(
            target=AnalysisTarget(
                catalog_uuid=identity.catalog_uuid,
                track_id=identity.track_id,
                track_uuid=identity.track_uuid,
                content_generation=identity.content_generation,
            ),
            output=_CORE_OUTPUT,
            values=sonara_values,
        )
    return identity, summary, sonara


def test_resolve_track_camelot_prefers_valid_tag_then_sonara_then_key_name() -> None:
    identity, track, sonara = _track(
        1,
        tag_key="10B",
        sonara_values={"detected_key_camelot": "8A", "detected_key_name": "F major"},
    )
    assert resolve_track_camelot(identity, track, sonara) == "10B"

    identity, track, sonara = _track(
        2,
        tag_key="F major",
        sonara_values={"detected_key_camelot": "8A", "detected_key_name": "C minor"},
    )
    assert resolve_track_camelot(identity, track, sonara) == "8A"

    identity, track, sonara = _track(
        3,
        tag_key="F# minor",
        sonara_values={"detected_key_camelot": "9A"},
    )
    assert resolve_track_camelot(identity, track, sonara) == "9A"

    identity, track, sonara = _track(4, tag_key="F# minor")
    assert resolve_track_camelot(identity, track, sonara) == "11A"

    identity, track, sonara = _track(5, sonara_values={"detected_key_camelot": "8A"})
    assert resolve_track_camelot(identity, track, sonara) == "8A"


@pytest.mark.parametrize(
    ("key_name", "camelot"),
    [
        ("A minor", "8A"),
        ("Am", "8A"),
        ("C major", "8B"),
        ("F# major", "2B"),
        ("D♭ minor", "12A"),
    ],
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
    identity, track, sonara = _track(
        1,
        tag_key="A minor",
        sonara_values={"detected_key_camelot": "8A", "key_confidence": 0.2},
    )
    assert resolve_track_key_confidence(identity, track, sonara) == 0.2
    assert attenuate_harmonic_score(1.0, 0.2, 0.2) == pytest.approx(0.75)
    assert attenuate_harmonic_score(0.2, 0.2, 0.2) == pytest.approx(0.3944444444)

    identity, track, sonara = _track(
        2,
        tag_key="8A",
        sonara_values={"detected_key_camelot": "2B", "key_confidence": 0.2},
    )
    assert resolve_track_key_confidence(identity, track, sonara) is None

    identity, track, sonara = _track(
        3,
        tag_key="F# minor",
        sonara_values={"detected_key_name": "A minor", "key_confidence": 0.1},
    )
    assert resolve_track_camelot(identity, track, sonara) == "11A"
    assert resolve_track_key_confidence(identity, track, sonara) is None


def test_persisted_camelot_and_energy_require_current_identity_bound_sonara() -> None:
    identity, track, sonara = _track(
        1,
        tag_key="F major",
        sonara_values={
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "energy_score": 0.9,
        },
    )

    assert resolve_track_camelot(identity, track, sonara) == "8A"
    assert resolve_track_key_confidence(identity, track, sonara) == pytest.approx(0.9)
    assert resolve_track_energy(identity, track, sonara) == pytest.approx(0.9)

    no_sonara_identity, no_sonara_track, no_sonara = _track(2, tag_key="8A")
    assert resolve_track_camelot(no_sonara_identity, no_sonara_track, no_sonara) == "8A"
    assert resolve_track_energy(no_sonara_identity, no_sonara_track, no_sonara) is None
    assert resolve_track_key_confidence(no_sonara_identity, no_sonara_track, no_sonara) is None

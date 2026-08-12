from __future__ import annotations

import json
import uuid

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.sonara_runtime import (
    SONARA_UNIT_INTERVAL_FIELDS,
)
from dj_track_similarity.sonara_storage import (
    _IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS,
    prepare_sonara_write,
)


def _candidate() -> AnalysisCandidate:
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid=str(uuid.UUID(int=1)),
            track_id=7,
            track_uuid=str(uuid.UUID(int=2)),
        ),
        file_path="/music/track.wav",
        file_size_bytes=123_456,
        file_modified_ns=456_789,
        missing_outputs=(AnalysisOutput("sonara", "core"),),
    )


def _analysis() -> dict[str, object]:
    return {
        "bpm": 128.0,
        "bpm_raw": 127.8,
        "bpm_confidence": 0.95,
        "bpm_candidates": [(128.0, 0.95)],
        "n_beats": 3,
        "beats": np.asarray([0, 22, 43], dtype=np.int64),
        "key": "A minor",
        "key_camelot": "8A",
        "key_confidence": 0.87,
        "key_candidates": [("A minor", "8A", 0.87)],
        "energy": 0.75,
        "danceability": 0.82,
        "vocalness": 0.3,
        "aggression_score": np.float32(0.5050471),
        "aggression_confidence": np.float32(0.9123457),
        "aggression_forcefulness": np.float32(0.6432198),
        "aggression_harshness": np.float32(0.4789124),
        "aggression_tension": np.float32(0.7312468),
        "aggression_rhythm": np.float32(0.8567891),
        "duration_sec": 180.0,
        "intro_end_sec": 16.0,
        "outro_start_sec": 160.0,
        "energy_curve": np.asarray([0.2, 0.5, 0.8], dtype=np.float32),
        "energy_curve_hop_sec": 0.5,
        "mfcc_mean": np.arange(13, dtype=np.float32),
        "chroma_mean": np.arange(12, dtype=np.float32) / 12.0,
        "spectral_contrast_mean": np.arange(7, dtype=np.float32) / 7.0,
        "onset_frames": np.asarray([0, 10, 20], dtype=np.int64),
        "chord_sequence": ["Am", "F", "C"],
        "chord_events": [{"label": "Am", "start_sec": 0.0, "end_sec": 8.0}],
        "tempo_curve": np.asarray([128.0, 128.1], dtype=np.float32),
        "downbeats": np.asarray([0, 43], dtype=np.int64),
        "segments": [{"start_sec": 0.0, "end_sec": 16.0, "energy": 0.4}],
        "loudness_curve": np.asarray([-10.0, -9.5], dtype=np.float32),
        "embedding": np.linspace(0.05, 0.95, 48, dtype=np.float32),
        "embedding_version": 99,
        "fingerprint": "future-unused-payload",
        "fingerprint_version": 7,
        "provenance": {
            "future_analyzer_parameter": "accepted",
        },
    }


def _prepare(
    analysis: dict[str, object],
):
    return prepare_sonara_write(
        _candidate(),
        analysis,
        analyzed_at="2026-07-23T12:00:00.000000Z",
    )


def test_complete_analyzer_result_becomes_one_typed_sonara_write() -> None:
    analysis = _analysis()

    write = _prepare(analysis)

    assert write.target.track_id == 7
    assert write.core.detected_bpm == 128.0
    assert write.core.beat_count == 3
    assert not hasattr(write, "timeline")
    assert not hasattr(write, "similarity_embedding")
    assert not hasattr(write, "fingerprint")


def test_detected_bpm_preserves_sonara_precision() -> None:
    analysis = _analysis()
    analysis["bpm"] = np.float32(128.125)

    write = _prepare(analysis)

    assert write.core.detected_bpm == float(np.float32(128.125))


def test_aggression_values_preserve_sonara_precision() -> None:
    analysis = _analysis()

    write = _prepare(analysis)

    for field_name in (
        "aggression_score",
        "aggression_confidence",
        "aggression_forcefulness",
        "aggression_harshness",
        "aggression_tension",
        "aggression_rhythm",
    ):
        assert getattr(write.core, field_name) == float(analysis[field_name])


def test_aggression_score_preserves_sonara_abstention() -> None:
    analysis = _analysis()
    analysis["aggression_score"] = None
    analysis["aggression_confidence"] = np.float32(0.0)

    write = _prepare(analysis)

    assert write.core.aggression_score is None
    assert write.core.aggression_confidence == 0.0


def test_unknown_future_analyzer_fields_do_not_gate_conversion() -> None:
    analysis = _analysis()
    analysis["new_sonara_field"] = {"future": True}
    provenance = analysis["provenance"]
    assert isinstance(provenance, dict)
    provenance["future_analyzer_parameter"] = {"enabled": True}

    write = _prepare(analysis)

    assert write.core.vocal_probability == pytest.approx(0.3)
    assert write.outputs == (AnalysisOutput("sonara", "core"),)


def test_declared_clamp_fields_match_converter_implementation() -> None:
    assert _IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS == frozenset(
        SONARA_UNIT_INTERVAL_FIELDS
    )


@pytest.mark.parametrize(
    "value",
    [np.float32(1.001), np.float32(-0.001)],
)
def test_unit_interval_values_inside_epsilon_are_clamped(value: np.float32) -> None:
    analysis = _analysis()
    analysis["energy"] = value

    write = _prepare(analysis)

    assert write.core.energy_score == (1.0 if value > 0 else 0.0)


@pytest.mark.parametrize(
    "value",
    [
        np.nextafter(np.float32(1.001), np.float32(np.inf)),
        np.nextafter(np.float32(-0.001), np.float32(-np.inf)),
    ],
)
def test_unit_interval_values_outside_epsilon_are_rejected(
    value: np.float32,
) -> None:
    analysis = _analysis()
    analysis["energy"] = value

    with pytest.raises(ValueError, match="allowed epsilon"):
        _prepare(analysis)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("mfcc_mean", np.zeros(12, dtype=np.float32), "mfcc_mean"),
        ("chroma_mean", np.zeros((1, 12), dtype=np.float32), "chroma_mean"),
    ],
)
def test_fixed_shape_outputs_reject_wrong_shapes(
    field_name: str,
    value: np.ndarray,
    message: str,
) -> None:
    analysis = _analysis()
    analysis[field_name] = value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis)


def test_non_core_values_are_ignored() -> None:
    analysis = _analysis()
    analysis["embedding"] = np.full(48, np.nan, dtype=np.float32)
    analysis["fingerprint"] = object()
    analysis["segments"] = [{"energy": float("nan")}]

    write = _prepare(analysis)

    assert write.core.detected_bpm == 128.0


def test_track_and_generation_are_copied_from_candidate_not_analyzer_payload() -> None:
    analysis = _analysis()
    analysis["track_id"] = 999

    write = _prepare(analysis)

    assert write.target.track_id == 7
    assert write.core.track_id == 7


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("bpm", 200.0, "at most 180"),
        ("energy_level", 11, "at most 10"),
        ("duration_sec", float("nan"), "finite number"),
        ("intro_end_sec", 181.0, "must not exceed duration"),
    ],
)
def test_representative_scalar_invariants_are_strict(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    analysis = _analysis()
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        (
            "bpm_candidates",
            [{"rank": 1, "bpm": 128.0, "score": 0.95}],
            r"raw \(bpm, score\) pairs",
        ),
        (
            "bpm_candidates",
            [(128.0, 0.5), (127.0, 0.8)],
            "descending score",
        ),
        (
            "key_candidates",
            [("C major", "8B", 0.87)],
            "match the detected key",
        ),
        (
            "key_candidates",
            [("A minor", "8A", 1.01)],
            "allowed epsilon",
        ),
    ],
)
def test_candidate_lists_preserve_shape_order_and_detected_key_invariants(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    analysis = _analysis()
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis)


def test_nested_bounded_values_are_clamped_without_clamping_bpm_scores() -> None:
    analysis = _analysis()
    analysis["energy_curve"] = [-0.0005, 0.5, 1.0005]
    analysis["key_candidates"] = [("A minor", "8A", 1.0005)]
    analysis["segments"] = [
        {"start_sec": 0.0, "end_sec": 16.0, "energy": 1.0005}
    ]
    analysis["bpm_candidates"] = [(128.0, 1.5)]

    write = _prepare(analysis)

    assert write.core.energy_curve_min == 0.0
    assert write.core.energy_curve_max == 1.0
    assert json.loads(write.core.key_candidates_json or "null")[0]["score"] == 1.0
    assert json.loads(write.core.bpm_candidates_json or "null")[0]["score"] == 1.5

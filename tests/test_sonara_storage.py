from __future__ import annotations

import base64
import json
import struct
import uuid

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    SonaraFingerprintOutput,
)
from dj_track_similarity.sonara_runtime import (
    SONARA_OUTPUT_KINDS,
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
            content_generation=3,
        ),
        file_path="/music/track.wav",
        file_size_bytes=123_456,
        file_modified_ns=456_789,
        missing_outputs=tuple(
            AnalysisOutput("sonara", output_kind)
            for output_kind in SONARA_OUTPUT_KINDS
        ),
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
        "fingerprint": base64.b64encode(
            struct.pack("<3I", 0, 123, 4_294_967_295)
        ).decode("ascii"),
        "fingerprint_version": 7,
        "provenance": {
            "future_analyzer_parameter": "accepted",
        },
    }


def _prepare(
    analysis: dict[str, object],
    *,
    outputs: tuple[str, ...] = SONARA_OUTPUT_KINDS,
):
    return prepare_sonara_write(
        _candidate(),
        analysis,
        outputs=outputs,
        analyzed_at="2026-07-23T12:00:00.000000Z",
    )


def test_complete_analyzer_result_becomes_one_typed_sonara_write() -> None:
    analysis = _analysis()

    write = _prepare(analysis)

    assert write.target.track_id == 7
    assert write.target.content_generation == 3
    assert write.core.detected_bpm == 128.0
    assert write.core.beat_count == 3
    assert write.timeline is not None
    assert write.timeline.payload["beats"] == [0, 22, 43]
    assert write.similarity_embedding is not None
    assert write.similarity_embedding.family == "sonara"
    np.testing.assert_array_equal(
        write.similarity_embedding.vector,
        np.asarray(analysis["embedding"], dtype="<f4"),
    )
    assert write.fingerprint is not None
    assert write.fingerprint.fingerprint_version == "7"
    assert write.fingerprint.words.tolist() == [0, 123, 4_294_967_295]


def test_unknown_future_analyzer_fields_do_not_gate_conversion() -> None:
    analysis = _analysis()
    analysis["new_sonara_field"] = {"future": True}
    provenance = analysis["provenance"]
    assert isinstance(provenance, dict)
    provenance["future_analyzer_parameter"] = {"enabled": True}

    write = _prepare(analysis)

    assert write.core.vocal_probability == pytest.approx(0.3)
    assert write.fingerprint is not None
    assert write.fingerprint.fingerprint_version == "7"


def test_output_selection_changes_only_emitted_artifacts() -> None:
    write = _prepare(_analysis(), outputs=("core",))

    assert write.outputs == (AnalysisOutput("sonara", "core"),)
    assert write.timeline is None
    assert write.similarity_embedding is None
    assert write.fingerprint is None


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

    write = _prepare(analysis, outputs=("core",))

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
        _prepare(analysis, outputs=("core",))


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("embedding", np.zeros(47, dtype=np.float32), "embedding must contain"),
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


def test_non_finite_values_are_rejected() -> None:
    analysis = _analysis()
    analysis["embedding"] = np.full(48, np.nan, dtype=np.float32)

    with pytest.raises(ValueError, match="finite"):
        _prepare(analysis)


def test_track_and_generation_are_copied_from_candidate_not_analyzer_payload() -> None:
    analysis = _analysis()
    analysis["track_id"] = 999
    analysis["content_generation"] = 999

    write = _prepare(analysis, outputs=("core",))

    assert write.target.track_id == 7
    assert write.target.content_generation == 3
    assert write.core.track_id == 7
    assert write.core.content_generation == 3


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("segments", None, "timeline output is incomplete"),
        (
            "beats",
            np.asarray([0.0, 22.0, 43.0], dtype=np.float32),
            "frame integer",
        ),
        ("downbeats", np.asarray([1], dtype=np.int64), "subset of timeline.beats"),
        (
            "tempo_curve",
            np.asarray([128.0], dtype=np.float32),
            "length must equal",
        ),
        (
            "chord_events",
            [{"label": "Am", "start": 0.0, "end": 8.0}],
            "contain exactly",
        ),
    ],
)
def test_timeline_requires_complete_native_structure(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    analysis = _analysis()
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis)


@pytest.mark.parametrize(
    ("fingerprint", "message"),
    [
        ("not-base64", "strict base64"),
        (base64.b64encode(b"\x00\x01").decode("ascii"), "complete uint32-le"),
    ],
)
def test_fingerprint_requires_strict_aligned_base64(
    fingerprint: str,
    message: str,
) -> None:
    analysis = _analysis()
    analysis["fingerprint"] = fingerprint

    with pytest.raises(ValueError, match=message):
        _prepare(analysis)


@pytest.mark.parametrize("words", [[-1], [4_294_967_296]])
def test_fingerprint_words_must_fit_uint32(words: list[int]) -> None:
    with pytest.raises(ValueError, match="fit uint32"):
        SonaraFingerprintOutput(
            fingerprint_version="1",
            words=words,
            analyzed_at="2026-07-23T12:00:00.000000Z",
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        (
            "segments",
            [{"start_sec": float("nan"), "end_sec": 1.0, "energy": 0.5}],
        ),
        (
            "chord_events",
            [{"label": "Am", "start_sec": 0.0, "end_sec": float("inf")}],
        ),
        ("loudness_curve", [-10.0, float("nan")]),
    ],
)
def test_timeline_rejects_nested_non_finite_values(
    field_name: str,
    bad_value: object,
) -> None:
    analysis = _analysis()
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match="finite number"):
        _prepare(analysis)


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
    assert write.timeline is not None
    assert write.timeline.payload["segments"][0]["energy"] == 1.0

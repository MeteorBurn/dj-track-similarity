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
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_SCHEMA_VERSION,
    SONARA_EXPECTED_VERSION,
    SONARA_UNIT_INTERVAL_CLAMP_FIELDS,
    SonaraContractSet,
    sonara_requested_features,
    sonara_runtime_contracts,
)
from dj_track_similarity.sonara_storage import (
    _IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS,
    prepare_sonara_write,
)


_BUILD_ID = "sha256:" + "1" * 64
_VOCAL_BUILD_ID = "sha256:" + "2" * 64
_ALL_OUTPUTS = ("core", "timeline", "embedding", "fingerprint")


class FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = _BUILD_ID
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = _VOCAL_BUILD_ID


def _contracts() -> SonaraContractSet:
    return sonara_runtime_contracts(FakeSonara)


def _candidate(contracts: SonaraContractSet) -> AnalysisCandidate:
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
            AnalysisOutput(identity) for identity in contracts.identities
        ),
    )


def _analysis(
    contracts: SonaraContractSet,
) -> dict[str, object]:
    fingerprint = base64.b64encode(struct.pack("<3I", 0, 123, 4_294_967_295)).decode(
        "ascii"
    )
    return {
        "bpm": 128.0,
        "bpm_raw": 127.8,
        "bpm_confidence": 0.95,
        "bpm_candidates": [(128.0, 0.95)],
        "onset_density": 4.2,
        "n_beats": 3,
        "beats": np.asarray([0, 22, 43], dtype=np.int64),
        "tempo_variability": 0.02,
        "grid_offset_sec": 0.01,
        "grid_stability": 0.98,
        "key": "A minor",
        "key_camelot": "8A",
        "key_confidence": 0.87,
        "key_candidates": [("A minor", "8A", 0.87)],
        "predominant_chord": "Am",
        "chord_change_rate": 0.5,
        "energy": 0.75,
        "energy_level": 8,
        "danceability": 0.82,
        "valence": 0.45,
        "acousticness": 0.1,
        "dissonance": 0.2,
        "spectral_centroid_mean": 3_200.0,
        "spectral_bandwidth_mean": 1_800.0,
        "spectral_rolloff_mean": 8_000.0,
        "spectral_flatness_mean": 0.15,
        "zero_crossing_rate": 0.08,
        "rms_mean": 0.12,
        "rms_max": 0.45,
        "loudness_lufs": -9.5,
        "dynamic_range_db": 6.0,
        "true_peak_db": -0.3,
        "replaygain_db": -1.2,
        "loudness_momentary_max_db": -6.0,
        "loudness_range_lu": 4.5,
        "duration_sec": 180.0,
        "intro_end_sec": 16.0,
        "outro_start_sec": 160.0,
        "leading_silence_sec": 0.05,
        "trailing_silence_sec": 0.1,
        "energy_curve": np.asarray([0.2, 0.5, 0.8], dtype=np.float32),
        "energy_curve_hop_sec": 0.5,
        "vocalness": 0.3,
        "mood_happy": 0.6,
        "mood_aggressive": 0.4,
        "mood_relaxed": 0.35,
        "mood_sad": 0.2,
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
        "embedding_version": 2,
        "fingerprint": fingerprint,
        "fingerprint_version": 1,
        "provenance": {
            "schema_version": SONARA_EXPECTED_SCHEMA_VERSION,
            "sample_rate": 22_050,
            "hop_length": 512,
            "mode": "playlist",
            "requested_features": list(
                sonara_requested_features(runtime=contracts.runtime)
            ),
            "vocalness_model_id": "sonara-vocalness-v2",
        },
    }


def _prepare(
    analysis: dict[str, object],
    *,
    contracts: SonaraContractSet,
    outputs: tuple[str, ...] = _ALL_OUTPUTS,
):
    return prepare_sonara_write(
        _candidate(contracts),
        analysis,
        contracts=contracts,
        outputs=outputs,
        analyzed_at="2026-07-23T12:00:00.000000Z",
    )


def test_complete_analyzer_result_becomes_one_typed_sonara_write() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)

    write = _prepare(analysis, contracts=contracts)

    assert write.target.track_id == 7
    assert write.target.content_generation == 3
    assert write.core.contract_hash == contracts.core.contract_hash
    assert write.core.detected_bpm == 128.0
    assert write.core.beat_count == 3
    assert json.loads(write.core.bpm_candidates_json or "null") == [
        {"rank": 1, "bpm": 128.0, "score": 0.95}
    ]
    assert json.loads(write.core.key_candidates_json or "null") == [
        {
            "rank": 1,
            "key_name": "A minor",
            "camelot": "8A",
            "score": 0.87,
        }
    ]
    np.testing.assert_array_equal(
        np.frombuffer(write.core.mfcc_mean_blob, dtype="<f4"),
        np.arange(13, dtype=np.float32),
    )
    assert write.core.energy_curve_sample_count == 3
    assert write.core.energy_curve_min == pytest.approx(0.2)
    assert write.core.energy_curve_max == pytest.approx(0.8)
    assert write.core.energy_curve_mean == pytest.approx(0.5)

    assert write.timeline is not None
    assert write.timeline.payload["beats"] == [0, 22, 43]
    assert "value" not in write.timeline.payload

    assert write.similarity_embedding is not None
    assert write.similarity_embedding.contract.normalization == "none"
    expected_embedding = np.asarray(analysis["embedding"], dtype="<f4")
    np.testing.assert_array_equal(
        write.similarity_embedding.vector,
        expected_embedding,
    )
    assert float(np.linalg.norm(write.similarity_embedding.vector)) != pytest.approx(
        1.0
    )

    assert write.fingerprint is not None
    assert write.fingerprint.fingerprint_version == "1"
    assert write.fingerprint.words.tolist() == [0, 123, 4_294_967_295]
    assert write.fingerprint.fingerprint_blob == struct.pack(
        "<3I",
        0,
        123,
        4_294_967_295,
    )


def test_core_only_does_not_emit_artifact_outputs() -> None:
    contracts = _contracts()
    outputs = ("core",)
    analysis = _analysis(contracts)

    write = _prepare(analysis, contracts=contracts, outputs=outputs)

    assert write.timeline is None
    assert write.similarity_embedding is None
    assert write.fingerprint is None
    assert write.outputs == (AnalysisOutput(contracts.core),)


def test_declared_clamp_fields_match_converter_implementation() -> None:
    assert _IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS == frozenset(
        SONARA_UNIT_INTERVAL_CLAMP_FIELDS
    )


@pytest.mark.parametrize(
    ("analyzer_field", "core_field"),
    [
        ("acousticness", "acousticness_score"),
        ("bpm_confidence", "bpm_confidence"),
        ("danceability", "danceability_score"),
        ("dissonance", "dissonance_score"),
        ("energy", "energy_score"),
        ("grid_stability", "beat_grid_stability"),
        ("key_confidence", "key_confidence"),
        ("mood_aggressive", "mood_aggressive_score"),
        ("mood_happy", "mood_happy_score"),
        ("mood_relaxed", "mood_relaxed_score"),
        ("mood_sad", "mood_sad_score"),
        ("spectral_flatness_mean", "spectral_flatness"),
        ("valence", "valence_score"),
        ("vocalness", "vocal_probability"),
        ("zero_crossing_rate", "zero_crossing_rate"),
    ],
)
def test_bounded_core_scalars_use_only_the_contract_epsilon_clamp(
    analyzer_field: str,
    core_field: str,
) -> None:
    contracts = _contracts()
    high = _analysis(contracts)
    high[analyzer_field] = 1.0005
    low = _analysis(contracts)
    low[analyzer_field] = -0.0005

    high_write = _prepare(high, contracts=contracts)
    low_write = _prepare(low, contracts=contracts)

    assert getattr(high_write.core, core_field) == 1.0
    assert getattr(low_write.core, core_field) == 0.0


@pytest.mark.parametrize(
    "scalar_factory",
    [
        pytest.param(float, id="python-float"),
        pytest.param(np.float32, id="float32"),
        pytest.param(np.float64, id="float64"),
        pytest.param(
            lambda value: float(np.float32(value)),
            id="pyo3-f32-as-python-float",
        ),
    ],
)
def test_exact_epsilon_boundaries_are_dtype_stable(
    scalar_factory,
) -> None:
    contracts = _contracts()
    high_value = scalar_factory(1.001)
    low_value = scalar_factory(-0.001)
    high = _analysis(contracts)
    high["energy"] = high_value
    high["energy_curve"] = [low_value, high_value]
    low = _analysis(contracts)
    low["energy"] = low_value

    high_write = _prepare(high, contracts=contracts)
    low_write = _prepare(low, contracts=contracts)

    assert high_write.core.energy_score == 1.0
    assert high_write.core.energy_curve_min == 0.0
    assert high_write.core.energy_curve_max == 1.0
    assert high_write.timeline is not None
    assert high_write.timeline.payload["energy_curve"] == [0.0, 1.0]
    assert low_write.core.energy_score == 0.0


@pytest.mark.parametrize(
    "scalar_factory",
    [
        pytest.param(float, id="python-float"),
        pytest.param(np.float32, id="float32"),
        pytest.param(np.float64, id="float64"),
        pytest.param(
            lambda value: float(np.float32(value)),
            id="pyo3-f32-as-python-float",
        ),
    ],
)
def test_next_representable_value_outside_epsilon_is_rejected(
    scalar_factory,
) -> None:
    contracts = _contracts()
    high_value = scalar_factory(np.nextafter(np.float32(1.001), np.float32(np.inf)))
    low_value = scalar_factory(np.nextafter(np.float32(-0.001), np.float32(-np.inf)))

    for value in (high_value, low_value):
        analysis = _analysis(contracts)
        analysis["energy"] = value
        with pytest.raises(ValueError, match="allowed epsilon"):
            _prepare(analysis, contracts=contracts)


def test_bounded_nested_values_use_the_same_epsilon_clamp() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis["energy_curve"] = [-0.0005, 0.5, 1.0005]
    analysis["key_candidates"] = [("A minor", "8A", 1.0005)]
    analysis["segments"] = [{"start_sec": 0.0, "end_sec": 16.0, "energy": 1.0005}]

    write = _prepare(analysis, contracts=contracts)

    assert write.core.energy_curve_min == 0.0
    assert write.core.energy_curve_max == 1.0
    assert json.loads(write.core.key_candidates_json or "null")[0]["score"] == 1.0
    assert write.timeline is not None
    assert write.timeline.payload["energy_curve"] == [0.0, 0.5, 1.0]
    assert write.timeline.payload["segments"][0]["energy"] == 1.0


def test_unbounded_bpm_candidate_and_db_fields_are_never_clamped() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis["bpm_candidates"] = [(128.0, 1.5)]
    analysis["true_peak_db"] = 1.0005

    write = _prepare(analysis, contracts=contracts)

    assert json.loads(write.core.bpm_candidates_json or "null")[0]["score"] == 1.5
    assert write.core.true_peak_dbtp == 1.0005


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("mfcc_mean", np.zeros(12), "exactly 13"),
        ("chroma_mean", np.zeros(11), "exactly 12"),
        ("spectral_contrast_mean", np.zeros(6), "exactly 7"),
        ("mfcc_mean", np.asarray([0.0] * 12 + [np.nan]), "non-finite"),
        ("embedding", np.zeros(47), "exactly 48"),
        ("embedding", np.asarray([0.0] * 47 + [np.inf]), "non-finite"),
    ],
)
def test_vector_shape_and_finiteness_are_strict(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis, contracts=contracts)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("bpm", 200.0, "at most 180"),
        ("bpm_confidence", 1.1, "allowed epsilon"),
        ("energy", -0.1, "allowed epsilon"),
        ("energy_level", 11, "at most 10"),
        ("duration_sec", float("nan"), "finite number"),
        ("bpm", "128.0", "finite number"),
        ("spectral_centroid_mean", -1.0, "at least 0.0"),
        ("vocalness", float("inf"), "finite number"),
        ("intro_end_sec", 181.0, "must not exceed duration"),
    ],
)
def test_scalar_ranges_and_units_are_strict(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis, contracts=contracts)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("schema_version", 3),
        ("sample_rate", 44_100),
        ("hop_length", 256),
        ("mode", "compact"),
        ("vocalness_model_id", "different-model"),
    ],
)
def test_provenance_must_match_active_runtime(
    field_name: str,
    bad_value: object,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    provenance = dict(analysis["provenance"])
    provenance[field_name] = bad_value
    analysis["provenance"] = provenance

    with pytest.raises(ValueError, match=field_name):
        _prepare(analysis, contracts=contracts)


def test_provenance_requires_an_object() -> None:
    contracts = _contracts()

    for malformed_provenance in (None, [], "not-an-object"):
        analysis = _analysis(contracts)
        analysis["provenance"] = malformed_provenance

        with pytest.raises(ValueError, match="provenance must be an object"):
            _prepare(analysis, contracts=contracts)


def test_provenance_package_version_is_optional_but_mismatch_is_rejected() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)

    assert _prepare(analysis, contracts=contracts).core.contract_hash == (
        contracts.core.contract_hash
    )

    provenance = dict(analysis["provenance"])
    provenance["package_version"] = f"{SONARA_EXPECTED_VERSION}+different-build"
    analysis["provenance"] = provenance
    with pytest.raises(ValueError, match="package_version"):
        _prepare(analysis, contracts=contracts)


def test_requested_features_requires_canonical_string_sequence() -> None:
    contracts = _contracts()
    expected = list(sonara_requested_features(runtime=contracts.runtime))
    malformed_values: tuple[object, ...] = (
        None,
        "bpm",
        [expected[0], 1],
        [expected[0], " "],
        list(reversed(expected)),
        [*expected, expected[0]],
    )

    for malformed_features in malformed_values:
        analysis = _analysis(contracts)
        provenance = dict(analysis["provenance"])
        if malformed_features is None:
            provenance.pop("requested_features")
        else:
            provenance["requested_features"] = malformed_features
        analysis["provenance"] = provenance

        with pytest.raises(ValueError, match="requested_features"):
            _prepare(analysis, contracts=contracts)


def test_core_only_persistence_requires_full_native_feature_provenance() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    provenance = dict(analysis["provenance"])
    provenance["requested_features"] = list(
        contracts.runtime.requested_features_by_output["core"]
    )
    analysis["provenance"] = provenance

    with pytest.raises(ValueError, match="requested_features"):
        _prepare(analysis, contracts=contracts, outputs=("core",))


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        (
            "bpm_candidates",
            [{"rank": 1, "bpm": 128.0, "score": 0.95}],
            "raw \\(bpm, score\\) pairs",
        ),
        (
            "bpm_candidates",
            [(128.0, 0.5), (127.0, 0.8)],
            "descending score",
        ),
        (
            "key_candidates",
            [{"key_name": "A minor", "camelot": "8A", "score": 0.87}],
            "raw \\(key_name, camelot, score\\) triples",
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
def test_candidate_lists_require_native_shape_and_canonical_consistency(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis, contracts=contracts)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("embedding_version", 3, "embedding_version"),
        ("fingerprint_version", 2, "fingerprint_version"),
        ("fingerprint", {"value": [1, 2, 3]}, "base64 string"),
        ("fingerprint", "not-base64", "strict base64"),
        (
            "fingerprint",
            base64.b64encode(b"\x00\x01").decode("ascii"),
            "complete uint32-le",
        ),
    ],
)
def test_optional_output_formats_have_no_legacy_compatibility(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis, contracts=contracts)


def test_timeline_payload_rejects_non_finite_nested_values() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis["segments"] = [{"start_sec": float("nan"), "end_sec": 1.0, "energy": 0.5}]

    with pytest.raises(ValueError, match="finite number"):
        _prepare(analysis, contracts=contracts)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("segments", None, "timeline output is incomplete"),
        (
            "beats",
            np.asarray([0.0, 22.0, 43.0], dtype=np.float32),
            "frame integer",
        ),
        (
            "downbeats",
            np.asarray([1], dtype=np.int64),
            "subset of timeline.beats",
        ),
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
        (
            "segments",
            [{"start_sec": 0.0, "end_sec": 16.0, "energy": 1.1}],
            "allowed epsilon",
        ),
    ],
)
def test_timeline_payload_requires_native_v029_shapes_and_units(
    field_name: str,
    bad_value: object,
    message: str,
) -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis[field_name] = bad_value

    with pytest.raises(ValueError, match=message):
        _prepare(analysis, contracts=contracts)


def test_declared_beat_count_must_match_actual_beats() -> None:
    contracts = _contracts()
    analysis = _analysis(contracts)
    analysis["n_beats"] = 99

    with pytest.raises(ValueError, match="n_beats"):
        _prepare(analysis, contracts=contracts)


def test_energy_curve_requires_positive_hop_and_unit_interval() -> None:
    contracts = _contracts()
    bad_hop = _analysis(contracts)
    bad_hop["energy_curve_hop_sec"] = 0.0
    bad_value = _analysis(contracts)
    bad_value["energy_curve"] = [0.2, 1.1]

    with pytest.raises(ValueError, match="greater than 0.0"):
        _prepare(bad_hop, contracts=contracts)
    with pytest.raises(ValueError, match="allowed epsilon"):
        _prepare(bad_value, contracts=contracts)

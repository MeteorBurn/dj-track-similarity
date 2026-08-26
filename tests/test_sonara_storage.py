from __future__ import annotations

import json
import base64
import uuid
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest

import dj_track_similarity.db_analysis as db_analysis
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_runtime import (
    DEFAULT_SONARA_BPM_MAX,
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
        "fingerprint": base64.b64encode(b"\x01\x00\x00\x00\x02\x00\x00\x00").decode("ascii"),
        "fingerprint_version": 7,
        "provenance": {
            "schema_version": 6,
            "bpm_min": 70.0,
            "bpm_max": 180.0,
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
    assert write.core.analysis_schema_version == 6
    assert write.core.bpm_min == 70.0
    assert write.core.bpm_max == 180.0
    assert write.embedding is not None
    assert write.embedding.family == "sonara"
    assert write.embedding.vector.dtype == np.dtype("<f4")
    assert write.embedding.vector.shape == (48,)
    assert np.array_equal(write.embedding.vector, analysis["embedding"])
    assert write.outputs == (
        AnalysisOutput("sonara", "core"),
        AnalysisOutput("sonara", "embedding"),
        AnalysisOutput("sonara", "fingerprint"),
    )
    assert write.fingerprint is not None
    assert write.fingerprint.value == "AQAAAAIAAAA="
    assert write.fingerprint.version == 7
    assert not hasattr(write, "timeline")
    assert not hasattr(write, "similarity_embedding")


def test_repository_saves_sonara_core_and_embedding_together(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    track_uuid = str(uuid.UUID(int=3))
    file_path = tmp_path / "track.wav"
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_uuid,
                    file_path.as_posix(),
                    123_456,
                    456_789,
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                ),
            ).lastrowid
        )
    candidate = AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid=database.catalog_uuid,
            track_id=track_id,
            track_uuid=track_uuid,
        ),
        file_path=file_path.as_posix(),
        file_size_bytes=123_456,
        file_modified_ns=456_789,
        missing_outputs=(
            AnalysisOutput("sonara", "core"),
            AnalysisOutput("sonara", "embedding"),
            AnalysisOutput("sonara", "fingerprint"),
        ),
    )
    write = prepare_sonara_write(
        candidate,
        _analysis(),
        analyzed_at="2026-07-23T12:00:00.000000Z",
    )

    result = database.save_sonara_results((write,))

    assert result[0].ok
    with closing(database.connect()) as connection:
        core = connection.execute(
            """
            SELECT analysis_schema_version, bpm_min, bpm_max
            FROM sonara_features
            WHERE track_id = ?
            """,
            (track_id,),
        ).fetchone()
        embedding = connection.execute(
            """
            SELECT track_uuid, dim, normalization, embedding_blob
            FROM sonara_embeddings
            WHERE track_id = ?
            """,
            (track_id,),
        ).fetchone()
        fingerprint = connection.execute(
            """
            SELECT track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
            FROM sonara_fingerprints
            WHERE track_id = ?
            """,
            (track_id,),
        ).fetchone()
    assert core is not None
    assert core["analysis_schema_version"] == 6
    assert core["bpm_min"] == 70.0
    assert core["bpm_max"] == 180.0
    assert embedding is not None
    assert embedding["track_uuid"] == track_uuid
    assert embedding["dim"] == 48
    assert embedding["normalization"] == "none"
    assert np.array_equal(
        np.frombuffer(embedding["embedding_blob"], dtype="<f4"),
        _analysis()["embedding"],
    )
    assert fingerprint is not None
    assert fingerprint["track_uuid"] == track_uuid
    assert fingerprint["fingerprint_version"] == 7
    assert fingerprint["fingerprint_base64"] == "AQAAAAIAAAA="
    assert fingerprint["analyzed_at"] == "2026-07-23T12:00:00.000000Z"
    detail = database.get_track_detail(track_id)
    assert detail.sonara_core is not None
    assert detail.sonara_core.analysis_schema_version == 6
    assert detail.sonara_core.bpm_min == 70.0
    assert detail.sonara_core.bpm_max == 180.0
    assert database.list_analysis_candidates(
        (AnalysisOutput("sonara", "fingerprint"),)
    ) == []
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "UPDATE sonara_fingerprints SET fingerprint_base64 = ? WHERE track_id = ?",
            ("invalid base64", track_id),
        )
    candidates = database.list_analysis_candidates(
        (AnalysisOutput("sonara", "fingerprint"),)
    )
    assert len(candidates) == 1
    assert candidates[0].target == candidate.target
    assert candidates[0].missing_outputs == (AnalysisOutput("sonara", "fingerprint"),)


def test_repository_rolls_back_core_when_embedding_write_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    track_uuid = str(uuid.UUID(int=4))
    file_path = tmp_path / "track.wav"
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_uuid,
                    file_path.as_posix(),
                    123_456,
                    456_789,
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                ),
            ).lastrowid
        )
    candidate = AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid=database.catalog_uuid,
            track_id=track_id,
            track_uuid=track_uuid,
        ),
        file_path=file_path.as_posix(),
        file_size_bytes=123_456,
        file_modified_ns=456_789,
        missing_outputs=(
            AnalysisOutput("sonara", "core"),
            AnalysisOutput("sonara", "embedding"),
        ),
    )
    write = prepare_sonara_write(
        candidate,
        _analysis(),
        analyzed_at="2026-07-23T12:00:00.000000Z",
    )

    def fail_embedding_write(**_kwargs: object) -> None:
        raise RuntimeError("forced embedding failure")

    monkeypatch.setattr(
        db_analysis,
        "write_valid_embedding_in_transaction",
        fail_embedding_write,
    )

    result = database.save_sonara_results((write,))

    assert not result[0].ok
    assert "forced embedding failure" in str(result[0].error)
    with closing(database.connect()) as connection:
        core_count = connection.execute(
            "SELECT COUNT(*) FROM sonara_features WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
        embedding_count = connection.execute(
            "SELECT COUNT(*) FROM sonara_embeddings WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
    assert core_count == 0
    assert embedding_count == 0


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
    assert write.outputs == (
        AnalysisOutput("sonara", "core"),
        AnalysisOutput("sonara", "embedding"),
        AnalysisOutput("sonara", "fingerprint"),
    )


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


def test_unknown_future_values_are_ignored() -> None:
    analysis = _analysis()
    analysis["future_output"] = object()
    analysis["segments"] = [{"energy": float("nan")}]

    write = _prepare(analysis)

    assert write.core.detected_bpm == 128.0


def test_embedding_rejects_non_finite_values_during_analysis_write() -> None:
    analysis = _analysis()
    analysis["embedding"] = np.full(48, np.nan, dtype=np.float32)

    with pytest.raises(ValueError, match="embedding contains non-finite values"):
        _prepare(analysis)


def test_track_and_generation_are_copied_from_candidate_not_analyzer_payload() -> None:
    analysis = _analysis()
    analysis["track_id"] = 999

    write = _prepare(analysis)

    assert write.target.track_id == 7
    assert write.core.track_id == 7


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        # Anchored to the configured ceiling, so changing the analysis range
        # does not turn this into a failing test.
        (
            "bpm",
            float(DEFAULT_SONARA_BPM_MAX) + 20.0,
            f"at most {float(DEFAULT_SONARA_BPM_MAX)}",
        ),
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


def test_library_range_is_derived_from_stored_rows_and_locks_analysis(
    tmp_path: Path,
) -> None:
    """The analysis range is a property of the data, chosen once and then fixed."""
    from dj_track_similarity.analysis_jobs import AnalysisJobManager

    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = AnalysisJobManager(database)

    # A library with no SONARA analysis is free to choose.
    assert database.sonara_analysis_ranges() == []
    summary = database.library_summary()
    assert summary.sonara_bpm_min is None
    assert summary.sonara_bpm_max is None

    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.UUID(int=11)),
                    (tmp_path / "track.wav").as_posix(),
                    1,
                    1,
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                ),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                bpm_min, bpm_max, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                bytes(13 * 4),
                bytes(12 * 4),
                bytes(7 * 4),
                6,
                79.0,
                192.0,
                "2026-07-23T12:00:00.000000Z",
            ),
        )

    # Once analysed, the library reports its range and holds every later run to it.
    assert database.sonara_analysis_ranges() == [(79.0, 192.0)]
    summary = database.library_summary()
    assert (summary.sonara_bpm_min, summary.sonara_bpm_max) == (79.0, 192.0)

    manager.create_job(models=["sonara"], sonara_bpm_min=79, sonara_bpm_max=192)
    manager.create_job(models=["sonara"])

    with pytest.raises(ValueError, match="Reset SONARA analysis"):
        manager.create_job(models=["sonara"], sonara_bpm_min=70, sonara_bpm_max=180)


def test_reset_frees_the_library_to_take_a_new_range(tmp_path: Path) -> None:
    from dj_track_similarity.analysis_models import AnalysisOutput

    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.UUID(int=12)),
                    (tmp_path / "track.wav").as_posix(),
                    1,
                    1,
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                    "2026-07-23T12:00:00.000000Z",
                ),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                bpm_min, bpm_max, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                bytes(13 * 4),
                bytes(12 * 4),
                bytes(7 * 4),
                6,
                79.0,
                192.0,
                "2026-07-23T12:00:00.000000Z",
            ),
        )
    assert database.sonara_analysis_ranges() == [(79.0, 192.0)]

    database.reset_analysis_outputs((AnalysisOutput("sonara", "core"),))

    assert database.sonara_analysis_ranges() == []

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pytest

import dj_track_similarity.hybrid_search as hybrid_search
from dj_track_similarity.analysis_contracts import FLOAT32_LE_ENCODING
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from dj_track_similarity.hybrid_explanation import MATCH_CHARACTER_AXES
from dj_track_similarity.hybrid_search import build_hybrid_search_preview
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    TrackDetail,
    TrackSummary,
)
from dj_track_similarity.sonara_contract import (
    SONARA_CORE_REQUESTED_FEATURES,
    SONARA_EMBEDDING_REQUESTED_FEATURES,
    SONARA_FINGERPRINT_REQUESTED_FEATURES,
    SONARA_PROJECT_FEATURE_REVISION,
    SONARA_TIMELINE_REQUESTED_FEATURES,
    SonaraContractSet,
    SonaraRuntimeIdentity,
    build_sonara_contracts,
)
from dj_track_similarity.track_models import TrackIdentity


_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"
_RISK_BREAKDOWN_KEYS = {
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


def _sonara_contracts() -> SonaraContractSet:
    return build_sonara_contracts(
        SonaraRuntimeIdentity(
            package_version="0.2.9",
            package_build_id="sha256:" + "5" * 64,
            schema_version=4,
            mode="playlist",
            sample_rate_hz=22_050,
            bpm_min=70,
            bpm_max=180,
            project_feature_revision=SONARA_PROJECT_FEATURE_REVISION,
            decoder_backend="sonara-symphonia",
            execution_path="analyze_batch",
            analysis_hop_samples=512,
            vocalness_model_id="sonara-vocalness",
            vocalness_model_build_id="sha256:" + "6" * 64,
            embedding_version=2,
            embedding_dim=48,
            embedding_normalization="none",
            embedding_encoding=FLOAT32_LE_ENCODING,
            fingerprint_version=1,
            fingerprint_encoding="uint32-le",
            fingerprint_byte_order="little",
            core_requested_features=SONARA_CORE_REQUESTED_FEATURES,
            timeline_requested_features=SONARA_TIMELINE_REQUESTED_FEATURES,
            embedding_requested_features=SONARA_EMBEDDING_REQUESTED_FEATURES,
            fingerprint_requested_features=SONARA_FINGERPRINT_REQUESTED_FEATURES,
        )
    )


def _identity(track_id: int) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=_CATALOG_UUID,
        track_id=track_id,
        track_uuid=f"00000000-0000-4000-8000-{track_id:012d}",
        content_generation=1,
    )


def _target(track_id: int) -> AnalysisTarget:
    identity = _identity(track_id)
    return AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )


def _summary(
    track_id: int,
    *,
    bpm: float = 124.0,
    musical_key: str = "8A",
    energy: float = 0.5,
) -> TrackSummary:
    identity = _identity(track_id)
    return TrackSummary(
        track_id=track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/track-{track_id}.wav",
        title=f"Track {track_id}",
        artist=f"Artist {track_id}",
        album="Fixture",
        tag_bpm=bpm,
        tag_key=musical_key,
        audio_duration_seconds=240.0,
        liked=False,
        analysis_coverage=AnalysisCoverage(
            sonara_core=True,
            maest_embedding=True,
            mert=True,
            clap=True,
        ),
        classifier_scores=(),
    )


def _sonara_row(
    output: AnalysisOutput,
    track_id: int,
    *,
    bpm: float,
    energy: float,
) -> SonaraFeatureRow:
    return SonaraFeatureRow(
        target=_target(track_id),
        output=output,
        values={
            "detected_bpm": bpm,
            "bpm_confidence": 0.95,
            "beat_grid_stability": 0.9,
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "onset_density_per_second": energy * 4.0,
            "energy_score": energy,
            "danceability_score": energy,
            "valence_score": energy,
            "acousticness_score": 1.0 - energy,
            "dissonance_score": 0.2,
            "chord_changes_per_second": 0.2,
            "rms_mean": energy,
            "rms_max": min(1.0, energy + 0.1),
            "integrated_loudness_lufs": -18.0 + energy * 8.0,
            "dynamic_range_db": 8.0,
            "spectral_centroid_hz": 1_000.0 + energy * 2_000.0,
            "spectral_bandwidth_hz": 1_000.0,
            "spectral_rolloff_hz": 3_000.0,
            "spectral_flatness": 0.1,
            "zero_crossing_rate": 0.08,
            "mfcc_mean_blob": tuple(energy for _ in range(13)),
            "chroma_mean_blob": tuple(energy for _ in range(12)),
            "spectral_contrast_mean_blob": tuple(energy for _ in range(7)),
            "analyzed_duration_seconds": 240.0,
            "intro_end_seconds": 16.0,
            "outro_start_seconds": 224.0,
            "energy_curve_mean": energy,
            "energy_curve_stddev": 0.1,
            "energy_curve_min": max(0.0, energy - 0.1),
            "energy_curve_max": min(1.0, energy + 0.1),
        },
    )


class _Repository:
    def __init__(self) -> None:
        contracts = _sonara_contracts()
        self.outputs = {
            ("sonara", "core"): AnalysisOutput(contracts.core),
            **{
                (family, "embedding"): current_embedding_analysis_output(family)
                for family in ("mert", "maest", "clap")
            },
        }
        self.summaries: dict[int, TrackSummary] = {}
        self.sonara_rows: dict[int, SonaraFeatureRow] = {}
        self.vectors: dict[str, dict[int, np.ndarray]] = {
            family: {} for family in ("mert", "maest", "clap")
        }
        self.session_requests: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []

    def add(
        self,
        track_id: int,
        *,
        mert: Sequence[float],
        maest: Sequence[float],
        clap: Sequence[float] | None = None,
        bpm: float = 124.0,
        energy: float = 0.5,
        musical_key: str = "8A",
    ) -> None:
        self.summaries[track_id] = _summary(
            track_id,
            bpm=bpm,
            musical_key=musical_key,
            energy=energy,
        )
        self.sonara_rows[track_id] = _sonara_row(
            self.outputs[("sonara", "core")],
            track_id,
            bpm=bpm,
            energy=energy,
        )
        vectors = {
            "mert": mert,
            "maest": maest,
            "clap": mert if clap is None else clap,
        }
        for family, values in vectors.items():
            compact = np.asarray(values, dtype=np.float32)
            dimension = int(self.outputs[(family, "embedding")].contract.dim)
            vector = np.zeros(dimension, dtype=np.float32)
            vector[: compact.size] = compact
            vector /= np.linalg.norm(vector)
            self.vectors[family][track_id] = vector

    def list_track_summaries(
        self, *, include_missing: bool = False
    ) -> tuple[TrackSummary, ...]:
        assert include_missing is False
        return tuple(self.summaries.values())

    def get_track_identities(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> dict[int, TrackIdentity]:
        assert include_missing is False
        return {
            track_id: _identity(track_id)
            for track_id in track_ids
            if track_id in self.summaries
        }

    def active_analysis_output(
        self, analysis_family: str, output_kind: str
    ) -> AnalysisOutput | None:
        return self.outputs.get((analysis_family, output_kind))

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        assert targets is None
        return tuple(
            AnalysisVectorRow(_target(track_id), output, vector)
            for track_id, vector in self.vectors[
                output.contract.analysis_family
            ].items()
        )

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        assert targets is None
        assert output == self.outputs[("sonara", "core")]
        return tuple(self.sonara_rows.values())

    def get_track_detail(
        self, track_id: int, *, include_missing: bool = False
    ) -> TrackDetail:
        raise AssertionError("classifier detail is not needed by these tests")

    def get_pair_feedback_map(
        self,
    ) -> Mapping[tuple[int, int, str], Mapping[str, object]]:
        return {}

    def create_search_session(
        self,
        mode: str,
        seed_track_ids: Sequence[int],
        request: Mapping[str, object],
    ) -> int:
        self.session_requests.append(
            {
                "mode": mode,
                "seed_track_ids": tuple(seed_track_ids),
                **dict(request),
            }
        )
        return 41

    def record_search_result_event(
        self,
        session_id: int,
        candidate_track_id: int,
        *,
        rank: int,
        total_score: float,
        score_breakdown: Mapping[str, object],
    ) -> None:
        self.events.append(
            {
                "session_id": session_id,
                "candidate_track_id": candidate_track_id,
                "rank": rank,
                "total_score": total_score,
                "score_breakdown": dict(score_breakdown),
            }
        )


def _analysis_outputs(repository: _Repository) -> dict[str, AnalysisOutput]:
    return {
        family: repository.outputs[(family, "embedding")]
        for family in ("mert", "maest", "clap")
    }


def _hybrid_library() -> _Repository:
    repository = _Repository()
    repository.add(1, mert=[1.0, 0.0], maest=[0.0, 1.0])
    repository.add(2, mert=[0.99, 0.01], maest=[1.0, 0.0])
    repository.add(3, mert=[0.0, 1.0], maest=[0.01, 0.99])
    repository.add(4, mert=[0.8, 0.2], maest=[0.2, 0.8])
    return repository


def _build(
    repository: _Repository,
    **kwargs: object,
):
    return build_hybrid_search_preview(
        repository,
        analysis_outputs=_analysis_outputs(repository),
        **kwargs,
    )


def test_hybrid_search_uses_equal_weights_and_typed_contracts() -> None:
    repository = _hybrid_library()

    result = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert", "maest"],
        per_source=3,
        limit=3,
    )

    assert result.weights_used == {"mert": 0.5, "maest": 0.5}
    assert result.sources == ("mert", "maest")
    assert result.source_contract_hashes == {
        family: repository.outputs[(family, "embedding")].contract_hash
        for family in ("mert", "maest")
    }
    assert len(result.results) == 3
    assert all(row.track.track_id != 1 for row in result.results)
    assert tuple(result.results[0].match_character) == MATCH_CHARACTER_AXES
    assert set(result.results[0].risk_breakdown) == _RISK_BREAKDOWN_KEYS


def test_hybrid_custom_weights_change_rrf_order() -> None:
    repository = _hybrid_library()

    mert = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert", "maest"],
        weights={"mert": 1.0, "maest": 0.0},
        per_source=3,
        limit=3,
    )
    maest = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert", "maest"],
        weights={"mert": 0.0, "maest": 1.0},
        per_source=3,
        limit=3,
    )

    assert mert.results[0].track.track_id == 2
    assert maest.results[0].track.track_id == 3


def test_hybrid_zero_weight_source_does_not_change_transition_adjusted_scores() -> None:
    repository = _Repository()
    for track_id, mert, maest in (
        (1, [1.0, 0.0], [1.0, 0.0]),
        (2, [0.98, 0.02], [0.99, 0.01]),
        (3, [0.99, 0.01], [0.0, 1.0]),
        (4, [0.0, 1.0], [0.98, 0.02]),
    ):
        repository.add(
            track_id,
            mert=mert,
            maest=maest,
            bpm=124.0,
            energy=0.5,
            musical_key="8A",
        )
    mert_only = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        weights={"mert": 1.0},
        per_source=2,
        limit=2,
        transition_risk_weight=1.0,
    )
    zero_weight_maest = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert", "maest"],
        weights={"mert": 1.0, "maest": 0.0},
        per_source=2,
        limit=2,
        transition_risk_weight=1.0,
    )

    assert [row.track.track_id for row in mert_only.results] == [3, 2]
    assert [row.track.track_id for row in zero_weight_maest.results] == [3, 2]
    for baseline, with_zero_weight_source in zip(
        mert_only.results,
        zero_weight_maest.results,
        strict=True,
    ):
        assert with_zero_weight_source.raw_rrf_score == pytest.approx(
            baseline.raw_rrf_score
        )
        assert with_zero_weight_source.transition_risk == pytest.approx(
            baseline.transition_risk
        )
        assert with_zero_weight_source.adjusted_score == pytest.approx(
            baseline.adjusted_score
        )
        assert (
            with_zero_weight_source.transition_diagnostics["components"][
                "source_disagreement_risk"
            ]
            == 0.0
        )


def test_hybrid_rejects_wrong_embedding_dimension_before_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _hybrid_library()
    repository.vectors["mert"][1] = np.asarray([1.0, 0.0], dtype=np.float32)
    monkeypatch.setattr(
        hybrid_search,
        "_rank_embedding_source",
        lambda *_args, **_kwargs: pytest.fail("scoring must not run"),
    )

    with pytest.raises(RuntimeError, match="dimension"):
        _build(
            repository,
            seed_track_ids=[1],
            sources=["mert"],
            weights={"mert": 1.0},
        )


def test_hybrid_rejects_non_unit_l2_embedding_before_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _hybrid_library()
    repository.vectors["mert"][1] *= 2.0
    monkeypatch.setattr(
        hybrid_search,
        "_rank_embedding_source",
        lambda *_args, **_kwargs: pytest.fail("scoring must not run"),
    )

    with pytest.raises(RuntimeError, match="not unit-normalized"):
        _build(
            repository,
            seed_track_ids=[1],
            sources=["mert"],
            weights={"mert": 1.0},
        )


def test_hybrid_rejects_duplicate_embedding_target_before_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _hybrid_library()
    load_vectors = repository.load_analysis_vectors

    def duplicate_first_row(
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        rows = load_vectors(output, targets=targets)
        return (*rows, rows[0])

    monkeypatch.setattr(repository, "load_analysis_vectors", duplicate_first_row)
    monkeypatch.setattr(
        hybrid_search,
        "_rank_embedding_source",
        lambda *_args, **_kwargs: pytest.fail("scoring must not run"),
    )

    with pytest.raises(RuntimeError, match="duplicate embedding rows"):
        _build(
            repository,
            seed_track_ids=[1],
            sources=["mert"],
            weights={"mert": 1.0},
        )


def test_hybrid_transition_risk_can_demote_a_risky_rrf_winner() -> None:
    repository = _Repository()
    repository.add(
        1,
        mert=[1.0, 0.0],
        maest=[1.0, 0.0],
        bpm=120.0,
        energy=0.5,
    )
    repository.add(
        2,
        mert=[0.99, 0.01],
        maest=[0.99, 0.01],
        bpm=200.0,
        energy=1.0,
        musical_key="8B",
    )
    repository.add(
        3,
        mert=[0.98, 0.02],
        maest=[0.98, 0.02],
        bpm=120.0,
        energy=0.5,
    )

    raw = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        weights={"mert": 1.0},
        rrf_k=1,
        transition_risk_weight=0.0,
        limit=2,
    )
    adjusted = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        weights={"mert": 1.0},
        rrf_k=1,
        transition_risk_weight=1.0,
        limit=2,
    )

    assert [row.track.track_id for row in raw.results] == [2, 3]
    raw_by_id = {row.track.track_id: row for row in raw.results}
    adjusted_by_id = {row.track.track_id: row for row in adjusted.results}
    assert (
        adjusted_by_id[2].transition_risk_penalty
        > adjusted_by_id[3].transition_risk_penalty
    )
    assert adjusted_by_id[2].adjusted_score < raw_by_id[2].adjusted_score


def test_hybrid_tie_break_is_deterministic_for_random_seed() -> None:
    repository = _Repository()
    repository.add(1, mert=[1.0, 0.0], maest=[1.0, 0.0])
    repository.add(2, mert=[0.8, 0.2], maest=[0.8, 0.2])
    repository.add(3, mert=[0.8, 0.2], maest=[0.8, 0.2])

    first = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        weights={"mert": 1.0},
        random_seed=17,
        limit=2,
    )
    second = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        weights={"mert": 1.0},
        random_seed=17,
        limit=2,
    )

    assert [row.track.track_id for row in first.results] == [
        row.track.track_id for row in second.results
    ]


@pytest.mark.parametrize(
    "weights",
    (
        {"mert": -0.1},
        {"mert": float("nan")},
        {"mert": 0.0, "maest": 0.0},
        {"unknown": 1.0},
    ),
)
def test_hybrid_search_rejects_invalid_weights(
    weights: dict[str, float],
) -> None:
    repository = _hybrid_library()

    with pytest.raises(ValueError):
        _build(
            repository,
            seed_track_ids=[1],
            sources=["mert", "maest"],
            weights=weights,
        )


def test_hybrid_search_reports_missing_source_coverage() -> None:
    repository = _Repository()
    repository.add(1, mert=[1.0, 0.0], maest=[1.0, 0.0])
    del repository.vectors["clap"][1]

    result = _build(
        repository,
        seed_track_ids=[1],
        sources=["clap"],
        weights={"clap": 1.0},
        limit=3,
    )

    assert result.results == ()
    assert any("returned no current candidates" in warning for warning in result.warnings)


def test_hybrid_search_records_only_when_requested() -> None:
    repository = _hybrid_library()

    dry_run = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        limit=1,
        record_session=False,
    )
    recorded = _build(
        repository,
        seed_track_ids=[1],
        sources=["mert"],
        limit=1,
        record_session=True,
    )

    assert dry_run.session_id is None
    assert recorded.session_id == 41
    assert len(repository.session_requests) == 1
    assert repository.events
    assert repository.session_requests[0]["source_contract_hashes"] == {
        "mert": repository.outputs[("mert", "embedding")].contract_hash
    }

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

import numpy as np
import pytest

from dj_track_similarity.analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from dj_track_similarity.hybrid_search import build_hybrid_search_preview
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    LibrarySummary,
    TrackDetail,
    TrackSummary,
)
from dj_track_similarity.set_builder import (
    SetBuilderConfig,
    SmartSetBuilder,
)
from dj_track_similarity.sonara_contract import SONARA_EXPECTED_VERSION
from dj_track_similarity.track_models import TrackIdentity


_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


def _embedding_output(family: str) -> AnalysisOutput:
    return AnalysisOutput(
        ContractIdentity(
            analysis_family=family,
            output_kind="embedding",
            model_name=f"{family}-fixture",
            model_version="1",
            dim=2,
            encoding=FLOAT32_LE_ENCODING,
            normalization="l2",
            checkpoint_id="sha256:" + family[0] * 64,
            preprocessing="fixture-v1",
            parameters={"fixture": True},
        )
    )


def _sonara_output() -> AnalysisOutput:
    return AnalysisOutput(
        ContractIdentity(
            analysis_family="sonara",
            output_kind="core",
            model_name="sonara-playlist",
            model_version=SONARA_EXPECTED_VERSION,
            release_hash="sha256:" + "7" * 64,
            checkpoint_id="sha256:" + "8" * 64,
            preprocessing="fixture-v1",
            parameters={"fixture": True},
        )
    )


def _identity(track_id: int) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=_CATALOG_UUID,
        track_id=track_id,
        track_uuid=f"00000000-0000-4000-8000-{track_id:012d}",
        content_generation=1,
    )


def _target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
    )


def _summary(track_id: int, *, bpm: float) -> TrackSummary:
    identity = _identity(track_id)
    return TrackSummary(
        track_id=identity.track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/track-{track_id}.wav",
        title=f"Track {track_id}",
        artist=f"Artist {track_id}",
        album="Fixture",
        tag_bpm=bpm,
        tag_key="8A",
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
    danceability: float,
) -> SonaraFeatureRow:
    identity = _identity(track_id)
    return SonaraFeatureRow(
        target=_target(identity),
        output=output,
        values={
            "detected_bpm": bpm,
            "bpm_confidence": 0.95,
            "beat_grid_stability": 0.9,
            "bpm_candidates_json": f"[[{bpm}, 1.0]]",
            "detected_key_name": "A minor",
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "predominant_chord": "Am",
            "onset_density_per_second": danceability * 4.0,
            "energy_score": energy,
            "energy_level": round(energy * 10),
            "danceability_score": danceability,
            "valence_score": energy,
            "acousticness_score": 1.0 - energy,
            "dissonance_score": 0.2,
            "chord_changes_per_second": danceability,
            "rms_mean": energy,
            "rms_max": min(1.0, energy + 0.1),
            "integrated_loudness_lufs": -18.0 + energy * 8.0,
            "dynamic_range_db": 8.0,
            "spectral_centroid_hz": 1_000.0 + energy * 2_000.0,
            "spectral_bandwidth_hz": 800.0 + energy * 1_000.0,
            "spectral_rolloff_hz": 2_000.0 + energy * 3_000.0,
            "spectral_flatness": 0.1 + energy * 0.2,
            "zero_crossing_rate": 0.05 + energy * 0.1,
            "mfcc_mean_blob": tuple(energy for _ in range(13)),
            "chroma_mean_blob": tuple(energy for _ in range(12)),
            "spectral_contrast_mean_blob": tuple(danceability for _ in range(7)),
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
        self.summaries = (
            _summary(1, bpm=128.0),
            _summary(2, bpm=127.0),
            _summary(3, bpm=90.0),
        )
        self.identities = {
            summary.track_id: _identity(summary.track_id) for summary in self.summaries
        }
        self.outputs = {
            ("sonara", "core"): _sonara_output(),
            ("mert", "embedding"): _embedding_output("mert"),
            ("maest", "embedding"): _embedding_output("maest"),
            ("clap", "embedding"): _embedding_output("clap"),
        }
        self.sonara_rows = (
            _sonara_row(
                self.outputs[("sonara", "core")],
                1,
                bpm=128.0,
                energy=0.8,
                danceability=0.9,
            ),
            _sonara_row(
                self.outputs[("sonara", "core")],
                2,
                bpm=127.0,
                energy=0.75,
                danceability=0.85,
            ),
            _sonara_row(
                self.outputs[("sonara", "core")],
                3,
                bpm=90.0,
                energy=0.1,
                danceability=0.2,
            ),
        )
        self.vectors = {
            "mert": {
                1: np.asarray([1.0, 0.0], dtype=np.float32),
                2: np.asarray([0.8, 0.6], dtype=np.float32),
                3: np.asarray([0.0, 1.0], dtype=np.float32),
            },
            "maest": {
                1: np.asarray([1.0, 0.0], dtype=np.float32),
                2: np.asarray([0.9, 0.4358899], dtype=np.float32),
                3: np.asarray([0.0, 1.0], dtype=np.float32),
            },
            "clap": {
                1: np.asarray([1.0, 0.0], dtype=np.float32),
                2: np.asarray([0.95, 0.3122499], dtype=np.float32),
                3: np.asarray([0.0, 1.0], dtype=np.float32),
            },
        }
        self.stale_vector_track_id: int | None = None
        self.duplicate_vector_track_id: int | None = None
        self.active_output_calls: list[tuple[str, str]] = []
        self.session_requests: list[dict[str, object]] = []
        self.recorded_events: list[dict[str, object]] = []

    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        assert include_missing is False
        return self.summaries

    def library_summary(self) -> LibrarySummary:
        count = len(self.summaries)
        return LibrarySummary(
            tracks=count,
            sonara=count,
            maest_analysis=0,
            maest_embedding=count,
            mert=count,
            muq=0,
            clap=count,
            liked=0,
            classifiers=0,
        )

    def get_track_identities(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> dict[int, TrackIdentity]:
        assert include_missing is False
        return {
            track_id: self.identities[track_id]
            for track_id in track_ids
            if track_id in self.identities
        }

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        key = (analysis_family, output_kind)
        self.active_output_calls.append(key)
        return self.outputs.get(key)

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        assert targets is None
        family = output.contract.analysis_family
        rows: list[AnalysisVectorRow] = []
        for track_id, vector in self.vectors[family].items():
            target = _target(self.identities[track_id])
            if track_id == self.stale_vector_track_id:
                target = replace(
                    target,
                    content_generation=target.content_generation + 1,
                )
            rows.append(
                AnalysisVectorRow(
                    target=target,
                    output=output,
                    vector=vector,
                )
            )
        if self.duplicate_vector_track_id is not None:
            track_id = self.duplicate_vector_track_id
            rows.append(
                AnalysisVectorRow(
                    target=_target(self.identities[track_id]),
                    output=output,
                    vector=self.vectors[family][track_id],
                )
            )
        return tuple(rows)

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        assert targets is None
        assert output == self.outputs[("sonara", "core")]
        return self.sonara_rows

    def get_track_detail(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackDetail:
        raise AssertionError("track detail is not needed without classifier controls")

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
        self.recorded_events.append(
            {
                "session_id": session_id,
                "candidate_track_id": candidate_track_id,
                "rank": rank,
                "total_score": total_score,
                "score_breakdown": dict(score_breakdown),
            }
        )


def _analysis_outputs(
    repository: _Repository,
) -> dict[str, AnalysisOutput]:
    return {
        family: repository.outputs[(family, "embedding")]
        for family in ("mert", "maest", "clap")
    }


def _run_vector_consumer(repository: _Repository, consumer: str) -> None:
    if consumer == "set":
        SmartSetBuilder(
            repository,
            analysis_outputs=_analysis_outputs(repository),
        ).generate(
            SetBuilderConfig(
                seed_mode="manual",
                seed_track_ids=[1],
                limit=2,
                random_seed=0,
            )
        )
        return
    if consumer == "hybrid":
        build_hybrid_search_preview(
            repository,
            seed_track_ids=(1,),
            analysis_outputs=_analysis_outputs(repository),
            sources=("mert",),
            weights={"mert": 1.0},
            limit=2,
        )
        return
    raise AssertionError(f"unknown vector consumer: {consumer}")


@pytest.mark.parametrize("consumer", ("set", "hybrid"))
def test_vector_consumers_reject_wrong_embedding_dimension(
    consumer: str,
) -> None:
    repository = _Repository()
    repository.vectors["mert"][1] = np.asarray(
        [1.0, 0.0, 0.0],
        dtype=np.float32,
    )

    with pytest.raises(RuntimeError, match="dimension.*active contract"):
        _run_vector_consumer(repository, consumer)


@pytest.mark.parametrize("consumer", ("set", "hybrid"))
def test_vector_consumers_reject_non_unit_l2_embedding(
    consumer: str,
) -> None:
    repository = _Repository()
    repository.vectors["mert"][1] = np.asarray(
        [2.0, 0.0],
        dtype=np.float32,
    )

    with pytest.raises(RuntimeError, match="not unit-normalized"):
        _run_vector_consumer(repository, consumer)


@pytest.mark.parametrize("consumer", ("set", "hybrid"))
def test_vector_consumers_reject_duplicate_track_rows(
    consumer: str,
) -> None:
    repository = _Repository()
    repository.duplicate_vector_track_id = 1

    with pytest.raises(RuntimeError, match="duplicate embedding rows"):
        _run_vector_consumer(repository, consumer)


def test_set_builder_uses_current_repository_rows_and_typed_sonara() -> None:
    repository = _Repository()

    result = SmartSetBuilder(
        repository,
        analysis_outputs=_analysis_outputs(repository),
    ).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            mode="balanced_set",
            limit=2,
            random_seed=0,
        )
    )

    assert result["seed_track_ids"] == [1]
    assert [item["track"]["track_id"] for item in result["items"]] == [1, 2]
    assert ("sonara", "embedding") not in repository.active_output_calls
    assert repository.active_output_calls == [
        ("sonara", "core"),
        ("mert", "embedding"),
        ("maest", "embedding"),
        ("clap", "embedding"),
    ]


def test_set_builder_rejects_stale_analysis_generation() -> None:
    repository = _Repository()
    repository.stale_vector_track_id = 2

    with pytest.raises(
        RuntimeError,
        match="analysis target does not match the current track identity",
    ):
        SmartSetBuilder(
            repository,
            analysis_outputs=_analysis_outputs(repository),
        ).generate(
            SetBuilderConfig(
                seed_mode="manual",
                seed_track_ids=[1],
                limit=2,
                random_seed=0,
            )
        )


def test_set_builder_rejects_non_active_sonara_contract() -> None:
    repository = _Repository()
    inactive_output = AnalysisOutput(
        replace(
            repository.outputs[("sonara", "core")].contract,
            release_hash="sha256:" + "9" * 64,
        )
    )
    repository.sonara_rows = (
        replace(repository.sonara_rows[0], output=inactive_output),
        *repository.sonara_rows[1:],
    )

    with pytest.raises(
        RuntimeError,
        match="SONARA data for the wrong contract",
    ):
        SmartSetBuilder(
            repository,
            analysis_outputs=_analysis_outputs(repository),
        ).generate(
            SetBuilderConfig(
                seed_mode="manual",
                seed_track_ids=[1],
                limit=2,
                random_seed=0,
            )
        )


def test_set_builder_rejects_current_adapter_contract_drift() -> None:
    repository = _Repository()
    expected = _analysis_outputs(repository)
    expected["mert"] = AnalysisOutput(
        replace(
            expected["mert"].contract,
            model_version="runtime-drift",
        )
    )

    with pytest.raises(RuntimeError, match="reanalysis is required"):
        SmartSetBuilder(
            repository,
            analysis_outputs=expected,
        ).generate(
            SetBuilderConfig(
                seed_mode="manual",
                seed_track_ids=[1],
                limit=2,
            )
        )


def test_hybrid_records_exact_source_contract_hashes() -> None:
    repository = _Repository()

    result = build_hybrid_search_preview(
        repository,
        seed_track_ids=(1,),
        analysis_outputs=_analysis_outputs(repository),
        sources=("mert", "sonara"),
        weights={"mert": 0.6, "sonara": 0.4},
        per_source=3,
        limit=2,
        random_seed=17,
        record_session=True,
    )

    expected_contracts = {
        "mert": repository.outputs[("mert", "embedding")].contract_hash,
        "sonara": repository.outputs[("sonara", "core")].contract_hash,
    }
    assert [row.track.track_id for row in result.results] == [2, 3]
    assert result.source_contract_hashes == expected_contracts
    assert repository.session_requests[0]["source_contract_hashes"] == (
        expected_contracts
    )
    assert repository.recorded_events
    assert all(
        event["score_breakdown"]["source_contract_hashes"] == expected_contracts
        for event in repository.recorded_events
    )
    assert ("sonara", "embedding") not in repository.active_output_calls


def test_hybrid_rejects_current_adapter_contract_drift() -> None:
    repository = _Repository()
    expected = _analysis_outputs(repository)
    expected["mert"] = AnalysisOutput(
        replace(
            expected["mert"].contract,
            model_version="runtime-drift",
        )
    )

    with pytest.raises(RuntimeError, match="reanalysis is required"):
        build_hybrid_search_preview(
            repository,
            seed_track_ids=(1,),
            analysis_outputs=expected,
            sources=("mert",),
            weights={"mert": 1.0},
            limit=2,
        )


def test_hybrid_rejects_stale_analysis_generation() -> None:
    repository = _Repository()
    repository.stale_vector_track_id = 2

    with pytest.raises(
        RuntimeError,
        match="analysis row identity does not match the current track",
    ):
        build_hybrid_search_preview(
            repository,
            seed_track_ids=(1,),
            analysis_outputs=_analysis_outputs(repository),
            sources=("mert",),
            weights={"mert": 1.0},
            limit=2,
        )

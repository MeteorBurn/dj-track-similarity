from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

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
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    LibrarySummary,
    TrackSummary,
)
from dj_track_similarity.set_builder import SetBuilderConfig, SmartSetBuilder
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
    bpm: float,
    artist: str | None = None,
) -> TrackSummary:
    identity = _identity(track_id)
    return TrackSummary(
        track_id=track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/track-{track_id}.wav",
        title=f"Track {track_id}",
        artist=artist or f"Artist {track_id}",
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
    return SonaraFeatureRow(
        target=_target(track_id),
        output=output,
        values={
            "detected_bpm": bpm,
            "bpm_confidence": 0.95,
            "beat_grid_stability": 0.9,
            "bpm_candidates_json": f"[[{bpm},1.0]]",
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
            "spectral_contrast_mean_blob": tuple(
                danceability for _ in range(7)
            ),
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

    def add(
        self,
        track_id: int,
        *,
        bpm: float = 128.0,
        energy: float = 0.5,
        danceability: float = 0.5,
        vector: Sequence[float] = (1.0, 0.0),
        artist: str | None = None,
        missing: Sequence[str] = (),
    ) -> None:
        self.summaries[track_id] = _summary(
            track_id,
            bpm=bpm,
            artist=artist,
        )
        if "sonara" not in missing:
            self.sonara_rows[track_id] = _sonara_row(
                self.outputs[("sonara", "core")],
                track_id,
                bpm=bpm,
                energy=energy,
                danceability=danceability,
            )
        for family in ("mert", "maest", "clap"):
            if family not in missing:
                output = self.outputs[(family, "embedding")]
                self.vectors[family][track_id] = _embedding_vector(
                    output,
                    vector,
                )

    def list_track_summaries(
        self, *, include_missing: bool = False
    ) -> tuple[TrackSummary, ...]:
        assert include_missing is False
        return tuple(self.summaries.values())

    def library_summary(self) -> LibrarySummary:
        return LibrarySummary(
            tracks=len(self.summaries),
            sonara=len(self.sonara_rows),
            maest_analysis=0,
            maest_embedding=len(self.vectors["maest"]),
            mert=len(self.vectors["mert"]),
            muq=0,
            clap=len(self.vectors["clap"]),
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


def _analysis_outputs(repository: _Repository) -> dict[str, AnalysisOutput]:
    return {
        family: repository.outputs[(family, "embedding")]
        for family in ("mert", "maest", "clap")
    }


def _embedding_vector(
    output: AnalysisOutput,
    values: Sequence[float],
) -> np.ndarray:
    vector = np.zeros(int(output.contract.dim), dtype=np.float32)
    source = np.asarray(values, dtype=np.float32)
    if source.ndim != 1 or source.size > vector.size:
        raise ValueError("fixture embedding values must fit the active contract")
    vector[: source.size] = source
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    if norm <= 0.0:
        raise ValueError("fixture embedding must have a non-zero norm")
    vector /= norm
    return vector


def _builder(repository: _Repository) -> SmartSetBuilder:
    return SmartSetBuilder(
        repository,
        analysis_outputs=_analysis_outputs(repository),
    )


def _track_ids(result: dict[str, object]) -> list[int]:
    items = result["items"]
    assert isinstance(items, list)
    return [int(item["track"]["track_id"]) for item in items]


def test_manual_set_builder_uses_typed_sonara_broad_score() -> None:
    repository = _Repository()
    repository.add(1, energy=0.8, danceability=0.8)
    repository.add(2, energy=0.79, danceability=0.79)
    repository.add(3, energy=0.1, danceability=0.1)

    result = _builder(repository).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            mode="similar_crate",
            limit=3,
            random_seed=0,
        )
    )

    assert _track_ids(result) == [1, 2, 3]
    assert result["items"][0]["reason"] == "seed_anchor"
    assert (
        result["items"][1]["score_breakdown"]["sonara_broad"]
        > result["items"][2]["score_breakdown"]["sonara_broad"]
    )


def test_same_random_seed_produces_same_auto_set() -> None:
    repository = _Repository()
    for track_id in range(1, 9):
        repository.add(
            track_id,
            energy=track_id / 10.0,
            danceability=(10 - track_id) / 10.0,
            vector=(1.0, track_id / 20.0),
        )
    config = SetBuilderConfig(
        seed_mode="auto",
        auto_seed_count=2,
        limit=6,
        mode="discovery",
        random_seed=37,
    )

    first = _builder(repository).generate(config)
    second = _builder(repository).generate(config)

    assert _track_ids(first) == _track_ids(second)
    assert first["seed_track_ids"] == second["seed_track_ids"]


def test_prefilter_bounds_candidates_before_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    for track_id in range(1, 1_007):
        repository.add(
            track_id,
            energy=(track_id % 100) / 100.0,
            danceability=(track_id % 80) / 80.0,
            vector=(1.0, (track_id % 50) / 100.0),
        )
    builder = _builder(repository)
    original = builder._hydrate_candidates
    hydrated_counts: list[int] = []

    def _record_hydration(candidates):
        hydrated_counts.append(len(candidates))
        return original(candidates)

    monkeypatch.setattr(builder, "_hydrate_candidates", _record_hydration)

    result = builder.generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            limit=2,
            random_seed=1,
        )
    )

    assert len(repository.summaries) == 1_006
    assert hydrated_counts == [1_001]
    assert _track_ids(result)[0] == 1


def test_low_to_high_bpm_mode_follows_preview_tempo_curve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    repository.add(1, bpm=100.0)
    repository.add(2, bpm=110.0)
    repository.add(3, bpm=120.0)
    repository.add(4, bpm=130.0)
    monkeypatch.setattr(
        "dj_track_similarity.set_builder._sample_ranked_index",
        lambda scores, rng, *, mode, force_sample: int(np.argmax(scores)),
    )

    result = _builder(repository).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            limit=4,
            bpm_mode="low_to_high",
            bpm_start=100.0,
            bpm_target=130.0,
            random_seed=2,
        )
    )

    assert _track_ids(result) == [1, 2, 3, 4]


def test_set_builder_excludes_tracks_missing_required_analysis() -> None:
    repository = _Repository()
    repository.add(1)
    repository.add(2)
    repository.add(3, missing=("clap",))

    result = _builder(repository).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            limit=3,
            random_seed=4,
        )
    )

    assert 3 not in _track_ids(result)
    assert result["coverage"]["eligible_tracks"] == 2
    assert result["coverage"]["missing_clap"] == 1


def test_set_builder_does_not_repeat_known_artist() -> None:
    repository = _Repository()
    repository.add(1, artist="Shared Artist")
    repository.add(2, artist="Shared Artist", vector=(0.99, 0.01))
    repository.add(3, artist="Other Artist", vector=(0.98, 0.02))

    result = _builder(repository).generate(
        SetBuilderConfig(
            seed_mode="manual",
            seed_track_ids=[1],
            limit=3,
            random_seed=0,
        )
    )

    assert _track_ids(result) == [1, 3]


@pytest.mark.parametrize("seed_track_ids", ([], [1, 2, 3, 4, 5, 6]))
def test_manual_mode_rejects_invalid_seed_counts(
    seed_track_ids: list[int],
) -> None:
    repository = _Repository()
    for track_id in range(1, 7):
        repository.add(track_id)

    with pytest.raises(ValueError, match="seed"):
        _builder(repository).generate(
            SetBuilderConfig(
                seed_mode="manual",
                seed_track_ids=seed_track_ids,
                limit=6,
            )
        )

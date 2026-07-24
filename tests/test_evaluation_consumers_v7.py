from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from dj_track_similarity.analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
)
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from dj_track_similarity.evaluation.candidates import export_candidate_pools
from dj_track_similarity.evaluation.recorded_sessions import (
    load_current_evaluation_sessions,
)
from dj_track_similarity.evaluation.seed_sampling import export_seed_sample
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.sonara_contract import SONARA_EXPECTED_VERSION
from dj_track_similarity.track_models import TrackIdentity


_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


def test_candidate_pool_uses_exact_v7_targets_and_contract_provenance() -> None:
    repository = _Repository()

    result = export_candidate_pools(
        repository,
        seed_track_ids=(1,),
        sources=("mert", "maest"),
        per_source=2,
        random_seed=19,
        record_session=True,
    )

    assert result.warnings == ()
    assert result.session_ids == (1,)
    assert {row.candidate_track_id for row in result.rows} == {2, 3}
    shared = next(row for row in result.rows if row.candidate_track_id == 2)
    assert {
        source: contribution.contract_hash
        for source, contribution in shared.source_contributions.items()
    } == {
        "maest": repository.outputs[("maest", "embedding")].contract_hash,
        "mert": repository.outputs[("mert", "embedding")].contract_hash,
    }
    assert shared.seed_track.identity == repository.identities[1]
    assert shared.candidate_track.identity == repository.identities[2]

    request = repository.created_sessions[0]["request"]
    assert request["catalog_uuid"] == repository.catalog_uuid
    assert request["seed_identities"] == [_identity_payload(repository.identities[1])]
    assert request["source_contract_hashes"] == {
        "maest": repository.outputs[("maest", "embedding")].contract_hash,
        "mert": repository.outputs[("mert", "embedding")].contract_hash,
    }
    assert all(
        event["score_breakdown"]["candidate_identity"]
        == _identity_payload(repository.identities[event["track_id"]])
        for event in repository.recorded_events
    )
    assert all(
        contribution["contract_hash"]
        for event in repository.recorded_events
        for contribution in event["score_breakdown"]["sources"].values()
    )


def test_candidate_pool_read_only_mode_does_not_open_evaluation_storage() -> None:
    repository = _Repository()

    result = export_candidate_pools(
        repository,
        seed_track_ids=(1,),
        sources=("mert",),
        per_source=1,
        random_seed=3,
        record_session=False,
    )

    assert len(result.rows) == 1
    assert result.session_ids == ()
    assert repository.created_sessions == []
    assert repository.recorded_events == []


def test_seed_sample_distinguishes_maest_analysis_and_embedding_coverage() -> None:
    repository = _Repository()
    repository.summaries[1] = _summary(
        repository.identities[1],
        coverage=AnalysisCoverage(
            sonara_core=True,
            mert=True,
            clap=True,
            maest_analysis=False,
            maest_embedding=True,
        ),
    )
    for track_id in (2, 3):
        repository.summaries[track_id] = _summary(
            repository.identities[track_id],
            coverage=AnalysisCoverage(sonara_core=True),
        )

    result = export_seed_sample(
        repository,
        count=1,
        require_complete_analysis=True,
    )

    assert result.eligible_count == 1
    row = result.rows[0]
    assert row.sonara_core
    assert row.mert_embedding
    assert row.clap_embedding
    assert not row.maest_analysis
    assert row.maest_embedding
    assert row.csv_row()["maest_analysis"] == 0
    assert row.csv_row()["maest_embedding"] == 1


def test_recorded_session_reader_requires_current_identity_and_contract() -> None:
    repository = _Repository()
    output = repository.outputs[("mert", "embedding")]
    seed = repository.identities[1]
    candidate = repository.identities[2]
    repository.raw_sessions = [
        {
            "id": 1,
            "mode": "evaluation_candidate_pool",
            "created_at": "2026-07-24T12:00:00Z",
            "request": {
                "catalog_uuid": repository.catalog_uuid,
                "seed_identities": [_identity_payload(seed)],
                "source_contract_hashes": {
                    "mert": output.contract_hash,
                },
            },
            "seeds": [
                {
                    "position": 0,
                    **_stored_identity_payload(seed),
                }
            ],
            "events": [
                {
                    "id": 1,
                    "rank": 1,
                    **_stored_identity_payload(candidate),
                    "score_breakdown": {
                        "candidate_identity": _identity_payload(candidate),
                        "sources": {
                            "mert": {
                                "rank": 1,
                                "score": 0.9,
                                "contract_hash": output.contract_hash,
                            }
                        },
                    },
                }
            ],
        }
    ]

    current = load_current_evaluation_sessions(repository)

    assert len(current) == 1
    assert current[0]["seed_track_ids"] == [1]
    repository.outputs[("mert", "embedding")] = _embedding_output(
        "mert",
        "9",
    )
    assert load_current_evaluation_sessions(repository) == []


@dataclass
class _Repository:
    catalog_uuid: str = _CATALOG_UUID

    def __post_init__(self) -> None:
        self.identities = {
            track_id: _identity(track_id)
            for track_id in (1, 2, 3)
        }
        coverage = AnalysisCoverage(
            sonara_core=True,
            mert=True,
            clap=True,
            maest_embedding=True,
        )
        self.summaries = {
            track_id: _summary(identity, coverage=coverage)
            for track_id, identity in self.identities.items()
        }
        self.outputs = {
            ("mert", "embedding"): current_embedding_analysis_output(
                "mert"
            ),
            ("maest", "embedding"): current_embedding_analysis_output(
                "maest"
            ),
            ("clap", "embedding"): current_embedding_analysis_output(
                "clap"
            ),
            ("sonara", "core"): _sonara_output(),
        }
        self.vectors = {
            "mert": {
                1: _expanded_vector(768, 1.0, 0.0),
                2: _expanded_vector(768, 0.9949874, 0.1),
                3: _expanded_vector(768, 0.8, 0.6),
            },
            "maest": {
                1: _expanded_vector(768, 0.0, 1.0),
                2: _expanded_vector(768, 0.1, 0.9949874),
                3: _expanded_vector(768, 0.6, 0.8),
            },
            "clap": {
                1: _expanded_vector(512, 1.0, 0.0),
                2: _expanded_vector(512, 0.9, 0.4358899),
                3: _expanded_vector(512, 0.0, 1.0),
            },
        }
        sonara_output = self.outputs[("sonara", "core")]
        self.sonara_rows = {
            track_id: SonaraFeatureRow(
                target=_target(identity),
                output=sonara_output,
                values={
                    "detected_bpm": 120.0 + track_id,
                    "detected_key_camelot": "8A",
                    "energy_score": 0.4 + 0.1 * track_id,
                },
            )
            for track_id, identity in self.identities.items()
        }
        self.created_sessions: list[dict[str, object]] = []
        self.recorded_events: list[dict[str, object]] = []
        self.raw_sessions: list[dict[str, object]] = []

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        return self.outputs.get((analysis_family, output_kind))

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        selected_ids = (
            set(self.identities)
            if targets is None
            else {target.track_id for target in targets}
        )
        return tuple(
            AnalysisVectorRow(
                target=_target(self.identities[track_id]),
                output=output,
                vector=vector,
            )
            for track_id, vector in self.vectors[
                output.contract.analysis_family
            ].items()
            if track_id in selected_ids
        )

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        selected_ids = (
            set(self.identities)
            if targets is None
            else {target.track_id for target in targets}
        )
        return tuple(
            self.sonara_rows[track_id]
            for track_id in sorted(selected_ids)
            if track_id in self.sonara_rows
        )

    def get_track_identity(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackIdentity | None:
        del include_missing
        return self.identities.get(track_id)

    def get_track_identities(
        self,
        track_ids: Sequence[int] | Mapping[int, object],
        *,
        include_missing: bool = False,
    ) -> dict[int, TrackIdentity]:
        del include_missing
        return {
            track_id: self.identities[track_id]
            for track_id in track_ids
            if track_id in self.identities
        }

    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        del include_missing
        return tuple(self.summaries[track_id] for track_id in track_ids)

    def list_track_paths(self) -> tuple[SimpleNamespace, ...]:
        return tuple(
            SimpleNamespace(track_id=track_id)
            for track_id in sorted(self.identities)
        )

    def create_search_session(
        self,
        mode: str,
        seed_track_ids: Sequence[int],
        request: Mapping[str, object],
    ) -> int:
        self.created_sessions.append(
            {
                "mode": mode,
                "seed_track_ids": list(seed_track_ids),
                "request": dict(request),
            }
        )
        return len(self.created_sessions)

    def record_search_result_event(
        self,
        session_id: int,
        track_id: int,
        rank: int,
        total_score: float,
        score_breakdown: Mapping[str, object],
    ) -> int:
        self.recorded_events.append(
            {
                "session_id": session_id,
                "track_id": track_id,
                "rank": rank,
                "total_score": total_score,
                "score_breakdown": dict(score_breakdown),
            }
        )
        return len(self.recorded_events)

    def list_search_sessions_with_events(
        self,
    ) -> list[dict[str, object]]:
        return self.raw_sessions


def _identity(track_id: int) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=_CATALOG_UUID,
        track_id=track_id,
        track_uuid=f"00000000-0000-4000-8000-{track_id:012d}",
        content_generation=1,
    )


def _expanded_vector(
    dim: int,
    first: float,
    second: float,
) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    vector[:2] = (first, second)
    return vector


def _target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
    )


def _summary(
    identity: TrackIdentity,
    *,
    coverage: AnalysisCoverage,
) -> TrackSummary:
    return TrackSummary(
        track_id=identity.track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/track-{identity.track_id}.wav",
        title=f"Track {identity.track_id}",
        artist=f"Artist {identity.track_id}",
        album="Fixture",
        tag_bpm=120.0 + identity.track_id,
        tag_key="8A",
        audio_duration_seconds=240.0,
        liked=False,
        analysis_coverage=coverage,
        classifier_scores=(),
    )


def _embedding_output(family: str, hash_digit: str) -> AnalysisOutput:
    return AnalysisOutput(
        ContractIdentity(
            analysis_family=family,
            output_kind="embedding",
            model_name=f"{family}-fixture",
            model_version="1",
            dim=2,
            encoding=FLOAT32_LE_ENCODING,
            normalization="l2",
            checkpoint_id="sha256:" + hash_digit * 64,
            preprocessing="fixture-v1",
            parameters={"fixture": True},
        )
    )


def _sonara_output() -> AnalysisOutput:
    return AnalysisOutput(
        ContractIdentity(
            analysis_family="sonara",
            output_kind="core",
            model_name="sonara-fixture",
            model_version=SONARA_EXPECTED_VERSION,
            release_hash="sha256:" + "4" * 64,
            checkpoint_id="sha256:" + "5" * 64,
            preprocessing="fixture-v1",
            parameters={"fixture": True},
        )
    )


def _identity_payload(identity: TrackIdentity) -> dict[str, object]:
    return {
        "catalog_uuid": identity.catalog_uuid,
        "track_id": identity.track_id,
        "track_uuid": identity.track_uuid,
        "content_generation": identity.content_generation,
    }


def _stored_identity_payload(
    identity: TrackIdentity,
) -> dict[str, object]:
    payload = _identity_payload(identity)
    payload.pop("catalog_uuid")
    return payload

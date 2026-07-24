from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from dj_track_similarity.analysis_contracts import FLOAT32_LE_ENCODING, ContractIdentity
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.track_models import TrackIdentity


CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


@dataclass
class EvaluationRepository:
    catalog_uuid: str = CATALOG_UUID
    track_count: int = 80

    def __post_init__(self) -> None:
        self.identities = {
            track_id: _identity(track_id)
            for track_id in range(1, self.track_count + 1)
        }
        coverage = AnalysisCoverage(
            sonara_core=True, mert=True, maest_embedding=True, clap=True
        )
        self.summaries = {
            track_id: _summary(identity, coverage)
            for track_id, identity in self.identities.items()
        }
        self.outputs = {
            ("mert", "embedding"): _embedding_output("mert", "1"),
            ("maest", "embedding"): _embedding_output("maest", "2"),
            ("clap", "embedding"): _embedding_output("clap", "3"),
            ("sonara", "core"): _sonara_output(),
        }
        self.sonara_rows = {
            track_id: SonaraFeatureRow(
                target=_target(identity),
                output=self.outputs[("sonara", "core")],
                values={
                    "detected_bpm": 120.0,
                    "detected_key_camelot": "8A",
                    "energy_score": 0.5,
                },
            )
            for track_id, identity in self.identities.items()
        }
        self.sessions: list[dict[str, Any]] = []
        self.feedback: dict[tuple[int, int, str], dict[str, Any]] = {}
        self.vectors: dict[str, dict[int, np.ndarray]] = {
            "mert": {},
            "maest": {},
            "clap": {},
        }
        self._event_id = 1

    def add_session(
        self,
        *,
        seed_track_id: int = 1,
        events: Sequence[Mapping[str, Any]],
        mode: str = "evaluation_candidate_pool",
        feedback_source: str = "manual",
    ) -> int:
        session_id = len(self.sessions) + 1
        sources = sorted(
            {
                str(source)
                for event in events
                for source in dict(event.get("sources") or {})
            }
        )
        session = {
            "id": session_id,
            "mode": mode,
            "created_at": f"2026-07-24T12:00:{session_id:02d}Z",
            "request": {
                "catalog_uuid": self.catalog_uuid,
                "feedback_source": feedback_source,
                "seed_identities": [identity_payload(self.identities[seed_track_id])],
                "source_contract_hashes": {
                    source: self.outputs[_output_key(source)].contract_hash
                    for source in sources
                },
            },
            "seeds": [
                {
                    "position": 0,
                    **stored_identity_payload(self.identities[seed_track_id]),
                }
            ],
            "events": [self._event_payload(event) for event in events],
        }
        self.sessions.append(session)
        return session_id

    def add_feedback(
        self,
        candidate_track_id: int,
        rating: int,
        *,
        seed_track_id: int = 1,
        source: str = "manual",
        reason_tags: Sequence[str] = (),
    ) -> None:
        self.feedback[(seed_track_id, candidate_track_id, source)] = {
            "seed_track_id": seed_track_id,
            "candidate_track_id": candidate_track_id,
            "source": source,
            "rating": rating,
            "reason_tags": list(reason_tags),
        }

    def active_analysis_output(
        self, analysis_family: str, output_kind: str
    ) -> AnalysisOutput | None:
        return self.outputs.get((analysis_family, output_kind))

    def get_track_identity(self, track_id: int) -> TrackIdentity | None:
        return self.identities.get(track_id)

    def list_search_sessions_with_events(self) -> list[dict[str, Any]]:
        return self.sessions

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

    def get_pair_feedback_map(self) -> dict[tuple[int, int, str], dict[str, Any]]:
        return self.feedback

    def create_search_session(
        self,
        mode: str,
        seed_track_ids: Sequence[int],
        request: Mapping[str, Any],
    ) -> int:
        session_id = len(self.sessions) + 1
        self.sessions.append(
            {
                "id": session_id,
                "mode": mode,
                "created_at": f"2026-07-24T12:00:{session_id:02d}Z",
                "request": dict(request),
                "seeds": [
                    {
                        "position": position,
                        **stored_identity_payload(self.identities[track_id]),
                    }
                    for position, track_id in enumerate(seed_track_ids)
                ],
                "events": [],
            }
        )
        return session_id

    def record_search_result_event(
        self,
        session_id: int,
        track_id: int,
        rank: int,
        total_score: float,
        score_breakdown: Mapping[str, Any],
    ) -> int:
        session = next(
            session
            for session in self.sessions
            if int(session["id"]) == session_id
        )
        event_id = self._event_id
        self._event_id += 1
        session["events"].append(
            {
                "id": event_id,
                "rank": rank,
                "total_score": total_score,
                **stored_identity_payload(self.identities[track_id]),
                "score_breakdown": dict(score_breakdown),
            }
        )
        return event_id

    def count_evaluation_rows(self) -> dict[str, int]:
        return {
            "search_sessions": len(self.sessions),
            "pair_feedback": len(self.feedback),
        }

    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        del include_missing
        return tuple(
            self.summaries[track_id]
            for track_id in track_ids
            if track_id in self.summaries
        )

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        del output
        selected_ids = (
            self.identities
            if targets is None
            else {target.track_id for target in targets}
        )
        return tuple(
            self.sonara_rows[track_id]
            for track_id in selected_ids
            if track_id in self.sonara_rows
        )

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
                vector=vector.copy(),
            )
            for track_id, vector in sorted(
                self.vectors.get(output.contract.analysis_family, {}).items()
            )
            if track_id in selected_ids
        )

    def set_vector(
        self,
        source: str,
        track_id: int,
        vector: Sequence[float],
    ) -> None:
        output = self.outputs[(source, "embedding")]
        clean_vector = np.zeros(int(output.contract.dim), dtype=np.float32)
        values = np.asarray(vector, dtype=np.float32)
        clean_vector[: min(clean_vector.size, values.size)] = values[
            : clean_vector.size
        ]
        norm = float(np.linalg.norm(clean_vector.astype(np.float64)))
        if norm <= 0.0:
            raise ValueError("fixture vector must have a positive norm")
        self.vectors[source][track_id] = clean_vector / norm

    def _event_payload(self, event: Mapping[str, Any]) -> dict[str, Any]:
        candidate_track_id = int(event["candidate_track_id"])
        contributions = {
            source: {
                **dict(contribution),
                "contract_hash": self.outputs[_output_key(source)].contract_hash,
            }
            for source, contribution in dict(event.get("sources") or {}).items()
        }
        score_breakdown = {
            "candidate_identity": identity_payload(self.identities[candidate_track_id]),
            "sources": contributions,
            **dict(event.get("score_breakdown") or {}),
        }
        payload = {
            "id": self._event_id,
            "rank": int(event.get("rank", self._event_id)),
            "total_score": float(event.get("total_score", 0.0)),
            **stored_identity_payload(self.identities[candidate_track_id]),
            "score_breakdown": score_breakdown,
        }
        self._event_id += 1
        return payload


def profile(weights: Mapping[str, float]):
    from dj_track_similarity.evaluation.score_profiles import (
        build_score_profile_from_source_report,
    )

    return build_score_profile_from_source_report(
        {
            "status": "ok",
            "profile_kind": "unsupervised_source_profile",
            "weight_kind": "unsupervised_internal_profile",
            "sources": list(weights),
            "seed_count": 1,
            "per_source": {},
            "consensus": {},
            "recommended_weights": {
                "weight_kind": "unsupervised_internal_profile",
                "weights": dict(weights),
                "note": "test",
            },
            "warnings": [],
            "limitations": [],
        },
        name="fixture",
    )


def identity_payload(identity: TrackIdentity) -> dict[str, object]:
    return {
        "catalog_uuid": identity.catalog_uuid,
        "track_id": identity.track_id,
        "track_uuid": identity.track_uuid,
        "content_generation": identity.content_generation,
    }


def stored_identity_payload(identity: TrackIdentity) -> dict[str, object]:
    payload = identity_payload(identity)
    payload.pop("catalog_uuid")
    return payload


def _identity(track_id: int) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=CATALOG_UUID,
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


def _summary(identity: TrackIdentity, coverage: AnalysisCoverage) -> TrackSummary:
    return TrackSummary(
        track_id=identity.track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/music/track-{identity.track_id}.wav",
        title=f"Track {identity.track_id}",
        artist="Fixture",
        album="Fixture",
        tag_bpm=120.0,
        tag_key="8A",
        audio_duration_seconds=240.0,
        liked=False,
        analysis_coverage=coverage,
        classifier_scores=(),
    )


def _embedding_output(family: str, digit: str) -> AnalysisOutput:
    return AnalysisOutput(
        ContractIdentity(
            analysis_family=family,
            output_kind="embedding",
            model_name=f"{family}-fixture",
            model_version="1",
            dim=2,
            encoding=FLOAT32_LE_ENCODING,
            normalization="l2",
            checkpoint_id="sha256:" + digit * 64,
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
            model_version="0.2.9",
            release_hash="sha256:" + "4" * 64,
            checkpoint_id="sha256:" + "5" * 64,
            preprocessing="fixture-v1",
            parameters={"fixture": True},
        )
    )


def _output_key(source: str) -> tuple[str, str]:
    return (source, "core") if source == "sonara" else (source, "embedding")

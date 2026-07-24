from __future__ import annotations

from dj_track_similarity.analysis_model_runners import current_embedding_analysis_output
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
from dj_track_similarity.evaluation.source_profile import SourceProfileRequest, build_source_profile, profile_candidate_rows
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.track_models import TrackIdentity
from dj_track_similarity.transition_diagnostics import TransitionTrack
from evaluation_v7_fixtures import EvaluationRepository


def test_source_profile_is_deterministic_for_same_seed() -> None:
    db, track_ids = _profile_library()

    first = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        top_k_values=[1, 2],
        random_seed=17,
    )
    second = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        top_k_values=[1, 2],
        random_seed=17,
    )

    assert first == second
    assert first["status"] == "ok"
    assert first["profile_kind"] == "unsupervised_source_profile"


def test_source_profile_weights_sum_to_one_for_available_sources() -> None:
    db, track_ids = _profile_library()

    report = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        random_seed=123,
    )

    weights = report["recommended_weights"]["weights"]

    assert report["recommended_weights"]["weight_kind"] == "unsupervised_internal_profile"
    assert sum(weights.values()) == 1.0
    assert all(weight >= 0 for weight in weights.values())


def test_source_profile_zero_coverage_source_gets_zero_weight_and_warning() -> None:
    db = EvaluationRepository()
    _activate_runtime_embedding_outputs(db, ("mert", "maest"))
    seed_id = 1
    candidate_id = 2
    db.set_vector("mert", seed_id, [1.0, 0.0])
    db.set_vector("mert", candidate_id, [0.9, 0.1])

    report = build_source_profile(
        db,
        seed_track_ids=[seed_id],
        sources=["mert", "maest"],
        per_source=1,
        random_seed=123,
    )

    assert report["per_source"]["maest"]["seeds_with_results"] == 0
    assert report["recommended_weights"]["weights"]["maest"] == 0.0
    assert any("source=maest has no coverage" in warning for warning in report["warnings"])


def test_source_profile_default_clap_without_rows_is_neutral() -> None:
    db = EvaluationRepository()
    _activate_runtime_embedding_outputs(db, ("mert", "maest", "clap"))
    db.sonara_rows.clear()
    seed_id = 1
    candidate_id = 2
    db.set_vector("mert", seed_id, [1.0, 0.0])
    db.set_vector("mert", candidate_id, [0.9, 0.1])

    report = build_source_profile(
        db,
        seed_track_ids=[seed_id],
        sources=None,
        per_source=1,
        random_seed=123,
    )

    weights = report["recommended_weights"]["weights"]
    assert report["sources"] == ["mert", "maest", "sonara", "clap"]
    assert weights["mert"] == 1.0
    assert weights["clap"] == 0.0
    assert any("source=clap has no coverage" in warning for warning in report["warnings"])


def test_source_profile_consensus_source_outweighs_isolated_source() -> None:
    seed = _track(1)
    rows = (
        _row(seed, _track(101), {"mert": 1, "maest": 1}),
        _row(seed, _track(102), {"mert": 2}),
        _row(seed, _track(103), {"maest": 2}),
        _row(seed, _track(104), {"sonara": 1}),
        _row(seed, _track(105), {"sonara": 2}),
    )

    report = profile_candidate_rows(
        SourceProfileRequest(
            seed_track_ids=(seed.identity.track_id,),
            sources=("mert", "maest", "sonara"),
            per_source=2,
            top_k_values=(2,),
            random_seed=123,
        ),
        rows,
    )
    weights = report["recommended_weights"]["weights"]

    assert weights["mert"] > weights["sonara"]
    assert weights["maest"] > weights["sonara"]
    assert report["per_source"]["sonara"]["conflict_rate"] == 1.0
    assert report["pairwise_agreement"]["mert"]["maest"]["jaccard_at_k"]["2"] > 0.0


def _profile_library() -> tuple[EvaluationRepository, dict[str, int]]:
    db = EvaluationRepository()
    _activate_runtime_embedding_outputs(db, ("mert", "maest"))
    track_ids = {
        "seed": 1,
        "shared": 2,
        "mert_only": 3,
        "maest_only": 4,
    }
    _save_profile_embeddings(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_profile_embeddings(db, track_ids["shared"], mert=[0.99, 0.1], maest=[0.1, 0.99])
    _save_profile_embeddings(db, track_ids["mert_only"], mert=[0.8, 0.2], maest=[1.0, 0.0])
    _save_profile_embeddings(db, track_ids["maest_only"], mert=[0.0, 1.0], maest=[0.2, 0.8])
    return db, track_ids


def _activate_runtime_embedding_outputs(
    db: EvaluationRepository,
    sources: tuple[str, ...],
) -> None:
    for source in sources:
        db.outputs[(source, "embedding")] = current_embedding_analysis_output(
            source
        )


def _save_profile_embeddings(
    db: EvaluationRepository,
    track_id: int,
    *,
    mert: list[float],
    maest: list[float],
) -> None:
    db.set_vector("mert", track_id, mert)
    db.set_vector("maest", track_id, maest)


def _track(track_id: int) -> TransitionTrack:
    identity = TrackIdentity(
        catalog_uuid="source-profile-fixture",
        track_id=track_id,
        track_uuid=f"track-{track_id}",
        content_generation=1,
    )
    summary = TrackSummary(
        track_id=track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"{track_id}.wav",
        title=f"Track {track_id}",
        artist=None,
        album=None,
        tag_bpm=None,
        tag_key=None,
        audio_duration_seconds=None,
        liked=False,
        analysis_coverage=AnalysisCoverage(),
        classifier_scores=(),
    )
    return TransitionTrack(identity=identity, summary=summary)


def _row(
    seed: TransitionTrack,
    candidate: TransitionTrack,
    source_ranks: dict[str, int],
) -> CandidatePoolRow:
    return CandidatePoolRow(
        seed_track=seed,
        candidate_track=candidate,
        blind_rank=candidate.identity.track_id,
        source_contributions={
            source: CandidateSourceContribution(
                rank=rank,
                score=1.0 / rank,
                contract_hash=f"contract-{source}",
            )
            for source, rank in source_ranks.items()
        },
    )

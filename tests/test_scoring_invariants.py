from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import uuid

import numpy as np
import pytest

from dj_track_similarity import embedding, hybrid_search, set_builder
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    classifier_required_outputs_hash,
)
from dj_track_similarity.classifier_manifest import (
    classifier_feature_manifest_hash,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidateSourceContribution
from dj_track_similarity.evaluation.weighted_candidates import (
    weighted_rrf_components,
    weighted_rrf_score,
)
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.tempo_resolution import (
    confidence_aware_tempo_score,
    resolve_tempo_evidence_v7,
    tempo_filter_compatible,
)
from dj_track_similarity.track_models import TrackIdentity


def _track(track_id: int) -> TrackSummary:
    return TrackSummary(
        track_id=track_id,
        catalog_uuid="catalog-1",
        track_uuid=f"track-{track_id}",
        content_generation=1,
        file_path=f"C:/music/{track_id}.wav",
        title=f"Track {track_id}",
        artist=f"Artist {track_id}",
        album=None,
        tag_bpm=None,
        tag_key=None,
        audio_duration_seconds=180.0,
        liked=False,
        analysis_coverage=AnalysisCoverage(),
        classifier_scores=(),
    )


def _identity(track_id: int) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid="catalog-1",
        track_id=track_id,
        track_uuid=f"track-{track_id}",
        content_generation=1,
    )


def _set_candidate(
    track_id: int = 1,
    *,
    vectors: Mapping[str, np.ndarray] | None = None,
    sonara_values: Mapping[str, float] | None = None,
) -> set_builder._Candidate:
    return set_builder._Candidate(
        track=_track(track_id),
        vectors=dict(vectors or {}),
        sonara_features={},
        sonara_values=dict(sonara_values or {}),
        text_values={},
        duplicate_key=f"track-{track_id}",
        identity=_identity(track_id),
    )


def _score_set_layers(
    monkeypatch: pytest.MonkeyPatch,
    layer_scores: Mapping[str, float],
) -> set_builder._ScoredCandidate:
    embedding_keys = {
        "mert": "mert",
        "maest": "maest_embedding",
        "clap": "clap_audio",
    }
    monkeypatch.setattr(
        set_builder,
        "_embedding_similarity",
        lambda _candidate, _context, key: layer_scores[embedding_keys[key]],
    )
    monkeypatch.setattr(
        set_builder,
        "_sonara_similarity",
        lambda _candidate, _context: (
            layer_scores["sonara_broad"],
            {"timbre": layer_scores["sonara_broad"]},
        ),
    )
    result = set_builder.SmartSetBuilder(
        object(),
        analysis_outputs={
            family: current_embedding_analysis_output(family)
            for family in set_builder.REQUIRED_EMBEDDINGS
        },
    )._score_candidate(
        _set_candidate(),
        set_builder._Context(seeds=[], ranges={}),
        set_builder.SetBuilderConfig(mode="balanced_set"),
    )
    assert result is not None
    return result


def test_set_fixed_weights_and_exact_synthetic_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert set_builder.DEFAULT_MODEL_WEIGHTS == {
        "mert": 0.30,
        "clap": 0.22,
        "maest": 0.18,
        "sonara_broad": 0.30,
    }
    assert set_builder.SONARA_GROUP_WEIGHTS == {
        "rhythm": 1.0,
        "dynamics": 1.1,
        "perception": 1.0,
        "tonal": 0.8,
        "timbre": 1.2,
    }

    layer_scores = {
        "mert": 0.80,
        "clap_audio": 0.60,
        "maest_embedding": 0.40,
        "sonara_broad": 0.20,
    }
    result = _score_set_layers(monkeypatch, layer_scores)
    expected = 0.80 * 0.30 + 0.60 * 0.22 + 0.40 * 0.18 + 0.20 * 0.30

    assert result.base_score == pytest.approx(expected)
    assert result.breakdown["consensus"] == pytest.approx(expected)
    assert {
        key: result.breakdown[key]
        for key in ("mert", "clap_audio", "maest_embedding", "sonara_broad")
    } == pytest.approx(layer_scores)


@pytest.mark.parametrize(
    ("changed_layer", "weight"),
    [
        ("mert", 0.30),
        ("clap_audio", 0.22),
        ("maest_embedding", 0.18),
        ("sonara_broad", 0.30),
    ],
)
def test_changing_one_set_layer_changes_only_its_raw_component(
    monkeypatch: pytest.MonkeyPatch,
    changed_layer: str,
    weight: float,
) -> None:
    baseline_scores = {
        "mert": 0.20,
        "clap_audio": 0.30,
        "maest_embedding": 0.40,
        "sonara_broad": 0.50,
    }
    changed_scores = {
        **baseline_scores,
        changed_layer: baseline_scores[changed_layer] + 0.25,
    }

    baseline = _score_set_layers(monkeypatch, baseline_scores)
    changed = _score_set_layers(monkeypatch, changed_scores)

    for layer in baseline_scores:
        if layer == changed_layer:
            assert changed.breakdown[layer] - baseline.breakdown[
                layer
            ] == pytest.approx(0.25)
        else:
            assert changed.breakdown[layer] == baseline.breakdown[layer]
    assert changed.base_score - baseline.base_score == pytest.approx(0.25 * weight)


def test_cosine_self_is_one_and_orthogonal_is_zero() -> None:
    self_vector, orthogonal_vector = embedding._normalize_rows(
        np.asarray([[3.0, 0.0], [0.0, 4.0]], dtype=np.float32)
    )
    context = set_builder._Context(
        seeds=[],
        ranges={},
        embedding_centroids={"mert": self_vector},
    )

    assert set_builder._embedding_similarity(
        _set_candidate(vectors={"mert": self_vector}),
        context,
        "mert",
    ) == pytest.approx(1.0)
    assert set_builder._embedding_similarity(
        _set_candidate(vectors={"mert": orthogonal_vector}),
        context,
        "mert",
    ) == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("vector", "message"),
    [
        ([0.0, 0.0], "zero vector"),
        ([1.0, np.nan], "non-finite"),
        ([1.0, np.inf], "non-finite"),
        ([1.0, -np.inf], "non-finite"),
    ],
)
def test_cosine_input_normalization_rejects_invalid_vectors(
    vector: list[float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        embedding._normalize_rows(np.asarray([vector], dtype=np.float32))


def _short_vector_stats(
    mfcc: np.ndarray,
    chroma: np.ndarray,
    spectral_contrast: np.ndarray,
) -> dict[str, float]:
    return set_builder._short_vector_statistics(
        {
            "mfcc_mean_blob": tuple(
                float(value) for value in np.asarray(mfcc, dtype="<f4")
            ),
            "chroma_mean_blob": tuple(
                float(value) for value in np.asarray(chroma, dtype="<f4")
            ),
            "spectral_contrast_mean_blob": tuple(
                float(value) for value in np.asarray(spectral_contrast, dtype="<f4")
            ),
        }
    )


def test_mfcc_and_chroma_dimensions_collapse_to_one_vector_component() -> None:
    stats = _short_vector_stats(
        np.arange(13, dtype=np.float32),
        np.arange(12, dtype=np.float32),
        np.arange(7, dtype=np.float32),
    )

    assert set(stats) == {
        "mfcc_mean.summary.min",
        "mfcc_mean.summary.max",
        "mfcc_mean.summary.mean",
        "mfcc_mean.summary.std",
        "chroma_mean.summary.min",
        "chroma_mean.summary.max",
        "chroma_mean.summary.mean",
        "chroma_mean.summary.std",
        "spectral_contrast_mean",
    }
    assert stats["mfcc_mean.summary.mean"] == pytest.approx(6.0)
    assert stats["chroma_mean.summary.mean"] == pytest.approx(5.5)
    assert stats["spectral_contrast_mean"] == pytest.approx(3.0)

    compact_values = {
        "mfcc_mean.summary.mean": 1.0,
        "chroma_mean.summary.mean": 0.0,
    }
    expanded_values = {
        **{f"mfcc_mean.summary.{stat}": 1.0 for stat in ("min", "max", "mean", "std")},
        **{
            f"chroma_mean.summary.{stat}": 0.0 for stat in ("min", "max", "mean", "std")
        },
    }

    def broad_score(
        values: Mapping[str, float],
    ) -> tuple[float | None, dict[str, float]]:
        ranges = {key: (0.0, 1.0) for key in values}
        centroid = {key: 1.0 for key in values}
        return set_builder._sonara_similarity_to_centroid(
            _set_candidate(sonara_values=values),
            ranges,
            centroid,
            set(),
        )

    compact_score, compact_groups = broad_score(compact_values)
    expanded_score, expanded_groups = broad_score(expanded_values)
    expected = 1.2 / (1.2 + 0.8)

    assert compact_groups == pytest.approx({"timbre": 1.0, "tonal": 0.0})
    assert expanded_groups == pytest.approx(compact_groups)
    assert compact_score == pytest.approx(expected)
    assert expanded_score == pytest.approx(expected)


@pytest.mark.parametrize(
    ("changed_vector", "expected_changed_keys"),
    [
        (
            "mfcc",
            {
                "mfcc_mean.summary.min",
                "mfcc_mean.summary.max",
                "mfcc_mean.summary.mean",
                "mfcc_mean.summary.std",
            },
        ),
        (
            "chroma",
            {
                "chroma_mean.summary.min",
                "chroma_mean.summary.max",
                "chroma_mean.summary.mean",
                "chroma_mean.summary.std",
            },
        ),
        ("spectral_contrast", {"spectral_contrast_mean"}),
    ],
)
def test_changing_one_short_vector_changes_only_its_set_component(
    changed_vector: str,
    expected_changed_keys: set[str],
) -> None:
    vectors = {
        "mfcc": np.arange(13, dtype=np.float32),
        "chroma": np.arange(12, dtype=np.float32),
        "spectral_contrast": np.arange(7, dtype=np.float32),
    }
    baseline = _short_vector_stats(
        vectors["mfcc"],
        vectors["chroma"],
        vectors["spectral_contrast"],
    )
    changed_vectors = dict(vectors)
    changed_vectors[changed_vector] = vectors[changed_vector] * 2.0 + 1.0
    changed = _short_vector_stats(
        changed_vectors["mfcc"],
        changed_vectors["chroma"],
        changed_vectors["spectral_contrast"],
    )

    actual_changed_keys = {
        key
        for key in baseline
        if not np.isclose(baseline[key], changed[key], rtol=1e-7, atol=1e-7)
    }
    assert actual_changed_keys == expected_changed_keys


def test_set_missing_features_are_renormalized_once_within_present_group() -> None:
    complete_values = {
        "spectral_centroid_mean": 1.0,
        "spectral_bandwidth_mean": 0.0,
    }
    ranges = {key: (0.0, 1.0) for key in complete_values}
    centroid = {key: 1.0 for key in complete_values}

    complete_score, complete_groups = set_builder._sonara_similarity_to_centroid(
        _set_candidate(sonara_values=complete_values),
        ranges,
        centroid,
        set(),
    )
    missing_score, missing_groups = set_builder._sonara_similarity_to_centroid(
        _set_candidate(sonara_values={"spectral_centroid_mean": 1.0}),
        ranges,
        centroid,
        set(),
    )

    expected_complete = 0.8 / (0.8 + 0.7)
    assert complete_groups == pytest.approx({"timbre": expected_complete})
    assert complete_score == pytest.approx(expected_complete)
    assert missing_groups == pytest.approx({"timbre": 1.0})
    assert missing_score == pytest.approx(1.0)


def test_weighted_rrf_components_are_exact_and_deterministically_ordered() -> None:
    contributions = {
        "mert": CandidateSourceContribution(rank=2, score=0.99),
        "maest": CandidateSourceContribution(rank=4, score=0.01),
    }
    weights = {"mert": 0.75, "maest": 0.25}

    components = weighted_rrf_components(contributions, weights, rrf_k=60)

    assert list(components) == ["maest", "mert"]
    assert components["maest"] == pytest.approx(
        {"rank": 4, "weight": 0.25, "contribution": 0.25 / 64.0}
    )
    assert components["mert"] == pytest.approx(
        {"rank": 2, "weight": 0.75, "contribution": 0.75 / 62.0}
    )
    assert weighted_rrf_score(contributions, weights, rrf_k=60) == pytest.approx(
        0.25 / 64.0 + 0.75 / 62.0
    )


def test_hybrid_weight_scaling_is_invariant_after_global_normalization() -> None:
    sources = ("mert", "maest")
    normalized = hybrid_search._normalize_weights(
        {"mert": 3.0, "maest": 1.0},
        sources,
    )
    scaled = hybrid_search._normalize_weights(
        {"mert": 300.0, "maest": 100.0},
        sources,
    )
    contributions = {
        "mert": CandidateSourceContribution(rank=2, score=0.9),
        "maest": CandidateSourceContribution(rank=7, score=0.8),
    }

    assert normalized == pytest.approx({"mert": 0.75, "maest": 0.25})
    assert scaled == pytest.approx(normalized)
    assert weighted_rrf_score(contributions, normalized, 60) == pytest.approx(
        weighted_rrf_score(contributions, scaled, 60)
    )


def test_hybrid_missing_source_keeps_its_global_weight_penalty() -> None:
    weights = {"mert": 0.75, "maest": 0.25}
    rank = 3
    only_low_weight_source = {
        "maest": CandidateSourceContribution(rank=rank, score=0.9),
    }

    actual = weighted_rrf_score(only_low_weight_source, weights, rrf_k=60)

    assert actual == pytest.approx(0.25 / (60 + rank))
    assert actual < 1.0 / (60 + rank)


def test_zero_weight_source_has_no_effect_and_cannot_include_a_candidate() -> None:
    weights = {"mert": 1.0, "maest": 0.0}
    positive = CandidateSourceContribution(rank=2, score=0.8)
    ignored = CandidateSourceContribution(rank=1, score=1.0)
    with_zero_source = {"mert": positive, "maest": ignored}
    without_zero_source = {"mert": positive}
    zero_only = {"maest": ignored}

    assert weighted_rrf_score(with_zero_source, weights, 60) == pytest.approx(
        weighted_rrf_score(without_zero_source, weights, 60)
    )
    assert weighted_rrf_score(zero_only, weights, 60) == 0.0

    candidates = (
        hybrid_search._HybridCandidate(
            track=_track(2),
            source_contributions=with_zero_source,
            source_seed_diagnostics={},
            seed_track_ids=(1,),
            identity=_identity(2),
        ),
        hybrid_search._HybridCandidate(
            track=_track(3),
            source_contributions=without_zero_source,
            source_seed_diagnostics={},
            seed_track_ids=(1,),
            identity=_identity(3),
        ),
        hybrid_search._HybridCandidate(
            track=_track(4),
            source_contributions=zero_only,
            source_seed_diagnostics={},
            seed_track_ids=(1,),
            identity=_identity(4),
        ),
    )
    scored = hybrid_search._scored_hybrid_candidates(
        candidates,
        weights=weights,
        rrf_k=60,
        random_seed=17,
        classifier_controls=hybrid_search._ClassifierControls(
            preferences={},
            risk_weights={},
        ),
    )

    assert {row.candidate.track.track_id for row in scored} == {2, 3}
    assert all(row.raw_rrf_score == pytest.approx(1.0 / 62.0) for row in scored)


def test_hybrid_rrf_ties_have_seeded_deterministic_order() -> None:
    candidates = tuple(
        hybrid_search._HybridCandidate(
            track=_track(track_id),
            source_contributions={
                "mert": CandidateSourceContribution(rank=5, score=source_score),
            },
            source_seed_diagnostics={},
            seed_track_ids=(1,),
            identity=_identity(track_id),
        )
        for track_id, source_score in ((20, 0.99), (10, 0.01))
    )
    controls = hybrid_search._ClassifierControls(preferences={}, risk_weights={})
    random_seed = 91

    first = hybrid_search._scored_hybrid_candidates(
        candidates,
        weights={"mert": 1.0},
        rrf_k=60,
        random_seed=random_seed,
        classifier_controls=controls,
    )
    second = hybrid_search._scored_hybrid_candidates(
        tuple(reversed(candidates)),
        weights={"mert": 1.0},
        rrf_k=60,
        random_seed=random_seed,
        classifier_controls=controls,
    )
    expected_ids = sorted(
        (20, 10),
        key=lambda track_id: (
            hybrid_search._tie_token(random_seed, track_id),
            track_id,
        ),
    )

    assert [row.candidate.track.track_id for row in first] == expected_ids
    assert [row.candidate.track.track_id for row in second] == expected_ids
    assert first[0].raw_rrf_score == pytest.approx(first[1].raw_rrf_score)


def test_v7_null_bpm_confidence_is_neutral_and_does_not_promote_tag_bpm() -> None:
    candidate = resolve_tempo_evidence_v7(
        {
            "detected_bpm": 155.0,
            "bpm_confidence": None,
            "beat_grid_stability": 1.0,
            "bpm_candidates_json": "[[155.0, 1.0]]",
        },
        tag_bpm=128.0,
    )
    reference = resolve_tempo_evidence_v7(
        {
            "detected_bpm": 128.0,
            "bpm_confidence": 1.0,
            "beat_grid_stability": 1.0,
        },
        tag_bpm=None,
    )

    assert candidate.bpm == 155.0
    assert candidate.source == "sonara_low_confidence"
    assert candidate.reliability == 0.0
    assert confidence_aware_tempo_score(candidate, reference) == pytest.approx(0.5)
    assert tempo_filter_compatible(candidate, reference, tolerance_bpm=1.0)


def test_classifier_feature_assembly_preserves_order_and_never_zero_fills(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = current_embedding_analysis_output("mert")
    db.register_analysis_outputs((output,))
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                "2026-07-24T13:00:00.000000Z",
                "2026-07-24T13:00:00.000000Z",
                "2026-07-24T13:00:00.000000Z",
            ),
        )
        track_id = int(cursor.lastrowid)
    target = AnalysisTarget(
        catalog_uuid=db.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )
    vector = np.zeros(int(output.contract.dim), dtype=np.float32)
    vector[:3] = (1.0, 2.0, 3.0)
    vector /= np.linalg.norm(vector)
    assert db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    contract=output.contract,
                    vector=vector,
                    analyzed_at="2026-07-24T13:00:00.000000Z",
                ),
            ),
        )
    )[0].ok

    feature_names = ("mert:2", "mert:0", "mert:1")
    specification = ClassifierSpecification(
        classifier_key="ordered_classifier",
        model_id="ordered-model",
        feature_set="mert-contract",
        feature_manifest_hash=classifier_feature_manifest_hash(feature_names),
        required_outputs_hash=classifier_required_outputs_hash((output,)),
        feature_names=feature_names,
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
    )
    rows = db.load_classifier_feature_rows(
        specification,
        targets=(target,),
    )

    assert len(rows) == 1
    assert rows[0].target == target
    assert rows[0].vector.tolist() == pytest.approx(
        [float(vector[2]), float(vector[0]), float(vector[1])]
    )

    out_of_range_names = ("mert:768",)
    out_of_range = ClassifierSpecification(
        classifier_key="out_of_range_classifier",
        model_id="out-of-range-model",
        feature_set="mert-contract",
        feature_manifest_hash=classifier_feature_manifest_hash(out_of_range_names),
        required_outputs_hash=classifier_required_outputs_hash((output,)),
        feature_names=out_of_range_names,
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
    )

    assert (
        db.load_classifier_feature_rows(
            out_of_range,
            targets=(target,),
        )
        == ()
    )

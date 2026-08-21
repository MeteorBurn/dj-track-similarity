"""Measure whether fusing CLAP and MuQ-MuLan beats the better single model.

The two text models win on different axes, which is the case rank fusion is
meant for. That is a hypothesis, not a result: fusion can also drag the stronger
model down when the weaker one promotes the wrong tracks. This script scores
every label that has an independent reference under each single model and under
several fusion rules, then reports the per-label delta against the better single
model and against a per-label oracle that always picks the better one.

It only reads. Both databases are opened read-only and nothing is written back.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from numpy.typing import NDArray
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score

from dj_track_similarity.analysis_model_runners import current_embedding_analysis_output
from dj_track_similarity.search import _contrast_vector_scores

FloatArray = NDArray[np.float32]

CROSSCHECK = Path(__file__).with_name("text_tag_crosscheck.py")
DEFAULT_REFERENCES = Path(__file__).with_name("text_tag_crosscheck_references.json")
TOP_K = 100
RRF_K_GRID = (10, 60, 200)
MULAN_WEIGHTS = (0.5, 0.6, 0.7, 0.8)
CASCADE_DEPTH = 500


_TOOLS = None


def crosscheck_module():
    """Reuse the cross-check loaders instead of duplicating them."""

    global _TOOLS
    if _TOOLS is not None:
        return _TOOLS
    spec = importlib.util.spec_from_file_location("text_tag_crosscheck", CROSSCHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules during class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _TOOLS = module
    return module


@dataclass(frozen=True)
class LabelScores:
    label: str
    truth: NDArray[np.float64]
    scores: dict[str, FloatArray]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    tools = crosscheck_module()
    spec = {
        key: value
        for key, value in json.loads(args.references.read_text(encoding="utf-8")).items()
        if not key.startswith("_")
    }
    presets = {preset["key"]: preset for preset in tools.load_presets()}

    per_label: dict[str, LabelScores] = {}
    for family in ("mulan", "clap"):
        matrix, row_of_track = tools.load_matrix(args.db, family)
        references = tools.load_references(args.db, spec, row_of_track, matrix.shape[0])
        adapter = tools.ADAPTERS[family](device=args.device)
        adapter.preflight()
        output = current_embedding_analysis_output(family, device=args.device)
        for label, entry in spec.items():
            reference = references.get(label)
            if reference is None:
                continue
            if family in entry.get("blind", ()):
                # Scoring a family against a reference trained on its own audio
                # embedding would feed self-agreement into the per-label oracle,
                # which is the baseline every fusion arm is measured against.
                continue
            scores = label_scores(adapter, output, matrix, presets[label], family)
            truth = binary_truth(reference, entry)
            existing = per_label.get(label)
            if existing is None:
                per_label[label] = LabelScores(label=label, truth=truth, scores={family: scores})
            else:
                existing.scores[family] = scores
        print(f"{family}: scored {len(per_label)} labels", file=sys.stderr)

    usable = {
        label: item
        for label, item in per_label.items()
        if len(item.scores) == 2 and 0 < item.truth.sum() < item.truth.size
    }
    echo = sum(1 for label in usable if spec[label].get("independence") == "echo")
    print(
        f"labels with both models and a usable reference: {len(usable)} "
        f"({len(usable) - echo} orthogonal, {echo} echo)",
        file=sys.stderr,
    )

    arms = build_arms()
    results = {name: {} for name in arms}
    singles: dict[str, dict[str, float]] = {"mulan": {}, "clap": {}}
    top_results: dict[str, dict[str, float]] = {name: {} for name in arms}
    top_singles: dict[str, dict[str, float]] = {"mulan": {}, "clap": {}}
    for label, item in usable.items():
        ranks = {family: rankdata(-item.scores[family], method="average") for family in item.scores}
        for family in ("mulan", "clap"):
            singles[family][label] = auc(item.truth, item.scores[family])
            top_singles[family][label] = precision_at_k(item.truth, item.scores[family])
        for name, arm in arms.items():
            fused = arm(item.scores, ranks)
            results[name][label] = auc(item.truth, fused)
            top_results[name][label] = precision_at_k(item.truth, fused)

    print()
    print("=== global ordering (ROC-AUC)")
    report(singles, results, usable, metric="mean AUC")
    print()
    print(f"=== top of the list (share of the reference in the first {TOP_K})")
    report(top_singles, top_results, usable, metric=f"mean p@{TOP_K}")
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "singles": singles,
                    "arms": dict(results),
                    "top_singles": top_singles,
                    "top_arms": dict(top_results),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nreport written to {args.out}", file=sys.stderr)
    return 0


def build_arms() -> dict:
    arms: dict = {}
    for k in RRF_K_GRID:
        arms[f"rrf k={k} w=.50"] = make_rrf(k, 0.5)
    for weight in MULAN_WEIGHTS:
        arms[f"rrf k=60 w={weight:.2f}"] = make_rrf(60, weight)
    arms["zscore sum"] = zscore_sum
    arms[f"cascade mulan->clap n={CASCADE_DEPTH}"] = cascade
    return arms


def make_rrf(k: int, mulan_weight: float):
    def arm(_scores: dict[str, FloatArray], ranks: dict[str, NDArray[np.float64]]) -> NDArray[np.float64]:
        return mulan_weight / (k + ranks["mulan"]) + (1.0 - mulan_weight) / (k + ranks["clap"])

    return arm


def zscore_sum(scores: dict[str, FloatArray], _ranks) -> NDArray[np.float64]:
    total = np.zeros(scores["mulan"].size, dtype=np.float64)
    for values in scores.values():
        standardized = (values - values.mean()) / (values.std() or 1.0)
        total += standardized
    return total


def cascade(scores: dict[str, FloatArray], ranks: dict[str, NDArray[np.float64]]) -> NDArray[np.float64]:
    """MuQ-MuLan retrieves, CLAP reorders inside that candidate set.

    Everything outside the candidate set keeps its retrieval order below the
    whole re-ranked block, so the tail stays comparable instead of tied.
    """

    size = scores["clap"].size
    selected = ranks["mulan"] <= CASCADE_DEPTH
    fused = -(ranks["mulan"] + size)
    reranked = rankdata(-scores["clap"][selected], method="average")
    fused[selected] = -reranked
    return fused


def label_scores(adapter, output, matrix: FloatArray, preset: dict, family: str) -> FloatArray:
    tools = crosscheck_module()
    positives = adapter.embed_texts(tools.resolve_variants(preset.get("positive"), family))
    negatives = adapter.embed_texts(tools.resolve_variants(preset.get("negative"), family))
    weight = tools.resolve_weight(preset["negativeWeight"], family)
    positive_scores, negative_scores, _contrast, _bounded = _contrast_vector_scores(
        matrix,
        output=output,
        positive_vectors=positives,
        negative_vectors=negatives if weight > 0 else [],
        negative_weight=max(weight, 0.0),
    )
    return positive_scores - weight * negative_scores


def binary_truth(reference, entry: dict) -> NDArray[np.float64]:
    direction = float(entry.get("direction", 1))
    if reference.kind == "binary":
        return reference.truth if direction > 0 else 1.0 - reference.truth
    threshold = entry.get("threshold")
    if threshold is None:
        quantile = 0.9 if direction > 0 else 0.1
        threshold = float(np.quantile(reference.truth, quantile))
    truth = reference.truth >= threshold if direction > 0 else reference.truth <= threshold
    return truth.astype(np.float64)


def auc(truth: NDArray[np.float64], scores: NDArray[np.float64]) -> float:
    return float(roc_auc_score(truth, scores))


def precision_at_k(truth: NDArray[np.float64], scores: NDArray[np.float64]) -> float:
    """Share of the reference inside the first TOP_K rows an arm ranks.

    AUC judges the whole ordering, and the label cross-check showed that this
    hides labels which only ever get the first screen right. A fusion rule that
    loses on AUC but wins here is still worth having, because the first screen
    is what a DJ actually reads.
    """

    top = np.argsort(-scores, kind="stable")[:TOP_K]
    return float(truth[top].mean())


def report(singles: dict, arms: dict, usable: dict, *, metric: str) -> None:
    labels = sorted(usable)
    best_single = {label: max(singles["mulan"][label], singles["clap"][label]) for label in labels}
    oracle = float(np.mean([best_single[label] for label in labels]))

    print(f"{'arm':<28}{metric:>10}{'vs best':>9}{'wins':>7}{'losses':>8}{'worst':>8}")
    print("-" * 70)
    for name in ("mulan", "clap"):
        values = [singles[name][label] for label in labels]
        print(f"{name:<28}{np.mean(values):>10.3f}{'':>9}{'':>7}{'':>8}{'':>8}")
    print(f"{'oracle per label':<28}{oracle:>10.3f}")
    print("-" * 70)
    for name, values in arms.items():
        deltas = np.array([values[label] - best_single[label] for label in labels])
        mean = float(np.mean([values[label] for label in labels]))
        wins = int((deltas > 0.002).sum())
        losses = int((deltas < -0.002).sum())
        print(
            f"{name:<28}{mean:>10.3f}{np.mean(deltas):>9.3f}"
            f"{wins:>7}{losses:>8}{deltas.min():>8.3f}"
        )

    best_arm = max(arms, key=lambda name: np.mean([arms[name][label] for label in labels]))
    print()
    print(f"best arm: {best_arm}")
    deltas = {label: arms[best_arm][label] - best_single[label] for label in labels}
    worst = sorted(deltas.items(), key=lambda item: item[1])[:6]
    print("largest regressions against the better single model:")
    for label, delta in worst:
        print(
            f"  {label:<26}{delta:>7.3f}  "
            f"(mulan {singles['mulan'][label]:.3f}, clap {singles['clap'][label]:.3f})"
        )


if __name__ == "__main__":
    raise SystemExit(main())

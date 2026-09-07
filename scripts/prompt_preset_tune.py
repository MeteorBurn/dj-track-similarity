"""Report-only bank tuning using explicit, grouped independent label judgements.

Input JSON owns catalog_uuid, manifest_id, output_identities and judgements.
Each judgement names intent_key, track_uuid, judgement_scope="label", verdict
(+1/-1), group_id, split (train/dev/test), and manifest_id. Ordinary UI query
clicks do not supply label truth. Optional text_vectors[family][prompt] contains
precomputed vectors for reproducible offline runs without encoder downloads.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score

from dj_track_similarity.analysis.model_runners import (
    _adapter_identity,
    current_embedding_analysis_output,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter
from dj_track_similarity.search.engine import _contrast_vector_scores
from dj_track_similarity.text_search_models import content_hash

from text_tag_crosscheck import load_presets

WEIGHT_GRID = (0.0, 0.15, 0.35, 0.5, 0.75, 1.0)
ADAPTERS = {"clap": ClapEmbeddingAdapter, "mulan": MuqMulanEmbeddingAdapter}


@dataclass(frozen=True)
class Bank:
    name: str
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    weight: float

    def snapshot(self) -> dict[str, Any]:
        value = {
            "positive_queries": list(self.positive),
            "negative_queries": list(self.negative),
            "negative_weight": self.weight if self.negative else 0.0,
        }
        return {"variant": self.name, **value, "bank_hash": content_hash(value)}


def _groups(judgements: list[dict[str, Any]]) -> dict[str, str]:
    groups: dict[str, str] = {}
    tracks: dict[str, str] = {}
    for item in judgements:
        group, split, track = (
            item.get("group_id"),
            item.get("split"),
            item.get("track_uuid"),
        )
        if (
            not isinstance(group, str)
            or not group
            or split not in ("train", "dev", "test")
            or not isinstance(track, str)
        ):
            raise ValueError(
                "Every judgement requires track_uuid, group_id and train/dev/test split"
            )
        if group in groups and groups[group] != split:
            raise ValueError("Related track versions leak across dataset splits")
        if track in tracks and tracks[track] != group:
            raise ValueError("One track cannot belong to multiple split groups")
        groups[group] = split
        tracks[track] = group
    return dict(sorted(groups.items()))


def _metrics(
    scores: np.ndarray, records: list[dict[str, Any]], row_of_uuid: dict[str, int]
) -> dict[str, Any]:
    """Rank judged candidates only; never manufacture negatives from unjudged rows."""
    ranked = sorted(
        records,
        key=lambda item: (
            -float(scores[row_of_uuid[item["track_uuid"]]]),
            item["track_uuid"],
        ),
    )
    top = ranked[:10]
    precision = sum(item["verdict"] > 0 for item in top) / len(top) if top else None
    truth = [item["verdict"] > 0 for item in records]
    judged_scores = [float(scores[row_of_uuid[item["track_uuid"]]]) for item in records]
    return {
        "precision_at_10": precision if len(top) == 10 else None,
        "precision_at_k": precision,
        "judged_pool_average_precision": float(
            average_precision_score(truth, judged_scores)
        )
        if records
        else None,
        "judged_count": len(records),
        "evaluated_k": len(top),
        "pool": "judged_only",
    }


def evaluate_family(
    *,
    snapshot: dict[str, Any],
    family: str,
    identity: dict[str, Any],
    dataset: dict[str, Any],
    presets: dict[str, dict[str, Any]],
    embed_texts,
    min_per_class: int = 2,
    candidates: list[dict[str, Any]] | None = None,
    selected: set[str] | None = None,
) -> dict[str, Any]:
    rows = sorted(snapshot["rows"], key=lambda row: row.target.track_uuid)
    uuids = [row.target.track_uuid for row in rows]
    row_of_uuid = {uuid: index for index, uuid in enumerate(uuids)}
    excluded: Counter[str] = Counter()
    excluded["production_ineligible_tracks"] = snapshot["excluded_count"]
    judgements = dataset.get("judgements", [])
    if not isinstance(judgements, list):
        raise ValueError("judgements must be an explicit list")
    groups = _groups(judgements)
    manifest_id = dataset.get("manifest_id")
    if not isinstance(manifest_id, str) or not manifest_id:
        raise ValueError("An explicit evaluation manifest_id is required")
    by_intent: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for item in judgements:
        reason = None
        intent = item.get("intent_key")
        if dataset.get("catalog_uuid") != snapshot["catalog_uuid"]:
            reason = "catalog_mismatch"
        elif dataset.get("output_identities", {}).get(family) != identity:
            reason = "output_identity_mismatch"
        elif intent not in presets:
            reason = "unknown_intent_key"
        elif selected and intent not in selected:
            reason = "not_selected"
        elif item.get("judgement_scope") != "label":
            reason = "not_explicit_label_judgement"
        elif item.get("manifest_id") != manifest_id:
            reason = "manifest_mismatch"
        elif item.get("track_uuid") not in row_of_uuid:
            reason = "ineligible_or_missing_embedding"
        elif item.get("verdict") not in (-1, 1) or isinstance(
            item.get("verdict"), bool
        ):
            reason = "unjudged"
        if reason:
            excluded[reason] += 1
            continue
        key = (intent, item["track_uuid"])
        if key in seen:
            raise ValueError("Duplicate intent/track judgement")
        seen.add(key)
        by_intent.setdefault(intent, []).append(item)
    report: dict[str, Any] = {
        "family": family,
        "status": "insufficient_eligible_labels",
        "promoted": False,
        "excluded": dict(sorted(excluded.items())),
        "intents": [],
        "manifest": {
            "manifest_id": manifest_id,
            "qrels_hash": content_hash(
                sorted(
                    judgements,
                    key=lambda item: (
                        str(item.get("intent_key")),
                        str(item.get("track_uuid")),
                    ),
                )
            ),
            "catalog_uuid": snapshot["catalog_uuid"],
            "analysis_output_identity": identity,
            "eligible_track_uuids": uuids,
            "group_splits": groups,
            "assignments": sorted(
                [
                    {
                        key: item[key]
                        for key in ("intent_key", "track_uuid", "group_id", "split")
                    }
                    for items in by_intent.values()
                    for item in items
                ],
                key=lambda item: (item["intent_key"], item["track_uuid"]),
            ),
            "score_pooling": "positive-centroid-top2-negative-v1",
            "feedback": "off",
            "code_revision": None,
            "versions": {"python": sys.version.split()[0], "numpy": np.__version__},
            "banks": [],
        },
    }
    if not rows:
        return report
    matrix = np.vstack([row.vector for row in rows]).astype(np.float32)
    output = current_embedding_analysis_output(family)
    vector_cache: dict[str, np.ndarray] = {}

    def vectors(lines: tuple[str, ...]) -> list[np.ndarray]:
        missing = list(
            dict.fromkeys(line for line in lines if line not in vector_cache)
        )
        if missing:
            encoded = embed_texts(missing)
            if len(encoded) != len(missing):
                raise ValueError("Encoder returned a different text vector count")
            vector_cache.update(zip(missing, encoded, strict=True))
        return [vector_cache[line] for line in lines]

    for intent, records in sorted(by_intent.items()):
        dev = [item for item in records if item["split"] == "dev"]
        heldout = [item for item in records if item["split"] == "test"]
        if any(
            sum(item["verdict"] == verdict for item in dev) < min_per_class
            for verdict in (-1, 1)
        ):
            report["excluded"]["insufficient_dev_labels"] = (
                report["excluded"].get("insufficient_dev_labels", 0) + 1
            )
            continue
        preset = presets[intent]
        shipping = preset["productionBanks"][family]
        positive = tuple(shipping["positive_queries"])
        negative = tuple(shipping["negative_queries"])
        production_weight = float(shipping["negative_weight"]) if negative else 0.0
        baseline = Bank("production", positive, negative, production_weight)
        banks = [baseline]
        variants = [("current", positive, negative)]
        for index in range(len(positive)):
            if len(positive) > 1:
                variants.append(
                    (
                        f"drop_positive_{index}",
                        positive[:index] + positive[index + 1 :],
                        negative,
                    )
                )
        for index in range(len(negative)):
            variants.append(
                (
                    f"drop_negative_{index}",
                    positive,
                    negative[:index] + negative[index + 1 :],
                )
            )
        for candidate in candidates or []:
            if (
                candidate.get("intent_key") != intent
                or candidate.get("family", family) != family
            ):
                continue
            if (
                candidate.get("name") in ("production", "current")
                or not isinstance(candidate.get("name"), str)
                or not candidate["name"].strip()
            ):
                raise ValueError(
                    "Candidate name must be nonempty and cannot be production/current"
                )
            candidate_positive = candidate.get("positive_queries", [])
            candidate_negative = candidate.get("negative_queries", [])
            if not candidate_positive or any(
                not isinstance(line, str) or not line.strip()
                for line in candidate_positive + candidate_negative
            ):
                raise ValueError("Candidate banks require nonempty positive text")
            variants.append(
                (
                    str(candidate["name"]),
                    tuple(candidate_positive),
                    tuple(candidate_negative),
                )
            )
        if len(variants) > 128:
            raise ValueError("Candidate grid exceeds the bounded experiment limit")
        for name, positives, negatives in variants:
            for weight in WEIGHT_GRID if negatives else (0.0,):
                banks.append(Bank(name, positives, negatives, weight))
        scored: list[tuple[Bank, np.ndarray, dict[str, Any]]] = []
        for bank in banks:
            _positive, _negative, scores, _weight = _contrast_vector_scores(
                matrix,
                output=output,
                positive_vectors=vectors(bank.positive),
                negative_vectors=vectors(bank.negative),
                negative_weight=bank.weight,
            )
            scored.append((bank, scores, _metrics(scores, dev, row_of_uuid)))
        # Selection reads dev only. Freeze identity before touching test labels.
        winner = max(scored, key=lambda row: row[2]["judged_pool_average_precision"])
        tuned_current = max(
            (row for row in scored if row[0].name in ("production", "current")),
            key=lambda row: row[2]["judged_pool_average_precision"],
        )
        frozen = winner[0].snapshot()
        enough_test = all(
            sum(item["verdict"] == verdict for item in heldout) >= min_per_class
            for verdict in (-1, 1)
        )
        baseline_test = (
            _metrics(scored[0][1], heldout, row_of_uuid) if enough_test else None
        )
        selected_test = (
            _metrics(winner[1], heldout, row_of_uuid) if enough_test else None
        )
        report["intents"].append(
            {
                "intent_key": intent,
                "evidence": "held_out" if enough_test else "dev_exploration_only",
                "production_baseline": {
                    **baseline.snapshot(),
                    "dev": scored[0][2],
                    "test": baseline_test,
                },
                "tuned_current": {
                    **tuned_current[0].snapshot(),
                    "dev": tuned_current[2],
                },
                "selected_dev_candidate": {
                    **frozen,
                    "dev": winner[2],
                    "test": selected_test,
                },
                "promoted": False,
                "selection_split": "dev",
                "selection_metric": "judged_pool_average_precision",
                "test_evaluations_per_selected_candidate": 1 if enough_test else 0,
                "judged_fraction": len(records) / len(rows),
                "grid": [
                    {**bank.snapshot(), "dev": metrics}
                    for bank, _scores, metrics in scored
                ],
            }
        )
        report["manifest"]["banks"].append(
            {
                "intent_key": intent,
                "variants": [bank.snapshot() for bank in banks],
                "frozen_candidate_hash": frozen["bank_hash"],
            }
        )
    if report["intents"]:
        report["status"] = "report_only"
    report["manifest"]["experiment_hash"] = content_hash(report["manifest"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--models", default="mulan,clap")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--min-per-class", type=int, default=2)
    parser.add_argument("--presets", default="")
    parser.add_argument("--evaluation-json", type=Path)
    parser.add_argument("--candidates-json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.min_per_class < 1:
        parser.error("--min-per-class must be positive")
    # Resolve the named library without constructing a writable application owner.
    args.db = args.db.resolve(strict=True)
    if args.evaluation_json is None:
        report = {
            "status": "insufficient_eligible_labels",
            "reason": "explicit_evaluation_json_required",
            "promoted": False,
            "results": [],
        }
    else:
        dataset = json.loads(args.evaluation_json.read_text(encoding="utf-8"))
        candidates = (
            json.loads(args.candidates_json.read_text(encoding="utf-8"))
            if args.candidates_json
            else []
        )
        presets = {
            preset["key"]: preset
            for preset in load_presets(include_composed_banks=True)
        }
        selected = {value.strip() for value in args.presets.split(",") if value.strip()}
        unknown = selected - presets.keys()
        if unknown:
            parser.error(f"Unknown preset keys: {sorted(unknown)}")
        results = []
        for family in args.models.split(","):
            family = family.strip().lower()
            if family not in ADAPTERS:
                parser.error(f"Unsupported text family: {family}")
            snapshot = LibraryDatabase.read_text_evaluation_embeddings(
                args.db, current_embedding_analysis_output(family)
            )
            adapter = ADAPTERS[family](device=args.device)
            identity = {
                **_adapter_identity(adapter),
                "analysis_family": family,
                "output_kind": "embedding",
            }
            precomputed = dataset.get("text_vectors", {}).get(family)
            embed = (
                adapter.embed_texts
                if precomputed is None
                else lambda texts: [
                    np.asarray(precomputed[text], dtype=np.float32) for text in texts
                ]
            )
            results.append(
                evaluate_family(
                    snapshot=snapshot,
                    family=family,
                    identity=identity,
                    dataset=dataset,
                    presets=presets,
                    embed_texts=embed,
                    min_per_class=args.min_per_class,
                    candidates=candidates,
                    selected=selected,
                )
            )
        report = {
            "status": "report_only"
            if any(result["intents"] for result in results)
            else "insufficient_eligible_labels",
            "promoted": False,
            "results": results,
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

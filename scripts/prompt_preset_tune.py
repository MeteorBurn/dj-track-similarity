"""Tune preset banks on accumulated relevance verdicts, report-first.

The text tab stores one verdict per (track, preset, model) in
``text_preset_feedback``: +1 when a search hit matched what the preset means,
-1 when it missed. This script turns that reinforcement signal into concrete
wording and weight proposals. For every preset with enough verdicts it scores,
on the frozen stored embeddings:

* the current bank across the hard-negative weight grid;
* every leave-one-out variant of the positive and the negative bank, which
  puts a measured marginal value next to each line.

Nothing is written anywhere: the script prints the winners and the operator
edits ``textPromptPresets.ts`` — the same report-first contract as the rest of
the tooling. Both databases are opened read-only. Verdict pools are the
operator's own ears; trained classifier outputs play no part here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import sys
import time

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import average_precision_score, roc_auc_score

from dj_track_similarity.analysis_model_runners import current_embedding_analysis_output
from dj_track_similarity.embedding import ClapEmbeddingAdapter, MuqMulanEmbeddingAdapter
from dj_track_similarity.search import _contrast_vector_scores

from text_prompt_benchmark import _load_matrix
from text_tag_crosscheck import load_presets

FloatArray = NDArray[np.float32]

WEIGHT_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)

ADAPTERS = {
    "clap": ClapEmbeddingAdapter,
    "mulan": MuqMulanEmbeddingAdapter,
}


@dataclass(frozen=True)
class FeedbackPool:
    preset_key: str
    family: str
    positive_rows: NDArray[np.int64]
    negative_rows: NDArray[np.int64]


@dataclass(frozen=True)
class BankScore:
    variant: str
    weight: float
    roc_auc: float
    average_precision: float


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Library database to read.")
    parser.add_argument("--models", default="mulan,clap")
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--min-per-class",
        type=int,
        default=5,
        help="Minimum relevant AND irrelevant verdicts before a preset is tuned.",
    )
    parser.add_argument(
        "--presets",
        default="",
        help="Comma-separated preset keys. Defaults to every preset with enough verdicts.",
    )
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args(argv)

    presets = {preset["key"]: preset for preset in load_presets()}
    selected = {name.strip() for name in args.presets.split(",") if name.strip()}
    unknown = selected - presets.keys()
    if unknown:
        raise SystemExit(f"Unknown preset keys: {sorted(unknown)}")

    report: list[dict] = []
    for family in [name.strip().lower() for name in args.models.split(",") if name.strip()]:
        if family not in ADAPTERS:
            raise SystemExit(f"Unsupported text embedding family: {family}")
        matrix, row_of_track = _load_matrix(args.db, family)
        pools = _load_pools(
            args.db,
            family,
            row_of_track,
            min_per_class=args.min_per_class,
            selected=selected,
        )
        if not pools:
            print(
                f"{family}: no preset has {args.min_per_class}+ verdicts per class yet — "
                "judge more text-search results first",
                file=sys.stderr,
            )
            continue
        adapter = ADAPTERS[family](device=args.device)
        started = time.perf_counter()
        adapter.preflight()
        print(f"{family}: model loaded in {time.perf_counter() - started:.1f}s", file=sys.stderr)
        output = current_embedding_analysis_output(family, device=args.device)
        for pool in pools:
            preset = presets[pool.preset_key]
            report.append(
                _tune_preset(adapter, output, matrix, pool, preset, family)
            )

    _print_report(report)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport written to {args.out}", file=sys.stderr)
    return 0


def _tune_preset(adapter, output, matrix, pool: FeedbackPool, preset: dict, family: str) -> dict:
    positives = _bank_lines(preset.get("positive"), family)
    negatives = _bank_lines(preset.get("negative"), family)

    variants: list[tuple[str, list[str], list[str]]] = [("current", positives, negatives)]
    for index in range(len(positives)):
        if len(positives) < 2:
            break
        variants.append(
            (
                f"drop +{index + 1}",
                positives[:index] + positives[index + 1 :],
                negatives,
            )
        )
    for index in range(len(negatives)):
        variants.append(
            (
                f"drop -{index + 1}",
                positives,
                negatives[:index] + negatives[index + 1 :],
            )
        )

    truth = np.zeros(matrix.shape[0], dtype=bool)
    truth[pool.positive_rows] = True
    rows = np.concatenate([pool.positive_rows, pool.negative_rows])

    scored: list[BankScore] = []
    for name, positive_bank, negative_bank in variants:
        positive_vectors = adapter.embed_texts(positive_bank)
        negative_vectors = adapter.embed_texts(negative_bank) if negative_bank else []
        positive_scores, negative_scores, _contrast, _weight = _contrast_vector_scores(
            matrix,
            output=output,
            positive_vectors=positive_vectors,
            negative_vectors=negative_vectors,
            negative_weight=0.0,
        )
        for weight in WEIGHT_GRID:
            if weight and not negative_bank:
                continue
            scores = positive_scores - weight * negative_scores
            scored.append(
                BankScore(
                    variant=name,
                    weight=weight,
                    roc_auc=float(roc_auc_score(truth[rows], scores[rows])),
                    average_precision=float(
                        average_precision_score(truth[rows], scores[rows])
                    ),
                )
            )

    baseline = max(
        (item for item in scored if item.variant == "current"),
        key=lambda item: item.roc_auc,
    )
    best = max(scored, key=lambda item: item.roc_auc)
    return {
        "preset": pool.preset_key,
        "model": family,
        "relevant": int(pool.positive_rows.size),
        "irrelevant": int(pool.negative_rows.size),
        "baseline": vars(baseline),
        "best": vars(best),
        "grid": [vars(item) for item in scored],
    }


def _bank_lines(bank: dict | None, family: str) -> list[str]:
    if not bank:
        return []
    return list(bank.get(family) or bank.get("shared") or [])


def _load_pools(
    db_path: Path,
    family: str,
    row_of_track: dict[int, int],
    *,
    min_per_class: int,
    selected: set[str],
) -> list[FeedbackPool]:
    with sqlite3.connect(_read_only_uri(db_path), uri=True) as connection:
        try:
            rows = connection.execute(
                """
                SELECT preset_key, verdict, track_id
                FROM text_preset_feedback
                WHERE analysis_family = ?
                ORDER BY preset_key
                """,
                (family,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    by_preset: dict[str, tuple[list[int], list[int]]] = {}
    for preset_key, verdict, track_id in rows:
        if selected and preset_key not in selected:
            continue
        row = row_of_track.get(int(track_id))
        if row is None:
            continue
        positive_rows, negative_rows = by_preset.setdefault(preset_key, ([], []))
        (positive_rows if verdict > 0 else negative_rows).append(row)
    pools = []
    for preset_key, (positive_rows, negative_rows) in sorted(by_preset.items()):
        if len(positive_rows) < min_per_class or len(negative_rows) < min_per_class:
            print(
                f"{family}: skipping {preset_key} — "
                f"{len(positive_rows)} relevant / {len(negative_rows)} irrelevant "
                f"verdicts, need {min_per_class}+ of each",
                file=sys.stderr,
            )
            continue
        pools.append(
            FeedbackPool(
                preset_key=preset_key,
                family=family,
                positive_rows=np.asarray(sorted(set(positive_rows)), dtype=np.int64),
                negative_rows=np.asarray(sorted(set(negative_rows)), dtype=np.int64),
            )
        )
    return pools


def _print_report(report: list[dict]) -> None:
    if not report:
        print("nothing tuned")
        return
    header = (
        f"{'preset':<28}{'model':<7}{'pool':<12}"
        f"{'current':<18}{'best':<26}{'gain':>7}"
    )
    print(header)
    print("-" * len(header))
    for item in report:
        baseline = item["baseline"]
        best = item["best"]
        gain = best["roc_auc"] - baseline["roc_auc"]
        print(
            f"{item['preset']:<28}{item['model']:<7}"
            f"{str(item['relevant']) + '+/' + str(item['irrelevant']) + '-':<12}"
            f"{baseline['roc_auc']:.3f} @w{baseline['weight']:.2f}     "
            f"{best['variant']:<12}{best['roc_auc']:.3f} @w{best['weight']:.2f}"
            f"{gain:>+7.3f}"
        )
    print(
        "\nA positive gain on 'drop +N' or 'drop -N' means that line hurts the"
        "\npreset on your verdicts; apply changes in textPromptPresets.ts and"
        "\nre-run. Small pools move: trust gains, not third decimals."
    )


def _read_only_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


if __name__ == "__main__":
    raise SystemExit(main())

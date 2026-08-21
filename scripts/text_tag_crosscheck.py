"""Cross-check text-layer labels against SONARA and MAEST signals.

Most of the prompt vocabulary has no hand-labelled examples, so its reliability
is unknown. Other analysis layers already describe the same library from a
different direction: SONARA measures tempo, key, energy, vocal probability and
spectral shape, and MAEST assigns genre labels. Ranking the library with a label
and comparing that ranking against one of those signals says whether the label
points where it claims to point.

This is a cross-check, not ground truth. A weak result can mean the label is
weak or that the reference does not describe it. The script only reads: both
databases are opened read-only and nothing is written back.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from dj_track_similarity.analysis_model_runners import current_embedding_analysis_output
from dj_track_similarity.embedding import ClapEmbeddingAdapter, MuqMulanEmbeddingAdapter
from dj_track_similarity.search import _contrast_vector_scores

FloatArray = NDArray[np.float32]

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESETS_TS = REPO_ROOT / "frontend" / "src" / "textPromptPresets.ts"
DEFAULT_REFERENCES = Path(__file__).with_name("text_tag_crosscheck_references.json")
TOP_K = 100

ADAPTERS = {"clap": ClapEmbeddingAdapter, "mulan": MuqMulanEmbeddingAdapter}

BINARY_STRONG = 0.70
BINARY_WEAK = 0.55
EXTREME_QUANTILE = 0.9


@dataclass(frozen=True)
class Reference:
    key: str
    kind: str
    truth: NDArray[np.float64]
    description: str


@dataclass(frozen=True)
class CrossCheck:
    label: str
    model: str
    reference: str
    kind: str
    statistic: float
    spearman: float
    top_share: float
    base_rate: float
    lift: float
    verdict: str

    def as_row(self) -> str:
        return (
            f"{self.label:<26}{self.model:<7}{self.reference:<34}"
            f"{self.statistic:>7.3f}{self.top_share:>8.2f}{self.base_rate:>8.2f}"
            f"{self.lift:>7.1f}  {self.verdict}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Library database to read.")
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--models", default="mulan,clap")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args(argv)

    references_spec = {
        key: value
        for key, value in json.loads(args.references.read_text(encoding="utf-8")).items()
        if not key.startswith("_")
    }
    presets = {preset["key"]: preset for preset in load_presets()}
    missing = sorted(set(references_spec) - set(presets))
    if missing:
        raise SystemExit(f"References name labels that no longer exist: {missing}")

    checks: list[CrossCheck] = []
    for family in [name.strip().lower() for name in args.models.split(",") if name.strip()]:
        if family not in ADAPTERS:
            raise SystemExit(f"Unsupported text embedding family: {family}")
        matrix, row_of_track = load_matrix(args.db, family)
        references = load_references(args.db, references_spec, row_of_track, matrix.shape[0])
        checks.extend(
            check_family(family, matrix, presets, references_spec, references, device=args.device)
        )

    print_report(checks)
    if args.out:
        args.out.write_text(json.dumps([vars(item) for item in checks], indent=2), encoding="utf-8")
        print(f"\nreport written to {args.out}", file=sys.stderr)
    return 0


def check_family(
    family: str,
    matrix: FloatArray,
    presets: dict[str, dict],
    spec: dict[str, dict],
    references: dict[str, Reference],
    *,
    device: str,
) -> list[CrossCheck]:
    adapter = ADAPTERS[family](device=device)
    adapter.preflight()
    output = current_embedding_analysis_output(family, device=device)

    checks: list[CrossCheck] = []
    for label, entry in spec.items():
        reference = references.get(label)
        if reference is None:
            continue
        preset = presets[label]
        positives = adapter.embed_texts(resolve_variants(preset.get("positive"), family))
        negatives = adapter.embed_texts(resolve_variants(preset.get("negative"), family))
        weight = resolve_weight(preset["negativeWeight"], family)
        positive_scores, negative_scores, _contrast, _bounded = _contrast_vector_scores(
            matrix,
            output=output,
            positive_vectors=positives,
            negative_vectors=negatives if weight > 0 else [],
            negative_weight=max(weight, 0.0),
        )
        scores = positive_scores - weight * negative_scores
        checks.append(measure(label, family, entry, reference, scores))
    return checks


def measure(
    label: str,
    family: str,
    entry: dict,
    reference: Reference,
    scores: FloatArray,
) -> CrossCheck:
    direction = float(entry.get("direction", 1))
    oriented = scores * direction
    # The statistic is orientation-aware, but the reported sample must always be
    # the tracks this label ranks highest, whatever direction it expects.
    top = np.argsort(-scores, kind="stable")[:TOP_K]

    correlation = float(spearmanr(oriented, reference.truth).statistic)
    if reference.kind == "binary":
        truth = reference.truth
        base_rate = float(truth.mean())
        top_share = float(truth[top].mean())
        statistic = float(roc_auc_score(truth, oriented))
    else:
        # A global rank correlation drowns in ties when the reference is skewed,
        # as SONARA vocal probability is across a mostly instrumental library.
        # Asking whether a label ranks the extreme tracks first survives that.
        # A probability-like reference gets an explicit threshold instead of a
        # quantile, because its tenth percentile is still noise.
        threshold = entry.get("threshold")
        if threshold is None:
            quantile = EXTREME_QUANTILE if direction > 0 else 1.0 - EXTREME_QUANTILE
            threshold = float(np.quantile(reference.truth, quantile))
        truth = (
            (reference.truth >= threshold) if direction > 0 else (reference.truth <= threshold)
        ).astype(np.float64)
        base_rate = float(truth.mean())
        top_share = float(truth[top].mean())
        statistic = float(roc_auc_score(truth, scores))
    lift = top_share / base_rate if base_rate > 0 else float("nan")
    return CrossCheck(
        label=label,
        model=family,
        reference=reference.description,
        kind=reference.kind,
        statistic=statistic,
        spearman=correlation,
        top_share=top_share,
        base_rate=base_rate,
        lift=lift,
        verdict=verdict_for(statistic, lift),
    )


def verdict_for(statistic: float, lift: float) -> str:
    """Judge global ordering and the top of the list together.

    A label can order the whole library poorly and still be useful: what a DJ
    reads is the first screen. Voice labels here reach a fivefold lift in the
    top 100 while their AUC stays near chance, so AUC alone would reject them.
    """

    strong_lift = lift >= 3.0 if np.isfinite(lift) else False
    weak_lift = lift >= 1.5 if np.isfinite(lift) else False
    if statistic < 0.45 and not weak_lift:
        return "INVERTED"
    if statistic >= BINARY_STRONG or strong_lift:
        return "ok"
    if statistic >= BINARY_WEAK or weak_lift:
        return "weak"
    return "suspect"


def load_presets() -> list[dict]:
    """Read the vocabulary from the TypeScript module that owns it."""

    script = (
        "const ts=require('typescript');const fs=require('fs');"
        "const out=ts.transpileModule(fs.readFileSync(process.argv[1],'utf8'),"
        "{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;"
        "const m={exports:{}};new Function('module','exports',out)(m,m.exports);"
        "console.log(JSON.stringify(m.exports.textPromptPresets));"
    )
    completed = subprocess.run(
        ["node", "-e", script, str(PRESETS_TS)],
        cwd=str(REPO_ROOT / "frontend"),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def resolve_variants(variants: dict | None, family: str) -> list[str]:
    if not variants:
        return []
    return list(variants.get(family) or variants["shared"])


def resolve_weight(weight: float | dict, family: str) -> float:
    if isinstance(weight, dict):
        return float(weight[family])
    return float(weight)


def load_matrix(db_path: Path, family: str) -> tuple[FloatArray, dict[int, int]]:
    with sqlite3.connect(read_only_uri(db_path), uri=True) as connection:
        rows = connection.execute(
            f"select track_id, dim, embedding_blob from {family}_embeddings order by track_id"
        ).fetchall()
    if not rows:
        raise SystemExit(f"{db_path} has no {family} embeddings")
    dimension = rows[0][1]
    matrix = np.empty((len(rows), dimension), dtype=np.float32)
    row_of_track: dict[int, int] = {}
    for index, (track_id, dim, blob) in enumerate(rows):
        if dim != dimension:
            raise SystemExit(f"{family} embedding dimensions are mixed: {dim} != {dimension}")
        matrix[index] = np.frombuffer(blob, dtype=np.float32)
        row_of_track[track_id] = index
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.all(norms > 0.0):
        raise SystemExit("stored embeddings contain a zero vector")
    return np.ascontiguousarray(matrix / norms, dtype=np.float32), row_of_track


def load_references(
    db_path: Path,
    spec: dict[str, dict],
    row_of_track: dict[int, int],
    rows: int,
) -> dict[str, Reference]:
    sonara_fields = {
        entry["field"] for entry in spec.values() if entry.get("source") == "sonara" and "field" in entry
    }
    needs_key = any(entry.get("expr") == "key_minor" for entry in spec.values())
    needs_syncopation = any(entry.get("expr") == "syncopated" for entry in spec.values())
    genre_labels = {entry["label"] for entry in spec.values() if entry.get("source") == "maest" and "label" in entry}

    columns: dict[str, NDArray[np.float64]] = {}
    with sqlite3.connect(read_only_uri(db_path), uri=True) as connection:
        if sonara_fields or needs_key:
            selected = sorted(sonara_fields)
            names = ", ".join(["track_id", *selected] + (["detected_key_name"] if needs_key else []))
            for name in selected:
                columns[name] = np.full(rows, np.nan)
            if needs_key:
                columns["key_minor"] = np.full(rows, np.nan)
            for row in connection.execute(f"select {names} from sonara_features"):
                index = row_of_track.get(row[0])
                if index is None:
                    continue
                for offset, name in enumerate(selected, start=1):
                    if row[offset] is not None:
                        columns[name][index] = float(row[offset])
                if needs_key:
                    key_name = row[len(selected) + 1]
                    if key_name:
                        columns["key_minor"][index] = 1.0 if "minor" in key_name.lower() else 0.0
        if genre_labels or needs_syncopation:
            for name in genre_labels:
                columns[name] = np.zeros(rows)
            if needs_syncopation:
                columns["syncopated"] = np.full(rows, np.nan)
            for track_id, syncopated, payload in connection.execute(
                "select track_id, syncopated_rhythm, genres_json from maest_genres"
            ):
                index = row_of_track.get(track_id)
                if index is None:
                    continue
                if needs_syncopation and syncopated is not None:
                    columns["syncopated"][index] = float(syncopated)
                if not genre_labels:
                    continue
                present = {item["label"] for item in json.loads(payload or "[]")}
                for name in genre_labels & present:
                    columns[name][index] = 1.0

    references: dict[str, Reference] = {}
    for label, entry in spec.items():
        name = entry.get("field") or entry.get("expr") or entry.get("label")
        values = columns.get(name)
        if values is None:
            continue
        finite = np.isfinite(values)
        if finite.sum() < rows:
            # Reference coverage gaps would bias the comparison; report only full columns.
            if finite.sum() < rows * 0.9:
                print(
                    f"skipping {label}: reference {name} covers {finite.sum()}/{rows} tracks",
                    file=sys.stderr,
                )
                continue
            values = np.where(finite, values, np.nanmedian(values))
        references[label] = Reference(
            key=label,
            kind=entry["kind"],
            truth=values.astype(np.float64),
            description=f"{entry.get('source')}:{name}",
        )
    return references


def read_only_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def print_report(checks: list[CrossCheck]) -> None:
    header = (
        f"{'label':<26}{'model':<7}{'reference':<34}"
        f"{'AUC':>7}{'top100':>8}{'lib':>8}{'lift':>7}  verdict"
    )
    print(header)
    print("-" * len(header))
    for item in sorted(checks, key=lambda row: (row.label, row.model)):
        print(item.as_row())

    print()
    for model in dict.fromkeys(item.model for item in checks):
        subset = [item for item in checks if item.model == model]
        counts = {
            verdict: sum(1 for item in subset if item.verdict == verdict)
            for verdict in ("ok", "weak", "suspect", "INVERTED")
        }
        print(f"{model}: " + ", ".join(f"{name} {count}" for name, count in counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())

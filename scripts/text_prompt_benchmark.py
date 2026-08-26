"""Rank a labelled library with text prompts and report how each prompt form scores.

Preset wording, model choice and the hard-negative weight have been argued about
without evidence. This script settles those arguments on one library: it reads
stored audio embeddings and Rhythm Lab labels, embeds each prompt form with the
real text adapters, and reports ranking quality per concept.

The script only reads. It opens both databases read-only and writes nothing back.

Labels come from review sessions rather than a random sample of the library, so
the absolute numbers describe that labelled pool, not the whole collection. The
comparison between models, prompt forms and negative weights stays valid because
every configuration is scored on the same pool.
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
from dj_track_similarity.search import _contrast_vector_scores, _normalize_matrix

FloatArray = NDArray[np.float32]

DEFAULT_PROMPTS = Path(__file__).with_name("text_prompt_benchmark_prompts.json")
DEFAULT_WEIGHTS = (0.0, 0.15, 0.35, 0.5, 0.75, 1.0)
PRODUCTION_WEIGHT = 0.35
TOP_K = 20

ADAPTERS = {
    "clap": ClapEmbeddingAdapter,
    "mulan": MuqMulanEmbeddingAdapter,
}


@dataclass(frozen=True)
class LabelledConcept:
    name: str
    positive_rows: NDArray[np.int64]
    negative_rows: NDArray[np.int64]
    forms: dict[str, dict[str, list[str]]]
    control: bool


@dataclass(frozen=True)
class Measurement:
    concept: str
    model: str
    form: str
    space: str
    pooling: str
    negative_weight: float
    roc_auc: float
    average_precision: float
    precision_at_k: float
    median_library_rank: float

    def as_row(self) -> str:
        return (
            f"{self.concept:<22}{self.model:<7}{self.form:<10}{self.space:<9}"
            f"{self.pooling:<10}"
            f"{self.negative_weight:>6.2f}{self.roc_auc:>9.3f}"
            f"{self.average_precision:>9.3f}{self.precision_at_k:>9.2f}"
            f"{self.median_library_rank:>12,.0f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Library database to read.")
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("tools/rhythm-lab/database/rhythm_lab.sqlite"),
        help="Rhythm Lab labels database.",
    )
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument(
        "--models",
        default="mulan,clap",
        help="Comma-separated text embedding families to compare.",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--concepts",
        default="",
        help="Comma-separated concept names. Defaults to every concept in the prompt file.",
    )
    parser.add_argument(
        "--centered",
        action="store_true",
        help="Also score against a library-mean-centered matrix (modality gap probe).",
    )
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args(argv)

    prompts = json.loads(args.prompts.read_text(encoding="utf-8"))
    selected = [name.strip() for name in args.concepts.split(",") if name.strip()]
    if selected:
        prompts = {name: prompts[name] for name in selected}

    measurements: list[Measurement] = []
    for family in [name.strip().lower() for name in args.models.split(",") if name.strip()]:
        if family not in ADAPTERS:
            raise SystemExit(f"Unsupported text embedding family: {family}")
        started = time.perf_counter()
        matrix, row_of_track = _load_matrix(args.db, family)
        concepts = _load_concepts(args.db, args.labels, prompts, row_of_track)
        print(
            f"{family}: {matrix.shape[0]:,} vectors, "
            f"{len(concepts)} concepts, loaded in {time.perf_counter() - started:.1f}s",
            file=sys.stderr,
        )
        measurements.extend(
            _measure_family(
                family,
                matrix,
                concepts,
                device=args.device,
                centered=args.centered,
            )
        )

    _print_report(measurements)
    if args.out:
        args.out.write_text(
            json.dumps([vars(item) for item in measurements], indent=2),
            encoding="utf-8",
        )
        print(f"\nreport written to {args.out}", file=sys.stderr)
    return 0


def _measure_family(
    family: str,
    matrix: FloatArray,
    concepts: list[LabelledConcept],
    *,
    device: str,
    centered: bool,
) -> list[Measurement]:
    adapter = ADAPTERS[family](device=device)
    started = time.perf_counter()
    adapter.preflight()
    print(f"{family}: model loaded in {time.perf_counter() - started:.1f}s", file=sys.stderr)

    output = current_embedding_analysis_output(family, device=device)
    spaces: list[tuple[str, FloatArray]] = [("raw", matrix)]
    if centered:
        spaces.append(("centered", _centered(matrix)))

    measurements: list[Measurement] = []
    for concept in concepts:
        for form, bank in concept.forms.items():
            positives = adapter.embed_texts(bank["positive"])
            negatives = adapter.embed_texts(bank.get("negative", []))
            for space, scored_matrix in spaces:
                positive_scores, negative_max, _contrast, _weight = (
                    _contrast_vector_scores(
                        scored_matrix,
                        output=output,
                        positive_vectors=positives,
                        negative_vectors=negatives,
                        negative_weight=PRODUCTION_WEIGHT,
                    )
                )
                for pooling, negative_scores in _negative_poolings(
                    scored_matrix,
                    output=output,
                    negative_vectors=negatives,
                    negative_max=negative_max,
                ):
                    for weight in DEFAULT_WEIGHTS:
                        if weight and not negatives:
                            continue
                        scores = positive_scores - weight * negative_scores
                        measurements.append(
                            _measure(
                                concept,
                                family,
                                form,
                                space,
                                pooling,
                                weight,
                                scores,
                            )
                        )
    return measurements


def _negative_poolings(
    matrix: FloatArray,
    *,
    output,
    negative_vectors: list[FloatArray],
    negative_max: FloatArray,
) -> list[tuple[str, FloatArray]]:
    """Ways of turning a negative bank into one penalty per track.

    Production takes the maximum, which lets the single closest negative decide
    the whole penalty. Averaging the two closest asks two prompts to agree
    before a track is pushed down, which should be steadier when one negative is
    worded badly and noisier when the bank is small.
    """

    poolings: list[tuple[str, FloatArray]] = [("max", negative_max)]
    if len(negative_vectors) < 2:
        return poolings
    similarities = matrix @ _normalize_matrix(negative_vectors, output=output).T
    top_two = np.sort(similarities, axis=1)[:, -2:]
    poolings.append(("top2-mean", top_two.mean(axis=1).astype(np.float32)))
    return poolings


def _measure(
    concept: LabelledConcept,
    family: str,
    form: str,
    space: str,
    pooling: str,
    weight: float,
    scores: FloatArray,
) -> Measurement:
    labelled = np.concatenate([concept.positive_rows, concept.negative_rows])
    truth = np.concatenate(
        [
            np.ones(concept.positive_rows.size, dtype=np.int8),
            np.zeros(concept.negative_rows.size, dtype=np.int8),
        ]
    )
    labelled_scores = scores[labelled]
    top = np.argsort(-labelled_scores, kind="stable")[:TOP_K]

    order = np.argsort(-scores, kind="stable")
    library_rank = np.empty(scores.size, dtype=np.int64)
    library_rank[order] = np.arange(1, scores.size + 1)

    return Measurement(
        concept=concept.name,
        model=family,
        form=form,
        space=space,
        pooling=pooling,
        negative_weight=weight,
        roc_auc=float(roc_auc_score(truth, labelled_scores)),
        average_precision=float(average_precision_score(truth, labelled_scores)),
        precision_at_k=float(truth[top].mean()),
        median_library_rank=float(np.median(library_rank[concept.positive_rows])),
    )


def _load_matrix(db_path: Path, family: str) -> tuple[FloatArray, dict[int, int]]:
    with sqlite3.connect(_read_only_uri(db_path), uri=True) as connection:
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
    return _normalized(matrix), row_of_track


def _load_concepts(
    db_path: Path,
    labels_path: Path,
    prompts: dict[str, dict],
    row_of_track: dict[int, int],
) -> list[LabelledConcept]:
    with sqlite3.connect(_read_only_uri(db_path), uri=True) as connection:
        track_id_of_uuid = dict(
            connection.execute("select track_uuid, track_id from tracks")
        )
        track_id_of_path = {
            _path_key(file_path): track_id
            for track_id, file_path in connection.execute(
                "select track_id, file_path from tracks"
            )
        }
    with sqlite3.connect(_read_only_uri(labels_path), uri=True) as connection:
        label_rows = connection.execute(
            "select classifier_key, label, track_uuid, selected_path"
            " from classifier_labels"
        ).fetchall()

    # A rescan regenerates track UUIDs, so a labelled pool outlives the UUIDs
    # it was written against. The label row keeps selected_path exactly for
    # this: resolve by UUID first and fall back to the file path.
    by_key: dict[tuple[str, str], list[int]] = {}
    for classifier_key, label, track_uuid, selected_path in label_rows:
        track_id = track_id_of_uuid.get(track_uuid)
        if track_id is None and selected_path:
            track_id = track_id_of_path.get(_path_key(selected_path))
        if track_id is None:
            continue
        by_key.setdefault((classifier_key, label), []).append(track_id)

    concepts: list[LabelledConcept] = []
    for name, spec in prompts.items():
        key = spec["classifier_key"]
        positives = _rows_for(
            by_key.get((key, spec["positive_label"]), []),
            row_of_track,
        )
        negatives = _rows_for(
            by_key.get((key, spec["negative_label"]), []),
            row_of_track,
        )
        if positives.size == 0 or negatives.size == 0:
            print(
                f"skipping {name}: {positives.size} positive and "
                f"{negatives.size} negative labels resolved in this library",
                file=sys.stderr,
            )
            continue
        concepts.append(
            LabelledConcept(
                name=name,
                positive_rows=positives,
                negative_rows=negatives,
                forms=spec["forms"],
                control=bool(spec.get("control")),
            )
        )
    return concepts


def _rows_for(
    track_ids: list[int],
    row_of_track: dict[int, int],
) -> NDArray[np.int64]:
    rows = [
        row_of_track[track_id]
        for track_id in track_ids
        if track_id in row_of_track
    ]
    return np.asarray(sorted(set(rows)), dtype=np.int64)


def _path_key(file_path: str) -> str:
    return file_path.replace("\\", "/").casefold()


def _normalized(matrix: FloatArray) -> FloatArray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.all(norms > 0.0):
        raise SystemExit("stored embeddings contain a zero vector")
    return np.ascontiguousarray(matrix / norms, dtype=np.float32)


def _centered(matrix: FloatArray) -> FloatArray:
    """Remove the shared library direction that dominates cosine scores."""

    return _normalized(matrix - matrix.mean(axis=0, keepdims=True))


def _read_only_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def _print_report(measurements: list[Measurement]) -> None:
    header = (
        f"{'concept':<22}{'model':<7}{'form':<10}{'space':<9}{'pooling':<10}"
        f"{'w':>6}{'ROC-AUC':>9}{'AP':>9}{f'P@{TOP_K}':>9}{'med.rank':>12}"
    )
    print(header)
    print("-" * len(header))
    for concept in dict.fromkeys(item.concept for item in measurements):
        rows = [item for item in measurements if item.concept == concept]
        for item in sorted(
            rows,
            key=lambda row: (row.model, row.form, row.space, row.pooling, row.negative_weight),
        ):
            print(item.as_row())
        best = max(rows, key=lambda row: row.roc_auc)
        print(
            f"  best: {best.model} / {best.form} / {best.space} / {best.pooling} "
            f"/ w={best.negative_weight:.2f} "
            f"-> ROC-AUC {best.roc_auc:.3f}"
        )
        print()


if __name__ == "__main__":
    raise SystemExit(main())

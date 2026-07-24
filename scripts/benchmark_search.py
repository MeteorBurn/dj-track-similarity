from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any, TypeVar

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dj_track_similarity.analysis_model_runners import (  # noqa: E402
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (  # noqa: E402
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity.database import LibraryDatabase  # noqa: E402
from dj_track_similarity.db_storage import storage_database_paths  # noqa: E402
from dj_track_similarity.hybrid_search import build_hybrid_search_preview  # noqa: E402
from dj_track_similarity.search import SimilaritySearch  # noqa: E402
from dj_track_similarity.track_models import FileTags, ScannedFile  # noqa: E402
from dj_track_similarity.vector_index import (  # noqa: E402
    EXACT_VECTOR_BACKEND_NAME,
    HNSW_VECTOR_BACKEND_NAME,
    create_vector_backend,
)


T = TypeVar("T")
EMBEDDING_SOURCES = ("mert", "maest")
EMBEDDING_DIM = 768
DEFAULT_TRACK_COUNTS = (1000,)
DEFAULT_OUTPUT_INDENT = 2
SYNTHETIC_ANALYZED_AT = "2026-07-24T00:00:00.000000Z"


@dataclass(frozen=True)
class BenchmarkConfig:
    output: Path
    track_counts: tuple[int, ...]
    seed_count: int
    per_source: int
    random_seed: int
    vector_backend: str
    keep_db: Path | None


def run_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    vector_backend_name = create_vector_backend(config.vector_backend).backend_name
    runs = [_benchmark_track_count(config, track_count) for track_count in config.track_counts]
    return {
        "benchmark": "v7_embedding_search_benchmark",
        "schema_version": 2,
        "generated_at": _utc_timestamp(),
        "environment": _environment_summary(),
        "config": {
            "track_counts": list(config.track_counts),
            "embedding_dim": EMBEDDING_DIM,
            "seed_count": config.seed_count,
            "per_source": config.per_source,
            "random_seed": config.random_seed,
            "sources": list(EMBEDDING_SOURCES),
            "vector_backend": vector_backend_name,
            "keep_db": str(config.keep_db) if config.keep_db is not None else None,
        },
        "runs": runs,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=DEFAULT_OUTPUT_INDENT, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _benchmark_track_count(config: BenchmarkConfig, track_count: int) -> dict[str, Any]:
    if config.keep_db is None:
        with TemporaryDirectory(prefix="dj-sim-v7-search-benchmark-") as temp_dir:
            db_path = Path(temp_dir) / f"synthetic-{track_count}.sqlite"
            return _benchmark_database_path(config, track_count, db_path, kept_db=False)

    db_path = _kept_database_path(
        config.keep_db,
        track_count,
        multiple_counts=len(config.track_counts) > 1,
    )
    _prepare_kept_database_path(db_path)
    return _benchmark_database_path(config, track_count, db_path, kept_db=True)


def _benchmark_database_path(
    config: BenchmarkConfig,
    track_count: int,
    db_path: Path,
    *,
    kept_db: bool,
) -> dict[str, Any]:
    setup_seconds, db = _timed(
        lambda: _setup_synthetic_database(config, track_count, db_path)
    )
    seed_track_ids = _sample_seed_track_ids(
        track_count,
        config.seed_count,
        config.random_seed,
    )
    load_metrics = _measure_embedding_loads(db)
    exact_metrics = _measure_vector_similarity_searches(db, config, seed_track_ids)
    hybrid_metrics = _measure_hybrid_searches(db, config, seed_track_ids)
    return {
        "track_count": track_count,
        "db_path": str(db_path),
        "artifacts_path": str(db.artifacts_path),
        "kept_db": kept_db,
        "setup": {"seconds": setup_seconds},
        "seed_track_ids": seed_track_ids,
        "data": {
            "embedding_sources": list(EMBEDDING_SOURCES),
            "embedding_dim": EMBEDDING_DIM,
            "storage": "v7-core-artifacts",
            "synthetic_audio_files_created": False,
        },
        "load_embedding_matrix": load_metrics,
        "exact_similarity": exact_metrics,
        "hybrid_search": hybrid_metrics,
        "memory_rss_bytes": _memory_rss_bytes(),
    }


def _setup_synthetic_database(
    config: BenchmarkConfig,
    track_count: int,
    db_path: Path,
) -> LibraryDatabase:
    db = LibraryDatabase(db_path)
    outputs = _synthetic_outputs()
    db.register_analysis_outputs(tuple(outputs.values()))

    rng = np.random.default_rng(config.random_seed + track_count)
    mert_vectors = _normalized_random_matrix(rng, track_count, EMBEDDING_DIM)
    maest_vectors = _normalized_random_matrix(rng, track_count, EMBEDDING_DIM)
    track_targets = _insert_synthetic_tracks(db, track_count, db_path)
    _store_synthetic_embeddings(
        db,
        targets=track_targets,
        outputs=outputs,
        mert_vectors=mert_vectors,
        maest_vectors=maest_vectors,
    )
    return db


def _synthetic_outputs() -> dict[str, AnalysisOutput]:
    maest = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    )
    maest_outputs = {
        output.contract.output_kind: output
        for output in maest.active_outputs
    }
    return {
        "mert": current_embedding_analysis_output("mert"),
        "maest_analysis": maest_outputs["analysis"],
        "maest": maest_outputs["embedding"],
    }


def _insert_synthetic_tracks(
    db: LibraryDatabase,
    track_count: int,
    db_path: Path,
) -> tuple[AnalysisTarget, ...]:
    targets: list[AnalysisTarget] = []
    synthetic_root = db_path.parent / "synthetic-audio"
    for index in range(track_count):
        mutation = db.upsert_scanned_track(
            file=ScannedFile(
                file_path=str(synthetic_root / f"track-{index:06d}.wav"),
                file_size_bytes=1_024 + index,
                file_modified_ns=1_000_000_000 + index,
                audio_format="wav",
                audio_codec="pcm_s16le",
                sample_rate_hz=44_100,
                channel_count=2,
                bit_rate_bps=1_411_200,
                audio_duration_seconds=180.0 + float(index % 240),
            ),
            tags=FileTags(
                artist=f"Synthetic Artist {index % 97:02d}",
                title=f"Synthetic Track {index:06d}",
                album=f"Synthetic Album {index % 31:02d}",
                tag_bpm=90.0 + float(index % 70),
                tag_key=_camelot_key(index),
                genres=("Synthetic",),
            ),
            scanned_at=SYNTHETIC_ANALYZED_AT,
        )
        identity = mutation.identity
        targets.append(
            AnalysisTarget(
                catalog_uuid=identity.catalog_uuid,
                track_id=identity.track_id,
                track_uuid=identity.track_uuid,
                content_generation=identity.content_generation,
            )
        )
    return tuple(targets)


def _store_synthetic_embeddings(
    db: LibraryDatabase,
    *,
    targets: Sequence[AnalysisTarget],
    outputs: dict[str, AnalysisOutput],
    mert_vectors: np.ndarray,
    maest_vectors: np.ndarray,
) -> None:
    mert_output = outputs["mert"]
    maest_analysis_output_value = outputs["maest_analysis"]
    maest_embedding_output_value = outputs["maest"]
    mert_writes = tuple(
        EmbeddingWrite(
            target=target,
            output=EmbeddingOutput(
                contract=mert_output.contract,
                vector=mert_vectors[index],
                analyzed_at=SYNTHETIC_ANALYZED_AT,
            ),
        )
        for index, target in enumerate(targets)
    )
    maest_writes = tuple(
        MaestWrite(
            target=target,
            analysis_contract=maest_analysis_output_value.contract,
            genres=(MaestGenreScore(label="Synthetic", score=1.0),),
            syncopated_rhythm=False,
            analyzed_at=SYNTHETIC_ANALYZED_AT,
            embedding=EmbeddingOutput(
                contract=maest_embedding_output_value.contract,
                vector=maest_vectors[index],
                analyzed_at=SYNTHETIC_ANALYZED_AT,
            ),
        )
        for index, target in enumerate(targets)
    )
    mert_results = db.save_embedding_results(mert_writes)
    maest_results = db.save_maest_results(maest_writes)
    failed = [result.error for result in (*mert_results, *maest_results) if not result.ok]
    if failed:
        raise RuntimeError(f"Synthetic v7 analysis writes failed: {failed[0]}")


def _measure_embedding_loads(db: LibraryDatabase) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for source in EMBEDDING_SOURCES:
        output = db.active_analysis_output(source, "embedding")
        if output is None:
            raise RuntimeError(f"Synthetic benchmark has no active {source} output")
        seconds, rows = _timed(
            lambda output=output: db.load_analysis_vectors(output)
        )
        metrics[source] = {
            "seconds": seconds,
            "tracks": len(rows),
            "dim": int(output.contract.dim or 0),
            "contract_hash": output.contract_hash,
        }
    return metrics


def _measure_vector_similarity_searches(
    db: LibraryDatabase,
    config: BenchmarkConfig,
    seed_track_ids: Sequence[int],
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for source in EMBEDDING_SOURCES:
        output = _active_embedding_output(db, source)
        vector_backend = create_vector_backend(config.vector_backend)
        searcher = SimilaritySearch(
            db,
            source,
            analysis_output=output,
            vector_backend=vector_backend,
        )
        source_metrics = {
            "backend": vector_backend.backend_name,
            **_measure_seed_operation(
                seed_track_ids,
                lambda seed_track_id, searcher=searcher: searcher.search(
                    searcher.resolve_targets((seed_track_id,)),
                    limit=config.per_source,
                ),
            ),
        }
        if vector_backend.backend_name != EXACT_VECTOR_BACKEND_NAME:
            source_metrics["recall_at_k"] = _measure_recall_at_k(
                db,
                source,
                config,
                seed_track_ids,
            )
        metrics[source] = source_metrics
    return metrics


def _measure_recall_at_k(
    db: LibraryDatabase,
    source: str,
    config: BenchmarkConfig,
    seed_track_ids: Sequence[int],
) -> dict[str, Any]:
    recalls: list[float] = []
    output = _active_embedding_output(db, source)
    exact_searcher = SimilaritySearch(
        db,
        source,
        analysis_output=output,
    )
    backend_searcher = SimilaritySearch(
        db,
        source,
        analysis_output=output,
        vector_backend=create_vector_backend(config.vector_backend),
    )
    for seed_track_id in seed_track_ids:
        targets = exact_searcher.resolve_targets((seed_track_id,))
        exact_results = exact_searcher.search(targets, limit=config.per_source)
        backend_results = backend_searcher.search(targets, limit=config.per_source)
        exact_ids = [result.target.track_id for result in exact_results]
        if not exact_ids:
            continue
        backend_ids = {result.target.track_id for result in backend_results}
        recalls.append(len(backend_ids.intersection(exact_ids)) / len(exact_ids))
    return {
        "k": config.per_source,
        "samples": len(recalls),
        "mean": (sum(recalls) / len(recalls)) if recalls else None,
        "min": min(recalls) if recalls else None,
    }


def _measure_hybrid_searches(
    db: LibraryDatabase,
    config: BenchmarkConfig,
    seed_track_ids: Sequence[int],
) -> dict[str, Any]:
    analysis_outputs = {
        source: _active_embedding_output(db, source)
        for source in EMBEDDING_SOURCES
    }
    metrics = _measure_seed_operation(
        seed_track_ids,
        lambda seed_track_id: build_hybrid_search_preview(
            db,
            seed_track_ids=(seed_track_id,),
            analysis_outputs=analysis_outputs,
            sources=EMBEDDING_SOURCES,
            per_source=config.per_source,
            limit=min(config.per_source, 25),
            random_seed=config.random_seed,
        ).results,
    )
    return {"sources": list(EMBEDDING_SOURCES), **metrics}


def _active_embedding_output(
    db: LibraryDatabase,
    source: str,
) -> AnalysisOutput:
    output = db.active_analysis_output(source, "embedding")
    if output is None:
        raise RuntimeError(
            f"Synthetic benchmark has no active {source} output"
        )
    return output


def _measure_seed_operation(
    seed_track_ids: Sequence[int],
    operation: Callable[[int], Sequence[Any]],
) -> dict[str, Any]:
    durations: list[float] = []
    result_counts: list[int] = []
    for seed_track_id in seed_track_ids:
        seconds, results = _timed(lambda seed_track_id=seed_track_id: operation(seed_track_id))
        durations.append(seconds)
        result_counts.append(len(results))
    return {
        "seed_count": len(seed_track_ids),
        "total_seconds": sum(durations),
        "p50_seconds": _percentile(durations, 50.0),
        "p95_seconds": _percentile(durations, 95.0),
        "min_result_count": min(result_counts) if result_counts else 0,
        "max_result_count": max(result_counts) if result_counts else 0,
    }


def _sample_seed_track_ids(
    track_count: int,
    seed_count: int,
    random_seed: int,
) -> list[int]:
    selected_count = min(track_count, seed_count)
    rng = np.random.default_rng(random_seed + track_count)
    return sorted(int(value) + 1 for value in rng.choice(track_count, size=selected_count, replace=False))


def _normalized_random_matrix(
    rng: np.random.Generator,
    rows: int,
    dim: int,
) -> np.ndarray:
    matrix = rng.standard_normal((rows, dim), dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise RuntimeError("Synthetic embedding generation produced an invalid vector")
    return (matrix / norms).astype(np.float32)


def _camelot_key(index: int) -> str:
    return f"{(index % 12) + 1}{'A' if index % 2 == 0 else 'B'}"


def _timed(operation: Callable[[], T]) -> tuple[float, T]:
    start = time.perf_counter()
    result = operation()
    return time.perf_counter() - start, result


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    lower_weight = upper - rank
    upper_weight = rank - lower
    return ordered[lower] * lower_weight + ordered[upper] * upper_weight


def _environment_summary() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "numpy": np.__version__,
        "pid": os.getpid(),
        "memory_rss_bytes": _memory_rss_bytes(),
    }


def _memory_rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return _resource_rss_bytes()
    process = psutil.Process(os.getpid())
    return int(process.memory_info().rss)


def _resource_rss_bytes() -> int | None:
    try:
        import resource  # type: ignore[import-not-found]
    except ImportError:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = int(usage.ru_maxrss)
    if sys.platform == "darwin":
        return rss
    return rss * 1024


def _kept_database_path(path: Path, track_count: int, *, multiple_counts: bool) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if not multiple_counts:
        return resolved
    suffix = resolved.suffix or ".sqlite"
    return resolved.with_name(f"{resolved.stem}-{track_count}{suffix}")


def _prepare_kept_database_path(path: Path) -> None:
    storage_paths = storage_database_paths(path)
    existing = [
        candidate
        for candidate in (path, storage_paths.artifacts, storage_paths.evaluation)
        if candidate.exists()
    ]
    if existing:
        raise FileExistsError(f"Kept benchmark database file already exists: {existing[0]}")
    path.parent.mkdir(parents=True, exist_ok=True)


def _parse_args(argv: Sequence[str] | None = None) -> BenchmarkConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Create a synthetic greenfield v7 Core+Artifacts bundle and benchmark "
            "MERT/MAEST vector and Hybrid search operations."
        ),
    )
    parser.add_argument("--output", required=True, type=Path, help="Path to write the JSON benchmark report.")
    parser.add_argument(
        "--track-count",
        action="append",
        type=_track_count_value,
        help="Synthetic track count. May be repeated. Defaults to 1000.",
    )
    parser.add_argument(
        "--track-counts",
        help="Comma-separated synthetic track counts, for example 1000,10000. Do not combine with --track-count.",
    )
    parser.add_argument("--seed-count", default=20, type=_positive_int, help="Number of sampled seed tracks per run. Defaults to 20.")
    parser.add_argument("--per-source", default=30, type=_positive_int, help="Candidate limit per source. Defaults to 30.")
    parser.add_argument("--random-seed", default=123, type=int, help="Deterministic random seed. Defaults to 123.")
    parser.add_argument(
        "--vector-backend",
        choices=("exact", "hnsw"),
        default="exact",
        help="Vector backend for direct similarity timing: exact or hnsw. Defaults to exact.",
    )
    parser.add_argument("--keep-db", type=Path, help="Optional path for keeping the synthetic Core+Artifacts bundle for debugging.")
    args = parser.parse_args(argv)
    config = BenchmarkConfig(
        output=args.output.expanduser().resolve(strict=False),
        track_counts=_parse_track_counts(args.track_count, args.track_counts),
        seed_count=args.seed_count,
        per_source=args.per_source,
        random_seed=args.random_seed,
        vector_backend=_vector_backend_name(args.vector_backend),
        keep_db=args.keep_db.expanduser().resolve(strict=False) if args.keep_db is not None else None,
    )
    output_conflict = _conflicting_kept_database_path(config)
    if output_conflict is not None:
        parser.error(f"--output must not point to a kept synthetic database path: {output_conflict}")
    return config


def _vector_backend_name(value: str) -> str:
    return EXACT_VECTOR_BACKEND_NAME if value == "exact" else HNSW_VECTOR_BACKEND_NAME


def _conflicting_kept_database_path(config: BenchmarkConfig) -> Path | None:
    if config.keep_db is None:
        return None
    multiple_counts = len(config.track_counts) > 1
    for track_count in config.track_counts:
        kept_database_path = _kept_database_path(
            config.keep_db,
            track_count,
            multiple_counts=multiple_counts,
        )
        if config.output == kept_database_path:
            return kept_database_path
    return None


def _parse_track_counts(track_count: Sequence[int] | None, track_counts: str | None) -> tuple[int, ...]:
    if track_count and track_counts:
        raise ValueError("Use either --track-count or --track-counts, not both")
    if track_count:
        return tuple(dict.fromkeys(track_count))
    if track_counts:
        values = [_track_count_value(part.strip()) for part in track_counts.split(",") if part.strip()]
        if not values:
            raise ValueError("--track-counts must include at least one integer")
        return tuple(dict.fromkeys(values))
    return DEFAULT_TRACK_COUNTS


def _track_count_value(value: object) -> int:
    clean_value = _positive_int(value)
    if clean_value < 2:
        raise argparse.ArgumentTypeError("track count must be at least 2")
    return clean_value


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise argparse.ArgumentTypeError("value must be a positive integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("value must be a positive integer") from error
    if clean_value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return clean_value


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = _parse_args(argv)
        report = run_benchmark(config)
        write_report(report, config.output)
    except Exception as error:
        print(f"benchmark_search failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote benchmark report: {config.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

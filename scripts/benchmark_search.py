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

from dj_track_similarity.database import LibraryDatabase  # noqa: E402
from dj_track_similarity.db_search_fts import rebuild_track_search_fts  # noqa: E402
from dj_track_similarity.evaluation.score_profiles import DEFAULT_LIMITATIONS, PROFILE_KIND, WEIGHT_KIND, ScoreProfile  # noqa: E402
from dj_track_similarity.evaluation.weighted_candidates import build_weighted_candidate_pool  # noqa: E402
from dj_track_similarity.hybrid_search import build_hybrid_search_preview  # noqa: E402
from dj_track_similarity.metadata_payload import metadata_to_json  # noqa: E402
from dj_track_similarity.search import SimilaritySearch  # noqa: E402


T = TypeVar("T")
EMBEDDING_SOURCES = ("mert", "maest")
DEFAULT_TRACK_COUNTS = (1000,)
DEFAULT_OUTPUT_INDENT = 2


@dataclass(frozen=True)
class BenchmarkConfig:
    output: Path
    track_counts: tuple[int, ...]
    embedding_dim: int
    classifier_profiles: int
    seed_count: int
    per_source: int
    random_seed: int
    keep_db: Path | None
    skip_sonara: bool

    @property
    def candidate_sources(self) -> tuple[str, ...]:
        if self.skip_sonara:
            return EMBEDDING_SOURCES
        return (*EMBEDDING_SOURCES, "sonara")


def run_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    runs = [_benchmark_track_count(config, track_count) for track_count in config.track_counts]
    return {
        "benchmark": "exact_search_baseline",
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "environment": _environment_summary(),
        "config": {
            "track_counts": list(config.track_counts),
            "embedding_dim": config.embedding_dim,
            "classifier_profiles": config.classifier_profiles,
            "seed_count": config.seed_count,
            "per_source": config.per_source,
            "random_seed": config.random_seed,
            "sources": list(config.candidate_sources),
            "skip_sonara": config.skip_sonara,
            "keep_db": str(config.keep_db) if config.keep_db is not None else None,
        },
        "runs": runs,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=DEFAULT_OUTPUT_INDENT, sort_keys=True) + "\n", encoding="utf-8")


def _benchmark_track_count(config: BenchmarkConfig, track_count: int) -> dict[str, Any]:
    if config.keep_db is None:
        with TemporaryDirectory(prefix="dj-sim-search-benchmark-") as temp_dir:
            db_path = Path(temp_dir) / f"synthetic-{track_count}.sqlite"
            return _benchmark_database_path(config, track_count, db_path, kept_db=False)

    db_path = _kept_database_path(config.keep_db, track_count, multiple_counts=len(config.track_counts) > 1)
    _prepare_kept_database_path(db_path)
    return _benchmark_database_path(config, track_count, db_path, kept_db=True)


def _benchmark_database_path(config: BenchmarkConfig, track_count: int, db_path: Path, *, kept_db: bool) -> dict[str, Any]:
    setup_seconds, db = _timed(lambda: _setup_synthetic_database(config, track_count, db_path))
    seed_track_ids = _sample_seed_track_ids(track_count, config.seed_count, config.random_seed)
    load_metrics = _measure_embedding_loads(db)
    exact_metrics = _measure_exact_similarity_searches(db, seed_track_ids, config.per_source)
    weighted_metrics = _measure_weighted_candidate_pools(db, config, seed_track_ids)
    hybrid_metrics = _measure_hybrid_searches(db, config, seed_track_ids)
    return {
        "track_count": track_count,
        "db_path": str(db_path),
        "kept_db": kept_db,
        "setup": {"seconds": setup_seconds},
        "seed_track_ids": seed_track_ids,
        "data": {
            "embedding_sources": list(EMBEDDING_SOURCES),
            "candidate_sources": list(config.candidate_sources),
            "classifier_profiles": config.classifier_profiles,
            "sonara_enabled": not config.skip_sonara,
        },
        "load_embedding_matrix": load_metrics,
        "exact_similarity": exact_metrics,
        "weighted_candidates": weighted_metrics,
        "hybrid_search": hybrid_metrics,
        "memory_rss_bytes": _memory_rss_bytes(),
    }


def _setup_synthetic_database(config: BenchmarkConfig, track_count: int, db_path: Path) -> LibraryDatabase:
    db = LibraryDatabase(db_path)
    rng = np.random.default_rng(config.random_seed + track_count)
    mert_vectors = _normalized_random_matrix(rng, track_count, config.embedding_dim)
    maest_vectors = _normalized_random_matrix(rng, track_count, config.embedding_dim)
    track_ids = _insert_synthetic_tracks(db, track_count, config, mert_vectors, maest_vectors)
    if len(track_ids) != track_count:
        raise RuntimeError(f"Expected {track_count} synthetic tracks, inserted {len(track_ids)}")
    return db


def _insert_synthetic_tracks(
    db: LibraryDatabase,
    track_count: int,
    config: BenchmarkConfig,
    mert_vectors: np.ndarray,
    maest_vectors: np.ndarray,
) -> list[int]:
    track_ids: list[int] = []
    with db._write_lock, db.connect() as connection:  # noqa: SLF001
        for index in range(track_count):
            metadata = _synthetic_metadata(index, include_sonara=not config.skip_sonara)
            features = metadata.get("sonara_features", {})
            cursor = connection.execute(
                """
                INSERT INTO tracks (
                    path, size, mtime, artist, title, album, bpm, musical_key,
                    energy, duration, has_sonara_analysis, has_maest_embedding,
                    has_mert_embedding, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
                """,
                (
                    f"synthetic://benchmark/track-{index:06d}.wav",
                    1024 + index,
                    float(index + 1),
                    f"Synthetic Artist {index % 97:02d}",
                    f"Synthetic Track {index:06d}",
                    f"Synthetic Album {index % 31:02d}",
                    _feature_number(features, "bpm", fallback=120.0),
                    str(features.get("key", _camelot_key(index))),
                    _feature_number(features, "energy", fallback=0.5),
                    180.0 + float(index % 240),
                    0 if config.skip_sonara else 1,
                    metadata_to_json(metadata, sort_keys=True),
                ),
            )
            track_ids.append(int(cursor.lastrowid))

        _insert_embeddings(connection, track_ids, "mert", "synthetic-mert", mert_vectors)
        _insert_embeddings(connection, track_ids, "maest", "synthetic-maest", maest_vectors)
        _insert_classifier_scores(connection, track_ids, config.classifier_profiles)
        rebuild_track_search_fts(connection)
    return track_ids


def _insert_embeddings(
    connection: Any,
    track_ids: Sequence[int],
    embedding_key: str,
    model_name: str,
    vectors: np.ndarray,
) -> None:
    rows = [
        (track_id, embedding_key, model_name, int(vectors.shape[1]), vectors[index].astype(np.float32).tobytes())
        for index, track_id in enumerate(track_ids)
    ]
    connection.executemany(
        """
        INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_classifier_scores(connection: Any, track_ids: Sequence[int], classifier_profiles: int) -> None:
    if classifier_profiles <= 0:
        return
    rows = []
    for profile_index in range(classifier_profiles):
        classifier = f"synthetic_profile_{profile_index + 1:02d}"
        for track_id in track_ids:
            score = ((track_id * (profile_index + 3)) % 1000) / 999.0
            label = "positive" if score >= 0.5 else "negative"
            probabilities = {"negative": 1.0 - score, "positive": score}
            rows.append(
                (
                    track_id,
                    classifier,
                    score,
                    label,
                    max(score, 1.0 - score),
                    metadata_to_json(probabilities, sort_keys=True),
                    "synthetic_combined",
                    "synthetic-benchmark",
                ),
            )
    connection.executemany(
        """
        INSERT INTO track_classifier_scores (
            track_id, classifier, score, label, confidence,
            probabilities_json, feature_set, model_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _measure_embedding_loads(db: LibraryDatabase) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for source in EMBEDDING_SOURCES:
        seconds, loaded = _timed(lambda source=source: db.load_embedding_matrix(source))
        tracks, matrix = loaded
        metrics[source] = {
            "seconds": seconds,
            "tracks": len(tracks),
            "dim": int(matrix.shape[1]) if matrix.size else 0,
        }
    return metrics


def _measure_exact_similarity_searches(db: LibraryDatabase, seed_track_ids: Sequence[int], per_source: int) -> dict[str, dict[str, Any]]:
    return {
        source: _measure_seed_operation(
            seed_track_ids,
            lambda seed_track_id, source=source: SimilaritySearch(db, embedding_key=source).search([seed_track_id], limit=per_source),
        )
        for source in EMBEDDING_SOURCES
    }


def _measure_weighted_candidate_pools(db: LibraryDatabase, config: BenchmarkConfig, seed_track_ids: Sequence[int]) -> dict[str, Any]:
    profile = _score_profile(config.candidate_sources)
    metrics = _measure_seed_operation(
        seed_track_ids,
        lambda seed_track_id: build_weighted_candidate_pool(
            db,
            [seed_track_id],
            profile,
            config.candidate_sources,
            config.per_source,
            config.random_seed,
            record_session=False,
        ).rows,
    )
    return {"sources": list(config.candidate_sources), **metrics}


def _measure_hybrid_searches(db: LibraryDatabase, config: BenchmarkConfig, seed_track_ids: Sequence[int]) -> dict[str, Any]:
    metrics = _measure_seed_operation(
        seed_track_ids,
        lambda seed_track_id: build_hybrid_search_preview(
            db,
            seed_track_ids=[seed_track_id],
            sources=config.candidate_sources,
            per_source=config.per_source,
            limit=min(config.per_source, 25),
            random_seed=config.random_seed,
        ).results,
    )
    return {"sources": list(config.candidate_sources), **metrics}


def _measure_seed_operation(seed_track_ids: Sequence[int], operation: Callable[[int], Sequence[Any]]) -> dict[str, Any]:
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


def _score_profile(sources: Sequence[str]) -> ScoreProfile:
    if not sources:
        raise ValueError("At least one benchmark source is required")
    weight = 1.0 / len(sources)
    return ScoreProfile(
        name="synthetic_exact_baseline",
        profile_kind=PROFILE_KIND,
        weight_kind=WEIGHT_KIND,
        sources=list(sources),
        weights={source: weight for source in sources},
        created_at="1970-01-01T00:00:00+00:00",
        source_report_summary={"source": "scripts/benchmark_search.py", "synthetic": True},
        limitations=list(DEFAULT_LIMITATIONS),
    )


def _sample_seed_track_ids(track_count: int, seed_count: int, random_seed: int) -> list[int]:
    clean_seed_count = min(seed_count, track_count)
    rng = np.random.default_rng(random_seed + 17)
    sampled = rng.choice(np.arange(1, track_count + 1), size=clean_seed_count, replace=False)
    return [int(track_id) for track_id in sorted(sampled.tolist())]


def _normalized_random_matrix(rng: np.random.Generator, rows: int, dim: int) -> np.ndarray:
    matrix = rng.normal(size=(rows, dim)).astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise RuntimeError("Synthetic embedding generation produced an invalid vector")
    return (matrix / norms).astype(np.float32)


def _synthetic_metadata(index: int, *, include_sonara: bool) -> dict[str, object]:
    metadata: dict[str, object] = {
        "artist": f"Synthetic Artist {index % 97:02d}",
        "title": f"Synthetic Track {index:06d}",
        "album": f"Synthetic Album {index % 31:02d}",
    }
    if not include_sonara:
        return metadata
    metadata["sonara_model"] = "synthetic-sonara"
    metadata["sonara_features"] = _synthetic_sonara_features(index)
    return metadata


def _synthetic_sonara_features(index: int) -> dict[str, object]:
    cycle = float(index % 100) / 99.0
    bpm = 90.0 + float(index % 70)
    return {
        "energy": cycle,
        "danceability": float(((index * 7) % 100) / 99.0),
        "valence": float(((index * 11) % 100) / 99.0),
        "acousticness": float(1.0 - cycle),
        "loudness_lufs": -20.0 + 14.0 * cycle,
        "dynamic_range_db": 4.0 + float(index % 13),
        "onset_density": 0.5 + float(index % 25) / 10.0,
        "rms_mean": 0.05 + 0.45 * cycle,
        "rms_max": 0.2 + 0.75 * cycle,
        "mfcc_mean": [float(math.sin(index + offset)) for offset in range(6)],
        "spectral_centroid_mean": 800.0 + float((index * 37) % 4200),
        "spectral_bandwidth_mean": 900.0 + float((index * 29) % 3600),
        "spectral_rolloff_mean": 1500.0 + float((index * 41) % 6200),
        "spectral_flatness_mean": float(((index * 13) % 100) / 1000.0),
        "spectral_contrast_mean": [float(((index + offset * 17) % 60) / 10.0) for offset in range(4)],
        "zero_crossing_rate": float(((index * 19) % 100) / 1000.0),
        "bpm": bpm,
        "key_confidence": float(0.4 + ((index * 5) % 60) / 100.0),
        "chord_change_rate": float(((index * 3) % 40) / 10.0),
        "dissonance": float(((index * 23) % 100) / 99.0),
        "chroma_mean": [float(((index + offset * 11) % 100) / 99.0) for offset in range(12)],
        "key": _camelot_key(index),
        "predominant_chord": _predominant_chord(index),
    }


def _feature_number(features: object, key: str, *, fallback: float) -> float:
    if not isinstance(features, dict):
        return fallback
    value = features.get(key)
    if isinstance(value, bool) or value is None:
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return number


def _camelot_key(index: int) -> str:
    return f"{(index % 12) + 1}{'A' if index % 2 == 0 else 'B'}"


def _predominant_chord(index: int) -> str:
    chords = ("Am", "C", "Dm", "F", "G", "Em")
    return chords[index % len(chords)]


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
    if path.exists():
        raise FileExistsError(f"Kept benchmark database already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def _parse_args(argv: Sequence[str] | None = None) -> BenchmarkConfig:
    parser = argparse.ArgumentParser(
        description="Create a synthetic v4 SQLite library and benchmark exact search baseline operations.",
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
    parser.add_argument("--embedding-dim", default=64, type=_positive_int, help="Synthetic embedding dimension. Defaults to 64.")
    parser.add_argument("--classifier-profiles", default=0, type=_non_negative_int, help="Synthetic classifier score profiles to populate. Defaults to 0.")
    parser.add_argument("--seed-count", default=20, type=_positive_int, help="Number of sampled seed tracks per run. Defaults to 20.")
    parser.add_argument("--per-source", default=30, type=_positive_int, help="Candidate limit per source. Defaults to 30.")
    parser.add_argument("--random-seed", default=123, type=int, help="Deterministic random seed. Defaults to 123.")
    parser.add_argument("--keep-db", type=Path, help="Optional path for keeping the synthetic database for debugging.")
    parser.add_argument("--skip-sonara", action="store_true", help="Skip synthetic SONARA payloads and SONARA source measurements.")
    args = parser.parse_args(argv)
    config = BenchmarkConfig(
        output=args.output.expanduser().resolve(strict=False),
        track_counts=_parse_track_counts(args.track_count, args.track_counts),
        embedding_dim=args.embedding_dim,
        classifier_profiles=args.classifier_profiles,
        seed_count=args.seed_count,
        per_source=args.per_source,
        random_seed=args.random_seed,
        keep_db=args.keep_db.expanduser().resolve(strict=False) if args.keep_db is not None else None,
        skip_sonara=bool(args.skip_sonara),
    )
    output_conflict = _conflicting_kept_database_path(config)
    if output_conflict is not None:
        parser.error(f"--output must not point to a kept synthetic database path: {output_conflict}")
    return config


def _conflicting_kept_database_path(config: BenchmarkConfig) -> Path | None:
    if config.keep_db is None:
        return None
    multiple_counts = len(config.track_counts) > 1
    for track_count in config.track_counts:
        kept_database_path = _kept_database_path(config.keep_db, track_count, multiple_counts=multiple_counts)
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


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("value must be a non-negative integer") from error
    if clean_value < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
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

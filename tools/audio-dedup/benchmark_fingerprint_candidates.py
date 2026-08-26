from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import time

import numpy as np

from audio_dedup import core
from audio_dedup.fingerprints import (
    FingerprintSketch,
    fingerprint_candidate_pairs,
    fingerprint_sketch,
)


def run_benchmark(
    *,
    group_count: int = 32,
    distractor_count: int = 128,
    seed: int = 20260826,
) -> dict[str, object]:
    if group_count <= 0 or distractor_count < 0:
        raise ValueError(
            "group_count must be positive and distractor_count must not be negative"
        )
    random = np.random.default_rng(seed)
    tracks: list[core.TrackRecord] = []
    sketches: list[FingerprintSketch] = []
    duplicate_pairs: set[tuple[int, int]] = set()
    next_track_id = 1

    for _ in range(group_count):
        words = random.integers(0, 2**32, size=720, dtype=np.uint32)
        duplicate_words = words.copy()
        changed_words = random.choice(len(duplicate_words), size=12, replace=False)
        duplicate_words[changed_words] ^= np.uint32(1)
        center = random.standard_normal(96, dtype=np.float32)
        left_id, right_id = next_track_id, next_track_id + 1
        tracks.extend(
            [
                _benchmark_track(
                    left_id, center + random.normal(0.0, 0.02, 96).astype(np.float32)
                ),
                _benchmark_track(
                    right_id, center + random.normal(0.0, 0.02, 96).astype(np.float32)
                ),
            ]
        )
        sketches.extend(
            [
                fingerprint_sketch(left_id, 1, _as_base64(words)),
                fingerprint_sketch(right_id, 1, _as_base64(duplicate_words)),
            ]
        )
        duplicate_pairs.add((left_id, right_id))
        next_track_id += 2

    for _ in range(distractor_count):
        words = random.integers(0, 2**32, size=720, dtype=np.uint32)
        vector = random.standard_normal(96, dtype=np.float32)
        tracks.append(_benchmark_track(next_track_id, vector))
        sketches.append(fingerprint_sketch(next_track_id, 1, _as_base64(words)))
        next_track_id += 1

    config = core.resolve_preset("safe", min_score=None)
    source_config = core.resolve_source_config(sources=("mert",), weights={"mert": 1.0})
    fingerprint_started = time.perf_counter()
    fingerprint_pairs = fingerprint_candidate_pairs(sketches)
    fingerprint_elapsed = (time.perf_counter() - fingerprint_started) * 1000.0
    embedding_started = time.perf_counter()
    embedding_pairs = core._signature_candidate_pairs(tracks, config, source_config)
    embedding_elapsed = (time.perf_counter() - embedding_started) * 1000.0

    fingerprint_then_embedding = set(fingerprint_pairs)
    fingerprint_then_embedding.update(embedding_pairs)
    embedding_then_fingerprint = set(embedding_pairs)
    embedding_then_fingerprint.update(fingerprint_pairs)
    return {
        "benchmark": "synthetic-audio-dedup-candidate-retrieval-v1",
        "seed": seed,
        "track_count": len(tracks),
        "known_duplicate_pair_count": len(duplicate_pairs),
        "strategies": {
            "fingerprint_lsh": _strategy_result(
                fingerprint_pairs,
                duplicate_pairs,
                fingerprint_elapsed,
            ),
            "embedding_lsh": _strategy_result(
                embedding_pairs,
                duplicate_pairs,
                embedding_elapsed,
            ),
            "union": _strategy_result(
                fingerprint_then_embedding,
                duplicate_pairs,
                fingerprint_elapsed + embedding_elapsed,
            ),
        },
        "ordering": {
            "fingerprint_then_embedding_pair_count": len(fingerprint_then_embedding),
            "embedding_then_fingerprint_pair_count": len(embedding_then_fingerprint),
            "candidate_sets_equal": fingerprint_then_embedding
            == embedding_then_fingerprint,
            "note": "Independent candidate retrieval is combined by set union, so order affects only scheduling latency, not recall or the pair set.",
        },
        "limits": {
            "exact_match": "The synthetic fixture uses known duplicate groups as an oracle; it does not estimate real-library precision.",
            "next_step": "Run Audio Dedup in report-only mode and listen to the fingerprint-review pairs before changing thresholds.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare synthetic fingerprint and MERT candidate retrieval for Audio Dedup."
    )
    parser.add_argument("--groups", type=int, default=32)
    parser.add_argument("--distractors", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = run_benchmark(
        group_count=args.groups,
        distractor_count=args.distractors,
        seed=args.seed,
    )
    rendered = json.dumps(result, indent=2)
    if args.out is None:
        print(rendered)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
        print(args.out)
    return 0


def _benchmark_track(track_id: int, embedding: np.ndarray) -> core.TrackRecord:
    return core.TrackRecord(
        track_id=track_id,
        path=f"C:/synthetic/{track_id}.flac",
        size=1_000_000,
        mtime=0.0,
        artist=None,
        title=None,
        album=None,
        bpm=None,
        musical_key=None,
        duration=180.0,
        metadata={},
        embeddings={"mert": embedding},
    )


def _as_base64(words: np.ndarray) -> str:
    return base64.b64encode(words.astype("<u4", copy=False).tobytes()).decode("ascii")


def _strategy_result(
    candidates: set[tuple[int, int]],
    duplicate_pairs: set[tuple[int, int]],
    elapsed_ms: float,
) -> dict[str, float | int]:
    retrieved_duplicates = len(candidates & duplicate_pairs)
    return {
        "candidate_pair_count": len(candidates),
        "known_duplicate_pairs_retrieved": retrieved_duplicates,
        "duplicate_retrieval_recall": round(
            retrieved_duplicates / len(duplicate_pairs), 6
        ),
        "oracle_precision_proxy": round(retrieved_duplicates / len(candidates), 6)
        if candidates
        else 0.0,
        "retrieval_elapsed_ms": round(elapsed_ms, 3),
    }


if __name__ == "__main__":
    raise SystemExit(main())

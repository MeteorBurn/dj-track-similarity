from __future__ import annotations

import base64
from dataclasses import dataclass
import sqlite3
from typing import Callable, Mapping

import numpy as np

from dj_track_similarity.analysis_models import FingerprintOutput


FINGERPRINT_LSH_BANDS = 8
FINGERPRINT_LSH_BITS_PER_BAND = 12
FINGERPRINT_LSH_PROJECTIONS = FINGERPRINT_LSH_BANDS * FINGERPRINT_LSH_BITS_PER_BAND
FINGERPRINT_LSH_BANDS_PER_KEY = 2
FINGERPRINT_LSH_KEYS = FINGERPRINT_LSH_BANDS // FINGERPRINT_LSH_BANDS_PER_KEY
FINGERPRINT_DESCRIPTOR_SEGMENTS = 4
FINGERPRINT_LSH_MAX_BUCKET_TRACKS = 512


@dataclass(frozen=True)
class FingerprintSketch:
    """Small, version-bound fingerprint representation used only for candidate retrieval."""

    track_id: int
    version: int
    descriptor: np.ndarray


@dataclass(frozen=True)
class FingerprintLoadResult:
    sketches: tuple[FingerprintSketch, ...]
    rejected_rows: int


def fingerprint_sketch(
    track_id: int,
    version: int,
    fingerprint_base64: str,
) -> FingerprintSketch:
    """Decode a stored SONARA fingerprint into a compact, non-reversible LSH descriptor."""
    try:
        payload = base64.b64decode(fingerprint_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("fingerprint storage value is not valid base64") from error
    if not payload or len(payload) % 4:
        raise ValueError("fingerprint storage value has no complete 32-bit frames")
    if len(payload) // 4 < FINGERPRINT_DESCRIPTOR_SEGMENTS:
        raise ValueError(
            "fingerprint storage value is shorter than the descriptor segment count"
        )
    if version <= 0:
        raise ValueError("fingerprint version must be positive")

    words = np.frombuffer(payload, dtype="<u4")
    bits = np.unpackbits(words.view(np.uint8), bitorder="little").reshape(-1, 32)
    descriptor = _fingerprint_descriptor(bits)
    return FingerprintSketch(
        track_id=int(track_id),
        version=int(version),
        descriptor=descriptor,
    )


def fingerprint_candidate_pairs(
    sketches: list[FingerprintSketch],
) -> set[tuple[int, int]]:
    """Return candidate pairs from version-separated deterministic fingerprint LSH."""
    pairs: set[tuple[int, int]] = set()
    by_version: dict[int, list[FingerprintSketch]] = {}
    for sketch in sketches:
        by_version.setdefault(sketch.version, []).append(sketch)
    for version, version_sketches in by_version.items():
        if len(version_sketches) < 2:
            continue
        matrix = np.vstack([sketch.descriptor for sketch in version_sketches]).astype(
            np.float32
        )
        matrix = matrix - matrix.mean(axis=0, keepdims=True)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        projection = np.random.default_rng(
            _projection_seed(version, matrix.shape[1])
        ).standard_normal(
            (matrix.shape[1], FINGERPRINT_LSH_PROJECTIONS),
            dtype=np.float32,
        )
        signatures = (matrix @ projection) >= 0
        buckets: dict[tuple[int, int], list[int]] = {}
        for row_index, sketch in enumerate(version_sketches):
            for key_index, value in _fingerprint_lsh_bucket_keys(signatures[row_index]):
                buckets.setdefault((key_index, value), []).append(sketch.track_id)
        for ids in buckets.values():
            if len(ids) < 2 or len(ids) > FINGERPRINT_LSH_MAX_BUCKET_TRACKS:
                continue
            for left_index, left_id in enumerate(ids):
                for right_id in ids[left_index + 1 :]:
                    pairs.add(_ordered_pair(left_id, right_id))
    return pairs


def load_fingerprint_sketches(
    connection: sqlite3.Connection,
    track_uuids: Mapping[int, str],
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_hook: Callable[[], None] | None = None,
) -> FingerprintLoadResult:
    """Read and validate saved fingerprints one database chunk at a time."""
    total_tracks = len(track_uuids)
    if not _has_fingerprint_table(connection):
        if progress_callback is not None:
            progress_callback(total_tracks, total_tracks)
        return FingerprintLoadResult((), 0)
    sketches: list[FingerprintSketch] = []
    rejected_rows = 0
    processed_tracks = 0
    for track_ids in _chunks(sorted(track_uuids), 200):
        if cancel_hook is not None:
            cancel_hook()
        for row in _fingerprint_rows(connection, track_ids):
            track_id = int(row["track_id"])
            value = _valid_fingerprint_value(row, track_uuids.get(track_id))
            if value is None:
                rejected_rows += 1
                continue
            fingerprint_version, fingerprint_base64 = value
            try:
                sketches.append(
                    fingerprint_sketch(
                        track_id,
                        fingerprint_version,
                        fingerprint_base64,
                    )
                )
            except ValueError:
                rejected_rows += 1
        processed_tracks += len(track_ids)
        if progress_callback is not None:
            progress_callback(processed_tracks, total_tracks)
    return FingerprintLoadResult(tuple(sketches), rejected_rows)


def fingerprint_match_scores(
    connection: sqlite3.Connection,
    candidate_pairs: set[tuple[int, int]],
    track_uuids: Mapping[int, str],
    *,
    matcher: Callable[[str, str], float] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_hook: Callable[[], None] | None = None,
) -> dict[tuple[int, int], float]:
    """Run native SONARA matching only for compact-LSH shortlisted pairs."""
    total_pairs = len(candidate_pairs)
    if not candidate_pairs:
        return {}
    if not _has_fingerprint_table(connection):
        if progress_callback is not None:
            progress_callback(total_pairs, total_pairs)
        return {}
    selected_matcher = matcher or _native_fingerprint_match
    scores: dict[tuple[int, int], float] = {}
    completed_pairs = 0
    for pair_chunk in _chunks(sorted(candidate_pairs), 250):
        if cancel_hook is not None:
            cancel_hook()
        track_ids = sorted({track_id for pair in pair_chunk for track_id in pair})
        values: dict[int, tuple[int, str]] = {}
        for row in _fingerprint_rows(connection, track_ids):
            track_id = int(row["track_id"])
            value = _valid_fingerprint_value(row, track_uuids.get(track_id))
            if value is not None:
                values[track_id] = value
        for pair in pair_chunk:
            left = values.get(pair[0])
            right = values.get(pair[1])
            if left is None or right is None or left[0] != right[0]:
                continue
            score = float(selected_matcher(left[1], right[1]))
            if np.isfinite(score):
                scores[pair] = max(0.0, min(1.0, score))
        completed_pairs += len(pair_chunk)
        if progress_callback is not None:
            progress_callback(completed_pairs, total_pairs)
    return scores


def _fingerprint_descriptor(bits: np.ndarray) -> np.ndarray:
    segments = np.array_split(bits, FINGERPRINT_DESCRIPTOR_SEGMENTS, axis=0)
    bit_means = [segment.mean(axis=0, dtype=np.float32) for segment in segments]
    transition_means = [
        np.logical_xor(segment[1:], segment[:-1]).mean(axis=0, dtype=np.float32)
        if len(segment) > 1
        else np.zeros(32, dtype=np.float32)
        for segment in segments
    ]
    return np.concatenate([*bit_means, *transition_means]).astype(
        np.float32, copy=False
    )


def _fingerprint_lsh_bucket_keys(signature: np.ndarray) -> tuple[tuple[int, int], ...]:
    """Require two adjacent 12-bit bands before a fingerprint pair becomes a candidate."""
    expected_size = FINGERPRINT_LSH_PROJECTIONS
    if signature.shape != (expected_size,):
        raise ValueError(f"fingerprint signature must contain {expected_size} bits")
    bits_per_key = FINGERPRINT_LSH_BITS_PER_BAND * FINGERPRINT_LSH_BANDS_PER_KEY
    return tuple(
        (
            key_index,
            _bits_to_int(signature[start : start + bits_per_key]),
        )
        for key_index, start in enumerate(range(0, expected_size, bits_per_key))
    )


def _projection_seed(version: int, dimension: int) -> int:
    return int.from_bytes(
        f"sonara-fingerprint-v{version}:{dimension}".encode("utf-8"),
        byteorder="little",
        signed=False,
    ) % (2**63 - 1)


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for index, bit in enumerate(bits):
        if bool(bit):
            value |= 1 << index
    return value


def _ordered_pair(left_id: int, right_id: int) -> tuple[int, int]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def _fingerprint_rows(
    connection: sqlite3.Connection,
    track_ids: list[int],
) -> list[sqlite3.Row]:
    if not track_ids:
        return []
    placeholders = ", ".join("?" for _ in track_ids)
    return connection.execute(
        f"""
        SELECT track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        FROM sonara_fingerprints
        WHERE track_id IN ({placeholders})
        """,
        track_ids,
    ).fetchall()


def _has_fingerprint_table(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sonara_fingerprints'"
        ).fetchone()
        is not None
    )


def _valid_fingerprint_value(
    row: sqlite3.Row,
    expected_track_uuid: str | None,
) -> tuple[int, str] | None:
    if expected_track_uuid is None or str(row["track_uuid"]) != expected_track_uuid:
        return None
    try:
        FingerprintOutput(
            value=row["fingerprint_base64"],
            version=row["fingerprint_version"],
            analyzed_at=row["analyzed_at"],
        )
    except (TypeError, ValueError):
        return None
    return int(row["fingerprint_version"]), str(row["fingerprint_base64"])


def _native_fingerprint_match(left: str, right: str) -> float:
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError(
            "SONARA fingerprint verification needs the 'sonara' extra; "
            "install it or rerun with --embedding"
        ) from error

    return float(sonara.fingerprint_match(left, right))


def _chunks(items: list[object], size: int) -> list[list[object]]:
    return [items[index : index + size] for index in range(0, len(items), size)]

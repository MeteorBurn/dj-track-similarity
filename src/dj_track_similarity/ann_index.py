from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any

import numpy as np

from .database import LibraryDatabase
from .vector_index import (
    EXACT_VECTOR_BACKEND_NAME,
    HNSW_VECTOR_BACKEND_NAME,
    ExactVectorSearchBackend,
    VectorIndexUnavailable,
    VectorSearchHit,
)


SIDECAR_DIR_NAME = ".dj-track-similarity-indexes"
PERSISTENT_INDEX_SCHEMA_VERSION = 1
PERSISTENT_INDEX_MANIFEST_SUFFIX = ".manifest.json"
PERSISTENT_INDEX_METRIC = "inner_product"
PERSISTENT_INDEX_BACKEND_AUTO = "auto"
PERSISTENT_INDEX_BACKEND_ALIASES = {
    "auto": PERSISTENT_INDEX_BACKEND_AUTO,
    "exact": EXACT_VECTOR_BACKEND_NAME,
    "exact-numpy": EXACT_VECTOR_BACKEND_NAME,
    "exact_numpy": EXACT_VECTOR_BACKEND_NAME,
    "numpy": EXACT_VECTOR_BACKEND_NAME,
    "hnsw": HNSW_VECTOR_BACKEND_NAME,
    "hnswlib": HNSW_VECTOR_BACKEND_NAME,
}
PERSISTENT_INDEX_ADAPTERS = ("mert", "maest", "clap")
DEFAULT_RECALL_THRESHOLD = 0.97
DEFAULT_RECALL_K_VALUES = (10, 50, 100)


@dataclass(frozen=True)
class EmbeddingIndexSnapshot:
    adapter: str
    model_id: str
    model_names: tuple[str, ...]
    track_ids: tuple[int, ...]
    matrix: np.ndarray
    embedding_count: int
    embedding_dim: int
    track_ids_hash: str
    embedding_version_hash: str
    source_embedding_updated_at_max: str | None


@dataclass(frozen=True)
class PersistentIndexBuildResult:
    adapter: str
    backend: str
    index_dir: Path
    artifact_path: Path
    manifest_path: Path
    embedding_count: int
    embedding_dim: int
    build_seconds: float
    index_size_bytes: int
    warnings: tuple[str, ...]
    manifest: dict[str, Any]


@dataclass(frozen=True)
class PersistentIndexVerification:
    adapter: str
    status: str
    message: str
    index_dir: Path
    manifest_path: Path | None
    artifact_path: Path | None
    reasons: tuple[str, ...]
    manifest: dict[str, Any] | None

    @property
    def is_usable(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class PersistentIndexClearResult:
    index_dir: Path
    adapter: str | None
    deleted_files: tuple[Path, ...]

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_files)


class PersistentAnnVectorSearchBackend:
    """Explicit opt-in persistent sidecar backend with exact fallback by default."""

    backend_name = "persistent_ann_sidecar"

    def __init__(
        self,
        db: LibraryDatabase,
        *,
        embedding_key: str = "mert",
        index_dir: str | Path | None = None,
        allow_exact_fallback: bool = True,
    ) -> None:
        self.db = db
        self.embedding_key = normalize_index_adapter(embedding_key)
        self.index_dir = resolve_index_dir(db, index_dir)
        self.allow_exact_fallback = bool(allow_exact_fallback)
        self.fallback_backend = ExactVectorSearchBackend()
        self.last_fallback_reason: str | None = None
        self.last_backend_name: str | None = None

    def search(
        self,
        matrix: np.ndarray,
        track_ids: Sequence[int],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        verification = verify_persistent_index(self.db, self.embedding_key, index_dir=self.index_dir)
        if not verification.is_usable:
            return self._fallback_or_raise(matrix, track_ids, query, limit, verification.message)

        try:
            searcher = load_persistent_index_searcher(verification)
            self.last_fallback_reason = None
            self.last_backend_name = searcher.backend_name
            return searcher.search(query, limit)
        except (OSError, ValueError, VectorIndexUnavailable) as error:
            return self._fallback_or_raise(matrix, track_ids, query, limit, str(error))

    def _fallback_or_raise(
        self,
        matrix: np.ndarray,
        track_ids: Sequence[int],
        query: np.ndarray,
        limit: int,
        reason: str,
    ) -> list[VectorSearchHit]:
        self.last_fallback_reason = reason
        self.last_backend_name = self.fallback_backend.backend_name
        if self.allow_exact_fallback:
            return self.fallback_backend.search(matrix, track_ids, query, limit)
        raise VectorIndexUnavailable(f"Persistent ANN sidecar is not usable: {reason}")


class PersistentIndexSearcher:
    backend_name: str

    def search(self, query: np.ndarray, limit: int) -> list[VectorSearchHit]:
        raise NotImplementedError


class ExactNumpyPersistentIndexSearcher(PersistentIndexSearcher):
    backend_name = EXACT_VECTOR_BACKEND_NAME

    def __init__(self, artifact_path: Path) -> None:
        with np.load(artifact_path) as data:
            self.matrix = np.asarray(data["matrix"], dtype=np.float32)
            self.track_ids = tuple(int(track_id) for track_id in np.asarray(data["track_ids"]).reshape(-1))
        self.exact_backend = ExactVectorSearchBackend()

    def search(self, query: np.ndarray, limit: int) -> list[VectorSearchHit]:
        return self.exact_backend.search(self.matrix, self.track_ids, query, limit)


class HnswPersistentIndexSearcher(PersistentIndexSearcher):
    backend_name = HNSW_VECTOR_BACKEND_NAME

    def __init__(self, artifact_path: Path, *, dim: int, count: int, ef_search: int) -> None:
        if dim <= 0:
            raise ValueError("Persistent HNSW index requires a positive embedding dimension")
        self._hnswlib = _load_hnswlib()
        self.index = self._hnswlib.Index(space="ip", dim=int(dim))
        self.index.load_index(str(artifact_path), max_elements=int(count))
        self.count = int(count)
        self.dim = int(dim)
        self.ef_search = _positive_int(ef_search, "ef_search")

    def search(self, query: np.ndarray, limit: int) -> list[VectorSearchHit]:
        search_limit = min(_non_negative_int(limit, "limit"), self.count)
        if search_limit == 0:
            return []
        query_vector = np.asarray(query, dtype=np.float32).reshape(-1)
        if query_vector.shape[0] != self.dim:
            raise ValueError(f"Persistent HNSW query dim mismatch: {query_vector.shape[0]} != {self.dim}")
        self.index.set_ef(max(self.ef_search, search_limit))
        labels, distances = self.index.knn_query(query_vector.reshape(1, -1), k=search_limit)
        flat_labels = np.asarray(labels).reshape(-1)
        flat_distances = np.asarray(distances, dtype=np.float32).reshape(-1)
        return [
            VectorSearchHit(track_id=int(label), score=float(1.0 - float(distance)), index=None)
            for label, distance in zip(flat_labels, flat_distances, strict=True)
        ]


def normalize_index_adapter(adapter: str) -> str:
    clean_adapter = str(adapter).strip().lower()
    if clean_adapter in PERSISTENT_INDEX_ADAPTERS:
        return clean_adapter
    allowed = ", ".join(PERSISTENT_INDEX_ADAPTERS)
    raise ValueError(f"Unsupported index adapter {adapter!r}. Allowed: {allowed}")


def normalize_index_backend(backend: str) -> str:
    clean_backend = str(backend).strip().lower()
    try:
        return PERSISTENT_INDEX_BACKEND_ALIASES[clean_backend]
    except KeyError as error:
        allowed = ", ".join(sorted(PERSISTENT_INDEX_BACKEND_ALIASES))
        raise ValueError(f"Unsupported index backend {backend!r}. Allowed: {allowed}") from error


def default_index_dir_for_db(db: LibraryDatabase | str | Path) -> Path:
    db_path = db.path if isinstance(db, LibraryDatabase) else Path(db)
    return db_path.expanduser().resolve(strict=False).parent / SIDECAR_DIR_NAME


def resolve_index_dir(db: LibraryDatabase | str | Path, index_dir: str | Path | None = None) -> Path:
    raw_path = default_index_dir_for_db(db) if index_dir is None else Path(index_dir)
    return _safe_index_dir(raw_path)


def load_embedding_index_snapshot(db: LibraryDatabase, adapter: str) -> EmbeddingIndexSnapshot:
    clean_adapter = normalize_index_adapter(adapter)
    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT track_id, model_name, dim, vector, updated_at
            FROM embeddings
            WHERE embedding_key = ?
            ORDER BY track_id
            """,
            (clean_adapter,),
        ).fetchall()
    if not rows:
        return EmbeddingIndexSnapshot(
            adapter=clean_adapter,
            model_id="empty",
            model_names=(),
            track_ids=(),
            matrix=np.zeros((0, 0), dtype=np.float32),
            embedding_count=0,
            embedding_dim=0,
            track_ids_hash=_hash_json([]),
            embedding_version_hash=_hash_json([]),
            source_embedding_updated_at_max=None,
        )

    track_ids: list[int] = []
    vectors: list[np.ndarray] = []
    model_names: set[str] = set()
    updated_at_values: list[str] = []
    version_hasher = hashlib.sha256()
    expected_dim: int | None = None

    for row in rows:
        track_id = int(row["track_id"])
        model_name = str(row["model_name"])
        dim = int(row["dim"])
        vector = np.frombuffer(row["vector"], dtype=np.float32).copy()
        if expected_dim is None:
            expected_dim = dim
        if dim != expected_dim:
            raise ValueError(f"Embedding index requires one dimension per adapter; found {expected_dim} and {dim}")
        if vector.shape[0] != dim:
            raise ValueError(f"Embedding row track_id={track_id} dim mismatch: {vector.shape[0]} != {dim}")
        if not np.isfinite(vector).all():
            raise ValueError(f"Embedding row track_id={track_id} contains non-finite values")
        updated_at = str(row["updated_at"])
        track_ids.append(track_id)
        vectors.append(vector)
        model_names.add(model_name)
        updated_at_values.append(updated_at)
        _hash_embedding_row(version_hasher, track_id=track_id, model_name=model_name, dim=dim, updated_at=updated_at, vector=vector)

    matrix = np.vstack(vectors).astype(np.float32)
    clean_model_names = tuple(sorted(model_names))
    return EmbeddingIndexSnapshot(
        adapter=clean_adapter,
        model_id=_model_id_for_names(clean_model_names),
        model_names=clean_model_names,
        track_ids=tuple(track_ids),
        matrix=matrix,
        embedding_count=len(track_ids),
        embedding_dim=int(matrix.shape[1]),
        track_ids_hash=_hash_json(track_ids),
        embedding_version_hash=version_hasher.hexdigest(),
        source_embedding_updated_at_max=max(updated_at_values) if updated_at_values else None,
    )


def build_persistent_index(
    db: LibraryDatabase,
    adapter: str,
    *,
    index_dir: str | Path | None = None,
    backend: str = PERSISTENT_INDEX_BACKEND_AUTO,
    ef_construction: int = 200,
    m: int = 16,
    ef_search: int = 100,
) -> PersistentIndexBuildResult:
    clean_adapter = normalize_index_adapter(adapter)
    clean_backend = normalize_index_backend(backend)
    clean_index_dir = resolve_index_dir(db, index_dir)
    snapshot = load_embedding_index_snapshot(db, clean_adapter)
    if snapshot.embedding_count == 0:
        raise ValueError(f"No {clean_adapter} embeddings were found; run analysis before building an index")
    if snapshot.embedding_dim == 0:
        raise ValueError(f"Cannot build {clean_adapter} index with zero-dimensional embeddings")

    selected_backend, warnings = _select_build_backend(clean_backend)
    settings = _index_settings(selected_backend, ef_construction=ef_construction, m=m, ef_search=ef_search)
    artifact_path, manifest_path = _artifact_paths(clean_index_dir, snapshot, selected_backend)
    clean_index_dir.mkdir(parents=True, exist_ok=True)
    clear_persistent_indexes(clean_index_dir, adapter=clean_adapter)

    start = time.perf_counter()
    if selected_backend == HNSW_VECTOR_BACKEND_NAME:
        _write_hnsw_index(artifact_path, snapshot, settings)
    elif selected_backend == EXACT_VECTOR_BACKEND_NAME:
        _write_exact_numpy_index(artifact_path, snapshot)
    else:
        raise ValueError(f"Unsupported selected index backend: {selected_backend}")
    build_seconds = time.perf_counter() - start

    manifest = _build_manifest(
        db,
        snapshot,
        backend=selected_backend,
        settings=settings,
        artifact_path=artifact_path,
        build_seconds=build_seconds,
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PersistentIndexBuildResult(
        adapter=clean_adapter,
        backend=selected_backend,
        index_dir=clean_index_dir,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        embedding_count=snapshot.embedding_count,
        embedding_dim=snapshot.embedding_dim,
        build_seconds=build_seconds,
        index_size_bytes=_file_size(artifact_path),
        warnings=warnings,
        manifest=manifest,
    )


def verify_persistent_index(
    db: LibraryDatabase,
    adapter: str,
    *,
    index_dir: str | Path | None = None,
) -> PersistentIndexVerification:
    clean_adapter = normalize_index_adapter(adapter)
    clean_index_dir = resolve_index_dir(db, index_dir)
    manifest_path = _latest_manifest_path(clean_index_dir, clean_adapter)
    if manifest_path is None:
        return PersistentIndexVerification(
            adapter=clean_adapter,
            status="missing",
            message=f"No persistent ANN index manifest found for adapter={clean_adapter} in {clean_index_dir}",
            index_dir=clean_index_dir,
            manifest_path=None,
            artifact_path=None,
            reasons=("manifest_missing",),
            manifest=None,
        )

    try:
        manifest = _read_manifest(manifest_path)
    except ValueError as error:
        return _verification_error(clean_adapter, clean_index_dir, manifest_path, None, None, str(error))
    artifact_path, artifact_reason = _artifact_path_from_manifest(clean_index_dir, manifest)
    if artifact_reason is not None:
        return _verification_error(clean_adapter, clean_index_dir, manifest_path, None, manifest, artifact_reason)
    if artifact_path is None or not artifact_path.exists():
        return PersistentIndexVerification(
            adapter=clean_adapter,
            status="stale",
            message=f"Persistent ANN index artifact is missing for adapter={clean_adapter}",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            reasons=("artifact_missing",),
            manifest=manifest,
        )

    try:
        snapshot = load_embedding_index_snapshot(db, clean_adapter)
    except ValueError as error:
        return _verification_error(clean_adapter, clean_index_dir, manifest_path, artifact_path, manifest, str(error))

    reasons = _manifest_mismatch_reasons(db, clean_adapter, manifest, snapshot)
    if reasons:
        return PersistentIndexVerification(
            adapter=clean_adapter,
            status="stale",
            message=f"Persistent ANN index is stale for adapter={clean_adapter}: {', '.join(reasons)}",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            reasons=tuple(reasons),
            manifest=manifest,
        )

    backend = str(manifest.get("backend", ""))
    if backend == HNSW_VECTOR_BACKEND_NAME and not _hnswlib_available():
        return PersistentIndexVerification(
            adapter=clean_adapter,
            status="unsupported",
            message=_hnsw_dependency_message("load persistent HNSW indexes"),
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            reasons=("hnswlib_missing",),
            manifest=manifest,
        )

    return PersistentIndexVerification(
        adapter=clean_adapter,
        status="ok",
        message=f"Persistent ANN index is current for adapter={clean_adapter}",
        index_dir=clean_index_dir,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        reasons=(),
        manifest=manifest,
    )


def clear_persistent_indexes(index_dir: str | Path, *, adapter: str | None = None) -> PersistentIndexClearResult:
    clean_adapter = normalize_index_adapter(adapter) if adapter is not None else None
    clean_index_dir = _safe_index_dir(index_dir)
    if not clean_index_dir.exists():
        return PersistentIndexClearResult(index_dir=clean_index_dir, adapter=clean_adapter, deleted_files=())
    if not clean_index_dir.is_dir():
        raise ValueError(f"Index path is not a directory: {clean_index_dir}")

    deleted: list[Path] = []
    for path in sorted(clean_index_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or not _is_owned_index_file(path.name, clean_adapter):
            continue
        _assert_inside_directory(clean_index_dir, path)
        path.unlink()
        deleted.append(path)
    return PersistentIndexClearResult(index_dir=clean_index_dir, adapter=clean_adapter, deleted_files=tuple(deleted))


def benchmark_persistent_index(
    db: LibraryDatabase,
    adapter: str,
    *,
    index_dir: str | Path | None = None,
    threshold: float = DEFAULT_RECALL_THRESHOLD,
    recall_k: int = 50,
    k_values: Sequence[int] | None = None,
    seed_count: int = 20,
    random_seed: int = 123,
) -> dict[str, Any]:
    clean_adapter = normalize_index_adapter(adapter)
    clean_threshold = _threshold_value(threshold)
    clean_recall_k = _positive_int(recall_k, "recall_k")
    clean_k_values = _benchmark_k_values(k_values, clean_recall_k)
    clean_seed_count = _positive_int(seed_count, "seed_count")
    clean_random_seed = int(random_seed)
    verification = verify_persistent_index(db, clean_adapter, index_dir=index_dir)
    if not verification.is_usable:
        raise ValueError(f"Cannot benchmark persistent ANN index: {verification.message}")

    snapshot = load_embedding_index_snapshot(db, clean_adapter)
    if snapshot.embedding_count < 2:
        raise ValueError("At least two embeddings are required to benchmark recall")

    persistent_searcher = load_persistent_index_searcher(verification)
    exact_backend = ExactVectorSearchBackend()
    seed_indices = _sample_seed_indices(snapshot.embedding_count, clean_seed_count, clean_random_seed)
    exact_latencies: list[float] = []
    ann_latencies: list[float] = []
    recall_values: dict[int, list[float]] = {k_value: [] for k_value in clean_k_values}
    track_ids = snapshot.track_ids
    max_limit = min(snapshot.embedding_count, max(clean_k_values) + 1)

    for seed_index in seed_indices:
        query = snapshot.matrix[seed_index]
        seed_track_id = track_ids[seed_index]
        exact_seconds, exact_hits = _timed(lambda query=query: exact_backend.search(snapshot.matrix, track_ids, query, limit=max_limit))
        ann_seconds, ann_hits = _timed(lambda query=query: persistent_searcher.search(query, limit=max_limit))
        exact_latencies.append(exact_seconds)
        ann_latencies.append(ann_seconds)
        exact_ids = _candidate_ids_without_seed(exact_hits, seed_track_id)
        ann_ids = _candidate_ids_without_seed(ann_hits, seed_track_id)
        for k_value in clean_k_values:
            recall_values[k_value].append(_recall_at_k(exact_ids, ann_ids, k_value))

    recalls = {f"recall_at_{k_value}": _recall_summary(values) for k_value, values in recall_values.items()}
    primary_recall = recalls[f"recall_at_{clean_recall_k}"]["mean"]
    status = "pass" if primary_recall is not None and primary_recall >= clean_threshold else "fail"
    manifest = verification.manifest or {}
    artifact_path = verification.artifact_path
    ann_latency = _latency_summary(ann_latencies)
    exact_latency = _latency_summary(exact_latencies)
    index_size_bytes = _file_size(artifact_path) if artifact_path is not None else 0
    build_seconds = manifest.get("build_seconds")
    return {
        "benchmark": "persistent_ann_recall",
        "schema_version": 1,
        "generated_at": _utc_timestamp(),
        "status": status,
        "adapter": clean_adapter,
        "backend": persistent_searcher.backend_name,
        "track_count": snapshot.embedding_count,
        "compare": "exact",
        "threshold": clean_threshold,
        "primary_recall_k": clean_recall_k,
        "seed_count": len(seed_indices),
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "index_size_bytes": index_size_bytes,
        "build_seconds": build_seconds,
        "verify_status": verification.status,
        "recall_at_10": recalls["recall_at_10"]["mean"],
        "recall_at_50": recalls["recall_at_50"]["mean"],
        "recall_at_100": recalls["recall_at_100"]["mean"],
        "p50_latency": ann_latency["p50_ms"],
        "p95_latency": ann_latency["p95_ms"],
        "latency_unit": "ms",
        "fallback_reason": None,
        "recall": recalls,
        "latency": {
            "exact": exact_latency,
            "ann": ann_latency,
        },
        "index": {
            "index_dir": str(verification.index_dir),
            "manifest_path": str(verification.manifest_path) if verification.manifest_path is not None else None,
            "artifact_path": str(artifact_path) if artifact_path is not None else None,
            "index_size_bytes": index_size_bytes,
            "created_at": manifest.get("created_at"),
            "build_seconds": build_seconds,
            "settings": manifest.get("settings", {}),
        },
    }


def load_persistent_index_searcher(verification: PersistentIndexVerification) -> PersistentIndexSearcher:
    if not verification.is_usable:
        raise VectorIndexUnavailable(f"Persistent ANN index is not usable: {verification.message}")
    if verification.artifact_path is None or verification.manifest is None:
        raise VectorIndexUnavailable("Persistent ANN verification did not include an artifact path")
    backend = str(verification.manifest.get("backend", ""))
    if backend == EXACT_VECTOR_BACKEND_NAME:
        return ExactNumpyPersistentIndexSearcher(verification.artifact_path)
    if backend == HNSW_VECTOR_BACKEND_NAME:
        settings = verification.manifest.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        return HnswPersistentIndexSearcher(
            verification.artifact_path,
            dim=int(verification.manifest.get("embedding_dim", 0)),
            count=int(verification.manifest.get("embedding_count", 0)),
            ef_search=int(settings.get("ef_search", 100)),
        )
    raise VectorIndexUnavailable(f"Unsupported persistent ANN backend in manifest: {backend!r}")


def _select_build_backend(requested_backend: str) -> tuple[str, tuple[str, ...]]:
    if requested_backend == PERSISTENT_INDEX_BACKEND_AUTO:
        if _hnswlib_available():
            return HNSW_VECTOR_BACKEND_NAME, ()
        return EXACT_VECTOR_BACKEND_NAME, (_hnsw_dependency_message("build HNSW indexes") + " Falling back to exact-numpy sidecar.",)
    if requested_backend == HNSW_VECTOR_BACKEND_NAME:
        _load_hnswlib()
    return requested_backend, ()


def _write_hnsw_index(artifact_path: Path, snapshot: EmbeddingIndexSnapshot, settings: dict[str, int]) -> None:
    hnswlib = _load_hnswlib()
    matrix = np.ascontiguousarray(snapshot.matrix, dtype=np.float32)
    index = hnswlib.Index(space="ip", dim=int(snapshot.embedding_dim))
    index.init_index(
        max_elements=int(snapshot.embedding_count),
        ef_construction=int(settings["ef_construction"]),
        M=int(settings["m"]),
    )
    index.add_items(matrix, np.asarray(snapshot.track_ids, dtype=np.int64))
    index.set_ef(int(settings["ef_search"]))
    index.save_index(str(artifact_path))


def _write_exact_numpy_index(artifact_path: Path, snapshot: EmbeddingIndexSnapshot) -> None:
    np.savez_compressed(
        artifact_path,
        matrix=np.ascontiguousarray(snapshot.matrix, dtype=np.float32),
        track_ids=np.asarray(snapshot.track_ids, dtype=np.int64),
    )


def _build_manifest(
    db: LibraryDatabase,
    snapshot: EmbeddingIndexSnapshot,
    *,
    backend: str,
    settings: dict[str, int],
    artifact_path: Path,
    build_seconds: float,
) -> dict[str, Any]:
    created_at = _utc_timestamp()
    fingerprint = _db_fingerprint(db)
    return {
        "schema_version": PERSISTENT_INDEX_SCHEMA_VERSION,
        "adapter": snapshot.adapter,
        "embedding_key": snapshot.adapter,
        "backend": backend,
        "metric": PERSISTENT_INDEX_METRIC,
        "settings": dict(settings),
        "db_fingerprint": fingerprint,
        "db_path_hash": fingerprint["path_hash"],
        "db_schema_version": fingerprint["schema_version"],
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "track_count": snapshot.embedding_count,
        "dim": snapshot.embedding_dim,
        "track_ids_hash": snapshot.track_ids_hash,
        "embedding_version_hash": snapshot.embedding_version_hash,
        "track_ids_version_hash": snapshot.embedding_version_hash,
        "source_embedding_updated_at_max": snapshot.source_embedding_updated_at_max,
        "model_id": snapshot.model_id,
        "model_name": snapshot.model_names[0] if len(snapshot.model_names) == 1 else snapshot.model_id,
        "model_names": list(snapshot.model_names),
        "created_at": created_at,
        "updated_at": created_at,
        "build_seconds": build_seconds,
        "artifact": {
            "file_name": artifact_path.name,
            "size_bytes": _file_size(artifact_path),
        },
    }


def _manifest_mismatch_reasons(
    db: LibraryDatabase,
    adapter: str,
    manifest: dict[str, Any],
    snapshot: EmbeddingIndexSnapshot,
) -> list[str]:
    reasons: list[str] = []
    fingerprint = _db_fingerprint(db)
    manifest_fingerprint = manifest.get("db_fingerprint")
    if not isinstance(manifest_fingerprint, dict):
        reasons.append("db_fingerprint_missing")
    else:
        if manifest_fingerprint.get("path_hash") != fingerprint["path_hash"]:
            reasons.append("db_path_hash")
        try:
            manifest_schema_version = int(manifest_fingerprint.get("schema_version", -1))
        except (TypeError, ValueError):
            manifest_schema_version = -1
        if manifest_schema_version != fingerprint["schema_version"]:
            reasons.append("db_schema_version")
    expected_values = {
        "schema_version": PERSISTENT_INDEX_SCHEMA_VERSION,
        "adapter": adapter,
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "track_ids_hash": snapshot.track_ids_hash,
        "embedding_version_hash": snapshot.embedding_version_hash,
        "source_embedding_updated_at_max": snapshot.source_embedding_updated_at_max,
        "metric": PERSISTENT_INDEX_METRIC,
    }
    for key, expected in expected_values.items():
        if manifest.get(key) != expected:
            reasons.append(key)
    if str(manifest.get("backend", "")) not in {EXACT_VECTOR_BACKEND_NAME, HNSW_VECTOR_BACKEND_NAME}:
        reasons.append("backend")
    return reasons


def _verification_error(
    adapter: str,
    index_dir: Path,
    manifest_path: Path,
    artifact_path: Path | None,
    manifest: dict[str, Any] | None,
    reason: str,
) -> PersistentIndexVerification:
    return PersistentIndexVerification(
        adapter=adapter,
        status="error",
        message=f"Persistent ANN index verification failed for adapter={adapter}: {reason}",
        index_dir=index_dir,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        reasons=(reason,),
        manifest=manifest,
    )


def _latest_manifest_path(index_dir: Path, adapter: str) -> Path | None:
    if not index_dir.exists() or not index_dir.is_dir():
        return None
    candidates = [
        path
        for path in index_dir.iterdir()
        if path.is_file() and path.name.startswith(f"embeddings_{adapter}_") and path.name.endswith(PERSISTENT_INDEX_MANIFEST_SUFFIX)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Index manifest JSON is invalid: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError("Index manifest JSON must be an object")
    return payload


def _artifact_path_from_manifest(index_dir: Path, manifest: dict[str, Any]) -> tuple[Path | None, str | None]:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        return None, "artifact metadata is missing"
    file_name = artifact.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        return None, "artifact file_name is missing"
    artifact_path = (index_dir / file_name).resolve(strict=False)
    try:
        artifact_path.relative_to(index_dir)
    except ValueError:
        return artifact_path, "artifact path escapes the index directory"
    return artifact_path, None


def _artifact_paths(index_dir: Path, snapshot: EmbeddingIndexSnapshot, backend: str) -> tuple[Path, Path]:
    extension = ".hnsw" if backend == HNSW_VECTOR_BACKEND_NAME else ".npz"
    base_name = f"embeddings_{snapshot.adapter}_{snapshot.model_id}_{snapshot.embedding_dim}"
    artifact_path = index_dir / f"{base_name}{extension}"
    manifest_path = index_dir / f"{base_name}{PERSISTENT_INDEX_MANIFEST_SUFFIX}"
    return artifact_path, manifest_path


def _index_settings(backend: str, *, ef_construction: int, m: int, ef_search: int) -> dict[str, int]:
    if backend == HNSW_VECTOR_BACKEND_NAME:
        return {
            "ef_construction": _positive_int(ef_construction, "ef_construction"),
            "m": _positive_int(m, "m"),
            "ef_search": _positive_int(ef_search, "ef_search"),
        }
    return {"ef_search": _positive_int(ef_search, "ef_search")}


def _db_fingerprint(db: LibraryDatabase) -> dict[str, int | str]:
    with db.connect() as connection:
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    path_text = str(db.path.expanduser().resolve(strict=False)).casefold()
    return {
        "path_hash": hashlib.sha256(path_text.encode("utf-8")).hexdigest(),
        "schema_version": schema_version,
    }


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_embedding_row(
    hasher: Any,
    *,
    track_id: int,
    model_name: str,
    dim: int,
    updated_at: str,
    vector: np.ndarray,
) -> None:
    hasher.update(str(track_id).encode("ascii"))
    hasher.update(b"\0")
    hasher.update(model_name.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(str(dim).encode("ascii"))
    hasher.update(b"\0")
    hasher.update(updated_at.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(np.ascontiguousarray(vector, dtype=np.float32).tobytes())
    hasher.update(b"\n")


def _model_id_for_names(model_names: Sequence[str]) -> str:
    if not model_names:
        return "unknown"
    if len(model_names) == 1:
        return _slugify(model_names[0])
    digest = _hash_json(list(model_names))[:12]
    return f"mixed_{digest}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-").lower()
    if not slug:
        return "unknown"
    if len(slug) <= 48:
        return slug
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:37]}_{digest}"


def _safe_index_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if resolved == resolved.parent:
        raise ValueError(f"Refusing to use filesystem root as an index directory: {resolved}")
    return resolved


def _assert_inside_directory(directory: Path, path: Path) -> None:
    resolved_directory = directory.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_directory)
    except ValueError as error:
        raise ValueError(f"Refusing to delete outside index directory: {resolved_path}") from error


def _is_owned_index_file(file_name: str, adapter: str | None) -> bool:
    if not file_name.startswith("embeddings_"):
        return False
    if adapter is not None and not file_name.startswith(f"embeddings_{adapter}_"):
        return False
    return file_name.endswith((".hnsw", ".npz", PERSISTENT_INDEX_MANIFEST_SUFFIX))


def _benchmark_k_values(k_values: Sequence[int] | None, recall_k: int) -> tuple[int, ...]:
    values = [recall_k, *DEFAULT_RECALL_K_VALUES]
    if k_values is not None:
        values.extend(k_values)
    return tuple(sorted({_positive_int(value, "k") for value in values}))


def _sample_seed_indices(embedding_count: int, seed_count: int, random_seed: int) -> tuple[int, ...]:
    clean_seed_count = min(seed_count, embedding_count)
    rng = np.random.default_rng(random_seed)
    sampled = rng.choice(np.arange(embedding_count), size=clean_seed_count, replace=False)
    return tuple(int(index) for index in sorted(sampled.tolist()))


def _candidate_ids_without_seed(hits: Sequence[VectorSearchHit], seed_track_id: int) -> tuple[int, ...]:
    return tuple(hit.track_id for hit in hits if hit.track_id != seed_track_id)


def _recall_at_k(exact_ids: Sequence[int], ann_ids: Sequence[int], k: int) -> float:
    expected = tuple(exact_ids[:k])
    if not expected:
        return 1.0
    found = set(ann_ids[:k])
    return len(found.intersection(expected)) / len(expected)


def _recall_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
    }


def _latency_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "p50_ms": _percentile_ms(values, 50.0),
        "p95_ms": _percentile_ms(values, 95.0),
    }


def _percentile_ms(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0] * 1000.0
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)] * 1000.0
    lower_weight = upper - rank
    upper_weight = rank - lower
    return (ordered[lower] * lower_weight + ordered[upper] * upper_weight) * 1000.0


def _timed(operation: Any) -> tuple[float, Any]:
    start = time.perf_counter()
    result = operation()
    return time.perf_counter() - start, result


def _threshold_value(value: float) -> float:
    threshold = float(value)
    if not math.isfinite(threshold) or threshold < 0.0 or threshold > 1.0:
        raise ValueError("threshold must be a finite number between 0.0 and 1.0")
    return threshold


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    clean_value = int(value)
    if clean_value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return clean_value


def _non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    clean_value = int(value)
    if clean_value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return clean_value


def _file_size(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    return int(path.stat().st_size)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_hnswlib() -> Any:
    try:
        return importlib.import_module("hnswlib")
    except ImportError as error:
        raise VectorIndexUnavailable(_hnsw_dependency_message("use persistent HNSW indexes")) from error


def _hnswlib_available() -> bool:
    try:
        importlib.import_module("hnswlib")
    except ImportError:
        return False
    return True


def _hnsw_dependency_message(action: str) -> str:
    return (
        f"Persistent ANN sidecar needs optional dependency 'hnswlib' to {action}. "
        "Install it with `python -m pip install -e .[ann]`, or pass --backend exact-numpy for deterministic development/testing."
    )

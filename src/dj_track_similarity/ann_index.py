from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any
import uuid

import numpy as np

from .analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
    ContractIdentityError,
)
from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    validate_production_contract,
)
from .vector_index import (
    HNSW_VECTOR_BACKEND_NAME,
    ExactVectorSearchBackend,
    VectorIndexUnavailable,
    VectorSearchHit,
    _hnsw_hits,
    _l2_query_vector,
    _l2_search_matrix,
    _search_limit,
    _targets_for_matrix,
)

if TYPE_CHECKING:
    from .db_analysis import AnalysisRepository


SIDECAR_DIR_NAME = ".dj-track-similarity-indexes"
PERSISTENT_INDEX_SCHEMA_VERSION = 2
PERSISTENT_INDEX_MANIFEST_SUFFIX = ".manifest.json"
PERSISTENT_INDEX_METRIC = "cosine"
PERSISTENT_INDEX_HNSW_SPACE = "ip"
PERSISTENT_INDEX_ANALYSIS_FAMILIES = (
    "maest",
    "mert",
    "muq",
    "clap",
)
DEFAULT_RECALL_THRESHOLD = 0.97
DEFAULT_RECALL_K_VALUES = (10, 50, 100)

_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "analysis_family",
        "backend",
        "metric",
        "hnsw_space",
        "contract",
        "catalog_uuid",
        "targets",
        "embedding_count",
        "embedding_dim",
        "target_identity_hash",
        "vector_content_hash",
        "created_at",
        "build_seconds",
        "settings",
        "artifact",
    }
)
_CONTRACT_MANIFEST_KEYS = frozenset(
    {
        "contract_hash",
        "canonical_payload",
    }
)
_TARGET_MANIFEST_KEYS = frozenset(
    {
        "catalog_uuid",
        "track_id",
        "track_uuid",
        "content_generation",
    }
)
_SETTINGS_MANIFEST_KEYS = frozenset(
    {
        "ef_construction",
        "m",
        "ef_search",
    }
)
_ARTIFACT_MANIFEST_KEYS = frozenset(
    {
        "file_name",
        "size_bytes",
        "sha256",
    }
)


@dataclass(frozen=True, slots=True)
class EmbeddingIndexSnapshot:
    analysis_family: str
    output: AnalysisOutput
    catalog_uuid: str
    targets: tuple[AnalysisTarget, ...]
    matrix: np.ndarray
    embedding_count: int
    embedding_dim: int
    target_identity_hash: str
    vector_content_hash: str


@dataclass(frozen=True, slots=True)
class PersistentIndexBuildResult:
    analysis_family: str
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


@dataclass(frozen=True, slots=True)
class PersistentIndexVerification:
    analysis_family: str
    status: str
    message: str
    index_dir: Path
    manifest_path: Path | None
    artifact_path: Path | None
    reasons: tuple[str, ...]
    manifest: dict[str, Any] | None
    snapshot: EmbeddingIndexSnapshot | None = None

    @property
    def is_usable(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True, slots=True)
class PersistentIndexClearResult:
    index_dir: Path
    analysis_family: str | None
    deleted_files: tuple[Path, ...]

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_files)


@dataclass(frozen=True, slots=True)
class _ParsedManifest:
    contract: ContractIdentity
    targets: tuple[AnalysisTarget, ...]
    settings: dict[str, int]


class PersistentAnnVectorSearchBackend:
    """Strict persistent HNSW search over one active v7 embedding contract.

    The backend deliberately has no exact-search fallback. A missing, stale,
    malformed, or unsupported persistent index raises
    :class:`VectorIndexUnavailable` so callers cannot unknowingly use a
    different retrieval path.
    """

    backend_name = "persistent_hnsw"

    def __init__(
        self,
        repository: AnalysisRepository,
        *,
        analysis_family: str,
        analysis_output: AnalysisOutput,
        index_dir: str | Path | None = None,
    ) -> None:
        self.repository = repository
        self.analysis_family = normalize_index_family(analysis_family)
        self.output = _active_index_output(
            repository,
            self.analysis_family,
            analysis_output,
        )
        self.index_dir = resolve_index_dir(repository, index_dir)

    def search(
        self,
        matrix: np.ndarray,
        targets: Sequence[AnalysisTarget],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        verification = verify_persistent_index(
            self.repository,
            self.analysis_family,
            analysis_output=self.output,
            index_dir=self.index_dir,
        )
        if not verification.is_usable:
            raise VectorIndexUnavailable(
                f"Persistent ANN index is not usable: {verification.message}"
            )
        snapshot = verification.snapshot
        if snapshot is None:
            raise VectorIndexUnavailable(
                "Persistent ANN verification did not return its current "
                "embedding snapshot"
            )
        if snapshot.output.contract.canonical_payload_json != (
            self.output.contract.canonical_payload_json
        ):
            raise VectorIndexUnavailable(
                "The active embedding contract changed after the persistent "
                "ANN backend was created"
            )

        search_matrix = _l2_search_matrix(matrix)
        search_targets = _targets_for_matrix(targets, search_matrix)
        if search_targets != snapshot.targets:
            raise VectorIndexUnavailable(
                "Persistent ANN input target identities do not exactly match "
                "the current indexed target set"
            )
        content_hash = _vector_content_hash(
            snapshot.output,
            search_targets,
            search_matrix,
        )
        if content_hash != snapshot.vector_content_hash:
            raise VectorIndexUnavailable(
                "Persistent ANN input vectors do not exactly match the "
                "current indexed snapshot"
            )

        searcher = load_persistent_index_searcher(verification)
        return searcher.search(query, limit)


class PersistentIndexSearcher:
    backend_name: str

    def search(
        self,
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        raise NotImplementedError


class HnswPersistentIndexSearcher(PersistentIndexSearcher):
    backend_name = HNSW_VECTOR_BACKEND_NAME

    def __init__(
        self,
        artifact_path: Path,
        *,
        targets: Sequence[AnalysisTarget],
        dim: int,
        ef_search: int,
        expected_size_bytes: int,
        expected_sha256: str,
    ) -> None:
        self.targets = tuple(targets)
        self.count = len(self.targets)
        self.dim = _positive_int(dim, "embedding_dim")
        self.ef_search = _positive_int(ef_search, "ef_search")
        if _file_size(artifact_path) != expected_size_bytes:
            raise VectorIndexUnavailable(
                "Persistent ANN artifact size changed after verification"
            )
        if _sha256_file(artifact_path) != expected_sha256:
            raise VectorIndexUnavailable(
                "Persistent ANN artifact SHA-256 changed after verification"
            )

        hnswlib = _load_hnswlib()
        self.index = hnswlib.Index(
            space=PERSISTENT_INDEX_HNSW_SPACE,
            dim=self.dim,
        )
        self.index.load_index(
            str(artifact_path),
            max_elements=self.count,
        )

    def search(
        self,
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        search_limit = min(_search_limit(limit), self.count)
        if search_limit == 0:
            return []
        shape_reference = np.empty((0, self.dim), dtype=np.float32)
        query_vector = _l2_query_vector(query, shape_reference)
        self.index.set_ef(max(self.ef_search, search_limit))
        labels, distances = self.index.knn_query(
            query_vector.reshape(1, -1),
            k=search_limit,
        )
        return _hnsw_hits(
            labels,
            distances,
            self.targets,
            self.count,
        )


def normalize_index_family(analysis_family: str) -> str:
    family = str(analysis_family).strip().lower()
    if family in PERSISTENT_INDEX_ANALYSIS_FAMILIES:
        return family
    allowed = ", ".join(PERSISTENT_INDEX_ANALYSIS_FAMILIES)
    raise ValueError(
        f"Unsupported ANN analysis family {analysis_family!r}. Allowed: {allowed}"
    )


def normalize_index_backend(backend: str) -> str:
    clean_backend = str(backend).strip().lower()
    if clean_backend == HNSW_VECTOR_BACKEND_NAME:
        return clean_backend
    raise ValueError(
        "Persistent ANN indexes require the explicit backend "
        f"{HNSW_VECTOR_BACKEND_NAME!r}; got {backend!r}"
    )


def default_index_dir_for_repository(
    repository: AnalysisRepository,
) -> Path:
    repository_path = _repository_path(repository)
    return repository_path.parent / SIDECAR_DIR_NAME


def resolve_index_dir(
    repository: AnalysisRepository,
    index_dir: str | Path | None = None,
) -> Path:
    raw_path = (
        default_index_dir_for_repository(repository)
        if index_dir is None
        else Path(index_dir)
    )
    return _safe_index_dir(raw_path)


def load_embedding_index_snapshot(
    repository: AnalysisRepository,
    analysis_family: str,
    analysis_output: AnalysisOutput,
) -> EmbeddingIndexSnapshot:
    family = normalize_index_family(analysis_family)
    output = _active_index_output(repository, family, analysis_output)

    raw_rows = tuple(repository.load_analysis_vectors(output))
    if any(not isinstance(row, AnalysisVectorRow) for row in raw_rows):
        raise TypeError("load_analysis_vectors must return AnalysisVectorRow values")
    rows = tuple(
        sorted(
            raw_rows,
            key=lambda row: (
                row.target.track_id,
                row.target.track_uuid,
                row.target.content_generation,
            ),
        )
    )
    for row in rows:
        if row.output.contract.canonical_payload_json != (
            output.contract.canonical_payload_json
        ):
            raise ValueError(
                "Analysis repository returned a vector under a different "
                "contract identity"
            )

    dim = output.contract.dim
    if dim is None:
        raise ValueError("Active embedding contract has no dimension")
    targets = tuple(row.target for row in rows)
    if rows:
        vectors = [np.asarray(row.vector, dtype="<f4").reshape(-1) for row in rows]
        if any(vector.shape != (dim,) for vector in vectors):
            raise ValueError(
                "Analysis repository returned an embedding with a dimension "
                "different from the active contract"
            )
        matrix = np.vstack(vectors).astype(np.float32, copy=False)
    else:
        matrix = np.empty((0, dim), dtype=np.float32)
    matrix = _l2_search_matrix(matrix)
    targets = _targets_for_matrix(targets, matrix)

    catalog_uuid = _repository_catalog_uuid(repository)
    if any(target.catalog_uuid != catalog_uuid for target in targets):
        raise ValueError(
            "Analysis repository returned a vector for a different catalog UUID"
        )
    matrix = np.ascontiguousarray(matrix, dtype=np.float32)
    matrix.setflags(write=False)
    return EmbeddingIndexSnapshot(
        analysis_family=family,
        output=output,
        catalog_uuid=catalog_uuid,
        targets=targets,
        matrix=matrix,
        embedding_count=len(targets),
        embedding_dim=dim,
        target_identity_hash=_target_identity_hash(targets),
        vector_content_hash=_vector_content_hash(
            output,
            targets,
            matrix,
        ),
    )


def build_persistent_index(
    repository: AnalysisRepository,
    analysis_family: str,
    *,
    analysis_output: AnalysisOutput,
    index_dir: str | Path | None = None,
    backend: str = HNSW_VECTOR_BACKEND_NAME,
    ef_construction: int = 200,
    m: int = 16,
    ef_search: int = 100,
) -> PersistentIndexBuildResult:
    family = normalize_index_family(analysis_family)
    selected_backend = normalize_index_backend(backend)
    _load_hnswlib()
    clean_index_dir = resolve_index_dir(repository, index_dir)
    snapshot = load_embedding_index_snapshot(
        repository,
        family,
        analysis_output,
    )
    if snapshot.embedding_count == 0:
        raise ValueError(
            f"No current {family} embeddings were found; run analysis before "
            "building an ANN index"
        )

    settings = {
        "ef_construction": _positive_int(
            ef_construction,
            "ef_construction",
        ),
        "m": _positive_int(m, "m"),
        "ef_search": _positive_int(ef_search, "ef_search"),
    }
    artifact_path, manifest_path = _artifact_paths(
        clean_index_dir,
        snapshot,
        build_token=uuid.uuid4().hex[:12],
    )
    clean_index_dir.mkdir(parents=True, exist_ok=True)
    temporary_artifact = artifact_path.with_name(
        f".{artifact_path.name}.{uuid.uuid4().hex}.tmp"
    )
    temporary_manifest = manifest_path.with_name(
        f".{manifest_path.name}.{uuid.uuid4().hex}.tmp"
    )

    start = time.perf_counter()
    try:
        _write_hnsw_index(
            temporary_artifact,
            snapshot,
            settings,
        )
        temporary_artifact.replace(artifact_path)
        build_seconds = time.perf_counter() - start
        manifest = _build_manifest(
            snapshot,
            backend=selected_backend,
            settings=settings,
            artifact_path=artifact_path,
            build_seconds=build_seconds,
        )
        temporary_manifest.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)
    finally:
        _remove_file_if_present(temporary_artifact)
        _remove_file_if_present(temporary_manifest)

    _remove_stale_owned_files(
        clean_index_dir,
        family,
        keep={artifact_path, manifest_path},
    )
    return PersistentIndexBuildResult(
        analysis_family=family,
        backend=selected_backend,
        index_dir=clean_index_dir,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        embedding_count=snapshot.embedding_count,
        embedding_dim=snapshot.embedding_dim,
        build_seconds=build_seconds,
        index_size_bytes=_file_size(artifact_path),
        warnings=(),
        manifest=manifest,
    )


def verify_persistent_index(
    repository: AnalysisRepository,
    analysis_family: str,
    *,
    analysis_output: AnalysisOutput,
    index_dir: str | Path | None = None,
) -> PersistentIndexVerification:
    family = normalize_index_family(analysis_family)
    clean_index_dir = resolve_index_dir(repository, index_dir)
    manifest_path = _latest_manifest_path(clean_index_dir, family)
    if manifest_path is None:
        return PersistentIndexVerification(
            analysis_family=family,
            status="missing",
            message=(
                "No persistent ANN index manifest found for "
                f"analysis_family={family} in {clean_index_dir}"
            ),
            index_dir=clean_index_dir,
            manifest_path=None,
            artifact_path=None,
            reasons=("manifest_missing",),
            manifest=None,
        )

    try:
        manifest = _read_manifest(manifest_path)
        parsed = _parse_manifest(manifest)
        artifact_path = _artifact_path_from_manifest(
            clean_index_dir,
            manifest,
        )
    except (OSError, TypeError, ValueError) as error:
        return _verification_result(
            family,
            status="error",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=None,
            manifest=None,
            reasons=("manifest_invalid",),
            detail=str(error),
        )

    if not artifact_path.exists():
        return _verification_result(
            family,
            status="stale",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            manifest=manifest,
            reasons=("artifact_missing",),
        )

    try:
        snapshot = load_embedding_index_snapshot(
            repository,
            family,
            analysis_output,
        )
    except (OSError, TypeError, ValueError) as error:
        return _verification_result(
            family,
            status="stale",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            manifest=manifest,
            reasons=("repository_snapshot",),
            detail=str(error),
        )

    reasons = _manifest_mismatch_reasons(
        family,
        manifest,
        parsed,
        snapshot,
        artifact_path,
    )
    if reasons:
        return _verification_result(
            family,
            status="stale",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            manifest=manifest,
            reasons=tuple(reasons),
            snapshot=snapshot,
        )
    if not _hnswlib_available():
        return _verification_result(
            family,
            status="unsupported",
            index_dir=clean_index_dir,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
            manifest=manifest,
            reasons=("hnswlib_missing",),
            detail=_hnsw_dependency_message("load persistent ANN indexes"),
            snapshot=snapshot,
        )

    return PersistentIndexVerification(
        analysis_family=family,
        status="ok",
        message=(f"Persistent ANN index is current for analysis_family={family}"),
        index_dir=clean_index_dir,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        reasons=(),
        manifest=manifest,
        snapshot=snapshot,
    )


def clear_persistent_indexes(
    index_dir: str | Path,
    *,
    analysis_family: str | None = None,
) -> PersistentIndexClearResult:
    family = (
        normalize_index_family(analysis_family) if analysis_family is not None else None
    )
    clean_index_dir = _safe_index_dir(index_dir)
    if not clean_index_dir.exists():
        return PersistentIndexClearResult(
            index_dir=clean_index_dir,
            analysis_family=family,
            deleted_files=(),
        )
    if not clean_index_dir.is_dir():
        raise ValueError(f"Index path is not a directory: {clean_index_dir}")

    deleted: list[Path] = []
    for path in sorted(
        clean_index_dir.iterdir(),
        key=lambda item: item.name,
    ):
        if not path.is_file() or not _is_owned_index_file(
            path.name,
            family,
        ):
            continue
        _assert_inside_directory(clean_index_dir, path)
        path.unlink()
        deleted.append(path)
    return PersistentIndexClearResult(
        index_dir=clean_index_dir,
        analysis_family=family,
        deleted_files=tuple(deleted),
    )


def benchmark_persistent_index(
    repository: AnalysisRepository,
    analysis_family: str,
    *,
    analysis_output: AnalysisOutput,
    index_dir: str | Path | None = None,
    threshold: float = DEFAULT_RECALL_THRESHOLD,
    recall_k: int = 50,
    k_values: Sequence[int] | None = None,
    seed_count: int = 20,
    random_seed: int = 123,
) -> dict[str, Any]:
    family = normalize_index_family(analysis_family)
    clean_threshold = _threshold_value(threshold)
    clean_recall_k = _positive_int(recall_k, "recall_k")
    clean_k_values = _benchmark_k_values(
        k_values,
        clean_recall_k,
    )
    clean_seed_count = _positive_int(seed_count, "seed_count")
    clean_random_seed = int(random_seed)
    verification = verify_persistent_index(
        repository,
        family,
        analysis_output=analysis_output,
        index_dir=index_dir,
    )
    if not verification.is_usable:
        raise ValueError(
            f"Cannot benchmark persistent ANN index: {verification.message}"
        )
    snapshot = verification.snapshot
    if snapshot is None:
        raise ValueError("Persistent ANN verification returned no embedding snapshot")
    if snapshot.embedding_count < 2:
        raise ValueError("At least two embeddings are required to benchmark recall")

    persistent_searcher = load_persistent_index_searcher(verification)
    exact_backend = ExactVectorSearchBackend()
    seed_indices = _sample_seed_indices(
        snapshot.embedding_count,
        clean_seed_count,
        clean_random_seed,
    )
    exact_latencies: list[float] = []
    ann_latencies: list[float] = []
    recall_values: dict[int, list[float]] = {k_value: [] for k_value in clean_k_values}
    max_limit = min(
        snapshot.embedding_count,
        max(clean_k_values) + 1,
    )

    for seed_index in seed_indices:
        query = snapshot.matrix[seed_index]
        seed_target = snapshot.targets[seed_index]
        exact_seconds, exact_hits = _timed(
            lambda query=query: exact_backend.search(
                snapshot.matrix,
                snapshot.targets,
                query,
                max_limit,
            )
        )
        ann_seconds, ann_hits = _timed(
            lambda query=query: persistent_searcher.search(
                query,
                max_limit,
            )
        )
        exact_latencies.append(exact_seconds)
        ann_latencies.append(ann_seconds)
        exact_targets = _candidates_without_seed(
            exact_hits,
            seed_target,
        )
        ann_targets = _candidates_without_seed(
            ann_hits,
            seed_target,
        )
        for k_value in clean_k_values:
            recall_values[k_value].append(
                _recall_at_k(
                    exact_targets,
                    ann_targets,
                    k_value,
                )
            )

    recalls = {
        f"recall_at_{k_value}": _recall_summary(values)
        for k_value, values in recall_values.items()
    }
    primary_recall = recalls[f"recall_at_{clean_recall_k}"]["mean"]
    status = (
        "pass"
        if primary_recall is not None and primary_recall >= clean_threshold
        else "fail"
    )
    manifest = verification.manifest or {}
    artifact_path = verification.artifact_path
    ann_latency = _latency_summary(ann_latencies)
    exact_latency = _latency_summary(exact_latencies)
    index_size_bytes = _file_size(artifact_path)
    return {
        "benchmark": "persistent_ann_recall",
        "schema_version": PERSISTENT_INDEX_SCHEMA_VERSION,
        "generated_at": _utc_timestamp(),
        "status": status,
        "analysis_family": family,
        "backend": persistent_searcher.backend_name,
        "metric": PERSISTENT_INDEX_METRIC,
        "track_count": snapshot.embedding_count,
        "compare": "exact_cosine",
        "threshold": clean_threshold,
        "primary_recall_k": clean_recall_k,
        "seed_count": len(seed_indices),
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "index_size_bytes": index_size_bytes,
        "build_seconds": manifest.get("build_seconds"),
        "verify_status": verification.status,
        "recall_at_10": recalls["recall_at_10"]["mean"],
        "recall_at_50": recalls["recall_at_50"]["mean"],
        "recall_at_100": recalls["recall_at_100"]["mean"],
        "p50_latency": ann_latency["p50_ms"],
        "p95_latency": ann_latency["p95_ms"],
        "latency_unit": "ms",
        "recall": recalls,
        "latency": {
            "exact": exact_latency,
            "ann": ann_latency,
        },
        "index": {
            "index_dir": str(verification.index_dir),
            "manifest_path": (
                str(verification.manifest_path)
                if verification.manifest_path is not None
                else None
            ),
            "artifact_path": (
                str(artifact_path) if artifact_path is not None else None
            ),
            "index_size_bytes": index_size_bytes,
            "created_at": manifest.get("created_at"),
            "build_seconds": manifest.get("build_seconds"),
            "settings": manifest.get("settings", {}),
        },
    }


def load_persistent_index_searcher(
    verification: PersistentIndexVerification,
) -> PersistentIndexSearcher:
    if not verification.is_usable:
        raise VectorIndexUnavailable(
            f"Persistent ANN index is not usable: {verification.message}"
        )
    if (
        verification.artifact_path is None
        or verification.manifest is None
        or verification.snapshot is None
    ):
        raise VectorIndexUnavailable(
            "Persistent ANN verification did not include the complete "
            "artifact and snapshot identity"
        )
    parsed = _parse_manifest(verification.manifest)
    artifact = verification.manifest["artifact"]
    if not isinstance(artifact, dict):
        raise VectorIndexUnavailable("Persistent ANN artifact metadata is invalid")
    return HnswPersistentIndexSearcher(
        verification.artifact_path,
        targets=verification.snapshot.targets,
        dim=verification.snapshot.embedding_dim,
        ef_search=parsed.settings["ef_search"],
        expected_size_bytes=int(artifact["size_bytes"]),
        expected_sha256=str(artifact["sha256"]),
    )


def _validate_index_output(
    output: AnalysisOutput,
    analysis_family: str,
) -> None:
    if not isinstance(output, AnalysisOutput):
        raise TypeError("active_analysis_output must return an AnalysisOutput")
    if output.key != (analysis_family, "embedding"):
        raise ValueError(
            "Active analysis output does not match the requested embedding "
            f"family: {output.key!r}"
        )
    validate_production_contract(output.contract)
    if output.contract.encoding != FLOAT32_LE_ENCODING:
        raise ValueError("Persistent ANN requires float32-le embedding encoding")
    if output.contract.normalization != "l2":
        raise ValueError("Persistent ANN supports only normalization='l2' embeddings")
    if output.contract.dim is None or output.contract.dim <= 0:
        raise ValueError("Persistent ANN requires a positive embedding dimension")


def _active_index_output(
    repository: AnalysisRepository,
    analysis_family: str,
    analysis_output: AnalysisOutput,
) -> AnalysisOutput:
    _validate_index_output(analysis_output, analysis_family)
    output = repository.active_analysis_output(
        analysis_family,
        "embedding",
    )
    if output is None:
        raise ValueError(
            f"No active {analysis_family}/embedding contract is registered"
        )
    _validate_index_output(output, analysis_family)
    if (
        output.contract_hash != analysis_output.contract_hash
        or output.contract.canonical_payload_json
        != analysis_output.contract.canonical_payload_json
    ):
        raise VectorIndexUnavailable(
            "Current runtime embedding contract does not match the active "
            f"{analysis_family!r} contract; reanalysis is required before "
            "building or using an ANN index"
        )
    return analysis_output


def _write_hnsw_index(
    artifact_path: Path,
    snapshot: EmbeddingIndexSnapshot,
    settings: Mapping[str, int],
) -> None:
    hnswlib = _load_hnswlib()
    index = hnswlib.Index(
        space=PERSISTENT_INDEX_HNSW_SPACE,
        dim=snapshot.embedding_dim,
    )
    index.init_index(
        max_elements=snapshot.embedding_count,
        ef_construction=int(settings["ef_construction"]),
        M=int(settings["m"]),
    )
    index.add_items(
        snapshot.matrix,
        np.arange(snapshot.embedding_count, dtype=np.int64),
    )
    index.set_ef(int(settings["ef_search"]))
    index.save_index(str(artifact_path))


def _build_manifest(
    snapshot: EmbeddingIndexSnapshot,
    *,
    backend: str,
    settings: dict[str, int],
    artifact_path: Path,
    build_seconds: float,
) -> dict[str, Any]:
    return {
        "schema_version": PERSISTENT_INDEX_SCHEMA_VERSION,
        "analysis_family": snapshot.analysis_family,
        "backend": backend,
        "metric": PERSISTENT_INDEX_METRIC,
        "hnsw_space": PERSISTENT_INDEX_HNSW_SPACE,
        "contract": _contract_manifest(snapshot.output.contract),
        "catalog_uuid": snapshot.catalog_uuid,
        "targets": [_target_manifest(target) for target in snapshot.targets],
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "target_identity_hash": snapshot.target_identity_hash,
        "vector_content_hash": snapshot.vector_content_hash,
        "created_at": _utc_timestamp(),
        "build_seconds": build_seconds,
        "settings": dict(settings),
        "artifact": {
            "file_name": artifact_path.name,
            "size_bytes": _file_size(artifact_path),
            "sha256": _sha256_file(artifact_path),
        },
    }


def _manifest_mismatch_reasons(
    analysis_family: str,
    manifest: dict[str, Any],
    parsed: _ParsedManifest,
    snapshot: EmbeddingIndexSnapshot,
    artifact_path: Path,
) -> list[str]:
    reasons: list[str] = []
    expected_values: dict[str, object] = {
        "schema_version": PERSISTENT_INDEX_SCHEMA_VERSION,
        "analysis_family": analysis_family,
        "backend": HNSW_VECTOR_BACKEND_NAME,
        "metric": PERSISTENT_INDEX_METRIC,
        "hnsw_space": PERSISTENT_INDEX_HNSW_SPACE,
        "catalog_uuid": snapshot.catalog_uuid,
        "embedding_count": snapshot.embedding_count,
        "embedding_dim": snapshot.embedding_dim,
        "target_identity_hash": snapshot.target_identity_hash,
        "vector_content_hash": snapshot.vector_content_hash,
    }
    for key, expected in expected_values.items():
        if manifest.get(key) != expected:
            reasons.append(key)
    if (
        parsed.contract.canonical_payload_json
        != snapshot.output.contract.canonical_payload_json
    ):
        reasons.append("contract")
    if parsed.targets != snapshot.targets:
        reasons.append("targets")

    artifact = manifest["artifact"]
    if not isinstance(artifact, dict):
        reasons.append("artifact")
        return reasons
    if int(artifact["size_bytes"]) != _file_size(artifact_path):
        reasons.append("artifact_size")
    if str(artifact["sha256"]) != _sha256_file(artifact_path):
        reasons.append("artifact_sha256")
    return reasons


def _parse_manifest(manifest: dict[str, Any]) -> _ParsedManifest:
    _require_exact_keys(
        manifest,
        _MANIFEST_KEYS,
        "persistent ANN manifest",
    )
    if manifest["schema_version"] != PERSISTENT_INDEX_SCHEMA_VERSION:
        raise ValueError("Persistent ANN manifest schema_version is not current")
    normalize_index_family(
        _required_text(
            manifest["analysis_family"],
            "analysis_family",
        )
    )
    normalize_index_backend(
        _required_text(
            manifest["backend"],
            "backend",
        )
    )
    if manifest["metric"] != PERSISTENT_INDEX_METRIC:
        raise ValueError("Persistent ANN manifest metric must be cosine")
    if manifest["hnsw_space"] != PERSISTENT_INDEX_HNSW_SPACE:
        raise ValueError("Persistent ANN manifest HNSW space must be ip")

    contract = _parse_contract_manifest(manifest["contract"])
    if (
        contract.analysis_family != manifest["analysis_family"]
        or contract.output_kind != "embedding"
    ):
        raise ValueError("Persistent ANN manifest contract does not match its family")
    validate_production_contract(contract)
    if contract.normalization != "l2":
        raise ValueError("Persistent ANN manifest contract is not l2-normalized")

    catalog_uuid = _required_text(
        manifest["catalog_uuid"],
        "catalog_uuid",
    )
    targets = _parse_target_manifests(
        manifest["targets"],
        catalog_uuid,
    )
    embedding_count = _non_negative_int(
        manifest["embedding_count"],
        "embedding_count",
    )
    embedding_dim = _positive_int(
        manifest["embedding_dim"],
        "embedding_dim",
    )
    if embedding_count != len(targets):
        raise ValueError(
            "Persistent ANN manifest embedding_count does not match targets"
        )
    if contract.dim != embedding_dim:
        raise ValueError(
            "Persistent ANN manifest embedding_dim does not match contract"
        )
    target_hash = _sha256_identity(
        manifest["target_identity_hash"],
        "target_identity_hash",
    )
    if target_hash != _target_identity_hash(targets):
        raise ValueError("Persistent ANN manifest target identity self-hash is invalid")
    _sha256_identity(
        manifest["vector_content_hash"],
        "vector_content_hash",
    )
    _required_text(manifest["created_at"], "created_at")
    build_seconds = _finite_non_negative_number(
        manifest["build_seconds"],
        "build_seconds",
    )
    if build_seconds < 0.0:
        raise ValueError("build_seconds must not be negative")

    settings = manifest["settings"]
    if not isinstance(settings, Mapping):
        raise ValueError("Persistent ANN manifest settings must be an object")
    _require_exact_keys(
        settings,
        _SETTINGS_MANIFEST_KEYS,
        "persistent ANN settings",
    )
    clean_settings = {
        key: _positive_int(settings[key], key) for key in _SETTINGS_MANIFEST_KEYS
    }

    artifact = manifest["artifact"]
    if not isinstance(artifact, Mapping):
        raise ValueError("Persistent ANN manifest artifact must be an object")
    _require_exact_keys(
        artifact,
        _ARTIFACT_MANIFEST_KEYS,
        "persistent ANN artifact",
    )
    file_name = _required_text(
        artifact["file_name"],
        "artifact.file_name",
    )
    if Path(file_name).name != file_name:
        raise ValueError("Persistent ANN artifact file_name must be a plain file name")
    _non_negative_int(
        artifact["size_bytes"],
        "artifact.size_bytes",
    )
    _sha256_identity(
        artifact["sha256"],
        "artifact.sha256",
    )
    return _ParsedManifest(
        contract=contract,
        targets=targets,
        settings=clean_settings,
    )


def _parse_contract_manifest(value: object) -> ContractIdentity:
    if not isinstance(value, Mapping):
        raise ValueError("Persistent ANN manifest contract must be an object")
    _require_exact_keys(
        value,
        _CONTRACT_MANIFEST_KEYS,
        "persistent ANN contract",
    )
    contract_hash = _sha256_identity(
        value["contract_hash"],
        "contract.contract_hash",
    )
    canonical_payload = value["canonical_payload"]
    if not isinstance(canonical_payload, Mapping):
        raise ValueError("Persistent ANN contract canonical_payload must be an object")
    try:
        payload_json = json.dumps(
            canonical_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        contract = ContractIdentity.from_canonical_payload_json(payload_json)
    except (
        ContractIdentityError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "Persistent ANN manifest contract identity is invalid"
        ) from error
    if contract.contract_hash != contract_hash:
        raise ValueError("Persistent ANN manifest contract self-hash is invalid")
    return contract


def _parse_target_manifests(
    value: object,
    catalog_uuid: str,
) -> tuple[AnalysisTarget, ...]:
    if not isinstance(value, list):
        raise ValueError("Persistent ANN manifest targets must be a list")
    targets: list[AnalysisTarget] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("Persistent ANN manifest target must be an object")
        _require_exact_keys(
            item,
            _TARGET_MANIFEST_KEYS,
            "persistent ANN target",
        )
        target = AnalysisTarget(
            catalog_uuid=_required_text(
                item["catalog_uuid"],
                "target.catalog_uuid",
            ),
            track_id=_positive_int(
                item["track_id"],
                "target.track_id",
            ),
            track_uuid=_required_text(
                item["track_uuid"],
                "target.track_uuid",
            ),
            content_generation=_positive_int(
                item["content_generation"],
                "target.content_generation",
            ),
        )
        if target.catalog_uuid != catalog_uuid:
            raise ValueError(
                "Persistent ANN target catalog UUID does not match manifest"
            )
        targets.append(target)
    target_tuple = tuple(targets)
    if len(set(target_tuple)) != len(target_tuple):
        raise ValueError("Persistent ANN manifest contains duplicate target identities")
    track_ids = [target.track_id for target in target_tuple]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError(
            "Persistent ANN manifest contains conflicting identities for one track ID"
        )
    return target_tuple


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Persistent ANN manifest JSON is invalid: {error.msg}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError("Persistent ANN manifest JSON must contain an object")
    return payload


def _artifact_path_from_manifest(
    index_dir: Path,
    manifest: Mapping[str, Any],
) -> Path:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping):
        raise ValueError("Persistent ANN artifact metadata is missing")
    file_name = _required_text(
        artifact.get("file_name"),
        "artifact.file_name",
    )
    if Path(file_name).name != file_name:
        raise ValueError("Persistent ANN artifact file_name must be a plain file name")
    artifact_path = (index_dir / file_name).resolve(strict=False)
    _assert_inside_directory(index_dir, artifact_path)
    return artifact_path


def _artifact_paths(
    index_dir: Path,
    snapshot: EmbeddingIndexSnapshot,
    *,
    build_token: str,
) -> tuple[Path, Path]:
    contract_token = snapshot.output.contract.contract_hash.removeprefix("sha256:")[:16]
    vector_token = snapshot.vector_content_hash.removeprefix("sha256:")[:16]
    base_name = (
        f"ann_{snapshot.analysis_family}_{contract_token}_{vector_token}_{build_token}"
    )
    return (
        index_dir / f"{base_name}.hnsw",
        index_dir / f"{base_name}{PERSISTENT_INDEX_MANIFEST_SUFFIX}",
    )


def _latest_manifest_path(
    index_dir: Path,
    analysis_family: str,
) -> Path | None:
    if not index_dir.exists() or not index_dir.is_dir():
        return None
    prefix = f"ann_{analysis_family}_"
    candidates = [
        path
        for path in index_dir.iterdir()
        if path.is_file()
        and path.name.startswith(prefix)
        and path.name.endswith(PERSISTENT_INDEX_MANIFEST_SUFFIX)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda path: (
            path.stat().st_mtime_ns,
            path.name,
        ),
    )


def _verification_result(
    analysis_family: str,
    *,
    status: str,
    index_dir: Path,
    manifest_path: Path | None,
    artifact_path: Path | None,
    manifest: dict[str, Any] | None,
    reasons: tuple[str, ...],
    detail: str | None = None,
    snapshot: EmbeddingIndexSnapshot | None = None,
) -> PersistentIndexVerification:
    reason_text = ", ".join(reasons)
    message = (
        f"Persistent ANN index {status} for "
        f"analysis_family={analysis_family}: {reason_text}"
    )
    if detail:
        message = f"{message} ({detail})"
    return PersistentIndexVerification(
        analysis_family=analysis_family,
        status=status,
        message=message,
        index_dir=index_dir,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        reasons=reasons,
        manifest=manifest,
        snapshot=snapshot,
    )


def _contract_manifest(
    contract: ContractIdentity,
) -> dict[str, object]:
    return {
        "contract_hash": contract.contract_hash,
        "canonical_payload": contract.canonical_payload,
    }


def _target_manifest(
    target: AnalysisTarget,
) -> dict[str, object]:
    return {
        "catalog_uuid": target.catalog_uuid,
        "track_id": target.track_id,
        "track_uuid": target.track_uuid,
        "content_generation": target.content_generation,
    }


def _target_identity_hash(
    targets: Sequence[AnalysisTarget],
) -> str:
    return _sha256_json([_target_manifest(target) for target in targets])


def _vector_content_hash(
    output: AnalysisOutput,
    targets: Sequence[AnalysisTarget],
    matrix: np.ndarray,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(output.contract.canonical_payload_json.encode("utf-8"))
    hasher.update(b"\n")
    for target, vector in zip(targets, matrix, strict=True):
        hasher.update(
            json.dumps(
                _target_manifest(target),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        )
        hasher.update(b"\0")
        hasher.update(
            np.ascontiguousarray(
                vector,
                dtype="<f4",
            ).tobytes()
        )
        hasher.update(b"\n")
    return f"sha256:{hasher.hexdigest()}"


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _repository_catalog_uuid(
    repository: AnalysisRepository,
) -> str:
    return _required_text(
        getattr(repository, "catalog_uuid", None),
        "repository.catalog_uuid",
    )


def _repository_path(
    repository: AnalysisRepository,
) -> Path:
    raw_path = getattr(repository, "path", None)
    if raw_path is None:
        raise TypeError("Analysis repository must expose its Core database path")
    return Path(raw_path).expanduser().resolve(strict=False)


def _safe_index_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if resolved == resolved.parent:
        raise ValueError(
            f"Refusing to use a filesystem root as an index directory: {resolved}"
        )
    return resolved


def _assert_inside_directory(
    directory: Path,
    path: Path,
) -> None:
    resolved_directory = directory.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_directory)
    except ValueError as error:
        raise ValueError(
            f"Refusing to access outside the index directory: {resolved_path}"
        ) from error


def _is_owned_index_file(
    file_name: str,
    analysis_family: str | None,
) -> bool:
    if not file_name.startswith("ann_"):
        return False
    if analysis_family is not None and not file_name.startswith(
        f"ann_{analysis_family}_"
    ):
        return False
    return file_name.endswith(
        (
            ".hnsw",
            PERSISTENT_INDEX_MANIFEST_SUFFIX,
        )
    )


def _remove_stale_owned_files(
    index_dir: Path,
    analysis_family: str,
    *,
    keep: set[Path],
) -> None:
    resolved_keep = {path.resolve(strict=False) for path in keep}
    for path in index_dir.iterdir():
        if (
            not path.is_file()
            or not _is_owned_index_file(
                path.name,
                analysis_family,
            )
            or path.resolve(strict=False) in resolved_keep
        ):
            continue
        _assert_inside_directory(index_dir, path)
        path.unlink()


def _remove_file_if_present(path: Path) -> None:
    if not path.exists():
        return
    _assert_inside_directory(path.parent, path)
    if path.is_file():
        path.unlink()


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    field_name: str,
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    raise ValueError(f"{field_name} keys mismatch; missing={missing}, extra={extra}")


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sha256_identity(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    if (
        len(text) != len("sha256:") + 64
        or not text.startswith("sha256:")
        or text != text.lower()
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex>")
    try:
        int(text.removeprefix("sha256:"), 16)
    except ValueError as error:
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex>") from error
    return text


def _benchmark_k_values(
    k_values: Sequence[int] | None,
    recall_k: int,
) -> tuple[int, ...]:
    values = [recall_k, *DEFAULT_RECALL_K_VALUES]
    if k_values is not None:
        values.extend(k_values)
    return tuple(sorted({_positive_int(value, "k") for value in values}))


def _sample_seed_indices(
    embedding_count: int,
    seed_count: int,
    random_seed: int,
) -> tuple[int, ...]:
    clean_seed_count = min(seed_count, embedding_count)
    rng = np.random.default_rng(random_seed)
    sampled = rng.choice(
        np.arange(embedding_count),
        size=clean_seed_count,
        replace=False,
    )
    return tuple(int(index) for index in sorted(sampled.tolist()))


def _candidates_without_seed(
    hits: Sequence[VectorSearchHit],
    seed_target: AnalysisTarget,
) -> tuple[AnalysisTarget, ...]:
    return tuple(hit.target for hit in hits if hit.target != seed_target)


def _recall_at_k(
    exact_targets: Sequence[AnalysisTarget],
    ann_targets: Sequence[AnalysisTarget],
    k: int,
) -> float:
    expected = tuple(exact_targets[:k])
    if not expected:
        return 1.0
    found = set(ann_targets[:k])
    return len(found.intersection(expected)) / len(expected)


def _recall_summary(
    values: Sequence[float],
) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
    }


def _latency_summary(
    values: Sequence[float],
) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "p50_ms": _percentile_ms(values, 50.0),
        "p95_ms": _percentile_ms(values, 95.0),
    }


def _percentile_ms(
    values: Sequence[float],
    percentile: float,
) -> float | None:
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


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _finite_non_negative_number(
    value: object,
    name: str,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite non-negative number") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


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
        raise VectorIndexUnavailable(
            _hnsw_dependency_message("use persistent ANN indexes")
        ) from error


def _hnswlib_available() -> bool:
    try:
        importlib.import_module("hnswlib")
    except ImportError:
        return False
    return True


def _hnsw_dependency_message(action: str) -> str:
    return (
        "Persistent ANN indexes need optional dependency 'hnswlib' to "
        f"{action}. Install it with "
        "`python -m pip install -e .[ann]`."
    )

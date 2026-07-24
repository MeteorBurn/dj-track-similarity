from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import dj_track_similarity.ann_index as ann_index
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
)
from dj_track_similarity.ann_index import (
    PersistentAnnVectorSearchBackend,
    build_persistent_index,
    load_embedding_index_snapshot,
    normalize_index_backend,
    normalize_index_family,
    verify_persistent_index,
)
from dj_track_similarity.vector_index import VectorIndexUnavailable


@dataclass
class FakeAnalysisRepository:
    path: Path
    catalog_uuid: str
    output: AnalysisOutput
    rows: tuple[AnalysisVectorRow, ...]
    calls: list[tuple[object, ...]] = field(default_factory=list)

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        self.calls.append(("active_analysis_output", analysis_family, output_kind))
        if (analysis_family, output_kind) != self.output.key:
            return None
        return self.output

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: object = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        self.calls.append(("load_analysis_vectors", output, targets))
        assert output.contract.canonical_payload_json == (
            self.output.contract.canonical_payload_json
        )
        assert targets is None
        return self.rows

    def connect(self) -> None:
        raise AssertionError("ANN runtime must not bypass AnalysisRepository with SQL")


class FakeHnswModule:
    class Index:
        def __init__(self, *, space: str, dim: int) -> None:
            assert space == "ip"
            self.dim = dim
            self.matrix = np.empty((0, dim), dtype=np.float32)
            self.labels = np.empty((0,), dtype=np.int64)

        def init_index(
            self,
            *,
            max_elements: int,
            ef_construction: int,
            M: int,
        ) -> None:
            assert max_elements > 0
            assert ef_construction > 0
            assert M > 0

        def add_items(
            self,
            matrix: np.ndarray,
            labels: np.ndarray,
        ) -> None:
            self.matrix = np.asarray(
                matrix,
                dtype=np.float32,
            ).copy()
            self.labels = np.asarray(
                labels,
                dtype=np.int64,
            ).copy()

        def set_ef(self, value: int) -> None:
            assert value > 0

        def save_index(self, path: str) -> None:
            with Path(path).open("wb") as stream:
                np.savez(
                    stream,
                    matrix=self.matrix,
                    labels=self.labels,
                )

        def load_index(
            self,
            path: str,
            *,
            max_elements: int,
        ) -> None:
            with np.load(path) as payload:
                self.matrix = np.asarray(
                    payload["matrix"],
                    dtype=np.float32,
                )
                self.labels = np.asarray(
                    payload["labels"],
                    dtype=np.int64,
                )
            assert self.matrix.shape == (max_elements, self.dim)

        def knn_query(
            self,
            query: np.ndarray,
            *,
            k: int,
        ) -> tuple[np.ndarray, np.ndarray]:
            query_vector = np.asarray(
                query,
                dtype=np.float32,
            ).reshape(-1)
            scores = self.matrix @ query_vector
            order = np.argsort(-scores, kind="stable")[:k]
            return (
                self.labels[order].reshape(1, -1),
                (1.0 - scores[order]).reshape(1, -1),
            )


@pytest.fixture
def fake_hnsw(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeHnswModule:
    module = FakeHnswModule()
    monkeypatch.setattr(ann_index, "_load_hnswlib", lambda: module)
    monkeypatch.setattr(
        ann_index,
        "_hnswlib_available",
        lambda: True,
    )
    return module


def test_build_manifest_binds_full_v7_identity_and_searches_by_target(
    tmp_path: Path,
    fake_hnsw: FakeHnswModule,
) -> None:
    del fake_hnsw
    repository = _repository(tmp_path)
    index_dir = tmp_path / "indexes"

    build = build_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    verification = verify_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    snapshot = load_embedding_index_snapshot(
        repository,
        "mert",
        repository.output,
    )
    manifest = json.loads(build.manifest_path.read_text(encoding="utf-8"))

    assert verification.status == "ok"
    assert manifest["analysis_family"] == "mert"
    assert manifest["backend"] == "hnswlib"
    assert manifest["metric"] == "cosine"
    assert manifest["hnsw_space"] == "ip"
    assert manifest["catalog_uuid"] == repository.catalog_uuid
    assert manifest["contract"] == {
        "contract_hash": repository.output.contract.contract_hash,
        "canonical_payload": repository.output.contract.canonical_payload,
    }
    assert manifest["targets"] == [
        {
            "catalog_uuid": target.catalog_uuid,
            "track_id": target.track_id,
            "track_uuid": target.track_uuid,
            "content_generation": target.content_generation,
        }
        for target in snapshot.targets
    ]
    assert "embedding_key" not in manifest
    assert "adapter" not in manifest
    assert "db_path_hash" not in manifest

    backend = PersistentAnnVectorSearchBackend(
        repository,
        analysis_family="mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    hits = backend.search(
        snapshot.matrix,
        snapshot.targets,
        snapshot.matrix[0],
        2,
    )

    assert [hit.target for hit in hits] == [
        snapshot.targets[0],
        snapshot.targets[1],
    ]
    assert [hit.index for hit in hits] == [0, 1]
    assert all(
        target.catalog_uuid == repository.catalog_uuid
        for target in (hit.target for hit in hits)
    )
    assert repository.calls


def test_generation_change_makes_index_stale_without_exact_fallback(
    tmp_path: Path,
    fake_hnsw: FakeHnswModule,
) -> None:
    del fake_hnsw
    repository = _repository(tmp_path)
    index_dir = tmp_path / "indexes"
    build_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    changed = repository.rows[1]
    changed_target = AnalysisTarget(
        catalog_uuid=changed.target.catalog_uuid,
        track_id=changed.target.track_id,
        track_uuid=changed.target.track_uuid,
        content_generation=changed.target.content_generation + 1,
    )
    repository.rows = (
        repository.rows[0],
        AnalysisVectorRow(
            target=changed_target,
            output=changed.output,
            vector=changed.vector,
        ),
        repository.rows[2],
    )
    current = load_embedding_index_snapshot(
        repository,
        "mert",
        repository.output,
    )

    verification = verify_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    backend = PersistentAnnVectorSearchBackend(
        repository,
        analysis_family="mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )

    assert verification.status == "stale"
    assert "targets" in verification.reasons
    assert "target_identity_hash" in verification.reasons
    with pytest.raises(
        VectorIndexUnavailable,
        match="not usable|stale",
    ):
        backend.search(
            current.matrix,
            current.targets,
            current.matrix[0],
            2,
        )
    assert not hasattr(backend, "allow_exact_fallback")
    assert not hasattr(backend, "fallback_backend")


def test_artifact_and_contract_tampering_are_rejected(
    tmp_path: Path,
    fake_hnsw: FakeHnswModule,
) -> None:
    del fake_hnsw
    repository = _repository(tmp_path)
    index_dir = tmp_path / "indexes"
    build = build_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    with build.artifact_path.open("ab") as stream:
        stream.write(b"tampered")

    artifact_tamper = verify_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )

    assert artifact_tamper.status == "stale"
    assert "artifact_size" in artifact_tamper.reasons
    assert "artifact_sha256" in artifact_tamper.reasons

    build = build_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    manifest: dict[str, Any] = json.loads(
        build.manifest_path.read_text(encoding="utf-8")
    )
    manifest["contract"]["canonical_payload"]["model_version"] = "tampered-model"
    build.manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    contract_tamper = verify_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )

    assert contract_tamper.status == "error"
    assert contract_tamper.reasons == ("manifest_invalid",)
    assert "self-hash" in contract_tamper.message


def test_search_rejects_noncurrent_input_target_or_vector_snapshot(
    tmp_path: Path,
    fake_hnsw: FakeHnswModule,
) -> None:
    del fake_hnsw
    repository = _repository(tmp_path)
    index_dir = tmp_path / "indexes"
    build_persistent_index(
        repository,
        "mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    snapshot = load_embedding_index_snapshot(
        repository,
        "mert",
        repository.output,
    )
    backend = PersistentAnnVectorSearchBackend(
        repository,
        analysis_family="mert",
        analysis_output=repository.output,
        index_dir=index_dir,
    )
    wrong_target = AnalysisTarget(
        catalog_uuid=snapshot.catalog_uuid,
        track_id=snapshot.targets[1].track_id,
        track_uuid="different-track-uuid",
        content_generation=snapshot.targets[1].content_generation,
    )
    wrong_targets = (
        snapshot.targets[0],
        wrong_target,
        snapshot.targets[2],
    )

    with pytest.raises(
        VectorIndexUnavailable,
        match="target identities",
    ):
        backend.search(
            snapshot.matrix,
            wrong_targets,
            snapshot.matrix[0],
            2,
        )

    changed_matrix = snapshot.matrix.copy()
    changed_matrix[[1, 2]] = changed_matrix[[2, 1]]
    with pytest.raises(
        VectorIndexUnavailable,
        match="input vectors",
    ):
        backend.search(
            changed_matrix,
            snapshot.targets,
            snapshot.matrix[0],
            2,
        )


def test_ann_accepts_only_explicit_l2_ml_families_and_hnsw_backend(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    for family in ("maest", "mert", "muq", "clap"):
        assert normalize_index_family(family) == family
    for unsupported in (
        "sonara",
        "sonara2",
        "sonara2vocal",
        "embedding",
    ):
        with pytest.raises(ValueError, match="Unsupported ANN"):
            normalize_index_family(unsupported)
    assert normalize_index_backend("hnswlib") == "hnswlib"
    for unsupported_backend in (
        "auto",
        "hnsw",
        "exact",
        "exact_numpy",
        "exact-numpy",
    ):
        with pytest.raises(ValueError, match="explicit backend"):
            normalize_index_backend(unsupported_backend)

    absent = FakeAnalysisRepository(
        path=repository.path,
        catalog_uuid=repository.catalog_uuid,
        output=repository.output,
        rows=(),
    )
    absent.active_analysis_output = lambda *_args: None  # type: ignore[method-assign]
    with pytest.raises(
        ValueError,
        match="No active mert/embedding contract",
    ):
        load_embedding_index_snapshot(absent, "mert", repository.output)

    non_l2_rows = list(repository.rows)
    non_l2_rows[0] = AnalysisVectorRow(
        target=non_l2_rows[0].target,
        output=non_l2_rows[0].output,
        vector=non_l2_rows[0].vector * 2.0,
    )
    repository.rows = tuple(non_l2_rows)
    with pytest.raises(
        ValueError,
        match="unit-normalized",
    ):
        load_embedding_index_snapshot(
            repository,
            "mert",
            repository.output,
        )


def _repository(tmp_path: Path) -> FakeAnalysisRepository:
    catalog_uuid = "catalog-ann-v7"
    output = current_embedding_analysis_output("mert")
    vectors = (
        _unit_vector(0),
        _unit_vector(0, second_index=1, second_value=0.1),
        _unit_vector(1),
    )
    targets = tuple(
        AnalysisTarget(
            catalog_uuid=catalog_uuid,
            track_id=index,
            track_uuid=f"track-uuid-{index}",
            content_generation=1,
        )
        for index in (1, 2, 3)
    )
    rows = tuple(
        AnalysisVectorRow(
            target=target,
            output=output,
            vector=vector,
        )
        for target, vector in zip(targets, vectors, strict=True)
    )
    return FakeAnalysisRepository(
        path=tmp_path / "library.sqlite",
        catalog_uuid=catalog_uuid,
        output=output,
        rows=rows,
    )


def _unit_vector(
    index: int,
    *,
    second_index: int | None = None,
    second_value: float = 0.0,
) -> np.ndarray:
    vector = np.zeros((768,), dtype=np.float32)
    vector[index] = 1.0
    if second_index is not None:
        vector[second_index] = second_value
    vector /= np.linalg.norm(vector)
    return vector

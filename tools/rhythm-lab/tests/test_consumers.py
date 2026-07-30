from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import threading
import uuid

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.analysis_models import (  # noqa: E402
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    current_embedding_spec,
)
from dj_track_similarity.classifier_manifest import (  # noqa: E402
    CLASSIFIER_PUBLICATION_POINTER_NAME,
    load_classifier_manifest_summary,
    resolve_classifier_artifact_paths,
)
from dj_track_similarity.classifier_scoring import promoted_classifiers  # noqa: E402
from dj_track_similarity.db_analysis import AnalysisRepository  # noqa: E402
from dj_track_similarity.db_artifacts import (  # noqa: E402
    create_artifacts_sidecar_schema,
)
from dj_track_similarity.db_ddl import create_core_schema  # noqa: E402
from rhythm_lab.cli import promote_profile_model  # noqa: E402
from rhythm_lab.artifact_io import (  # noqa: E402
    ArtifactIntegrityError,
    artifact_sha256,
    load_verified_artifact,
)
from rhythm_lab import artifact_io  # noqa: E402
from rhythm_lab.cli import PromotionError  # noqa: E402
from rhythm_lab.features import build_labeled_feature_matrix  # noqa: E402
from rhythm_lab.lab_db import RhythmLabDatabase  # noqa: E402
from rhythm_lab.source_db import (  # noqa: E402
    SourceDatabase,
    _ready_embedding_vectors,
)
from rhythm_lab.predictions import apply_model_to_lab  # noqa: E402
from rhythm_lab.training import train_feature_set  # noqa: E402
from rhythm_lab.web_app import create_app  # noqa: E402


NOW = "2026-07-24T10:00:00.000000Z"


class _ReadyClassifier:
    classes_ = np.asarray(["yes", "no"], dtype=object)

    def __init__(self, feature_count: int) -> None:
        self.n_features_in_ = feature_count

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        return np.tile(np.asarray([[0.8, 0.2]], dtype=np.float64), (len(matrix), 1))


class Repository(AnalysisRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.artifacts_path = root / "library.artifacts.sqlite"
        self.catalog_uuid = str(uuid.uuid4())
        self._write_lock = threading.RLock()
        with sqlite3.connect(self.path) as core:
            create_core_schema(core)
            core.execute(
                """
                INSERT INTO library_catalog(
                    singleton_id, catalog_uuid, created_at, updated_at
                ) VALUES (1, ?, ?, ?)
                """,
                (self.catalog_uuid, NOW, NOW),
            )
        with sqlite3.connect(self.artifacts_path) as artifacts:
            create_artifacts_sidecar_schema(
                artifacts,
                catalog_uuid=self.catalog_uuid,
            )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def connect_artifacts(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.artifacts_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _mert_output() -> AnalysisOutput:
    return AnalysisOutput("mert", "embedding")


def _insert_track(
    repository: Repository,
    output: AnalysisOutput,
    *,
    index: int,
) -> None:
    track_uuid = str(uuid.uuid4())
    with repository.connect() as core:
        cursor = core.execute(
            """
            INSERT INTO tracks(
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, ?, 1, ?, ?, ?)
            """,
            (track_uuid, f"C:/music/{index}.wav", index + 1, NOW, NOW, NOW),
        )
        track_id = int(cursor.lastrowid)
    specification = current_embedding_spec(output.analysis_family)
    vector = np.zeros(specification.dimension, dtype=np.float32)
    vector[index] = 1.0
    target = AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )
    result = repository.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=vector,
                    analyzed_at=NOW,
                ),
            ),
        )
    )
    assert result[0].ok


def _write_promotable_artifact(
    root: Path,
    *,
    output: AnalysisOutput | None = None,
) -> Path:
    selected_output = output or _mert_output()
    family = selected_output.analysis_family
    feature_count = current_embedding_spec(family).dimension
    artifact = root / f"focused-{family}-test.joblib"
    joblib.dump(
        {
            "classifier_key": "focused",
            "feature_set": family,
            "feature_names": [
                f"{family}:{index}" for index in range(feature_count)
            ],
            "label_order": ["yes", "no"],
            "positive_label": "yes",
            "production_calibration": {
                "status": "uncalibrated",
                "reason": "test fixture",
            },
            "model": _ReadyClassifier(feature_count),
        },
        artifact,
    )
    metrics = artifact.with_suffix(".metrics.json")
    metrics.write_text(
        json.dumps(
            {
                "artifact_filename": artifact.name,
                "artifact_hash": artifact_sha256(artifact.read_bytes()),
                "feature_set": family,
                "feature_names": [
                    f"{family}:{index}" for index in range(feature_count)
                ],
            }
        ),
        encoding="utf-8",
    )
    return artifact


def _create_focused_profile(path: Path) -> None:
    lab = RhythmLabDatabase(path)
    lab.create_profile(
        classifier_key="focused",
        name="Focused",
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )


def test_source_features_lab_training_and_promotion_use_current_structure(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)

    source = SourceDatabase(repository.path)
    tracks = source.list_tracks()
    lab_path = tmp_path / "lab.sqlite"
    artifact_dir = tmp_path / "artifacts"
    lab = RhythmLabDatabase(lab_path)
    lab.create_profile(
        classifier_key="focused",
        name="Focused",
        artifact_dir=artifact_dir,
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    for index, track in enumerate(tracks):
        scoped.set_label(track, "yes" if index < 2 else "no")
    scoped.save_prediction(
        tracks[0],
        feature_set="mert",
        model_artifact="focused.joblib",
        label="yes",
        confidence=0.8,
        probabilities={"yes": 0.8, "no": 0.2},
    )
    track_page = source.list_tracks_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
        label="all",
    )
    assert track_page["total"] == 4
    assert {item["label"] for item in track_page["items"]} == {"yes", "no"}
    empty_track_page = source.list_tracks_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
        label="all",
        offset=100,
    )
    assert empty_track_page["items"] == []
    assert empty_track_page["total"] == 4
    prediction_page = source.list_predictions_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        profile_type="binary",
        positive_label="yes",
        negative_label="no",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
        label="all",
    )
    assert prediction_page["total"] == 1
    prediction = prediction_page["items"][0]
    assert prediction["track_uuid"] == tracks[0].track_uuid
    assert prediction["content_generation"] == 1
    assert prediction["selected_path"] == tracks[0].file_path
    assert prediction["track_id"] == tracks[0].track_id
    empty_prediction_page = source.list_predictions_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        profile_type="binary",
        positive_label="yes",
        negative_label="no",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
        label="all",
        offset=100,
    )
    assert empty_prediction_page["items"] == []
    assert empty_prediction_page["total"] == 1

    features = build_labeled_feature_matrix(
        repository.path,
        lab_path,
        "mert",
        classifier_key="focused",
    )
    assert {track.track_uuid for track in features.tracks} == {
        track.track_uuid for track in tracks
    }
    assert features.matrix.shape == (4, 768)
    assert features.feature_names == [f"mert:{index}" for index in range(768)]
    assert features.source_dimensions == {"mert": 768}

    result = train_feature_set(
        features.matrix,
        features.labels,
        feature_names=features.feature_names,
        feature_set="mert",
        artifact_dir=artifact_dir,
        label_order=["yes", "no"],
        positive_label="yes",
        artifact_prefix="focused",
        classifier_key="focused",
    )
    promoted = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=result.artifact_path,
        target_root=tmp_path / "promoted",
    )
    metadata = json.loads(
        Path(promoted["metadata_path"]).read_text(encoding="utf-8")
    )
    assert set(metadata["production"]) == {
        "score_semantics",
        "calibration",
        "limitations",
    }
    summary = load_classifier_manifest_summary(
        promoted["model_path"],
        expected_classifier_key="focused",
        metadata_path=promoted["metadata_path"],
    )
    assert summary.status == "valid", summary.errors
    promoted_predictions = apply_model_to_lab(
        repository.path,
        lab_path,
        promoted["model_path"],
        classifier_key="focused",
    )
    assert promoted_predictions["predicted"] == 4

    with repository.connect() as core:
        core.execute(
            "UPDATE tracks SET content_generation = 2 WHERE track_id = ?",
            (tracks[0].track_id,),
        )
    changed = build_labeled_feature_matrix(
        repository.path,
        lab_path,
        "mert",
        classifier_key="focused",
    )
    assert tracks[0].track_uuid not in {
        track.track_uuid for track in changed.tracks
    }
    stale_prediction_page = source.list_predictions_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        profile_type="binary",
        positive_label="yes",
        negative_label="no",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
        label="all",
    )
    stale_prediction = next(
        item
        for item in stale_prediction_page["items"]
        if item["track_uuid"] == tracks[0].track_uuid
    )
    assert stale_prediction["track_id"] is None
    assert stale_prediction["track_uuid"] == tracks[0].track_uuid
    assert stale_prediction["content_generation"] == 1
    assert stale_prediction["selected_path"] == tracks[0].file_path


def test_source_feature_states_distinguish_current_and_missing(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    mert = _mert_output()
    repository.register_analysis_outputs((mert,))
    _insert_track(repository, mert, index=0)
    states = SourceDatabase(repository.path).feature_states()

    assert states["mert"].status == "current"
    assert states["muq"].status == "missing"
    assert "current-generation" in str(states["muq"].reason)
    assert states["clap"].status == "missing"


def test_embedding_reads_are_bounded_by_track_id_chunks() -> None:
    class EmptyResult:
        def fetchall(self) -> list[object]:
            return []

    class RecordingConnection:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def execute(
            self,
            sql: str,
            params: list[object],
        ) -> EmptyResult:
            self.calls.append((sql, tuple(params)))
            return EmptyResult()

    connection = RecordingConnection()
    vectors = _ready_embedding_vectors(
        connection,  # type: ignore[arg-type]
        family="mert",
        track_ids=range(1, 1_702),
    )

    assert vectors == {}
    assert len(connection.calls) == 3
    assert max(len(params) for _, params in connection.calls) <= 801
    assert all("a.track_id IN" in sql for sql, _ in connection.calls)


def test_web_uses_current_track_identity_and_recipe_readiness(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    mert = _mert_output()
    repository.register_analysis_outputs((mert,))
    for index in range(2):
        _insert_track(repository, mert, index=index)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        current = client.get("/api/source/current")
        assert current.status_code == 200
        assert current.json()["catalog_uuid"] == repository.catalog_uuid
        assert current.json()["expected_catalog_uuid"] == repository.catalog_uuid

        tracks_response = client.get(
            "/api/profiles/focused/tracks",
            params={"label": "all"},
        )
        assert tracks_response.status_code == 200
        tracks = tracks_response.json()["items"]
        first, second = tracks
        assert first["track_id"] > 0
        assert first["file_path"].endswith(".wav")
        assert set(first["feature_status"]) == {
            "sonara",
            "mert",
            "maest",
            "clap",
            "muq",
        }
        assert first["feature_status"]["mert"]["status"] == "current"
        assert first["feature_status"]["muq"]["status"] == "missing"

        mert_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mert"},
        ).json()
        combined_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "combined"},
        ).json()
        muq_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "muq"},
        ).json()
        assert mert_readiness["features_ready"] is True
        assert mert_readiness["labels_ready"] is False
        assert combined_readiness["features_ready"] is False
        assert combined_readiness["feature_recipe"]["required_sources"] == [
            "sonara",
            "mert",
            "maest",
        ]
        assert muq_readiness["features_ready"] is False
        assert muq_readiness["feature_recipe"]["blocking"][0]["source"] == "muq"

        liked_payload = {
            "catalog_uuid": first["catalog_uuid"],
            "track_uuid": first["track_uuid"],
            "content_generation": first["content_generation"],
            "liked": True,
        }
        liked = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json=liked_payload,
        )
        assert liked.status_code == 200
        assert liked.json() == {
            "catalog_uuid": first["catalog_uuid"],
            "track_id": first["track_id"],
            "track_uuid": first["track_uuid"],
            "content_generation": first["content_generation"],
            "file_path": first["file_path"],
            "liked": True,
        }

        wrong_identity = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json={
                "catalog_uuid": second["catalog_uuid"],
                "track_uuid": second["track_uuid"],
                "content_generation": second["content_generation"],
                "liked": True,
            },
        )
        assert wrong_identity.status_code == 409
        stale_generation = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json={
                **liked_payload,
                "content_generation": first["content_generation"] + 1,
            },
        )
        assert stale_generation.status_code == 409
        wrong_catalog = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json={**liked_payload, "catalog_uuid": "other-catalog"},
        )
        assert wrong_catalog.status_code == 409
        incomplete = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json={"liked": False},
        )
        assert incomplete.status_code == 422

        static_script = client.get("/static/app.js")
        assert static_script.status_code == 200
        script = static_script.text
        assert "track.track_id" in script
        assert "track.file_path" in script
        assert "catalog_uuid: track.catalog_uuid" in script
        assert "trackFeatureStatus" in script
        assert '"muq"' in script
        assert "source_data_ready" in script
        assert "track.id" not in script
        assert "track.path" not in script


def test_web_promotion_rejects_artifact_when_muq_vectors_are_invalid(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    current_muq = AnalysisOutput("muq", "embedding")
    repository.register_analysis_outputs((current_muq,))
    _insert_track(repository, current_muq, index=0)
    with repository.connect_artifacts() as artifacts:
        artifacts.execute(
            "UPDATE muq_embeddings SET normalization = 'none'"
        )

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    lab_path = tmp_path / "lab.sqlite"
    lab = RhythmLabDatabase(lab_path)
    lab.create_profile(
        classifier_key="focused",
        name="Focused",
        artifact_dir=artifact_dir,
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )
    _write_promotable_artifact(artifact_dir, output=current_muq)

    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        classifier_target_root=tmp_path / "promoted",
        source_catalog_uuid=repository.catalog_uuid,
    )
    with TestClient(app) as client:
        readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "muq"},
        )
        assert readiness.status_code == 200
        option = readiness.json()["artifact_summary"]["promotion_options"][0]
        assert option["feature_set"] == "muq"
        assert option["source_data_ready"] is False
        assert "No valid current-generation MUQ data" in option["source_data_reason"]

        response = client.post(
            "/api/profiles/focused/promote",
            json={"feature_set": "muq"},
        )
        assert response.status_code == 409
        assert not (tmp_path / "promoted").exists()


def test_promotion_accepts_structurally_complete_muq_artifact(
    tmp_path: Path,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    output = AnalysisOutput("muq", "embedding")
    artifact = _write_promotable_artifact(tmp_path, output=output)

    promoted = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=tmp_path / "promoted",
    )
    summary = load_classifier_manifest_summary(
        promoted["model_path"],
        expected_classifier_key="focused",
        metadata_path=promoted["metadata_path"],
    )

    assert summary.status == "valid", summary.errors
    assert summary.feature_set == "muq"
    assert summary.feature_names == tuple(
        f"muq:{index}"
        for index in range(current_embedding_spec("muq").dimension)
    )


def test_tampered_or_unbound_artifact_is_rejected_before_joblib_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "focused-mert-test.joblib"
    joblib.dump(
        {
            "classifier_key": "focused",
            "feature_set": "mert",
            "model": object(),
        },
        artifact,
    )
    original_bytes = artifact.read_bytes()
    metrics = artifact.with_suffix(".metrics.json")
    metrics.write_text(
        json.dumps(
            {
                "artifact_filename": artifact.name,
                "artifact_hash": artifact_sha256(original_bytes),
            }
        ),
        encoding="utf-8",
    )
    artifact.write_bytes(original_bytes + b"tampered")

    lab_path = tmp_path / "lab.sqlite"
    lab = RhythmLabDatabase(lab_path)
    lab.create_profile(
        classifier_key="focused",
        name="Focused",
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )
    calls = 0

    def forbidden_load(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("joblib.load must not run before SHA-256 verification")

    monkeypatch.setattr(joblib, "load", forbidden_load)
    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        apply_model_to_lab(
            tmp_path / "unused.sqlite",
            lab_path,
            artifact,
            classifier_key="focused",
        )
    with pytest.raises(PromotionError, match="SHA-256 mismatch"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=artifact,
            target_root=tmp_path / "promoted",
        )

    unbound = tmp_path / "unbound.joblib"
    unbound.write_bytes(original_bytes)
    with pytest.raises(ArtifactIntegrityError, match="metadata is required"):
        apply_model_to_lab(
            tmp_path / "unused.sqlite",
            lab_path,
            unbound,
            classifier_key="focused",
        )
    assert calls == 0


def test_atomic_generation_pointer_survives_failed_publication_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(tmp_path)
    target_root = tmp_path / "promoted"
    first = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=target_root,
    )
    pointer = Path(first["pointer_path"])
    pointer_before = pointer.read_bytes()
    old_model = Path(first["model_path"])
    real_replace = artifact_io.os.replace

    def fail_pointer_switch(source: object, destination: object) -> None:
        if Path(destination).name == CLASSIFIER_PUBLICATION_POINTER_NAME:
            raise OSError("injected pointer-switch failure")
        real_replace(source, destination)

    monkeypatch.setattr(artifact_io.os, "replace", fail_pointer_switch)
    with pytest.raises(PromotionError, match="pointer-switch failure"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=artifact,
            target_root=target_root,
        )

    assert pointer.read_bytes() == pointer_before
    resolved = resolve_classifier_artifact_paths(
        pointer.parent / "model.joblib"
    )
    assert resolved.model_path == old_model
    discovered = promoted_classifiers(target_root)
    assert len(discovered) == 1
    assert discovered[0]["manifest_status"] == "valid"
    assert discovered[0]["model_path"] == str(old_model)


def test_scoring_ready_artifact_is_validated_before_pointer_publication(
    tmp_path: Path,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(tmp_path)
    target_root = tmp_path / "promoted"

    promoted = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=target_root,
    )

    pointer = Path(promoted["pointer_path"])
    resolved = resolve_classifier_artifact_paths(pointer.parent / "model.joblib")
    discovered = promoted_classifiers(target_root)
    assert resolved.model_path == promoted["model_path"]
    assert discovered[0]["manifest_status"] == "valid"
    assert discovered[0]["is_scoring_compatible"] is True


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    [
        ("empty_features", "non-empty ordered feature_names list"),
        ("unusable_model", "must implement predict_proba"),
    ],
)
def test_semantically_invalid_artifact_does_not_switch_pointer(
    tmp_path: Path,
    invalid_case: str,
    expected_error: str,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(tmp_path)
    target_root = tmp_path / "promoted"
    first = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=target_root,
    )
    pointer = Path(first["pointer_path"])
    pointer_before = pointer.read_bytes()
    generations_dir = pointer.parent / "generations"
    generations_before = {
        path.name for path in generations_dir.iterdir() if path.is_dir()
    }

    payload = joblib.load(artifact)
    if invalid_case == "empty_features":
        payload["feature_names"] = []
    else:
        payload["model"] = object()
    joblib.dump(payload, artifact)
    artifact.with_suffix(".metrics.json").write_text(
        json.dumps(
            {
                "artifact_filename": artifact.name,
                "artifact_hash": artifact_sha256(artifact.read_bytes()),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromotionError, match=expected_error):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=artifact,
            target_root=target_root,
        )

    assert pointer.read_bytes() == pointer_before
    assert {
        path.name for path in generations_dir.iterdir() if path.is_dir()
    } == generations_before
    resolved = resolve_classifier_artifact_paths(pointer.parent / "model.joblib")
    assert resolved.model_path == first["model_path"]


def test_promoted_generation_tamper_fails_before_joblib_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(tmp_path)
    target_root = tmp_path / "promoted"
    promoted = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=target_root,
    )
    model_path = Path(promoted["model_path"])
    metadata_path = Path(promoted["metadata_path"])
    model_bytes = model_path.read_bytes()
    calls = 0

    def forbidden_load(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("joblib.load must not run before SHA-256 verification")

    monkeypatch.setattr(joblib, "load", forbidden_load)
    model_path.write_bytes(model_bytes + b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        load_verified_artifact(model_path)
    discovered = promoted_classifiers(target_root)
    assert discovered[0]["manifest_status"] == "invalid"
    assert calls == 0

    model_path.write_bytes(model_bytes)
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="manifest SHA-256"):
        resolve_classifier_artifact_paths(
            Path(promoted["pointer_path"]).parent / "model.joblib"
        )
    assert calls == 0

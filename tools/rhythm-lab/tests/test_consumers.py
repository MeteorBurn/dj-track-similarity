from __future__ import annotations

import base64
from dataclasses import replace
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
from dj_track_similarity.classifier.manifest import (  # noqa: E402
    load_classifier_manifest_summary,
    resolve_classifier_artifact_paths,
)
from dj_track_similarity.classifier.scoring import promoted_classifiers  # noqa: E402
from dj_track_similarity.db.analysis import AnalysisRepository  # noqa: E402
from dj_track_similarity.db.ddl import create_library_schema  # noqa: E402
from dj_track_similarity.db.library_queries import LibraryQueryRepository  # noqa: E402
from dj_track_similarity.db.schema import insert_library  # noqa: E402
from dj_track_similarity.rhythm_lab_collections import (  # noqa: E402
    RhythmLabCollectionSelection,
    RhythmLabCollections,
    RhythmLabTrackSelection,
    sonara_content_key,
)
from rhythm_lab.cli import promote_profile_model  # noqa: E402
from rhythm_lab.artifact_io import (  # noqa: E402
    ArtifactIntegrityError,
    artifact_sha256,
    load_verified_artifact,
)
from rhythm_lab import predictions as predictions_module  # noqa: E402
from rhythm_lab import source_db as source_db_module  # noqa: E402
from rhythm_lab.cli import PromotionError  # noqa: E402
from rhythm_lab.features import build_labeled_feature_matrix  # noqa: E402
from rhythm_lab.lab_db import RhythmLabDatabase  # noqa: E402
from rhythm_lab.source_db import (  # noqa: E402
    SourceDatabase,
    _ready_embedding_vectors,
)
from rhythm_lab.predictions import apply_model_to_lab  # noqa: E402
from rhythm_lab.training import train_feature_set  # noqa: E402
from rhythm_lab import web_app as web_app_module  # noqa: E402
from rhythm_lab.web_app import create_app  # noqa: E402


NOW = "2026-07-24T10:00:00.000000Z"


class _ReadyClassifier:
    classes_ = np.asarray(["yes", "no"], dtype=object)

    def __init__(self, feature_count: int) -> None:
        self.n_features_in_ = feature_count

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        return np.tile(np.asarray([[0.8, 0.2]], dtype=np.float64), (len(matrix), 1))

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.full(len(matrix), "yes", dtype=object)


class Repository(AnalysisRepository, LibraryQueryRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.catalog_uuid = str(uuid.uuid4())
        self._write_lock = threading.RLock()
        with sqlite3.connect(self.path) as connection:
            create_library_schema(connection)
            insert_library(connection, self.catalog_uuid, created_at=NOW)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

def _mulan_output() -> AnalysisOutput:
    return AnalysisOutput("mulan", "embedding")


def _fingerprint_base64(index: int) -> str:
    """Deterministic valid base64 of 8 bytes; the same index means the same content."""

    return base64.b64encode(bytes([index % 256, 9]) * 4).decode("ascii")


def _insert_fingerprint(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    track_uuid: str,
    index: int,
) -> None:
    connection.execute(
        """
        INSERT INTO sonara_fingerprints(
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, 1, ?, ?)
        """,
        (track_id, track_uuid, _fingerprint_base64(index), NOW),
    )


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
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, ?, ?, ?, ?)
            """,
            (track_uuid, f"C:/music/{index}.wav", index + 1, NOW, NOW, NOW),
        )
        track_id = int(cursor.lastrowid)
        _insert_fingerprint(core, track_id=track_id, track_uuid=track_uuid, index=index)
    specification = current_embedding_spec(output.analysis_family)
    vector = np.zeros(specification.dimension, dtype=np.float32)
    vector[index] = 1.0
    target = AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
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


def _insert_track_without_embedding(
    repository: Repository,
    *,
    index: int,
) -> None:
    track_uuid = str(uuid.uuid4())
    with repository.connect() as core:
        cursor = core.execute(
            """
            INSERT INTO tracks(
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, ?, ?, ?, ?)
            """,
            (track_uuid, f"C:/music/{index}.wav", index + 1, NOW, NOW, NOW),
        )
        _insert_fingerprint(core, track_id=int(cursor.lastrowid), track_uuid=track_uuid, index=index)


def _insert_complete_rhythm_lab_rows(
    repository: Repository,
    *,
    track_id: int,
    missing_source: str | None = None,
) -> None:
    with repository.connect() as connection:
        track_uuid = str(
            connection.execute(
                "SELECT track_uuid FROM tracks WHERE track_id = ?",
                (track_id,),
            ).fetchone()[0]
        )
        if missing_source != "sonara":
            connection.execute(
                """
                INSERT INTO sonara_features(
                    track_id, mfcc_mean_blob, chroma_mean_blob,
                    spectral_contrast_mean_blob, analysis_schema_version,
                    analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    bytes(13 * 4),
                    bytes(12 * 4),
                    bytes(7 * 4),
                    6,
                    NOW,
                ),
            )
        for family in ("maest", "clap", "muq", "mulan"):
            if family == missing_source:
                continue
            specification = current_embedding_spec(family)
            vector = np.zeros(specification.dimension, dtype="<f4")
            if specification.normalization == "l2":
                vector[0] = 1.0
            connection.execute(
                f"""
                INSERT INTO {family}_embeddings(
                    track_id, track_uuid, dim, normalization,
                    embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    track_uuid,
                    specification.dimension,
                    specification.normalization,
                    vector.tobytes(order="C"),
                    NOW,
                ),
            )


def _complete_all_tracks_for_rhythm_lab(
    repository: Repository,
    *,
    existing_source: str,
) -> None:
    with repository.connect() as connection:
        track_ids = [
            int(row[0])
            for row in connection.execute(
                "SELECT track_id FROM tracks ORDER BY track_id"
            )
        ]
    for track_id in track_ids:
        _insert_complete_rhythm_lab_rows(
            repository,
            track_id=track_id,
            missing_source=existing_source,
        )


def _write_promotable_artifact(
    root: Path,
    *,
    output: AnalysisOutput | None = None,
    catalog_uuid: str | None = "catalog-current",
    stamp: str = "test",
    calibrated: bool = False,
) -> Path:
    selected_output = output or _mulan_output()
    family = selected_output.analysis_family
    feature_count = current_embedding_spec(family).dimension
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"focused-{family}-{stamp}.joblib"
    calibration = (
        {"status": "calibrated", "method": "sigmoid", "reason": None}
        if calibrated
        else {"status": "uncalibrated", "method": None, "reason": "test fixture"}
    )
    joblib.dump(
        {
            "classifier_key": "focused",
            "feature_set": family,
            "feature_names": [
                f"{family}:{index}" for index in range(feature_count)
            ],
            "label_order": ["yes", "no"],
            "positive_label": "yes",
            "production_calibration": calibration,
            "source_catalog_uuid": catalog_uuid,
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
                "source_catalog_uuid": catalog_uuid,
                "production_calibration": calibration,
            }
        ),
        encoding="utf-8",
    )
    return artifact


def _create_focused_profile(
    path: Path,
    *,
    artifact_dir: Path | None = None,
) -> None:
    lab = RhythmLabDatabase(path)
    lab.create_profile(
        classifier_key="focused",
        name="Focused",
        description="Focused classifier description.",
        artifact_dir=artifact_dir,
        # Fixtures label a handful of tracks; the product default is 100 per class.
        training_min_labels=2,
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )


def test_web_profile_creation_uses_canonical_profiles_directory(
    tmp_path: Path,
) -> None:
    app = create_app(labels_db_path=tmp_path / "lab.sqlite")

    with TestClient(app) as client:
        response = client.post(
            "/api/profiles",
            json={
                "classifier_key": "voice_presence",
                "name": "Voice Presence",
                "artifact_dir": str(tmp_path / "outside"),
                "labels": [
                    {"key": "yes", "name": "Yes", "role": "positive"},
                    {"key": "no", "name": "No", "role": "negative"},
                ],
            },
        )

    assert response.status_code == 200
    assert Path(response.json()["artifact_dir"]).parts[-2:] == (
        "profiles",
        "voice-presence",
    )
    assert response.json()["training_min_labels"] == 100


def test_source_tracks_read_current_file_tags_schema(tmp_path: Path) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    with repository.connect() as core:
        track_id = int(core.execute("SELECT track_id FROM tracks").fetchone()[0])
        core.execute(
            """
            INSERT INTO tags(
                track_id, title, artist, album, tag_bpm, tag_key, comment,
                year, label, country, track_number, genres_json, tags_read_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "Current title",
                "Current artist",
                "Current album",
                124.5,
                "7A",
                "Current comment",
                2026,
                "Current label",
                "RO",
                "03",
                json.dumps(["Minimal", "Breaks"]),
                NOW,
            ),
        )
        core.execute(
            """
            INSERT INTO maest_genres(
                track_id, syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                track_id,
                0,
                json.dumps(
                    [
                        {"label": "MAEST Minimal", "score": 0.93},
                        {"label": "MAEST Breaks", "score": 0.81},
                    ]
                ),
                NOW,
            ),
        )

    source = SourceDatabase(repository.path)
    track = source.list_tracks()[0]
    assert track.file_tags is not None
    assert track.file_tags.title == "Current title"
    assert track.file_tags.artist == "Current artist"
    assert track.file_tags.album == "Current album"
    assert track.file_tags.tag_bpm == 124.5
    assert track.file_tags.tag_key == "7A"
    assert track.file_tags.comment == "Current comment"
    assert track.file_tags.year == 2026
    assert track.file_tags.label == "Current label"
    assert track.file_tags.country == "RO"
    assert track.file_tags.track_number == "03"
    assert track.file_tags.genres == ("Minimal", "Breaks")
    assert track.file_tags.tags_read_at == NOW

    lab_path = tmp_path / "rhythm_lab.sqlite"
    _create_focused_profile(lab_path)
    RhythmLabDatabase(lab_path).sync_track_sightings(source)
    page = source.list_tracks_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
    )
    assert page["total"] == 1
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["content_key"] == track.content_key == sonara_content_key(1, _fingerprint_base64(0))
    assert item["title"] == "Current title"
    assert item["artist"] == "Current artist"
    assert item["album"] == "Current album"
    assert item["tag_bpm"] == 124.5
    assert item["tag_key"] == "7A"
    assert item["genres"] == ["MAEST Minimal", "MAEST Breaks"]

    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        source_catalog_uuid=repository.catalog_uuid,
    )
    with TestClient(app) as client:
        response = client.get("/api/profiles/focused/tracks", params={"limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Current title"


def test_source_features_lab_training_and_promotion_use_current_structure(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = AnalysisOutput("mert_v2", "embedding")
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mert_v2")

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
    scoped.sync_track_sightings(source)
    for index, track in enumerate(tracks):
        scoped.set_label(track, "yes" if index < 2 else "no")
    scoped.save_prediction(
        tracks[0],
        feature_set="mert_v2",
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
    assert prediction["content_key"] == tracks[0].content_key
    assert prediction["track_uuid"] == tracks[0].track_uuid
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
        "mert_v2",
        classifier_key="focused",
    )
    assert {track.track_uuid for track in features.tracks} == {
        track.track_uuid for track in tracks
    }
    assert features.matrix.shape == (4, 1024)
    assert features.feature_names == [f"mert_v2:{index}" for index in range(1024)]
    assert features.source_dimensions == {"mert_v2": 1024}

    result = train_feature_set(
        features.matrix,
        features.labels,
        feature_names=features.feature_names,
        feature_set="mert_v2",
        artifact_dir=artifact_dir,
        label_order=["yes", "no"],
        positive_label="yes",
        artifact_prefix="focused",
        classifier_key="focused",
        source_catalog_uuid=repository.catalog_uuid,
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

def test_source_feature_states_distinguish_current_and_missing(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    mulan = _mulan_output()
    repository.register_analysis_outputs((mulan,))
    _insert_track(repository, mulan, index=0)
    states = SourceDatabase(repository.path).feature_states()

    assert states["mulan"].status == "current"
    assert states["muq"].status == "missing"
    assert "no stored MUQ data" in str(states["muq"].reason)
    assert states["clap"].status == "missing"
    assert states["mert_v2"].status == "missing"

    mert_v2 = AnalysisOutput("mert_v2", "embedding")
    repository.register_analysis_outputs((mert_v2,))
    _insert_track(repository, mert_v2, index=1)
    source = SourceDatabase(repository.path)
    assert source.feature_states()["mert_v2"].status == "current"
    matrix = source.load_embedding_matrix("mert_v2")
    assert matrix.matrix.shape == (1, 1024)
    assert matrix.normalization == "l2"
    assert matrix.matrix[0, 1] == 1.0
    assert matrix.not_ready_track_ids == (1,)
    track = matrix.tracks[0]
    assert track.analysis_coverage.mert_v2 is True
    assert track.analysis_coverage.mulan is False
    assert track.feature_status["mert_v2"].status == "current"

    layers = tuple(np.eye(1, 1024, index, dtype=np.float32)[0] for index in range(24))
    write = EmbeddingWrite(
        AnalysisTarget(repository.catalog_uuid, track.track_id, track.track_uuid),
        EmbeddingOutput("mert_v2", layers[-1], NOW, layers),
    )
    assert repository.save_embedding_results((write,))[0].ok
    np.testing.assert_array_equal(source.load_embedding_matrix("mert_v2").matrix[0], layers[-1])
    assert source.feature_inventory()[0]["mert_v2"] == 1

    with repository.connect() as connection:
        connection.execute(
            "UPDATE mert_v2_embeddings SET track_uuid = ? WHERE track_id = ? AND layer = 24",
            (str(uuid.uuid4()), track.track_id),
        )
    rejected = source.load_embedding_matrix("mert_v2")
    assert rejected.matrix.shape == (0, 1024)
    assert rejected.not_ready_track_ids == (1, track.track_id)
    assert source.get_track(track.track_id).feature_status["mert_v2"].status == "missing"


def test_source_feature_inventory_is_cached_until_storage_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    source = SourceDatabase(repository.path)
    real_feature_counts = source_db_module._feature_counts
    calls = 0

    def recording_feature_counts(connection: sqlite3.Connection) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return real_feature_counts(connection)

    monkeypatch.setattr(
        source_db_module,
        "_feature_counts",
        recording_feature_counts,
    )

    first_counts, first_states = source.feature_inventory()
    second_counts, second_states = source.feature_inventory()

    assert calls == 1
    assert dict(second_counts) == dict(first_counts)
    assert dict(second_states) == dict(first_states)

    _insert_track(repository, output, index=1)
    refreshed_counts, _ = source.feature_inventory()

    assert calls == 2
    assert refreshed_counts["mulan"] == first_counts["mulan"] + 1


def test_rhythm_lab_track_ids_follow_the_requested_recipe(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    _insert_track_without_embedding(repository, index=0)
    _insert_track_without_embedding(repository, index=1)
    with repository.connect() as connection:
        track_ids = [
            int(row[0])
            for row in connection.execute(
                "SELECT track_id FROM tracks ORDER BY track_id"
            )
        ]
    _insert_complete_rhythm_lab_rows(repository, track_id=track_ids[0])
    _insert_complete_rhythm_lab_rows(
        repository,
        track_id=track_ids[1],
        missing_source="mulan",
    )

    source = SourceDatabase(repository.path)

    # Default pool: every family stored in this library, so the MuLan gap excludes track 2.
    assert source.rhythm_lab_track_ids() == (track_ids[0],)
    assert source.rhythm_lab_track_ids(("sonara", "mulan")) == (track_ids[0],)
    # A recipe without MuLan keeps it.
    assert source.rhythm_lab_track_ids(("sonara", "maest")) == tuple(track_ids)
    # A family with no rows here (mert_v2) yields an empty pool instead of a query error.
    assert source.rhythm_lab_track_ids(("sonara", "mert_v2")) == ()
    assert source.rhythm_lab_track_ids(("mert_v2@12",)) == ()
    assert source.mert_v2_stored_layers() == ()


def test_source_feature_counts_trust_existing_rows_without_blob_validation(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    _insert_track_without_embedding(repository, index=0)
    with repository.connect() as connection:
        track_id, track_uuid = connection.execute(
            "SELECT track_id, track_uuid FROM tracks"
        ).fetchone()
        connection.execute(
            """
            INSERT INTO mulan_embeddings(
                track_id, track_uuid, dim, normalization,
                embedding_blob, analyzed_at
            ) VALUES (?, ?, 1, 'none', ?, ?)
            """,
            (track_id, track_uuid, bytes(4), NOW),
        )
        connection.execute(
            """
            INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                np.full(13, np.nan, dtype="<f4").tobytes(),
                bytes(12 * 4),
                bytes(7 * 4),
                6,
                NOW,
            ),
        )

    source = SourceDatabase(repository.path)

    assert source.feature_counts()["mulan"] == 1
    assert source.count_embeddings("mulan") == 1
    assert source.count_sonara_features() == 1


def test_rhythm_lab_track_page_follows_the_requested_recipe(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _insert_track(repository, output, index=1)
    with repository.connect() as connection:
        track_ids = [
            int(row[0])
            for row in connection.execute(
                "SELECT track_id FROM tracks ORDER BY track_id"
            )
        ]
    _insert_complete_rhythm_lab_rows(
        repository,
        track_id=track_ids[0],
        missing_source="mulan",
    )
    labels_path = tmp_path / "lab.sqlite"
    _create_focused_profile(labels_path)
    source = SourceDatabase(repository.path)
    RhythmLabDatabase(labels_path).sync_track_sightings(source)

    def page(required_sources: tuple[str, ...] | None) -> list[int]:
        result = source.list_tracks_page(
            labels_db_path=labels_path,
            classifier_key="focused",
            label_keys=("yes", "no"),
            training_label_keys=("yes", "no"),
            required_sources=required_sources,
        )
        assert result["total"] == len(result["items"])
        return [item["track_id"] for item in result["items"]]

    # Default pool requires every stored family; only track 1 has all of them.
    assert page(None) == [track_ids[0]]
    # A MuLan-only recipe shows both tracks; a subset without MuLan shows track 1.
    assert page(("mulan",)) == track_ids
    assert page(("sonara", "muq")) == [track_ids[0]]
    assert page(("mert_v2",)) == []


def test_labeled_features_exclude_tracks_missing_a_recipe_source(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _insert_track(repository, output, index=1)
    source = SourceDatabase(repository.path)
    tracks = source.list_tracks()
    _insert_complete_rhythm_lab_rows(
        repository,
        track_id=tracks[0].track_id,
        missing_source="mulan",
    )
    labels_path = tmp_path / "lab.sqlite"
    _create_focused_profile(labels_path)
    scoped = RhythmLabDatabase(labels_path, classifier_key="focused")
    scoped.set_label(tracks[0], "yes")
    scoped.set_label(tracks[1], "no")

    # The training pool follows the recipe: both tracks store MuLan, only one stores MAEST.
    mulan_only = build_labeled_feature_matrix(
        repository.path,
        labels_path,
        "mulan",
        classifier_key="focused",
    )
    with_maest = build_labeled_feature_matrix(
        repository.path,
        labels_path,
        "mulan+maest",
        classifier_key="focused",
    )

    assert {track.track_id for track in mulan_only.tracks} == {track.track_id for track in tracks}
    assert mulan_only.skipped_identities == ()
    assert [track.track_id for track in with_maest.tracks] == [tracks[0].track_id]
    assert with_maest.skipped_identities == (tracks[1].content_key,)


def test_profile_summary_counts_only_complete_rhythm_lab_tracks(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _insert_track(repository, output, index=1)
    with repository.connect() as connection:
        complete_track_id = int(
            connection.execute(
                "SELECT MIN(track_id) FROM tracks"
            ).fetchone()[0]
        )
    _insert_complete_rhythm_lab_rows(
        repository,
        track_id=complete_track_id,
        missing_source="mulan",
    )
    labels_path = tmp_path / "lab.sqlite"
    _create_focused_profile(labels_path)
    scoped = RhythmLabDatabase(labels_path, classifier_key="focused")
    track = SourceDatabase(repository.path).tracks_by_ids([complete_track_id])[complete_track_id]
    scoped.set_label(track, "yes")
    remote_root = tmp_path / "remote"
    remote_root.mkdir()
    remote = Repository(remote_root)
    for index in (0, 77, 78):
        _insert_track_without_embedding(remote, index=index)
    remote_source = SourceDatabase(remote.path)
    remote_tracks = remote_source.list_tracks()
    scoped.sync_track_sightings(remote_source)
    scoped.set_label(remote_tracks[1], "no")
    scoped.create_profile(
        classifier_key="other",
        name="Other",
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )
    scoped.scoped("other").set_label(track, "no")
    collections = RhythmLabCollections(labels_path)
    collection = collections.save_collection(
        "Whole collection",
        RhythmLabCollectionSelection(
            catalog_uuid=track.catalog_uuid,
            tracks=(RhythmLabTrackSelection(
                catalog_uuid=track.catalog_uuid,
                track_uuid=track.track_uuid,
                selected_path=track.file_path,
                content_key=str(track.content_key),
            ),),
        ),
    )
    collections.append_tracks(
        collection.id,
        RhythmLabCollectionSelection(
            catalog_uuid=remote.catalog_uuid,
            tracks=tuple(
                RhythmLabTrackSelection(
                    catalog_uuid=item.catalog_uuid,
                    track_uuid=item.track_uuid,
                    selected_path=item.file_path,
                    content_key=str(item.content_key),
                )
                for item in remote_tracks
            ),
        ),
    )
    empty = collections.save_collection(
        "Empty collection",
        RhythmLabCollectionSelection(catalog_uuid=track.catalog_uuid, tracks=()),
    )
    app = create_app(
        repository.path,
        labels_db_path=labels_path,
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        response = client.get("/api/profiles/focused/summary")
        progress_response = client.get(
            "/api/profiles/focused/summary", params={"collection_id": collection.id}
        )
        page = client.get(
            "/api/profiles/focused/tracks",
            params={"collection_id": collection.id, "label": "yes", "limit": 1},
        )
        after_page = client.get(
            "/api/profiles/focused/summary", params={"collection_id": collection.id}
        )
        other = client.get(
            "/api/profiles/other/summary", params={"collection_id": collection.id}
        )
        empty_response = client.get(
            "/api/profiles/focused/summary", params={"collection_id": empty.id}
        )
        missing = client.get(
            "/api/profiles/focused/summary", params={"collection_id": empty.id + 1}
        )
        invalid = client.get("/api/profiles/focused/summary", params={"collection_id": 0})

    assert response.status_code == 200
    assert response.json()["tracks"] == 1
    assert response.json()["labels"] == {"yes": 1}
    assert "collection_progress" not in response.json()
    assert progress_response.status_code == 200
    assert progress_response.json()["collection_progress"] == {
        "total": 3, "labels": {"yes": 1, "no": 1}, "unlabeled": 1,
    }
    assert progress_response.json()["labels"] == response.json()["labels"]
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert after_page.json() == progress_response.json()
    assert other.json()["collection_progress"] == {
        "total": 3, "labels": {"no": 1}, "unlabeled": 2,
    }
    assert empty_response.json()["collection_progress"] == {
        "total": 0, "labels": {}, "unlabeled": 0,
    }
    assert missing.status_code == 404
    assert "Review collection not found" in missing.json()["detail"]
    assert invalid.status_code == 422
    with TestClient(create_app(labels_db_path=labels_path)) as client:
        without_source = client.get(
            "/api/profiles/focused/summary", params={"collection_id": collection.id}
        )
    assert without_source.json()["collection_progress"] == progress_response.json()["collection_progress"]


def test_labels_from_another_catalog_are_not_counted_or_trained(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    track = SourceDatabase(repository.path).list_tracks()[0]
    labels_path = tmp_path / "lab.sqlite"
    _create_focused_profile(labels_path)
    scoped = RhythmLabDatabase(labels_path, classifier_key="focused")
    # The same file labelled from another library: same content, one label.
    scoped.set_label(
        replace(track, catalog_uuid=str(uuid.uuid4()), track_uuid=str(uuid.uuid4())),
        "yes",
    )
    scoped.set_label(track, "yes")
    # Content this library never sighted is not current here.
    scoped.set_label(
        replace(
            track,
            catalog_uuid=str(uuid.uuid4()),
            track_uuid=str(uuid.uuid4()),
            content_key=sonara_content_key(1, _fingerprint_base64(77)),
        ),
        "no",
    )
    assert scoped.label_counts() == {"yes": 1, "no": 1}
    app = create_app(
        repository.path,
        labels_db_path=labels_path,
        classifier_target_root=tmp_path / "promoted",
        source_catalog_uuid=repository.catalog_uuid,
    )

    features = build_labeled_feature_matrix(
        repository.path,
        labels_path,
        "mulan",
        classifier_key="focused",
    )
    with TestClient(app) as client:
        summary = client.get("/api/profiles/focused/summary").json()
        readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        ).json()

    assert features.labels == ["yes"]
    assert features.skipped_identities == ()
    assert summary["labels"] == {"yes": 1}
    assert readiness["current"] == {"yes": 1, "no": 0}


def test_prediction_page_hides_track_only_when_a_required_source_row_is_removed(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    _insert_track(repository, output, index=1)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    source = SourceDatabase(repository.path)
    track = source.list_tracks()[0]
    labels_path = tmp_path / "lab.sqlite"
    _create_focused_profile(labels_path)
    scoped = RhythmLabDatabase(labels_path, classifier_key="focused")
    scoped.sync_track_sightings(source)
    scoped.save_prediction(
        track,
        feature_set="mulan",
        model_artifact="focused.joblib",
        label="yes",
        confidence=0.8,
        probabilities={"yes": 0.8, "no": 0.2},
    )
    # The other track keeps MuLan stored, so the family stays available library-wide.
    with repository.connect() as connection:
        connection.execute(
            "DELETE FROM mulan_embeddings WHERE track_id = ?",
            (track.track_id,),
        )

    def page(required_sources: tuple[str, ...] | None) -> int:
        result = source.list_predictions_page(
            labels_db_path=labels_path,
            classifier_key="focused",
            profile_type="binary",
            positive_label="yes",
            negative_label="no",
            label_keys=("yes", "no"),
            training_label_keys=("yes", "no"),
            label="all",
            predicted="all",
            required_sources=required_sources,
        )
        assert result["total"] == len(result["items"])
        return result["total"]

    assert page(None) == 0
    assert page(("mulan",)) == 0
    # Removing an unrelated family's row does not hide the prediction.
    assert page(("sonara", "muq")) == 1


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
        family="mulan",
        track_ids=range(1, 1_702),
    )

    assert vectors == {}
    assert len(connection.calls) == 3
    assert max(len(params) for _, params in connection.calls) <= 801
    assert all("a.track_id IN" in sql for sql, _ in connection.calls)


def test_web_uses_current_track_identity_and_recipe_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    mulan = _mulan_output()
    repository.register_analysis_outputs((mulan,))
    for index in range(4):
        _insert_track(repository, mulan, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    # Libraries analyzed before MERT-v2 existed have no table at all; the lab
    # must report the family as missing instead of failing on the query.
    with repository.connect() as connection:
        connection.execute("DROP TABLE mert_v2_embeddings")
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    # Two labels per class satisfy the fixture threshold, so benchmarks may start.
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    for index, track in enumerate(SourceDatabase(repository.path).list_tracks()):
        scoped.set_label(track, "yes" if index < 2 else "no")
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        classifier_target_root=tmp_path / "promoted",
        source_catalog_uuid=repository.catalog_uuid,
    )
    benchmark_calls: list[dict[str, object]] = []

    def fake_benchmark(*_args: object, **kwargs: object) -> dict[str, object]:
        benchmark_calls.append(kwargs)
        return {"strategy": kwargs["strategy"], "feature_sets": ["sonara+mulan"], "planned_runs": 1, "profiles": []}

    monkeypatch.setattr(web_app_module, "run_ablation_benchmark", fake_benchmark)
    stored_families = ["sonara", "maest", "muq", "mulan", "clap"]

    with TestClient(app) as client:
        current = client.get("/api/source/current")
        assert current.status_code == 200
        assert current.json()["catalog_uuid"] == repository.catalog_uuid
        assert current.json()["launched_catalog_uuid"] == repository.catalog_uuid
        assert current.json()["track_count"] == 4
        assert current.json()["available_feature_sources"] == stored_families
        assert current.json()["default_feature_set"] == "+".join(stored_families)
        assert current.json()["feature_sources"]["mulan"] == {
            "status": "current",
            "reason": None,
            "count": 4,
            "track_count": 4,
        }
        assert current.json()["feature_sources"]["mert_v2"]["status"] == "missing"
        assert current.json()["mert_v2_layers"] == []

        tracks_response = client.get(
            "/api/profiles/focused/tracks",
            params={"label": "all"},
        )
        assert tracks_response.status_code == 200
        tracks = tracks_response.json()["items"]
        assert len(tracks) == 4
        first, second = tracks[:2]
        assert first["track_id"] > 0
        assert first["content_key"].startswith("sfp1:")
        assert first["content_key"] != second["content_key"]
        assert first["file_path"].endswith(".wav")
        assert set(first["feature_status"]) == {
            "sonara",
            "mulan",
            "mert_v2",
            "maest",
            "clap",
            "muq",
            "mulan",
        }
        assert first["feature_status"]["mulan"]["status"] == "current"
        assert first["feature_status"]["mert_v2"]["status"] == "missing"
        assert first["feature_status"]["muq"]["status"] == "current"
        assert first["feature_status"]["mulan"]["status"] == "current"
        # Pages take an optional recipe; an unstored family yields an empty page.
        assert client.get(
            "/api/profiles/focused/tracks",
            params={"label": "all", "feature_set": "mert_v2"},
        ).json()["total"] == 0
        assert client.get(
            "/api/profiles/focused/tracks",
            params={"feature_set": "combined"},
        ).status_code == 400

        mulan_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        ).json()
        sonara_mulan_maest_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "maest+mulan+sonara"},
        ).json()
        muq_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "muq"},
        ).json()
        default_readiness = client.get(
            "/api/profiles/focused/training/readiness",
        ).json()
        assert mulan_readiness["features_ready"] is True
        assert mulan_readiness["promoted_model"]["status"] == "not_promoted"
        assert mulan_readiness["trained_model"]["feature_set"] is None
        assert mulan_readiness["labels_ready"] is True
        assert mulan_readiness["label_threshold_ready"] is True
        assert mulan_readiness["calibration_ready"] is False
        assert "100" in mulan_readiness["calibration_readiness"]["reason"]
        assert mulan_readiness["available_feature_sources"] == stored_families
        assert mulan_readiness["default_feature_set"] == "+".join(stored_families)
        assert mulan_readiness["mert_v2_layers"] == []
        assert "available_feature_sets" not in mulan_readiness
        source_features = mulan_readiness["source_features"]
        assert set(source_features) == set(first["feature_status"])
        assert source_features["mulan"] == {
            "status": "current",
            "reason": None,
            "count": 4,
            "track_count": 4,
        }
        assert source_features["mert_v2"]["status"] == "missing"
        assert source_features["mert_v2"]["count"] == 0
        # Requested recipes come back canonical; the default is every stored family.
        assert sonara_mulan_maest_readiness["features_ready"] is True
        assert sonara_mulan_maest_readiness["feature_recipe"]["feature_set"] == "sonara+maest+mulan"
        assert sonara_mulan_maest_readiness["feature_recipe"]["required_sources"] == [
            "sonara",
            "maest",
            "mulan",
        ]
        assert "total" in mulan_readiness and "current" in mulan_readiness
        assert muq_readiness["features_ready"] is True
        assert muq_readiness["feature_recipe"]["blocking"] == []
        assert default_readiness["feature_recipe"]["feature_set"] == "+".join(stored_families)
        assert default_readiness["features_ready"] is True

        # Benchmarks are planned from the stored families before any training starts.
        benchmark = client.post(
            "/api/profiles/focused/training/benchmark",
            json={"strategy": "custom", "feature_sets": ["mulan+sonara"]},
        )
        assert benchmark.status_code == 200, benchmark.text
        assert benchmark.json()["planned_runs"] == 1
        assert benchmark.json()["feature_sets"] == ["sonara+mulan"]
        assert benchmark_calls[-1]["strategy"] == "custom"
        assert benchmark_calls[-1]["feature_sets"] == ("mulan+sonara",)
        assert client.post(
            "/api/profiles/focused/training/benchmark",
            json={"strategy": "layers"},
        ).status_code == 400
        assert client.post(
            "/api/profiles/focused/training/benchmark",
            json={"strategy": "custom", "feature_sets": ["mert_v2"]},
        ).status_code == 400
        assert len(benchmark_calls) == 1

        liked_payload = {
            "catalog_uuid": first["catalog_uuid"],
            "track_uuid": first["track_uuid"],
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
            "file_path": first["file_path"],
            "liked": True,
        }

        wrong_identity = client.post(
            f"/api/tracks/{first['track_id']}/liked",
            json={
                "catalog_uuid": second["catalog_uuid"],
                "track_uuid": second["track_uuid"],
                "liked": True,
            },
        )
        assert wrong_identity.status_code == 409
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

        # The launcher switches libraries without the launch-time catalog pin:
        # another library opens and reports its own stored families, while a
        # non-library file (the lab's own labels database) is refused.
        other_root = tmp_path / "other"
        other_root.mkdir()
        other = Repository(other_root)
        other.register_analysis_outputs((mulan,))
        _insert_track(other, mulan, index=5)
        switched = client.post("/api/source/switch", json={"path": str(other.path)})
        assert switched.status_code == 200, switched.text
        assert switched.json()["catalog_uuid"] == other.catalog_uuid
        assert switched.json()["launched_catalog_uuid"] == repository.catalog_uuid
        assert switched.json()["track_count"] == 1
        assert switched.json()["available_feature_sources"] == ["mulan"]
        assert switched.json()["default_feature_set"] == "mulan"
        assert client.post("/api/source/switch", json={"path": str(lab_path)}).status_code == 409
        assert client.get("/api/source/current").json()["catalog_uuid"] == other.catalog_uuid

        # The profile is labeled in the first library only: here none of its
        # labels resolve, so training-type operations are refused server-side.
        foreign = client.post("/api/profiles/focused/training/benchmark", json={"strategy": "singles"})
        assert foreign.status_code == 409, foreign.text
        assert "yes — 0 (2 total), no — 0 (2 total)" in foreign.json()["detail"]
        assert client.post("/api/source/switch", json={"path": str(repository.path)}).status_code == 200

        # While a profile operation runs, the source stays put.
        benchmark_started = threading.Event()
        benchmark_release = threading.Event()
        benchmark_status: list[int] = []

        def blocking_benchmark(*_args: object, **kwargs: object) -> dict[str, object]:
            benchmark_started.set()
            assert benchmark_release.wait(timeout=10)
            return {"strategy": kwargs["strategy"], "feature_sets": ["mulan"], "planned_runs": 1, "profiles": []}

        monkeypatch.setattr(web_app_module, "run_ablation_benchmark", blocking_benchmark)
        benchmark_thread = threading.Thread(
            target=lambda: benchmark_status.append(
                client.post("/api/profiles/focused/training/benchmark", json={"strategy": "singles"}).status_code
            ),
        )
        benchmark_thread.start()
        try:
            assert benchmark_started.wait(timeout=10)
            busy = client.post("/api/source/switch", json={"path": str(other.path)})
            assert busy.status_code == 409
            assert "benchmark" in busy.json()["detail"]
        finally:
            benchmark_release.set()
            benchmark_thread.join(timeout=10)
        assert benchmark_status == [200]
        assert client.post("/api/source/switch", json={"path": str(other.path)}).status_code == 200


def test_web_reuses_lab_database_repository_for_profile_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    real_database = web_app_module.RhythmLabDatabase
    constructor_calls: list[tuple[Path, str | None]] = []

    class RecordingRhythmLabDatabase(real_database):
        def __init__(
            self,
            path: str | Path,
            *,
            classifier_key: str | None = None,
        ) -> None:
            constructor_calls.append((Path(path), classifier_key))
            super().__init__(path, classifier_key=classifier_key)

    monkeypatch.setattr(
        web_app_module,
        "RhythmLabDatabase",
        RecordingRhythmLabDatabase,
    )
    app = create_app(labels_db_path=lab_path)

    with TestClient(app) as client:
        summary = client.get("/api/profiles/focused/summary")
        tracks = client.get("/api/profiles/focused/tracks")
        readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        )

    assert summary.status_code == 200
    assert tracks.status_code == 200
    assert readiness.status_code == 200
    assert constructor_calls == [(lab_path, None)]


def test_web_reuses_collection_repository_for_collection_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    real_collections = web_app_module.RhythmLabCollections
    constructor_calls: list[Path] = []

    class RecordingRhythmLabCollections(real_collections):
        def __init__(self, labels_db_path: str | Path) -> None:
            constructor_calls.append(Path(labels_db_path))
            super().__init__(labels_db_path)

    monkeypatch.setattr(
        web_app_module,
        "RhythmLabCollections",
        RecordingRhythmLabCollections,
    )
    app = create_app(labels_db_path=lab_path)

    with TestClient(app) as client:
        first = client.get("/api/collections")
        second = client.get("/api/collections")

    assert first.status_code == 200
    assert second.status_code == 200
    assert constructor_calls == [lab_path]


def test_calibration_preflight_uses_usable_rows_and_preserves_current_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track_without_embedding(repository, index=0)
    for index in range(1, 4):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    artifact_dir = tmp_path / "artifacts"
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path, artifact_dir=artifact_dir)
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    for index, track in enumerate(SourceDatabase(repository.path).list_tracks()):
        scoped.set_label(track, "yes" if index < 2 else "no")
    calibrated = _write_promotable_artifact(
        artifact_dir,
        output=output,
        catalog_uuid=repository.catalog_uuid,
        stamp="20260807T100000Z",
        calibrated=True,
    )
    benchmark_calls = 0

    def forbidden_benchmark(*args: object, **kwargs: object) -> object:
        nonlocal benchmark_calls
        benchmark_calls += 1
        raise AssertionError("calibration must stop before training")

    monkeypatch.setattr(
        web_app_module,
        "benchmark_lab_database",
        forbidden_benchmark,
    )
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_LABELS", 4)
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_POSITIVE", 2)
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_NEGATIVE", 2)
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        ).json()
        response = client.post(
            "/api/profiles/focused/training/calibrate",
            json={"feature_set": "mulan"},
        )
        after = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        ).json()

    assert readiness["current"] == {"yes": 2, "no": 2}
    assert readiness["usable"] == {"yes": 1, "no": 2}
    assert readiness["calibration_ready"] is False
    assert response.status_code == 409
    assert benchmark_calls == 0
    assert (
        after["artifact_summary"]["promotion_options"][0]["latest_model"]
        == str(calibrated)
    )


def test_train_refresh_applies_the_exact_artifact_returned_by_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    artifact_dir = tmp_path / "artifacts"
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path, artifact_dir=artifact_dir)
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    for index, track in enumerate(SourceDatabase(repository.path).list_tracks()):
        scoped.set_label(track, "yes" if index < 2 else "no")

    trained_artifact = _write_promotable_artifact(
        artifact_dir,
        output=output,
        catalog_uuid=repository.catalog_uuid,
        stamp="20260807T100000Z",
    )
    newer_artifact = _write_promotable_artifact(
        artifact_dir,
        output=output,
        catalog_uuid=repository.catalog_uuid,
        stamp="20260807T120000Z",
    )

    def fake_benchmark(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "mulan": {
                "status": "trained",
                "artifact_path": str(trained_artifact),
                "metrics_path": str(
                    trained_artifact.with_suffix(".metrics.json")
                ),
                "trained_rows": 4,
                "skipped_rows": 0,
                "feature_count": 768,
            }
        }

    monkeypatch.setattr(
        web_app_module,
        "benchmark_lab_database",
        fake_benchmark,
    )
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        # The profile's per-class label minimum gates training, benchmarking and
        # calibration on the server: 4 labels cannot satisfy 3 per class.
        raised = client.patch("/api/profiles/focused", json={"training_min_labels": 3})
        assert raised.status_code == 200, raised.text
        assert raised.json()["training_min_labels"] == 3
        for path, body in (
            ("training/train-refresh", {"feature_set": "mulan"}),
            ("training/benchmark", {"strategy": "singles"}),
            ("training/calibrate", {"feature_set": "mulan"}),
        ):
            blocked = client.post(f"/api/profiles/focused/{path}", json=body)
            assert blocked.status_code == 409, blocked.text
            assert "at least 3 labels per class" in blocked.json()["detail"]
        readiness = client.get("/api/profiles/focused/training/readiness", params={"feature_set": "mulan"}).json()
        assert (readiness["label_threshold"], readiness["label_threshold_ready"]) == (3, False)
        assert client.patch("/api/profiles/focused", json={"training_min_labels": 2}).status_code == 200

        response = client.post(
            "/api/profiles/focused/training/train-refresh",
            json={"feature_set": "mulan"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["artifact"] == str(trained_artifact)
    assert response.json()["artifact"] != str(newer_artifact)


def test_prediction_refresh_uses_requested_feature_recipe(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = AnalysisOutput("mert_v2", "embedding")
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mert_v2")
    artifact_dir = tmp_path / "artifacts"
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path, artifact_dir=artifact_dir)
    artifact = _write_promotable_artifact(
        artifact_dir,
        output=output,
        catalog_uuid=repository.catalog_uuid,
    )
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/profiles/focused/predictions/refresh",
            json={"feature_set": "mert_v2"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["feature_set"] == "mert_v2"
    assert response.json()["artifact"] == str(artifact)
    assert response.json()["predicted"] == 4


def test_prediction_applies_artifacts_by_feature_spec_not_source_catalog(
    tmp_path: Path,
) -> None:
    first_repository = Repository(tmp_path)
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_repository = Repository(other_root)
    output = _mulan_output()
    other_repository.register_analysis_outputs((output,))
    _insert_track(other_repository, output, index=0)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=first_repository.catalog_uuid,
    )

    # Trained on another library, compatible spec: the artifact applies here.
    applied = apply_model_to_lab(
        other_repository.path,
        lab_path,
        artifact,
        classifier_key="focused",
    )
    assert applied["predicted"] == 1

    # A recipe family with no stored data here is refused before any prediction.
    muq_artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=AnalysisOutput("muq", "embedding"),
        catalog_uuid=other_repository.catalog_uuid,
    )
    with pytest.raises(ValueError, match="no stored MUQ data"):
        apply_model_to_lab(
            other_repository.path,
            lab_path,
            muq_artifact,
            classifier_key="focused",
        )


def test_prediction_and_promotion_accept_artifact_without_source_catalog_binding(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=None,
    )

    applied = apply_model_to_lab(
        repository.path,
        lab_path,
        artifact,
        classifier_key="focused",
    )
    promoted = promote_profile_model(
        lab_path,
        "focused",
        artifact_path=artifact,
        target_root=tmp_path / "promoted",
    )
    metadata = json.loads(Path(promoted["metadata_path"]).read_text(encoding="utf-8"))

    assert applied["predicted"] == 1
    # The catalog stays provenance only, so an unbound artifact records None.
    assert metadata["source_catalog_uuid"] is None


def test_prediction_refresh_failure_leaves_previous_candidate_set_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    for index in range(5):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    tracks = SourceDatabase(repository.path).list_tracks()
    for track in tracks:
        scoped.save_prediction(
            track,
            feature_set="mulan",
            model_artifact="old.joblib",
            label="no",
            confidence=0.75,
            probabilities={"yes": 0.25, "no": 0.75},
        )
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=repository.catalog_uuid,
        stamp="new",
    )
    build_calls = 0
    original_build = predictions_module.build_feature_matrix

    def fail_second_batch(*args: object, **kwargs: object):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 2:
            raise RuntimeError("later batch failed")
        return original_build(*args, **kwargs)

    monkeypatch.setattr(predictions_module, "PREDICTION_BATCH_SIZE", 2)
    monkeypatch.setattr(
        predictions_module,
        "build_feature_matrix",
        fail_second_batch,
    )

    with pytest.raises(RuntimeError, match="later batch failed"):
        apply_model_to_lab(
            repository.path,
            lab_path,
            artifact,
            classifier_key="focused",
        )

    rows = scoped.predictions()
    assert len(rows) == 5
    assert {row["model_artifact"] for row in rows} == {"old.joblib"}


def test_calibration_becomes_current_for_refresh_and_web_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mulan_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
    _complete_all_tracks_for_rhythm_lab(repository, existing_source="mulan")
    artifact_dir = tmp_path / "artifacts"
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path, artifact_dir=artifact_dir)
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    for index, track in enumerate(SourceDatabase(repository.path).list_tracks()):
        scoped.set_label(track, "yes" if index < 2 else "no")
    _write_promotable_artifact(
        artifact_dir,
        output=output,
        catalog_uuid=repository.catalog_uuid,
        stamp="20260807T100000Z",
    )
    calibrated_artifact: Path | None = None

    def fake_benchmark(
        source_db_path,
        labels_db_path,
        selected_artifact_dir,
        *,
        classifier_key,
        feature_sets,
        random_state=42,
        calibrate=False,
        progress_callback=None,
    ):
        nonlocal calibrated_artifact
        assert Path(source_db_path) == repository.path
        assert Path(labels_db_path) == lab_path
        assert Path(selected_artifact_dir) == artifact_dir
        assert classifier_key == "focused"
        assert feature_sets == ("mulan",)
        assert random_state == 42
        assert calibrate is True
        assert progress_callback is not None
        progress_callback("Calibrating test model", 5, 10)
        calibrated_artifact = _write_promotable_artifact(
            artifact_dir,
            output=output,
            catalog_uuid=repository.catalog_uuid,
            stamp="20260807T110000Z",
            calibrated=True,
        )
        return {
            "mulan": {
                "status": "trained",
                "artifact_path": str(calibrated_artifact),
                "metrics_path": str(
                    calibrated_artifact.with_suffix(".metrics.json")
                ),
                "trained_rows": 4,
                "skipped_rows": 0,
                "feature_count": 768,
            }
        }

    monkeypatch.setattr(
        web_app_module,
        "benchmark_lab_database",
        fake_benchmark,
    )
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_LABELS", 4)
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_POSITIVE", 2)
    monkeypatch.setattr(web_app_module, "MIN_CALIBRATION_NEGATIVE", 2)
    app = create_app(
        repository.path,
        labels_db_path=lab_path,
        classifier_target_root=tmp_path / "promoted",
        source_catalog_uuid=repository.catalog_uuid,
    )

    with TestClient(app) as client:
        calibration = client.post(
            "/api/profiles/focused/training/calibrate",
            json={"feature_set": "mulan"},
        )
        assert calibration.status_code == 200, calibration.text
        assert calibrated_artifact is not None
        assert calibration.json()["artifact"] == str(calibrated_artifact)
        calibration_progress = client.get(
            "/api/profiles/focused/training/progress"
        ).json()
        assert calibration_progress == {
            "operation": "calibrate",
            "status": "completed",
            "stage": "Calibration complete",
            "percent": 100,
            "error": None,
        }
        readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mulan"},
        ).json()
        option = readiness["artifact_summary"]["promotion_options"][0]
        assert option["latest_model"] == str(calibrated_artifact)
        assert option["calibration_status"] == "calibrated"
        promoted = client.post(
            "/api/profiles/focused/promote",
            json={"feature_set": "mulan"},
        )

    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["source_artifact"] == str(calibrated_artifact)


def test_tampered_or_unbound_artifact_is_rejected_before_joblib_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "focused-mulan-test.joblib"
    joblib.dump(
        {
            "classifier_key": "focused",
            "feature_set": "mulan",
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


def test_promote_replaces_the_root_model_pair(tmp_path: Path) -> None:
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
    profile_dir = target_root / "focused"
    assert Path(promoted["model_path"]) == profile_dir / "model.joblib"
    assert Path(promoted["metadata_path"]) == profile_dir / "model.json"
    assert not (profile_dir / "current.json").exists()
    assert not (profile_dir / "generations").exists()
    manifest = json.loads((profile_dir / "model.json").read_text(encoding="utf-8"))
    assert manifest["publication_status"] == "ready"
    assert manifest["profile_description"] == "Focused classifier description."
    resolved = resolve_classifier_artifact_paths(profile_dir / "model.joblib")
    assert resolved.model_path == profile_dir / "model.joblib"
    discovered = promoted_classifiers(target_root)
    assert len(discovered) == 1
    assert discovered[0]["manifest_status"] == "valid"
    assert discovered[0]["profile_description"] == "Focused classifier description."
    assert discovered[0]["model_path"] == str(profile_dir / "model.joblib")


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    [
        ("empty_features", "non-empty ordered feature_names list"),
        ("unusable_model", "must implement predict_proba"),
    ],
)
def test_semantically_invalid_artifact_does_not_replace_root_model(
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
    model_path = Path(first["model_path"])
    metadata_path = Path(first["metadata_path"])
    model_before = model_path.read_bytes()
    metadata_before = metadata_path.read_bytes()

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

    assert model_path.read_bytes() == model_before
    assert metadata_path.read_bytes() == metadata_before
    resolved = resolve_classifier_artifact_paths(model_path)
    assert resolved.model_path == first["model_path"]


def test_promoted_model_requires_ready_publication_status_before_load(
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
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["publication_status"] = "publishing"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    calls = 0

    def forbidden_load(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("joblib.load must not run before SHA-256 verification")

    monkeypatch.setattr(joblib, "load", forbidden_load)
    with pytest.raises(ArtifactIntegrityError, match="publication_status"):
        load_verified_artifact(model_path)
    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="focused",
    )
    assert summary.status == "invalid"
    assert calls == 0

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
    load_classifier_manifest_summary,
    resolve_classifier_artifact_paths,
)
from dj_track_similarity.classifier_scoring import promoted_classifiers  # noqa: E402
from dj_track_similarity.db_analysis import AnalysisRepository  # noqa: E402
from dj_track_similarity.db_ddl import create_library_schema  # noqa: E402
from dj_track_similarity.db_schema import insert_library  # noqa: E402
from dj_track_similarity.db_summary import SummaryRepository  # noqa: E402
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


class Repository(AnalysisRepository, SummaryRepository):
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


def _insert_track_without_embedding(
    repository: Repository,
    *,
    index: int,
) -> None:
    with repository.connect() as core:
        core.execute(
            """
            INSERT INTO tracks(
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, ?, 1, ?, ?, ?)
            """,
            (str(uuid.uuid4()), f"C:/music/{index}.wav", index + 1, NOW, NOW, NOW),
        )


def _write_promotable_artifact(
    root: Path,
    *,
    output: AnalysisOutput | None = None,
    catalog_uuid: str | None = "catalog-current",
    stamp: str = "test",
    calibrated: bool = False,
) -> Path:
    selected_output = output or _mert_output()
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


def test_source_tracks_read_current_file_tags_schema(tmp_path: Path) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
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
                track_id, content_generation, syncopated_rhythm,
                genres_json, analyzed_at
            ) VALUES (?, 1, 0, ?, ?)
            """,
            (
                track_id,
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
    page = source.list_tracks_page(
        labels_db_path=lab_path,
        classifier_key="focused",
        label_keys=("yes", "no"),
        training_label_keys=("yes", "no"),
    )
    assert page["total"] == 1
    assert len(page["items"]) == 1
    item = page["items"][0]
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


def test_source_feature_inventory_is_cached_until_storage_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
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
    assert refreshed_counts["mert"] == first_counts["mert"] + 1


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
        classifier_target_root=tmp_path / "promoted",
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
        sonara_mert_maest_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "sonara+mert+maest"},
        ).json()
        muq_readiness = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "muq"},
        ).json()
        assert mert_readiness["features_ready"] is True
        assert mert_readiness["promoted_model"]["status"] == "not_promoted"
        assert mert_readiness["trained_model"]["feature_set"] is None
        assert mert_readiness["labels_ready"] is False
        assert mert_readiness["calibration_ready"] is False
        assert "100" in mert_readiness["calibration_readiness"]["reason"]
        assert sonara_mert_maest_readiness["features_ready"] is False
        assert sonara_mert_maest_readiness["feature_recipe"]["required_sources"] == [
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

        index = client.get("/")
        assert index.status_code == 200
        assert "app.js?v=rhythm-lab-20260811-promoted-model-quality-v4" in index.text
        assert 'id="refreshCandidatesStatus"' not in index.text

        static_script = client.get("/static/app.js")
        assert static_script.status_code == 200
        script = static_script.text
        assert "track.track_id" in script
        assert "track.file_path" in script
        assert "catalog_uuid: track.catalog_uuid" in script
        assert "function trackStatusLine(track)" in script
        assert 'activeView === "candidates" ? predictionScoreStatus(track)' in script
        assert "maest-genre-pill" in script
        assert 'split("---").pop()' in script
        assert "lucide-audio-waveform" in script
        assert '"Trained Model"' in script
        assert '"Promoted Model"' in script
        assert "Promoted model.json" in script
        assert "Next training recipe" in script
        assert 'label: "Combined"' in script
        assert '"muq"' in script
        assert "source_data_ready" in script
        assert '"sonara+mert+maest+clap+muq"' in script
        assert "async function calibrateClassifier()" in script
        assert "/training/calibrate" in script
        assert "async function refreshCandidates()" in script
        assert "/predictions/refresh" in script
        assert "function setWorkflowStatus(message)" in script
        assert "let trainingProgressPollGeneration = 0;" in script
        assert "let trainingProgressHasStarted = false;" in script
        assert 'class="training-workflow-feedback"' in script
        assert 'id="refreshCandidatesStatus" class="meta source-status-line"' in script
        assert 'id="trainingInformation"' in script
        assert "function refreshTrainingInformation(data)" in script
        train_refresh_script = script.split("async function trainRefresh()", 1)[1].split(
            "async function runBenchmark()", 1
        )[0]
        assert 'switchView("candidates")' not in train_refresh_script
        assert "await refreshWorkflowData({ candidatesChanged: true });" not in train_refresh_script
        assert "loadTrainingView()" not in train_refresh_script
        assert 'stage: "Training and candidate refresh complete", percent: 100' in train_refresh_script
        refresh_candidates_script = script.split(
            "async function refreshCandidates()", 1
        )[1].split("async function promoteClassifier()", 1)[0]
        assert 'switchView("candidates")' not in refresh_candidates_script
        assert "await refreshWorkflowData({ candidatesChanged: true });" not in refresh_candidates_script
        assert "loadTrainingView()" not in refresh_candidates_script
        assert "await loadTrainingReadiness();" in refresh_candidates_script
        assert 'startTrainingProgressPolling(activeProfile.classifier_key, "refresh");' in refresh_candidates_script
        assert 'String(progress.operation || "") !== operation' in script
        benchmark_script = script.split("async function runBenchmark()", 1)[1].split(
            "function selectedArtifactFeatureSet", 1
        )[0]
        assert "loadTrainingView()" not in benchmark_script
        assert 'stage: "Benchmark complete", percent: 100' in benchmark_script
        assert "await loadTrainingReadiness();" in benchmark_script
        promotion_script = script.split("async function promoteClassifier()", 1)[1].split(
            "async function refreshWorkflowData", 1
        )[0]
        assert "await refreshWorkflowData();" not in promotion_script
        assert 'stage: "Promotion complete", percent: 100' in promotion_script
        assert "await loadTrainingReadiness();" in promotion_script
        calibrate_script = script.split("async function calibrateClassifier()", 1)[1].split(
            "async function refreshCandidates()", 1
        )[0]
        assert "loadTrainingView()" not in calibrate_script
        assert "await loadTrainingReadiness();" in calibrate_script
        assert 'startTrainingProgressPolling(activeProfile.classifier_key, "calibrate");' in calibrate_script
        assert 'stage: "Calibration complete", percent: 100' in calibrate_script
        assert "feature_group_weights" in script
        assert '["sonara", "mert", "maest", "clap", "muq"]' in script
        assert "Loading Training" in script
        assert "Training could not load" in script
        assert "if (!selected) return" in script
        assert "track.id" not in script
        assert "track.path" not in script


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
            params={"feature_set": "mert"},
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
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    _insert_track_without_embedding(repository, index=0)
    for index in range(1, 4):
        _insert_track(repository, output, index=index)
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
            params={"feature_set": "mert"},
        ).json()
        response = client.post(
            "/api/profiles/focused/training/calibrate",
            json={"feature_set": "mert"},
        )
        after = client.get(
            "/api/profiles/focused/training/readiness",
            params={"feature_set": "mert"},
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
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
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
            "mert": {
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
        response = client.post(
            "/api/profiles/focused/training/train-refresh",
            json={"feature_set": "mert"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["artifact"] == str(trained_artifact)
    assert response.json()["artifact"] != str(newer_artifact)


def test_web_promotion_rejects_artifact_when_muq_vectors_are_invalid(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    current_muq = AnalysisOutput("muq", "embedding")
    repository.register_analysis_outputs((current_muq,))
    _insert_track(repository, current_muq, index=0)
    with repository.connect() as connection:
        connection.execute(
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
    _write_promotable_artifact(
        artifact_dir,
        output=current_muq,
        catalog_uuid=repository.catalog_uuid,
    )

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


def test_prediction_refresh_uses_requested_feature_recipe(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
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
            json={"feature_set": "mert"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["feature_set"] == "mert"
    assert response.json()["artifact"] == str(artifact)
    assert response.json()["predicted"] == 4


def test_prediction_rejects_artifact_from_another_source_catalog(
    tmp_path: Path,
) -> None:
    first_repository = Repository(tmp_path)
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_repository = Repository(other_root)
    output = _mert_output()
    other_repository.register_analysis_outputs((output,))
    _insert_track(other_repository, output, index=0)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=first_repository.catalog_uuid,
    )

    with pytest.raises(ValueError, match="does not match active catalog"):
        apply_model_to_lab(
            other_repository.path,
            lab_path,
            artifact,
            classifier_key="focused",
        )


def test_prediction_rejects_artifact_without_source_catalog_binding(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    _insert_track(repository, output, index=0)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=None,
    )

    with pytest.raises(ValueError, match="not bound to a source catalog"):
        apply_model_to_lab(
            repository.path,
            lab_path,
            artifact,
            classifier_key="focused",
        )
    with pytest.raises(PromotionError, match="not bound to a source catalog"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=artifact,
            target_root=tmp_path / "promoted",
        )


def test_prediction_refresh_uses_bounded_features_and_one_atomic_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(5):
        _insert_track(repository, output, index=index)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    artifact = _write_promotable_artifact(
        tmp_path / "artifacts",
        output=output,
        catalog_uuid=repository.catalog_uuid,
    )
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    old_track = SourceDatabase(repository.path).list_tracks()[0]
    scoped.save_prediction(
        old_track,
        feature_set="muq",
        model_artifact="old-other-recipe.joblib",
        label="no",
        confidence=0.7,
        probabilities={"yes": 0.3, "no": 0.7},
    )
    feature_batch_sizes: list[int] = []
    staged_batch_sizes: list[int] = []
    swap_calls = 0
    original_tracks_by_ids = SourceDatabase.tracks_by_ids
    original_stage_append = predictions_module.PredictionStage.append
    original_replace_predictions = (
        RhythmLabDatabase.replace_predictions_from_stage
    )

    def recording_tracks_by_ids(
        self: SourceDatabase,
        track_ids: object,
    ) -> dict[int, object]:
        selected_ids = list(track_ids)  # type: ignore[arg-type]
        feature_batch_sizes.append(len(selected_ids))
        return original_tracks_by_ids(self, selected_ids)

    def recording_stage_append(
        self: object,
        predictions: object,
    ) -> None:
        rows = list(predictions)  # type: ignore[arg-type]
        staged_batch_sizes.append(len(rows))
        original_stage_append(self, rows)

    def recording_replace_predictions_from_stage(
        self: RhythmLabDatabase,
        stage_path: Path,
        **kwargs: object,
    ) -> int:
        nonlocal swap_calls
        swap_calls += 1
        return original_replace_predictions(self, stage_path, **kwargs)

    monkeypatch.setattr(predictions_module, "PREDICTION_BATCH_SIZE", 2)
    monkeypatch.setattr(
        SourceDatabase,
        "tracks_by_ids",
        recording_tracks_by_ids,
    )
    monkeypatch.setattr(
        predictions_module.PredictionStage,
        "append",
        recording_stage_append,
    )
    monkeypatch.setattr(
        RhythmLabDatabase,
        "replace_predictions_from_stage",
        recording_replace_predictions_from_stage,
    )

    result = apply_model_to_lab(
        repository.path,
        lab_path,
        artifact,
        classifier_key="focused",
    )

    assert result["predicted"] == 5
    assert result["skipped"] == 0
    assert result["deleted_old_predictions"] == 1
    assert feature_batch_sizes == [2, 2, 1]
    assert staged_batch_sizes == [2, 2, 1]
    assert swap_calls == 1
    visible_rows = scoped.predictions()
    assert len(visible_rows) == 5
    assert {row["model_artifact"] for row in visible_rows} == {str(artifact)}


def test_prediction_refresh_failure_leaves_previous_candidate_set_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(5):
        _insert_track(repository, output, index=index)
    lab_path = tmp_path / "lab.sqlite"
    _create_focused_profile(lab_path)
    scoped = RhythmLabDatabase(lab_path, classifier_key="focused")
    tracks = SourceDatabase(repository.path).list_tracks()
    for track in tracks:
        scoped.save_prediction(
            track,
            feature_set="mert",
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
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    for index in range(4):
        _insert_track(repository, output, index=index)
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
        assert feature_sets == ("mert",)
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
            "mert": {
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
            json={"feature_set": "mert"},
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
            params={"feature_set": "mert"},
        ).json()
        option = readiness["artifact_summary"]["promotion_options"][0]
        assert option["latest_model"] == str(calibrated_artifact)
        assert option["calibration_status"] == "calibrated"
        promoted = client.post(
            "/api/profiles/focused/promote",
            json={"feature_set": "mert"},
        )

    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["source_artifact"] == str(calibrated_artifact)


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


def test_scoring_ready_artifact_is_validated_before_root_replacement(
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

    resolved = resolve_classifier_artifact_paths(Path(promoted["model_path"]))
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

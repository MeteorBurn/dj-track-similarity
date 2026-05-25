from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import csv
import joblib

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LAB_ROOT = ROOT / "tools" / "rhythm-lab"
sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.database import LibraryDatabase

from rhythm_lab.features import build_labeled_feature_matrix
from rhythm_lab.lab_db import RhythmLabDatabase
from rhythm_lab.predictions import apply_model_to_lab, export_predictions_csv
from rhythm_lab.source_db import SourceDatabase
from rhythm_lab.training import train_feature_set
from rhythm_lab.web_app import create_app


def test_source_database_opens_existing_project_database_read_only(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "broken.wav", title="Broken")
    source.save_embedding(track_id, np.asarray([1, 0, 0], dtype=np.float32), "mert-test", embedding_key="mert")

    read_only = SourceDatabase(source_path)

    assert read_only.path == source_path.resolve()
    assert read_only.get_track(track_id).title == "Broken"
    assert read_only.embedding_track_ids("mert") == {track_id}
    with read_only.connect() as connection:
        try:
            connection.execute("CREATE TABLE should_not_write(id INTEGER)")
        except sqlite3.OperationalError as error:
            assert "readonly" in str(error).lower() or "read-only" in str(error).lower()
        else:  # pragma: no cover - defensive guard.
            raise AssertionError("source database connection allowed writes")


def test_source_database_rejects_missing_file_without_creating_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"

    try:
        SourceDatabase(missing)
    except FileNotFoundError as error:
        assert str(missing) in str(error)
    else:  # pragma: no cover - defensive guard.
        raise AssertionError("missing source database was accepted")

    assert not missing.exists()


def test_labels_database_migrates_rhythm_tables_to_break_energy_classifier_tables(tmp_path: Path) -> None:
    labels_path = tmp_path / "rhythm_lab.sqlite"
    old_lab = LibraryDatabase(labels_path)
    local_track_id = _track(old_lab, tmp_path, "local.wav", title="Local")
    with old_lab._write_lock, old_lab.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE rhythm_lab_tracks (
                track_id INTEGER PRIMARY KEY,
                source_track_id INTEGER NOT NULL UNIQUE,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE rhythm_labels (
                track_id INTEGER PRIMARY KEY,
                label TEXT NOT NULL CHECK(label IN ('broken', 'straight_four_on_the_floor', 'ambiguous')),
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            "INSERT INTO rhythm_lab_tracks(track_id, source_track_id) VALUES (?, ?)",
            (local_track_id, 777),
        )
        connection.execute(
            "INSERT INTO rhythm_labels(track_id, label, note) VALUES (?, 'straight_four_on_the_floor', 'old note')",
            (local_track_id,),
        )

    labels = RhythmLabDatabase(labels_path)

    assert labels.label_for_track(777).label == "straight"
    assert labels.label_for_track(local_track_id) is None
    assert labels.training_labels() == {777: "straight"}
    with labels.connect() as connection:
        table_names = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "classifier_labels" in table_names
        assert "classifier_predictions" in table_names
        assert "classifier_training_checkpoints" in table_names
        assert "rhythm_labels" not in table_names
        assert "rhythm_predictions" not in table_names
        assert "rhythm_training_checkpoint" not in table_names
        row = connection.execute(
            "SELECT classifier_key, source_track_id, label FROM classifier_labels"
        ).fetchone()
        assert dict(row) == {"classifier_key": "break_energy", "source_track_id": 777, "label": "straight"}


def test_labels_database_creates_default_break_energy_profile(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")

    profile = labels.get_profile("break_energy")

    assert profile.classifier_key == "break_energy"
    assert profile.name == "Break Energy"
    assert profile.positive_label == "broken"
    assert profile.negative_label == "straight"
    assert [label.key for label in profile.labels] == ["broken", "straight", "ambiguous"]
    assert [label.role for label in profile.labels] == ["positive", "negative", "review"]
    assert profile.artifact_prefix == "break-energy"


def test_profile_creation_archive_and_current_track_label_replacement(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    profile = labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    scoped = RhythmLabDatabase(labels.path, classifier_key=profile.classifier_key)

    scoped.set_label(101, "vocal")
    scoped.set_label(101, "instrumental")
    scoped.set_label(102, "uncertain")
    scoped.set_label(103, "vocal")
    scoped.set_label(103, None)
    labels.archive_profile("vocal_presence")

    assert scoped.label_for_track(101).label == "instrumental"
    assert scoped.label_for_track(103) is None
    assert scoped.training_labels() == {101: "instrumental"}
    assert [profile.classifier_key for profile in labels.list_profiles()] == ["break_energy"]
    assert "vocal_presence" in [profile.classifier_key for profile in labels.list_profiles(include_archived=True)]


def test_multiclass_profile_creation_uses_custom_single_label_per_track(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    profile = labels.create_profile(
        classifier_key="mood",
        profile_type="multiclass",
        name="Mood",
        description="User-defined mood labels.",
        artifact_dir=tmp_path / "artifacts" / "mood",
        labels=[
            {"key": "euphoric", "name": "Euphoric", "role": "class"},
            {"key": "dark", "name": "Dark", "role": "class"},
            {"key": "hypnotic", "name": "Hypnotic", "role": "class"},
        ],
    )
    scoped = RhythmLabDatabase(labels.path, classifier_key="mood")

    scoped.set_label(101, "euphoric")
    scoped.set_label(101, "dark")
    scoped.set_label(102, "hypnotic")

    assert profile.profile_type == "multiclass"
    assert profile.training_label_keys == ("euphoric", "dark", "hypnotic")
    assert [label.role for label in profile.labels] == ["class", "class", "class"]
    assert scoped.label_for_track(101).label == "dark"
    assert scoped.training_labels() == {101: "dark", 102: "hypnotic"}


def test_multiclass_profile_migrates_old_profile_label_role_check(tmp_path: Path) -> None:
    labels_path = tmp_path / "labels.sqlite"
    with sqlite3.connect(labels_path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_profiles (
                classifier_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                artifact_dir TEXT NOT NULL,
                artifact_prefix TEXT NOT NULL,
                positive_label TEXT NOT NULL,
                negative_label TEXT NOT NULL,
                archived_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE classifier_profile_labels (
                classifier_key TEXT NOT NULL,
                label_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL CHECK(role IN ('positive', 'negative', 'review')),
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(classifier_key, label_key),
                FOREIGN KEY(classifier_key) REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
            );
            """
        )

    labels = RhythmLabDatabase(labels_path)
    profile = labels.create_profile(
        classifier_key="mood",
        profile_type="multiclass",
        name="Mood",
        artifact_dir=tmp_path / "artifacts" / "mood",
        labels=[
            {"key": "warm", "name": "Warm", "role": "class"},
            {"key": "tense", "name": "Tense", "role": "class"},
        ],
    )

    assert profile.profile_type == "multiclass"
    assert [label.key for label in profile.labels] == ["warm", "tense"]


def test_label_key_rename_migrates_profile_labels_predictions_and_checkpoints(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "vocal.wav", title="Vocal")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    scoped = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")
    scoped.set_label(source.get_track(track_id), "vocal")
    scoped.save_prediction(
        source.get_track(track_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="vocal",
        confidence=0.8,
        probabilities={"vocal": 0.8, "instrumental": 0.2},
    )
    scoped.record_training_checkpoint({"vocal": 12, "instrumental": 9}, model_artifact="model.joblib")

    labels.rename_label_key("vocal_presence", "vocal", "lead_vocal", display_name="Lead Vocal")
    renamed = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")

    profile = renamed.get_profile("vocal_presence")
    assert profile.positive_label == "lead_vocal"
    assert [label.key for label in profile.labels] == ["lead_vocal", "instrumental", "uncertain"]
    assert renamed.label_for_track(track_id).label == "lead_vocal"
    prediction = renamed.predictions()[0]
    assert prediction["label"] == "lead_vocal"
    assert prediction["probabilities"] == {"instrumental": 0.2, "lead_vocal": 0.8}
    assert renamed.training_checkpoint()["counts"] == {"instrumental": 9, "lead_vocal": 12}


def test_web_app_profile_scoped_track_labels_are_isolated(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "voice.wav", title="Voice")
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    response = client.post(f"/api/profiles/vocal_presence/tracks/{track_id}/label", json={"label": "vocal"})
    vocal_tracks = client.get("/api/profiles/vocal_presence/tracks", params={"label": "vocal"}).json()
    break_tracks = client.get("/api/profiles/break_energy/tracks", params={"label": "vocal"})

    assert response.status_code == 200
    assert response.json()["label"] == "vocal"
    assert vocal_tracks["total"] == 1
    assert vocal_tracks["items"][0]["label"] == "vocal"
    assert break_tracks.status_code == 400
    assert RhythmLabDatabase(labels_path, classifier_key="break_energy").label_for_track(track_id) is None


def test_web_app_creates_multiclass_profile_from_request(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    labels_path = tmp_path / "labels.sqlite"
    client = TestClient(create_app(labels_db_path=labels_path))

    response = client.post(
        "/api/profiles",
        json={
            "classifier_key": "mood",
            "profile_type": "multiclass",
            "name": "Mood",
            "description": "User-defined mood classes.",
            "artifact_dir": str(tmp_path / "artifacts" / "mood"),
            "labels": [
                {"key": "euphoric", "name": "Euphoric", "description": "Uplifting peak-time mood.", "role": "class"},
                {"key": "dark", "name": "Dark", "description": "Tense low-light mood.", "role": "class"},
                {"key": "hypnotic", "name": "Hypnotic", "description": "Looping trance-like mood.", "role": "class"},
            ],
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["profile_type"] == "multiclass"
    assert payload["positive_label"] == "euphoric"
    assert payload["negative_label"] == "dark"
    assert [label["role"] for label in payload["labels"]] == ["class", "class", "class"]
    assert payload["labels"][0]["description"] == "Uplifting peak-time mood."


def test_web_app_profile_refresh_candidates_uses_profile_artifact_dir(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "voice.wav", title="Voice")
    labels_path = tmp_path / "labels.sqlite"
    artifact_dir = tmp_path / "artifacts" / "vocal-presence"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "vocal-presence-combined-20260524T110000Z.joblib"
    artifact.write_bytes(b"model")
    labels = RhythmLabDatabase(labels_path)
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=artifact_dir,
        artifact_prefix="vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    import rhythm_lab.web_app as web_app

    calls = []

    def fake_apply_model_to_lab(source_db_path: Path, labels_db_path: Path, artifact_path: Path, *, classifier_key: str):
        calls.append((source_db_path, labels_db_path, artifact_path, classifier_key))
        scoped = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
        scoped.save_prediction(
            source.get_track(track_id),
            feature_set="combined",
            model_artifact=artifact_path,
            label="vocal",
            confidence=0.9,
            probabilities={"vocal": 0.9, "instrumental": 0.1},
        )
        return {"feature_set": "combined", "predicted": 1, "skipped": 0}

    monkeypatch.setattr(web_app, "apply_model_to_lab", fake_apply_model_to_lab)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    refreshed = client.post("/api/profiles/vocal_presence/predictions/refresh")
    candidates = client.get("/api/profiles/vocal_presence/predictions", params={"label": "all"}).json()

    assert refreshed.status_code == 200
    assert refreshed.json()["artifact"] == str(artifact)
    assert calls == [(source_path.resolve(), labels_path, artifact, "vocal_presence")]
    assert candidates["total"] == 1
    assert candidates["items"][0]["positive_probability"] == 0.9
    assert candidates["items"][0]["negative_probability"] == 0.1
    assert candidates["items"][0]["predicted_label"] == "vocal"


def test_web_app_reads_source_database_and_writes_labels_database_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken_id = _track(source, tmp_path, "broken.wav", title="Broken")
    straight_id = _track(source, tmp_path, "straight.wav", title="Straight")
    source.save_genres(broken_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    source.save_sonara_features(broken_id, {"onset_density": {"type": "float", "value": 4.2}}, model_name="sonara-test")
    source.save_embedding(broken_id, np.asarray([1, 0, 0], dtype=np.float32), "maest-test", embedding_key="maest")
    labels_path = tmp_path / "labels.sqlite"
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    summary = client.get("/api/profiles/break_energy/summary").json()
    tracks = client.get("/api/tracks").json()
    assert summary["tracks"] == 2
    assert summary["sonara"] == 1
    assert summary["maest"] == 1
    assert summary["mert"] == 0
    assert tracks["total"] == 2
    first = tracks["items"][0]
    assert first["id"] == broken_id
    assert first["label"] is None
    assert first["maest_syncopated_rhythm"] is True
    assert first["feature_status"] == {"sonara": True, "mert": False, "maest": True}
    assert first["genres"] == ["Breakbeat"]
    assert next(item for item in tracks["items"] if item["id"] == straight_id)["maest_syncopated_rhythm"] is False

    response = client.post(f"/api/tracks/{broken_id}/label", json={"label": "broken"})

    assert response.status_code == 200
    assert response.json()["label"] == "broken"
    assert RhythmLabDatabase(labels_path).label_for_track(broken_id).label == "broken"
    with source.connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='classifier_labels'"
        ).fetchone() is None


def test_web_app_predictions_endpoint_filters_candidates_by_probability_focus(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    low_id = _track(source, tmp_path, "low.wav", title="Low")
    high_id = _track(source, tmp_path, "high.wav", title="High")
    balanced_id = _track(source, tmp_path, "balanced.wav", title="Balanced")
    source.save_genres(high_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    source.save_sonara_features(high_id, {"onset_density": {"type": "float", "value": 4.2}}, model_name="sonara-test")
    source.save_embedding(high_id, np.asarray([1, 0, 0], dtype=np.float32), "maest-test", embedding_key="maest")
    source.save_embedding(high_id, np.asarray([0, 1, 0], dtype=np.float32), "mert-test", embedding_key="mert")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.save_prediction(
        source.get_track(low_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="straight",
        confidence=0.8,
        probabilities={"broken": 0.2, "straight": 0.8},
    )
    labels.save_prediction(
        source.get_track(high_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="broken",
        confidence=0.7,
        probabilities={"broken": 0.7, "straight": 0.3},
    )
    labels.save_prediction(
        source.get_track(balanced_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="broken",
        confidence=0.51,
        probabilities={"broken": 0.51, "straight": 0.49},
    )
    labels.set_label(source.get_track(high_id), "broken")
    import rhythm_lab.source_db as source_db

    def fail_single_track_load(self, track_id: int):
        raise AssertionError("predictions endpoint must not fetch source tracks one at a time")

    monkeypatch.setattr(source_db.SourceDatabase, "get_track", fail_single_track_load)
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    all_candidates = client.get("/api/predictions", params={"label": "all"}).json()
    unlabeled = client.get("/api/predictions", params={"label": "unlabeled"}).json()
    filtered = client.get("/api/predictions", params={"label": "all", "min_broken": 0.5}).json()
    straight_focus = client.get(
        "/api/predictions",
        params={"label": "all", "probability_focus": "straight_highest"},
    ).json()
    balanced_focus = client.get(
        "/api/predictions",
        params={"label": "all", "probability_focus": "balanced"},
    ).json()
    combined = client.get(
        "/api/predictions",
        params={"label": "broken", "min_broken": 0.5, "q": "high", "syncopated": "yes"},
    ).json()
    mismatched = client.get(
        "/api/predictions",
        params={"label": "broken", "min_broken": 0.5, "q": "low", "syncopated": "yes"},
    ).json()

    assert all_candidates["total"] == 3
    assert [item["id"] for item in all_candidates["items"]] == [high_id, balanced_id, low_id]
    assert all_candidates["items"][0]["broken_probability"] == 0.7
    assert all_candidates["items"][0]["label"] == "broken"
    assert all_candidates["items"][0]["genres"] == ["Breakbeat"]
    assert all_candidates["items"][0]["maest_syncopated_rhythm"] is True
    assert all_candidates["items"][0]["feature_status"] == {"sonara": True, "mert": True, "maest": True}
    assert unlabeled["total"] == 2
    assert unlabeled["items"][0]["id"] == balanced_id
    assert filtered["total"] == 2
    assert [item["id"] for item in filtered["items"]] == [high_id, balanced_id]
    assert [item["id"] for item in straight_focus["items"]] == [low_id, balanced_id, high_id]
    assert [item["id"] for item in balanced_focus["items"]] == [balanced_id, high_id, low_id]
    assert combined["total"] == 1
    assert combined["items"][0]["id"] == high_id
    assert mismatched["total"] == 0


def test_web_app_refresh_candidates_uses_latest_combined_artifact_and_prunes_old_predictions(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    older = artifacts / "break-energy-combined-20260524T100000Z.joblib"
    newer = artifacts / "break-energy-combined-20260524T110000Z.joblib"
    maest = artifacts / "break-energy-maest-20260524T120000Z.joblib"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    maest.write_bytes(b"maest")
    import rhythm_lab.web_app as web_app

    calls = []

    def fake_apply_model_to_lab(source_db_path: Path, labels_db_path: Path, artifact_path: Path):
        calls.append((source_db_path, labels_db_path, artifact_path))
        labels = RhythmLabDatabase(labels_db_path)
        source = LibraryDatabase(source_db_path)
        track_id = _track(source, tmp_path, "predicted.wav", title="Predicted")
        labels.save_prediction(
            source.get_track(track_id),
            feature_set="combined",
            model_artifact=artifact_path,
            label="broken",
            confidence=0.9,
            probabilities={"broken": 0.9, "straight": 0.1},
        )
        labels.save_prediction(
            source.get_track(track_id),
            feature_set="combined",
            model_artifact=older,
            label="straight",
            confidence=0.8,
            probabilities={"broken": 0.2, "straight": 0.8},
        )
        return {"feature_set": "combined", "predicted": 1, "skipped": 2}

    monkeypatch.setattr(web_app, "ARTIFACT_DIR", artifacts)
    monkeypatch.setattr(web_app, "apply_model_to_lab", fake_apply_model_to_lab)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    response = client.post("/api/predictions/refresh")

    assert response.status_code == 200
    assert response.json()["artifact"] == str(newer)
    assert response.json()["predicted"] == 1
    assert response.json()["skipped"] == 2
    assert calls == [(source_path.resolve(), labels_path.resolve(), newer)]
    predictions = RhythmLabDatabase(labels_path).predictions()
    assert len(predictions) == 1
    assert predictions[0]["model_artifact"] == str(newer)


def test_web_app_train_refresh_requires_100_new_broken_and_straight_labels(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    for index in range(100):
        labels.set_label(10_000 + index, "broken")
        labels.set_label(20_000 + index, "straight")
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    artifact = artifacts / "break-energy-combined-20260524T130000Z.joblib"
    import rhythm_lab.web_app as web_app

    calls = []

    def fake_benchmark_lab_database(source_db_path: Path, labels_db_path: Path, artifact_dir: Path):
        calls.append(("train", source_db_path, labels_db_path, artifact_dir))
        artifact.write_bytes(b"combined")
        return {"combined": {"status": "trained", "artifact_path": str(artifact)}}

    def fake_apply_model_to_lab(source_db_path: Path, labels_db_path: Path, artifact_path: Path):
        calls.append(("predict", source_db_path, labels_db_path, artifact_path))
        return {"feature_set": "combined", "predicted": 0, "skipped": 0}

    monkeypatch.setattr(web_app, "ARTIFACT_DIR", artifacts)
    monkeypatch.setattr(web_app, "benchmark_lab_database", fake_benchmark_lab_database)
    monkeypatch.setattr(web_app, "apply_model_to_lab", fake_apply_model_to_lab)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    ready = client.get("/api/training/readiness").json()
    trained = client.post("/api/training/train-refresh")
    blocked = client.post("/api/training/train-refresh")

    assert ready["ready"] is True
    assert ready["added"] == {"broken": 100, "straight": 100}
    assert trained.status_code == 200
    assert trained.json()["training_counts"] == {"broken": 100, "straight": 100}
    assert trained.json()["artifact"] == str(artifact)
    assert trained.json()["artifact_cleanup"] == {"deleted_joblib": 0, "deleted_metrics": 0}
    assert calls == [
        ("train", source_path.resolve(), labels_path.resolve(), artifacts),
        ("predict", source_path.resolve(), labels_path.resolve(), artifact),
    ]
    assert RhythmLabDatabase(labels_path).training_checkpoint()["counts"] == {"broken": 100, "straight": 100}
    assert blocked.status_code == 400
    assert "Need 100 new broken and 100 new straight Break Energy labels" in blocked.json()["detail"]


def test_web_app_training_readiness_initializes_checkpoint_from_existing_combined_artifact(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    for index in range(500):
        labels.set_label(10_000 + index, "broken")
        labels.set_label(20_000 + index, "straight")
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    artifact = artifacts / "break-energy-combined-20260524T130000Z.joblib"
    artifact.write_bytes(b"combined")
    import rhythm_lab.web_app as web_app

    monkeypatch.setattr(web_app, "ARTIFACT_DIR", artifacts)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    ready = client.get("/api/training/readiness").json()
    blocked = client.post("/api/training/train-refresh")

    assert ready["ready"] is False
    assert ready["current"] == {"broken": 500, "straight": 500}
    assert ready["last_trained"] == {"broken": 500, "straight": 500}
    assert ready["added"] == {"broken": 0, "straight": 0}
    assert RhythmLabDatabase(labels_path).training_checkpoint()["counts"] == {"broken": 500, "straight": 500}
    assert blocked.status_code == 400


def test_artifact_cleanup_keeps_recent_files_per_feature_and_protected_artifact(tmp_path: Path) -> None:
    from rhythm_lab.web_app import cleanup_training_artifacts

    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    for index in range(5):
        (artifacts / f"break-energy-combined-20260524T10000{index}Z.joblib").write_bytes(b"model")
        (artifacts / f"break-energy-mert-20260524T10000{index}Z.joblib").write_bytes(b"model")
    for index in range(12):
        (artifacts / f"break-energy-combined-20260524T1100{index:02d}Z.metrics.json").write_text("{}", encoding="utf-8")
    protected = artifacts / "break-energy-combined-20260524T100000Z.joblib"
    unrelated = artifacts / "broken-candidates.csv"
    unrelated.write_text("source_track_id\n", encoding="utf-8")

    result = cleanup_training_artifacts(artifacts, protected_artifact=protected)

    remaining = {path.name for path in artifacts.iterdir()}
    assert protected.name in remaining
    assert unrelated.name in remaining
    assert "break-energy-combined-20260524T100001Z.joblib" not in remaining
    assert "break-energy-mert-20260524T100000Z.joblib" not in remaining
    assert "break-energy-combined-20260524T110001Z.metrics.json" not in remaining
    assert len([name for name in remaining if name.startswith("break-energy-combined-") and name.endswith(".joblib")]) == 4
    assert len([name for name in remaining if name.startswith("break-energy-mert-") and name.endswith(".joblib")]) == 3
    assert len([name for name in remaining if name.startswith("break-energy-combined-") and name.endswith(".metrics.json")]) == 10
    assert result["deleted_joblib"] == 3
    assert result["deleted_metrics"] == 2


def test_cli_promote_break_energy_copies_latest_combined_model_to_classifier_asset(tmp_path: Path) -> None:
    from rhythm_lab.cli import build_parser

    artifacts = tmp_path / "artifacts" / "break-energy"
    target = tmp_path / "models" / "classifiers" / "break-energy"
    artifacts.mkdir(parents=True)
    old = artifacts / "break-energy-combined-20260524T100000Z.joblib"
    latest = artifacts / "break-energy-combined-20260524T110000Z.joblib"
    maest = artifacts / "break-energy-maest-20260524T120000Z.joblib"
    joblib.dump({"feature_set": "combined", "label_order": ["broken", "straight"], "model": object()}, old)
    joblib.dump({"feature_set": "combined", "label_order": ["broken", "straight"], "model": object()}, latest)
    joblib.dump({"feature_set": "maest", "label_order": ["broken", "straight"], "model": object()}, maest)

    args = build_parser().parse_args([
        "promote-break-energy",
        "--artifacts",
        str(artifacts),
        "--target",
        str(target),
        "--labels",
        str(tmp_path / "labels.sqlite"),
    ])
    args.func(args)

    promoted = target / "model.joblib"
    metadata_path = target / "model.json"
    assert promoted.exists()
    assert joblib.load(promoted)["feature_set"] == "combined"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["classifier"] == "break_energy"
    assert metadata["score_name"] == "Break Energy"
    assert metadata["source_artifact"] == str(latest)


def test_web_app_tracks_endpoint_uses_source_sql_pagination(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    first_id = _track(source, tmp_path, "a.wav", title="A")
    second_id = _track(source, tmp_path, "b.wav", title="B")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.set_label(source.get_track(second_id), "straight")
    import rhythm_lab.source_db as source_db

    def fail_full_scan(self):
        raise AssertionError("tracks endpoint must not full-scan the source database")

    monkeypatch.setattr(source_db.SourceDatabase, "list_tracks", fail_full_scan)
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    page = client.get("/api/tracks", params={"limit": 1, "offset": 1}).json()
    labeled = client.get("/api/tracks", params={"label": "straight"}).json()

    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == second_id
    assert labeled["total"] == 1
    assert labeled["items"][0]["label"] == "straight"
    assert labeled["items"][0]["id"] == second_id
    assert first_id != second_id


def test_web_app_summary_uses_embedding_counts_without_loading_id_sets(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "a.wav", title="A")
    source.save_embedding(track_id, np.asarray([1, 0, 0], dtype=np.float32), "mert-test", embedding_key="mert")
    import rhythm_lab.source_db as source_db

    def fail_id_set(self, embedding_key: str):
        raise AssertionError("summary must count embeddings in SQL instead of loading id sets")

    monkeypatch.setattr(source_db.SourceDatabase, "embedding_track_ids", fail_id_set)
    client = TestClient(create_app(source_path, labels_db_path=tmp_path / "labels.sqlite"))

    summary = client.get("/api/summary").json()

    assert summary["tracks"] == 1
    assert summary["mert"] == 1
    assert summary["maest"] == 0


def test_web_app_source_switch_requires_existing_database(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    missing_path = tmp_path / "missing.sqlite"
    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))

    missing = client.post("/api/source/switch", json={"path": str(missing_path)})
    loaded = client.post("/api/source/switch", json={"path": str(source_path)})
    current = client.get("/api/source/current").json()

    assert missing.status_code == 400
    assert not missing_path.exists()
    assert loaded.status_code == 200
    assert loaded.json()["selected"] is True
    assert current["path"] == str(source_path.resolve())


def test_web_app_source_switch_accepts_quoted_or_padded_manual_path(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))

    quoted = client.post("/api/source/switch", json={"path": f' "{source_path}" '})

    assert quoted.status_code == 200
    assert quoted.json()["path"] == str(source_path.resolve())


def test_cli_serve_does_not_load_source_database_by_default() -> None:
    from rhythm_lab.cli import build_parser

    args = build_parser().parse_args(["serve"])

    assert args.source is None


def test_web_app_uses_existing_database_file_dialog(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import rhythm_lab.web_app as web_app

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    monkeypatch.setattr(web_app, "open_existing_database_file_dialog", lambda: source_path)
    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))

    response = client.post("/api/source/dialog")

    assert response.status_code == 200
    assert response.json()["path"] == str(source_path.resolve())
    assert response.json()["selected"] is False
    assert client.get("/api/source/current").json()["selected"] is False


def test_web_app_html_contains_source_database_controls(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert "<strong>Rhythm Lab</strong>" in html
    assert 'id="activeProfileName">No profile selected</span>' in html
    assert 'id="sourcePath"' in html
    assert 'id="chooseSource"' in html
    assert 'id="loadSource"' in html
    assert 'fetch("/api/source/dialog"' in script
    assert 'fetch("/api/source/switch"' in script
    assert 'id="summary" class="summary-strip"' in html
    assert "function renderSummary(data)" in script
    assert "coverageBadge(\"SONARA\", data.sonara || 0, \"sonara\")" in script
    assert "labelCountBadges(data.labels || {})" in script
    assert "`${data.tracks} tracks | MAEST ${data.maest} | MERT ${data.mert} | Labels: ${formatLabelCounts(data.labels)}`" not in script


def test_web_app_requires_explicit_profile_selection_on_startup(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    script = client.get("/static/app.js").text

    assert 'addOption(profileSelectEl, "", "Choose profile");' in script
    assert 'activeProfile = null;' in script
    assert 'activeProfileNameEl.textContent = "No profile selected";' in script
    assert "profiles[0].classifier_key" not in script


def test_web_app_serves_static_profile_ui_without_hardcoded_label_buttons(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text

    assert '<link rel="stylesheet" href="/static/styles.css?v=summary-badges-1" />' in html
    assert '<script src="/static/app.js?v=summary-badges-1" defer></script>' in html
    assert 'id="profileSelect"' in html
    assert "/api/profiles" in script
    assert "function renderLabelButtons" in script
    assert '<button data-label="broken">Broken</button>' not in html
    assert "classifier-gradient" in styles


def test_profile_dialog_cancel_closes_without_form_validation(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert '<button id="cancelProfileButton" type="button" value="cancel">Cancel</button>' in html
    assert '<button id="createProfileButton" type="submit" value="default">Create</button>' in html
    assert 'document.getElementById("cancelProfileButton").addEventListener("click", () => profileDialogEl.close());' in script


def test_profile_dialog_exposes_multiclass_type_and_custom_labels(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert '<h2>New classifier profile</h2>' in html
    assert 'id="newProfileType"' in html
    assert '<option value="binary" selected>Binary</option>' in html
    assert '<option value="multiclass">Multiclass</option>' in html
    assert 'id="multiclassLabelRows"' in html
    assert 'id="addMulticlassLabel"' in html
    assert 'class="multiclass-label-description"' in html
    assert 'function collectNewProfileLabels' in script
    assert 'profile_type: document.getElementById("newProfileType").value' in script
    assert 'role: "class"' in script
    assert 'description: row.querySelector(".multiclass-label-description").value' in script
    assert 'document.getElementById("newProfileType").addEventListener("change", updateNewProfileTypeControls);' in script
    assert 'function updateNewProfileTypeControls' in script


def test_static_ui_non_submit_buttons_have_explicit_button_type(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    for button_id in (
        "newProfile",
        "archiveProfile",
        "chooseSource",
        "loadSource",
        "libraryTab",
        "candidatesTab",
        "trainingTab",
        "settingsTab",
        "refreshCandidates",
        "trainRefresh",
        "load",
        "prevPage",
        "nextPage",
    ):
        assert f'<button id="{button_id}" type="button"' in html
    assert '<button type="button" class="${active}" data-label="${escapeHtml(label.key)}">' in script
    assert 'buttons.push(\'<button type="button" data-label="">Clear</button>\');' in script


def test_web_app_serves_favicon(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    response = client.get("/favicon.svg")

    assert '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />' in html
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text


def test_web_app_html_contains_candidates_tab(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="libraryTab"' in html
    assert 'id="candidatesTab"' in html
    assert 'id="candidateMinBroken"' in html
    assert '<option value="positive_highest" selected>highest positive probability</option>' in html
    assert '<option value="negative_highest">highest negative probability</option>' in html
    assert '<option value="balanced">uncertain / balanced</option>' in html
    assert 'fetch(`/api/profiles/${activeProfile.classifier_key}/predictions?' in script
    assert "positive_probability" in script
    assert 'SONARA ${mark(track.feature_status.sonara)} · MERT ${mark(track.feature_status.mert)} · MAEST ${mark(track.feature_status.maest)}' in script
    assert '<div class="genres-line"><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in script


def test_web_app_filter_controls_combine_without_losing_tab_state(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text

    assert 'id="commonFilters"' in html
    assert 'id="candidateFilters"' in html
    assert 'syncopatedEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'labelEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'candidatePredictedEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'candidateMinBrokenEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert ".filters[hidden]," in styles
    assert 'candidateFiltersEl.hidden = view !== "candidates";' in script
    assert 'id="refreshCandidates"' in html
    assert 'id="trainRefresh"' in html
    assert '<button id="trainRefresh" type="button" class="icon-button train-refresh"' in html
    assert 'fetch(`/api/profiles/${activeProfile.classifier_key}/predictions/refresh`, { method: "POST" })' in script
    assert 'fetch(`/api/profiles/${activeProfile.classifier_key}/training/readiness`)' in script
    assert 'fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, { method: "POST" })' in script
    assert 'refreshCandidatesEl.disabled = true;' in script
    assert 'trainRefreshEl.disabled = true;' in script
    assert "async function parseRefreshResponse(response)" in script
    assert "async function loadTrainingReadiness()" in script
    assert ".refresh-candidates" in styles
    assert ".train-refresh" in styles
    assert "const viewOffsets = { library: 0, candidates: 0, training: 0, settings: 0 };" in script
    assert "let loadSequence = 0;" in script
    assert "const sequence = ++loadSequence;" in script
    assert 'if (sequence !== loadSequence || activeView !== "library") return;' in script
    assert 'if (sequence !== loadSequence || activeView !== "candidates") return;' in script
    assert "viewOffsets[activeView] = offset;" in script
    assert "offset = viewOffsets[view] || 0;" in script
    assert "q: queryEl.value," in script
    assert "syncopated: syncopatedEl.value," in script
    assert "label: labelEl.value," in script
    assert "predicted: candidatePredictedEl.value," in script
    assert "probability_focus: candidateMinBrokenEl.value," in script


def test_web_app_refresh_and_train_controls_are_icon_buttons(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert '<button id="refreshCandidates" type="button" class="icon-button refresh-candidates"' in html
    assert 'aria-label="Refresh candidates"' in html
    assert 'class="lucide lucide-refresh-cw"' in html
    assert ">Refresh candidates</button>" not in html
    assert '<button id="trainRefresh" type="button" class="icon-button train-refresh"' in html
    assert 'aria-label="Train and refresh candidates"' in html
    assert 'class="lucide lucide-brain"' in html
    assert ">Train + refresh</button>" not in html
    assert ".icon-button {\n  width: 38px;\n  height: 38px;" in styles
    assert ".icon-button svg {\n  width: 18px;\n  height: 18px;" in styles


def test_web_app_header_profile_controls_align_with_source_controls(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    profile_controls = html.split('<div class="profile-controls">', 1)[1].split("</div>", 1)[0]
    tabs = html.split('<nav class="tabs">', 1)[1].split("</nav>", 1)[0]
    assert profile_controls.index('id="settingsTab"') < profile_controls.index('id="archiveProfile"')
    assert 'id="settingsTab"' not in tabs
    assert "--header-grid-columns: minmax(360px, 1fr) var(--header-action-width) var(--header-wide-action-width) minmax(170px, auto);" in styles
    assert ".top-bar,\n.source-row {\n  display: grid;" in styles
    assert ".profile-controls {\n  display: contents;" in styles
    assert "#profileSelect {\n  grid-column: 1;\n  justify-self: end;" in styles
    assert "#newProfile,\n#chooseSource {\n  grid-column: 2;" in styles
    assert "#settingsTab,\n#loadSource {\n  grid-column: 3;" in styles
    assert "#archiveProfile {\n  grid-column: 4;" in styles


def test_web_app_header_badge_aligns_with_title_text(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    styles = (
        TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
        .get("/static/styles.css")
        .text.replace("\r\n", "\n")
    )

    assert ".top-bar > div:first-child {\n  grid-column: 1;\n  grid-row: 1;\n  display: flex;\n  align-items: center;" in styles
    assert ".classifier-profile {\n  display: inline-flex;\n  align-items: center;" in styles


def test_web_app_html_colors_manual_labels_by_label_value(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text

    assert ".profile-label-badge" in styles
    assert "label-${escapeHtml(track.label)}" in script
    assert "button.classList.add(button.dataset.label)" not in script
    assert "button.active.broken" not in styles
    assert "button.active.straight" not in styles
    assert "button.active.ambiguous" not in styles


def test_web_app_multiclass_label_buttons_use_right_aligned_grid(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert 'class="actions ${isMulticlassProfile() ? "multiclass-actions" : ""}"' in script
    assert ".multiclass-actions {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(132px, 1fr));" in styles
    assert "justify-content: end;" in styles
    assert "width: min(340px, 100%);" in styles
    assert "@media (max-width: 760px)" in styles
    assert "@media (max-width: 420px)" in styles
    assert ".multiclass-actions {\n    grid-template-columns: 1fr;" in styles


def test_web_app_summary_uses_compact_badges(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert ".summary-strip {\n  display: flex;" in styles
    assert ".summary-group {\n  display: inline-flex;" in styles
    assert ".summary-badge {\n  display: inline-flex;" in styles
    assert ".summary-labels {\n  max-width: 100%;" in styles
    assert ".coverage-sonara" in styles


def test_web_app_track_title_does_not_add_separator_without_artist(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    script = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/static/app.js").text

    assert "function displayTrackTitle(track)" in script
    assert "${escapeHtml(displayTrackTitle(track))}" in script
    assert "${escapeHtml(track.artist || \"\")} - ${escapeHtml(track.title || track.path)}" not in script


def test_web_app_places_rhythm_badges_on_genres_line(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    script = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/static/app.js").text

    assert '<div class="genres-line"><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in script
    assert '${badgeRow(track)}\n          <audio controls' not in script


def test_web_app_stops_previous_audio_preview_when_another_starts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    script = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/static/app.js").text

    assert "let activeAudio = null;" in script
    assert "wireAudioPreview(row.querySelector(\"audio\"));" in script
    assert "function wireAudioPreview(audio)" in script
    assert "activeAudio.pause();" in script
    assert "activeAudio.currentTime = 0;" in script


def test_web_app_serves_aiff_preview_as_seekable_browser_audio(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import rhythm_lab.web_app as web_app

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "preview.aiff", title="Preview")
    labels_path = tmp_path / "labels.sqlite"
    calls = []

    def fail_streaming_process(*args, **kwargs):
        raise AssertionError("AIFF preview should not use streaming ffmpeg stdout")

    def fake_run(command, *, stderr, check):
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(web_app, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(web_app.subprocess, "Popen", fail_streaming_process)
    monkeypatch.setattr(web_app.subprocess, "run", fake_run)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    response = client.get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-length"] == str(len(b"RIFFbrowser-compatible-wav"))
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert calls
    assert calls[0][-2:] == ["-y", calls[0][-1]]


def test_web_app_audio_preview_is_compact(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    styles = (
        TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
        .get("/static/styles.css")
        .text.replace("\r\n", "\n")
    )

    assert "audio {\n  width: min(520px, 100%);\n  height: 34px;\n  margin-top: 6px;" in styles


def test_web_app_shell_has_inner_gutters(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    styles = (
        TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
        .get("/static/styles.css")
        .text.replace("\r\n", "\n")
    )

    assert "--page-gutter: clamp(10px, 2.4vw, 34px);" in styles
    assert "--panel-pad-x: clamp(12px, 1.6vw, 22px);" in styles
    assert "width: min(1440px, calc(100% - (var(--page-gutter) * 2)));" in styles
    assert "padding: 16px var(--panel-pad-x) 14px;" in styles
    assert "padding: 16px var(--panel-pad-x) 40px;" in styles


def test_web_app_track_rows_have_more_vertical_spacing(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")
    script = client.get("/static/app.js").text

    assert ".track-main {\n  display: flex;\n  flex-direction: column;\n  gap: 4px;" in styles
    assert ".rhythm-media-block {\n  margin-top: 8px;" in styles
    assert '<div class="rhythm-media-block">' in script


def test_feature_matrix_uses_source_database_features_and_external_labels(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken = _track(source, tmp_path, "broken.wav", title="Broken")
    straight = _track(source, tmp_path, "straight.wav", title="Straight")
    for index, track_id in enumerate([broken, straight]):
        source.save_sonara_features(
            track_id,
            {
                "onset_density": {"type": "float", "value": float(index + 1)},
                "mfcc_mean": {"type": "list", "value": [float(index)] * 13},
                "chroma_mean": {"type": "list", "value": [float(index)] * 12},
            },
            model_name="sonara-test",
        )
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.set_label(source.get_track(broken), "broken")
    labels.set_label(source.get_track(straight), "straight")

    features = build_labeled_feature_matrix(source_path, labels.path, "sonara")

    assert features.track_ids == [broken, straight]
    assert features.labels == ["broken", "straight"]
    assert features.matrix.shape[0] == 2


def test_apply_model_to_lab_saves_predictions_and_exports_csv(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    tracks = [_track(source, tmp_path, f"track-{index}.wav", title=f"Track {index}") for index in range(6)]
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    for index, track_id in enumerate(tracks):
        source.save_sonara_features(
            track_id,
            {
                "onset_density": {"type": "float", "value": float(index)},
                "mfcc_mean": {"type": "list", "value": [float(index)] * 13},
                "chroma_mean": {"type": "list", "value": [float(index)] * 12},
            },
            model_name="sonara-test",
        )
        labels.set_label(source.get_track(track_id), "broken" if index < 3 else "straight")

    features = build_labeled_feature_matrix(source.path, labels.path, "sonara")
    trained = train_feature_set(
        features.matrix,
        features.labels,
        feature_names=features.feature_names,
        feature_set="sonara",
        artifact_dir=tmp_path / "artifacts",
    )

    summary = apply_model_to_lab(source.path, labels.path, trained.artifact_path)
    csv_path = export_predictions_csv(labels.path, tmp_path / "predictions.csv")

    assert summary["predicted"] == 6
    assert len(labels.predictions()) == 6
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("source_track_id,")


def test_custom_profile_training_and_prediction_use_profile_labels(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    tracks = [_track(source, tmp_path, f"vocal-{index}.wav", title=f"Vocal {index}") for index in range(8)]
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    scoped = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")
    for index, track_id in enumerate(tracks):
        source.save_sonara_features(
            track_id,
            {
                "onset_density": {"type": "float", "value": float(index)},
                "mfcc_mean": {"type": "list", "value": [float(index)] * 13},
                "chroma_mean": {"type": "list", "value": [float(index)] * 12},
            },
            model_name="sonara-test",
        )
        scoped.set_label(source.get_track(track_id), "vocal" if index < 4 else "instrumental")

    features = build_labeled_feature_matrix(source.path, labels.path, "sonara", classifier_key="vocal_presence")
    trained = train_feature_set(
        features.matrix,
        features.labels,
        feature_names=features.feature_names,
        feature_set="sonara",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        label_order=["vocal", "instrumental"],
        positive_label="vocal",
        artifact_prefix="vocal-presence",
        classifier_key="vocal_presence",
    )
    summary = apply_model_to_lab(source.path, labels.path, trained.artifact_path, classifier_key="vocal_presence")

    payload = joblib.load(trained.artifact_path)
    predictions = scoped.predictions()
    assert payload["classifier_key"] == "vocal_presence"
    assert payload["label_order"] == ["vocal", "instrumental"]
    assert trained.artifact_path.name.startswith("vocal-presence-sonara-")
    assert summary["predicted"] == 8
    assert len(predictions) == 8
    assert {row["label"] for row in predictions} <= {"vocal", "instrumental"}
    assert all(set(row["probabilities"]) == {"vocal", "instrumental"} for row in predictions)


def test_train_feature_set_writes_broken_discovery_metrics(tmp_path: Path) -> None:
    matrix = np.asarray(
        [[float(index), 0.0] for index in range(8)]
        + [[float(index + 20), 1.0] for index in range(8)],
        dtype=np.float32,
    )
    labels = ["broken"] * 8 + ["straight"] * 8

    result = train_feature_set(
        matrix,
        labels,
        feature_names=["axis", "marker"],
        feature_set="test",
        artifact_dir=tmp_path / "artifacts",
    )

    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    discovery = metrics["broken_discovery"]
    thresholds = discovery["thresholds"]
    top_n = discovery["top_n"]
    cross_validation = metrics["cross_validation"]

    assert discovery["positive_label"] == "broken"
    assert {row["threshold"] for row in thresholds} >= {0.25, 0.5}
    assert all("broken_recall" in row for row in thresholds)
    assert all("candidate_count" in row for row in thresholds)
    assert top_n[0]["n"] == 1
    assert "broken_recall_mean" in cross_validation
    assert cross_validation["fold_count"] >= 2


def test_export_predictions_csv_orders_by_broken_probability(tmp_path: Path) -> None:
    source = LibraryDatabase(tmp_path / "source.sqlite")
    lower_id = _track(source, tmp_path, "lower.wav", title="Lower")
    higher_id = _track(source, tmp_path, "higher.wav", title="Higher")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.save_prediction(
        source.get_track(lower_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="straight",
        confidence=0.8,
        probabilities={"broken": 0.2, "straight": 0.8},
    )
    labels.save_prediction(
        source.get_track(higher_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="broken",
        confidence=0.7,
        probabilities={"broken": 0.7, "straight": 0.3},
    )

    csv_path = export_predictions_csv(labels.path, tmp_path / "predictions.csv")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_track_id"] == str(higher_id)
    assert rows[0]["broken_probability"] == "0.7"
    assert rows[0]["straight_probability"] == "0.3"


def test_export_predictions_csv_uses_latest_prediction_per_track(tmp_path: Path) -> None:
    source = LibraryDatabase(tmp_path / "source.sqlite")
    track_id = _track(source, tmp_path, "track.wav", title="Track")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    track = source.get_track(track_id)
    labels.save_prediction(
        track,
        feature_set="combined",
        model_artifact="old.joblib",
        label="broken",
        confidence=0.9,
        probabilities={"broken": 0.9, "straight": 0.1},
    )
    labels.save_prediction(
        track,
        feature_set="combined",
        model_artifact="new.joblib",
        label="straight",
        confidence=0.8,
        probabilities={"broken": 0.2, "straight": 0.8},
    )

    csv_path = export_predictions_csv(labels.path, tmp_path / "predictions.csv")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["model_artifact"] == "new.joblib"
    assert rows[0]["broken_probability"] == "0.2"


def test_lab_database_prunes_old_predictions_for_feature_set_only(tmp_path: Path) -> None:
    source = LibraryDatabase(tmp_path / "source.sqlite")
    track_id = _track(source, tmp_path, "track.wav", title="Track")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    track = source.get_track(track_id)
    labels.save_prediction(
        track,
        feature_set="combined",
        model_artifact="old-combined.joblib",
        label="broken",
        confidence=0.9,
        probabilities={"broken": 0.9, "straight": 0.1},
    )
    labels.save_prediction(
        track,
        feature_set="combined",
        model_artifact="new-combined.joblib",
        label="straight",
        confidence=0.8,
        probabilities={"broken": 0.2, "straight": 0.8},
    )
    labels.save_prediction(
        track,
        feature_set="maest",
        model_artifact="old-maest.joblib",
        label="broken",
        confidence=0.7,
        probabilities={"broken": 0.7, "straight": 0.3},
    )

    deleted = labels.prune_predictions(feature_set="combined", keep_model_artifact="new-combined.joblib")

    predictions = labels.predictions()
    assert deleted == 1
    assert {(row["feature_set"], row["model_artifact"]) for row in predictions} == {
        ("combined", "new-combined.joblib"),
        ("maest", "old-maest.joblib"),
    }


def test_lab_database_records_training_checkpoint_counts(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")

    assert labels.training_checkpoint()["counts"] == {"broken": 0, "straight": 0}

    labels.record_training_checkpoint({"broken": 100, "straight": 120}, model_artifact="model.joblib")

    checkpoint = labels.training_checkpoint()
    assert checkpoint["counts"] == {"broken": 100, "straight": 120}
    assert checkpoint["model_artifact"] == "model.joblib"


def test_cli_train_accepts_separate_source_and_labels_databases(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    for index in range(6):
        track_id = _track(source, tmp_path, f"track-{index}.wav", title=f"Track {index}")
        source.save_sonara_features(
            track_id,
            {
                "onset_density": {"type": "float", "value": float(index)},
                "mfcc_mean": {"type": "list", "value": [float(index)] * 13},
                "chroma_mean": {"type": "list", "value": [float(index)] * 12},
            },
            model_name="sonara-test",
        )
        labels.set_label(source.get_track(track_id), "broken" if index < 3 else "straight")

    result = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "train",
            "--source",
            str(source_path),
            "--labels",
            str(labels.path),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["sonara"]["status"] == "trained"
    assert payload["mert"]["status"] == "skipped"


def _track(db: LibraryDatabase, tmp_path: Path, name: str, *, title: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": title})

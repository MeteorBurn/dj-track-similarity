from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path
import csv
import wave
import joblib

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LAB_ROOT = ROOT / "tools" / "rhythm-lab"
sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.database import LibraryDatabase

from rhythm_lab.features import build_labeled_feature_matrix
from rhythm_lab.cli import PromotionError, promote_profile_model
from rhythm_lab.lab_db import RhythmLabDatabase
from rhythm_lab.predictions import _predict_probabilities, apply_model_to_lab, export_predictions_csv
from rhythm_lab.source_db import SourceDatabase
from rhythm_lab.training import train_feature_set
from rhythm_lab.web_app import create_app, install_rhythm_lab_asyncio_exception_logging


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
    assert profile.training_min_added == 50
    with labels.connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='classifier_track_likes'"
        ).fetchone() is None


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


def test_profile_names_are_unique_case_insensitive_for_create_and_update(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )

    try:
        labels.create_profile(
            classifier_key="duplicate_vocal",
            name="vocal presence",
            description="Duplicate display name.",
            artifact_dir=tmp_path / "artifacts" / "duplicate-vocal",
            labels=[
                {"key": "yes", "name": "Yes", "role": "positive"},
                {"key": "no", "name": "No", "role": "negative"},
            ],
        )
    except ValueError as error:
        assert "profile name already exists" in str(error).lower()
    else:  # pragma: no cover - defensive guard.
        raise AssertionError("duplicate profile name was accepted")

    try:
        labels.update_profile("break_energy", name="VOCAL PRESENCE")
    except ValueError as error:
        assert "profile name already exists" in str(error).lower()
    else:  # pragma: no cover - defensive guard.
        raise AssertionError("duplicate profile name update was accepted")


def test_delete_profile_by_name_or_key_removes_profile_scoped_data(tmp_path: Path) -> None:
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
    scoped.upsert_label_queue_items(
        mode="uncertainty",
        items=[
            {
                "source_track_id": track_id,
                "score": 0.48,
                "priority": 10.0,
                "reason": {"reason": "near decision boundary"},
            }
        ],
    )
    scoped.record_training_checkpoint({"vocal": 1, "instrumental": 0}, model_artifact="model.joblib")

    deleted = labels.delete_profile(name="Vocal Presence")

    assert deleted.classifier_key == "vocal_presence"
    try:
        labels.get_profile("vocal_presence")
    except KeyError:
        pass
    else:  # pragma: no cover - defensive guard.
        raise AssertionError("deleted profile still exists")
    with labels.connect() as connection:
        for table in (
            "classifier_profile_labels",
            "classifier_labels",
            "classifier_label_queue",
            "classifier_predictions",
            "classifier_training_checkpoints",
        ):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE classifier_key = 'vocal_presence'"
            ).fetchone()[0]
            assert count == 0, table

    labels.create_profile(
        classifier_key="texture",
        name="Texture",
        description="Texture test.",
        artifact_dir=tmp_path / "artifacts" / "texture",
        labels=[
            {"key": "rough", "name": "Rough", "role": "positive"},
            {"key": "smooth", "name": "Smooth", "role": "negative"},
        ],
    )

    assert labels.delete_profile(classifier_key="texture").name == "Texture"


def test_label_queue_upserts_state_transitions_and_profile_isolation(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    break_queue = RhythmLabDatabase(labels.path, classifier_key="break_energy")
    vocal_queue = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")

    break_queue.upsert_label_queue_items(
        mode="uncertainty",
        items=[
            {"source_track_id": 101, "score": 0.49, "priority": 4.0, "reason": {"rank": 1}},
            {"source_track_id": 102, "score": 0.52, "priority": 3.0, "reason": {"rank": 2}},
        ],
    )
    break_queue.mark_queue_item(101, mode="uncertainty", state="skipped")
    break_queue.upsert_label_queue_items(
        mode="uncertainty",
        items=[
            {"source_track_id": 101, "score": 0.51, "priority": 9.0, "reason": {"rank": 1, "updated": True}},
        ],
    )
    vocal_queue.upsert_label_queue_items(
        mode="uncertainty",
        items=[
            {"source_track_id": 101, "score": 0.2, "priority": 5.0, "reason": {"profile": "vocal"}},
        ],
    )

    break_items = break_queue.label_queue_items()
    vocal_items = vocal_queue.label_queue_items()
    skipped = break_queue.label_queue_items(state="skipped")

    assert len(break_items) == 2
    assert len(vocal_items) == 1
    assert skipped[0]["source_track_id"] == 101
    assert skipped[0]["state"] == "skipped"
    assert skipped[0]["score"] == 0.51
    assert skipped[0]["priority"] == 9.0
    assert skipped[0]["reason"]["updated"] is True

    cleared = break_queue.clear_label_queue(state="skipped")

    assert cleared == 1
    assert [item["source_track_id"] for item in break_queue.label_queue_items()] == [102]
    assert [item["source_track_id"] for item in vocal_queue.label_queue_items()] == [101]


def test_archive_profile_marks_only_that_profile_queue_archived(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    break_queue = RhythmLabDatabase(labels.path, classifier_key="break_energy")
    vocal_queue = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")
    break_queue.upsert_label_queue_items(mode="uncertainty", items=[{"source_track_id": 1, "priority": 1, "reason": {}}])
    vocal_queue.upsert_label_queue_items(mode="uncertainty", items=[{"source_track_id": 2, "priority": 1, "reason": {}}])

    labels.archive_profile("vocal_presence")

    assert break_queue.label_queue_items()[0]["state"] == "suggested"
    assert vocal_queue.label_queue_items()[0]["state"] == "archived"


def test_profile_training_min_added_can_be_created_and_updated(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    profile = labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        training_min_added=12,
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )

    updated = labels.update_profile("vocal_presence", training_min_added=8)

    assert profile.training_min_added == 12
    assert updated.training_min_added == 8
    assert labels.get_profile("vocal_presence").training_min_added == 8


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
            "training_min_added": 9,
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
    assert payload["training_min_added"] == 9
    assert payload["positive_label"] == "euphoric"
    assert payload["negative_label"] == "dark"
    assert [label["role"] for label in payload["labels"]] == ["class", "class", "class"]
    assert payload["labels"][0]["description"] == "Uplifting peak-time mood."

    patched = client.patch("/api/profiles/mood", json={"training_min_added": 6}).json()
    assert patched["training_min_added"] == 6


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
    tracks = client.get("/api/profiles/break_energy/tracks").json()
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

    response = client.post(f"/api/profiles/break_energy/tracks/{broken_id}/label", json={"label": "broken"})

    assert response.status_code == 200
    assert response.json()["label"] == "broken"
    assert RhythmLabDatabase(labels_path).label_for_track(broken_id).label == "broken"
    with source.connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='classifier_labels'"
        ).fetchone() is None


def test_web_app_bpm_range_filters_use_only_sonara_bpm_when_bounds_are_set(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)

    tagged_path = tmp_path / "tagged.wav"
    tagged_path.write_bytes(b"RIFF0000WAVE")
    tagged_id = source.upsert_track(
        path=tagged_path,
        size=tagged_path.stat().st_size,
        mtime=1,
        metadata={"title": "Tagged", "bpm": 118},
        bpm=150,
    )
    source.save_sonara_features(
        tagged_id,
        {"bpm": {"type": "float", "value": 150.0}},
        model_name="sonara-test",
    )

    fallback_path = tmp_path / "fallback.wav"
    fallback_path.write_bytes(b"RIFF0000WAVE")
    fallback_id = source.upsert_track(
        path=fallback_path,
        size=fallback_path.stat().st_size,
        mtime=1,
        metadata={"title": "Fallback"},
        bpm=140,
    )
    source.save_sonara_features(
        fallback_id,
        {"bpm": {"type": "float", "value": 126.0}},
        model_name="sonara-test",
    )

    outside_path = tmp_path / "outside.wav"
    outside_path.write_bytes(b"RIFF0000WAVE")
    outside_id = source.upsert_track(
        path=outside_path,
        size=outside_path.stat().st_size,
        mtime=1,
        metadata={"title": "Outside"},
        bpm=132,
    )
    source.save_sonara_features(
        outside_id,
        {"bpm": {"type": "float", "value": 132.0}},
        model_name="sonara-test",
    )

    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    for track_id, probability in ((tagged_id, 0.9), (fallback_id, 0.8), (outside_id, 0.7)):
        labels.save_prediction(
            source.get_track(track_id),
            feature_set="combined",
            model_artifact="model.joblib",
            label="broken",
            confidence=probability,
            probabilities={"broken": probability, "straight": 1.0 - probability},
        )
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    unfiltered = client.get(
        "/api/profiles/break_energy/tracks",
        params={"bpm_min": "", "bpm_max": ""},
    ).json()
    minimum_only = client.get(
        "/api/profiles/break_energy/tracks",
        params={"bpm_min": "130"},
    ).json()
    maximum_only = client.get(
        "/api/profiles/break_energy/tracks",
        params={"bpm_max": "127"},
    ).json()
    range_tracks = client.get(
        "/api/profiles/break_energy/tracks",
        params={"bpm_min": "125", "bpm_max": "127"},
    ).json()
    fallback_candidates = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "bpm_min": "125", "bpm_max": "127"},
    ).json()

    assert unfiltered["total"] == 3
    assert minimum_only["total"] == 2
    assert [item["id"] for item in minimum_only["items"]] == [outside_id, tagged_id]
    assert maximum_only["total"] == 1
    assert maximum_only["items"][0]["id"] == fallback_id
    assert range_tracks["total"] == 1
    assert range_tracks["items"][0]["id"] == fallback_id
    assert range_tracks["items"][0]["bpm"] == 126.0
    assert fallback_candidates["total"] == 1
    assert fallback_candidates["items"][0]["id"] == fallback_id
    assert fallback_candidates["items"][0]["bpm"] == 126.0


def test_web_app_profile_likes_share_main_library_state(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    track_id = _track(source, tmp_path, "track.wav", title="Track")
    other_id = _track(source, tmp_path, "other.wav", title="Other")
    source.set_track_liked(other_id, True)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect vocal parts.",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    like_response = client.post(f"/api/tracks/{track_id}/liked", json={"liked": True})
    tracks = client.get("/api/profiles/break_energy/tracks").json()
    liked_tracks = client.get("/api/profiles/break_energy/tracks", params={"liked": "yes"}).json()
    unlike_response = client.post(f"/api/tracks/{other_id}/liked", json={"liked": False})
    liked_after_unlike = client.get("/api/profiles/break_energy/tracks", params={"liked": "yes"}).json()
    summary = client.get("/api/profiles/break_energy/summary").json()

    assert like_response.status_code == 200
    assert like_response.json() == {"track_id": track_id, "liked": True}
    assert unlike_response.status_code == 200
    assert unlike_response.json() == {"track_id": other_id, "liked": False}
    assert source.get_track(track_id).liked is True
    assert source.get_track(other_id).liked is False
    assert tracks["total"] == 2
    assert {item["id"] for item in tracks["items"]} == {track_id, other_id}
    assert next(item for item in tracks["items"] if item["id"] == track_id)["liked"] is True
    assert next(item for item in tracks["items"] if item["id"] == other_id)["liked"] is True
    assert liked_tracks["total"] == 2
    assert {item["id"] for item in liked_tracks["items"]} == {track_id, other_id}
    assert liked_after_unlike["total"] == 1
    assert liked_after_unlike["items"][0]["id"] == track_id
    assert summary["liked"] == 1
    with labels.connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='classifier_track_likes'"
        ).fetchone() is None


def test_web_app_predictions_endpoint_filters_candidates_by_probability_focus(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    low_id = _track(source, tmp_path, "low.wav", title="Low")
    high_id = _track(source, tmp_path, "high.wav", title="High")
    balanced_id = _track(source, tmp_path, "balanced.wav", title="Balanced")
    source.set_track_liked(high_id, True)
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
    import rhythm_lab.lab_db as lab_db
    import rhythm_lab.source_db as source_db

    def fail_predictions_scan(self):
        raise AssertionError("predictions endpoint must not full-scan classifier predictions")

    def fail_single_track_load(self, track_id: int):
        raise AssertionError("predictions endpoint must not fetch source tracks one at a time")

    monkeypatch.setattr(lab_db.RhythmLabDatabase, "predictions", fail_predictions_scan)
    monkeypatch.setattr(source_db.SourceDatabase, "get_track", fail_single_track_load)
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    all_candidates = client.get("/api/profiles/break_energy/predictions", params={"label": "all"}).json()
    unlabeled = client.get("/api/profiles/break_energy/predictions", params={"label": "unlabeled"}).json()
    filtered = client.get("/api/profiles/break_energy/predictions", params={"label": "all", "min_positive": 0.5}).json()
    comma_decimal_filtered = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "min_positive": "0,5"},
    )
    predicted_broken = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "predicted": "broken"},
    ).json()
    predicted_straight = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "predicted": "straight"},
    ).json()
    straight_focus = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "probability_focus": "negative_highest"},
    ).json()
    balanced_focus = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "probability_focus": "balanced"},
    ).json()
    by_filename = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "q": "low.wav"},
    ).json()
    by_full_path = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "all", "q": str(source.get_track(low_id).path)},
    ).json()
    combined = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "broken", "min_positive": 0.5, "q": "high", "syncopated": "yes"},
    ).json()
    mismatched = client.get(
        "/api/profiles/break_energy/predictions",
        params={"label": "broken", "min_positive": 0.5, "q": "low", "syncopated": "yes"},
    ).json()

    assert all_candidates["total"] == 3
    assert [item["id"] for item in all_candidates["items"]] == [high_id, balanced_id, low_id]
    assert all_candidates["items"][0]["positive_probability"] == 0.7
    assert all_candidates["items"][0]["label"] == "broken"
    assert all_candidates["items"][0]["liked"] is True
    assert all_candidates["items"][0]["genres"] == ["Breakbeat"]
    assert all_candidates["items"][0]["maest_syncopated_rhythm"] is True
    assert all_candidates["items"][0]["feature_status"] == {"sonara": True, "mert": True, "maest": True}
    assert unlabeled["total"] == 2
    assert unlabeled["items"][0]["id"] == balanced_id
    assert filtered["total"] == 2
    assert [item["id"] for item in filtered["items"]] == [high_id, balanced_id]
    assert comma_decimal_filtered.status_code == 200
    assert comma_decimal_filtered.json()["total"] == 2
    assert [item["id"] for item in comma_decimal_filtered.json()["items"]] == [high_id, balanced_id]
    assert predicted_broken["total"] == 2
    assert [item["id"] for item in predicted_broken["items"]] == [high_id, balanced_id]
    assert predicted_straight["total"] == 1
    assert predicted_straight["items"][0]["id"] == low_id
    assert [item["id"] for item in straight_focus["items"]] == [low_id, balanced_id, high_id]
    assert [item["id"] for item in balanced_focus["items"]] == [balanced_id, high_id, low_id]
    assert by_filename["total"] == 1
    assert by_filename["items"][0]["id"] == low_id
    assert by_full_path["total"] == 1
    assert by_full_path["items"][0]["id"] == low_id
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
    RhythmLabDatabase(labels_path).update_profile("break_energy", artifact_dir=artifacts)
    import rhythm_lab.web_app as web_app

    calls = []

    def fake_apply_model_to_lab(source_db_path: Path, labels_db_path: Path, artifact_path: Path, *, classifier_key: str):
        calls.append((source_db_path, labels_db_path, artifact_path, classifier_key))
        labels = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
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

    monkeypatch.setattr(web_app, "apply_model_to_lab", fake_apply_model_to_lab)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    response = client.post("/api/profiles/break_energy/predictions/refresh")

    assert response.status_code == 200
    assert response.json()["artifact"] == str(newer)
    assert response.json()["predicted"] == 1
    assert response.json()["skipped"] == 2
    assert calls == [(source_path.resolve(), labels_path.resolve(), newer, "break_energy")]
    predictions = RhythmLabDatabase(labels_path).predictions()
    assert len(predictions) == 1
    assert predictions[0]["model_artifact"] == str(newer)


def test_predict_probabilities_preserves_high_confidence_precision() -> None:
    class AlmostCertainModel:
        classes_ = np.asarray(["broken", "straight"])

        def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
            return np.asarray([[0.99999999, 0.00000001]], dtype=np.float64)

    probabilities = _predict_probabilities(AlmostCertainModel(), np.zeros((1, 2)), ["broken", "straight"])

    assert probabilities == [{"broken": 0.99999999, "straight": 0.00000001}]


def test_web_app_train_refresh_requires_50_new_broken_and_straight_labels(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    for index in range(50):
        labels.set_label(10_000 + index, "broken")
        labels.set_label(20_000 + index, "straight")
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    labels.update_profile("break_energy", artifact_dir=artifacts)
    artifact = artifacts / "break-energy-combined-20260524T130000Z.joblib"
    import rhythm_lab.web_app as web_app

    calls = []

    def fake_benchmark_lab_database(source_db_path: Path, labels_db_path: Path, artifact_dir: Path, *, classifier_key: str):
        calls.append(("train", source_db_path, labels_db_path, artifact_dir, classifier_key))
        artifact.write_bytes(b"combined")
        return {"combined": {"status": "trained", "artifact_path": str(artifact)}}

    def fake_apply_model_to_lab(source_db_path: Path, labels_db_path: Path, artifact_path: Path, *, classifier_key: str):
        calls.append(("predict", source_db_path, labels_db_path, artifact_path, classifier_key))
        return {"feature_set": "combined", "predicted": 0, "skipped": 0}

    monkeypatch.setattr(web_app, "benchmark_lab_database", fake_benchmark_lab_database)
    monkeypatch.setattr(web_app, "apply_model_to_lab", fake_apply_model_to_lab)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    ready = client.get("/api/profiles/break_energy/training/readiness").json()
    trained = client.post("/api/profiles/break_energy/training/train-refresh")
    blocked = client.post("/api/profiles/break_energy/training/train-refresh")

    assert ready["ready"] is True
    assert ready["added"] == {"broken": 50, "straight": 50}
    assert trained.status_code == 200
    assert trained.json()["training_counts"] == {"broken": 50, "straight": 50}
    assert trained.json()["artifact"] == str(artifact)
    assert trained.json()["artifact_cleanup"] == {"deleted_joblib": 0, "deleted_metrics": 0}
    assert calls == [
        ("train", source_path.resolve(), labels_path.resolve(), artifacts, "break_energy"),
        ("predict", source_path.resolve(), labels_path.resolve(), artifact, "break_energy"),
    ]
    assert RhythmLabDatabase(labels_path).training_checkpoint()["counts"] == {"broken": 50, "straight": 50}
    assert blocked.status_code == 400
    assert "Need 50 new broken and 50 new straight labels" in blocked.json()["detail"]


def test_profile_training_readiness_uses_profile_training_min_added(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        training_min_added=3,
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    scoped = RhythmLabDatabase(labels_path, classifier_key="vocal_presence")
    for index in range(3):
        scoped.set_label(10_000 + index, "vocal")
        scoped.set_label(20_000 + index, "instrumental")
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    ready = client.get("/api/profiles/vocal_presence/training/readiness").json()
    patched = client.patch("/api/profiles/vocal_presence", json={"training_min_added": 4}).json()
    not_ready = client.get("/api/profiles/vocal_presence/training/readiness").json()

    assert ready["ready"] is True
    assert ready["required_added"] == {"vocal": 3, "instrumental": 3}
    assert patched["training_min_added"] == 4
    assert not_ready["ready"] is False
    assert not_ready["required_added"] == {"vocal": 4, "instrumental": 4}
    assert not_ready["added"] == {"vocal": 3, "instrumental": 3}


def test_profile_training_readiness_reports_artifacts_metrics_and_history(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    for index in range(8):
        labels.set_label(10_000 + index, "broken")
        labels.set_label(20_000 + index, "straight")
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    old_model = artifacts / "break-energy-combined-20260524T120000Z.joblib"
    latest_model = artifacts / "break-energy-combined-20260524T130000Z.joblib"
    sonara_model = artifacts / "break-energy-sonara-20260524T125000Z.joblib"
    old_metrics = artifacts / "break-energy-combined-20260524T120000Z.metrics.json"
    latest_metrics = artifacts / "break-energy-combined-20260524T130000Z.metrics.json"
    sonara_metrics = artifacts / "break-energy-sonara-20260524T125000Z.metrics.json"
    old_model.write_bytes(b"old")
    latest_model.write_bytes(b"latest")
    sonara_model.write_bytes(b"sonara")
    old_metrics.write_text(
        json.dumps(
            {
                "feature_set": "combined",
                "created_at": "20260524T120000Z",
                "trained_rows": 12,
                "test_rows": 4,
                "feature_count": 24,
                "cross_validation": {
                    "accuracy_mean": 0.61,
                    "macro_f1_mean": 0.62,
                    "positive_precision_mean": 0.63,
                    "positive_recall_mean": 0.64,
                },
            }
        ),
        encoding="utf-8",
    )
    latest_metrics.write_text(
        json.dumps(
            {
                "feature_set": "combined",
                "created_at": "20260524T130000Z",
                "trained_rows": 16,
                "test_rows": 4,
                "feature_count": 42,
                "cross_validation": {
                    "accuracy_mean": 0.71,
                    "macro_f1_mean": 0.72,
                    "positive_precision_mean": 0.73,
                    "positive_recall_mean": 0.74,
                },
            }
        ),
        encoding="utf-8",
    )
    sonara_metrics.write_text(
        json.dumps(
            {
                "feature_set": "sonara",
                "created_at": "20260524T125000Z",
                "trained_rows": 15,
                "feature_count": 12,
                "cross_validation": {"accuracy_mean": 0.51, "macro_f1_mean": 0.52},
            }
        ),
        encoding="utf-8",
    )
    labels.update_profile("break_energy", artifact_dir=artifacts)
    labels.record_training_checkpoint({"broken": 6, "straight": 5}, model_artifact=latest_model)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    payload = client.get("/api/profiles/break_energy/training/readiness").json()

    assert payload["last_trained_at"]
    assert payload["artifact_summary"]["artifact_dir"] == str(artifacts)
    assert payload["artifact_summary"]["latest_combined"] == str(latest_model)
    assert payload["artifact_summary"]["model_count"] == 3
    assert payload["artifact_summary"]["metrics_count"] == 3
    combined = next(row for row in payload["artifact_summary"]["by_feature"] if row["feature_set"] == "combined")
    assert combined["latest_model"] == str(latest_model)
    assert combined["latest_metrics"] == str(latest_metrics)
    assert combined["created_at"] == "20260524T130000Z"
    assert combined["trained_rows"] == 16
    assert combined["feature_count"] == 42
    assert combined["accuracy_mean"] == 0.71
    assert combined["positive_recall_mean"] == 0.74
    assert payload["metrics_history"][0]["created_at"] == "20260524T130000Z"
    assert payload["metrics_history"][1]["created_at"] == "20260524T120000Z"


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
    labels.update_profile("break_energy", artifact_dir=artifacts)
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    ready = client.get("/api/profiles/break_energy/training/readiness").json()
    blocked = client.post("/api/profiles/break_energy/training/train-refresh")

    assert ready["ready"] is False
    assert ready["current"] == {"broken": 500, "straight": 500}
    assert ready["last_trained"] == {"broken": 500, "straight": 500}
    assert ready["added"] == {"broken": 0, "straight": 0}
    assert RhythmLabDatabase(labels_path).training_checkpoint()["counts"] == {"broken": 500, "straight": 500}
    assert blocked.status_code == 400


def test_web_app_promote_requires_trained_combined_artifact(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    RhythmLabDatabase(labels_path).update_profile("break_energy", artifact_dir=tmp_path / "artifacts" / "break-energy")
    target_root = tmp_path / "models" / "classifiers"
    client = TestClient(create_app(source_path, labels_db_path=labels_path, classifier_target_root=target_root))

    response = client.post("/api/profiles/break_energy/promote")

    assert response.status_code == 400
    assert "Train a combined model before promoting" in response.json()["detail"]
    assert not target_root.exists()


def test_web_app_promote_copies_latest_trained_combined_model(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    LibraryDatabase(source_path)
    labels_path = tmp_path / "labels.sqlite"
    labels = RhythmLabDatabase(labels_path)
    labels.set_label(101, "broken")
    labels.set_label(102, "straight")
    artifacts = tmp_path / "artifacts" / "break-energy"
    artifacts.mkdir(parents=True)
    latest = artifacts / "break-energy-combined-20260524T130000Z.joblib"
    joblib.dump(
        {
            "classifier_key": "break_energy",
            "feature_set": "combined",
            "feature_names": ["tempo", "energy"],
            "label_order": ["broken", "straight"],
            "positive_label": "broken",
            "model": object(),
        },
        latest,
    )
    labels.update_profile("break_energy", artifact_dir=artifacts)
    labels.record_training_checkpoint({"broken": 1, "straight": 1}, model_artifact=latest)
    target_root = tmp_path / "models" / "classifiers"
    client = TestClient(create_app(source_path, labels_db_path=labels_path, classifier_target_root=target_root))

    response = client.post("/api/profiles/break_energy/promote")

    assert response.status_code == 200
    target = target_root / "break-energy"
    assert response.json()["model_path"] == str(target / "model.joblib")
    assert response.json()["metadata_path"] == str(target / "model.json")
    assert joblib.load(target / "model.joblib")["feature_set"] == "combined"
    metadata = json.loads((target / "model.json").read_text(encoding="utf-8"))
    assert metadata["classifier_key"] == "break_energy"
    assert metadata["feature_set"] == "combined"
    assert metadata["feature_count"] == 2
    assert metadata["source_artifact"] == str(latest)
    assert metadata["trained_label_counts"] == {"broken": 1, "straight": 1}


def test_static_ui_promote_button_sits_after_train_refresh_and_is_wired() -> None:
    html = (LAB_ROOT / "rhythm_lab" / "static" / "index.html").read_text(encoding="utf-8")
    script = (LAB_ROOT / "rhythm_lab" / "static" / "app.js").read_text(encoding="utf-8")

    train_index = html.index('id="trainRefresh"')
    promote_index = html.index('id="promoteClassifier"')

    assert promote_index > train_index
    assert 'class="icon-button promote-classifier"' in html
    assert 'promoteClassifierEl.addEventListener("click", () => promoteClassifier().catch(showError));' in script
    assert "promoteClassifierEl.disabled = !canPromote;" in script


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

    result = cleanup_training_artifacts(artifacts, protected_artifact=protected, artifact_prefix="break-energy")

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


def test_cli_promote_profile_copies_latest_combined_model_to_classifier_asset(tmp_path: Path) -> None:
    from rhythm_lab.cli import build_parser

    labels_db = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels_db.create_profile(
        classifier_key="live_instrumentation",
        name="Live Instrumentation",
        artifact_dir=tmp_path / "artifacts" / "live-instrumentation",
        artifact_prefix="live-instrumentation",
        labels=[
            {"key": "live_instrument", "name": "Live Instrument", "role": "positive"},
            {"key": "no_instrument", "name": "No Instrument", "role": "negative"},
            {"key": "uncertain", "name": "Uncertain", "role": "review"},
        ],
    )
    labels_db = RhythmLabDatabase(labels_db.path, classifier_key="live_instrumentation")
    labels_db.set_label(101, "live_instrument")
    labels_db.set_label(102, "no_instrument")

    artifacts = tmp_path / "artifacts" / "live-instrumentation"
    target_root = tmp_path / "models" / "classifiers"
    artifacts.mkdir(parents=True)
    old = artifacts / "live-instrumentation-combined-20260524T100000Z.joblib"
    latest = artifacts / "live-instrumentation-combined-20260524T110000Z.joblib"
    maest = artifacts / "live-instrumentation-maest-20260524T120000Z.joblib"
    joblib.dump(
        {
            "classifier_key": "live_instrumentation",
            "feature_set": "combined",
            "label_order": ["live_instrument", "no_instrument"],
            "positive_label": "live_instrument",
            "model": object(),
        },
        old,
    )
    joblib.dump(
        {
            "classifier_key": "live_instrumentation",
            "feature_set": "combined",
            "label_order": ["live_instrument", "no_instrument"],
            "positive_label": "live_instrument",
            "model": object(),
        },
        latest,
    )
    joblib.dump(
        {
            "classifier_key": "live_instrumentation",
            "feature_set": "maest",
            "label_order": ["live_instrument", "no_instrument"],
            "positive_label": "live_instrument",
            "model": object(),
        },
        maest,
    )

    args = build_parser().parse_args([
        "promote",
        "--profile",
        "live_instrumentation",
        "--target",
        str(target_root),
        "--labels",
        str(labels_db.path),
    ])
    args.func(args)

    target = target_root / "live-instrumentation"
    promoted = target / "model.joblib"
    metadata_path = target / "model.json"
    assert promoted.exists()
    assert joblib.load(promoted)["feature_set"] == "combined"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["classifier_key"] == "live_instrumentation"
    assert metadata["profile_name"] == "Live Instrumentation"
    assert metadata["positive_label"] == "live_instrument"
    assert metadata["negative_label"] == "no_instrument"
    assert "classifier" not in metadata
    assert "score_name" not in metadata
    assert metadata["source_artifact"] == str(latest)
    assert metadata["trained_label_counts"] == {"live_instrument": 1, "no_instrument": 1}


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

    page = client.get("/api/profiles/break_energy/tracks", params={"limit": 1, "offset": 1}).json()
    labeled = client.get("/api/profiles/break_energy/tracks", params={"label": "straight"}).json()

    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["id"] == second_id
    assert labeled["total"] == 1
    assert labeled["items"][0]["label"] == "straight"
    assert labeled["items"][0]["id"] == second_id
    assert first_id != second_id


def test_web_app_tracks_endpoint_supports_stable_random_library_order(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    for title in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"):
        _track(source, tmp_path, f"{title.lower()}.wav", title=title)
    labels_path = tmp_path / "labels.sqlite"
    client = TestClient(create_app(source_path, labels_db_path=labels_path))

    normal = client.get(
        "/api/profiles/break_energy/tracks",
        params={"limit": 8, "order": "normal"},
    ).json()
    first_random = client.get(
        "/api/profiles/break_energy/tracks",
        params={"limit": 4, "offset": 0, "order": "random", "seed": "12345"},
    ).json()
    second_random = client.get(
        "/api/profiles/break_energy/tracks",
        params={"limit": 4, "offset": 4, "order": "random", "seed": "12345"},
    ).json()
    repeated_random = client.get(
        "/api/profiles/break_energy/tracks",
        params={"limit": 8, "order": "random", "seed": "12345"},
    ).json()
    reshuffled = client.get(
        "/api/profiles/break_energy/tracks",
        params={"limit": 8, "order": "random", "seed": "67890"},
    ).json()

    normal_ids = [item["id"] for item in normal["items"]]
    paged_random_ids = [item["id"] for item in first_random["items"] + second_random["items"]]
    repeated_random_ids = [item["id"] for item in repeated_random["items"]]
    reshuffled_ids = [item["id"] for item in reshuffled["items"]]

    assert normal_ids == sorted(normal_ids)
    assert paged_random_ids == repeated_random_ids
    assert sorted(repeated_random_ids) == normal_ids
    assert repeated_random_ids != normal_ids
    assert reshuffled_ids != repeated_random_ids


def test_web_app_marks_labels_used_in_previous_training_checkpoint(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    trained_id = _track(source, tmp_path, "trained.wav", title="Trained")
    new_id = _track(source, tmp_path, "new.wav", title="New")
    review_id = _track(source, tmp_path, "review.wav", title="Review")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.set_label(source.get_track(trained_id), "broken")
    labels.set_label(source.get_track(new_id), "straight")
    labels.set_label(source.get_track(review_id), "ambiguous")
    labels.record_training_checkpoint({"broken": 1, "straight": 0}, model_artifact="model.joblib")
    with labels.connect() as connection:
        connection.execute(
            """
            UPDATE classifier_labels
            SET updated_at = CASE source_track_id
                WHEN ? THEN '2026-01-01 00:00:00'
                WHEN ? THEN '2026-01-03 00:00:00'
                WHEN ? THEN '2026-01-01 00:00:00'
            END
            WHERE classifier_key = 'break_energy'
            """,
            (trained_id, new_id, review_id),
        )
        connection.execute(
            """
            UPDATE classifier_training_checkpoints
            SET updated_at = '2026-01-02 00:00:00'
            WHERE classifier_key = 'break_energy'
            """
        )
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    page = client.get("/api/profiles/break_energy/tracks", params={"label": "all"}).json()

    by_id = {item["id"]: item for item in page["items"]}
    assert by_id[trained_id]["label_trained"] is True
    assert by_id[new_id]["label_trained"] is False
    assert by_id[review_id]["label_trained"] is False
    assert "label_updated_at" not in by_id[trained_id]


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

    summary = client.get("/api/profiles/break_energy/summary").json()

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


def test_web_app_http_error_responses_are_logged(caplog, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    missing_path = tmp_path / "missing.sqlite"
    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))

    with caplog.at_level(logging.WARNING, logger="rhythm_lab"):
        response = client.post("/api/source/switch", json={"path": str(missing_path)})

    assert response.status_code == 400
    assert "HTTP request returned error method=POST path=/api/source/switch status=400" in caplog.text


def test_web_app_registers_asyncio_exception_logging_startup(tmp_path: Path) -> None:
    app = create_app(labels_db_path=tmp_path / "labels.sqlite")

    assert install_rhythm_lab_asyncio_exception_logging in app.router.on_startup


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


def test_cli_serve_passes_bracketed_log_config_to_uvicorn(monkeypatch, tmp_path: Path) -> None:
    import rhythm_lab.cli as lab_cli
    import rhythm_lab.web_app as web_app
    import uvicorn

    captured = {}
    monkeypatch.setattr(web_app, "create_app", lambda *args, **kwargs: object())

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    lab_cli._serve(
        argparse.Namespace(
            source=None,
            labels=tmp_path / "labels.sqlite",
            host="127.0.0.1",
            port=8777,
        )
    )

    log_config = captured["kwargs"]["log_config"]
    assert log_config["formatters"]["default"]["format"] == "[%(asctime)s] [%(levelname)s] %(message)s"
    assert log_config["formatters"]["default"]["datefmt"] == "%Y-%m-%d] [%H:%M:%S"
    assert log_config["loggers"]["uvicorn"]["level"] == "INFO"


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
    styles = client.get("/static/styles.css").text
    stop_button_rule = styles.split(".icon-button.rhythm-lab-stop-button {", 1)[1].split("}", 1)[0]

    assert "<strong>Rhythm Lab</strong>" in html
    assert 'id="activeProfileName">No profile selected</span>' in html
    assert 'id="shutdownLab"' in html
    assert html.index('id="shutdownLab"') < html.index('id="activeProfileName"')
    assert 'class="icon-button rhythm-lab-stop-button"' in html
    assert 'aria-label="Stop Rhythm Lab"' in html
    assert 'fetch("/api/shutdown"' in script
    assert "async function shutdownLab()" in script
    assert ".icon-button.rhythm-lab-stop-button" in styles
    assert "width: 30px" in stop_button_rule
    assert "height: 30px" in stop_button_rule
    assert "margin-left: 14px" in stop_button_rule
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


def test_web_app_shutdown_endpoint_uses_shutdown_callback(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    calls = []
    client = TestClient(
        create_app(
            labels_db_path=tmp_path / "labels.sqlite",
            shutdown_callback=lambda: calls.append("shutdown"),
        )
    )

    response = client.post("/api/shutdown")

    assert response.status_code == 200
    assert response.json() == {"stopping": True}
    assert calls == ["shutdown"]


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
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert '<link rel="stylesheet" href="/static/styles.css?v=rhythm-lab-20260701-random-order-init" />' in html
    assert '<script src="/static/app.js?v=rhythm-lab-20260701-random-order-init" defer></script>' in html
    assert 'id="profileSelect"' in html
    assert "/api/profiles" in script
    assert "function renderLabelButtons" in script
    assert '<button data-label="broken">Broken</button>' not in html
    assert "classifier-gradient" in styles
    assert 'featureStatusBadge("TRAINED", track.label_trained)' in script
    assert ".features-indicator.ready" in styles
    assert ".features-indicator.missing" in styles


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
    assert 'id="newProfileTrainingMinAdded"' in html
    assert 'id="profileTrainingMinAddedInput"' in html
    assert '<option value="binary" selected>Binary</option>' in html
    assert '<option value="multiclass">Multiclass</option>' in html
    assert 'id="multiclassLabelRows"' in html
    assert 'id="addMulticlassLabel"' in html
    assert 'class="multiclass-label-description"' in html
    assert 'function collectNewProfileLabels' in script
    assert 'profile_type: document.getElementById("newProfileType").value' in script
    assert 'training_min_added: Number(document.getElementById("newProfileTrainingMinAdded").value || 50)' in script
    assert 'training_min_added: Number(document.getElementById("profileTrainingMinAddedInput").value || 50)' in script
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
        "likedTab",
        "trainingTab",
        "settingsTab",
        "refreshCandidates",
        "trainRefresh",
        "shuffleLibraryOrder",
        "load",
        "prevPage",
        "nextPage",
    ):
        assert f'<button id="{button_id}" type="button"' in html
    assert '<button type="button" class="${active}" data-action="label" data-label="${escapeHtml(label.key)}">' in script
    assert 'buttons.push(\'<button type="button" data-action="label" data-label="">Clear</button>\');' in script


def test_static_ui_supports_page_number_jump(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="pageNumber"' in html
    assert 'pageNumberEl.addEventListener("change", () => jumpToPage());' in script
    assert 'pageNumberEl.addEventListener("keydown", event => { if (event.key === "Enter") jumpToPage(); });' in script
    assert "function pageCount(totalItems, limit)" in script
    assert "function currentPage(data)" in script
    assert "const first = shown ? data.offset + 1 : 0;" in script
    assert "const last = shown ? data.offset + shown : 0;" in script
    assert 'pageInfoEl.textContent = `${current} / ${pages} (${first}-${last} / ${data.total})`;' in script
    assert "offset = (targetPage - 1) * limit;" in script
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")
    assert ".page-number {\n  flex: 0 0 auto;" in styles
    assert "  width: 56px;" in styles
    assert "  max-width: 56px;" in styles
    assert html.index('id="pageSize"') < html.index('id="prevPage"')
    assert html.index('id="prevPage"') < html.index('id="nextPage"')
    assert html.index('id="nextPage"') < html.index('id="pageNumber"')
    assert html.index('id="pageNumber"') < html.index('id="load"')
    assert html.index('id="load"') < html.index('id="pageInfo"')


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
    styles = client.get("/static/styles.css").text

    assert 'id="libraryTab"' in html
    assert 'id="candidatesTab"' in html
    assert 'id="likedTab"' in html
    assert 'id="candidateMinBroken"' in html
    assert '<option value="positive_highest" selected>highest positive probability</option>' in html
    assert '<option value="negative_highest">highest negative probability</option>' in html
    assert '<option value="balanced">uncertain / balanced</option>' in html
    assert 'fetch(`/api/profiles/${activeProfile.classifier_key}/predictions?' in script
    assert "positive_probability" in script
    assert '<span class="status-item"><b>SCORE</b><span class="status-detail">${formatProbability(predictedScore(track))}</span></span>' in script
    assert "return positiveScore(track);" in script
    assert "function positiveScore(track)" in script
    assert "return binaryPredictedScore(track.negative_probability, track.positive_probability);" not in script
    assert '<span class="status-item"><b>TYPE</b><span class="status-detail">${escapeHtml(track.feature_set)}</span></span>' in script
    assert "function predictionBadge(track)" in script
    assert 'number.toFixed(6)' in script
    assert 'if (number < 1 && number.toFixed(6) === "1.000000") return "0.999999";' in script
    assert "candidate-prediction-line" not in script
    assert "candidate-prediction-line" not in styles
    assert "multiclassProbabilitiesLine" not in script
    assert '${trackStatusLine(track)}' in script
    assert 'function trainedStatus(track)' in script
    assert 'return featureStatusBadge("TRAINED", track.label_trained);' in script
    assert 'function predictionStatus(track)' in script
    assert '<span class="status-item"><b>PREDICTED</b>${predictionBadge(track)}</span>' in script
    assert "toggleLike" in script
    assert "likedIndicator" not in script
    assert "<b>LIKED</b>" not in script
    assert ".analysis-status-badge.status-liked" not in styles
    assert 'params.set("liked", "yes");' in script
    assert "renderLikeButton" in script
    assert '<b>LABEL</b>' not in script
    assert "<b>ANALYZED</b>" not in script
    assert "status-separator" not in script
    assert "track.feature_status.sonara && track.feature_status.mert && track.feature_status.maest" in script
    assert "function featuresIndicator(track)" in script
    assert 'function featureStatusBadge(name, value)' in script
    assert '<span class="status-item"><b>${name}</b><span class="analysis-status-badge ${value ? "status-yes" : "status-no"}">${mark(value)}</span></span>' in script
    assert '<strong class="track-heading"><span class="track-title-main"><span class="track-number">#${track.rowNumber}</span>${escapeHtml(displayTrackTitle(track))}</span>${featuresIndicator(track)}</strong>' in script
    assert '<div class="meta feature-line">${trackStatusLine(track)}</div>' in script
    assert '<div class="meta genres-line"><span class="status-item"><b>GENRES</b></span><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in script


def test_web_app_filter_controls_combine_without_losing_tab_state(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text

    assert 'id="commonFilters"' in html
    assert '<section id="candidateFilters" class="filters candidate-filters-placeholder">' in html
    assert 'id="libraryOrder"' in html
    assert '<option value="normal" selected>Normal order</option>' in html
    assert '<option value="random">Random</option>' in html
    assert 'id="shuffleLibraryOrder"' in html
    assert 'id="candidateMinPositive" type="number" min="0" max="1" step="0.05" value="0"' in html
    assert 'id="syncopated"' not in html
    assert 'id="bpmMin" type="number" min="0" step="0.1" placeholder="BPM from"' in html
    assert 'id="bpmMax" type="number" min="0" step="0.1" placeholder="BPM to"' in html
    assert html.index('id="label"') < html.index('id="candidateFilters"')
    assert html.index('id="candidateFilters"') < html.index('id="libraryOrder"')
    assert html.index('id="libraryOrder"') < html.index('id="shuffleLibraryOrder"')
    assert html.index('id="shuffleLibraryOrder"') < html.index('id="candidatePredicted"')
    assert html.index('id="candidateMinBroken"') < html.index('<section class="pager">')
    assert "const syncopatedEl" not in script
    assert 'bpmMinEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'bpmMaxEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'labelEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'libraryOrderEl.addEventListener("change", () => updateLibraryOrder({ reset: true }));' in script
    assert 'shuffleLibraryOrderEl.addEventListener("click", () => shuffleLibraryOrder());' in script
    assert 'candidatePredictedEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert 'candidateMinBrokenEl.addEventListener("change", () => loadActive({ reset: true }));' in script
    assert ".candidate-filters-placeholder > *" in styles
    assert ".filters[hidden]," in styles
    assert "function updateFilterPanelControls()" in script
    assert 'candidateFiltersEl.hidden = activeView === "training" || activeView === "settings";' in script
    assert 'candidateFiltersEl.classList.toggle("candidate-filters-placeholder", activeView !== "library" && activeView !== "candidates");' in script
    assert 'libraryOrderEl.disabled = activeView !== "library";' in script
    assert 'shuffleLibraryOrderEl.hidden = activeView !== "library";' in script
    assert 'candidatePredictedEl.hidden = activeView !== "candidates";' in script
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
    assert "const viewOffsets = { library: 0, candidates: 0, liked: 0, training: 0, settings: 0 };" in script
    assert "let loadSequence = 0;" in script
    assert "const sequence = ++loadSequence;" in script
    assert 'if (sequence !== loadSequence || activeView !== "library") return;' in script
    assert 'if (sequence !== loadSequence || activeView !== "candidates") return;' in script
    assert 'if (sequence !== loadSequence || activeView !== "liked") return;' in script
    assert "viewOffsets[activeView] = offset;" in script
    assert "offset = viewOffsets[view] || 0;" in script
    assert "q: queryEl.value," in script
    assert "bpm_min: bpmFilterValue(bpmMinEl.value)," in script
    assert "bpm_max: bpmFilterValue(bpmMaxEl.value)," in script
    assert "label: labelEl.value," in script
    assert 'params.set("order", libraryOrderEl.value);' in script
    assert 'params.set("seed", String(libraryRandomSeed));' in script
    assert "predicted: candidatePredictedEl.value," in script
    assert "probability_focus: candidateMinBrokenEl.value," in script
    assert "min_positive: probabilityFilterValue()," in script
    assert 'replace(",", ".")' in script
    assert "function bpmFilterValue(value)" in script


def test_web_app_training_tab_adds_bottom_training_stats_card(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert '<div class="guidance-card training-info-card"><b>Training Stats</b>' in script
    assert "${renderTrainingInformationMetrics(data)}" in script
    assert script.index('<div class="guidance-card"><b>Training plan</b>') < script.index("${renderTrainingInformationMetrics(data)}")
    assert "function renderTrainingInformationMetrics(data)" in script
    assert "function formatHumanDate(value)" in script
    assert "Intl.DateTimeFormat" in script
    assert "function parseTrainingDate(value)" in script
    assert "function renderTrainingArtifactsLine(summary)" in script
    assert "feature sets · latest combined" in script
    assert "function renderTrainingMetricsLine(summary)" in script
    assert "function renderTrainingDynamicsLine(history)" in script
    assert "previous run" in script
    assert "const latest = (history || [])[0];" in script
    assert ".training-info-card .meta" in styles
    assert ".training-info-card .meta {\n  display: grid;" in styles
    assert ".training-info-card .meta {\n  font-size:" not in styles
    assert ".training-info-line {\n  font-size:" not in styles
    assert ".training-panel {\n  display: grid;" not in styles


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


def test_web_app_navigation_tabs_have_icons(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    html = client.get("/").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert '<button id="libraryTab" type="button" class="tab-button active">' in html
    assert 'class="lucide lucide-library-big"' in html
    assert '<button id="candidatesTab" type="button" class="tab-button">' in html
    assert 'class="lucide lucide-sparkles"' in html
    assert '<button id="likedTab" type="button" class="tab-button">' in html
    assert 'class="lucide lucide-heart"' in html
    assert '<button id="trainingTab" type="button" class="tab-button">' in html
    assert 'class="lucide lucide-dumbbell"' in html
    assert ".tab-button {\n  display: inline-flex;" in styles
    assert ".tab-button svg {\n  width: 16px;\n  height: 16px;" in styles


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
    assert ".analysis-status-badge" in styles
    assert ".profile-label-badge.label-role-positive" in styles
    assert ".profile-label-badge.label-role-negative" in styles
    assert ".profile-label-badge.label-role-review" in styles
    assert 'label-role-${escapeHtml(role)}' in script
    assert "label-${escapeHtml(label)}" in script
    assert "button.classList.add(button.dataset.label)" not in script
    assert "button.active.broken" not in styles
    assert "button.active.straight" not in styles
    assert "button.active.ambiguous" not in styles


def test_web_app_multiclass_label_buttons_use_right_aligned_grid(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    script = client.get("/static/app.js").text
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert '<div class="label-actions ${isMulticlassProfile() ? "multiclass-label-actions" : ""}">' in script
    assert ".multiclass-label-actions {\n  display: grid;\n  grid-template-columns: repeat(2, minmax(132px, 1fr));" in styles
    assert "justify-content: end;" in styles
    assert "width: min(340px, 100%);" in styles
    assert "@media (max-width: 760px)" in styles
    assert "@media (max-width: 420px)" in styles
    assert ".multiclass-label-actions {\n    grid-template-columns: 1fr;" in styles


def test_web_app_summary_uses_compact_badges(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite"))
    styles = client.get("/static/styles.css").text.replace("\r\n", "\n")

    assert ".summary-strip {\n  display: grid;" in styles
    assert "grid-template-columns: auto minmax(0, 1fr);" in styles
    assert ".summary-group {\n  display: inline-flex;" in styles
    assert ".summary-badge {\n  display: inline-flex;" in styles
    assert ".summary-labels {\n  justify-self: end;\n  max-width: 100%;" in styles
    assert "justify-content: flex-end;" in styles
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

    assert '<div class="meta genres-line"><span class="status-item"><b>GENRES</b></span><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in script
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


def test_web_app_serves_24_bit_wav_preview_as_seekable_browser_audio(monkeypatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import rhythm_lab.web_app as web_app

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    path = tmp_path / "preview-24.wav"
    _write_wav(path, sample_width=3)
    track_id = source.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": "Preview 24"})
    labels_path = tmp_path / "labels.sqlite"
    calls = []

    def fake_run(command, *, stderr, check):
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(web_app, "require_ffmpeg", lambda: "ffmpeg")
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
    assert calls[0][4] == str(path)
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
    assert "#tracks:not(:empty) {\n  overflow: hidden;\n  border: 1px solid rgba(38, 49, 61, 0.9);\n  border-radius: 12px;\n  padding: 0 var(--panel-pad-x);" in styles


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


def test_train_feature_set_writes_generic_positive_discovery_metrics(tmp_path: Path) -> None:
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
    discovery = metrics["positive_discovery"]
    thresholds = discovery["thresholds"]
    top_n = discovery["top_n"]
    cross_validation = metrics["cross_validation"]

    assert discovery["positive_label"] == "broken"
    assert "broken_discovery" not in metrics
    assert {row["threshold"] for row in thresholds} >= {0.25, 0.5}
    assert all("positive_recall" in row for row in thresholds)
    assert all("broken_recall" not in row for row in thresholds)
    assert all("straight_candidates" not in row for row in thresholds)
    assert all("candidate_count" in row for row in thresholds)
    assert top_n[0]["n"] == 1
    assert "positive_recall_mean" in cross_validation
    assert "broken_recall_mean" not in cross_validation
    assert cross_validation["fold_count"] >= 2


def test_train_feature_set_can_write_calibrated_validation_report(tmp_path: Path) -> None:
    matrix = np.asarray(
        [[float(index), 0.0] for index in range(60)]
        + [[float(index + 200), 1.0] for index in range(60)],
        dtype=np.float32,
    )
    labels = ["broken"] * 60 + ["straight"] * 60

    result = train_feature_set(
        matrix,
        labels,
        feature_names=["axis", "marker"],
        feature_set="combined",
        artifact_dir=tmp_path / "artifacts",
        calibrate=True,
    )

    payload = joblib.load(result.artifact_path)
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    calibration = metrics["production_calibration"]
    validation = calibration["validation"]
    assert payload["production_calibration"]["status"] == "calibrated"
    assert calibration["status"] == "calibrated"
    assert calibration["method"] == "sigmoid"
    assert validation["sample_count"] > 0
    assert validation["positive_count"] > 0
    assert validation["negative_count"] > 0
    assert validation["brier"] <= 1.0
    assert validation["ece10"] <= 1.0
    assert calibration["thresholds"]["default"] == 0.5


def test_promote_require_calibration_blocks_uncalibrated_artifact(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    artifact_dir = tmp_path / "artifacts"
    matrix = np.asarray(
        [[float(index), 0.0] for index in range(6)]
        + [[float(index + 20), 1.0] for index in range(6)],
        dtype=np.float32,
    )
    train_feature_set(
        matrix,
        ["broken"] * 6 + ["straight"] * 6,
        feature_names=["axis", "marker"],
        feature_set="combined",
        artifact_dir=artifact_dir,
    )

    try:
        promote_profile_model(
            labels.path,
            "break_energy",
            artifacts=artifact_dir,
            target_root=tmp_path / "models" / "classifiers",
            require_calibration=True,
        )
    except PromotionError as error:
        assert "calibration" in str(error).lower()
    else:  # pragma: no cover - defensive guard.
        raise AssertionError("uncalibrated artifact was promoted with require_calibration=True")

    assert not (tmp_path / "models" / "classifiers" / "break-energy" / "model.joblib").exists()


def test_promote_calibrated_artifact_writes_identity_and_calibration_manifest(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    artifact_dir = tmp_path / "artifacts"
    matrix = np.asarray(
        [[float(index), 0.0] for index in range(60)]
        + [[float(index + 200), 1.0] for index in range(60)],
        dtype=np.float32,
    )
    train_feature_set(
        matrix,
        ["broken"] * 60 + ["straight"] * 60,
        feature_names=["axis", "marker"],
        feature_set="combined",
        artifact_dir=artifact_dir,
        calibrate=True,
    )

    promoted = promote_profile_model(
        labels.path,
        "break_energy",
        artifacts=artifact_dir,
        target_root=tmp_path / "models" / "classifiers",
        require_calibration=True,
    )

    metadata = promoted["metadata"]
    assert metadata["model_id"].startswith("break_energy_")
    assert metadata["artifact_hash"].startswith("sha256:")
    assert metadata["production"]["calibration"]["status"] == "calibrated"
    assert metadata["production"]["calibration"]["validation_roc_auc"] is not None
    limitations = metadata["production"]["limitations"]
    assert any("calibrated positive-label probabilities" in limitation for limitation in limitations)
    assert all("not a calibrated probability" not in limitation for limitation in limitations)


def test_export_predictions_csv_orders_by_profile_positive_probability(tmp_path: Path) -> None:
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
    assert "broken_probability" not in rows[0]
    assert "straight_probability" not in rows[0]
    assert rows[0]["probability_broken"] == "0.7"
    assert rows[0]["probability_straight"] == "0.3"


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
    assert rows[0]["probability_broken"] == "0.2"


def test_export_predictions_csv_uses_custom_profile_probability_columns(tmp_path: Path) -> None:
    source = LibraryDatabase(tmp_path / "source.sqlite")
    track_id = _track(source, tmp_path, "track.wav", title="Track")
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    scoped = RhythmLabDatabase(labels.path, classifier_key="vocal_presence")
    scoped.save_prediction(
        source.get_track(track_id),
        feature_set="combined",
        model_artifact="model.joblib",
        label="vocal",
        confidence=0.8,
        probabilities={"vocal": 0.8, "instrumental": 0.2},
    )

    csv_path = export_predictions_csv(labels.path, tmp_path / "predictions.csv", classifier_key="vocal_presence")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["probability_vocal"] == "0.8"
    assert rows[0]["probability_instrumental"] == "0.2"
    assert "broken_probability" not in rows[0]


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


def test_cli_suggest_labels_can_write_queue(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    first_id = _track(source, tmp_path, "first.wav", title="First")
    second_id = _track(source, tmp_path, "second.wav", title="Second")
    for track_id, score in ((first_id, 0.49), (second_id, 0.9)):
        source.save_classifier_score(
            track_id,
            classifier="break_energy",
            score=score,
            label="medium" if score < 0.8 else "high",
            confidence=max(score, 1.0 - score),
            probabilities={"broken": score, "straight": 1.0 - score},
            feature_set="combined",
            model_id="test-model",
        )
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")

    result = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "suggest-labels",
            "--source",
            str(source_path),
            "--labels",
            str(labels.path),
            "--profile",
            "break_energy",
            "--mode",
            "uncertainty",
            "--limit",
            "2",
            "--write-queue",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    payload = json.loads(result.stdout)
    queued = labels.label_queue_items()
    assert result.returncode == 0, result.stderr
    assert payload["queue_written"] == 2
    assert [item["source_track_id"] for item in queued] == [first_id, second_id]
    assert queued[0]["mode"] == "uncertainty"
    assert queued[0]["reason"]["label_status"] == "unlabeled"


def test_cli_delete_profile_accepts_name_or_key_with_confirmation(tmp_path: Path) -> None:
    labels = RhythmLabDatabase(tmp_path / "labels.sqlite")
    labels.create_profile(
        classifier_key="vocal_presence",
        name="Vocal Presence",
        description="Detect obvious vocal parts.",
        artifact_dir=tmp_path / "artifacts" / "vocal-presence",
        labels=[
            {"key": "vocal", "name": "Vocal", "role": "positive"},
            {"key": "instrumental", "name": "Instrumental", "role": "negative"},
        ],
    )
    labels.create_profile(
        classifier_key="texture",
        name="Texture",
        description="Texture test.",
        artifact_dir=tmp_path / "artifacts" / "texture",
        labels=[
            {"key": "rough", "name": "Rough", "role": "positive"},
            {"key": "smooth", "name": "Smooth", "role": "negative"},
        ],
    )

    by_name = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "delete-profile",
            "--labels",
            str(labels.path),
            "--name",
            "Vocal Presence",
            "--confirm",
            "Vocal Presence",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert by_name.returncode == 0, by_name.stderr
    assert "deleted=vocal_presence" in by_name.stdout

    by_key = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "delete-profile",
            "--labels",
            str(labels.path),
            "--profile",
            "texture",
            "--confirm",
            "texture",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert by_key.returncode == 0, by_key.stderr
    assert "deleted=texture" in by_key.stdout


def _track(db: LibraryDatabase, tmp_path: Path, name: str, *, title: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": title})


def _write_wav(path: Path, *, sample_width: int) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(sample_width)
        audio.setframerate(44100)
        audio.writeframes(b"\x00" * sample_width * 2 * 128)

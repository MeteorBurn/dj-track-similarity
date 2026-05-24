from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import csv

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LAB_ROOT = ROOT / "experiments" / "rhythm-lab"
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


def test_labels_database_migrates_old_lab_track_ids_to_source_track_ids(tmp_path: Path) -> None:
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

    tracks = client.get("/api/tracks").json()
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
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rhythm_labels'"
        ).fetchone() is None


def test_web_app_predictions_endpoint_lists_candidates_by_broken_probability(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    low_id = _track(source, tmp_path, "low.wav", title="Low")
    high_id = _track(source, tmp_path, "high.wav", title="High")
    source.save_genres(high_id, [{"label": "Tech House", "score": 0.9}], model_name="maest-test")
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
    labels.set_label(source.get_track(high_id), "broken")
    client = TestClient(create_app(source_path, labels_db_path=labels.path))

    all_candidates = client.get("/api/predictions", params={"label": "all"}).json()
    unlabeled = client.get("/api/predictions", params={"label": "unlabeled"}).json()
    filtered = client.get("/api/predictions", params={"label": "all", "min_broken": 0.5}).json()

    assert all_candidates["total"] == 2
    assert [item["id"] for item in all_candidates["items"]] == [high_id, low_id]
    assert all_candidates["items"][0]["broken_probability"] == 0.7
    assert all_candidates["items"][0]["label"] == "broken"
    assert all_candidates["items"][0]["genres"] == ["Tech House"]
    assert all_candidates["items"][0]["maest_syncopated_rhythm"] is False
    assert all_candidates["items"][0]["feature_status"] == {"sonara": True, "mert": True, "maest": True}
    assert unlabeled["total"] == 1
    assert unlabeled["items"][0]["id"] == low_id
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == high_id


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

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert 'id="sourcePath"' in html
    assert 'id="chooseSource"' in html
    assert 'id="loadSource"' in html
    assert 'fetch("/api/source/dialog"' in html
    assert 'fetch("/api/source/switch"' in html
    assert "`${data.tracks} tracks | MAEST ${data.maest} | MERT ${data.mert} – Labels: ${formatLabelCounts(data.labels)}`" in html


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

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert 'id="libraryTab"' in html
    assert 'id="candidatesTab"' in html
    assert 'id="candidateMinBroken"' in html
    assert 'fetch(`/api/predictions?' in html
    assert "broken_probability" in html
    assert 'SONARA ${mark(track.feature_status.sonara)} · MERT ${mark(track.feature_status.mert)} · MAEST ${mark(track.feature_status.maest)} · label <b>${track.label || "none"}</b>' in html
    assert '<div class="genres-line"><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in html


def test_web_app_html_colors_manual_labels_by_label_value(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert ".rhythm-label-badge.broken" in html
    assert ".rhythm-label-badge.straight" in html
    assert ".rhythm-label-badge.ambiguous" in html
    assert "label-${escapeHtml(track.label)}" in html
    assert "button.classList.add(button.dataset.label)" not in html
    assert "button.active.broken" not in html
    assert "button.active.straight" not in html
    assert "button.active.ambiguous" not in html


def test_web_app_track_title_does_not_add_separator_without_artist(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert "function displayTrackTitle(track)" in html
    assert "${escapeHtml(displayTrackTitle(track))}" in html
    assert "${escapeHtml(track.artist || \"\")} - ${escapeHtml(track.title || track.path)}" not in html


def test_web_app_places_rhythm_badges_on_genres_line(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert '<div class="genres-line"><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>' in html
    assert '${badgeRow(track)}\n          <audio controls' not in html


def test_web_app_stops_previous_audio_preview_when_another_starts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert "let activeAudio = null;" in html
    assert "wireAudioPreview(row.querySelector(\"audio\"));" in html
    assert "function wireAudioPreview(audio)" in html
    assert "activeAudio.pause();" in html
    assert "activeAudio.currentTime = 0;" in html


def test_web_app_audio_preview_is_compact(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert "audio { width: min(520px, 100%); height: 34px; margin-top: 6px;" in html


def test_web_app_track_rows_have_more_vertical_spacing(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_app(labels_db_path=tmp_path / "labels.sqlite")).get("/").text

    assert ".track-main { display: flex; flex-direction: column; gap: 3px;" in html
    assert ".rhythm-media-block { margin-top: 7px;" in html
    assert '<div class="rhythm-media-block">' in html


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

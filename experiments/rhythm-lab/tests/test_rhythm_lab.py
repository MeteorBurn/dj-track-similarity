from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
LAB_ROOT = ROOT / "experiments" / "rhythm-lab"
sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase

from rhythm_lab.importer import import_non_sync_sample, import_syncopated_subset
from rhythm_lab.lab_db import RhythmLabDatabase
from rhythm_lab.maest_embeddings import LabMaestAnalysisJobManager, MaestEmbeddingAdapter
from rhythm_lab.predictions import apply_model_to_lab, export_predictions_csv
from rhythm_lab.training import train_feature_set
from rhythm_lab.web_app import create_app


def test_import_syncopated_subset_copies_only_flagged_tracks_and_sonara(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken_id = _track(source, tmp_path, "broken.wav", title="Broken")
    straight_id = _track(source, tmp_path, "straight.wav", title="Straight")
    source.save_genres(broken_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    source.save_genres(straight_id, [{"label": "House", "score": 0.8}], model_name="maest-test")
    source.save_sonara_features(
        broken_id,
        {"onset_density": {"type": "float", "value": 4.2}, "mfcc_mean": {"type": "list", "value": [1.0, 2.0]}},
        bpm=130,
        model_name="sonara-test",
    )

    lab_path = tmp_path / "rhythm_lab.sqlite"
    summary = import_syncopated_subset(source_path, lab_path)

    lab = RhythmLabDatabase(lab_path)
    tracks = lab.library.list_tracks()
    assert summary.scanned == 2
    assert summary.imported == 1
    assert len(tracks) == 1
    assert Path(tracks[0].path).name == "broken.wav"
    assert tracks[0].metadata["maest_syncopated_rhythm"] is True
    assert tracks[0].metadata["sonara_features"]["onset_density"]["value"] == 4.2
    assert lab.source_track_id(tracks[0].id) == broken_id
    assert source.get_track(straight_id).metadata["maest_syncopated_rhythm"] is False


def test_import_non_sync_sample_skips_existing_and_sync_tracks(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken_id = _track(source, tmp_path, "broken.wav", title="Broken")
    house_id = _track(source, tmp_path, "house.wav", title="House")
    techno_id = _track(source, tmp_path, "techno.wav", title="Techno")
    unknown_id = _track(source, tmp_path, "unknown.wav", title="Unknown")
    source.save_genres(broken_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    source.save_genres(house_id, [{"label": "House", "score": 0.9}], model_name="maest-test")
    source.save_genres(techno_id, [{"label": "Techno", "score": 0.8}], model_name="maest-test")

    lab_path = tmp_path / "rhythm_lab.sqlite"
    lab = RhythmLabDatabase(lab_path)
    existing_track_id = _track(lab.library, tmp_path, "existing-house.wav", title="Existing House")
    lab.record_source_track(existing_track_id, house_id)

    summary = import_non_sync_sample(source_path, lab_path, count=2)

    tracks = RhythmLabDatabase(lab_path).library.list_tracks()
    source_ids = {RhythmLabDatabase(lab_path).source_track_id(track.id) for track in tracks}
    imported_source_ids = source_ids - {house_id}
    assert summary.scanned == 4
    assert summary.imported == 2
    assert imported_source_ids == {techno_id, unknown_id}
    assert broken_id not in source_ids
    assert len(source.list_tracks()) == 4


def test_lab_labels_persist_and_training_rows_exclude_ambiguous(tmp_path: Path) -> None:
    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    broken = _track(lab.library, tmp_path, "broken.wav", title="Broken")
    straight = _track(lab.library, tmp_path, "straight.wav", title="Straight")
    ambiguous = _track(lab.library, tmp_path, "ambiguous.wav", title="Ambiguous")

    lab.set_label(broken, "broken")
    lab.set_label(straight, "straight")
    lab.set_label(ambiguous, "ambiguous")

    assert lab.label_for_track(broken).label == "broken"
    assert lab.label_counts() == {"ambiguous": 1, "broken": 1, "straight": 1}
    assert lab.training_labels() == {
        broken: "broken",
        straight: "straight",
    }


def test_lab_database_migrates_old_straight_label_value(tmp_path: Path) -> None:
    db_path = tmp_path / "rhythm_lab.sqlite"
    library = LibraryDatabase(db_path)
    track_id = _track(library, tmp_path, "straight.wav", title="Straight")
    with library._write_lock, library.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE rhythm_labels (
                track_id INTEGER PRIMARY KEY,
                label TEXT NOT NULL CHECK(label IN ('broken', 'straight_four_on_the_floor', 'ambiguous')),
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            CREATE TABLE rhythm_predictions (
                track_id INTEGER NOT NULL,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL CHECK(label IN ('broken', 'straight_four_on_the_floor')),
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, feature_set, model_artifact),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            """
        )
        connection.execute(
            "INSERT INTO rhythm_labels(track_id, label) VALUES (?, 'straight_four_on_the_floor')",
            (track_id,),
        )
        connection.execute(
            """
            INSERT INTO rhythm_predictions(
                track_id, feature_set, model_artifact, label, confidence, probabilities_json
            )
            VALUES (?, 'sonara', 'old.joblib', 'straight_four_on_the_floor', 0.8, ?)
            """,
            (track_id, json.dumps({"broken": 0.2, "straight_four_on_the_floor": 0.8})),
        )

    lab = RhythmLabDatabase(db_path)

    assert lab.label_for_track(track_id).label == "straight"
    assert lab.training_labels() == {track_id: "straight"}
    assert lab.predictions()[0]["label"] == "straight"
    assert lab.predictions()[0]["probabilities"] == {"broken": 0.2, "straight": 0.8}
    lab.set_label(track_id, "straight_four_on_the_floor")
    assert lab.label_for_track(track_id).label == "straight"


def test_existing_analysis_job_can_compute_maest_embeddings_for_lab_db(tmp_path: Path) -> None:
    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    first = _track(lab.library, tmp_path, "first.wav", title="First")
    second = _track(lab.library, tmp_path, "second.wav", title="Second")

    class FakeMaestEmbeddingAdapter:
        embedding_key = "maest"
        model_name = "fake-maest-embedding"
        dim = 3
        device = "cpu"

        def __init__(self, device: str = "auto", inference_batch_size: int = 4) -> None:
            self.device = device
            self.inference_batch_size = inference_batch_size

        def embed(self, path: str) -> np.ndarray:
            return self.embed_batch([path])[0]

        def embed_batch(self, paths: list[str]) -> list[np.ndarray]:
            return [np.asarray([index + 1, 1, 0], dtype=np.float32) for index, _path in enumerate(paths)]

    manager = AnalysisJobManager(lab.library, {"maest": FakeMaestEmbeddingAdapter})
    status = manager.run_sync(adapter_name="maest", device="cpu", batch_size=2)

    assert status.state == "completed"
    assert status.total == 2
    assert status.analyzed == 2
    tracks, matrix = lab.library.load_embedding_matrix("maest")
    assert [track.id for track in tracks] == [first, second]
    assert matrix.shape == (2, 3)


def test_lab_maest_job_saves_fresh_genres_with_embeddings(tmp_path: Path) -> None:
    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    track_id = _track(lab.library, tmp_path, "track.wav", title="Track")
    lab.library.save_genres(track_id, [{"label": "Old House", "score": 0.9}], model_name="old-maest")

    class FakeMaestEmbeddingAdapter:
        embedding_key = "maest"
        model_name = "fresh-maest"
        dim = 3
        device = "cpu"

        def __init__(self, device: str = "auto", inference_batch_size: int = 4) -> None:
            self.device = device
            self.inference_batch_size = inference_batch_size
            self._genres_by_path: dict[str, list[dict[str, object]]] = {}

        def embed(self, path: str) -> np.ndarray:
            return self.embed_batch([path])[0]

        def embed_batch(self, paths: list[str]) -> list[np.ndarray]:
            self._genres_by_path = {
                str(path): [{"label": "Fresh Breaks", "score": 0.99}, {"label": "Jungle", "score": 0.88}]
                for path in paths
            }
            return [np.asarray([1, 0, 0], dtype=np.float32) for _path in paths]

        def genres_for_path(self, path: str) -> list[dict[str, object]] | None:
            return self._genres_by_path.get(str(path))

    manager = LabMaestAnalysisJobManager(lab.library, {"maest": FakeMaestEmbeddingAdapter})
    status = manager.run_sync(adapter_name="maest", device="cpu", batch_size=1)

    assert status.state == "completed"
    assert status.analyzed == 1
    track = lab.library.get_track(track_id)
    assert track.genres == ["Fresh Breaks", "Jungle"]
    assert track.genre_scores == {"Fresh Breaks": 0.99, "Jungle": 0.88}
    assert track.metadata["maest_model"] == "fresh-maest"
    assert track.metadata["maest_syncopated_rhythm"] is True
    _tracks, matrix = lab.library.load_embedding_matrix("maest")
    assert matrix.shape == (1, 3)


def test_maest_embedding_adapter_averages_model_embeddings(monkeypatch, tmp_path: Path) -> None:
    import torch

    import rhythm_lab.maest_embeddings as maest_embeddings

    class FakeModel:
        labels = ["Breakbeat", "House"]

        def to(self, _device: str):
            return self

        def eval(self):
            return self

        def __call__(self, audio, *, melspectrogram_input=False):
            logits = torch.tensor([[0.0, 2.0]], dtype=torch.float32).repeat(audio.shape[0], 1)
            embeddings = torch.arange(audio.shape[0] * 4, dtype=torch.float32).reshape(audio.shape[0], 4)
            return logits, embeddings

    class FakeTorchAudio:
        class transforms:
            class Resample:
                def __init__(self, *_args, **_kwargs) -> None:
                    pass

                def __call__(self, audio):
                    return audio

    def fake_load_model(self: MaestEmbeddingAdapter) -> None:
        self._torch = torch
        self._torchaudio = FakeTorchAudio()
        self.device = "cpu"
        self._model = FakeModel()

    def fake_load_audio(_path, *, torchaudio_module=None, target_sample_rate=None):
        return np.ones(16000 * 120, dtype=np.float32), 16000, "fake"

    monkeypatch.setattr(MaestEmbeddingAdapter, "_load_model", fake_load_model)
    monkeypatch.setattr(maest_embeddings, "load_audio_mono", fake_load_audio)

    adapter = MaestEmbeddingAdapter(device="cpu")
    path = tmp_path / "track.wav"
    vector = adapter.embed(path)

    assert vector.shape == (4,)
    assert vector.tolist() == [4.0, 5.0, 6.0, 7.0]
    assert adapter.genres_for_path(path) == [
        {"label": "House", "score": float(torch.sigmoid(torch.tensor(2.0)))},
        {"label": "Breakbeat", "score": 0.5},
    ]


def test_train_feature_set_saves_reloadable_artifact(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    matrix = np.asarray(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [1.0, 1.0],
            [0.9, 1.0],
            [0.2, 0.1],
            [0.8, 0.9],
        ],
        dtype=np.float32,
    )
    labels = [
        "broken",
        "broken",
        "straight",
        "straight",
        "broken",
        "straight",
    ]

    result = train_feature_set(
        matrix,
        labels,
        feature_names=["a", "b"],
        feature_set="synthetic",
        artifact_dir=artifact_dir,
        random_state=7,
    )

    assert result.artifact_path.exists()
    assert result.metrics_path.exists()
    payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    assert payload["feature_set"] == "synthetic"
    assert payload["label_order"] == ["broken", "straight"]

    import joblib

    saved = joblib.load(result.artifact_path)
    assert saved["feature_set"] == "synthetic"
    np.testing.assert_array_equal(saved["model"].predict(matrix), result.model.predict(matrix))


def test_web_app_lists_tracks_and_updates_labels(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    track_id = _track(lab.library, tmp_path, "broken.wav", title="Broken")
    straight_id = _track(lab.library, tmp_path, "straight.wav", title="Straight")
    lab.library.save_genres(track_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    lab.library.save_sonara_features(track_id, {"onset_density": {"type": "float", "value": 4.2}}, model_name="sonara-test")
    client = TestClient(create_app(lab.path))

    tracks = client.get("/api/tracks").json()
    assert tracks["total"] == 2
    assert tracks["items"][0]["id"] == track_id
    assert tracks["items"][0]["label"] is None
    assert tracks["items"][0]["maest_syncopated_rhythm"] is True
    assert tracks["items"][0]["feature_status"]["maest"] is False
    assert tracks["items"][0]["feature_status"]["sonara"] is True
    assert tracks["items"][0]["genres"] == ["Breakbeat"]
    straight_track = next(item for item in tracks["items"] if item["id"] == straight_id)
    assert straight_track["maest_syncopated_rhythm"] is False
    syncopated_tracks = client.get("/api/tracks", params={"syncopated": "yes"}).json()
    non_syncopated_tracks = client.get("/api/tracks", params={"syncopated": "no"}).json()
    assert syncopated_tracks["total"] == 1
    assert syncopated_tracks["items"][0]["id"] == track_id
    assert non_syncopated_tracks["total"] == 1
    assert non_syncopated_tracks["items"][0]["id"] == straight_id
    lab.library.save_embedding(track_id, np.asarray([1, 0, 0], dtype=np.float32), "maest-test", embedding_key="maest")
    tracks_with_embedding = client.get("/api/tracks").json()
    assert tracks_with_embedding["items"][0]["feature_status"]["maest"] is True
    html = client.get("/").text
    assert html.index('id="syncopated"') < html.index('id="label"')
    assert '<option value="yes">syncopated rhythm</option>' in html
    assert '<option value="no">no syncopated rhythm</option>' in html
    assert 'syncopatedEl.addEventListener("change"' in html
    assert "syncopated: syncopatedEl.value" in html
    assert '<div class="meta track-path">${escapeHtml(track.path)}</div>' in html
    assert '<div class="meta feature-line">SONARA ${mark(track.feature_status.sonara)} · MERT ${mark(track.feature_status.mert)} · MAEST ${mark(track.feature_status.maest)} · label <b>${track.label || "none"}</b></div>' in html
    assert '<div class="genres-line"><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span></div>' in html
    assert "${badgeRow(track)}" in html
    assert "syncopated-badge" in html
    assert "syncopated rhythm" in html
    assert 'track.maest_syncopated_rhythm === true' in html
    assert "function badgeRow(track)" in html
    assert "MAEST ${mark(track.feature_status.maest)}" in html
    assert "MAEST emb" not in html
    assert "formatLabelCounts" in html
    assert "JSON.stringify(data.labels)" not in html
    assert "rhythm-label-badge" in html
    assert "rhythmLabelBadge" in html
    assert "genres-line" in html

    response = client.post(f"/api/tracks/{track_id}/label", json={"label": "broken"})

    assert response.status_code == 200
    assert response.json()["label"] == "broken"
    assert lab.label_for_track(track_id).label == "broken"


def test_web_app_paginates_tracks(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    for index in range(3):
        _track(lab.library, tmp_path, f"track-{index}.wav", title=f"Track {index}")
    client = TestClient(create_app(lab.path))

    first_page = client.get("/api/tracks", params={"limit": 2, "offset": 0}).json()
    second_page = client.get("/api/tracks", params={"limit": 2, "offset": 2}).json()
    html = client.get("/").text

    assert first_page["total"] == 3
    assert [item["title"] for item in first_page["items"]] == ["Track 0", "Track 1"]
    assert [item["title"] for item in second_page["items"]] == ["Track 2"]
    assert 'id="prevPage"' in html
    assert 'id="nextPage"' in html
    assert 'id="pageSize"' in html
    assert 'id="pageInfo"' in html
    assert "track.rowNumber" in html


def test_web_app_transcodes_aiff_media_to_wav(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    import rhythm_lab.web_app as web_app

    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    track_id = _track(lab.library, tmp_path, "preview.aif", title="Preview")
    calls: list[list[str]] = []

    class FakeStdout:
        def __init__(self) -> None:
            self._chunks = [b"RIFF....WAVE", b""]

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self, command: list[str], **_kwargs: object) -> None:
            calls.append(command)
            self.stdout = FakeStdout()

        def wait(self) -> int:
            return 0

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            raise AssertionError("completed transcode should not be killed")

    monkeypatch.setattr(web_app, "require_ffmpeg", lambda: "ffmpeg-test", raising=False)
    monkeypatch.setattr(web_app, "subprocess", SimpleNamespace(Popen=FakeProcess, PIPE=-1, DEVNULL=-3), raising=False)

    response = TestClient(create_app(lab.path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF....WAVE"
    assert calls == [[
        "ffmpeg-test",
        "-v",
        "error",
        "-i",
        str(tmp_path / "preview.aif"),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
        "pcm_s16le",
        "pipe:1",
    ]]


def test_cli_import_subset_command_creates_lab_database(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken_id = _track(source, tmp_path, "broken.wav", title="Broken")
    _track(source, tmp_path, "straight.wav", title="Straight")
    source.save_genres(broken_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    lab_path = tmp_path / "rhythm_lab.sqlite"

    result = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "import-subset",
            "--source",
            str(source_path),
            "--db",
            str(lab_path),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "imported=1" in result.stdout
    assert len(RhythmLabDatabase(lab_path).library.list_tracks()) == 1


def test_cli_import_non_sync_sample_command_adds_requested_non_sync_tracks(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite"
    source = LibraryDatabase(source_path)
    broken_id = _track(source, tmp_path, "broken.wav", title="Broken")
    _track(source, tmp_path, "straight.wav", title="Straight")
    source.save_genres(broken_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    lab_path = tmp_path / "rhythm_lab.sqlite"

    result = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "import-non-sync-sample",
            "--source",
            str(source_path),
            "--db",
            str(lab_path),
            "--count",
            "1",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    lab = RhythmLabDatabase(lab_path)
    tracks = lab.library.list_tracks()
    assert result.returncode == 0, result.stderr
    assert "requested=1" in result.stdout
    assert "imported=1" in result.stdout
    assert len(tracks) == 1
    assert tracks[0].metadata.get("maest_syncopated_rhythm") is not True


def test_cli_formats_single_line_analysis_progress() -> None:
    from types import SimpleNamespace

    from rhythm_lab.cli import _format_analysis_progress

    status = SimpleNamespace(
        adapter_name="mert",
        state="running",
        total=100,
        processed=25,
        analyzed=24,
        failed=1,
        avg_seconds_per_track=2.0,
        current_path=r"C:\Music\track.wav",
    )

    assert (
        _format_analysis_progress(status, bar_width=10)
        == "mert running [##--------] 25/100 25.0% analyzed=24 failed=1 avg=2.0s current=track.wav"
    )


def test_cli_analyze_mert_prints_progress_for_empty_lab_database(tmp_path: Path) -> None:
    lab_path = tmp_path / "rhythm_lab.sqlite"
    RhythmLabDatabase(lab_path)

    result = subprocess.run(
        [
            sys.executable,
            str(LAB_ROOT / "rhythm_lab_cli.py"),
            "analyze-mert",
            "--db",
            str(lab_path),
            "--device",
            "cpu",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "mert completed [########################] 0/0 100.0%" in result.stderr
    assert "state=completed total=0 processed=0 analyzed=0 failed=0" in result.stdout


def test_apply_model_to_lab_saves_predictions_and_exports_csv(tmp_path: Path) -> None:
    lab = RhythmLabDatabase(tmp_path / "rhythm_lab.sqlite")
    tracks = [_track(lab.library, tmp_path, f"track-{index}.wav", title=f"Track {index}") for index in range(6)]
    for index, track_id in enumerate(tracks):
        lab.library.save_sonara_features(
            track_id,
            {
                "onset_density": {"type": "float", "value": float(index)},
                "mfcc_mean": {"type": "list", "value": [float(index)] * 13},
                "chroma_mean": {"type": "list", "value": [float(index)] * 12},
            },
            model_name="sonara-test",
        )
        label = "broken" if index < 3 else "straight"
        lab.set_label(track_id, label)
    from rhythm_lab.features import build_labeled_feature_matrix

    features = build_labeled_feature_matrix(lab.path, "sonara")
    trained = train_feature_set(
        features.matrix,
        features.labels,
        feature_names=features.feature_names,
        feature_set="sonara",
        artifact_dir=tmp_path / "artifacts",
    )

    summary = apply_model_to_lab(lab.path, trained.artifact_path)
    csv_path = export_predictions_csv(lab.path, tmp_path / "predictions.csv")

    assert summary["predicted"] == 6
    assert len(lab.predictions()) == 6
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].startswith("track_id,")


def _track(db: LibraryDatabase, tmp_path: Path, name: str, *, title: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": title})

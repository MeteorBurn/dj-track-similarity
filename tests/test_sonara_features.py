from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import SONARA_ANALYSIS_SIGNATURE_KEY, sonara_analysis_signature_errors
from dj_track_similarity.sonara_features import analyze_and_store_sonara_batch


class TrackAnalysis(dict):
    @property
    def failed(self):
        return "error" in self


class FullFakeSonara:
    __version__ = "0.2.9"
    calls = []

    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        return [TrackAnalysis(
            path=path,
            bpm=126.4,
            bpm_raw=126.4,
            bpm_confidence=0.88,
            energy=0.74,
            duration_sec=180.0,
            key="A minor",
            key_camelot="8A",
            mfcc_mean=np.arange(13, dtype=np.float32),
            energy_curve=np.asarray([0.2, 0.5, 0.8], dtype=np.float32),
            beats=np.asarray([0.0, 0.5, 1.0], dtype=np.float32),
            segments=[{"label": "intro", "start": 0.0, "end": 16.0}],
            embedding=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
            fingerprint="AAAAAA==",
            embedding_version="1",
            fingerprint_version="1",
            provenance={
                "schema_version": 4,
                "sample_rate": 22050,
                "mode": "playlist",
                "requested_features": kwargs["features"],
            },
        ) for path in paths]


def _track(db: LibraryDatabase, tmp_path: Path, name: str = "track.wav"):
    path = tmp_path / name
    path.write_bytes(b"audio")
    track_id = db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": name})
    return db.get_track(track_id)


def test_default_native_analysis_writes_only_core_with_current_signature(tmp_path: Path) -> None:
    FullFakeSonara.calls.clear()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track = _track(db, tmp_path)

    result = analyze_and_store_sonara_batch(db, [track], sonara_module=FullFakeSonara)

    assert result[0].error is None
    call = FullFakeSonara.calls[-1]
    assert "vocalness" in call["features"]
    assert "embedding" not in call["features"]
    assert call["vocalness_model"] == "bundled"
    stored = db.get_track(track.id)
    assert stored.analyses == ["sonara"]
    assert stored.bpm == 126.4
    assert db.load_sonara_timeline(track.id) is None
    assert db.embedding_vector(track.id, "sonara") is None
    signature = stored.metadata[SONARA_ANALYSIS_SIGNATURE_KEY]
    assert signature["project_feature_revision"] == 4
    assert signature["decoder_backend"] == "sonara-symphonia"
    assert signature["execution_path"] == "analyze_batch"
    assert sonara_analysis_signature_errors(signature) == ()


def test_all_outputs_are_split_across_core_timeline_and_representations(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track = _track(db, tmp_path)

    result = analyze_and_store_sonara_batch(
        db,
        [track],
        sonara_module=FullFakeSonara,
        outputs=["core", "timeline", "representations"],
    )

    assert result[0].error is None
    stored = db.get_track(track.id)
    assert "energy_curve_summary" in stored.metadata["sonara_features"]
    assert "beats" not in stored.metadata["sonara_features"]
    assert db.load_sonara_timeline(track.id)["beats"]["value"] == [0.0, 0.5, 1.0]
    assert np.allclose(db.embedding_vector(track.id, "sonara"), [0.1, 0.2, 0.3])
    assert stored.timeline_fields
    assert stored.representation_fields


def test_timeline_and_representations_can_resume_without_rewriting_core(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track = _track(db, tmp_path)
    analyze_and_store_sonara_batch(db, [track], sonara_module=FullFakeSonara, outputs=["core"])
    core_signature = db.get_track(track.id).metadata[SONARA_ANALYSIS_SIGNATURE_KEY]

    result = analyze_and_store_sonara_batch(
        db,
        [db.get_track(track.id)],
        sonara_module=FullFakeSonara,
        outputs=["timeline", "representations"],
    )

    assert result[0].error is None
    assert db.get_track(track.id).metadata[SONARA_ANALYSIS_SIGNATURE_KEY] == core_signature
    assert db.load_sonara_timeline(track.id) is not None
    assert db.embedding_vector(track.id, "sonara") is not None


def test_sonara_reset_clears_all_outputs_and_dependent_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track = _track(db, tmp_path)
    analyze_and_store_sonara_batch(
        db,
        [track],
        sonara_module=FullFakeSonara,
        outputs=["core", "timeline", "representations"],
    )
    db.save_classifier_score(
        track.id,
        classifier="sonara_classifier",
        score=0.8,
        label="positive",
        confidence=0.8,
        probabilities={"positive": 0.8},
        feature_set="sonara+maest",
        model_id="old",
    )

    result = db.reset_analysis("sonara")

    assert result["classifier_scores_deleted"] == 1
    assert db.get_track(track.id).metadata.get("sonara_features") is None
    assert db.load_sonara_timeline(track.id) is None
    assert db.embedding_vector(track.id, "sonara") is None
    assert db.classifier_score(track.id, "sonara_classifier") is None

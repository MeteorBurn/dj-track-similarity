from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import SONARA_ANALYSIS_SIGNATURE_KEY
from dj_track_similarity.sonara_features import analyze_and_store_sonara_batch


class FakeTrackAnalysis(dict):
    @property
    def failed(self) -> bool:
        return "error" in self


class FakeSonara:
    __version__ = "0.2.9"
    calls: list[dict[str, object]] = []

    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        results = []
        for path in paths:
            if Path(path).name == "bad.wav":
                results.append(FakeTrackAnalysis(path=path, error="unsupported codec", error_kind="decode"))
                continue
            results.append(FakeTrackAnalysis(
                path=path,
                bpm=128.0,
                energy=0.7,
                duration_sec=60.0,
                beats=np.asarray([0.0, 0.5], dtype=np.float32),
                embedding=np.asarray([0.1, 0.2], dtype=np.float32),
                fingerprint="AAAAAA==",
                provenance={
                    "schema_version": 4,
                    "sample_rate": 22050,
                    "mode": "playlist",
                    "requested_features": kwargs["features"],
                },
            ))
        return results


def _track(db: LibraryDatabase, tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_bytes(b"audio")
    track_id = db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={})
    return db.get_track(track_id)


def test_native_batch_passes_exact_contract_and_maps_results_by_input_order(tmp_path: Path) -> None:
    FakeSonara.calls.clear()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    tracks = [_track(db, tmp_path, name) for name in ("first.wav", "bad.wav", "third.wav")]
    progress: list[tuple[int, int]] = []

    results = analyze_and_store_sonara_batch(
        db,
        tracks,
        sonara_module=FakeSonara,
        outputs=["core", "timeline", "representations"],
        progress=lambda done, total: progress.append((done, total)),
    )

    call = FakeSonara.calls[-1]
    assert call["paths"] == [track.path for track in tracks]
    assert call["sr"] == 22050
    assert call["mode"] == "playlist"
    assert (call["bpm_min"], call["bpm_max"]) == (70, 180)
    assert call["vocalness_model"] == "bundled"
    assert set(call["features"]) >= {"bpm", "beats", "embedding", "fingerprint", "vocalness"}
    assert [result.track.id for result in results] == [track.id for track in tracks]
    assert results[0].error is None
    assert "unsupported codec" in str(results[1].error)
    assert results[2].error is None

    stored = db.get_track(tracks[0].id)
    signature = stored.metadata[SONARA_ANALYSIS_SIGNATURE_KEY]
    assert signature["decoder_backend"] == "sonara-symphonia"
    assert signature["execution_path"] == "analyze_batch"
    assert stored.metadata["sonara_provenance"]["decoder_backend"] == "sonara-symphonia"
    assert db.load_sonara_timeline(tracks[0].id) is not None
    assert db.embedding_vector(tracks[0].id, "sonara") is not None
    assert db.get_track(tracks[1].id).metadata.get("sonara_features") is None

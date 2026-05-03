from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.tags import build_tag_preview


def test_tag_preview_reports_custom_tags_without_touching_audio_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    before = audio_path.read_bytes()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=len(before),
        mtime=audio_path.stat().st_mtime,
        metadata={"artist": "A", "title": "T"},
        bpm=128,
        musical_key="8A",
        energy=0.73,
    )

    preview = build_tag_preview(db, [track_id])

    assert audio_path.read_bytes() == before
    assert preview[0].track_id == track_id
    assert preview[0].path == audio_path.as_posix()
    assert preview[0].tags == {
        "DJ_SIM_BPM": "128.0",
        "DJ_SIM_KEY": "8A",
        "DJ_SIM_ENERGY": "0.730",
    }

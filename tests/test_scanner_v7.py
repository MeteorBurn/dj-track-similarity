"""Tests for the v7 scanner write path.

Run with:
    python -m pytest tests/test_scanner_v7.py --override-ini addopts= -q

No conftest.py; each test constructs its own temp SQLite + synthetic WAV.
"""

from __future__ import annotations

import json
import sqlite3
import wave
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import TALB, TBPM, TIT2, TCON, TKEY, TPE1

from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.db_tracks import upsert_track_v7
from dj_track_similarity.scanner import scan_library_v7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_v7(tmp_path: Path) -> sqlite3.Connection:
    """Return an open connection to a fresh v7 in-memory-backed DB on disk."""
    db_path = tmp_path / "library_v7.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_v7_schema(conn)
    return conn


def _make_tagged_wav(path: Path, *, artist: str, title: str, album: str, bpm: float, key: str, genres: list[str]) -> None:
    """Write a minimal valid WAV file and attach ID3 tags via Mutagen."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        # 0.1 s of silence
        handle.writeframes(b"\x00\x00" * 4_410)

    audio = MutagenFile(path)
    audio.add_tags()
    audio.tags.add(TPE1(encoding=3, text=[artist]))
    audio.tags.add(TIT2(encoding=3, text=[title]))
    audio.tags.add(TALB(encoding=3, text=[album]))
    audio.tags.add(TBPM(encoding=3, text=[str(bpm)]))
    audio.tags.add(TKEY(encoding=3, text=[key]))
    if genres:
        audio.tags.add(TCON(encoding=3, text=[genres[0]]))
    audio.save()


# ---------------------------------------------------------------------------
# Primary acceptance test (Todo 14)
# ---------------------------------------------------------------------------

def test_scan_populates_tracks_and_file_tags(tmp_path: Path) -> None:
    """scan_library_v7 writes both tracks and file_tags rows for each audio file."""
    music_root = tmp_path / "music"
    music_root.mkdir()

    _make_tagged_wav(
        music_root / "track_a.wav",
        artist="Artist A",
        title="Track A",
        album="Album One",
        bpm=128.0,
        key="8A",
        genres=["Techno"],
    )
    _make_tagged_wav(
        music_root / "track_b.wav",
        artist="Artist B",
        title="Track B",
        album="Album Two",
        bpm=140.0,
        key="5B",
        genres=["House", "Deep House"],
    )

    conn = _open_v7(tmp_path)

    stats = scan_library_v7(music_root, conn)

    # --- ScanStats ---
    assert stats.added == 2
    assert stats.updated == 0
    assert stats.unchanged == 0

    # --- tracks table ---
    track_count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    assert track_count == 2

    null_mtime_count = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE file_modified_ns IS NULL"
    ).fetchone()[0]
    assert null_mtime_count == 0

    positive_mtime_count = conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE file_modified_ns > 0"
    ).fetchone()[0]
    assert positive_mtime_count == 2

    # --- file_tags table ---
    tag_count = conn.execute("SELECT COUNT(*) FROM file_tags").fetchone()[0]
    assert tag_count == 2

    # genres_json must be a valid JSON array for every row
    for row in conn.execute("SELECT genres_json FROM file_tags").fetchall():
        parsed = json.loads(row["genres_json"])
        assert isinstance(parsed, list)

    # BPM values must be stored
    bpm_rows = conn.execute(
        "SELECT tag_bpm FROM file_tags WHERE tag_bpm IS NOT NULL ORDER BY tag_bpm"
    ).fetchall()
    assert len(bpm_rows) == 2
    bpm_values = [float(r["tag_bpm"]) for r in bpm_rows]
    assert bpm_values == [128.0, 140.0]

    # content_generation = 1 for all new tracks
    gen_rows = conn.execute("SELECT content_generation FROM tracks").fetchall()
    assert all(int(r["content_generation"]) == 1 for r in gen_rows)

    # artist / title / album round-trip
    tag_rows = {
        r["artist"]: r
        for r in conn.execute(
            "SELECT ft.artist, ft.title, ft.album, ft.tag_key, ft.genres_json "
            "FROM file_tags ft"
        ).fetchall()
    }
    assert "Artist A" in tag_rows
    assert tag_rows["Artist A"]["title"] == "Track A"
    assert tag_rows["Artist A"]["album"] == "Album One"
    assert tag_rows["Artist A"]["tag_key"] == "8A"
    assert json.loads(tag_rows["Artist A"]["genres_json"]) == ["Techno"]

    assert "Artist B" in tag_rows
    assert tag_rows["Artist B"]["title"] == "Track B"
    # TCON stores only the first genre string in ID3; the scanner reads it as-is
    genres_b = json.loads(tag_rows["Artist B"]["genres_json"])
    assert isinstance(genres_b, list)
    assert len(genres_b) >= 1
    assert "House" in genres_b[0] or genres_b[0] == "House"

    conn.close()


def test_scan_unchanged_files_are_skipped(tmp_path: Path) -> None:
    """Second scan of unchanged files increments unchanged counter, not added."""
    music_root = tmp_path / "music"
    music_root.mkdir()
    _make_tagged_wav(
        music_root / "track.wav",
        artist="DJ Test",
        title="Stable Track",
        album="Stable Album",
        bpm=130.0,
        key="1A",
        genres=["Minimal"],
    )

    conn = _open_v7(tmp_path)

    first = scan_library_v7(music_root, conn)
    second = scan_library_v7(music_root, conn)

    assert first.added == 1
    assert first.unchanged == 0
    assert second.added == 0
    assert second.unchanged == 1

    track_count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    assert track_count == 1

    conn.close()


def test_scan_changed_file_increments_content_generation(tmp_path: Path) -> None:
    """When a file's size or mtime changes, content_generation is incremented."""
    music_root = tmp_path / "music"
    music_root.mkdir()
    wav_path = music_root / "evolving.wav"
    _make_tagged_wav(
        wav_path,
        artist="DJ Evolve",
        title="Evolving Track",
        album="Change Album",
        bpm=125.0,
        key="2A",
        genres=["Techno"],
    )

    conn = _open_v7(tmp_path)
    scan_library_v7(music_root, conn)

    gen_before = conn.execute("SELECT content_generation FROM tracks").fetchone()["content_generation"]
    assert int(gen_before) == 1

    # Simulate file content change by appending bytes (changes size + mtime)
    with open(wav_path, "ab") as fh:
        fh.write(b"\x00" * 16)

    scan_library_v7(music_root, conn)

    gen_after = conn.execute("SELECT content_generation FROM tracks").fetchone()["content_generation"]
    assert int(gen_after) == 2

    conn.close()


def test_upsert_track_v7_new_track_has_content_generation_1(tmp_path: Path) -> None:
    """upsert_track_v7 sets content_generation=1 for brand-new tracks."""
    conn = _open_v7(tmp_path)

    track_id = upsert_track_v7(
        conn,
        file_path="/music/test.wav",
        file_size_bytes=1024,
        file_modified_ns=1_700_000_000_000_000_000,
        title="Test Track",
        artist="Test Artist",
        tag_bpm=128.0,
        genres_json='["Techno"]',
    )

    row = conn.execute("SELECT content_generation FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    assert int(row["content_generation"]) == 1

    tag_row = conn.execute("SELECT tag_bpm, genres_json FROM file_tags WHERE track_id = ?", (track_id,)).fetchone()
    assert float(tag_row["tag_bpm"]) == 128.0
    assert json.loads(tag_row["genres_json"]) == ["Techno"]

    conn.close()


def test_upsert_track_v7_content_change_deletes_analysis_rows(tmp_path: Path) -> None:
    """BUG-C3: changing file_size_bytes deletes sonara/maest_scores/classifier_scores."""
    conn = _open_v7(tmp_path)

    track_id = upsert_track_v7(
        conn,
        file_path="/music/changing.wav",
        file_size_bytes=1000,
        file_modified_ns=1_000_000_000,
        title="Changing Track",
        artist="Artist",
        genres_json="[]",
    )

    # Manually insert a contracts row so we can insert a sonara row
    conn.execute(
        """
        INSERT INTO contracts (
            contract_hash, analysis_family, output_kind, model_name,
            release_hash, canonical_payload_json, created_at
        ) VALUES ('hash1', 'sonara', 'core', 'sonara-test', 'rel1', '{}', '2024-01-01T00:00:00Z')
        """
    )
    conn.execute(
        """
        INSERT INTO sonara (
            track_id, content_generation, contract_hash,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, 'hash1', ?, ?, ?, '2024-01-01T00:00:00Z')
        """,
        (track_id, b"\x00" * 52, b"\x00" * 48, b"\x00" * 28),
    )
    conn.commit()

    sonara_before = conn.execute("SELECT COUNT(*) FROM sonara WHERE track_id = ?", (track_id,)).fetchone()[0]
    assert sonara_before == 1

    # Update with changed file size → content_generation increments, sonara deleted
    upsert_track_v7(
        conn,
        file_path="/music/changing.wav",
        file_size_bytes=2000,  # changed
        file_modified_ns=1_000_000_000,
        title="Changing Track",
        artist="Artist",
        genres_json="[]",
    )

    gen = conn.execute("SELECT content_generation FROM tracks WHERE track_id = ?", (track_id,)).fetchone()["content_generation"]
    assert int(gen) == 2

    sonara_after = conn.execute("SELECT COUNT(*) FROM sonara WHERE track_id = ?", (track_id,)).fetchone()[0]
    assert sonara_after == 0

    conn.close()

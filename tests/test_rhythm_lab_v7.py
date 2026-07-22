"""Tests for v7 read-path integration in Rhythm Lab source data.

Todo 22 (Wave 4) — binds by catalog_uuid + track_uuid + content_generation.

Test conventions:
- No conftest.py; each test builds its own in-memory SQLite.
- Minimal DDL — only the columns exercised by the three new functions.
- Run: python -m pytest tests/test_rhythm_lab_v7.py --override-ini addopts= -q
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the rhythm_lab package importable when running from the repo root.
_RHYTHM_LAB_ROOT = Path(__file__).resolve().parents[1] / "tools" / "rhythm-lab"
if str(_RHYTHM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_RHYTHM_LAB_ROOT))

import sqlite3

import pytest

from dj_track_similarity.rhythm_lab_launcher import read_v7_catalog_uuid
from dj_track_similarity.rhythm_lab_collections import resolve_v7_track_by_uuid
from rhythm_lab.source_db import iter_v7_labelable_tracks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_DDL = """
CREATE TABLE library_catalog (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE tracks (
    track_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    track_uuid         TEXT    NOT NULL UNIQUE,
    file_path          TEXT    NOT NULL UNIQUE,
    file_size_bytes    INTEGER NOT NULL DEFAULT 0,
    file_modified_ns   INTEGER NOT NULL DEFAULT 0,
    content_generation INTEGER NOT NULL DEFAULT 1,
    last_scanned_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE file_tags (
    track_id   INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    title      TEXT,
    artist     TEXT,
    album      TEXT,
    tag_bpm    REAL,
    tag_key    TEXT,
    tags_read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sonara (
    track_id           INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    content_generation INTEGER NOT NULL DEFAULT 1,
    contract_hash      TEXT    NOT NULL DEFAULT 'dummy-hash',
    mfcc_mean_blob              BLOB NOT NULL DEFAULT X'',
    chroma_mean_blob            BLOB NOT NULL DEFAULT X'',
    spectral_contrast_mean_blob BLOB NOT NULL DEFAULT X'',
    analyzed_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_v7_conn() -> sqlite3.Connection:
    """Return an in-memory v7 Core connection with minimal schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_MINIMAL_DDL)
    return conn


def _insert_catalog(conn: sqlite3.Connection, catalog_uuid: str) -> None:
    conn.execute(
        "INSERT INTO library_catalog(singleton_id, catalog_uuid, created_at, updated_at) "
        "VALUES (1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (catalog_uuid,),
    )
    conn.commit()


def _insert_track(
    conn: sqlite3.Connection,
    *,
    track_uuid: str,
    file_path: str,
    content_generation: int = 1,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    tag_bpm: float | None = None,
    tag_key: str | None = None,
    with_sonara: bool = False,
) -> int:
    cur = conn.execute(
        "INSERT INTO tracks(track_uuid, file_path, content_generation) VALUES (?, ?, ?)",
        (track_uuid, file_path, content_generation),
    )
    track_id = cur.lastrowid
    assert track_id is not None
    conn.execute(
        "INSERT INTO file_tags(track_id, artist, title, album, tag_bpm, tag_key) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (track_id, artist, title, album, tag_bpm, tag_key),
    )
    if with_sonara:
        conn.execute(
            "INSERT INTO sonara(track_id, content_generation) VALUES (?, ?)",
            (track_id, content_generation),
        )
    conn.commit()
    return track_id


# ---------------------------------------------------------------------------
# test_v7_catalog_binding
# ---------------------------------------------------------------------------


def test_v7_catalog_binding() -> None:
    """read_v7_catalog_uuid returns the UUID; iter_v7_labelable_tracks yields
    only tracks that have a sonara row."""
    conn = _make_v7_conn()
    _insert_catalog(conn, "test-catalog-uuid")

    # Track 1 — has SONARA
    _insert_track(
        conn,
        track_uuid="uuid-1",
        file_path="/music/track1.flac",
        content_generation=1,
        artist="Artist A",
        title="Track One",
        tag_bpm=128.0,
        with_sonara=True,
    )
    # Track 2 — has SONARA
    _insert_track(
        conn,
        track_uuid="uuid-2",
        file_path="/music/track2.flac",
        content_generation=1,
        artist="Artist B",
        title="Track Two",
        tag_bpm=140.0,
        with_sonara=True,
    )
    # Track 3 — no SONARA (should be excluded)
    _insert_track(
        conn,
        track_uuid="uuid-3",
        file_path="/music/track3.flac",
        content_generation=1,
        artist="Artist C",
        title="Track Three",
        with_sonara=False,
    )

    # read_v7_catalog_uuid
    result_uuid = read_v7_catalog_uuid(conn)
    assert result_uuid == "test-catalog-uuid"

    # iter_v7_labelable_tracks — only 2 tracks with SONARA
    labelable = list(iter_v7_labelable_tracks(conn, "test-catalog-uuid"))
    assert len(labelable) == 2

    uuids = {d["track_uuid"] for d in labelable}
    assert uuids == {"uuid-1", "uuid-2"}

    # Each dict has the required keys
    required_keys = {
        "track_id", "track_uuid", "content_generation",
        "file_path", "artist", "title", "album", "tag_bpm", "tag_key",
    }
    for item in labelable:
        assert required_keys == set(item.keys()), f"Missing keys in {item}"

    # Spot-check values
    by_uuid = {d["track_uuid"]: d for d in labelable}
    assert by_uuid["uuid-1"]["tag_bpm"] == pytest.approx(128.0)
    assert by_uuid["uuid-2"]["artist"] == "Artist B"


# ---------------------------------------------------------------------------
# test_v7_track_resolution_by_uuid
# ---------------------------------------------------------------------------


def test_v7_track_resolution_by_uuid() -> None:
    """resolve_v7_track_by_uuid returns dict on match, None on mismatch/missing."""
    conn = _make_v7_conn()
    _insert_catalog(conn, "cat-uuid")

    track_id = _insert_track(
        conn,
        track_uuid="abc",
        file_path="/music/abc.flac",
        content_generation=1,
    )

    # Exact match
    result = resolve_v7_track_by_uuid(conn, "abc", 1)
    assert result is not None
    assert result["track_id"] == track_id
    assert result["track_uuid"] == "abc"
    assert result["content_generation"] == 1
    assert result["file_path"] == "/music/abc.flac"

    # Generation mismatch → stale label → None
    stale = resolve_v7_track_by_uuid(conn, "abc", 2)
    assert stale is None

    # Unknown UUID → None
    missing = resolve_v7_track_by_uuid(conn, "xyz", 1)
    assert missing is None


# ---------------------------------------------------------------------------
# test_v7_catalog_mismatch_raises
# ---------------------------------------------------------------------------


def test_v7_catalog_mismatch_raises() -> None:
    """iter_v7_labelable_tracks raises ValueError when catalog_uuid mismatches."""
    conn = _make_v7_conn()
    _insert_catalog(conn, "real-catalog-uuid")

    with pytest.raises(ValueError, match="catalog_uuid mismatch"):
        list(iter_v7_labelable_tracks(conn, "wrong-uuid"))

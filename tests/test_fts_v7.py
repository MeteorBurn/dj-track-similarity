"""Tests for rebuild_track_search_fts_v7 (db_search_fts.py).

Verifies that the v7 FTS rebuild populates track_search_fts exclusively from
human-readable sources (tracks.file_path, file_tags.*, maest_scores.genres_json)
and never indexes numeric features, hashes, contracts, or BLOB content.

Run with:
    python -m pytest tests/test_fts_v7.py --override-ini addopts= -q

No conftest.py; each test constructs its own in-memory SQLite database.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.db_search_fts import (
    fts_match_query,
    rebuild_track_search_fts_v7,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = "2026-01-01T00:00:00.000000Z"


def _open_v7() -> sqlite3.Connection:
    """Return an in-memory connection with the v7 schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_v7_schema(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_track(
    conn: sqlite3.Connection,
    track_id: int,
    file_path: str,
    uuid: str | None = None,
) -> None:
    uuid = uuid or f"uuid-{track_id}"
    conn.execute(
        """
        INSERT INTO tracks(
            track_id, track_uuid, file_path,
            file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, 1000, 1000000, 1, ?, ?, ?)
        """,
        (track_id, uuid, file_path, _NOW, _NOW, _NOW),
    )


def _insert_file_tags(
    conn: sqlite3.Connection,
    track_id: int,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    comment: str | None = None,
    label: str | None = None,
    catalog_number: str | None = None,
    country: str | None = None,
    isrc: str | None = None,
    year: int | None = None,
    track_number: str | None = None,
    disc_number: str | None = None,
    genres: list[str] | None = None,
) -> None:
    genres_json = json.dumps(genres or [])
    conn.execute(
        """
        INSERT INTO file_tags(
            track_id, title, artist, album, comment, label,
            catalog_number, country, isrc, year, track_number, disc_number,
            genres_json, tags_read_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            track_id, title, artist, album, comment, label,
            catalog_number, country, isrc, year, track_number, disc_number,
            genres_json, _NOW,
        ),
    )


def _insert_maest_scores(
    conn: sqlite3.Connection,
    track_id: int,
    genre_objects: list[dict],
    contract_hash: str = "maest-contract-hash-001",
) -> None:
    """Insert a maest_scores row with a list of {genre_name, score} dicts."""
    # Ensure the contract exists first
    conn.execute(
        """
        INSERT OR IGNORE INTO contracts(
            contract_hash, analysis_family, output_kind, model_name,
            canonical_payload_json, created_at
        ) VALUES (?, 'maest', 'analysis', 'maest-model', '{}', ?)
        """,
        (contract_hash, _NOW),
    )
    conn.execute(
        """
        INSERT INTO maest_scores(
            track_id, content_generation, contract_hash,
            genres_json, analyzed_at
        ) VALUES (?, 1, ?, ?, ?)
        """,
        (track_id, contract_hash, json.dumps(genre_objects), _NOW),
    )


def _fts_search(conn: sqlite3.Connection, query: str) -> list[int]:
    """Return track_ids matching the FTS5 MATCH query."""
    match_expr = fts_match_query(query)
    rows = conn.execute(
        "SELECT track_id FROM track_search_fts WHERE track_search_fts MATCH ?",
        (match_expr,),
    ).fetchall()
    return [int(r["track_id"]) for r in rows]


def _fts_content_contains(conn: sqlite3.Connection, text: str) -> bool:
    """Return True if *text* appears verbatim in any FTS column content."""
    # Read all FTS rows and check each indexed column
    rows = conn.execute(
        """
        SELECT file_path, title, artist, album, comment, label,
               catalog_number, country, isrc, year, track_number,
               disc_number, file_genres, maest_genres
        FROM track_search_fts
        """
    ).fetchall()
    text_lower = text.lower()
    for row in rows:
        for col in row:
            if col and text_lower in str(col).lower():
                return True
    return False


# ---------------------------------------------------------------------------
# Core test: only human text is indexed
# ---------------------------------------------------------------------------

def test_fts_contains_only_human_text() -> None:
    """FTS contains title/artist/genres but NOT contract hashes or numeric scalars."""
    conn = _open_v7()

    # Track 1: full metadata
    _insert_track(conn, 1, "/music/techno/artist_a_track1.flac")
    _insert_file_tags(
        conn, 1,
        title="Midnight Drive",
        artist="Artist Alpha",
        album="Dark Frequencies",
        comment="Recorded live",
        label="Subterranean Records",
        catalog_number="SUB-042",
        country="DE",
        isrc="DEABC2600001",
        year=2026,
        track_number="1",
        disc_number="1",
        genres=["Techno", "Industrial"],
    )
    _insert_maest_scores(conn, 1, [
        {"genre_name": "Techno", "score": 0.91},
        {"genre_name": "Industrial Techno", "score": 0.72},
    ])

    # Track 2: house track, no maest scores
    _insert_track(conn, 2, "/music/house/artist_b_track2.mp3")
    _insert_file_tags(
        conn, 2,
        title="Sunrise Groove",
        artist="Artist Beta",
        album="Morning Sessions",
        genres=["House", "Deep House"],
    )

    # Track 3: no file_tags, no maest_scores — only file_path
    _insert_track(conn, 3, "/music/unknown/mystery_track.wav")

    conn.commit()

    count = rebuild_track_search_fts_v7(conn)
    assert count == 3, f"Expected 3 FTS rows, got {count}"

    # --- Positive assertions: human text IS searchable ---
    assert 1 in _fts_search(conn, "techno"), "Track 1 should match 'techno'"
    assert 1 in _fts_search(conn, "midnight"), "Track 1 should match 'midnight'"
    assert 1 in _fts_search(conn, "alpha"), "Track 1 should match 'alpha'"
    assert 1 in _fts_search(conn, "subterranean"), "Track 1 should match label"
    assert 1 in _fts_search(conn, "industrial"), "Track 1 should match maest genre"
    assert 2 in _fts_search(conn, "house"), "Track 2 should match 'house'"
    assert 2 in _fts_search(conn, "sunrise"), "Track 2 should match title"
    assert 3 in _fts_search(conn, "mystery"), "Track 3 should match file_path token"

    # --- Negative assertions: hashes and numeric scalars are NOT indexed ---
    # Contract hash must not appear
    assert not _fts_content_contains(conn, "maest-contract-hash-001"), (
        "Contract hash must not be indexed in FTS"
    )
    # Unique sentinel hash that would only appear if we indexed contract columns
    assert not _fts_content_contains(conn, "sha256:testhash"), (
        "Arbitrary hash sentinel must not appear in FTS"
    )
    # Numeric score values must not appear as text
    assert not _fts_content_contains(conn, "0.91"), (
        "Numeric MAEST score must not be indexed"
    )
    assert not _fts_content_contains(conn, "0.72"), (
        "Numeric MAEST score must not be indexed"
    )

    # --- Verify FTS columns are correct (no search_text blob column) ---
    col_names = {
        desc[0]
        for desc in conn.execute("SELECT * FROM track_search_fts LIMIT 0").description
    }
    expected_cols = {
        "track_id", "file_path", "title", "artist", "album", "comment",
        "label", "catalog_number", "country", "isrc", "year",
        "track_number", "disc_number", "file_genres", "maest_genres",
    }
    assert expected_cols.issubset(col_names), (
        f"FTS missing columns: {expected_cols - col_names}"
    )

    conn.close()


# ---------------------------------------------------------------------------
# Test: maest_genres update is reflected after rebuild
# ---------------------------------------------------------------------------

def test_fts_rebuild_updates_on_maest_genres_change() -> None:
    """After updating maest_scores.genres_json, rebuild reflects new genres."""
    conn = _open_v7()

    _insert_track(conn, 1, "/music/evolving_track.flac")
    _insert_file_tags(conn, 1, title="Evolving Sound", artist="DJ Change")
    _insert_maest_scores(conn, 1, [
        {"genre_name": "Footwork", "score": 0.85},
    ])
    conn.commit()

    # First rebuild — "footwork" should be searchable
    rebuild_track_search_fts_v7(conn)
    assert 1 in _fts_search(conn, "footwork"), "Initial genre 'Footwork' should be searchable"
    assert 1 not in _fts_search(conn, "drone"), "Genre 'Drone' should not yet be searchable"

    # Update maest_scores to entirely different genres
    conn.execute(
        "UPDATE maest_scores SET genres_json = ? WHERE track_id = 1",
        (json.dumps([{"genre_name": "Drone", "score": 0.90}, {"genre_name": "Noise", "score": 0.75}]),),
    )
    conn.commit()

    # Second rebuild — new genres should be searchable, old should not
    rebuild_track_search_fts_v7(conn)
    assert 1 in _fts_search(conn, "drone"), "Updated genre 'Drone' should be searchable after rebuild"
    assert 1 in _fts_search(conn, "noise"), "Updated genre 'Noise' should be searchable after rebuild"
    assert 1 not in _fts_search(conn, "footwork"), (
        "Old genre 'Footwork' should no longer match after rebuild"
    )

    conn.close()


# ---------------------------------------------------------------------------
# Test: file_genres from file_tags.genres_json
# ---------------------------------------------------------------------------

def test_fts_file_genres_are_searchable() -> None:
    """file_tags.genres_json genres are indexed in the file_genres column."""
    conn = _open_v7()

    _insert_track(conn, 1, "/music/genre_test.flac")
    _insert_file_tags(conn, 1, title="Genre Test", genres=["Progressive House", "Melodic Techno"])
    conn.commit()

    rebuild_track_search_fts_v7(conn)

    assert 1 in _fts_search(conn, "progressive"), "file genre 'Progressive House' should be searchable"
    assert 1 in _fts_search(conn, "melodic"), "file genre 'Melodic Techno' should be searchable"

    conn.close()


# ---------------------------------------------------------------------------
# Test: tracks without file_tags or maest_scores still get indexed
# ---------------------------------------------------------------------------

def test_fts_track_without_tags_indexed_by_file_path() -> None:
    """A track with no file_tags or maest_scores is still indexed via file_path."""
    conn = _open_v7()

    _insert_track(conn, 1, "/music/untagged/orphan_track_xyzzy.flac")
    conn.commit()

    count = rebuild_track_search_fts_v7(conn)
    assert count == 1

    assert 1 in _fts_search(conn, "orphan"), "file_path token 'orphan' should be searchable"
    assert 1 in _fts_search(conn, "xyzzy"), "file_path token 'xyzzy' should be searchable"

    conn.close()


# ---------------------------------------------------------------------------
# Test: year is indexed as text
# ---------------------------------------------------------------------------

def test_fts_year_indexed_as_text() -> None:
    """file_tags.year is stored as text in the FTS year column."""
    conn = _open_v7()

    _insert_track(conn, 1, "/music/year_test.flac")
    _insert_file_tags(conn, 1, title="Year Test", year=1999)
    conn.commit()

    rebuild_track_search_fts_v7(conn)

    assert _fts_content_contains(conn, "1999"), "Year 1999 should appear as text in FTS"

    conn.close()


# ---------------------------------------------------------------------------
# Test: rebuild is idempotent
# ---------------------------------------------------------------------------

def test_fts_rebuild_is_idempotent() -> None:
    """Calling rebuild twice produces the same row count without duplicates."""
    conn = _open_v7()

    for i in range(1, 4):
        _insert_track(conn, i, f"/music/track_{i}.flac")
        _insert_file_tags(conn, i, title=f"Track {i}", artist="Artist")
    conn.commit()

    count1 = rebuild_track_search_fts_v7(conn)
    count2 = rebuild_track_search_fts_v7(conn)

    assert count1 == 3, f"First rebuild: expected 3, got {count1}"
    assert count2 == 3, f"Second rebuild: expected 3 (no duplicates), got {count2}"

    conn.close()


# ---------------------------------------------------------------------------
# Test: maest genres with plain string array (tolerance)
# ---------------------------------------------------------------------------

def test_fts_maest_genres_plain_string_array() -> None:
    """maest_scores.genres_json plain string arrays are tolerated."""
    conn = _open_v7()

    _insert_track(conn, 1, "/music/plain_genres.flac")
    _insert_file_tags(conn, 1, title="Plain Genres")
    # Insert plain string array instead of object array
    conn.execute(
        """
        INSERT OR IGNORE INTO contracts(
            contract_hash, analysis_family, output_kind, model_name,
            canonical_payload_json, created_at
        ) VALUES ('plain-contract', 'maest', 'analysis', 'maest-model', '{}', ?)
        """,
        (_NOW,),
    )
    conn.execute(
        """
        INSERT INTO maest_scores(
            track_id, content_generation, contract_hash, genres_json, analyzed_at
        ) VALUES (1, 1, 'plain-contract', '["Breakbeat", "Jungle"]', ?)
        """,
        (_NOW,),
    )
    conn.commit()

    rebuild_track_search_fts_v7(conn)

    assert 1 in _fts_search(conn, "breakbeat"), "Plain string genre 'Breakbeat' should be searchable"
    assert 1 in _fts_search(conn, "jungle"), "Plain string genre 'Jungle' should be searchable"

    conn.close()

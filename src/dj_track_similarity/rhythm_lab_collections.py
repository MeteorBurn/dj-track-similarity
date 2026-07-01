from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


DEFAULT_COLLECTION_SOURCE = "manual"
COLLECTION_MODES = {"append", "replace"}


@dataclass(frozen=True)
class ReviewCollectionTrack:
    collection_id: int
    source_track_id: int
    position: int
    score: float | None
    note: str | None
    added_at: str


@dataclass(frozen=True)
class ReviewCollection:
    id: int
    name: str
    source: str
    note: str | None
    created_at: str
    updated_at: str
    track_count: int
    tracks: tuple[ReviewCollectionTrack, ...] = ()


def default_rhythm_lab_labels_path() -> Path:
    return Path(__file__).resolve().parents[2] / "tools" / "rhythm-lab" / "data" / "rhythm_lab.sqlite"


def ensure_review_collection_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS review_collections (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'manual',
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS review_collection_tracks (
            collection_id INTEGER NOT NULL,
            source_track_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            score REAL,
            note TEXT,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(collection_id, source_track_id),
            FOREIGN KEY(collection_id) REFERENCES review_collections(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_review_collection_tracks_order
        ON review_collection_tracks(collection_id, position, source_track_id);
        """
    )


class RhythmLabCollections:
    def __init__(self, labels_db_path: str | Path) -> None:
        self.path = Path(labels_db_path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            ensure_review_collection_schema(connection)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def list_collections(self) -> list[ReviewCollection]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.name, c.source, c.note, c.created_at, c.updated_at,
                       COUNT(t.source_track_id) AS track_count
                FROM review_collections c
                LEFT JOIN review_collection_tracks t ON t.collection_id = c.id
                GROUP BY c.id
                ORDER BY c.updated_at DESC, LOWER(c.name)
                """
            ).fetchall()
        return [_collection_from_row(row) for row in rows]

    def get_collection(self, collection_id: int) -> ReviewCollection:
        clean_id = _validate_collection_id(collection_id)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT c.id, c.name, c.source, c.note, c.created_at, c.updated_at,
                       COUNT(t.source_track_id) AS track_count
                FROM review_collections c
                LEFT JOIN review_collection_tracks t ON t.collection_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (clean_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Review collection not found: {clean_id}")
            tracks = _collection_tracks(connection, clean_id)
        return _collection_from_row(row, tracks=tracks)

    def collection_by_name(self, name: str) -> ReviewCollection | None:
        clean_name = _validate_collection_name(name)
        with self.connect() as connection:
            row = connection.execute("SELECT id FROM review_collections WHERE name = ?", (clean_name,)).fetchone()
        return self.get_collection(int(row["id"])) if row is not None else None

    def save_collection(
        self,
        name: str,
        track_ids: list[int] | tuple[int, ...],
        *,
        source: str = DEFAULT_COLLECTION_SOURCE,
        note: str | None = None,
        mode: str = "append",
    ) -> ReviewCollection:
        clean_mode = _validate_mode(mode)
        collection_id = self._upsert_collection(name, source=source, note=note)
        if clean_mode == "replace":
            return self.replace_tracks(collection_id, track_ids)
        return self.append_tracks(collection_id, track_ids)

    def append_tracks(self, collection_id: int, track_ids: list[int] | tuple[int, ...]) -> ReviewCollection:
        clean_id = _validate_collection_id(collection_id)
        ids = _unique_track_ids(track_ids)
        with self.connect() as connection:
            _require_collection(connection, clean_id)
            next_position = int(
                connection.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM review_collection_tracks WHERE collection_id = ?",
                    (clean_id,),
                ).fetchone()[0]
            )
            existing = {
                int(row["source_track_id"])
                for row in connection.execute(
                    "SELECT source_track_id FROM review_collection_tracks WHERE collection_id = ?",
                    (clean_id,),
                ).fetchall()
            }
            for track_id in ids:
                if track_id in existing:
                    continue
                connection.execute(
                    """
                    INSERT INTO review_collection_tracks(collection_id, source_track_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (clean_id, track_id, next_position),
                )
                next_position += 1
            connection.execute(
                "UPDATE review_collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (clean_id,),
            )
        return self.get_collection(clean_id)

    def replace_tracks(self, collection_id: int, track_ids: list[int] | tuple[int, ...]) -> ReviewCollection:
        clean_id = _validate_collection_id(collection_id)
        ids = _unique_track_ids(track_ids)
        with self.connect() as connection:
            _require_collection(connection, clean_id)
            connection.execute("DELETE FROM review_collection_tracks WHERE collection_id = ?", (clean_id,))
            for position, track_id in enumerate(ids, start=1):
                connection.execute(
                    """
                    INSERT INTO review_collection_tracks(collection_id, source_track_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (clean_id, track_id, position),
                )
            connection.execute(
                "UPDATE review_collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (clean_id,),
            )
        return self.get_collection(clean_id)

    def delete_collection(self, collection_id: int) -> bool:
        clean_id = _validate_collection_id(collection_id)
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM review_collections WHERE id = ?", (clean_id,))
        return cursor.rowcount > 0

    def _upsert_collection(self, name: str, *, source: str, note: str | None) -> int:
        clean_name = _validate_collection_name(name)
        clean_source = (source or DEFAULT_COLLECTION_SOURCE).strip() or DEFAULT_COLLECTION_SOURCE
        clean_note = note.strip() if isinstance(note, str) and note.strip() else None
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_collections(name, source, note)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    source = excluded.source,
                    note = COALESCE(excluded.note, review_collections.note),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (clean_name, clean_source, clean_note),
            )
            row = connection.execute("SELECT id FROM review_collections WHERE name = ?", (clean_name,)).fetchone()
        assert row is not None
        return int(row["id"])


def _collection_tracks(connection: sqlite3.Connection, collection_id: int) -> tuple[ReviewCollectionTrack, ...]:
    rows = connection.execute(
        """
        SELECT collection_id, source_track_id, position, score, note, added_at
        FROM review_collection_tracks
        WHERE collection_id = ?
        ORDER BY position, source_track_id
        """,
        (collection_id,),
    ).fetchall()
    return tuple(
        ReviewCollectionTrack(
            collection_id=int(row["collection_id"]),
            source_track_id=int(row["source_track_id"]),
            position=int(row["position"]),
            score=float(row["score"]) if row["score"] is not None else None,
            note=row["note"],
            added_at=str(row["added_at"]),
        )
        for row in rows
    )


def _collection_from_row(
    row: sqlite3.Row,
    *,
    tracks: tuple[ReviewCollectionTrack, ...] = (),
) -> ReviewCollection:
    return ReviewCollection(
        id=int(row["id"]),
        name=str(row["name"]),
        source=str(row["source"]),
        note=row["note"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        track_count=int(row["track_count"]),
        tracks=tracks,
    )


def _require_collection(connection: sqlite3.Connection, collection_id: int) -> None:
    row = connection.execute("SELECT 1 FROM review_collections WHERE id = ?", (collection_id,)).fetchone()
    if row is None:
        raise KeyError(f"Review collection not found: {collection_id}")


def _validate_collection_id(value: int) -> int:
    clean = int(value)
    if clean <= 0:
        raise ValueError("Review collection id must be a positive integer")
    return clean


def _validate_collection_name(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError("Review collection name is required")
    return clean


def _validate_mode(value: str) -> str:
    clean = value.strip().lower()
    if clean not in COLLECTION_MODES:
        raise ValueError(f"Review collection mode must be one of: {', '.join(sorted(COLLECTION_MODES))}")
    return clean


def _unique_track_ids(track_ids: list[int] | tuple[int, ...]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in track_ids:
        clean = int(value)
        if clean <= 0:
            raise ValueError("Review collection track ids must be positive integers")
        if clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result

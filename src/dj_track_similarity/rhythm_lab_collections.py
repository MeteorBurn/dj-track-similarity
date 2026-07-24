"""Review-collection persistence for the separately owned Rhythm Lab database.

Core track ids are accepted only at the main-app boundary and are resolved
through :class:`TrackRepository` into stable v7 identities.  Persisted
collection membership is keyed by catalog UUID and track UUID, with the
content generation and selected path retained as an immutable audit snapshot.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Protocol


DEFAULT_COLLECTION_SOURCE = "manual"
COLLECTION_MODES = {"append", "replace"}

_COLLECTION_COLUMNS = {
    "id",
    "catalog_uuid",
    "name",
    "source",
    "note",
    "created_at",
    "updated_at",
}
_COLLECTION_TRACK_COLUMNS = {
    "collection_id",
    "catalog_uuid",
    "track_uuid",
    "content_generation",
    "selected_path",
    "position",
    "score",
    "note",
    "added_at",
}


class _TrackFileState(Protocol):
    catalog_uuid: str
    track_id: int
    track_uuid: str
    file_path: str
    content_generation: int


class RhythmLabTrackRepository(Protocol):
    """Canonical Core read contract used by the main-app bridge."""

    catalog_uuid: str

    def get_track_file_states_by_ids(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[_TrackFileState, ...]: ...


@dataclass(frozen=True, slots=True)
class RhythmLabTrackSelection:
    """One exact v7 track snapshot selected for a review collection."""

    catalog_uuid: str
    track_uuid: str
    content_generation: int
    selected_path: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_uuid",
            _required_text(self.catalog_uuid, field="catalog_uuid"),
        )
        object.__setattr__(
            self,
            "track_uuid",
            _required_text(self.track_uuid, field="track_uuid"),
        )
        _positive_int(
            self.content_generation,
            field="content_generation",
        )
        _nonempty_path(self.selected_path)


@dataclass(frozen=True, slots=True)
class RhythmLabCollectionSelection:
    """Ordered collection input bound to one library catalog."""

    catalog_uuid: str
    tracks: tuple[RhythmLabTrackSelection, ...]

    def __post_init__(self) -> None:
        catalog_uuid = _required_text(self.catalog_uuid, field="catalog_uuid")
        object.__setattr__(self, "catalog_uuid", catalog_uuid)
        seen: set[str] = set()
        for track in self.tracks:
            if not isinstance(track, RhythmLabTrackSelection):
                raise TypeError(
                    "tracks must contain RhythmLabTrackSelection values"
                )
            if track.catalog_uuid != catalog_uuid:
                raise ValueError(
                    "Every selected track must belong to the selection catalog"
                )
            if track.track_uuid in seen:
                raise ValueError(
                    "Collection selection contains a duplicate track_uuid"
                )
            seen.add(track.track_uuid)


@dataclass(frozen=True, slots=True)
class ReviewCollectionTrack:
    collection_id: int
    catalog_uuid: str
    track_uuid: str
    content_generation: int
    selected_path: str
    position: int
    score: float | None
    note: str | None
    added_at: str


@dataclass(frozen=True, slots=True)
class ReviewCollection:
    id: int
    catalog_uuid: str
    name: str
    source: str
    note: str | None
    created_at: str
    updated_at: str
    track_count: int
    tracks: tuple[ReviewCollectionTrack, ...] = ()


def default_rhythm_lab_labels_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "rhythm-lab"
        / "data"
        / "rhythm_lab.sqlite"
    )


def build_rhythm_lab_collection_selection(
    repository: RhythmLabTrackRepository,
    track_ids: Iterable[int],
) -> RhythmLabCollectionSelection:
    """Resolve transient Core ids into one ordered, stable v7 selection.

    Resolution is delegated to the canonical TrackRepository batch method. No
    Core SQL is issued here, and no missing or changed track is guessed from a
    saved path.
    """

    catalog_uuid = _required_text(
        repository.catalog_uuid,
        field="repository catalog_uuid",
    )
    ordered_ids = _unique_positive_ids(track_ids)
    states = repository.get_track_file_states_by_ids(
        ordered_ids,
        include_missing=False,
    )
    states_by_id: dict[int, _TrackFileState] = {}
    for state in states:
        track_id = _positive_int(state.track_id, field="track_id")
        if track_id in states_by_id:
            raise RuntimeError(
                "TrackRepository returned a duplicate track identity"
            )
        states_by_id[track_id] = state
    if set(states_by_id) != set(ordered_ids):
        raise RuntimeError(
            "TrackRepository did not return exactly the requested current tracks"
        )

    selected: list[RhythmLabTrackSelection] = []
    for track_id in ordered_ids:
        state = states_by_id[track_id]
        if state.catalog_uuid != catalog_uuid:
            raise RuntimeError(
                "TrackRepository returned a track from a different catalog"
            )
        selected.append(
            RhythmLabTrackSelection(
                catalog_uuid=catalog_uuid,
                track_uuid=str(state.track_uuid),
                content_generation=state.content_generation,
                selected_path=str(state.file_path),
            )
        )
    return RhythmLabCollectionSelection(
        catalog_uuid=catalog_uuid,
        tracks=tuple(selected),
    )


def ensure_review_collection_schema(connection: sqlite3.Connection) -> None:
    """Create the v7-only review collection tables in a Lab database.

    A legacy ``source_track_id`` schema is rejected instead of being
    interpreted as current identity. Recovery/import is a separate explicit
    workflow.
    """

    _reject_noncanonical_table(
        connection,
        table="review_collections",
        expected_columns=_COLLECTION_COLUMNS,
    )
    _reject_noncanonical_table(
        connection,
        table="review_collection_tracks",
        expected_columns=_COLLECTION_TRACK_COLUMNS,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS review_collections (
            id INTEGER PRIMARY KEY,
            catalog_uuid TEXT NOT NULL,
            name TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'manual',
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id, catalog_uuid)
        );

        CREATE TABLE IF NOT EXISTS review_collection_tracks (
            collection_id INTEGER NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            content_generation INTEGER NOT NULL
                CHECK(content_generation >= 1),
            selected_path TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 1),
            score REAL,
            note TEXT,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(collection_id, catalog_uuid, track_uuid),
            FOREIGN KEY(collection_id, catalog_uuid)
                REFERENCES review_collections(id, catalog_uuid)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_review_collection_tracks_order
        ON review_collection_tracks(
            collection_id,
            position,
            catalog_uuid,
            track_uuid
        );
        """
    )
    _require_exact_columns(
        connection,
        table="review_collections",
        expected_columns=_COLLECTION_COLUMNS,
    )
    _require_exact_columns(
        connection,
        table="review_collection_tracks",
        expected_columns=_COLLECTION_TRACK_COLUMNS,
    )


class RhythmLabCollections:
    """Repository for review collections in the Rhythm Lab database only."""

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
                SELECT
                    c.id,
                    c.catalog_uuid,
                    c.name,
                    c.source,
                    c.note,
                    c.created_at,
                    c.updated_at,
                    COUNT(t.track_uuid) AS track_count
                FROM review_collections c
                LEFT JOIN review_collection_tracks t
                  ON t.collection_id = c.id
                 AND t.catalog_uuid = c.catalog_uuid
                GROUP BY c.id, c.catalog_uuid
                ORDER BY c.updated_at DESC, LOWER(c.name), c.id
                """
            ).fetchall()
        return [_collection_from_row(row) for row in rows]

    def get_collection(self, collection_id: int) -> ReviewCollection:
        clean_id = _positive_int(collection_id, field="collection_id")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    c.id,
                    c.catalog_uuid,
                    c.name,
                    c.source,
                    c.note,
                    c.created_at,
                    c.updated_at,
                    COUNT(t.track_uuid) AS track_count
                FROM review_collections c
                LEFT JOIN review_collection_tracks t
                  ON t.collection_id = c.id
                 AND t.catalog_uuid = c.catalog_uuid
                WHERE c.id = ?
                GROUP BY c.id, c.catalog_uuid
                """,
                (clean_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Review collection not found: {clean_id}")
            tracks = _collection_tracks(connection, clean_id)
        return _collection_from_row(row, tracks=tracks)

    def collection_by_name(self, name: str) -> ReviewCollection | None:
        clean_name = _required_text(name, field="collection name")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM review_collections WHERE name = ?",
                (clean_name,),
            ).fetchone()
        return self.get_collection(int(row["id"])) if row is not None else None

    def save_collection(
        self,
        name: str,
        selection: RhythmLabCollectionSelection,
        *,
        source: str = DEFAULT_COLLECTION_SOURCE,
        note: str | None = None,
        mode: str = "append",
    ) -> ReviewCollection:
        selected = _validated_selection(selection)
        clean_mode = _validate_mode(mode)
        collection_id = self._upsert_collection(
            name,
            catalog_uuid=selected.catalog_uuid,
            source=source,
            note=note,
        )
        if clean_mode == "replace":
            return self.replace_tracks(collection_id, selected)
        return self.append_tracks(collection_id, selected)

    def append_tracks(
        self,
        collection_id: int,
        selection: RhythmLabCollectionSelection,
    ) -> ReviewCollection:
        clean_id = _positive_int(collection_id, field="collection_id")
        selected = _validated_selection(selection)
        with self.connect() as connection:
            _require_collection_catalog(
                connection,
                clean_id,
                selected.catalog_uuid,
            )
            next_position = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(position), 0) + 1
                    FROM review_collection_tracks
                    WHERE collection_id = ?
                      AND catalog_uuid = ?
                    """,
                    (clean_id, selected.catalog_uuid),
                ).fetchone()[0]
            )
            existing = {
                str(row["track_uuid"])
                for row in connection.execute(
                    """
                    SELECT track_uuid
                    FROM review_collection_tracks
                    WHERE collection_id = ?
                      AND catalog_uuid = ?
                    """,
                    (clean_id, selected.catalog_uuid),
                ).fetchall()
            }
            new_tracks = [
                track
                for track in selected.tracks
                if track.track_uuid not in existing
            ]
            _insert_collection_tracks(
                connection,
                clean_id,
                new_tracks,
                start_position=next_position,
            )
            connection.execute(
                """
                UPDATE review_collections
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND catalog_uuid = ?
                """,
                (clean_id, selected.catalog_uuid),
            )
        return self.get_collection(clean_id)

    def replace_tracks(
        self,
        collection_id: int,
        selection: RhythmLabCollectionSelection,
    ) -> ReviewCollection:
        clean_id = _positive_int(collection_id, field="collection_id")
        selected = _validated_selection(selection)
        with self.connect() as connection:
            _require_collection_catalog(
                connection,
                clean_id,
                selected.catalog_uuid,
            )
            connection.execute(
                """
                DELETE FROM review_collection_tracks
                WHERE collection_id = ?
                  AND catalog_uuid = ?
                """,
                (clean_id, selected.catalog_uuid),
            )
            _insert_collection_tracks(
                connection,
                clean_id,
                selected.tracks,
                start_position=1,
            )
            connection.execute(
                """
                UPDATE review_collections
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND catalog_uuid = ?
                """,
                (clean_id, selected.catalog_uuid),
            )
        return self.get_collection(clean_id)

    def delete_collection(self, collection_id: int) -> bool:
        clean_id = _positive_int(collection_id, field="collection_id")
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM review_collections WHERE id = ?",
                (clean_id,),
            )
        return cursor.rowcount > 0

    def _upsert_collection(
        self,
        name: str,
        *,
        catalog_uuid: str,
        source: str,
        note: str | None,
    ) -> int:
        clean_name = _required_text(name, field="collection name")
        clean_catalog = _required_text(catalog_uuid, field="catalog_uuid")
        clean_source = (
            (source or DEFAULT_COLLECTION_SOURCE).strip()
            or DEFAULT_COLLECTION_SOURCE
        )
        clean_note = (
            note.strip()
            if isinstance(note, str) and note.strip()
            else None
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_collections(
                    catalog_uuid,
                    name,
                    source,
                    note
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    source = excluded.source,
                    note = COALESCE(
                        excluded.note,
                        review_collections.note
                    ),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    clean_catalog,
                    clean_name,
                    clean_source,
                    clean_note,
                ),
            )
            row = connection.execute(
                """
                SELECT id, catalog_uuid
                FROM review_collections
                WHERE name = ?
                """,
                (clean_name,),
            ).fetchone()
            assert row is not None
            if str(row["catalog_uuid"]) != clean_catalog:
                raise RuntimeError(
                    "Review collection belongs to a different catalog"
                )
            return int(row["id"])


def _collection_tracks(
    connection: sqlite3.Connection,
    collection_id: int,
) -> tuple[ReviewCollectionTrack, ...]:
    rows = connection.execute(
        """
        SELECT
            collection_id,
            catalog_uuid,
            track_uuid,
            content_generation,
            selected_path,
            position,
            score,
            note,
            added_at
        FROM review_collection_tracks
        WHERE collection_id = ?
        ORDER BY position, catalog_uuid, track_uuid
        """,
        (collection_id,),
    ).fetchall()
    return tuple(
        ReviewCollectionTrack(
            collection_id=int(row["collection_id"]),
            catalog_uuid=str(row["catalog_uuid"]),
            track_uuid=str(row["track_uuid"]),
            content_generation=int(row["content_generation"]),
            selected_path=str(row["selected_path"]),
            position=int(row["position"]),
            score=(
                float(row["score"])
                if row["score"] is not None
                else None
            ),
            note=row["note"],
            added_at=str(row["added_at"]),
        )
        for row in rows
    )


def _insert_collection_tracks(
    connection: sqlite3.Connection,
    collection_id: int,
    tracks: Sequence[RhythmLabTrackSelection],
    *,
    start_position: int,
) -> None:
    rows = (
        (
            collection_id,
            track.catalog_uuid,
            track.track_uuid,
            track.content_generation,
            track.selected_path,
            position,
        )
        for position, track in enumerate(
            tracks,
            start=start_position,
        )
    )
    connection.executemany(
        """
        INSERT INTO review_collection_tracks(
            collection_id,
            catalog_uuid,
            track_uuid,
            content_generation,
            selected_path,
            position
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _collection_from_row(
    row: sqlite3.Row,
    *,
    tracks: tuple[ReviewCollectionTrack, ...] = (),
) -> ReviewCollection:
    return ReviewCollection(
        id=int(row["id"]),
        catalog_uuid=str(row["catalog_uuid"]),
        name=str(row["name"]),
        source=str(row["source"]),
        note=row["note"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        track_count=int(row["track_count"]),
        tracks=tracks,
    )


def _require_collection_catalog(
    connection: sqlite3.Connection,
    collection_id: int,
    catalog_uuid: str,
) -> None:
    row = connection.execute(
        """
        SELECT catalog_uuid
        FROM review_collections
        WHERE id = ?
        """,
        (collection_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Review collection not found: {collection_id}")
    if str(row["catalog_uuid"]) != catalog_uuid:
        raise RuntimeError(
            "Review collection belongs to a different catalog"
        )


def _validated_selection(
    selection: RhythmLabCollectionSelection,
) -> RhythmLabCollectionSelection:
    if not isinstance(selection, RhythmLabCollectionSelection):
        raise TypeError(
            "Expected RhythmLabCollectionSelection; raw track ids are not "
            "persistent Rhythm Lab identity"
        )
    return selection


def _validate_mode(value: str) -> str:
    clean = value.strip().lower()
    if clean not in COLLECTION_MODES:
        raise ValueError(
            "Review collection mode must be one of: "
            + ", ".join(sorted(COLLECTION_MODES))
        )
    return clean


def _unique_positive_ids(values: Iterable[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        clean = _positive_int(value, field="track_id")
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _nonempty_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("selected_path must be non-empty text")
    return value


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> set[str] | None:
    exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_schema
        WHERE type = 'table'
          AND name = ?
        """,
        (table,),
    ).fetchone()
    if exists is None:
        return None
    return {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def _reject_noncanonical_table(
    connection: sqlite3.Connection,
    *,
    table: str,
    expected_columns: set[str],
) -> None:
    columns = _table_columns(connection, table)
    if columns is not None and columns != expected_columns:
        raise RuntimeError(
            f"Rhythm Lab table {table!r} is not the canonical v7 schema; "
            "use the explicit label recovery workflow"
        )


def _require_exact_columns(
    connection: sqlite3.Connection,
    *,
    table: str,
    expected_columns: set[str],
) -> None:
    columns = _table_columns(connection, table)
    if columns != expected_columns:
        raise RuntimeError(
            f"Rhythm Lab table {table!r} does not match the canonical v7 schema"
        )

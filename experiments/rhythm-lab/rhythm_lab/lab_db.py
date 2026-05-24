from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Literal

from dj_track_similarity.metadata_payload import metadata_to_json
from dj_track_similarity.models import Track


OLD_STRAIGHT_LABEL = "straight_four_on_the_floor"
STRAIGHT_LABEL = "straight"
RhythmLabelName = Literal["broken", "straight", "ambiguous"]
RHYTHM_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL, "ambiguous")
TRAINING_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL)


@dataclass(frozen=True)
class RhythmLabel:
    source_track_id: int
    label: str
    note: str | None = None
    updated_at: str | None = None


class RhythmLabDatabase:
    """Writable rhythm-lab user data, separate from the read-only source library."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_lab_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _ensure_lab_schema(self) -> None:
        with self.connect() as connection:
            _ensure_rhythm_labels_table(connection)
            _ensure_rhythm_predictions_table(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_rhythm_labels_label
                ON rhythm_labels(label, updated_at);

                CREATE INDEX IF NOT EXISTS idx_rhythm_predictions_label
                ON rhythm_predictions(label, confidence);
                """
            )

    def set_label(self, track: Track | int, label: str | None, *, note: str | None = None) -> RhythmLabel | None:
        source_track_id, path, size, mtime = _track_snapshot(track)
        if label is None or not label.strip():
            with self.connect() as connection:
                connection.execute("DELETE FROM rhythm_labels WHERE source_track_id = ?", (source_track_id,))
            return None
        label = _canonical_label(label.strip())
        if label not in RHYTHM_LABELS:
            raise ValueError(f"Unsupported rhythm label: {label}")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rhythm_labels(source_track_id, path, size, mtime, label, note)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_track_id) DO UPDATE SET
                    path = excluded.path,
                    size = excluded.size,
                    mtime = excluded.mtime,
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source_track_id, path, size, mtime, label, note),
            )
        return self.label_for_track(source_track_id)

    def label_for_track(self, source_track_id: int) -> RhythmLabel | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT source_track_id, label, note, updated_at
                FROM rhythm_labels
                WHERE source_track_id = ?
                """,
                (source_track_id,),
            ).fetchone()
        if row is None:
            return None
        return RhythmLabel(int(row["source_track_id"]), str(row["label"]), row["note"], row["updated_at"])

    def labels_by_track(self) -> dict[int, RhythmLabel]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT source_track_id, label, note, updated_at FROM rhythm_labels"
            ).fetchall()
        return {
            int(row["source_track_id"]): RhythmLabel(
                int(row["source_track_id"]), str(row["label"]), row["note"], row["updated_at"]
            )
            for row in rows
        }

    def label_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute("SELECT label, COUNT(*) AS count FROM rhythm_labels GROUP BY label").fetchall()
        return {str(row["label"]): int(row["count"]) for row in rows}

    def training_labels(self) -> dict[int, str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_track_id, label
                FROM rhythm_labels
                WHERE label IN ('broken', 'straight')
                ORDER BY source_track_id
                """
            ).fetchall()
        return {int(row["source_track_id"]): str(row["label"]) for row in rows}

    def save_prediction(
        self,
        track: Track,
        *,
        feature_set: str,
        model_artifact: str | Path,
        label: str,
        confidence: float,
        probabilities: dict[str, float],
    ) -> None:
        if label not in TRAINING_LABELS:
            raise ValueError(f"Unsupported predicted rhythm label: {label}")
        payload = metadata_to_json(probabilities)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rhythm_predictions(
                    source_track_id, path, artist, title, feature_set, model_artifact,
                    label, confidence, probabilities_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_track_id, feature_set, model_artifact) DO UPDATE SET
                    path = excluded.path,
                    artist = excluded.artist,
                    title = excluded.title,
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    track.id,
                    track.path,
                    track.artist,
                    track.title,
                    feature_set,
                    str(model_artifact),
                    label,
                    float(confidence),
                    payload,
                ),
            )

    def predictions(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_track_id, feature_set, model_artifact, label, confidence,
                       probabilities_json, path, artist, title
                FROM rhythm_predictions
                ORDER BY confidence ASC, path
                """
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            try:
                probabilities = json.loads(str(row["probabilities_json"]))
            except json.JSONDecodeError:
                probabilities = {}
            result.append(
                {
                    "source_track_id": int(row["source_track_id"]),
                    "track_id": int(row["source_track_id"]),
                    "feature_set": str(row["feature_set"]),
                    "model_artifact": str(row["model_artifact"]),
                    "label": str(row["label"]),
                    "confidence": float(row["confidence"]),
                    "probabilities": probabilities,
                    "path": str(row["path"]),
                    "artist": row["artist"],
                    "title": row["title"],
                }
            )
        return result


def _track_snapshot(track: Track | int) -> tuple[int, str | None, int | None, float | None]:
    if isinstance(track, Track):
        return track.id, track.path, track.size, track.mtime
    return int(track), None, None, None


def _canonical_label(label: str) -> str:
    return STRAIGHT_LABEL if label == OLD_STRAIGHT_LABEL else label


def _ensure_rhythm_labels_table(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "rhythm_labels")
    if not columns:
        connection.execute(_rhythm_labels_table_sql("rhythm_labels"))
        return
    if "source_track_id" in columns:
        return
    connection.execute(_rhythm_labels_table_sql("rhythm_labels_new"))
    if _columns(connection, "rhythm_lab_tracks"):
        source_expr = (
            "COALESCE((SELECT source_track_id FROM rhythm_lab_tracks "
            "WHERE rhythm_lab_tracks.track_id = rhythm_labels.track_id), rhythm_labels.track_id)"
        )
    else:
        source_expr = "rhythm_labels.track_id"
    path_expr = (
        "(SELECT path FROM tracks WHERE tracks.id = rhythm_labels.track_id)"
        if _columns(connection, "tracks")
        else "NULL"
    )
    size_expr = (
        "(SELECT size FROM tracks WHERE tracks.id = rhythm_labels.track_id)"
        if _columns(connection, "tracks")
        else "NULL"
    )
    mtime_expr = (
        "(SELECT mtime FROM tracks WHERE tracks.id = rhythm_labels.track_id)"
        if _columns(connection, "tracks")
        else "NULL"
    )
    connection.execute(
        f"""
        INSERT OR REPLACE INTO rhythm_labels_new(source_track_id, path, size, mtime, label, note, updated_at)
        SELECT {source_expr},
               {path_expr},
               {size_expr},
               {mtime_expr},
               CASE label WHEN 'straight_four_on_the_floor' THEN 'straight' ELSE label END,
               note,
               updated_at
        FROM rhythm_labels
        WHERE label IN ('broken', 'straight_four_on_the_floor', 'straight', 'ambiguous')
        """
    )
    connection.execute("DROP TABLE rhythm_labels")
    connection.execute("ALTER TABLE rhythm_labels_new RENAME TO rhythm_labels")


def _ensure_rhythm_predictions_table(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "rhythm_predictions")
    if not columns:
        connection.execute(_rhythm_predictions_table_sql("rhythm_predictions"))
        return
    if "source_track_id" in columns:
        return
    rows = connection.execute(
        """
        SELECT track_id, feature_set, model_artifact, label, confidence, probabilities_json, updated_at
        FROM rhythm_predictions
        """
    ).fetchall()
    connection.execute(_rhythm_predictions_table_sql("rhythm_predictions_new"))
    for row in rows:
        label = _canonical_label(str(row["label"]))
        if label not in TRAINING_LABELS:
            continue
        source_track_id = _source_track_id_for_old_track(connection, int(row["track_id"]))
        connection.execute(
            """
            INSERT OR REPLACE INTO rhythm_predictions_new(
                source_track_id, path, artist, title, feature_set, model_artifact,
                label, confidence, probabilities_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_track_id,
                _old_track_value(connection, int(row["track_id"]), "path"),
                _old_track_value(connection, int(row["track_id"]), "artist"),
                _old_track_value(connection, int(row["track_id"]), "title"),
                str(row["feature_set"]),
                str(row["model_artifact"]),
                label,
                float(row["confidence"]),
                _canonical_probabilities_json(str(row["probabilities_json"])),
                row["updated_at"],
            ),
        )
    connection.execute("DROP TABLE rhythm_predictions")
    connection.execute("ALTER TABLE rhythm_predictions_new RENAME TO rhythm_predictions")


def _source_track_id_for_old_track(connection: sqlite3.Connection, track_id: int) -> int:
    if _columns(connection, "rhythm_lab_tracks"):
        row = connection.execute(
            "SELECT source_track_id FROM rhythm_lab_tracks WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        if row is not None:
            return int(row["source_track_id"])
    return track_id


def _old_track_value(connection: sqlite3.Connection, track_id: int, column: str) -> object | None:
    if not _columns(connection, "tracks"):
        return None
    row = connection.execute(f"SELECT {column} FROM tracks WHERE id = ?", (track_id,)).fetchone()
    return row[column] if row is not None else None


def _canonical_probabilities_json(payload: str) -> str:
    try:
        probabilities = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(probabilities, dict) and OLD_STRAIGHT_LABEL in probabilities:
        old_value = probabilities.pop(OLD_STRAIGHT_LABEL)
        probabilities.setdefault(STRAIGHT_LABEL, old_value)
    return metadata_to_json(probabilities) if isinstance(probabilities, dict) else payload


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        return set()
    return {str(info["name"]) for info in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _rhythm_labels_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE {table} (
            source_track_id INTEGER PRIMARY KEY,
            path TEXT,
            size INTEGER,
            mtime REAL,
            label TEXT NOT NULL CHECK(label IN ('broken', 'straight', 'ambiguous')),
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """


def _rhythm_predictions_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE {table} (
            source_track_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            artist TEXT,
            title TEXT,
            feature_set TEXT NOT NULL,
            model_artifact TEXT NOT NULL,
            label TEXT NOT NULL CHECK(label IN ('broken', 'straight')),
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(source_track_id, feature_set, model_artifact)
        )
    """

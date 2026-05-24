from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Literal

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.metadata_payload import metadata_to_json


OLD_STRAIGHT_LABEL = "straight_four_on_the_floor"
STRAIGHT_LABEL = "straight"
RhythmLabelName = Literal["broken", "straight", "ambiguous"]
RHYTHM_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL, "ambiguous")
TRAINING_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL)


@dataclass(frozen=True)
class RhythmLabel:
    track_id: int
    label: str
    note: str | None = None
    updated_at: str | None = None


class RhythmLabDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.library = LibraryDatabase(self.path)
        self._ensure_lab_schema()

    def connect(self) -> sqlite3.Connection:
        return self.library.connect()

    def _ensure_lab_schema(self) -> None:
        with self.library._write_lock, self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rhythm_lab_tracks (
                    track_id INTEGER PRIMARY KEY,
                    source_track_id INTEGER NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
                );
                """
            )
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

    def record_source_track(self, track_id: int, source_track_id: int) -> None:
        with self.library._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rhythm_lab_tracks(track_id, source_track_id)
                VALUES (?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    source_track_id = excluded.source_track_id
                """,
                (track_id, source_track_id),
            )

    def source_track_id(self, track_id: int) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT source_track_id FROM rhythm_lab_tracks WHERE track_id = ?",
                (track_id,),
            ).fetchone()
        return int(row["source_track_id"]) if row else None

    def source_track_ids(self) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute("SELECT source_track_id FROM rhythm_lab_tracks").fetchall()
        return {int(row["source_track_id"]) for row in rows}

    def set_label(self, track_id: int, label: str | None, *, note: str | None = None) -> RhythmLabel | None:
        if label is None or not label.strip():
            with self.library._write_lock, self.connect() as connection:
                connection.execute("DELETE FROM rhythm_labels WHERE track_id = ?", (track_id,))
            return None
        label = _canonical_label(label.strip())
        if label not in RHYTHM_LABELS:
            raise ValueError(f"Unsupported rhythm label: {label}")
        self.library.get_track(track_id)
        with self.library._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rhythm_labels(track_id, label, note)
                VALUES (?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (track_id, label, note),
            )
        return self.label_for_track(track_id)

    def label_for_track(self, track_id: int) -> RhythmLabel | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT track_id, label, note, updated_at FROM rhythm_labels WHERE track_id = ?",
                (track_id,),
            ).fetchone()
        if row is None:
            return None
        return RhythmLabel(int(row["track_id"]), str(row["label"]), row["note"], row["updated_at"])

    def labels_by_track(self) -> dict[int, RhythmLabel]:
        with self.connect() as connection:
            rows = connection.execute("SELECT track_id, label, note, updated_at FROM rhythm_labels").fetchall()
        return {
            int(row["track_id"]): RhythmLabel(int(row["track_id"]), str(row["label"]), row["note"], row["updated_at"])
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
                SELECT track_id, label
                FROM rhythm_labels
                WHERE label IN ('broken', 'straight')
                ORDER BY track_id
                """
            ).fetchall()
        return {int(row["track_id"]): str(row["label"]) for row in rows}

    def embedding_track_ids(self, embedding_key: str) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT track_id FROM embeddings WHERE embedding_key = ?",
                (embedding_key,),
            ).fetchall()
        return {int(row["track_id"]) for row in rows}

    def save_prediction(
        self,
        track_id: int,
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
        with self.library._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO rhythm_predictions(
                    track_id, feature_set, model_artifact, label, confidence, probabilities_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id, feature_set, model_artifact) DO UPDATE SET
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (track_id, feature_set, str(model_artifact), label, float(confidence), payload),
            )

    def predictions(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.track_id, p.feature_set, p.model_artifact, p.label, p.confidence,
                       p.probabilities_json, t.path, t.artist, t.title
                FROM rhythm_predictions p
                JOIN tracks t ON t.id = p.track_id
                ORDER BY p.confidence ASC, t.path
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
                    "track_id": int(row["track_id"]),
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


def _canonical_label(label: str) -> str:
    return STRAIGHT_LABEL if label == OLD_STRAIGHT_LABEL else label


def _ensure_rhythm_labels_table(connection: sqlite3.Connection) -> None:
    sql = _table_sql(connection, "rhythm_labels")
    if sql is None:
        connection.execute(_rhythm_labels_table_sql("rhythm_labels"))
        return
    if OLD_STRAIGHT_LABEL not in sql:
        return
    connection.execute(_rhythm_labels_table_sql("rhythm_labels_new"))
    connection.execute(
        """
        INSERT OR REPLACE INTO rhythm_labels_new(track_id, label, note, updated_at)
        SELECT track_id,
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
    sql = _table_sql(connection, "rhythm_predictions")
    if sql is None:
        connection.execute(_rhythm_predictions_table_sql("rhythm_predictions"))
        return
    if OLD_STRAIGHT_LABEL not in sql:
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
        connection.execute(
            """
            INSERT OR REPLACE INTO rhythm_predictions_new(
                track_id, feature_set, model_artifact, label, confidence, probabilities_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["track_id"]),
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


def _canonical_probabilities_json(payload: str) -> str:
    try:
        probabilities = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(probabilities, dict) and OLD_STRAIGHT_LABEL in probabilities:
        old_value = probabilities.pop(OLD_STRAIGHT_LABEL)
        probabilities.setdefault(STRAIGHT_LABEL, old_value)
    return metadata_to_json(probabilities) if isinstance(probabilities, dict) else payload


def _table_sql(connection: sqlite3.Connection, table: str) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return str(row["sql"]) if row and row["sql"] else None


def _rhythm_labels_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE {table} (
            track_id INTEGER PRIMARY KEY,
            label TEXT NOT NULL CHECK(label IN ('broken', 'straight', 'ambiguous')),
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        )
    """


def _rhythm_predictions_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE {table} (
            track_id INTEGER NOT NULL,
            feature_set TEXT NOT NULL,
            model_artifact TEXT NOT NULL,
            label TEXT NOT NULL CHECK(label IN ('broken', 'straight')),
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, feature_set, model_artifact),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        )
    """

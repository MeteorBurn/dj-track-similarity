from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Literal

from dj_track_similarity.metadata_payload import metadata_to_json
from dj_track_similarity.models import Track


BREAK_ENERGY_CLASSIFIER_KEY = "break_energy"
OLD_STRAIGHT_LABEL = "straight_four_on_the_floor"
STRAIGHT_LABEL = "straight"
ClassifierLabelName = Literal["broken", "straight", "ambiguous"]
CLASSIFIER_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL, "ambiguous")
TRAINING_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL)


@dataclass(frozen=True)
class ClassifierLabel:
    source_track_id: int
    label: str
    note: str | None = None
    updated_at: str | None = None


class RhythmLabDatabase:
    """Writable classifier-lab state, separate from the read-only source library."""

    def __init__(self, path: str | Path, *, classifier_key: str = BREAK_ENERGY_CLASSIFIER_KEY) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.classifier_key = classifier_key
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
            _ensure_classifier_tables(connection)
            _migrate_rhythm_tables(connection)
            _drop_rhythm_tables(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_classifier_labels_lookup
                ON classifier_labels(classifier_key, label, updated_at);

                CREATE INDEX IF NOT EXISTS idx_classifier_predictions_lookup
                ON classifier_predictions(classifier_key, label, confidence);
                """
            )

    def set_label(self, track: Track | int, label: str | None, *, note: str | None = None) -> ClassifierLabel | None:
        source_track_id, path, size, mtime = _track_snapshot(track)
        if label is None or not label.strip():
            with self.connect() as connection:
                connection.execute(
                    "DELETE FROM classifier_labels WHERE classifier_key = ? AND source_track_id = ?",
                    (self.classifier_key, source_track_id),
                )
            return None
        label = _canonical_label(label.strip())
        if label not in CLASSIFIER_LABELS:
            raise ValueError(f"Unsupported classifier label: {label}")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_labels(classifier_key, source_track_id, path, size, mtime, label, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(classifier_key, source_track_id) DO UPDATE SET
                    path = excluded.path,
                    size = excluded.size,
                    mtime = excluded.mtime,
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (self.classifier_key, source_track_id, path, size, mtime, label, note),
            )
        return self.label_for_track(source_track_id)

    def label_for_track(self, source_track_id: int) -> ClassifierLabel | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT source_track_id, label, note, updated_at
                FROM classifier_labels
                WHERE classifier_key = ? AND source_track_id = ?
                """,
                (self.classifier_key, source_track_id),
            ).fetchone()
        if row is None:
            return None
        return ClassifierLabel(int(row["source_track_id"]), str(row["label"]), row["note"], row["updated_at"])

    def labels_by_track(self) -> dict[int, ClassifierLabel]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_track_id, label, note, updated_at
                FROM classifier_labels
                WHERE classifier_key = ?
                """,
                (self.classifier_key,),
            ).fetchall()
        return {
            int(row["source_track_id"]): ClassifierLabel(
                int(row["source_track_id"]), str(row["label"]), row["note"], row["updated_at"]
            )
            for row in rows
        }

    def label_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT label, COUNT(*) AS count
                FROM classifier_labels
                WHERE classifier_key = ?
                GROUP BY label
                """,
                (self.classifier_key,),
            ).fetchall()
        return {str(row["label"]): int(row["count"]) for row in rows}

    def training_labels(self) -> dict[int, str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_track_id, label
                FROM classifier_labels
                WHERE classifier_key = ? AND label IN ('broken', 'straight')
                ORDER BY source_track_id
                """,
                (self.classifier_key,),
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
            raise ValueError(f"Unsupported predicted classifier label: {label}")
        payload = metadata_to_json(probabilities)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_predictions(
                    classifier_key, source_track_id, path, artist, title, feature_set, model_artifact,
                    label, confidence, probabilities_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(classifier_key, source_track_id, feature_set, model_artifact) DO UPDATE SET
                    path = excluded.path,
                    artist = excluded.artist,
                    title = excluded.title,
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    self.classifier_key,
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
                SELECT rowid AS prediction_rowid, source_track_id, feature_set, model_artifact, label, confidence,
                       probabilities_json, path, artist, title, updated_at
                FROM classifier_predictions
                WHERE classifier_key = ?
                ORDER BY confidence ASC, path
                """,
                (self.classifier_key,),
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
                    "prediction_rowid": int(row["prediction_rowid"]),
                    "track_id": int(row["source_track_id"]),
                    "feature_set": str(row["feature_set"]),
                    "model_artifact": str(row["model_artifact"]),
                    "label": str(row["label"]),
                    "confidence": float(row["confidence"]),
                    "probabilities": probabilities,
                    "path": str(row["path"]),
                    "artist": row["artist"],
                    "title": row["title"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def prune_predictions(self, *, feature_set: str, keep_model_artifact: str | Path) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM classifier_predictions
                WHERE classifier_key = ?
                  AND feature_set = ?
                  AND model_artifact != ?
                """,
                (self.classifier_key, feature_set, str(keep_model_artifact)),
            )
            return int(cursor.rowcount)

    def training_checkpoint(self) -> dict[str, object]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT counts_json, model_artifact, updated_at
                FROM classifier_training_checkpoints
                WHERE classifier_key = ?
                """,
                (self.classifier_key,),
            ).fetchone()
        if row is None:
            return {
                "counts": {"broken": 0, "straight": 0},
                "model_artifact": None,
                "updated_at": None,
            }
        try:
            counts = json.loads(str(row["counts_json"]))
        except json.JSONDecodeError:
            counts = {}
        return {
            "counts": {
                "broken": int(counts.get("broken", 0)) if isinstance(counts, dict) else 0,
                "straight": int(counts.get("straight", 0)) if isinstance(counts, dict) else 0,
            },
            "model_artifact": row["model_artifact"],
            "updated_at": row["updated_at"],
        }

    def record_training_checkpoint(self, counts: dict[str, int], *, model_artifact: str | Path) -> None:
        payload = metadata_to_json({"broken": int(counts.get("broken", 0)), "straight": int(counts.get("straight", 0))})
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_training_checkpoints(classifier_key, counts_json, model_artifact)
                VALUES (?, ?, ?)
                ON CONFLICT(classifier_key) DO UPDATE SET
                    counts_json = excluded.counts_json,
                    model_artifact = excluded.model_artifact,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (self.classifier_key, payload, str(model_artifact)),
            )


def _track_snapshot(track: Track | int) -> tuple[int, str | None, int | None, float | None]:
    if isinstance(track, Track):
        return track.id, track.path, track.size, track.mtime
    return int(track), None, None, None


def _canonical_label(label: str) -> str:
    return STRAIGHT_LABEL if label == OLD_STRAIGHT_LABEL else label


def _ensure_classifier_tables(connection: sqlite3.Connection) -> None:
    connection.execute(_classifier_labels_table_sql("classifier_labels"))
    connection.execute(_classifier_predictions_table_sql("classifier_predictions"))
    connection.execute(_classifier_training_checkpoints_table_sql("classifier_training_checkpoints"))


def _migrate_rhythm_tables(connection: sqlite3.Connection) -> None:
    if _columns(connection, "rhythm_labels"):
        _migrate_rhythm_labels(connection)
    if _columns(connection, "rhythm_predictions"):
        _migrate_rhythm_predictions(connection)
    if _columns(connection, "rhythm_training_checkpoint"):
        _migrate_rhythm_training_checkpoint(connection)


def _migrate_rhythm_labels(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "rhythm_labels")
    source_expr = "source_track_id" if "source_track_id" in columns else _old_source_track_expr("rhythm_labels")
    path_expr = "path" if "path" in columns else _old_track_lookup_expr("path")
    size_expr = "size" if "size" in columns else _old_track_lookup_expr("size")
    mtime_expr = "mtime" if "mtime" in columns else _old_track_lookup_expr("mtime")
    connection.execute(
        f"""
        INSERT OR REPLACE INTO classifier_labels(
            classifier_key, source_track_id, path, size, mtime, label, note, updated_at
        )
        SELECT ?,
               {source_expr},
               {path_expr},
               {size_expr},
               {mtime_expr},
               CASE label WHEN 'straight_four_on_the_floor' THEN 'straight' ELSE label END,
               note,
               updated_at
        FROM rhythm_labels
        WHERE label IN ('broken', 'straight_four_on_the_floor', 'straight', 'ambiguous')
        """,
        (BREAK_ENERGY_CLASSIFIER_KEY,),
    )


def _migrate_rhythm_predictions(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "rhythm_predictions")
    source_expr = "source_track_id" if "source_track_id" in columns else _old_source_track_expr("rhythm_predictions")
    path_expr = "path" if "path" in columns else _old_track_lookup_expr("path")
    artist_expr = "artist" if "artist" in columns else _old_track_lookup_expr("artist")
    title_expr = "title" if "title" in columns else _old_track_lookup_expr("title")
    rows = connection.execute(
        f"""
        SELECT {source_expr} AS source_track_id,
               {path_expr} AS path,
               {artist_expr} AS artist,
               {title_expr} AS title,
               feature_set,
               model_artifact,
               label,
               confidence,
               probabilities_json,
               updated_at
        FROM rhythm_predictions
        """
    ).fetchall()
    for row in rows:
        label = _canonical_label(str(row["label"]))
        if label not in TRAINING_LABELS:
            continue
        connection.execute(
            """
            INSERT OR REPLACE INTO classifier_predictions(
                classifier_key, source_track_id, path, artist, title, feature_set, model_artifact,
                label, confidence, probabilities_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                BREAK_ENERGY_CLASSIFIER_KEY,
                int(row["source_track_id"]),
                str(row["path"] or ""),
                row["artist"],
                row["title"],
                str(row["feature_set"]),
                str(row["model_artifact"]),
                label,
                float(row["confidence"]),
                _canonical_probabilities_json(str(row["probabilities_json"])),
                row["updated_at"],
            ),
        )


def _migrate_rhythm_training_checkpoint(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT broken_count, straight_count, model_artifact, updated_at
        FROM rhythm_training_checkpoint
        WHERE id = 1
        """
    ).fetchone()
    if row is None:
        return
    counts = metadata_to_json({"broken": int(row["broken_count"]), "straight": int(row["straight_count"])})
    connection.execute(
        """
        INSERT OR REPLACE INTO classifier_training_checkpoints(
            classifier_key, counts_json, model_artifact, updated_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (BREAK_ENERGY_CLASSIFIER_KEY, counts, row["model_artifact"], row["updated_at"]),
    )


def _drop_rhythm_tables(connection: sqlite3.Connection) -> None:
    for table in ("rhythm_labels", "rhythm_predictions", "rhythm_training_checkpoint", "rhythm_lab_tracks"):
        connection.execute(f"DROP TABLE IF EXISTS {table}")


def _old_source_track_expr(table: str) -> str:
    if table not in {"rhythm_labels", "rhythm_predictions"}:
        raise ValueError(f"Unsupported old source table: {table}")
    return (
        "COALESCE((SELECT source_track_id FROM rhythm_lab_tracks "
        f"WHERE rhythm_lab_tracks.track_id = {table}.track_id), {table}.track_id)"
    )


def _old_track_lookup_expr(column: str) -> str:
    if column not in {"path", "size", "mtime", "artist", "title"}:
        raise ValueError(f"Unsupported old track column: {column}")
    return f"(SELECT {column} FROM tracks WHERE tracks.id = rhythm_labels.track_id)" if column in {"path", "size", "mtime"} else f"(SELECT {column} FROM tracks WHERE tracks.id = rhythm_predictions.track_id)"


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


def _classifier_labels_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
            source_track_id INTEGER NOT NULL,
            path TEXT,
            size INTEGER,
            mtime REAL,
            label TEXT NOT NULL CHECK(label IN ('broken', 'straight', 'ambiguous')),
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(classifier_key, source_track_id)
        )
    """


def _classifier_predictions_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
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
            PRIMARY KEY(classifier_key, source_track_id, feature_set, model_artifact)
        )
    """


def _classifier_training_checkpoints_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT PRIMARY KEY,
            counts_json TEXT NOT NULL CHECK(json_valid(counts_json)),
            model_artifact TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import hashlib
import json
import sqlite3

import numpy as np

from dj_track_similarity.database import DEFAULT_EMBEDDING_KEY, LibraryDatabase
from dj_track_similarity.db_schema import TRACK_SELECT_FIELDS, TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR
from dj_track_similarity.metadata_payload import genres_from_metadata, metadata_from_json, optional_float
from dj_track_similarity.models import Track


REQUIRED_TRACK_COLUMNS = {
    "id",
    "path",
    "size",
    "mtime",
    "artist",
    "title",
    "album",
    "bpm",
    "musical_key",
    "energy",
    "duration",
    "metadata_json",
}
REQUIRED_EMBEDDING_COLUMNS = {"track_id", "embedding_key", "model_name", "dim", "vector"}


class SourceDatabase:
    """Read-only view over a main dj-track-similarity SQLite database."""

    def __init__(self, path: str | Path) -> None:
        selected = Path(_clean_path_text(path)).expanduser()
        if not str(selected).strip() or not selected.name:
            raise ValueError("Source database path is required")
        if not selected.exists():
            raise FileNotFoundError(f"Source database does not exist: {selected}")
        if not selected.is_file():
            raise ValueError("Source database path must be an existing file")
        self.path = selected.resolve(strict=True)
        self._validate_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA query_only = ON")
        connection.create_function("rhythm_lab_random_rank", 2, _stable_random_rank, deterministic=True)
        return connection

    def count_tracks(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])

    def count_embeddings(self, embedding_key: str) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE embedding_key = ?",
                    (embedding_key,),
                ).fetchone()[0]
            )

    def count_sonara_features(self) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks
                    WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL
                    """
                ).fetchone()[0]
            )

    def count_liked_tracks(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM track_likes").fetchone()[0])

    def get_track(self, track_id: int) -> Track:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.id = ?
                """,
                (DEFAULT_EMBEDDING_KEY, track_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return LibraryDatabase._row_to_track(row)

    def tracks_by_ids(self, track_ids: Iterable[int]) -> dict[int, Track]:
        unique_ids = list(dict.fromkeys(int(track_id) for track_id in track_ids))
        if not unique_ids:
            return {}
        result: dict[int, Track] = {}
        with self.connect() as connection:
            for start in range(0, len(unique_ids), 900):
                chunk = unique_ids[start : start + 900]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT {TRACK_SELECT_FIELDS}
                    FROM tracks t
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    WHERE t.id IN ({placeholders})
                    """,
                    (DEFAULT_EMBEDDING_KEY, *chunk),
                ).fetchall()
                for row in rows:
                    track = LibraryDatabase._row_to_track(row)
                    result[int(track.id)] = track
        return result

    def list_tracks(self) -> list[Track]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (DEFAULT_EMBEDDING_KEY,),
            ).fetchall()
        return [LibraryDatabase._row_to_track(row) for row in rows]

    def list_tracks_page(
        self,
        *,
        labels_db_path: str | Path,
        classifier_key: str,
        label_keys: tuple[str, ...] = ("broken", "straight", "ambiguous"),
        training_label_keys: tuple[str, ...] = ("broken", "straight"),
        query: str = "",
        syncopated: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        liked: str = "all",
        label: str = "all",
        collection_id: int | None = None,
        order: str = "normal",
        seed: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        order_sql = _track_page_order_sql(order=order, liked=liked, collection=collection_id is not None)
        where_parts, params = _track_page_filter_sql(
            query=query,
            syncopated=syncopated,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            liked=liked,
            label=label,
            label_keys=label_keys,
        )
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        random_seed = _random_seed_value(seed)
        labels_uri = (
            f"file:{Path(labels_db_path).expanduser().resolve(strict=False).as_posix()}?mode=ro"
        )
        collection_join = ""
        collection_params: tuple[object, ...] = ()
        if collection_id is not None:
            collection_join = (
                "JOIN labels.review_collection_tracks rct "
                "ON rct.source_track_id = t.id AND rct.collection_id = ?"
            )
            collection_params = (int(collection_id),)
        training_placeholders = ", ".join("?" for _ in training_label_keys) or "NULL"
        label_trained_sql = (
            f"CASE WHEN rl.label IN ({training_placeholders}) "
            "AND cp.updated_at IS NOT NULL "
            "AND rl.updated_at <= cp.updated_at THEN 1 ELSE 0 END"
        )
        with self.connect() as connection:
            connection.execute("ATTACH DATABASE ? AS labels", (labels_uri,))
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM tracks t
                    {collection_join}
                    LEFT JOIN labels.classifier_labels rl
                      ON rl.classifier_key = ? AND rl.source_track_id = t.id
                    {where_sql}
                    """,
                    (*collection_params, classifier_key, *params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS},
                       rl.label AS classifier_label,
                       {label_trained_sql} AS classifier_label_trained,
                       emert.track_id IS NOT NULL AS has_mert_embedding,
                       emaest.track_id IS NOT NULL AS has_maest_embedding
                FROM tracks t
                {collection_join}
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                LEFT JOIN embeddings emert ON emert.track_id = t.id AND emert.embedding_key = 'mert'
                LEFT JOIN embeddings emaest ON emaest.track_id = t.id AND emaest.embedding_key = 'maest'
                LEFT JOIN labels.classifier_labels rl
                  ON rl.classifier_key = ? AND rl.source_track_id = t.id
                LEFT JOIN labels.classifier_training_checkpoints cp
                  ON cp.classifier_key = ?
                {where_sql}
                {order_sql}
                LIMIT ? OFFSET ?
                """,
                (
                    *training_label_keys,
                    *collection_params,
                    DEFAULT_EMBEDDING_KEY,
                    classifier_key,
                    classifier_key,
                    *params,
                    *((random_seed,) if order == "random" and collection_id is None else ()),
                    bounded_limit,
                    bounded_offset,
                ),
            ).fetchall()
        return {
            "items": [_track_page_item(row) for row in rows],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def list_predictions_page(
        self,
        *,
        labels_db_path: str | Path,
        classifier_key: str,
        profile_type: str,
        positive_label: str,
        negative_label: str,
        label_keys: tuple[str, ...],
        training_label_keys: tuple[str, ...],
        query: str = "",
        syncopated: str = "all",
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        label: str = "unlabeled",
        predicted: str = "all",
        probability_focus: str = "positive_highest",
        min_positive: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        where_sql, filter_params = _prediction_page_filter_sql(
            query=query,
            syncopated=syncopated,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            label=label,
            predicted=predicted,
            label_keys=label_keys,
            min_positive=min_positive,
            profile_type=profile_type,
        )
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        labels_uri = f"file:{Path(labels_db_path).expanduser().resolve(strict=False).as_posix()}?mode=ro"
        training_placeholders = ", ".join("?" for _ in training_label_keys) or "NULL"
        cte_sql = f"""
            WITH ranked_predictions AS (
                SELECT
                    p.rowid AS prediction_rowid,
                    p.source_track_id,
                    p.path AS prediction_path,
                    p.artist AS prediction_artist,
                    p.title AS prediction_title,
                    p.feature_set,
                    p.model_artifact,
                    p.label AS predicted_label,
                    p.confidence,
                    p.probabilities_json,
                    p.updated_at,
                    COALESCE(
                        CAST(json_extract(p.probabilities_json, ?) AS REAL), 0.0
                    ) AS positive_probability,
                    COALESCE(
                        CAST(json_extract(p.probabilities_json, ?) AS REAL), 0.0
                    ) AS negative_probability,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.source_track_id
                        ORDER BY COALESCE(p.updated_at, '') DESC, p.rowid DESC, p.model_artifact DESC
                    ) AS prediction_rank
                FROM labels.classifier_predictions p
                WHERE p.classifier_key = ?
            ),
            latest_predictions AS (
                SELECT *
                FROM ranked_predictions
                WHERE prediction_rank = 1
            ),
            candidate_rows AS (
                SELECT
                    p.prediction_rowid,
                    p.source_track_id,
                    p.prediction_path,
                    p.prediction_artist,
                    p.prediction_title,
                    p.feature_set,
                    p.model_artifact,
                    p.predicted_label,
                    p.confidence,
                    p.probabilities_json,
                    p.updated_at,
                    p.positive_probability,
                    p.negative_probability,
                    EXISTS(SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id) AS liked,
                    t.id AS source_row_id,
                    t.path AS source_path,
                    t.artist AS source_artist,
                    t.title AS source_title,
                    t.album AS source_album,
                    t.metadata_json AS source_metadata_json,
                    rl.label AS classifier_label,
                    CASE WHEN rl.label IN ({training_placeholders})
                         AND cp.updated_at IS NOT NULL
                         AND rl.updated_at <= cp.updated_at
                         THEN 1 ELSE 0 END AS classifier_label_trained,
                    emert.track_id IS NOT NULL AS has_mert_embedding,
                    emaest.track_id IS NOT NULL AS has_maest_embedding
                FROM latest_predictions p
                LEFT JOIN tracks t ON t.id = p.source_track_id
                LEFT JOIN embeddings emert
                  ON emert.track_id = t.id AND emert.embedding_key = 'mert'
                LEFT JOIN embeddings emaest
                  ON emaest.track_id = t.id AND emaest.embedding_key = 'maest'
                LEFT JOIN labels.classifier_labels rl
                  ON rl.classifier_key = ? AND rl.source_track_id = p.source_track_id
                LEFT JOIN labels.classifier_training_checkpoints cp
                  ON cp.classifier_key = ?
            )
        """
        base_params = [
            _json_probability_path(positive_label),
            _json_probability_path(negative_label),
            classifier_key,
            *training_label_keys,
            classifier_key,
            classifier_key,
        ]
        order_sql = _prediction_page_order_sql(
            probability_focus=probability_focus,
            profile_type=profile_type,
        )
        with self.connect() as connection:
            connection.execute("ATTACH DATABASE ? AS labels", (labels_uri,))
            total = int(
                connection.execute(
                    f"{cte_sql} SELECT COUNT(*) FROM candidate_rows {where_sql}",
                    (*base_params, *filter_params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {cte_sql}
                SELECT *
                FROM candidate_rows
                {where_sql}
                {order_sql}
                LIMIT ? OFFSET ?
                """,
                (*base_params, *filter_params, bounded_limit, bounded_offset),
            ).fetchall()
        return {
            "items": [
                _prediction_page_item(
                    row,
                    profile_type=profile_type,
                    positive_label=positive_label,
                    negative_label=negative_label,
                )
                for row in rows
            ],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def embedding_track_ids(self, embedding_key: str) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT track_id FROM embeddings WHERE embedding_key = ?",
                (embedding_key,),
            ).fetchall()
        return {int(row["track_id"]) for row in rows}

    def load_embedding_matrix(self, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> tuple[list[Track], np.ndarray]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR}
                FROM tracks t
                JOIN embeddings e ON e.track_id = t.id
                WHERE e.embedding_key = ?
                ORDER BY e.track_id
                """,
                (embedding_key,),
            ).fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        tracks = [LibraryDatabase._row_to_track(row, include_metadata=False) for row in rows]
        vectors = [np.frombuffer(row["vector"], dtype=np.float32).copy() for row in rows]
        return tracks, np.vstack(vectors).astype(np.float32)

    def _validate_schema(self) -> None:
        with self.connect() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "tracks" not in tables:
                raise ValueError("Source database is missing tracks table")
            if "embeddings" not in tables:
                raise ValueError("Source database is missing embeddings table")
            track_columns = _columns(connection, "tracks")
            embedding_columns = _columns(connection, "embeddings")
            missing_track = sorted(REQUIRED_TRACK_COLUMNS - track_columns)
            missing_embedding = sorted(REQUIRED_EMBEDDING_COLUMNS - embedding_columns)
            if missing_track:
                raise ValueError(f"Source tracks table is missing columns: {', '.join(missing_track)}")
            if missing_embedding:
                raise ValueError(f"Source embeddings table is missing columns: {', '.join(missing_embedding)}")


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _clean_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _track_page_filter_sql(
    *,
    query: str,
    syncopated: str,
    bpm_min: float | None,
    bpm_max: float | None,
    liked: str,
    label: str,
    label_keys: tuple[str, ...],
) -> tuple[list[str], list[object]]:
    where_parts: list[str] = []
    params: list[object] = []
    needle = query.strip().casefold()
    if needle:
        like = f"%{needle}%"
        searchable_columns = (
            "LOWER(COALESCE(t.artist, ''))",
            "LOWER(COALESCE(t.title, ''))",
            "LOWER(COALESCE(t.album, ''))",
            "LOWER(t.path)",
            "LOWER(t.metadata_json)",
        )
        where_parts.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns) + ")")
        params.extend([like] * len(searchable_columns))
    if syncopated == "yes":
        where_parts.append("json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif syncopated == "no":
        where_parts.append("COALESCE(json_extract(t.metadata_json, '$.maest_syncopated_rhythm'), 0) != 1")
    elif syncopated != "all":
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    sonara_bpm = _sonara_bpm_sql("t.metadata_json")
    if bpm_min is not None:
        where_parts.append(f"{sonara_bpm} >= ?")
        params.append(float(bpm_min))
    if bpm_max is not None:
        where_parts.append(f"{sonara_bpm} <= ?")
        params.append(float(bpm_max))
    if liked == "yes":
        where_parts.append("EXISTS (SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id)")
    elif liked == "no":
        where_parts.append("NOT EXISTS (SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id)")
    elif liked != "all":
        raise ValueError(f"Unknown liked filter: {liked}")
    if label == "unlabeled":
        where_parts.append("rl.label IS NULL")
    elif label in set(label_keys):
        where_parts.append("rl.label = ?")
        params.append(label)
    elif label != "all":
        raise ValueError(f"Unknown label filter: {label}")
    return where_parts, params


def _track_page_item(row: sqlite3.Row) -> dict[str, object]:
    track = LibraryDatabase._row_to_track(row)
    metadata = track.metadata or {}
    return {
        "id": track.id,
        "path": track.path,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "bpm": _sonara_bpm_from_metadata(metadata),
        "musical_key": track.musical_key,
        "genres": track.genres,
        "genre_scores": track.genre_scores,
        "liked": track.liked,
        "label": row["classifier_label"],
        "label_trained": bool(row["classifier_label_trained"]),
        "maest_syncopated_rhythm": metadata.get("maest_syncopated_rhythm") is True,
        "feature_status": {
            "sonara": isinstance(metadata.get("sonara_features"), dict),
            "mert": bool(row["has_mert_embedding"]),
            "maest": bool(row["has_maest_embedding"]),
        },
    }


def _prediction_page_filter_sql(
    *,
    query: str,
    syncopated: str,
    bpm_min: float | None,
    bpm_max: float | None,
    label: str,
    predicted: str,
    label_keys: tuple[str, ...],
    min_positive: float,
    profile_type: str,
) -> tuple[str, list[object]]:
    where_parts: list[str] = []
    params: list[object] = []
    needle = query.strip().casefold()
    if needle:
        like = f"%{needle}%"
        searchable_columns = (
            "LOWER(COALESCE(source_artist, ''))",
            "LOWER(COALESCE(source_title, ''))",
            "LOWER(COALESCE(source_album, ''))",
            "LOWER(COALESCE(source_path, ''))",
            "LOWER(COALESCE(source_metadata_json, ''))",
        )
        where_parts.append("source_row_id IS NOT NULL")
        where_parts.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns) + ")")
        params.extend([like] * len(searchable_columns))
    if syncopated == "yes":
        where_parts.append("source_row_id IS NOT NULL")
        where_parts.append("json_extract(source_metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif syncopated == "no":
        where_parts.append("source_row_id IS NOT NULL")
        where_parts.append("COALESCE(json_extract(source_metadata_json, '$.maest_syncopated_rhythm'), 0) != 1")
    elif syncopated != "all":
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    sonara_bpm = _sonara_bpm_sql("source_metadata_json")
    if bpm_min is not None:
        where_parts.append("source_row_id IS NOT NULL")
        where_parts.append(f"{sonara_bpm} >= ?")
        params.append(float(bpm_min))
    if bpm_max is not None:
        where_parts.append("source_row_id IS NOT NULL")
        where_parts.append(f"{sonara_bpm} <= ?")
        params.append(float(bpm_max))
    if label == "unlabeled":
        where_parts.append("classifier_label IS NULL")
    elif label in set(label_keys):
        where_parts.append("classifier_label = ?")
        params.append(label)
    elif label != "all":
        raise ValueError(f"Unknown label filter: {label}")
    if predicted != "all":
        where_parts.append("predicted_label = ?")
        params.append(predicted)
    threshold_column = "confidence" if profile_type == "multiclass" else "positive_probability"
    if min_positive > 0.0:
        where_parts.append(f"{threshold_column} >= ?")
        params.append(float(min_positive))
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, params


def _prediction_page_order_sql(*, probability_focus: str, profile_type: str) -> str:
    path_expr = "LOWER(COALESCE(source_path, prediction_path, ''))"
    if profile_type == "multiclass":
        if probability_focus == "balanced":
            return f"ORDER BY confidence ASC, {path_expr} ASC"
        return f"ORDER BY confidence DESC, {path_expr} ASC"
    if probability_focus == "negative_highest":
        return f"ORDER BY negative_probability DESC, confidence DESC, {path_expr} ASC"
    if probability_focus == "balanced":
        return f"ORDER BY ABS(positive_probability - negative_probability) ASC, confidence DESC, {path_expr} ASC"
    return f"ORDER BY positive_probability DESC, confidence DESC, {path_expr} ASC"


def _track_page_order_sql(*, order: str, liked: str = "all", collection: bool = False) -> str:
    path_expr = "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    if collection:
        return "ORDER BY rct.position ASC, t.id"
    if liked == "yes":
        return f"ORDER BY (SELECT tl.liked_at FROM track_likes tl WHERE tl.track_id = t.id) ASC, {path_expr}"
    if order == "normal":
        return f"ORDER BY {path_expr}"
    if order == "random":
        return f"ORDER BY rhythm_lab_random_rank(?, t.id), {path_expr}"
    raise ValueError(f"Unknown library order: {order}")


def _random_seed_value(seed: object) -> int:
    try:
        value = int(seed)
    except (TypeError, ValueError) as error:
        raise ValueError("Library random seed must be an integer") from error
    return max(0, value)


def _stable_random_rank(seed: object, track_id: object) -> int:
    payload = f"{int(seed)}:{int(track_id)}".encode("ascii")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) & 0x7FFFFFFFFFFFFFFF


def _prediction_page_item(
    row: sqlite3.Row,
    *,
    profile_type: str,
    positive_label: str,
    negative_label: str,
) -> dict[str, object]:
    metadata = metadata_from_json(row["source_metadata_json"]) if row["source_row_id"] is not None else {}
    genres, genre_scores = genres_from_metadata(metadata) if row["source_row_id"] is not None else ([], None)
    probabilities = _probabilities_from_json(row["probabilities_json"])
    return {
        "id": int(row["source_track_id"]),
        "source_track_id": int(row["source_track_id"]),
        "path": row["source_path"] or row["prediction_path"],
        "artist": row["source_artist"] if row["source_row_id"] is not None else row["prediction_artist"],
        "title": row["source_title"] if row["source_row_id"] is not None else row["prediction_title"],
        "bpm": _sonara_bpm_from_metadata(metadata),
        "liked": bool(row["liked"]) if row["source_row_id"] is not None else False,
        "label": row["classifier_label"],
        "label_trained": bool(row["classifier_label_trained"]),
        "predicted_label": row["predicted_label"],
        "confidence": float(row["confidence"]),
        "profile_type": profile_type,
        "positive_probability": float(row["positive_probability"]),
        "negative_probability": float(row["negative_probability"]),
        "positive_label": positive_label,
        "negative_label": negative_label,
        "probabilities": probabilities,
        "feature_set": row["feature_set"],
        "model_artifact": row["model_artifact"],
        "genres": genres,
        "genre_scores": genre_scores,
        "maest_syncopated_rhythm": metadata.get("maest_syncopated_rhythm") is True,
        "feature_status": {
            "sonara": isinstance(metadata.get("sonara_features"), dict),
            "mert": bool(row["has_mert_embedding"]),
            "maest": bool(row["has_maest_embedding"]),
        },
    }


def _probabilities_from_json(payload: object) -> dict[str, object]:
    try:
        probabilities = json.loads(str(payload))
    except json.JSONDecodeError:
        return {}
    return probabilities if isinstance(probabilities, dict) else {}


def _json_probability_path(label: str) -> str:
    return f"$.{label}"


def _sonara_bpm_sql(metadata_column: str) -> str:
    return (
        "CASE "
        f"WHEN json_type({metadata_column}, '$.sonara_features.bpm.value') IN ('integer', 'real', 'text') "
        f"THEN CAST(json_extract({metadata_column}, '$.sonara_features.bpm.value') AS REAL) "
        f"WHEN json_type({metadata_column}, '$.sonara_features.bpm') IN ('integer', 'real', 'text') "
        f"THEN CAST(json_extract({metadata_column}, '$.sonara_features.bpm') AS REAL) "
        "ELSE NULL END"
    )


def _sonara_bpm_from_metadata(metadata: dict[str, object]) -> float | None:
    features = metadata.get("sonara_features")
    if not isinstance(features, dict):
        return None
    value = features.get("bpm")
    if isinstance(value, dict):
        value = value.get("value")
    return optional_float(value)

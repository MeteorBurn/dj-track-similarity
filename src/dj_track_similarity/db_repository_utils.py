from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .metadata_payload import string_or_none


DEFAULT_EMBEDDING_KEY = "mert"
MAEST_EMBEDDING_KEY = "maest"
LIBRARY_ROOT_SETTING_KEY = "library_root"
SYNCOPATED_RHYTHM_GENRES = (
    "Breakbeat",
    "Breakcore",
    "Breaks",
    "Progressive Breaks",
    "Broken Beat",
    "Drum n Bass",
    "Jungle",
    "Halftime",
    "Juke",
    "UK Garage",
    "Speed Garage",
    "Bassline",
    "Electro",
)


def normalize_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _limit_sql(limit: int | None) -> tuple[str, tuple[int, ...]]:
    if limit is None:
        return "", ()
    return "LIMIT ?", (max(0, int(limit)),)


def _embedding_keys_for_track(connection: sqlite3.Connection, track_id: int) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT embedding_key FROM embeddings WHERE track_id = ?",
        (int(track_id),),
    ).fetchall()
    return tuple(str(row["embedding_key"]) for row in rows)


def _classifier_scores_from_row(row: sqlite3.Row) -> dict[str, dict[str, object]] | None:
    raw = row["classifier_scores_json"]
    if raw is None:
        return None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def _set_maest_metadata(metadata: dict[str, object], *, model_name: str, genres: list[dict[str, object]]) -> None:
    for key in ("maest_model", "maest_genres", "maest_syncopated_rhythm"):
        metadata.pop(key, None)
    metadata["maest_model"] = model_name
    metadata["maest_genres"] = genres
    metadata["maest_syncopated_rhythm"] = _has_syncopated_rhythm_genre(genres)


def _has_syncopated_rhythm_genre(genres: list[dict[str, object]]) -> bool:
    syncopated = {genre.lower() for genre in SYNCOPATED_RHYTHM_GENRES}
    for genre in genres:
        label = string_or_none(genre.get("label"))
        if label and label.lower() in syncopated:
            return True
    return False


def _normalize_root(path: str | Path) -> str:
    normalized = normalize_path(path).rstrip("/")
    if not normalized:
        raise ValueError("Library root must not be empty")
    return normalized


def _relocate_path(path: str, old_root: str, new_root: str) -> str | None:
    path_key = path.casefold()
    old_key = old_root.casefold()
    if path_key == old_key:
        return new_root
    prefix = f"{old_key}/"
    if not path_key.startswith(prefix):
        return None
    relative = path[len(old_root) :].lstrip("/")
    return f"{new_root}/{relative}" if relative else new_root

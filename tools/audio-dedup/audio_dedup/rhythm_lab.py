from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from dj_track_similarity.db.tracks import ordinal_path_key
from dj_track_similarity.track_models import TrackIdentity

from . import report_selection as report_selection_module
from . import values as values_module


# Rhythm Lab tables whose rows name one file: (table, catalog, track, path column).
_FILE_SNAPSHOT_COLUMNS = (
    ("track_sightings", "catalog_uuid", "track_uuid", "selected_path"),
    ("classifier_labels", "last_catalog_uuid", "last_track_uuid", "last_selected_path"),
    ("classifier_label_queue", "catalog_uuid", "track_uuid", "selected_path"),
    ("classifier_predictions", "catalog_uuid", "track_uuid", "selected_path"),
    ("review_collection_tracks", "catalog_uuid", "track_uuid", "selected_path"),
)


def cleanup_rhythm_lab_database(
    rhythm_lab_db: Path | None,
    identities: Iterable[TrackIdentity],
    files: Iterable[tuple[str, str]] = (),
) -> int:
    """Delete the Rhythm Lab rows that name a deleted file; return the rows deleted.

    A row names a deleted file by its snapshot identity in the deleting
    library, or, in any library, by the file's path together with its content
    key (``files`` holds ``(content_key, file_path)`` pairs). It goes even if a
    byte-identical copy survives; rows naming the same path with other content,
    or any other file, stay. Deleted labels also come off their profile's
    training checkpoint, floored at zero. Collections themselves stay, and
    tables the file lacks are skipped.
    """
    selected_identities = report_selection_module._unique_identities(identities)
    selected_files = sorted({(content_key, ordinal_path_key(path)) for content_key, path in files})
    if not selected_identities or rhythm_lab_db is None:
        return 0
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False)
    if not selected_db.exists():
        return 0
    deleted_rows = 0
    deleted_labels: Counter[tuple[str, str]] = Counter()
    connection = sqlite3.connect(selected_db)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        # Python's lower(), as the library keys paths; SQLite's folds only ASCII.
        connection.create_function("ordinal_path_key", 1, ordinal_path_key, deterministic=True)
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        connection.execute("BEGIN IMMEDIATE")
        for table, catalog_column, track_column, path_column in _FILE_SNAPSHOT_COLUMNS:
            if table not in tables:
                continue
            predicates = [
                _identity_predicate(chunk, catalog_column, track_column)
                for chunk in values_module._chunks(list(selected_identities), 200)
            ] + [
                _file_predicate(chunk, path_column)
                for chunk in values_module._chunks(selected_files, 200)
            ]
            for predicate_sql, parameters in predicates:
                if table == "classifier_labels":
                    rows = connection.execute(
                        f"DELETE FROM {table} WHERE {predicate_sql} RETURNING classifier_key, label",
                        parameters,
                    ).fetchall()
                    deleted_labels.update((str(key), str(label)) for key, label in rows)
                    deleted_rows += len(rows)
                else:
                    deleted_rows += connection.execute(
                        f"DELETE FROM {table} WHERE {predicate_sql}",
                        parameters,
                    ).rowcount
        if deleted_labels and "classifier_training_checkpoints" in tables:
            _drop_checkpoint_counts(connection, deleted_labels)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()
    return deleted_rows


def _identity_predicate(
    identities: list[TrackIdentity],
    catalog_column: str,
    track_column: str,
) -> tuple[str, tuple[object, ...]]:
    # A row-value IN list is indexed once per statement; an OR of column pairs
    # is evaluated term by term on every row of an unindexed table.
    if not identities:
        raise ValueError("At least one identity is required")
    parameters: list[object] = []
    for identity in identities:
        parameters.extend((identity.catalog_uuid, identity.track_uuid))
    values_sql = ", ".join("(?, ?)" for _ in identities)
    return f"({catalog_column}, {track_column}) IN (VALUES {values_sql})", tuple(parameters)


def _file_predicate(
    files: list[tuple[str, str]],
    path_column: str,
) -> tuple[str, tuple[object, ...]]:
    # The content key leads, so the sightings index narrows rows before the
    # path key is computed.
    parameters = [value for pair in files for value in pair]
    values_sql = ", ".join("(?, ?)" for _ in files)
    return f"(content_key, ordinal_path_key({path_column})) IN (VALUES {values_sql})", tuple(parameters)


def _drop_checkpoint_counts(
    connection: sqlite3.Connection,
    deleted_labels: Counter[tuple[str, str]],
) -> None:
    """Take deleted labels off their profiles' trained counts, floored at zero.

    ``updated_at`` stays: Rhythm Lab shows it as the last training time.
    """
    for classifier_key in sorted({key for key, _label in deleted_labels}):
        row = connection.execute(
            "SELECT counts_json FROM classifier_training_checkpoints WHERE classifier_key = ?",
            (classifier_key,),
        ).fetchone()
        if row is None:
            continue
        counts = json.loads(str(row[0]))
        for (key, label), deleted in deleted_labels.items():
            if key == classifier_key and label in counts:
                counts[label] = max(0, int(counts[label]) - deleted)
        connection.execute(
            "UPDATE classifier_training_checkpoints SET counts_json = ? WHERE classifier_key = ?",
            (
                json.dumps(counts, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                classifier_key,
            ),
        )

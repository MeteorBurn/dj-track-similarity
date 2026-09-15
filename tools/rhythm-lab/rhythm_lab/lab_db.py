from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
from collections.abc import Iterable, Mapping
from typing import Literal

from dj_track_similarity.rhythm_lab_collections import (
    CONTENT_IDENTITY_MIGRATION_COMMAND,
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS,
    ensure_review_collection_schema,
    reject_noncanonical_table,
    sonara_content_key,
    validate_review_collection_schema,
    validate_rhythm_lab_classifier_schema,
)

from .source_db import SourceDatabase, SourceDatabaseIntegrityError, SourceTrack


ClassifierLabelName = Literal["broken", "straight", "ambiguous"]
ProfileType = Literal["binary", "multiclass"]
PROFILE_TYPES: tuple[str, ...] = ("binary", "multiclass")
ProfileLabelRole = Literal["positive", "negative", "review", "class"]
PROFILE_LABEL_ROLES: tuple[str, ...] = ("positive", "negative", "review", "class")
LABEL_QUEUE_MODES: tuple[str, ...] = (
    "uncertainty",
    "hard_negative",
    "diversity",
    "disagreement",
    "high_impact_unlabeled",
)
LABEL_QUEUE_STATES: tuple[str, ...] = (
    "suggested",
    "accepted_for_labeling",
    "labeled",
    "skipped",
    "used_for_training",
    "archived",
)
_PROFILE_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_profiles"]
)
_PROFILE_LABEL_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_profile_labels"]
)
_CLASSIFIER_LABEL_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_labels"]
)
_CLASSIFIER_QUEUE_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_label_queue"]
)
_CLASSIFIER_PREDICTION_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_predictions"]
)
_TRAINING_CHECKPOINT_COLUMNS = set(
    RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["classifier_training_checkpoints"]
)
_SIGHTING_COLUMNS = set(RHYTHM_LAB_CLASSIFIER_TABLE_COLUMNS["track_sightings"])
DEFAULT_TRAINING_MIN_ADDED = 50
DEFAULT_TRAINING_MIN_LABELS = 100
# One definition for CREATE TABLE and for adding the column to a legacy
# profiles table during the content-identity migration.
TRAINING_MIN_LABELS_COLUMN_SQL = (
    f"training_min_labels INTEGER NOT NULL DEFAULT {DEFAULT_TRAINING_MIN_LABELS} "
    "CHECK(training_min_labels >= 2)"
)
PROFILE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LABEL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SQLITE_BUSY_TIMEOUT_MS = 30_000
SQLITE_CACHE_SIZE_KIB = -32_768
_KEY_CHUNK_SIZE = 800


class ContentKeyVersionChanged(RuntimeError):
    """The library carries a SONARA fingerprint version the stored sightings do not."""


@dataclass(frozen=True)
class ClassifierLabel:
    content_key: str
    label: str
    note: str | None = None
    updated_at: str | None = None
    last_catalog_uuid: str | None = None
    last_track_uuid: str | None = None
    last_selected_path: str | None = None


@dataclass(frozen=True)
class ClassifierPredictionWrite:
    content_key: str
    catalog_uuid: str
    track_uuid: str
    selected_path: str
    artist: str | None
    title: str | None
    label: str
    confidence: float
    probabilities_json: str


class PredictionStage:
    """Task-scoped disk staging for one complete candidate refresh.

    Rows are keyed by content, so duplicate files in one library stage once
    (the first track seen wins).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> PredictionStage:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            """
            CREATE TABLE staged_predictions(
                content_key TEXT PRIMARY KEY,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                artist TEXT,
                title TEXT,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL
            ) WITHOUT ROWID
            """
        )
        self._connection = connection
        return self

    def append(
        self,
        predictions: Iterable[ClassifierPredictionWrite],
    ) -> None:
        if self._connection is None:
            raise RuntimeError("Prediction stage is not open")
        values = [
            (
                prediction.content_key,
                prediction.catalog_uuid,
                prediction.track_uuid,
                prediction.selected_path,
                prediction.artist,
                prediction.title,
                prediction.label,
                prediction.confidence,
                prediction.probabilities_json,
            )
            for prediction in predictions
        ]
        if values:
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO staged_predictions(
                    content_key,
                    catalog_uuid,
                    track_uuid,
                    selected_path,
                    artist,
                    title,
                    label,
                    confidence,
                    probabilities_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            if exc_type is None:
                connection.commit()
            else:
                connection.rollback()
        finally:
            connection.close()


@dataclass(frozen=True)
class ClassifierProfileLabel:
    key: str
    name: str
    role: str
    description: str = ""
    position: int = 0


@dataclass(frozen=True)
class ClassifierProfile:
    classifier_key: str
    profile_type: str
    name: str
    description: str
    artifact_dir: str
    artifact_prefix: str
    training_min_added: int
    positive_label: str
    negative_label: str
    labels: tuple[ClassifierProfileLabel, ...]
    # Labels per training class that must resolve in the open library before
    # train-refresh, benchmark and calibrate are allowed.
    training_min_labels: int = DEFAULT_TRAINING_MIN_LABELS
    archived_at: str | None = None

    @property
    def training_label_keys(self) -> tuple[str, ...]:
        if self.profile_type == "multiclass":
            return tuple(label.key for label in self.labels if label.role == "class")
        return (self.positive_label, self.negative_label)

    @property
    def label_keys(self) -> tuple[str, ...]:
        return tuple(label.key for label in self.labels)


class RhythmLabDatabase:
    """Writable classifier-lab state, separate from the read-only source library."""

    def __init__(self, path: str | Path, *, classifier_key: str | None = None) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.classifier_key = _validate_profile_key(classifier_key) if classifier_key is not None else None
        # catalog_uuid -> library storage signature at the last sightings sync.
        self._sighting_signatures: dict[str, tuple[tuple[int, int], ...]] = {}
        if self.path.exists():
            _validate_existing_lab_schema_read_only(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_lab_schema()

    def scoped(self, classifier_key: str) -> "RhythmLabDatabase":
        scoped = object.__new__(type(self))
        scoped.path = self.path
        scoped.classifier_key = _validate_profile_key(classifier_key)
        scoped._sighting_signatures = self._sighting_signatures
        return scoped

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            _configure_lab_connection(connection)
            return connection
        except BaseException:
            connection.close()
            raise

    def _ensure_lab_schema(self) -> None:
        with self.connect() as connection:
            # Validate every existing table before the first DDL statement.
            # This second pass sees committed WAL frames that immutable
            # main-file preflight intentionally ignores.
            _validate_lab_schema_tables(connection)
            create_lab_schema(connection)

    def sync_track_sightings(self, source: SourceDatabase) -> dict[str, object]:
        """Record which current tracks of ``source`` carry which content key.

        Incremental: only tracks that are new or whose identity, path or file
        facts changed since the last sync are re-hashed; sightings of tracks
        that are no longer current are dropped. A library whose fingerprint
        version differs from the stored sightings is refused before any write.
        Repeated calls are no-ops until the library file or its WAL changes.
        """

        signature = source.storage_signature()
        catalog_uuid = source.catalog_uuid
        if self._sighting_signatures.get(catalog_uuid) == signature:
            return {"catalog_uuid": catalog_uuid, "changed": False, "upserted": 0, "deleted": 0}
        connection = sqlite3.connect(self.path.as_uri(), uri=True, timeout=30)
        try:
            _configure_lab_connection(connection)
            connection.create_function(
                "rhythm_lab_content_key",
                2,
                sonara_content_key,
                deterministic=True,
            )
            connection.execute(
                "ATTACH DATABASE ? AS src",
                (f"{source.path.as_uri()}?mode=ro",),
            )
            try:
                require_fingerprint_table(connection, "src")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    upserted, deleted = upsert_track_sightings(
                        connection,
                        alias="src",
                        catalog_uuid=catalog_uuid,
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
            finally:
                connection.execute("DETACH DATABASE src")
        finally:
            connection.close()
        self._sighting_signatures[catalog_uuid] = signature
        return {
            "catalog_uuid": catalog_uuid,
            "changed": True,
            "upserted": upserted,
            "deleted": deleted,
        }

    def representative_sightings(
        self,
        catalog_uuid: str,
        content_keys: Iterable[str],
    ) -> dict[str, int]:
        """``content_key -> lowest current track_id`` in one catalog; unseen keys are absent."""

        clean_catalog = _required_identity_text(catalog_uuid, "catalog_uuid")
        keys = list(dict.fromkeys(str(key) for key in content_keys))
        result: dict[str, int] = {}
        with self.connect() as connection:
            for start in range(0, len(keys), _KEY_CHUNK_SIZE):
                chunk = keys[start : start + _KEY_CHUNK_SIZE]
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT content_key, MIN(track_id) AS track_id
                    FROM track_sightings
                    WHERE catalog_uuid = ? AND content_key IN ({placeholders})
                    GROUP BY content_key
                    """,
                    (clean_catalog, *chunk),
                ).fetchall()
                result.update({str(row["content_key"]): int(row["track_id"]) for row in rows})
        return result

    def content_keys_for_tracks(
        self,
        catalog_uuid: str,
        track_uuids: Iterable[str],
    ) -> dict[str, str]:
        """``track_uuid -> content_key`` from the synced sightings of one catalog."""

        clean_catalog = _required_identity_text(catalog_uuid, "catalog_uuid")
        uuids = list(dict.fromkeys(str(value) for value in track_uuids))
        result: dict[str, str] = {}
        with self.connect() as connection:
            for start in range(0, len(uuids), _KEY_CHUNK_SIZE):
                chunk = uuids[start : start + _KEY_CHUNK_SIZE]
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT track_uuid, content_key
                    FROM track_sightings
                    WHERE catalog_uuid = ? AND track_uuid IN ({placeholders})
                    """,
                    (clean_catalog, *chunk),
                ).fetchall()
                result.update({str(row["track_uuid"]): str(row["content_key"]) for row in rows})
        return result

    def list_profiles(self, *, include_archived: bool = False) -> list[ClassifierProfile]:
        where = "" if include_archived else "WHERE archived_at IS NULL"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT classifier_key
                FROM classifier_profiles
                {where}
                ORDER BY LOWER(name), classifier_key
                """
            ).fetchall()
            return [_get_profile(connection, str(row["classifier_key"])) for row in rows]

    def get_profile(self, classifier_key: str | None = None) -> ClassifierProfile:
        key = _required_profile_key(classifier_key or self.classifier_key)
        with self.connect() as connection:
            return _get_profile(connection, key)

    def _active_profile_key(self) -> str:
        return _required_profile_key(self.classifier_key)

    def create_profile(
        self,
        *,
        classifier_key: str,
        profile_type: str = "binary",
        name: str,
        description: str = "",
        artifact_dir: str | Path | None = None,
        artifact_prefix: str | None = None,
        training_min_added: int = DEFAULT_TRAINING_MIN_ADDED,
        training_min_labels: int = DEFAULT_TRAINING_MIN_LABELS,
        labels: list[dict[str, object] | ClassifierProfileLabel],
    ) -> ClassifierProfile:
        key = _validate_profile_key(classifier_key)
        clean_type = _validate_profile_type(profile_type)
        label_specs = _normalize_profile_labels(labels, profile_type=clean_type)
        positive_label, negative_label = _training_labels_from_specs(label_specs, profile_type=clean_type)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Profile name is required")
        artifact_path = _normalize_artifact_dir(artifact_dir or _default_artifact_dir(key))
        prefix = (artifact_prefix or key.replace("_", "-")).strip()
        if not prefix:
            raise ValueError("Artifact prefix is required")
        min_added = _validate_training_min_added(training_min_added)
        min_labels = _validate_training_min_labels(training_min_labels)
        with self.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO classifier_profiles(
                        classifier_key, profile_type, name, description, artifact_dir, artifact_prefix,
                        training_min_added, training_min_labels, positive_label, negative_label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        clean_type,
                        clean_name,
                        description.strip(),
                        artifact_path,
                        prefix,
                        min_added,
                        min_labels,
                        positive_label,
                        negative_label,
                    ),
                )
                _replace_profile_labels(connection, key, label_specs)
            except sqlite3.IntegrityError as error:
                message = str(error).lower()
                if "profile_name" in message or "index" in message:
                    raise ValueError(f"A profile with this name already exists: {clean_name}") from error
                raise ValueError(f"Profile already exists or is invalid: {key}") from error
        return self.get_profile(key)

    def update_profile(
        self,
        classifier_key: str,
        *,
        profile_type: str | None = None,
        name: str | None = None,
        description: str | None = None,
        artifact_dir: str | Path | None = None,
        artifact_prefix: str | None = None,
        training_min_added: int | None = None,
        training_min_labels: int | None = None,
        labels: list[dict[str, object] | ClassifierProfileLabel] | None = None,
    ) -> ClassifierProfile:
        key = _validate_profile_key(classifier_key)
        with self.connect() as connection:
            current_profile = _get_profile(connection, key)
            clean_type = _validate_profile_type(profile_type) if profile_type is not None else current_profile.profile_type
            if profile_type is not None and clean_type != current_profile.profile_type and labels is None:
                raise ValueError("Changing the profile type requires replacing its labels")
            assignments: list[str] = []
            params: list[object] = []
            if profile_type is not None and clean_type != current_profile.profile_type:
                assignments.append("profile_type = ?")
                params.append(clean_type)
            if name is not None:
                clean_name = name.strip()
                if not clean_name:
                    raise ValueError("Profile name is required")
                assignments.append("name = ?")
                params.append(clean_name)
            if description is not None:
                assignments.append("description = ?")
                params.append(description.strip())
            if artifact_dir is not None:
                assignments.append("artifact_dir = ?")
                params.append(_normalize_artifact_dir(artifact_dir))
            if artifact_prefix is not None:
                prefix = artifact_prefix.strip()
                if not prefix:
                    raise ValueError("Artifact prefix is required")
                assignments.append("artifact_prefix = ?")
                params.append(prefix)
            if training_min_added is not None:
                assignments.append("training_min_added = ?")
                params.append(_validate_training_min_added(training_min_added))
            if training_min_labels is not None:
                assignments.append("training_min_labels = ?")
                params.append(_validate_training_min_labels(training_min_labels))
            if assignments:
                assignments.append("updated_at = CURRENT_TIMESTAMP")
                try:
                    connection.execute(
                        f"UPDATE classifier_profiles SET {', '.join(assignments)} WHERE classifier_key = ?",
                        (*params, key),
                    )
                except sqlite3.IntegrityError as error:
                    message = str(error).lower()
                    if "profile_name" in message or "index" in message:
                        raise ValueError(f"A profile with this name already exists: {name.strip() if name else ''}") from error
                    raise
            if labels is not None:
                label_specs = _normalize_profile_labels(labels, profile_type=clean_type)
                existing = _used_label_keys(connection, key)
                missing = sorted(existing - {label.key for label in label_specs})
                if missing:
                    raise ValueError(
                        "Cannot remove labels that are already used; rename or clear them first: "
                        + ", ".join(missing)
                    )
                positive_label, negative_label = _training_labels_from_specs(label_specs, profile_type=clean_type)
                connection.execute(
                    """
                    UPDATE classifier_profiles
                    SET profile_type = ?, positive_label = ?, negative_label = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE classifier_key = ?
                    """,
                    (clean_type, positive_label, negative_label, key),
                )
                _replace_profile_labels(connection, key, label_specs)
        return self.get_profile(key)

    def delete_profile(
        self,
        *,
        classifier_key: str | None = None,
        name: str | None = None,
    ) -> ClassifierProfile:
        if bool(classifier_key) == bool(name):
            raise ValueError("Provide exactly one of classifier_key or name")
        with self.connect() as connection:
            profile = (
                _get_profile(connection, _validate_profile_key(classifier_key))
                if classifier_key is not None
                else _get_profile_by_name(connection, name or "")
            )
            for table in (
                "classifier_labels",
                "classifier_label_queue",
                "classifier_predictions",
                "classifier_training_checkpoints",
                "classifier_profile_labels",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE classifier_key = ?",
                    (profile.classifier_key,),
                )
            connection.execute(
                "DELETE FROM classifier_profiles WHERE classifier_key = ?",
                (profile.classifier_key,),
            )
        return profile

    def archive_profile(self, classifier_key: str) -> ClassifierProfile:
        key = _validate_profile_key(classifier_key)
        with self.connect() as connection:
            _get_profile(connection, key)
            connection.execute(
                """
                UPDATE classifier_profiles
                SET archived_at = COALESCE(archived_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP
                WHERE classifier_key = ?
                """,
                (key,),
            )
            connection.execute(
                """
                UPDATE classifier_label_queue
                SET state = 'archived', updated_at = CURRENT_TIMESTAMP
                WHERE classifier_key = ?
                """,
                (key,),
            )
        return self.get_profile(key)

    def rename_label_key(
        self,
        classifier_key: str,
        old_key: str,
        new_key: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
    ) -> ClassifierProfile:
        profile_key = _validate_profile_key(classifier_key)
        old_label = _validate_label_key(old_key)
        new_label = _validate_label_key(new_key)
        if old_label == new_label:
            return self.get_profile(profile_key)
        with self.connect() as connection:
            profile = _get_profile(connection, profile_key)
            label_row = connection.execute(
                """
                SELECT label_key, display_name, description
                FROM classifier_profile_labels
                WHERE classifier_key = ? AND label_key = ?
                """,
                (profile_key, old_label),
            ).fetchone()
            if label_row is None:
                raise KeyError(f"Profile {profile_key} has no label {old_label}")
            conflict = connection.execute(
                """
                SELECT 1 FROM classifier_profile_labels
                WHERE classifier_key = ? AND label_key = ?
                """,
                (profile_key, new_label),
            ).fetchone()
            if conflict is not None:
                raise ValueError(f"Profile {profile_key} already has label {new_label}")
            new_name = display_name.strip() if display_name is not None else str(label_row["display_name"])
            new_description = description.strip() if description is not None else str(label_row["description"] or "")
            connection.execute(
                """
                UPDATE classifier_profile_labels
                SET label_key = ?, display_name = ?, description = ?
                WHERE classifier_key = ? AND label_key = ?
                """,
                (new_label, new_name, new_description, profile_key, old_label),
            )
            positive_label = new_label if profile.positive_label == old_label else profile.positive_label
            negative_label = new_label if profile.negative_label == old_label else profile.negative_label
            connection.execute(
                """
                UPDATE classifier_profiles
                SET positive_label = ?, negative_label = ?, updated_at = CURRENT_TIMESTAMP
                WHERE classifier_key = ?
                """,
                (positive_label, negative_label, profile_key),
            )
            connection.execute(
                "UPDATE classifier_labels SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE classifier_key = ? AND label = ?",
                (new_label, profile_key, old_label),
            )
            connection.execute(
                "UPDATE classifier_predictions SET label = ?, updated_at = CURRENT_TIMESTAMP WHERE classifier_key = ? AND label = ?",
                (new_label, profile_key, old_label),
            )
            _rename_prediction_probability_key(connection, profile_key, old_label, new_label)
            _rename_checkpoint_count_key(connection, profile_key, old_label, new_label)
        return self.get_profile(profile_key)

    def set_label(
        self,
        track: SourceTrack,
        label: str | None,
        *,
        note: str | None = None,
    ) -> ClassifierLabel | None:
        profile_key = self._active_profile_key()
        content_key = track_content_key(track)
        if label is None or not label.strip():
            with self.connect() as connection:
                connection.execute(
                    """
                    DELETE FROM classifier_labels
                    WHERE classifier_key = ? AND content_key = ?
                    """,
                    (profile_key, content_key),
                )
            return None
        label = label.strip()
        profile = self.get_profile()
        if label not in profile.label_keys:
            raise ValueError(f"Unsupported label: {label}")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_labels(
                    classifier_key,
                    content_key,
                    label,
                    note,
                    last_catalog_uuid,
                    last_track_uuid,
                    last_selected_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(classifier_key, content_key) DO UPDATE SET
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP,
                    last_catalog_uuid = excluded.last_catalog_uuid,
                    last_track_uuid = excluded.last_track_uuid,
                    last_selected_path = excluded.last_selected_path
                """,
                (
                    profile_key,
                    content_key,
                    label,
                    note,
                    track.catalog_uuid,
                    track.track_uuid,
                    track.file_path,
                ),
            )
        return self.label_for_track(track)

    def label_for_track(self, track: SourceTrack) -> ClassifierLabel | None:
        profile_key = self._active_profile_key()
        content_key = track_content_key(track)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT content_key, label, note, updated_at,
                       last_catalog_uuid, last_track_uuid, last_selected_path
                FROM classifier_labels
                WHERE classifier_key = ? AND content_key = ?
                """,
                (profile_key, content_key),
            ).fetchone()
        if row is None:
            return None
        return _classifier_label_from_row(row)

    def label_counts(self, *, catalog_uuid: str | None = None) -> dict[str, int]:
        """Labels per key; with ``catalog_uuid`` only content sighted in that catalog."""

        profile_key = self._active_profile_key()
        where, params = _label_scope(profile_key, catalog_uuid)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT l.label, COUNT(*) AS count
                FROM classifier_labels AS l
                WHERE {where}
                GROUP BY l.label
                """,
                params,
            ).fetchall()
        return {str(row["label"]): int(row["count"]) for row in rows}

    def collection_progress(self, collection_id: int) -> dict[str, object]:
        """Count saved collection content against this profile, across all catalogs."""

        profile_key = self._active_profile_key()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT l.label, COUNT(t.content_key) AS count
                FROM review_collections AS c
                LEFT JOIN review_collection_tracks AS t ON t.collection_id = c.id
                LEFT JOIN classifier_labels AS l
                  ON l.content_key = t.content_key AND l.classifier_key = ?
                WHERE c.id = ?
                GROUP BY l.label
                """,
                (profile_key, collection_id),
            ).fetchall()
        if not rows:
            raise KeyError(f"Review collection not found: {collection_id}")
        return {
            "total": sum(int(row["count"]) for row in rows),
            "labels": {
                str(row["label"]): int(row["count"])
                for row in rows
                if row["label"] is not None
            },
            "unlabeled": next(
                (int(row["count"]) for row in rows if row["label"] is None), 0
            ),
        }

    def upsert_label_queue_items(self, *, mode: str, items: list[dict[str, object]]) -> int:
        profile_key = self._active_profile_key()
        clean_mode = _validate_queue_mode(mode)
        rows: list[tuple[object, ...]] = []
        for item in items:
            sighting = _queue_sighting_from_mapping(item)
            priority = _validate_queue_priority(item.get("priority", 0.0))
            score = _optional_queue_score(item.get("score"))
            reason = item.get("reason", item.get("reason_json", {}))
            reason_payload = reason if isinstance(reason, dict) else {"reason": str(reason)}
            rows.append(
                (
                    profile_key,
                    *sighting,
                    clean_mode,
                    score,
                    priority,
                    _canonical_json(reason_payload),
                )
            )
        if not rows:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO classifier_label_queue(
                    classifier_key,
                    content_key,
                    catalog_uuid,
                    track_uuid,
                    selected_path,
                    mode,
                    score,
                    priority,
                    reason_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(classifier_key, content_key, mode) DO UPDATE SET
                    catalog_uuid = excluded.catalog_uuid,
                    track_uuid = excluded.track_uuid,
                    selected_path = excluded.selected_path,
                    score = excluded.score,
                    priority = excluded.priority,
                    reason_json = excluded.reason_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def label_queue_items(self, *, state: str | None = None) -> list[dict[str, object]]:
        profile_key = self._active_profile_key()
        params: list[object] = [profile_key]
        state_clause = ""
        if state is not None:
            state_clause = "AND state = ?"
            params.append(_validate_queue_state(state))
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, classifier_key, content_key, catalog_uuid, track_uuid,
                       selected_path, mode, score, priority,
                       reason_json, state, created_at, updated_at
                FROM classifier_label_queue
                WHERE classifier_key = ?
                  {state_clause}
                ORDER BY priority DESC, updated_at DESC, content_key
                """,
                tuple(params),
            ).fetchall()
        return [_queue_row_payload(row) for row in rows]

    def mark_queue_item(self, queue_id: int, *, state: str) -> dict[str, object]:
        profile_key = self._active_profile_key()
        clean_queue_id = _positive_integer(queue_id, "queue_id")
        clean_state = _validate_queue_state(state)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE classifier_label_queue
                SET state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND classifier_key = ?
                """,
                (clean_state, clean_queue_id, profile_key),
            )
            if cursor.rowcount == 0:
                raise KeyError(
                    f"Queue item not found for {profile_key}:id={clean_queue_id}"
                )
            row = connection.execute(
                """
                SELECT id, classifier_key, content_key, catalog_uuid, track_uuid,
                       selected_path, mode, score, priority,
                       reason_json, state, created_at, updated_at
                FROM classifier_label_queue
                WHERE id = ? AND classifier_key = ?
                """,
                (clean_queue_id, profile_key),
            ).fetchone()
        assert row is not None
        return _queue_row_payload(row)

    def clear_label_queue(self, *, state: str) -> int:
        profile_key = self._active_profile_key()
        clean_state = _validate_queue_state(state)
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM classifier_label_queue WHERE classifier_key = ? AND state = ?",
                (profile_key, clean_state),
            )
            return int(cursor.rowcount)

    def training_labels(
        self,
        *,
        catalog_uuid: str | None = None,
    ) -> dict[str, str]:
        """``content_key -> training label``; with ``catalog_uuid`` only content sighted there."""

        profile_key = self._active_profile_key()
        training_keys = self.get_profile().training_label_keys
        if not training_keys:
            return {}
        placeholders = ", ".join("?" for _ in training_keys)
        scope, params = _label_scope(profile_key, catalog_uuid)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT l.content_key, l.label
                FROM classifier_labels AS l
                WHERE {scope} AND l.label IN ({placeholders})
                ORDER BY l.content_key
                """,
                (*params, *training_keys),
            ).fetchall()
        return {str(row["content_key"]): str(row["label"]) for row in rows}

    def save_prediction(
        self,
        track: SourceTrack,
        *,
        feature_set: str,
        model_artifact: str | Path,
        label: str,
        confidence: float,
        probabilities: dict[str, float],
    ) -> None:
        self.save_predictions(
            ((track, label, confidence, probabilities),),
            feature_set=feature_set,
            model_artifact=model_artifact,
        )

    def save_predictions(
        self,
        predictions: Iterable[
            tuple[SourceTrack, str, float, dict[str, float]]
        ],
        *,
        feature_set: str,
        model_artifact: str | Path,
    ) -> None:
        writes = [
            prepare_prediction_write(
                track,
                label=label,
                confidence=confidence,
                probabilities=probabilities,
            )
            for track, label, confidence, probabilities in predictions
        ]
        self._write_prediction_rows(
            writes,
            feature_set=feature_set,
            model_artifact=model_artifact,
        )

    def replace_predictions_from_stage(
        self,
        stage_path: str | Path,
        *,
        feature_set: str,
        model_artifact: str | Path,
    ) -> int:
        """Atomically swap the profile's complete disk-staged candidate set into view.

        Predictions are the cache of the last refresh, keyed by content, so the
        whole profile set is replaced regardless of which library produced it.
        """

        profile_key = self._active_profile_key()
        allowed_labels = set(self.get_profile().training_label_keys)
        clean_feature_set = _required_identity_text(feature_set, "feature_set")
        artifact_text = _required_identity_text(
            str(model_artifact),
            "model_artifact",
        )
        stage = Path(stage_path).expanduser().resolve(strict=True)
        deleted = 0
        with self.connect() as connection:
            connection.execute(
                "ATTACH DATABASE ? AS prediction_stage",
                (str(stage),),
            )
            try:
                staged_labels = {
                    str(row[0])
                    for row in connection.execute(
                        """
                        SELECT DISTINCT label
                        FROM prediction_stage.staged_predictions
                        """
                    )
                }
                unsupported = sorted(staged_labels - allowed_labels)
                if unsupported:
                    raise ValueError(
                        "Unsupported predicted label: "
                        + ", ".join(unsupported)
                    )
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    DELETE FROM classifier_predictions
                    WHERE classifier_key = ?
                    """,
                    (profile_key,),
                )
                deleted = int(cursor.rowcount)
                connection.execute(
                    """
                    INSERT INTO classifier_predictions(
                        classifier_key,
                        content_key,
                        catalog_uuid,
                        track_uuid,
                        selected_path,
                        artist,
                        title,
                        feature_set,
                        model_artifact,
                        label,
                        confidence,
                        probabilities_json
                    )
                    SELECT ?, content_key, catalog_uuid, track_uuid,
                           selected_path, artist, title, ?, ?, label,
                           confidence, probabilities_json
                    FROM prediction_stage.staged_predictions
                    """,
                    (profile_key, clean_feature_set, artifact_text),
                )
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.execute("DETACH DATABASE prediction_stage")
        return deleted

    def _write_prediction_rows(
        self,
        predictions: list[ClassifierPredictionWrite],
        *,
        feature_set: str,
        model_artifact: str | Path,
    ) -> None:
        profile_key = self._active_profile_key()
        allowed_labels = set(self.get_profile().training_label_keys)
        unsupported = sorted(
            {prediction.label for prediction in predictions} - allowed_labels
        )
        if unsupported:
            raise ValueError(
                "Unsupported predicted label: "
                + ", ".join(unsupported)
            )
        clean_feature_set = _required_identity_text(feature_set, "feature_set")
        artifact_text = _required_identity_text(
            str(model_artifact),
            "model_artifact",
        )
        values = [
            (
                profile_key,
                prediction.content_key,
                prediction.catalog_uuid,
                prediction.track_uuid,
                prediction.selected_path,
                prediction.artist,
                prediction.title,
                clean_feature_set,
                artifact_text,
                prediction.label,
                prediction.confidence,
                prediction.probabilities_json,
            )
            for prediction in predictions
        ]
        if not values:
            return
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO classifier_predictions(
                    classifier_key,
                    content_key,
                    catalog_uuid,
                    track_uuid,
                    selected_path,
                    artist,
                    title,
                    feature_set,
                    model_artifact,
                    label,
                    confidence,
                    probabilities_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    classifier_key,
                    content_key,
                    feature_set,
                    model_artifact
                ) DO UPDATE SET
                    catalog_uuid = excluded.catalog_uuid,
                    track_uuid = excluded.track_uuid,
                    selected_path = excluded.selected_path,
                    artist = excluded.artist,
                    title = excluded.title,
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )

    def predictions(self) -> list[dict[str, object]]:
        profile_key = self._active_profile_key()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT rowid AS prediction_rowid, content_key, catalog_uuid, track_uuid,
                       selected_path, feature_set,
                       model_artifact, label, confidence, probabilities_json,
                       artist, title, updated_at
                FROM classifier_predictions
                WHERE classifier_key = ?
                ORDER BY confidence ASC, selected_path
                """,
                (profile_key,),
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            try:
                probabilities = json.loads(str(row["probabilities_json"]))
            except json.JSONDecodeError:
                probabilities = {}
            result.append(
                {
                    "prediction_rowid": int(row["prediction_rowid"]),
                    "content_key": str(row["content_key"]),
                    "catalog_uuid": str(row["catalog_uuid"]),
                    "track_uuid": str(row["track_uuid"]),
                    "feature_set": str(row["feature_set"]),
                    "model_artifact": str(row["model_artifact"]),
                    "label": str(row["label"]),
                    "confidence": float(row["confidence"]),
                    "probabilities": probabilities,
                    "selected_path": str(row["selected_path"]),
                    "artist": row["artist"],
                    "title": row["title"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def prune_predictions(self, *, feature_set: str, keep_model_artifact: str | Path) -> int:
        profile_key = self._active_profile_key()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM classifier_predictions
                WHERE classifier_key = ?
                  AND feature_set = ?
                  AND model_artifact != ?
                """,
                (profile_key, feature_set, str(keep_model_artifact)),
            )
            return int(cursor.rowcount)

    def training_checkpoint(self) -> dict[str, object]:
        profile_key = self._active_profile_key()
        training_keys = self.get_profile().training_label_keys
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT counts_json, model_artifact, updated_at
                FROM classifier_training_checkpoints
                WHERE classifier_key = ?
                """,
                (profile_key,),
            ).fetchone()
        if row is None:
            return {
                "counts": {label: 0 for label in training_keys},
                "model_artifact": None,
                "updated_at": None,
            }
        try:
            counts = json.loads(str(row["counts_json"]))
        except json.JSONDecodeError:
            counts = {}
        return {
            "counts": _training_counts_payload(counts, training_keys) if isinstance(counts, dict) else {label: 0 for label in training_keys},
            "model_artifact": row["model_artifact"],
            "updated_at": row["updated_at"],
        }

    def record_training_checkpoint(self, counts: dict[str, int], *, model_artifact: str | Path) -> None:
        profile_key = self._active_profile_key()
        payload = _canonical_json(
            _training_counts_payload(counts, self.get_profile().training_label_keys)
        )
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
                (profile_key, payload, str(model_artifact)),
            )


def track_content_key(track: SourceTrack) -> str:
    """The persisted identity of a current source track; unfingerprinted tracks have none."""

    if not isinstance(track, SourceTrack):
        raise TypeError("track must be a SourceTrack")
    if not track.content_key:
        raise ValueError("Track has no SONARA fingerprint; analyze it in the main app first")
    return track.content_key


def prepare_prediction_write(
    track: SourceTrack,
    *,
    label: str,
    confidence: float,
    probabilities: Mapping[str, float],
) -> ClassifierPredictionWrite:
    content_key = track_content_key(track)
    confidence_value = _finite_number(confidence, "confidence")
    clean_probabilities = {
        str(key): _finite_number(value, f"probabilities[{key!r}]")
        for key, value in probabilities.items()
    }
    tags = track.file_tags
    return ClassifierPredictionWrite(
        content_key=content_key,
        catalog_uuid=track.catalog_uuid,
        track_uuid=track.track_uuid,
        selected_path=track.file_path,
        artist=tags.artist if tags is not None else None,
        title=tags.title if tags is not None else None,
        label=str(label),
        confidence=confidence_value,
        probabilities_json=_canonical_json(clean_probabilities),
    )


def require_fingerprint_table(connection: sqlite3.Connection, alias: str) -> None:
    """Refuse a library that was never fingerprinted; content identity needs it."""

    row = connection.execute(
        f"SELECT 1 FROM {alias}.sqlite_master WHERE type = 'table' AND name = 'sonara_fingerprints'"
    ).fetchone()
    if row is None:
        raise SourceDatabaseIntegrityError(
            "Library has no sonara_fingerprints table; run SONARA analysis in the main app first"
        )


def upsert_track_sightings(
    connection: sqlite3.Connection,
    *,
    alias: str,
    catalog_uuid: str,
) -> tuple[int, int]:
    """Bring ``main.track_sightings`` for one catalog in line with the attached library.

    ``rhythm_lab_content_key`` must be registered on ``connection`` and the
    caller owns the transaction. Only tracks that are new or changed against
    the stored sighting are read from ``sonara_fingerprints`` and hashed.
    Returns ``(upserted, deleted)``.
    """

    connection.execute("DROP TABLE IF EXISTS temp.sighting_candidates")
    connection.execute("DROP TABLE IF EXISTS temp.sighting_rows")
    connection.execute(
        """
        CREATE TEMP TABLE sighting_candidates(
            track_id INTEGER NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            file_modified_ns INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        INSERT INTO temp.sighting_candidates(
            track_id, track_uuid, selected_path, file_size_bytes, file_modified_ns
        )
        SELECT t.track_id, t.track_uuid, t.file_path, t.file_size_bytes, t.file_modified_ns
        FROM {alias}.tracks AS t
        LEFT JOIN main.track_sightings AS sg
          ON sg.catalog_uuid = ? AND sg.track_uuid = t.track_uuid
        WHERE t.missing_since IS NULL
          AND (
              sg.track_uuid IS NULL
              OR sg.track_id != t.track_id
              OR sg.selected_path != t.file_path
              OR sg.file_size_bytes != t.file_size_bytes
              OR sg.file_modified_ns != t.file_modified_ns
          )
        """,
        (catalog_uuid,),
    )
    connection.execute(
        """
        CREATE TEMP TABLE sighting_rows(
            content_key TEXT NOT NULL,
            track_id INTEGER NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            file_modified_ns INTEGER NOT NULL,
            fingerprint_version INTEGER NOT NULL,
            fingerprint_analyzed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        INSERT INTO temp.sighting_rows(
            content_key, track_id, track_uuid, selected_path, file_size_bytes,
            file_modified_ns, fingerprint_version, fingerprint_analyzed_at
        )
        SELECT rhythm_lab_content_key(fp.fingerprint_version, fp.fingerprint_base64),
               c.track_id, c.track_uuid, c.selected_path, c.file_size_bytes,
               c.file_modified_ns, fp.fingerprint_version, fp.analyzed_at
        FROM temp.sighting_candidates AS c
        JOIN {alias}.sonara_fingerprints AS fp
          ON fp.track_id = c.track_id AND fp.track_uuid = c.track_uuid
        """
    )
    stored_versions = {
        int(row[0])
        for row in connection.execute(
            "SELECT DISTINCT fingerprint_version FROM main.track_sightings"
        )
    }
    incoming_versions = {
        int(row[0])
        for row in connection.execute(
            "SELECT DISTINCT fingerprint_version FROM temp.sighting_rows"
        )
    }
    if stored_versions and incoming_versions - stored_versions:
        raise ContentKeyVersionChanged(
            "SONARA fingerprint version changed "
            f"(labels database {sorted(stored_versions)}, library {sorted(incoming_versions)}); "
            "labels are bound to the stored version. Before syncing this library, "
            f"rekey them with `{CONTENT_IDENTITY_MIGRATION_COMMAND} --rekey`"
        )
    cursor = connection.execute(
        """
        INSERT INTO main.track_sightings(
            content_key, catalog_uuid, track_id, track_uuid, selected_path,
            file_size_bytes, file_modified_ns, fingerprint_version,
            fingerprint_analyzed_at
        )
        SELECT content_key, ?, track_id, track_uuid, selected_path,
               file_size_bytes, file_modified_ns, fingerprint_version,
               fingerprint_analyzed_at
        FROM temp.sighting_rows
        WHERE true
        ON CONFLICT(catalog_uuid, track_uuid) DO UPDATE SET
            content_key = excluded.content_key,
            track_id = excluded.track_id,
            selected_path = excluded.selected_path,
            file_size_bytes = excluded.file_size_bytes,
            file_modified_ns = excluded.file_modified_ns,
            fingerprint_version = excluded.fingerprint_version,
            fingerprint_analyzed_at = excluded.fingerprint_analyzed_at,
            seen_at = CURRENT_TIMESTAMP
        """,
        (catalog_uuid,),
    )
    upserted = int(cursor.rowcount)
    cursor = connection.execute(
        f"""
        DELETE FROM main.track_sightings
        WHERE catalog_uuid = ?
          AND NOT EXISTS (
              SELECT 1 FROM {alias}.tracks AS t
              WHERE t.track_uuid = track_sightings.track_uuid
                AND t.track_id = track_sightings.track_id
                AND t.missing_since IS NULL
          )
        """,
        (catalog_uuid,),
    )
    deleted = int(cursor.rowcount)
    connection.execute("DROP TABLE temp.sighting_rows")
    connection.execute("DROP TABLE temp.sighting_candidates")
    return upserted, deleted


_LAB_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_classifier_labels_lookup
    ON classifier_labels(classifier_key, label, content_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_classifier_predictions_lookup
    ON classifier_predictions(classifier_key, label, confidence, content_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_classifier_predictions_latest
    ON classifier_predictions(
        classifier_key,
        content_key,
        updated_at DESC,
        model_artifact DESC
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_classifier_predictions_model
    ON classifier_predictions(classifier_key, feature_set, model_artifact)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_classifier_label_queue_state
    ON classifier_label_queue(classifier_key, state, priority DESC, updated_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_track_sightings_content
    ON track_sightings(content_key, catalog_uuid, track_id)
    """,
)


def create_lab_schema(connection: sqlite3.Connection) -> None:
    """Create every missing lab table and index with single statements.

    Existing tables must already carry the current layout. No ``executescript``
    is used, so a caller's open transaction stays open.
    """

    _ensure_profile_tables(connection)
    _ensure_classifier_tables(connection)
    ensure_review_collection_schema(connection)
    for statement in _LAB_INDEX_STATEMENTS:
        connection.execute(statement)


def _label_scope(profile_key: str, catalog_uuid: str | None) -> tuple[str, list[object]]:
    """WHERE fragment over ``classifier_labels AS l``: the profile, optionally one catalog's sightings."""

    where = "l.classifier_key = ?"
    params: list[object] = [profile_key]
    if catalog_uuid is not None:
        where += (
            " AND EXISTS (SELECT 1 FROM track_sightings AS sg"
            " WHERE sg.content_key = l.content_key AND sg.catalog_uuid = ?)"
        )
        params.append(_required_identity_text(catalog_uuid, "catalog_uuid"))
    return where, params


def _ensure_profile_tables(connection: sqlite3.Connection) -> None:
    reject_noncanonical_table(
        connection,
        table="classifier_profiles",
        expected_columns=_PROFILE_COLUMNS,
    )
    reject_noncanonical_table(
        connection,
        table="classifier_profile_labels",
        expected_columns=_PROFILE_LABEL_COLUMNS,
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS classifier_profiles (
            classifier_key TEXT PRIMARY KEY,
            profile_type TEXT NOT NULL DEFAULT 'binary' CHECK(profile_type IN ('binary', 'multiclass')),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            artifact_dir TEXT NOT NULL,
            artifact_prefix TEXT NOT NULL,
            training_min_added INTEGER NOT NULL DEFAULT 50 CHECK(training_min_added >= 1),
            {TRAINING_MIN_LABELS_COLUMN_SQL},
            positive_label TEXT NOT NULL,
            negative_label TEXT NOT NULL,
            archived_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS classifier_profile_labels (
            classifier_key TEXT NOT NULL,
            label_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL CHECK(role IN ('positive', 'negative', 'review', 'class')),
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(classifier_key, label_key),
            FOREIGN KEY(classifier_key) REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
        """
    )
    _ensure_unique_profile_names(connection)


def _ensure_unique_profile_names(connection: sqlite3.Connection) -> None:
    duplicates = connection.execute(
        """
        SELECT LOWER(TRIM(name)) AS normalized_name, GROUP_CONCAT(classifier_key, ', ') AS classifier_keys
        FROM classifier_profiles
        GROUP BY LOWER(TRIM(name))
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    if duplicates:
        details = "; ".join(
            f"{row['normalized_name']}: {row['classifier_keys']}"
            for row in duplicates
        )
        raise ValueError(f"Duplicate classifier profile names must be resolved before opening Rhythm Lab: {details}")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_classifier_profiles_profile_name_unique
        ON classifier_profiles(LOWER(TRIM(name)))
        """
    )


def _ensure_classifier_tables(connection: sqlite3.Connection) -> None:
    for table, columns in (
        ("classifier_labels", _CLASSIFIER_LABEL_COLUMNS),
        ("classifier_label_queue", _CLASSIFIER_QUEUE_COLUMNS),
        ("classifier_predictions", _CLASSIFIER_PREDICTION_COLUMNS),
        ("classifier_training_checkpoints", _TRAINING_CHECKPOINT_COLUMNS),
        ("track_sightings", _SIGHTING_COLUMNS),
    ):
        reject_noncanonical_table(
            connection,
            table=table,
            expected_columns=columns,
        )
    connection.execute(_classifier_labels_table_sql("classifier_labels"))
    connection.execute(_classifier_label_queue_table_sql("classifier_label_queue"))
    connection.execute(_classifier_predictions_table_sql("classifier_predictions"))
    connection.execute(_classifier_training_checkpoints_table_sql("classifier_training_checkpoints"))
    connection.execute(_track_sightings_table_sql("track_sightings"))


def _validate_existing_lab_schema_read_only(path: Path) -> None:
    with sqlite3.connect(
        f"{path.as_uri()}?mode=ro&immutable=1",
        uri=True,
        timeout=30,
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        _validate_lab_schema_tables(connection)


def _configure_lab_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute(f"PRAGMA cache_size = {SQLITE_CACHE_SIZE_KIB}")
    journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    if journal_mode is None or str(journal_mode[0]).lower() != "wal":
        actual = None if journal_mode is None else journal_mode[0]
        raise RuntimeError(
            "Rhythm Lab SQLite database could not enter WAL journal mode; "
            f"got {actual!r}"
        )


def _validate_lab_schema_tables(connection: sqlite3.Connection) -> None:
    """Reject foreign layouts before any DDL; every table is judged by its column set."""

    validate_rhythm_lab_classifier_schema(connection)
    validate_review_collection_schema(connection)


def _get_profile(connection: sqlite3.Connection, classifier_key: str) -> ClassifierProfile:
    row = connection.execute(
        """
        SELECT classifier_key, profile_type, name, description, artifact_dir, artifact_prefix,
               training_min_added, training_min_labels, positive_label, negative_label, archived_at
        FROM classifier_profiles
        WHERE classifier_key = ?
        """,
        (classifier_key,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown profile: {classifier_key}")
    label_rows = connection.execute(
        """
        SELECT label_key, display_name, description, role, position
        FROM classifier_profile_labels
        WHERE classifier_key = ?
        ORDER BY position, label_key
        """,
        (classifier_key,),
    ).fetchall()
    labels = tuple(
        ClassifierProfileLabel(
            key=str(label_row["label_key"]),
            name=str(label_row["display_name"]),
            description=str(label_row["description"] or ""),
            role=str(label_row["role"]),
            position=int(label_row["position"]),
        )
        for label_row in label_rows
    )
    return ClassifierProfile(
        classifier_key=str(row["classifier_key"]),
        profile_type=str(row["profile_type"] or "binary"),
        name=str(row["name"]),
        description=str(row["description"] or ""),
        artifact_dir=str(row["artifact_dir"]),
        artifact_prefix=str(row["artifact_prefix"]),
        training_min_added=int(row["training_min_added"] or DEFAULT_TRAINING_MIN_ADDED),
        positive_label=str(row["positive_label"]),
        negative_label=str(row["negative_label"]),
        labels=labels,
        training_min_labels=int(row["training_min_labels"]),
        archived_at=row["archived_at"],
    )


def _get_profile_by_name(connection: sqlite3.Connection, name: str) -> ClassifierProfile:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Profile name is required")
    row = connection.execute(
        """
        SELECT classifier_key
        FROM classifier_profiles
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
        """,
        (clean_name,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown classifier profile name: {clean_name}")
    return _get_profile(connection, str(row["classifier_key"]))


def _normalize_profile_labels(
    labels: list[dict[str, object] | ClassifierProfileLabel],
    *,
    profile_type: str = "binary",
) -> tuple[ClassifierProfileLabel, ...]:
    if not labels:
        raise ValueError("At least two training labels are required")
    clean_type = _validate_profile_type(profile_type)
    result: list[ClassifierProfileLabel] = []
    seen: set[str] = set()
    for position, raw in enumerate(labels):
        if isinstance(raw, ClassifierProfileLabel):
            key = raw.key
            name = raw.name
            role = raw.role
            description = raw.description
        else:
            key = str(raw.get("key") or raw.get("label_key") or "").strip()
            name = str(raw.get("name") or raw.get("display_name") or key).strip()
            role = str(raw.get("role") or "").strip()
            description = str(raw.get("description") or "").strip()
        key = _validate_label_key(key)
        if key in seen:
            raise ValueError(f"Duplicate label key: {key}")
        if role not in PROFILE_LABEL_ROLES:
            raise ValueError(f"Unsupported label role: {role}")
        if not name:
            raise ValueError(f"Display name is required for label: {key}")
        seen.add(key)
        result.append(ClassifierProfileLabel(key=key, name=name, role=role, description=description, position=position))
    _training_labels_from_specs(tuple(result), profile_type=clean_type)
    return tuple(result)


def _training_labels_from_specs(labels: tuple[ClassifierProfileLabel, ...], *, profile_type: str = "binary") -> tuple[str, str]:
    clean_type = _validate_profile_type(profile_type)
    if clean_type == "multiclass":
        classes = [label.key for label in labels if label.role == "class"]
        unsupported = [label.role for label in labels if label.role != "class"]
        if unsupported:
            raise ValueError("Multiclass profiles support only class labels")
        if len(classes) < 2:
            raise ValueError("A multiclass profile needs at least two class labels")
        return classes[0], classes[1]
    positive = [label.key for label in labels if label.role == "positive"]
    negative = [label.key for label in labels if label.role == "negative"]
    class_labels = [label.key for label in labels if label.role == "class"]
    if class_labels:
        raise ValueError("Class labels require a multiclass profile")
    if len(positive) != 1 or len(negative) != 1:
        raise ValueError("Exactly one positive and one negative training label are required")
    return positive[0], negative[0]


def _replace_profile_labels(
    connection: sqlite3.Connection,
    classifier_key: str,
    labels: tuple[ClassifierProfileLabel, ...],
) -> None:
    connection.execute("DELETE FROM classifier_profile_labels WHERE classifier_key = ?", (classifier_key,))
    connection.executemany(
        """
        INSERT INTO classifier_profile_labels(
            classifier_key, label_key, display_name, description, role, position
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (classifier_key, label.key, label.name, label.description, label.role, label.position)
            for label in labels
        ],
    )


def _used_label_keys(connection: sqlite3.Connection, classifier_key: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT label FROM classifier_labels WHERE classifier_key = ?
        UNION
        SELECT label FROM classifier_predictions WHERE classifier_key = ?
        """,
        (classifier_key, classifier_key),
    ).fetchall()
    return {str(row["label"]) for row in rows}


def _rename_prediction_probability_key(
    connection: sqlite3.Connection,
    classifier_key: str,
    old_key: str,
    new_key: str,
) -> None:
    rows = connection.execute(
        """
        SELECT classifier_key, content_key, feature_set, model_artifact, probabilities_json
        FROM classifier_predictions
        WHERE classifier_key = ?
        """,
        (classifier_key,),
    ).fetchall()
    for row in rows:
        try:
            probabilities = json.loads(str(row["probabilities_json"]))
        except json.JSONDecodeError:
            continue
        if not isinstance(probabilities, dict) or old_key not in probabilities:
            continue
        old_value = probabilities.pop(old_key)
        probabilities[new_key] = old_value
        connection.execute(
            """
            UPDATE classifier_predictions
            SET probabilities_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE classifier_key = ?
              AND content_key = ?
              AND feature_set = ?
              AND model_artifact = ?
            """,
            (
                _canonical_json(probabilities),
                row["classifier_key"],
                row["content_key"],
                row["feature_set"],
                row["model_artifact"],
            ),
        )


def _rename_checkpoint_count_key(
    connection: sqlite3.Connection,
    classifier_key: str,
    old_key: str,
    new_key: str,
) -> None:
    row = connection.execute(
        "SELECT counts_json FROM classifier_training_checkpoints WHERE classifier_key = ?",
        (classifier_key,),
    ).fetchone()
    if row is None:
        return
    try:
        counts = json.loads(str(row["counts_json"]))
    except json.JSONDecodeError:
        return
    if not isinstance(counts, dict) or old_key not in counts:
        return
    old_value = counts.pop(old_key)
    counts[new_key] = old_value
    connection.execute(
        """
        UPDATE classifier_training_checkpoints
        SET counts_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE classifier_key = ?
        """,
        (_canonical_json(counts), classifier_key),
    )


def _training_counts_payload(counts: dict[str, object], training_keys: tuple[str, ...]) -> dict[str, int]:
    return {label: int(counts.get(label, 0)) for label in training_keys}


def _validate_profile_type(profile_type: str) -> str:
    value = str(profile_type or "").strip()
    if value not in PROFILE_TYPES:
        raise ValueError(f"Unsupported profile type: {value}")
    return value


def _validate_training_min_added(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("New labels before retraining must be a positive integer") from error
    if number < 1:
        raise ValueError("New labels before retraining must be at least 1")
    return number


def _validate_training_min_labels(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Minimum labels per class must be an integer") from error
    if number < 2:
        raise ValueError("Minimum labels per class must be at least 2")
    return number


def _validate_profile_key(key: str) -> str:
    value = str(key or "").strip()
    if not PROFILE_KEY_PATTERN.match(value):
        raise ValueError("Profile key may contain only lowercase letters, digits and underscores")
    return value


def _required_profile_key(key: str | None) -> str:
    if key is None or not str(key).strip():
        raise ValueError("Profile key is required")
    return _validate_profile_key(key)


def _validate_label_key(key: str) -> str:
    value = str(key or "").strip()
    if not LABEL_KEY_PATTERN.match(value):
        raise ValueError("Label key may contain only lowercase letters, digits and underscores")
    return value


def _validate_queue_mode(mode: object) -> str:
    value = str(mode or "").strip().lower().replace("-", "_")
    if value not in LABEL_QUEUE_MODES:
        raise ValueError(f"Unsupported label queue mode: {value}")
    return value


def _validate_queue_state(state: object) -> str:
    value = str(state or "").strip().lower().replace("-", "_")
    if value not in LABEL_QUEUE_STATES:
        raise ValueError(f"Unsupported label queue state: {value}")
    return value


def _validate_queue_priority(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Queue priority must be numeric") from error
    if not math.isfinite(number):
        raise ValueError("Queue priority must be finite")
    return number


def _optional_queue_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Queue score must be numeric") from error
    if not math.isfinite(number):
        raise ValueError("Queue score must be finite")
    return number


def _queue_row_payload(row: sqlite3.Row) -> dict[str, object]:
    try:
        reason = json.loads(str(row["reason_json"]))
    except json.JSONDecodeError:
        reason = {}
    return {
        "id": int(row["id"]),
        "classifier_key": str(row["classifier_key"]),
        "content_key": str(row["content_key"]),
        "catalog_uuid": str(row["catalog_uuid"]),
        "track_uuid": str(row["track_uuid"]),
        "selected_path": str(row["selected_path"]),
        "mode": str(row["mode"]),
        "score": float(row["score"]) if row["score"] is not None else None,
        "priority": float(row["priority"]),
        "reason": reason if isinstance(reason, dict) else {},
        "state": str(row["state"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _default_artifact_dir(classifier_key: str) -> Path:
    return Path(__file__).resolve().parents[1] / "profiles" / classifier_key.replace("_", "-")


def _normalize_artifact_dir(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _required_identity_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _queue_sighting_from_mapping(item: Mapping[str, object]) -> tuple[str, str, str, str]:
    """``(content_key, catalog_uuid, track_uuid, selected_path)`` of one queue item."""

    if not isinstance(item, Mapping):
        raise TypeError("queue item must be a mapping")
    return (
        _required_identity_text(item.get("content_key"), "content_key"),
        _required_identity_text(item.get("catalog_uuid"), "catalog_uuid"),
        _required_identity_text(item.get("track_uuid"), "track_uuid"),
        _required_identity_text(
            item.get("selected_path", item.get("file_path")),
            "selected_path",
        ),
    )


def _classifier_label_from_row(row: sqlite3.Row) -> ClassifierLabel:
    return ClassifierLabel(
        content_key=str(row["content_key"]),
        label=str(row["label"]),
        note=row["note"],
        updated_at=row["updated_at"],
        last_catalog_uuid=row["last_catalog_uuid"],
        last_track_uuid=row["last_track_uuid"],
        last_selected_path=row["last_selected_path"],
    )


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number


def _finite_number(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Rhythm Lab JSON payload must contain finite JSON values") from error


def _classifier_labels_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
            content_key TEXT NOT NULL,
            label TEXT NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_catalog_uuid TEXT NOT NULL,
            last_track_uuid TEXT NOT NULL,
            last_selected_path TEXT NOT NULL,
            PRIMARY KEY(classifier_key, content_key),
            FOREIGN KEY(classifier_key)
                REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
    """


def _classifier_label_queue_table_sql(table: str) -> str:
    modes = "', '".join(LABEL_QUEUE_MODES)
    states = "', '".join(LABEL_QUEUE_STATES)
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classifier_key TEXT NOT NULL,
            content_key TEXT NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('{modes}')),
            score REAL,
            priority REAL NOT NULL,
            reason_json TEXT NOT NULL CHECK(json_valid(reason_json)),
            state TEXT NOT NULL DEFAULT 'suggested' CHECK(state IN ('{states}')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(classifier_key, content_key, mode),
            FOREIGN KEY(classifier_key) REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
    """


def _classifier_predictions_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
            content_key TEXT NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            artist TEXT,
            title TEXT,
            feature_set TEXT NOT NULL,
            model_artifact TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(classifier_key, content_key, feature_set, model_artifact),
            FOREIGN KEY(classifier_key)
                REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
    """


def _track_sightings_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            content_key TEXT NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_id INTEGER NOT NULL CHECK(track_id > 0),
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL CHECK(file_size_bytes >= 0),
            file_modified_ns INTEGER NOT NULL CHECK(file_modified_ns >= 0),
            fingerprint_version INTEGER NOT NULL CHECK(fingerprint_version > 0),
            fingerprint_analyzed_at TEXT NOT NULL,
            seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(catalog_uuid, track_uuid)
        ) WITHOUT ROWID
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

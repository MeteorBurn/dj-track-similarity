from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
from collections.abc import Mapping
from typing import Literal

from dj_track_similarity.rhythm_lab_collections import ensure_review_collection_schema

from .source_db import SourceTrack


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
_PROFILE_COLUMNS = {
    "classifier_key",
    "profile_type",
    "name",
    "description",
    "artifact_dir",
    "artifact_prefix",
    "training_min_added",
    "positive_label",
    "negative_label",
    "archived_at",
    "created_at",
    "updated_at",
}
_PROFILE_LABEL_COLUMNS = {
    "classifier_key",
    "label_key",
    "display_name",
    "description",
    "role",
    "position",
    "created_at",
    "updated_at",
}
_CLASSIFIER_LABEL_COLUMNS = {
    "classifier_key",
    "catalog_uuid",
    "track_uuid",
    "content_generation",
    "selected_path",
    "file_size_bytes",
    "file_modified_ns",
    "label",
    "note",
    "updated_at",
}
_CLASSIFIER_QUEUE_COLUMNS = {
    "id",
    "classifier_key",
    "catalog_uuid",
    "track_uuid",
    "content_generation",
    "selected_path",
    "mode",
    "score",
    "priority",
    "reason_json",
    "state",
    "created_at",
    "updated_at",
}
_CLASSIFIER_PREDICTION_COLUMNS = {
    "classifier_key",
    "catalog_uuid",
    "track_uuid",
    "content_generation",
    "selected_path",
    "artist",
    "title",
    "feature_set",
    "model_artifact",
    "label",
    "confidence",
    "probabilities_json",
    "updated_at",
}
_TRAINING_CHECKPOINT_COLUMNS = {
    "classifier_key",
    "counts_json",
    "model_artifact",
    "updated_at",
}
DEFAULT_TRAINING_MIN_ADDED = 50
PROFILE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LABEL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class TrackIdentity:
    catalog_uuid: str
    track_uuid: str
    content_generation: int
    file_path: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_uuid",
            _required_identity_text(self.catalog_uuid, "catalog_uuid"),
        )
        object.__setattr__(
            self,
            "track_uuid",
            _required_identity_text(self.track_uuid, "track_uuid"),
        )
        if (
            isinstance(self.content_generation, bool)
            or not isinstance(self.content_generation, int)
            or self.content_generation <= 0
        ):
            raise ValueError("content_generation must be a positive integer")
        object.__setattr__(
            self,
            "file_path",
            _required_identity_text(self.file_path, "file_path"),
        )


@dataclass(frozen=True)
class ClassifierLabel:
    identity: TrackIdentity
    selected_path: str
    label: str
    note: str | None = None
    updated_at: str | None = None


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
            _ensure_profile_tables(connection)
            _ensure_classifier_tables(connection)
            ensure_review_collection_schema(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_classifier_labels_lookup
                ON classifier_labels(
                    classifier_key,
                    label,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path
                );

                CREATE INDEX IF NOT EXISTS idx_classifier_predictions_lookup
                ON classifier_predictions(
                    classifier_key,
                    label,
                    confidence,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path
                );

                CREATE INDEX IF NOT EXISTS idx_classifier_label_queue_state
                ON classifier_label_queue(classifier_key, state, priority DESC, updated_at);

                CREATE INDEX IF NOT EXISTS idx_classifier_label_queue_identity
                ON classifier_label_queue(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path,
                    mode
                );
                """
            )

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
        return [self.get_profile(str(row["classifier_key"])) for row in rows]

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
        labels: list[dict[str, object] | ClassifierProfileLabel],
    ) -> ClassifierProfile:
        key = _validate_profile_key(classifier_key)
        clean_type = _validate_profile_type(profile_type)
        label_specs = _normalize_profile_labels(labels, profile_type=clean_type)
        positive_label, negative_label = _training_labels_from_specs(label_specs, profile_type=clean_type)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Classifier profile name is required")
        artifact_path = _normalize_artifact_dir(artifact_dir or _default_artifact_dir(key))
        prefix = (artifact_prefix or key.replace("_", "-")).strip()
        if not prefix:
            raise ValueError("Artifact prefix is required")
        min_added = _validate_training_min_added(training_min_added)
        with self.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO classifier_profiles(
                        classifier_key, profile_type, name, description, artifact_dir, artifact_prefix,
                        training_min_added, positive_label, negative_label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        clean_type,
                        clean_name,
                        description.strip(),
                        artifact_path,
                        prefix,
                        min_added,
                        positive_label,
                        negative_label,
                    ),
                )
                _replace_profile_labels(connection, key, label_specs)
            except sqlite3.IntegrityError as error:
                message = str(error).lower()
                if "profile_name" in message or "index" in message:
                    raise ValueError(f"Classifier profile name already exists: {clean_name}") from error
                raise ValueError(f"Classifier profile already exists or is invalid: {key}") from error
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
        labels: list[dict[str, object] | ClassifierProfileLabel] | None = None,
    ) -> ClassifierProfile:
        key = _validate_profile_key(classifier_key)
        with self.connect() as connection:
            current_profile = _get_profile(connection, key)
            clean_type = _validate_profile_type(profile_type) if profile_type is not None else current_profile.profile_type
            if profile_type is not None and clean_type != current_profile.profile_type and labels is None:
                raise ValueError("Changing classifier profile type requires replacing the profile labels")
            assignments: list[str] = []
            params: list[object] = []
            if profile_type is not None and clean_type != current_profile.profile_type:
                assignments.append("profile_type = ?")
                params.append(clean_type)
            if name is not None:
                clean_name = name.strip()
                if not clean_name:
                    raise ValueError("Classifier profile name is required")
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
                        raise ValueError(f"Classifier profile name already exists: {name.strip() if name else ''}") from error
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
                raise KeyError(f"Unknown label for profile {profile_key}: {old_label}")
            conflict = connection.execute(
                """
                SELECT 1 FROM classifier_profile_labels
                WHERE classifier_key = ? AND label_key = ?
                """,
                (profile_key, new_label),
            ).fetchone()
            if conflict is not None:
                raise ValueError(f"Label already exists for profile {profile_key}: {new_label}")
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
        identity = track_identity(track)
        if label is None or not label.strip():
            with self.connect() as connection:
                connection.execute(
                    """
                    DELETE FROM classifier_labels
                    WHERE classifier_key = ?
                      AND catalog_uuid = ?
                      AND track_uuid = ?
                      AND content_generation = ?
                      AND selected_path = ?
                    """,
                    (
                        profile_key,
                        identity.catalog_uuid,
                        identity.track_uuid,
                        identity.content_generation,
                        identity.file_path,
                    ),
                )
            return None
        label = label.strip()
        profile = self.get_profile()
        if label not in profile.label_keys:
            raise ValueError(f"Unsupported classifier label: {label}")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_labels(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path,
                    file_size_bytes,
                    file_modified_ns,
                    label,
                    note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path
                ) DO UPDATE SET
                    file_size_bytes = excluded.file_size_bytes,
                    file_modified_ns = excluded.file_modified_ns,
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile_key,
                    identity.catalog_uuid,
                    identity.track_uuid,
                    identity.content_generation,
                    identity.file_path,
                    track.file_size_bytes,
                    track.file_modified_ns,
                    label,
                    note,
                ),
            )
        return self.label_for_track(identity)

    def label_for_track(self, identity: TrackIdentity) -> ClassifierLabel | None:
        profile_key = self._active_profile_key()
        clean_identity = _require_track_identity(identity)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT catalog_uuid, track_uuid, content_generation,
                       selected_path, label, note, updated_at
                FROM classifier_labels
                WHERE classifier_key = ?
                  AND catalog_uuid = ?
                  AND track_uuid = ?
                  AND content_generation = ?
                  AND selected_path = ?
                """,
                (
                    profile_key,
                    clean_identity.catalog_uuid,
                    clean_identity.track_uuid,
                    clean_identity.content_generation,
                    clean_identity.file_path,
                ),
            ).fetchone()
        if row is None:
            return None
        return _classifier_label_from_row(row)

    def labels_by_identity(self) -> dict[TrackIdentity, ClassifierLabel]:
        profile_key = self._active_profile_key()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT catalog_uuid, track_uuid, content_generation,
                       selected_path, label, note, updated_at
                FROM classifier_labels
                WHERE classifier_key = ?
                """,
                (profile_key,),
            ).fetchall()
        return {
            label.identity: label
            for row in rows
            for label in (_classifier_label_from_row(row),)
        }

    def label_counts(self) -> dict[str, int]:
        profile_key = self._active_profile_key()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT label, COUNT(*) AS count
                FROM classifier_labels
                WHERE classifier_key = ?
                GROUP BY label
                """,
                (profile_key,),
            ).fetchall()
        return {str(row["label"]): int(row["count"]) for row in rows}

    def upsert_label_queue_items(self, *, mode: str, items: list[dict[str, object]]) -> int:
        profile_key = self._active_profile_key()
        clean_mode = _validate_queue_mode(mode)
        rows: list[tuple[object, ...]] = []
        for item in items:
            identity = _identity_from_mapping(item)
            priority = _validate_queue_priority(item.get("priority", 0.0))
            score = _optional_queue_score(item.get("score"))
            reason = item.get("reason", item.get("reason_json", {}))
            reason_payload = reason if isinstance(reason, dict) else {"reason": str(reason)}
            rows.append(
                (
                    profile_key,
                    identity.catalog_uuid,
                    identity.track_uuid,
                    identity.content_generation,
                    identity.file_path,
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
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path,
                    mode,
                    score,
                    priority,
                    reason_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path,
                    mode
                ) DO UPDATE SET
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
                SELECT id, classifier_key, catalog_uuid, track_uuid,
                       content_generation, selected_path, mode, score, priority,
                       reason_json, state, created_at, updated_at
                FROM classifier_label_queue
                WHERE classifier_key = ?
                  {state_clause}
                ORDER BY priority DESC, updated_at DESC,
                         catalog_uuid, track_uuid, content_generation
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
                SELECT id, classifier_key, catalog_uuid, track_uuid,
                       content_generation, selected_path, mode, score, priority,
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

    def training_labels(self) -> dict[TrackIdentity, str]:
        profile_key = self._active_profile_key()
        training_keys = self.get_profile().training_label_keys
        if not training_keys:
            return {}
        placeholders = ", ".join("?" for _ in training_keys)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT catalog_uuid, track_uuid, content_generation,
                       selected_path, label
                FROM classifier_labels
                WHERE classifier_key = ? AND label IN ({placeholders})
                ORDER BY catalog_uuid, track_uuid, content_generation
                """,
                (profile_key, *training_keys),
            ).fetchall()
        return {
            TrackIdentity(
                catalog_uuid=str(row["catalog_uuid"]),
                track_uuid=str(row["track_uuid"]),
                content_generation=int(row["content_generation"]),
                file_path=str(row["selected_path"]),
            ): str(row["label"])
            for row in rows
        }

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
        profile_key = self._active_profile_key()
        if label not in self.get_profile().training_label_keys:
            raise ValueError(f"Unsupported predicted classifier label: {label}")
        identity = track_identity(track)
        confidence_value = _finite_number(confidence, "confidence")
        clean_probabilities = {
            str(key): _finite_number(value, f"probabilities[{key!r}]")
            for key, value in probabilities.items()
        }
        payload = _canonical_json(clean_probabilities)
        tags = track.file_tags
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO classifier_predictions(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
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
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    selected_path,
                    feature_set,
                    model_artifact
                ) DO UPDATE SET
                    artist = excluded.artist,
                    title = excluded.title,
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile_key,
                    identity.catalog_uuid,
                    identity.track_uuid,
                    identity.content_generation,
                    track.file_path,
                    tags.artist if tags is not None else None,
                    tags.title if tags is not None else None,
                    feature_set,
                    str(model_artifact),
                    label,
                    confidence_value,
                    payload,
                ),
            )

    def predictions(self) -> list[dict[str, object]]:
        profile_key = self._active_profile_key()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT rowid AS prediction_rowid, catalog_uuid, track_uuid,
                       content_generation, selected_path, feature_set,
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
                    "catalog_uuid": str(row["catalog_uuid"]),
                    "track_uuid": str(row["track_uuid"]),
                    "content_generation": int(row["content_generation"]),
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


def track_identity(track: SourceTrack) -> TrackIdentity:
    if not isinstance(track, SourceTrack):
        raise TypeError("track must be a SourceTrack")
    return TrackIdentity(
        catalog_uuid=track.catalog_uuid,
        track_uuid=track.track_uuid,
        content_generation=track.content_generation,
        file_path=track.file_path,
    )


def _ensure_profile_tables(connection: sqlite3.Connection) -> None:
    _reject_noncanonical_table(
        connection,
        table="classifier_profiles",
        expected_columns=_PROFILE_COLUMNS,
    )
    _reject_noncanonical_table(
        connection,
        table="classifier_profile_labels",
        expected_columns=_PROFILE_LABEL_COLUMNS,
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS classifier_profiles (
            classifier_key TEXT PRIMARY KEY,
            profile_type TEXT NOT NULL DEFAULT 'binary' CHECK(profile_type IN ('binary', 'multiclass')),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            artifact_dir TEXT NOT NULL,
            artifact_prefix TEXT NOT NULL,
            training_min_added INTEGER NOT NULL DEFAULT 50 CHECK(training_min_added >= 1),
            positive_label TEXT NOT NULL,
            negative_label TEXT NOT NULL,
            archived_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

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
        );
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
    ):
        _reject_noncanonical_table(
            connection,
            table=table,
            expected_columns=columns,
        )
    connection.execute(_classifier_labels_table_sql("classifier_labels"))
    connection.execute(_classifier_label_queue_table_sql("classifier_label_queue"))
    connection.execute(_classifier_predictions_table_sql("classifier_predictions"))
    connection.execute(_classifier_training_checkpoints_table_sql("classifier_training_checkpoints"))


def _get_profile(connection: sqlite3.Connection, classifier_key: str) -> ClassifierProfile:
    row = connection.execute(
        """
        SELECT classifier_key, profile_type, name, description, artifact_dir, artifact_prefix,
               training_min_added, positive_label, negative_label, archived_at
        FROM classifier_profiles
        WHERE classifier_key = ?
        """,
        (classifier_key,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Unknown classifier profile: {classifier_key}")
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
        archived_at=row["archived_at"],
    )


def _get_profile_by_name(connection: sqlite3.Connection, name: str) -> ClassifierProfile:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Classifier profile name is required")
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
            raise ValueError("At least two class labels are required for a multiclass profile")
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
        SELECT classifier_key, catalog_uuid, track_uuid, content_generation,
               selected_path, feature_set, model_artifact, probabilities_json
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
              AND catalog_uuid = ?
              AND track_uuid = ?
              AND content_generation = ?
              AND selected_path = ?
              AND feature_set = ?
              AND model_artifact = ?
            """,
            (
                _canonical_json(probabilities),
                row["classifier_key"],
                row["catalog_uuid"],
                row["track_uuid"],
                row["content_generation"],
                row["selected_path"],
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
        raise ValueError(f"Unsupported classifier profile type: {value}")
    return value


def _validate_training_min_added(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Training refresh label threshold must be a positive integer") from error
    if number < 1:
        raise ValueError("Training refresh label threshold must be at least 1")
    return number


def _validate_profile_key(key: str) -> str:
    value = str(key or "").strip()
    if not PROFILE_KEY_PATTERN.match(value):
        raise ValueError("Classifier profile key must use lowercase letters, numbers, and underscores")
    return value


def _required_profile_key(key: str | None) -> str:
    if key is None or not str(key).strip():
        raise ValueError("Classifier profile key is required")
    return _validate_profile_key(key)


def _validate_label_key(key: str) -> str:
    value = str(key or "").strip()
    if not LABEL_KEY_PATTERN.match(value):
        raise ValueError("Label key must use lowercase letters, numbers, and underscores")
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
        "catalog_uuid": str(row["catalog_uuid"]),
        "track_uuid": str(row["track_uuid"]),
        "content_generation": int(row["content_generation"]),
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
    return Path(__file__).resolve().parents[1] / "artifacts" / classifier_key.replace("_", "-")


def _normalize_artifact_dir(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        return set()
    return {str(info["name"]) for info in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _reject_noncanonical_table(
    connection: sqlite3.Connection,
    *,
    table: str,
    expected_columns: set[str],
) -> None:
    columns = _columns(connection, table)
    if columns and columns != expected_columns:
        raise RuntimeError(
            f"Rhythm Lab database table {table!r} is not the greenfield v7 schema; "
            "choose a new lab database path"
        )


def _required_identity_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _require_track_identity(identity: TrackIdentity) -> TrackIdentity:
    if not isinstance(identity, TrackIdentity):
        raise TypeError("identity must be a TrackIdentity")
    return identity


def _identity_from_mapping(item: Mapping[str, object]) -> TrackIdentity:
    if not isinstance(item, Mapping):
        raise TypeError("queue item must be a mapping")
    generation = item.get("content_generation")
    if isinstance(generation, bool):
        raise ValueError("content_generation must be a positive integer")
    try:
        clean_generation = int(generation)
    except (TypeError, ValueError) as error:
        raise ValueError("content_generation must be a positive integer") from error
    return TrackIdentity(
        catalog_uuid=_required_identity_text(item.get("catalog_uuid"), "catalog_uuid"),
        track_uuid=_required_identity_text(item.get("track_uuid"), "track_uuid"),
        content_generation=clean_generation,
        file_path=_required_identity_text(
            item.get("selected_path", item.get("file_path")),
            "file_path",
        ),
    )


def _classifier_label_from_row(row: sqlite3.Row) -> ClassifierLabel:
    return ClassifierLabel(
        identity=TrackIdentity(
            catalog_uuid=str(row["catalog_uuid"]),
            track_uuid=str(row["track_uuid"]),
            content_generation=int(row["content_generation"]),
            file_path=str(row["selected_path"]),
        ),
        selected_path=str(row["selected_path"]),
        label=str(row["label"]),
        note=row["note"],
        updated_at=row["updated_at"],
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
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            content_generation INTEGER NOT NULL CHECK(content_generation > 0),
            selected_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL CHECK(file_size_bytes >= 0),
            file_modified_ns INTEGER NOT NULL CHECK(file_modified_ns >= 0),
            label TEXT NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(
                classifier_key, catalog_uuid, track_uuid, content_generation,
                selected_path
            ),
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
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            content_generation INTEGER NOT NULL CHECK(content_generation > 0),
            selected_path TEXT NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('{modes}')),
            score REAL,
            priority REAL NOT NULL,
            reason_json TEXT NOT NULL CHECK(json_valid(reason_json)),
            state TEXT NOT NULL DEFAULT 'suggested' CHECK(state IN ('{states}')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(
                classifier_key, catalog_uuid, track_uuid, content_generation,
                selected_path, mode
            ),
            FOREIGN KEY(classifier_key) REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
    """


def _classifier_predictions_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            content_generation INTEGER NOT NULL CHECK(content_generation > 0),
            selected_path TEXT NOT NULL,
            artist TEXT,
            title TEXT,
            feature_set TEXT NOT NULL,
            model_artifact TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(
                classifier_key, catalog_uuid, track_uuid, content_generation,
                selected_path, feature_set, model_artifact
            ),
            FOREIGN KEY(classifier_key)
                REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
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

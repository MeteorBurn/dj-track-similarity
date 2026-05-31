from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal

from dj_track_similarity.metadata_payload import metadata_to_json
from dj_track_similarity.models import Track


BREAK_ENERGY_CLASSIFIER_KEY = "break_energy"
STRAIGHT_LABEL = "straight"
ClassifierLabelName = Literal["broken", "straight", "ambiguous"]
CLASSIFIER_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL, "ambiguous")
TRAINING_LABELS: tuple[str, ...] = ("broken", STRAIGHT_LABEL)
ProfileType = Literal["binary", "multiclass"]
PROFILE_TYPES: tuple[str, ...] = ("binary", "multiclass")
ProfileLabelRole = Literal["positive", "negative", "review", "class"]
PROFILE_LABEL_ROLES: tuple[str, ...] = ("positive", "negative", "review", "class")
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "break-energy"
DEFAULT_ARTIFACT_PREFIX = "break-energy"
DEFAULT_TRAINING_MIN_ADDED = 50
DEFAULT_BREAK_ENERGY_DESCRIPTION = (
    "Positive class for syncopated, broken, break-heavy, or drum-break rhythm texture."
)
PROFILE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LABEL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ClassifierLabel:
    source_track_id: int
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
            _ensure_profile_tables(connection)
            _ensure_classifier_tables(connection)
            _ensure_default_break_energy_profile(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_classifier_labels_lookup
                ON classifier_labels(classifier_key, label, updated_at);

                CREATE INDEX IF NOT EXISTS idx_classifier_predictions_lookup
                ON classifier_predictions(classifier_key, label, confidence);
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
        key = _validate_profile_key(classifier_key or self.classifier_key)
        with self.connect() as connection:
            return _get_profile(connection, key)

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

    def set_label(self, track: Track | int, label: str | None, *, note: str | None = None) -> ClassifierLabel | None:
        source_track_id, path, size, mtime = _track_snapshot(track)
        if label is None or not label.strip():
            with self.connect() as connection:
                connection.execute(
                    "DELETE FROM classifier_labels WHERE classifier_key = ? AND source_track_id = ?",
                    (self.classifier_key, source_track_id),
                )
            return None
        label = label.strip()
        profile = self.get_profile()
        if label not in profile.label_keys:
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
        training_keys = self.get_profile().training_label_keys
        if not training_keys:
            return {}
        placeholders = ", ".join("?" for _ in training_keys)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT source_track_id, label
                FROM classifier_labels
                WHERE classifier_key = ? AND label IN ({placeholders})
                ORDER BY source_track_id
                """,
                (self.classifier_key, *training_keys),
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
        if label not in self.get_profile().training_label_keys:
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
        training_keys = self.get_profile().training_label_keys
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
        payload = metadata_to_json(_training_counts_payload(counts, self.get_profile().training_label_keys))
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


def _ensure_profile_tables(connection: sqlite3.Connection) -> None:
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
    if "profile_type" not in _columns(connection, "classifier_profiles"):
        connection.execute(
            "ALTER TABLE classifier_profiles ADD COLUMN profile_type TEXT NOT NULL DEFAULT 'binary'"
        )
    if "training_min_added" not in _columns(connection, "classifier_profiles"):
        connection.execute(
            "ALTER TABLE classifier_profiles ADD COLUMN training_min_added INTEGER NOT NULL DEFAULT 50"
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
    connection.execute(_classifier_labels_table_sql("classifier_labels"))
    connection.execute(_classifier_predictions_table_sql("classifier_predictions"))
    connection.execute(_classifier_training_checkpoints_table_sql("classifier_training_checkpoints"))


def _ensure_default_break_energy_profile(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM classifier_profiles WHERE classifier_key = ?",
        (BREAK_ENERGY_CLASSIFIER_KEY,),
    ).fetchone()
    if row is None:
        connection.execute(
            """
            INSERT INTO classifier_profiles(
                classifier_key, name, description, artifact_dir, artifact_prefix,
                training_min_added, positive_label, negative_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                BREAK_ENERGY_CLASSIFIER_KEY,
                "Break Energy",
                DEFAULT_BREAK_ENERGY_DESCRIPTION,
                _normalize_artifact_dir(DEFAULT_ARTIFACT_DIR),
                DEFAULT_ARTIFACT_PREFIX,
                DEFAULT_TRAINING_MIN_ADDED,
                "broken",
                STRAIGHT_LABEL,
            ),
        )
    existing_labels = {
        str(row["label_key"])
        for row in connection.execute(
            "SELECT label_key FROM classifier_profile_labels WHERE classifier_key = ?",
            (BREAK_ENERGY_CLASSIFIER_KEY,),
        ).fetchall()
    }
    defaults = (
        ClassifierProfileLabel("broken", "Broken", "positive", "Break-heavy or syncopated energy", 0),
        ClassifierProfileLabel(STRAIGHT_LABEL, "Straight", "negative", "Straight four-on-the-floor reference", 1),
        ClassifierProfileLabel("ambiguous", "Ambiguous", "review", "Review-only label excluded from training", 2),
    )
    for label in defaults:
        if label.key in existing_labels:
            continue
        connection.execute(
            """
            INSERT INTO classifier_profile_labels(
                classifier_key, label_key, display_name, description, role, position
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                BREAK_ENERGY_CLASSIFIER_KEY,
                label.key,
                label.name,
                label.description,
                label.role,
                label.position,
            ),
        )


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
        SELECT classifier_key, source_track_id, feature_set, model_artifact, probabilities_json
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
            WHERE classifier_key = ? AND source_track_id = ? AND feature_set = ? AND model_artifact = ?
            """,
            (
                metadata_to_json(probabilities),
                row["classifier_key"],
                row["source_track_id"],
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
        (metadata_to_json(counts), classifier_key),
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


def _validate_label_key(key: str) -> str:
    value = str(key or "").strip()
    if not LABEL_KEY_PATTERN.match(value):
        raise ValueError("Label key must use lowercase letters, numbers, and underscores")
    return value


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


def _classifier_labels_table_sql(table: str) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            classifier_key TEXT NOT NULL,
            source_track_id INTEGER NOT NULL,
            path TEXT,
            size INTEGER,
            mtime REAL,
            label TEXT NOT NULL,
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
            label TEXT NOT NULL,
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

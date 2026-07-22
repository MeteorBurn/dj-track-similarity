from __future__ import annotations

import sqlite3

from .db_search_fts import create_track_search_fts, rebuild_track_search_fts
from .db_storage import ensure_sidecar_schemas
from .metadata_payload import metadata_from_json, metadata_to_json, optional_float, string_or_none
from .sonara_contract import SONARA_PROJECT_FEATURE_REVISION, feature_set_uses_sonara


CURRENT_SCHEMA_VERSION = 6
SQLITE_BUSY_TIMEOUT_SECONDS = 30
SONARA_CLASSIFIER_REVISION_SETTING_KEY = "classifier.sonara_feature_revision"
SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY = "sonara.active_release_hash"
SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY = "classifier.sonara_release_hash"

TRACK_BASE_FIELDS = """
t.id, t.path, t.size, t.mtime, t.artist, t.title, t.album, t.bpm, t.musical_key, t.energy, t.duration,
EXISTS(SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id) AS liked
"""
TRACK_ANALYSIS_FLAG_FIELDS = """
(
    t.has_sonara_analysis = 1
    AND sonara_analysis_is_current(t.metadata_json) = 1
) AS has_sonara,
t.has_maest_embedding = 1 AS has_maest
"""
TRACK_EMBEDDING_KEY_FIELD = """
(
    SELECT json_group_array(embedding_key)
    FROM embeddings
    WHERE track_id = t.id
) AS embedding_keys_json
"""
TRACK_STORAGE_MANIFEST_FIELDS = """
(
    SELECT fields_json
    FROM timeline.sonara_timeline
    WHERE track_id = t.id
) AS timeline_fields_json,
(
    SELECT json_group_array(field_name)
    FROM (
        SELECT
            CASE embedding_key
                WHEN 'sonara' THEN 'embedding'
                ELSE embedding_key || '_embedding'
            END AS field_name
        FROM representations.embeddings
        WHERE track_id = t.id
        UNION ALL
        SELECT fingerprint_key AS field_name
        FROM representations.fingerprints
        WHERE track_id = t.id
        ORDER BY field_name
    )
) AS representation_fields_json
"""
TRACK_CLASSIFIER_SCORES_FIELD = """
(
    SELECT COALESCE(
        json_group_object(
            classifier,
            json_object(
                'score', score,
                'label', label,
                'confidence', confidence,
                'probabilities', json(probabilities_json),
                'feature_set', feature_set,
                'model_id', model_id,
                'analyzed_at', analyzed_at
            )
        ),
        '{}'
    )
    FROM track_classifier_scores
    WHERE track_id = t.id
) AS classifier_scores_json
"""
TRACK_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, t.metadata_json, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_STORAGE_MANIFEST_FIELDS},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""

MAEST_HAS_GENRES_SQL = """
(
    json_type(metadata_json, '$.maest_genres') = 'array'
    AND json_array_length(json_extract(metadata_json, '$.maest_genres')) > 0
)
"""
def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    tables = _user_tables(connection)
    if tables and not {"tracks", "library_settings"}.issubset(tables):
        raise RuntimeError(_migration_required_message())

    if not tables:
        _create_current_schema(connection)
        ensure_sidecar_schemas(connection)
        _ensure_sonara_classifier_feature_revision(connection)
        return

    if _schema_version(connection) == 5:
        _migrate_v5_to_v6(connection)

    if _schema_version(connection) != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(_migration_required_message())
    _validate_current_schema(connection)
    _create_current_indexes_and_triggers(connection)
    ensure_sidecar_schemas(connection)
    _ensure_sonara_classifier_feature_revision(connection)


def _create_current_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            artist TEXT,
            title TEXT,
            album TEXT,
            bpm REAL,
            musical_key TEXT,
            energy REAL,
            duration REAL,
            has_sonara_analysis INTEGER NOT NULL DEFAULT 0,
            has_maest_embedding INTEGER NOT NULL DEFAULT 0,
            has_mert_embedding INTEGER NOT NULL DEFAULT 0,
            has_muq_embedding INTEGER NOT NULL DEFAULT 0,
            has_clap_embedding INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(metadata_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE embeddings (
            track_id INTEGER NOT NULL,
            embedding_key TEXT NOT NULL,
            model_name TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, embedding_key),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE library_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE track_classifier_scores (
            track_id INTEGER NOT NULL,
            classifier TEXT NOT NULL,
            score REAL NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            feature_set TEXT NOT NULL,
            model_id TEXT NOT NULL,
            analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, classifier),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE track_likes (
            track_id INTEGER PRIMARY KEY,
            liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        PRAGMA user_version = {CURRENT_SCHEMA_VERSION};
        """
    )
    create_track_search_fts(connection)
    _create_current_indexes_and_triggers(connection)


def _create_current_indexes_and_triggers(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_tracks_sort_artist_title_path
        ON tracks (COALESCE(artist, ''), COALESCE(title, ''), path);

        CREATE INDEX IF NOT EXISTS idx_tracks_syncopated_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_sonara_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_sonara_analysis = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_maest_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_maest_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_mert_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_mert_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_muq_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_muq_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_clap_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_clap_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_sonara_flag
        ON tracks(id)
        WHERE has_sonara_analysis = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_maest_embedding_flag
        ON tracks(id)
        WHERE has_maest_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_mert_embedding_flag
        ON tracks(id)
        WHERE has_mert_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_muq_embedding_flag
        ON tracks(id)
        WHERE has_muq_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_clap_embedding_flag
        ON tracks(id)
        WHERE has_clap_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_embeddings_key_track
        ON embeddings(embedding_key, track_id);

        CREATE TABLE IF NOT EXISTS track_classifier_scores (
            track_id INTEGER NOT NULL,
            classifier TEXT NOT NULL,
            score REAL NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            feature_set TEXT NOT NULL,
            model_id TEXT NOT NULL,
            analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, classifier),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_classifier_scores_lookup
        ON track_classifier_scores(classifier, score DESC, track_id);

        CREATE TABLE IF NOT EXISTS track_likes (
            track_id INTEGER PRIMARY KEY,
            liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TRIGGER IF NOT EXISTS tracks_metadata_json_insert_valid
        BEFORE INSERT ON tracks
        FOR EACH ROW
        WHEN NOT json_valid(NEW.metadata_json)
        BEGIN
            SELECT RAISE(ABORT, 'tracks.metadata_json must be valid JSON');
        END;

        CREATE TRIGGER IF NOT EXISTS tracks_metadata_json_update_valid
        BEFORE UPDATE OF metadata_json ON tracks
        FOR EACH ROW
        WHEN NOT json_valid(NEW.metadata_json)
        BEGIN
            SELECT RAISE(ABORT, 'tracks.metadata_json must be valid JSON');
        END;
        """
    )
    _create_evaluation_schema(connection)


def _create_evaluation_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            seed_track_ids_json TEXT NOT NULL CHECK(json_valid(seed_track_ids_json)),
            request_json TEXT NOT NULL CHECK(json_valid(request_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS search_result_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES search_sessions(id) ON DELETE CASCADE,
            track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            total_score REAL NOT NULL,
            score_breakdown_json TEXT NOT NULL CHECK(json_valid(score_breakdown_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS track_pair_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seed_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            candidate_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
            reason_tags_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(reason_tags_json)),
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(seed_track_id, candidate_track_id, source)
        );

        CREATE TABLE IF NOT EXISTS transition_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outgoing_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            incoming_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
            risk_tags_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(risk_tags_json)),
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS calibration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            search_mode TEXT NOT NULL,
            config_json TEXT NOT NULL CHECK(json_valid(config_json)),
            metrics_json TEXT NOT NULL CHECK(json_valid(metrics_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_search_sessions_mode_created
        ON search_sessions(mode, created_at);

        CREATE INDEX IF NOT EXISTS idx_search_result_events_session_rank
        ON search_result_events(session_id, rank);

        CREATE INDEX IF NOT EXISTS idx_search_result_events_track
        ON search_result_events(track_id);

        CREATE INDEX IF NOT EXISTS idx_track_pair_feedback_seed_rating
        ON track_pair_feedback(seed_track_id, rating, candidate_track_id);

        CREATE INDEX IF NOT EXISTS idx_track_pair_feedback_candidate
        ON track_pair_feedback(candidate_track_id);

        CREATE INDEX IF NOT EXISTS idx_transition_feedback_outgoing_created
        ON transition_feedback(outgoing_track_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_transition_feedback_incoming
        ON transition_feedback(incoming_track_id);

        CREATE INDEX IF NOT EXISTS idx_calibration_runs_profile_mode_created
        ON calibration_runs(profile_name, search_mode, created_at);
        """
    )


def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
    """Move SONARA 0.2.9 optional outputs to sidecars and invalidate only old SONARA data.

    MAEST, MERT, MuQ, and CLAP embeddings are hot application data used by search and remain in the
    Core database. Their flags and MAEST metadata must survive this SONARA-specific migration.
    """

    sonara_keys = {
        "sonara_features",
        "sonara_features_file",
        "sonara_model",
        "sonara_provenance",
        "sonara_analysis_signature",
    }
    rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
    for row in rows:
        metadata = metadata_from_json(row["metadata_json"])
        for key in sonara_keys:
            metadata.pop(key, None)
        connection.execute(
            """
            UPDATE tracks
            SET bpm = ?,
                musical_key = ?,
                energy = ?,
                duration = ?,
                has_sonara_analysis = 0,
                metadata_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                optional_float(metadata.get("bpm")),
                string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey")),
                optional_float(metadata.get("energy")),
                optional_float(metadata.get("duration")),
                metadata_to_json(metadata),
                int(row["id"]),
            ),
        )
    for embedding_key, flag_column in (
        ("maest", "has_maest_embedding"),
        ("mert", "has_mert_embedding"),
        ("muq", "has_muq_embedding"),
        ("clap", "has_clap_embedding"),
    ):
        connection.execute(
            f"""
            UPDATE tracks
            SET {flag_column} = EXISTS (
                SELECT 1
                FROM embeddings e
                WHERE e.track_id = tracks.id AND e.embedding_key = ?
            )
            """,
            (embedding_key,),
        )
    connection.execute("DROP TABLE IF EXISTS sonara_curves")
    connection.execute(
        "DELETE FROM library_settings WHERE key = ?",
        (SONARA_CLASSIFIER_REVISION_SETTING_KEY,),
    )
    rebuild_track_search_fts(connection)
    connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")


def _ensure_sonara_classifier_feature_revision(connection: sqlite3.Connection) -> None:
    """Invalidate SONARA-dependent classifier scores when the feature revision or
    the SONARA release hash has changed since scores were last validated.

    Two independent gating signals are checked:

    1. **Feature revision** (existing check): ``SONARA_PROJECT_FEATURE_REVISION``
       must match the value stored under ``SONARA_CLASSIFIER_REVISION_SETTING_KEY``.

    2. **Release hash** (BUG-C2 fix): when ``SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY``
       is present in ``library_settings``, it must match the value stored under
       ``SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY``.  A mismatch means a SONARA
       package/decoder/contract change occurred without a feature-revision bump,
       leaving scores computed against the old release active.

    Either mismatch triggers deletion of all SONARA-dependent
    ``track_classifier_scores`` rows.  Non-SONARA scores are never touched.
    After deletion both sentinel values are updated so the next open is a no-op.
    """
    revision_row = connection.execute(
        "SELECT value FROM library_settings WHERE key = ?",
        (SONARA_CLASSIFIER_REVISION_SETTING_KEY,),
    ).fetchone()
    revision_ok = revision_row is not None and str(revision_row["value"]) == str(SONARA_PROJECT_FEATURE_REVISION)

    # Release-hash gate: compare the active SONARA release hash against the hash
    # that was recorded when classifier scores were last validated.
    active_hash_row = connection.execute(
        "SELECT value FROM library_settings WHERE key = ?",
        (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
    ).fetchone()
    active_hash = str(active_hash_row["value"]) if active_hash_row is not None else None

    hash_ok: bool
    if active_hash is None:
        # No active hash recorded — hash gate is not applicable; rely on revision only.
        hash_ok = True
    else:
        scored_hash_row = connection.execute(
            "SELECT value FROM library_settings WHERE key = ?",
            (SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY,),
        ).fetchone()
        scored_hash = str(scored_hash_row["value"]) if scored_hash_row is not None else None
        hash_ok = scored_hash == active_hash

    if revision_ok and hash_ok:
        return

    score_rows = connection.execute(
        "SELECT track_id, classifier, feature_set FROM track_classifier_scores"
    ).fetchall()
    stale_scores = [
        (int(score["track_id"]), str(score["classifier"]))
        for score in score_rows
        if feature_set_uses_sonara(score["feature_set"])
    ]
    if stale_scores:
        connection.executemany(
            "DELETE FROM track_classifier_scores WHERE track_id = ? AND classifier = ?",
            stale_scores,
        )

    # Update the feature-revision sentinel.
    connection.execute(
        """
        INSERT INTO library_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (SONARA_CLASSIFIER_REVISION_SETTING_KEY, str(SONARA_PROJECT_FEATURE_REVISION)),
    )

    # Update the release-hash sentinel so the next open is a no-op.
    if active_hash is not None:
        connection.execute(
            """
            INSERT INTO library_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY, active_hash),
        )


def _validate_current_schema(connection: sqlite3.Connection) -> None:
    track_columns = _columns(connection, "tracks")
    embedding_columns = _columns(connection, "embeddings")
    required_track_columns = {
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
        "has_sonara_analysis",
        "has_maest_embedding",
        "has_mert_embedding",
        "has_muq_embedding",
        "has_clap_embedding",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    required_embedding_columns = {"track_id", "embedding_key", "model_name", "dim", "vector", "updated_at"}
    settings_columns = _columns(connection, "library_settings")
    required_settings_columns = {"key", "value", "updated_at"}
    tables = _user_tables(connection)
    if not required_track_columns.issubset(track_columns):
        raise RuntimeError(_migration_required_message())
    if not required_embedding_columns.issubset(embedding_columns):
        raise RuntimeError(_migration_required_message())
    if not required_settings_columns.issubset(settings_columns):
        raise RuntimeError(_migration_required_message())
    if "track_search_fts" not in tables:
        raise RuntimeError(_migration_required_message())
    if "sonara_curves" in tables:
        raise RuntimeError(_migration_required_message())
    _validate_evaluation_schema(connection)


def _validate_evaluation_schema(connection: sqlite3.Connection) -> None:
    required_tables = {
        "search_sessions": {
            "id",
            "mode",
            "seed_track_ids_json",
            "request_json",
            "created_at",
        },
        "search_result_events": {
            "id",
            "session_id",
            "track_id",
            "rank",
            "total_score",
            "score_breakdown_json",
            "created_at",
        },
        "track_pair_feedback": {
            "id",
            "seed_track_id",
            "candidate_track_id",
            "rating",
            "reason_tags_json",
            "notes",
            "source",
            "created_at",
            "updated_at",
        },
        "transition_feedback": {
            "id",
            "outgoing_track_id",
            "incoming_track_id",
            "rating",
            "risk_tags_json",
            "notes",
            "source",
            "created_at",
        },
        "calibration_runs": {
            "id",
            "profile_name",
            "search_mode",
            "config_json",
            "metrics_json",
            "created_at",
        },
    }
    tables = _user_tables(connection)
    if not set(required_tables).issubset(tables):
        raise RuntimeError(_migration_required_message())
    for table, required_columns in required_tables.items():
        if not required_columns.issubset(_columns(connection, table)):
            raise RuntimeError(_migration_required_message())


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _migration_required_message() -> str:
    return (
        "SQLite database schema is not current. Stop the app and use a database created with the current "
        "application version, or rebuild the library database by scanning the source music library again."
    )

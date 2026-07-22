"""v6 → v7 side-by-side database migration.

Entry point: :func:`migrate_v7`.

Design:
- Opens v6 source read-only via SQLite URI ``mode=ro`` + ``PRAGMA query_only=ON``.
- Never mutates source files.
- Performs online backup into a staging directory.
- Creates v7 Core schema + Artifacts sidecar (+ Evaluation sidecar if needed).
- Migrates all data per the draft spec (A3 normalization, A4 fingerprint discard).
- Writes a recovery manifest before any rename.
- Publishes sidecars first, Core LAST.
- Deletes staging + manifest on success.

Recovery:
- If staging exists but Core rename didn't happen → clean up staging + manifest
  on next migrate attempt, then exit with actionable error.
- If Core rename succeeded → do NOT auto-clean; migration is complete.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class MigrationError(RuntimeError):
    """Raised for actionable migration failures."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _open_source_readonly(source: Path) -> sqlite3.Connection:
    """Open *source* via SQLite URI mode=ro and enforce query_only."""
    uri = source.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_backup(src_conn: sqlite3.Connection, dest_path: Path) -> None:
    """Online backup of *src_conn* into *dest_path* (creates the file)."""
    dest = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dest)
    finally:
        dest.close()


def _score_bucket(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _argmax_probabilities(probs_json: str) -> str:
    """Return the key with the highest value from a JSON object string."""
    probs: dict[str, float] = json.loads(probs_json)
    return max(probs, key=lambda k: probs[k])


def _mtime_to_ns(mtime: object) -> tuple[int, bool]:
    """Convert v6 mtime (float seconds) to integer nanoseconds.

    Returns (ns, is_zero_mtime) where is_zero_mtime=True when mtime was
    NULL, zero, or malformed.
    """
    if mtime is None:
        return 0, True
    try:
        f = float(mtime)
        if f <= 0:
            return 0, True
        return int(f * 1_000_000_000), False
    except (TypeError, ValueError):
        return 0, True


def _deterministic_uuid(catalog_uuid: str, v6_track_id: int) -> str:
    """Generate a deterministic v5 UUID from (catalog_uuid, v6_track_id)."""
    namespace = uuid.UUID(catalog_uuid) if _is_valid_uuid(catalog_uuid) else uuid.NAMESPACE_URL
    name = f"v6-track-{v6_track_id}"
    return str(uuid.uuid5(namespace, name))


def _is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Contract reconstruction helpers
# ---------------------------------------------------------------------------


def _compute_ml_contract_hash(
    family: str,
    model_name: str,
    model_version: Optional[str],
    dim: int,
    normalization: str,
) -> str:
    payload: dict[str, object] = {
        "analysis_family": family,
        "output_kind": "embedding",
        "model_name": model_name,
        "model_version": model_version,
        "dim": dim,
        "encoding": "float32-le",
        "normalization": normalization,
        "release_hash": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical


def _compute_maest_embedding_contract_hash(
    model_name: str,
    model_version: Optional[str],
    dim: int,
    normalization: str,
) -> tuple[str, str]:
    payload: dict[str, object] = {
        "analysis_family": "maest",
        "output_kind": "embedding",
        "model_name": model_name,
        "model_version": model_version,
        "dim": dim,
        "encoding": "float32-le",
        "normalization": normalization,
        "release_hash": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical


def _compute_maest_analysis_contract_hash(
    model_name: str,
    model_version: Optional[str],
) -> tuple[str, str]:
    payload: dict[str, object] = {
        "analysis_family": "maest",
        "output_kind": "analysis",
        "model_name": model_name,
        "model_version": model_version,
        "dim": None,
        "encoding": None,
        "normalization": None,
        "release_hash": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical


def _upsert_contract(
    core_conn: sqlite3.Connection,
    contract_hash: str,
    family: str,
    output_kind: str,
    model_name: str,
    model_version: Optional[str],
    release_hash: Optional[str],
    canonical: str,
) -> None:
    existing = core_conn.execute(
        "SELECT 1 FROM contracts WHERE contract_hash = ?", (contract_hash,)
    ).fetchone()
    if existing is None:
        now = _now_iso()
        core_conn.execute(
            """
            INSERT INTO contracts (
                contract_hash, analysis_family, output_kind,
                model_name, model_version, release_hash,
                canonical_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (contract_hash, family, output_kind, model_name, model_version, release_hash, canonical, now),
        )


# ---------------------------------------------------------------------------
# Embedding family analysis
# ---------------------------------------------------------------------------


def _analyze_embedding_families(
    src_conn: sqlite3.Connection,
) -> dict[str, dict]:
    """Inspect v6 embeddings table and classify each family.

    Returns a dict keyed by embedding_key with:
      - 'rows': list of row dicts
      - 'consistent': bool (single model_name + dim combination)
      - 'model_name': str (if consistent)
      - 'dim': int (if consistent)
      - 'normalization': str (default 'none' — v6 has no normalization column)
    """
    families: dict[str, dict] = {}

    rows = src_conn.execute(
        "SELECT track_id, embedding_key, model_name, dim, vector, updated_at FROM embeddings"
    ).fetchall()

    for row in rows:
        key = row["embedding_key"]
        if key not in families:
            families[key] = {"rows": [], "model_names": set(), "dims": set()}
        families[key]["rows"].append(dict(row))
        families[key]["model_names"].add(row["model_name"])
        families[key]["dims"].add(row["dim"])

    result: dict[str, dict] = {}
    for key, data in families.items():
        consistent = len(data["model_names"]) == 1 and len(data["dims"]) == 1
        entry: dict = {
            "rows": data["rows"],
            "consistent": consistent,
            "normalization": "none",  # v6 has no normalization column; default per spec
        }
        if consistent:
            entry["model_name"] = next(iter(data["model_names"]))
            entry["dim"] = next(iter(data["dims"]))
        result[key] = entry

    return result


# ---------------------------------------------------------------------------
# Core migration steps
# ---------------------------------------------------------------------------


def _migrate_tracks_and_file_tags(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    catalog_uuid: str,
) -> tuple[dict[int, dict], int, int]:
    """Migrate v6 tracks → v7 tracks + file_tags.

    Returns:
        (track_map, tracks_migrated, tracks_with_zero_mtime)
        track_map: {v6_track_id: {'track_id': int, 'track_uuid': str, 'content_generation': int}}
    """
    v6_tracks = src_conn.execute(
        """
        SELECT id, path, size, mtime, artist, title, album, bpm, musical_key,
               energy, duration, metadata_json, created_at, updated_at
        FROM tracks
        ORDER BY id
        """
    ).fetchall()

    track_map: dict[int, dict] = {}
    tracks_migrated = 0
    tracks_with_zero_mtime = 0
    now = _now_iso()

    for row in v6_tracks:
        v6_id = row["id"]
        track_uuid = _deterministic_uuid(catalog_uuid, v6_id)
        file_modified_ns, is_zero = _mtime_to_ns(row["mtime"])
        if is_zero:
            tracks_with_zero_mtime += 1

        created_at = row["created_at"] or now
        updated_at = row["updated_at"] or now

        # Insert into v7 tracks
        cur = core_conn.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                audio_duration_seconds, content_generation,
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                row["path"],
                row["size"],
                file_modified_ns,
                row["duration"],
                now,
                created_at,
                updated_at,
            ),
        )
        new_track_id = cur.lastrowid

        # Parse metadata_json for file_tags
        try:
            meta: dict = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}

        # Extract genres from metadata (MAEST genres are separate; file genres = empty for v6)
        genres_json = "[]"

        core_conn.execute(
            """
            INSERT INTO file_tags (
                track_id, title, artist, album, tag_bpm, tag_key,
                genres_json, tags_read_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_track_id,
                row["title"],
                row["artist"],
                row["album"],
                row["bpm"],
                row["musical_key"],
                genres_json,
                now,
            ),
        )

        track_map[v6_id] = {
            "track_id": new_track_id,
            "track_uuid": track_uuid,
            "content_generation": 1,
        }
        tracks_migrated += 1

    return track_map, tracks_migrated, tracks_with_zero_mtime


def _migrate_maest_scores(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    track_map: dict[int, dict],
) -> int:
    """Migrate MAEST genre scores from v6 metadata_json → v7 maest_scores.

    Returns count of migrated rows.
    """
    v6_tracks = src_conn.execute(
        "SELECT id, metadata_json FROM tracks ORDER BY id"
    ).fetchall()

    migrated = 0
    now = _now_iso()

    for row in v6_tracks:
        v6_id = row["id"]
        if v6_id not in track_map:
            continue
        try:
            meta: dict = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        maest_genres = meta.get("maest_genres")
        if not maest_genres:
            continue

        maest_model = meta.get("maest_model", "discogs-maest-30s-pw-129e-519l")
        syncopated = meta.get("maest_syncopated_rhythm")
        syncopated_int: Optional[int] = None
        if syncopated is not None:
            syncopated_int = 1 if syncopated else 0

        # Build genres_json in v7 format
        genres_list = []
        for i, g in enumerate(maest_genres):
            genres_list.append({
                "rank": i + 1,
                "genre_name": g.get("genre_name", ""),
                "score": g.get("score", 0.0),
            })
        genres_json = json.dumps(genres_list, ensure_ascii=False)

        # Upsert MAEST analysis contract
        contract_hash, canonical = _compute_maest_analysis_contract_hash(
            model_name=maest_model,
            model_version=None,
        )
        _upsert_contract(
            core_conn,
            contract_hash=contract_hash,
            family="maest",
            output_kind="analysis",
            model_name=maest_model,
            model_version=None,
            release_hash=None,
            canonical=canonical,
        )

        track_info = track_map[v6_id]
        core_conn.execute(
            """
            INSERT OR REPLACE INTO maest_scores (
                track_id, content_generation, contract_hash,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                track_info["track_id"],
                track_info["content_generation"],
                contract_hash,
                syncopated_int,
                genres_json,
                now,
            ),
        )
        migrated += 1

    return migrated


def _migrate_embeddings(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    artifacts_conn: sqlite3.Connection,
    track_map: dict[int, dict],
    family_data: dict[str, dict],
) -> tuple[dict[str, int], list[str]]:
    """Migrate ML embeddings from v6 embeddings table → v7 artifacts sidecar.

    Returns:
        (embeddings_migrated, mixed_legacy_contracts)
        embeddings_migrated: {family: count}
        mixed_legacy_contracts: list of family names skipped due to mixed contracts
    """
    embeddings_migrated: dict[str, int] = {"maest": 0, "mert": 0, "muq": 0, "clap": 0}
    mixed_legacy_contracts: list[str] = []
    now = _now_iso()

    # Map embedding_key → v7 family name and table
    family_map = {
        "maest": ("maest", "maest_embeddings"),
        "mert": ("mert", "mert_embeddings"),
        "muq": ("muq", "muq_embeddings"),
        "clap": ("clap", "clap_embeddings"),
    }

    for emb_key, (family, table) in family_map.items():
        if emb_key not in family_data:
            continue

        data = family_data[emb_key]
        if not data["consistent"]:
            mixed_legacy_contracts.append(emb_key)
            LOGGER.warning("Skipping family %r: mixed model_name/dim across rows", emb_key)
            continue

        model_name = data["model_name"]
        dim = data["dim"]
        normalization = data["normalization"]  # 'none' for v6

        # Upsert contract into Core
        if family == "maest":
            contract_hash, canonical = _compute_maest_embedding_contract_hash(
                model_name=model_name,
                model_version=None,
                dim=dim,
                normalization=normalization,
            )
            _upsert_contract(
                core_conn,
                contract_hash=contract_hash,
                family="maest",
                output_kind="embedding",
                model_name=model_name,
                model_version=None,
                release_hash=None,
                canonical=canonical,
            )
        else:
            contract_hash, canonical = _compute_ml_contract_hash(
                family=family,
                model_name=model_name,
                model_version=None,
                dim=dim,
                normalization=normalization,
            )
            _upsert_contract(
                core_conn,
                contract_hash=contract_hash,
                family=family,
                output_kind="embedding",
                model_name=model_name,
                model_version=None,
                release_hash=None,
                canonical=canonical,
            )

        # Insert embedding rows into artifacts sidecar
        for emb_row in data["rows"]:
            v6_id = emb_row["track_id"]
            if v6_id not in track_map:
                continue

            blob: bytes = emb_row["vector"]
            # Validate: blob length must equal dim * 4
            if len(blob) != dim * 4:
                LOGGER.warning(
                    "Skipping %s embedding for v6 track %d: blob length %d != dim*4=%d",
                    emb_key, v6_id, len(blob), dim * 4,
                )
                continue

            # Validate finite values
            try:
                import numpy as np
                vec = np.frombuffer(blob, dtype="<f4")
                if not bool(np.all(np.isfinite(vec))):
                    LOGGER.warning("Skipping %s embedding for v6 track %d: non-finite values", emb_key, v6_id)
                    continue
            except Exception:
                pass  # If numpy unavailable, skip validation

            track_info = track_map[v6_id]
            artifacts_conn.execute(
                f"""
                INSERT OR REPLACE INTO {table} (
                    track_id, track_uuid, content_generation, contract_hash,
                    dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_info["track_id"],
                    track_info["track_uuid"],
                    track_info["content_generation"],
                    contract_hash,
                    dim,
                    normalization,
                    blob,
                    now,
                ),
            )
            embeddings_migrated[family] += 1

    return embeddings_migrated, mixed_legacy_contracts


def _migrate_classifier_scores(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    track_map: dict[int, dict],
) -> tuple[int, int]:
    """Migrate non-SONARA classifier scores from v6 → v7.

    Only migrates scores whose feature_set does NOT contain 'sonara'.
    Returns (migrated, discarded).
    """
    v6_scores = src_conn.execute(
        """
        SELECT track_id, classifier, score, label, confidence,
               probabilities_json, feature_set, model_id, analyzed_at
        FROM track_classifier_scores
        ORDER BY track_id, classifier
        """
    ).fetchall()

    migrated = 0
    discarded = 0
    now = _now_iso()

    for row in v6_scores:
        v6_id = row["track_id"]
        if v6_id not in track_map:
            discarded += 1
            continue

        feature_set = row["feature_set"] or ""
        # Discard SONARA-dependent scores
        if "sonara" in feature_set.lower():
            discarded += 1
            continue

        # Compute predicted_class and score_bucket
        try:
            predicted_class = _argmax_probabilities(row["probabilities_json"])
        except (json.JSONDecodeError, ValueError, KeyError):
            predicted_class = row["label"] or "unknown"

        score = float(row["score"])
        bucket = _score_bucket(score)

        # feature_manifest_hash: compute from feature_set string (best effort)
        feature_manifest_hash = "sha256:" + hashlib.sha256(
            feature_set.encode("utf-8")
        ).hexdigest()

        track_info = track_map[v6_id]
        try:
            core_conn.execute(
                """
                INSERT OR REPLACE INTO classifier_scores (
                    track_id, classifier_key, content_generation,
                    model_id, feature_set, feature_manifest_hash,
                    uses_sonara, sonara_release_hash,
                    positive_label, predicted_class, score_bucket,
                    score, confidence, probabilities_json, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_info["track_id"],
                    row["classifier"],
                    track_info["content_generation"],
                    row["model_id"],
                    feature_set,
                    feature_manifest_hash,
                    row["label"] or predicted_class,
                    predicted_class,
                    bucket,
                    score,
                    float(row["confidence"]),
                    row["probabilities_json"],
                    row["analyzed_at"] or now,
                ),
            )
            migrated += 1
        except sqlite3.Error as exc:
            LOGGER.warning("Skipping classifier score for v6 track %d / %s: %s", v6_id, row["classifier"], exc)
            discarded += 1

    return migrated, discarded


def _migrate_likes(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    track_map: dict[int, dict],
) -> None:
    rows = src_conn.execute("SELECT track_id, liked_at FROM track_likes").fetchall()
    for row in rows:
        v6_id = row["track_id"]
        if v6_id not in track_map:
            continue
        track_info = track_map[v6_id]
        try:
            core_conn.execute(
                "INSERT OR IGNORE INTO likes (track_id, liked_at) VALUES (?, ?)",
                (track_info["track_id"], row["liked_at"]),
            )
        except sqlite3.Error as exc:
            LOGGER.warning("Skipping like for v6 track %d: %s", v6_id, exc)


def _migrate_pair_feedback(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    track_map: dict[int, dict],
) -> None:
    rows = src_conn.execute(
        """
        SELECT seed_track_id, candidate_track_id, rating, reason_tags_json,
               notes, source, created_at, updated_at
        FROM track_pair_feedback
        ORDER BY id
        """
    ).fetchall()
    now = _now_iso()
    for row in rows:
        seed_v6 = row["seed_track_id"]
        cand_v6 = row["candidate_track_id"]
        if seed_v6 not in track_map or cand_v6 not in track_map:
            continue
        try:
            core_conn.execute(
                """
                INSERT OR IGNORE INTO pair_feedback (
                    seed_track_id, candidate_track_id, rating,
                    reason_tags_json, notes, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_map[seed_v6]["track_id"],
                    track_map[cand_v6]["track_id"],
                    row["rating"],
                    row["reason_tags_json"] or "[]",
                    row["notes"],
                    row["source"] or "manual",
                    row["created_at"] or now,
                    row["updated_at"] or now,
                ),
            )
        except sqlite3.Error as exc:
            LOGGER.warning("Skipping pair_feedback row: %s", exc)


def _migrate_transition_feedback(
    src_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
    track_map: dict[int, dict],
) -> None:
    rows = src_conn.execute(
        """
        SELECT outgoing_track_id, incoming_track_id, rating, risk_tags_json,
               notes, source, created_at
        FROM transition_feedback
        ORDER BY id
        """
    ).fetchall()
    now = _now_iso()
    for row in rows:
        out_v6 = row["outgoing_track_id"]
        in_v6 = row["incoming_track_id"]
        if out_v6 not in track_map or in_v6 not in track_map:
            continue
        try:
            core_conn.execute(
                """
                INSERT OR IGNORE INTO transition_feedback (
                    outgoing_track_id, incoming_track_id, rating,
                    risk_tags_json, notes, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_map[out_v6]["track_id"],
                    track_map[in_v6]["track_id"],
                    row["rating"],
                    row["risk_tags_json"] or "[]",
                    row["notes"],
                    row["source"] or "manual",
                    row["created_at"] or now,
                ),
            )
        except sqlite3.Error as exc:
            LOGGER.warning("Skipping transition_feedback row: %s", exc)


def _migrate_search_history(
    src_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
    track_map: dict[int, dict],
    catalog_uuid: str,
) -> bool:
    """Migrate search_sessions, search_result_events, calibration_runs → evaluation sidecar.

    Returns True if any data was migrated.
    """
    sessions = src_conn.execute("SELECT * FROM search_sessions ORDER BY id").fetchall()
    cal_runs = src_conn.execute("SELECT * FROM calibration_runs ORDER BY id").fetchall()

    if not sessions and not cal_runs:
        return False

    now = _now_iso()

    for sess in sessions:
        # Insert session
        cur = eval_conn.execute(
            """
            INSERT INTO search_sessions (mode, request_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                sess["mode"],
                sess["request_json"],
                sess["created_at"] or now,
            ),
        )
        new_session_id = cur.lastrowid

        # Migrate result events
        events = src_conn.execute(
            """
            SELECT track_id, rank, total_score, score_breakdown_json, created_at
            FROM search_result_events
            WHERE session_id = ?
            ORDER BY rank
            """,
            (sess["id"],),
        ).fetchall()

        for evt in events:
            v6_id = evt["track_id"]
            if v6_id not in track_map:
                continue
            track_info = track_map[v6_id]
            try:
                eval_conn.execute(
                    """
                    INSERT INTO search_result_events (
                        session_id, rank, track_id, track_uuid, content_generation,
                        snapshot_state, total_score, score_breakdown_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'current', ?, ?, ?)
                    """,
                    (
                        new_session_id,
                        evt["rank"],
                        track_info["track_id"],
                        track_info["track_uuid"],
                        track_info["content_generation"],
                        evt["total_score"],
                        evt["score_breakdown_json"],
                        evt["created_at"] or now,
                    ),
                )
            except sqlite3.Error as exc:
                LOGGER.warning("Skipping search_result_event: %s", exc)

    for run in cal_runs:
        try:
            eval_conn.execute(
                """
                INSERT INTO calibration_runs (
                    profile_name, search_mode, config_json, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run["profile_name"],
                    run["search_mode"],
                    run["config_json"],
                    run["metrics_json"],
                    run["created_at"] or now,
                ),
            )
        except sqlite3.Error as exc:
            LOGGER.warning("Skipping calibration_run: %s", exc)

    return True


def _rebuild_fts(core_conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 index from tracks + file_tags + maest_scores."""
    core_conn.execute("DELETE FROM track_search_fts")

    rows = core_conn.execute(
        """
        SELECT t.track_id, t.file_path,
               ft.title, ft.artist, ft.album, ft.comment, ft.label,
               ft.catalog_number, ft.country, ft.isrc, ft.year,
               ft.track_number, ft.disc_number, ft.genres_json,
               ms.genres_json AS maest_genres_json
        FROM tracks t
        LEFT JOIN file_tags ft ON ft.track_id = t.track_id
        LEFT JOIN maest_scores ms ON ms.track_id = t.track_id
        ORDER BY t.track_id
        """
    ).fetchall()

    for row in rows:
        # Extract MAEST genre names for FTS
        maest_genres_text = ""
        if row["maest_genres_json"]:
            try:
                genres = json.loads(row["maest_genres_json"])
                maest_genres_text = " ".join(g.get("genre_name", "") for g in genres)
            except (json.JSONDecodeError, TypeError):
                pass

        file_genres_text = ""
        if row["genres_json"]:
            try:
                genres = json.loads(row["genres_json"])
                file_genres_text = " ".join(str(g) for g in genres)
            except (json.JSONDecodeError, TypeError):
                pass

        core_conn.execute(
            """
            INSERT INTO track_search_fts (
                track_id, file_path, title, artist, album, comment, label,
                catalog_number, country, isrc, year, track_number, disc_number,
                file_genres, maest_genres
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["track_id"],
                row["file_path"],
                row["title"],
                row["artist"],
                row["album"],
                row["comment"],
                row["label"],
                row["catalog_number"],
                row["country"],
                row["isrc"],
                str(row["year"]) if row["year"] is not None else None,
                row["track_number"],
                row["disc_number"],
                file_genres_text or None,
                maest_genres_text or None,
            ),
        )


# ---------------------------------------------------------------------------
# Recovery manifest helpers
# ---------------------------------------------------------------------------


def _write_recovery_manifest(
    manifest_path: Path,
    migration_id: str,
    staged_core: Path,
    staged_artifacts: Path,
    staged_evaluation: Optional[Path],
    dest_core: Path,
    dest_artifacts: Path,
    dest_evaluation: Optional[Path],
) -> None:
    manifest = {
        "migration_id": migration_id,
        "schema_version": 7,
        "written_at": _now_iso(),
        "staged_core": str(staged_core),
        "staged_artifacts": str(staged_artifacts),
        "staged_evaluation": str(staged_evaluation) if staged_evaluation else None,
        "dest_core": str(dest_core),
        "dest_artifacts": str(dest_artifacts),
        "dest_evaluation": str(dest_evaluation) if dest_evaluation else None,
        "core_renamed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _mark_core_renamed(manifest_path: Path) -> None:
    """Update manifest to record that Core rename succeeded."""
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["core_renamed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception:
        pass  # Best-effort


def _check_stale_staging(
    manifest_path: Path,
    staging_dir: Path,
) -> Optional[str]:
    """Check for a stale staging directory from a previous interrupted migration.

    Returns an error message if stale staging was found and cleaned up,
    or None if no stale staging exists.

    The manifest records the *old* staging path (which may differ from the
    *new* staging_dir computed for this run).  We clean the old path from the
    manifest, not the new one.
    """
    if not manifest_path.exists() and not staging_dir.exists():
        return None

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("core_renamed"):
                # Core rename succeeded — migration is complete, don't clean up
                return (
                    f"A previous migration appears complete (Core was renamed). "
                    f"Destination already exists. Remove it manually if you want to re-migrate."
                )

            # Derive the old staging dir from the staged_core path in the manifest
            staged_core_str = manifest.get("staged_core", "")
            old_staging_dir: Optional[Path] = None
            if staged_core_str:
                old_staging_dir = Path(staged_core_str).parent
        except Exception:
            old_staging_dir = None

        # Incomplete migration — clean up old staging + manifest
        if old_staging_dir is not None and old_staging_dir.exists():
            shutil.rmtree(old_staging_dir, ignore_errors=True)
        elif staging_dir.exists():
            # Fallback: clean the new staging dir if old path unavailable
            shutil.rmtree(staging_dir, ignore_errors=True)
        manifest_path.unlink(missing_ok=True)
        return (
            f"Found incomplete migration staging at {old_staging_dir or staging_dir}. "
            f"Cleaned up. Re-run migrate-schema-v7 to start fresh."
        )

    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
        return (
            f"Found orphaned staging directory at {staging_dir} (no manifest). "
            f"Cleaned up. Re-run migrate-schema-v7 to start fresh."
        )

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def migrate_v7(
    source: "str | Path",
    destination: "str | Path",
    rhythm_lab_labels: Optional["str | Path"] = None,
    rhythm_lab_destination: Optional["str | Path"] = None,
    report_path: Optional["str | Path"] = None,
) -> dict:
    """Migrate a v6 SQLite library database to v7 (side-by-side).

    Args:
        source: Path to the v6 source database (opened read-only).
        destination: Path for the new v7 Core database (must not exist).
        rhythm_lab_labels: Optional path to v6 Rhythm Lab labels database.
        rhythm_lab_destination: Optional destination for migrated Rhythm Lab DB.
        report_path: Optional path to write the migration report JSON.

    Returns:
        Migration report dict.

    Raises:
        MigrationError: For actionable failures (wrong version, dest exists, etc.).
    """
    source = Path(source)
    destination = Path(destination)

    # Derived paths
    dest_parent = destination.parent
    dest_name = destination.name
    dest_stem = destination.stem
    dest_artifacts = dest_parent / f"{dest_stem}.artifacts.sqlite"
    dest_evaluation = dest_parent / f"{dest_stem}.evaluation.sqlite"

    migration_id = str(uuid.uuid4())
    staging_dir = dest_parent / f".{dest_name}.v7-migrate-{migration_id}"
    manifest_path = dest_parent / f".{dest_name}.v7-publication.json"

    # --- Pre-flight checks ---

    # Check for stale staging from a previous interrupted run
    stale_msg = _check_stale_staging(manifest_path, staging_dir)
    if stale_msg:
        raise MigrationError(stale_msg)

    if not source.exists():
        raise MigrationError(f"Source database not found: {source}")

    if destination.exists():
        raise MigrationError(
            f"Destination already exists: {destination}\n"
            f"Remove it manually or choose a different destination path."
        )
    if dest_artifacts.exists():
        raise MigrationError(
            f"Artifacts sidecar destination already exists: {dest_artifacts}\n"
            f"Remove it manually or choose a different destination path."
        )

    # Open source read-only
    src_conn = _open_source_readonly(source)
    try:
        # Verify source schema version
        user_version = src_conn.execute("PRAGMA user_version").fetchone()[0]
        if user_version != 6:
            raise MigrationError(
                f"Source database has user_version={user_version}, expected 6.\n"
                f"This command only migrates v6 → v7 databases."
            )

        # Get or generate catalog_uuid
        try:
            settings_row = src_conn.execute(
                "SELECT value FROM library_settings WHERE key = 'catalog_uuid'"
            ).fetchone()
            catalog_uuid = settings_row["value"] if settings_row else str(uuid.uuid4())
        except sqlite3.Error:
            catalog_uuid = str(uuid.uuid4())

        # Count v6 SONARA fingerprints for report
        discarded_v6_fingerprints = 0
        try:
            fp_count = src_conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE has_sonara_analysis = 1"
            ).fetchone()[0]
            discarded_v6_fingerprints = fp_count
        except sqlite3.Error:
            pass

        # Analyze embedding families before staging
        family_data = _analyze_embedding_families(src_conn)

        # Check if search history exists
        has_search_history = False
        try:
            sess_count = src_conn.execute("SELECT COUNT(*) FROM search_sessions").fetchone()[0]
            cal_count = src_conn.execute("SELECT COUNT(*) FROM calibration_runs").fetchone()[0]
            has_search_history = (sess_count + cal_count) > 0
        except sqlite3.Error:
            pass

        # --- Create staging directory ---
        staging_dir.mkdir(parents=True, exist_ok=False)

        staged_core = staging_dir / dest_name
        staged_artifacts = staging_dir / f"{dest_stem}.artifacts.sqlite"
        staged_evaluation = staging_dir / f"{dest_stem}.evaluation.sqlite" if has_search_history else None

        try:
            # Step 1: Online backup source → staging Core
            LOGGER.info("Backing up source to staging: %s", staged_core)
            _sqlite_backup(src_conn, staged_core)

            # Step 2: Apply v7 Core schema to the backup (replacing v6 schema)
            # We create a fresh v7 Core DB in staging
            from .db_schema_v7 import create_v7_schema
            from .db_artifacts import create_artifacts_sidecar_schema
            from .db_evaluation_sidecar import create_evaluation_sidecar_schema

            # Remove the backup and create fresh v7 Core
            staged_core.unlink()
            create_v7_schema(str(staged_core))

            # Step 3: Create artifacts sidecar
            create_artifacts_sidecar_schema(str(staged_artifacts), catalog_uuid=catalog_uuid)

            # Step 4: Create evaluation sidecar if needed
            if has_search_history:
                create_evaluation_sidecar_schema(str(staged_evaluation), catalog_uuid=catalog_uuid)

            # Open staging connections for writing
            core_conn = sqlite3.connect(str(staged_core))
            core_conn.execute("PRAGMA journal_mode = WAL")
            core_conn.execute("PRAGMA foreign_keys = ON")
            core_conn.row_factory = sqlite3.Row

            artifacts_conn = sqlite3.connect(str(staged_artifacts))
            artifacts_conn.execute("PRAGMA journal_mode = WAL")
            artifacts_conn.execute("PRAGMA foreign_keys = ON")

            eval_conn: Optional[sqlite3.Connection] = None
            if has_search_history and staged_evaluation:
                eval_conn = sqlite3.connect(str(staged_evaluation))
                eval_conn.execute("PRAGMA journal_mode = WAL")
                eval_conn.execute("PRAGMA foreign_keys = ON")

            try:
                # Insert library_catalog
                now = _now_iso()
                core_conn.execute(
                    """
                    INSERT INTO library_catalog (singleton_id, catalog_uuid, created_at, updated_at)
                    VALUES (1, ?, ?, ?)
                    """,
                    (catalog_uuid, now, now),
                )

                # Migrate library_settings
                try:
                    settings = src_conn.execute(
                        "SELECT key, value, updated_at FROM library_settings"
                    ).fetchall()
                    for s in settings:
                        try:
                            core_conn.execute(
                                """
                                INSERT OR IGNORE INTO library_settings (setting_key, setting_value, updated_at)
                                VALUES (?, ?, ?)
                                """,
                                (s["key"], s["value"], s["updated_at"] or now),
                            )
                        except sqlite3.Error:
                            pass
                except sqlite3.Error:
                    pass

                # Step 5: Migrate data
                with core_conn:
                    track_map, tracks_migrated, tracks_with_zero_mtime = _migrate_tracks_and_file_tags(
                        src_conn, core_conn, catalog_uuid
                    )

                with core_conn:
                    maest_scores_migrated = _migrate_maest_scores(src_conn, core_conn, track_map)

                with artifacts_conn:
                    embeddings_migrated, mixed_legacy_contracts = _migrate_embeddings(
                        src_conn, core_conn, artifacts_conn, track_map, family_data
                    )

                with core_conn:
                    classifier_migrated, classifier_discarded = _migrate_classifier_scores(
                        src_conn, core_conn, track_map
                    )

                with core_conn:
                    _migrate_likes(src_conn, core_conn, track_map)

                with core_conn:
                    _migrate_pair_feedback(src_conn, core_conn, track_map)

                with core_conn:
                    _migrate_transition_feedback(src_conn, core_conn, track_map)

                if eval_conn and has_search_history:
                    with eval_conn:
                        _migrate_search_history(src_conn, eval_conn, track_map, catalog_uuid)

                # Rebuild FTS
                with core_conn:
                    _rebuild_fts(core_conn)

            finally:
                core_conn.close()
                artifacts_conn.close()
                if eval_conn:
                    eval_conn.close()

            # Step 6: Write recovery manifest
            _write_recovery_manifest(
                manifest_path=manifest_path,
                migration_id=migration_id,
                staged_core=staged_core,
                staged_artifacts=staged_artifacts,
                staged_evaluation=staged_evaluation,
                dest_core=destination,
                dest_artifacts=dest_artifacts,
                dest_evaluation=dest_evaluation if has_search_history else None,
            )

            # Step 7: Publish — sidecars first, Core LAST
            LOGGER.info("Publishing artifacts sidecar: %s", dest_artifacts)
            shutil.move(str(staged_artifacts), str(dest_artifacts))

            if has_search_history and staged_evaluation and staged_evaluation.exists():
                LOGGER.info("Publishing evaluation sidecar: %s", dest_evaluation)
                shutil.move(str(staged_evaluation), str(dest_evaluation))

            # Rhythm Lab labels (if provided)
            rhythm_lab_migrated = False
            if rhythm_lab_labels and rhythm_lab_destination:
                rl_src = Path(rhythm_lab_labels)
                rl_dest = Path(rhythm_lab_destination)
                if rl_src.exists() and not rl_dest.exists():
                    staged_rl = staging_dir / rl_dest.name
                    rl_src_conn = _open_source_readonly(rl_src)
                    try:
                        _sqlite_backup(rl_src_conn, staged_rl)
                    finally:
                        rl_src_conn.close()
                    # Update source_core_schema_version from 6 to 7
                    rl_conn = sqlite3.connect(str(staged_rl))
                    try:
                        rl_conn.execute(
                            "UPDATE lab_catalog SET source_core_schema_version = 7 "
                            "WHERE source_core_schema_version = 6"
                        )
                        rl_conn.commit()
                    except sqlite3.Error:
                        pass
                    finally:
                        rl_conn.close()
                    shutil.move(str(staged_rl), str(rl_dest))
                    rhythm_lab_migrated = True

            # Core LAST
            LOGGER.info("Publishing Core (LAST): %s", destination)
            shutil.move(str(staged_core), str(destination))
            _mark_core_renamed(manifest_path)

            # Step 8: Cleanup staging + manifest
            shutil.rmtree(staging_dir, ignore_errors=True)
            manifest_path.unlink(missing_ok=True)

        except Exception:
            # Leave staging + manifest for recovery inspection
            LOGGER.exception("Migration failed; staging preserved at %s", staging_dir)
            raise

    finally:
        src_conn.close()

    # Build report
    report = {
        "migration_id": migration_id,
        "tracks_migrated": tracks_migrated,
        "file_tags_migrated": tracks_migrated,
        "maest_scores_migrated": maest_scores_migrated,
        "embeddings_migrated": embeddings_migrated,
        "classifier_scores_migrated": classifier_migrated,
        "classifier_scores_discarded": classifier_discarded,
        "discarded_v6_fingerprints": discarded_v6_fingerprints,
        "mixed_legacy_contracts": mixed_legacy_contracts,
        "tracks_with_zero_mtime": tracks_with_zero_mtime,
        "search_history_migrated": has_search_history,
        "rhythm_lab_labels_migrated": rhythm_lab_migrated,
        "warnings": [],
    }

    if report_path:
        Path(report_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOGGER.info("Migration report written to %s", report_path)

    LOGGER.info(
        "Migration complete: tracks=%d embeddings=%s discarded_fingerprints=%d",
        tracks_migrated,
        embeddings_migrated,
        discarded_v6_fingerprints,
    )
    return report

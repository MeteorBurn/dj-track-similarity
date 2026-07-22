from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Mapping
from dataclasses import dataclass

from .db_search_fts import fts_match_query, normalize_search_mode


SqlParam = str | float


@dataclass(frozen=True, slots=True)
class TrackListingRequest:
    query: str = ""
    preset: str = "all"
    liked_only: bool = False
    classifier_min_scores: Mapping[str, float] | None = None
    search_mode: str = "like"


@dataclass(frozen=True, slots=True)
class TrackListingQuery:
    where_sql: str
    params: tuple[SqlParam, ...]
    primary_classifier: tuple[str, float] | None
    fts_join_sql: str
    from_sql: str
    order_sql: str


def split_primary_classifier_filter(
    classifier_min_scores: dict[str, float] | None,
) -> tuple[tuple[str, float] | None, dict[str, float]]:
    items = list((classifier_min_scores or {}).items())
    if not items:
        return None, {}
    classifier, threshold = items[0]
    return (str(classifier), float(threshold)), {str(key): float(value) for key, value in items[1:]}


def combine_where_condition(condition_sql: str, where_sql: str) -> str:
    if not where_sql:
        return f"WHERE {condition_sql}"
    return f"WHERE {condition_sql} AND {where_sql.removeprefix('WHERE ').strip()}"


def build_track_listing_query(request: TrackListingRequest) -> TrackListingQuery:
    mode = normalize_search_mode(request.search_mode)
    use_fts = mode == "fts" and bool(request.query.strip())
    fts_query = fts_match_query(request.query) if use_fts else ""
    thresholds = dict(request.classifier_min_scores or {})
    primary_classifier, remaining_thresholds = split_primary_classifier_filter(thresholds)
    where_sql, params = build_track_filter_sql(
        query="" if use_fts else request.query,
        preset=request.preset,
        liked_only=request.liked_only,
        classifier_min_scores=remaining_thresholds if primary_classifier else thresholds,
    )
    if use_fts:
        condition = "track_search_fts MATCH ?" if fts_query else "0 = 1"
        where_sql = combine_where_condition(condition, where_sql)
        if fts_query:
            params = [fts_query, *params]
    return TrackListingQuery(
        where_sql=where_sql,
        params=tuple(params),
        primary_classifier=primary_classifier,
        fts_join_sql="JOIN track_search_fts fts ON fts.track_id = t.id" if use_fts and fts_query else "",
        from_sql="track_search_fts fts JOIN tracks t ON t.id = fts.track_id" if use_fts and fts_query else "tracks t",
        order_sql=track_order_sql(liked_only=request.liked_only, classifier_min_scores=thresholds),
    )


def build_track_filter_sql(
    *,
    query: str,
    preset: str,
    liked_only: bool = False,
    classifier_min_scores: dict[str, float] | None = None,
) -> tuple[str, list[SqlParam]]:
    where_parts: list[str] = []
    params: list[SqlParam] = []
    needle = query.strip().lower()
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
    if preset == "syncopated":
        where_parts.append("json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif preset != "all":
        raise ValueError(f"Unknown library preset: {preset}")
    if liked_only:
        where_parts.append("EXISTS (SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id)")
    for classifier, threshold in (classifier_min_scores or {}).items():
        where_parts.append(
            """
            EXISTS (
                SELECT 1
                FROM track_classifier_scores cs
                WHERE cs.track_id = t.id
                  AND cs.classifier = ?
                  AND cs.score >= ?
            )
            """
        )
        params.extend([classifier, float(threshold)])
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, params


def track_order_sql(*, liked_only: bool = False, classifier_min_scores: dict[str, float] | None = None) -> str:
    fallback_order = "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    liked_order = ""
    if liked_only:
        liked_order = "(SELECT tl.liked_at FROM track_likes tl WHERE tl.track_id = t.id) ASC, "
    classifiers = list((classifier_min_scores or {}).keys())
    if not classifiers:
        return liked_order + fallback_order
    classifier = classifiers[0].replace("'", "''")
    classifier_order = (
        "(SELECT cs.score FROM track_classifier_scores cs "
        f"WHERE cs.track_id = t.id AND cs.classifier = '{classifier}') DESC, "
    )
    return liked_order + classifier_order + fallback_order


# ---------------------------------------------------------------------------
# v7 track assembly — reads from v7 Core + Artifacts sidecar connections.
# These functions do NOT touch v6 code paths above.
# ---------------------------------------------------------------------------

# Sidecar embedding tables and their analysis_family names.
_SIDECAR_EMBEDDING_TABLES: list[tuple[str, str]] = [
    ("mert_embeddings", "mert"),
    ("muq_embeddings", "muq"),
    ("clap_embeddings", "clap"),
    ("maest_embeddings", "maest"),
    ("sonara_similarity_embeddings", "sonara"),
]

# SONARA timbre blob specs: (vector_type, dim)
_SONARA_TIMBRE_BLOBS: list[tuple[str, int]] = [
    ("mfcc_mean", 13),
    ("chroma_mean", 12),
    ("spectral_contrast_mean", 7),
]


def _decode_json_list(raw: str | None) -> list:
    """Safely decode a JSON array string; returns [] on None or error."""
    if raw is None:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _decode_json_dict(raw: str | None) -> dict:
    """Safely decode a JSON object string; returns {} on None or error."""
    if raw is None:
        return {}
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _check_exists(conn: sqlite3.Connection, sql: str, params: tuple) -> bool:
    """Return True if the given EXISTS query returns a row."""
    row = conn.execute(sql, params).fetchone()
    return bool(row and row[0])


def _build_analysis_coverage(
    core_conn: sqlite3.Connection,
    artifacts_conn: sqlite3.Connection,
    track_id: int,
    sonara_active_release_hash: str | None,
) -> dict[str, bool]:
    """Build the analysis_coverage dict for a track."""
    # sonara_core: row exists in sonara table matching the active release contract
    if sonara_active_release_hash is not None:
        sonara_core = _check_exists(
            core_conn,
            """
            SELECT 1 FROM sonara s
            JOIN contracts c ON c.contract_hash = s.contract_hash
            WHERE s.track_id = ?
              AND c.release_hash = ?
            LIMIT 1
            """,
            (track_id, sonara_active_release_hash),
        )
    else:
        sonara_core = _check_exists(
            core_conn,
            "SELECT 1 FROM sonara WHERE track_id = ? LIMIT 1",
            (track_id,),
        )

    maest = _check_exists(
        core_conn,
        "SELECT 1 FROM maest_scores WHERE track_id = ? LIMIT 1",
        (track_id,),
    )

    mert = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM mert_embeddings WHERE track_id = ? LIMIT 1",
        (track_id,),
    )
    muq = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM muq_embeddings WHERE track_id = ? LIMIT 1",
        (track_id,),
    )
    clap = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM clap_embeddings WHERE track_id = ? LIMIT 1",
        (track_id,),
    )
    sonara_embedding = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM sonara_similarity_embeddings WHERE track_id = ? LIMIT 1",
        (track_id,),
    )
    timeline = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM sonara_timeline WHERE track_id = ? LIMIT 1",
        (track_id,),
    )
    fingerprint = _check_exists(
        artifacts_conn,
        "SELECT 1 FROM sonara_fingerprints WHERE track_id = ? LIMIT 1",
        (track_id,),
    )

    return {
        "sonara_core": sonara_core,
        "timeline": timeline,
        "sonara_embedding": sonara_embedding,
        "fingerprint": fingerprint,
        "maest": maest,
        "mert": mert,
        "muq": muq,
        "clap": clap,
    }


def _build_classifier_summary(core_conn: sqlite3.Connection, track_id: int) -> list[dict]:
    """Return classifier score summaries (no probabilities_json, no contract details)."""
    rows = core_conn.execute(
        """
        SELECT classifier_key, score, predicted_class, score_bucket, confidence
        FROM classifier_scores
        WHERE track_id = ?
        ORDER BY classifier_key
        """,
        (track_id,),
    ).fetchall()
    return [
        {
            "classifier_key": row[0],
            "score": row[1],
            "predicted_class": row[2],
            "score_bucket": row[3],
            "confidence": row[4],
        }
        for row in rows
    ]


def assemble_track_summary_v7(
    core_conn: sqlite3.Connection,
    artifacts_conn: sqlite3.Connection,
    track_id: int,
    sonara_active_release_hash: str | None = None,
) -> dict | None:
    """Assemble a TrackSummaryV7-shaped dict from v7 Core + Artifacts DBs.

    Returns None when the track_id does not exist in the v7 tracks table.
    Never exposes metadata_json, has_* flags, contract_hash values, or raw BLOB bytes.
    """
    # --- tracks row ---
    track_row = core_conn.execute(
        """
        SELECT track_id, file_path, audio_duration_seconds
        FROM tracks
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()
    if track_row is None:
        return None

    # --- file_tags row (optional) ---
    tags_row = core_conn.execute(
        """
        SELECT title, artist, album, tag_bpm, tag_key
        FROM file_tags
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()

    title = tags_row[0] if tags_row else None
    artist = tags_row[1] if tags_row else None
    album = tags_row[2] if tags_row else None
    tag_bpm = tags_row[3] if tags_row else None
    tag_key = tags_row[4] if tags_row else None

    # --- liked ---
    liked = _check_exists(
        core_conn,
        "SELECT 1 FROM likes WHERE track_id = ? LIMIT 1",
        (track_id,),
    )

    # --- analysis coverage ---
    analysis_coverage = _build_analysis_coverage(
        core_conn, artifacts_conn, track_id, sonara_active_release_hash
    )

    # --- classifier summaries ---
    classifier_scores = _build_classifier_summary(core_conn, track_id)

    return {
        "track_id": track_row[0],
        "file_path": track_row[1],
        "title": title,
        "artist": artist,
        "album": album,
        "tag_bpm": tag_bpm,
        "tag_key": tag_key,
        "audio_duration_seconds": track_row[2],
        "liked": liked,
        "analysis_coverage": analysis_coverage,
        "classifier_scores": classifier_scores,
    }


def assemble_track_detail_v7(
    core_conn: sqlite3.Connection,
    artifacts_conn: sqlite3.Connection,
    track_id: int,
    sonara_active_release_hash: str | None = None,
) -> dict | None:
    """Assemble a TrackDetailV7-shaped dict from v7 Core + Artifacts DBs.

    Returns None when the track_id does not exist in the v7 tracks table.
    Never exposes metadata_json, has_* flags, contract_hash values, or raw BLOB bytes.
    """
    # --- tracks row (full) ---
    track_row = core_conn.execute(
        """
        SELECT track_id, file_path,
               file_size_bytes, file_modified_ns,
               audio_format, audio_codec,
               sample_rate_hz, channel_count, bit_rate_bps,
               audio_duration_seconds,
               last_scanned_at, missing_since
        FROM tracks
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()
    if track_row is None:
        return None

    (
        t_track_id, t_file_path,
        t_file_size_bytes, t_file_modified_ns,
        t_audio_format, t_audio_codec,
        t_sample_rate_hz, t_channel_count, t_bit_rate_bps,
        t_audio_duration_seconds,
        t_last_scanned_at, t_missing_since,
    ) = track_row

    file_technical = {
        "file_size_bytes": t_file_size_bytes,
        "file_modified_ns": t_file_modified_ns,
        "audio_format": t_audio_format,
        "audio_codec": t_audio_codec,
        "sample_rate_hz": t_sample_rate_hz,
        "channel_count": t_channel_count,
        "bit_rate_bps": t_bit_rate_bps,
        "audio_duration_seconds": t_audio_duration_seconds,
        "last_scanned_at": t_last_scanned_at,
        "missing_since": t_missing_since,
    }

    # --- file_tags row (full, optional) ---
    tags_row = core_conn.execute(
        """
        SELECT title, artist, album, tag_bpm, tag_key,
               comment, year, label, catalog_number, country,
               isrc, track_number, disc_number, genres_json, tags_read_at
        FROM file_tags
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()

    file_tags_dict: dict | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    tag_bpm: float | None = None
    tag_key: str | None = None

    if tags_row is not None:
        title = tags_row[0]
        artist = tags_row[1]
        album = tags_row[2]
        tag_bpm = tags_row[3]
        tag_key = tags_row[4]
        file_tags_dict = {
            "title": tags_row[0],
            "artist": tags_row[1],
            "album": tags_row[2],
            "tag_bpm": tags_row[3],
            "tag_key": tags_row[4],
            "comment": tags_row[5],
            "year": tags_row[6],
            "label": tags_row[7],
            "catalog_number": tags_row[8],
            "country": tags_row[9],
            "isrc": tags_row[10],
            "track_number": tags_row[11],
            "disc_number": tags_row[12],
            "genres": _decode_json_list(tags_row[13]),
            "tags_read_at": tags_row[14],
        }

    # --- liked ---
    liked = _check_exists(
        core_conn,
        "SELECT 1 FROM likes WHERE track_id = ? LIMIT 1",
        (track_id,),
    )

    # --- analysis coverage ---
    analysis_coverage = _build_analysis_coverage(
        core_conn, artifacts_conn, track_id, sonara_active_release_hash
    )

    # --- SONARA Core (scalars only, no BLOBs) ---
    sonara_row = core_conn.execute(
        """
        SELECT
            detected_bpm, raw_bpm, bpm_confidence,
            onset_density_per_second, beat_count, tempo_variability,
            beat_grid_offset_seconds, beat_grid_stability, bpm_candidates_json,
            detected_key_name, detected_key_camelot, key_confidence,
            predominant_chord, chord_changes_per_second, key_candidates_json,
            energy_score, energy_level, danceability_score, valence_score,
            acousticness_score, dissonance_score,
            spectral_centroid_hz, spectral_bandwidth_hz, spectral_rolloff_hz,
            spectral_flatness, zero_crossing_rate,
            rms_mean, rms_max, integrated_loudness_lufs, dynamic_range_db,
            true_peak_dbtp, replay_gain_db, max_momentary_loudness_lufs, loudness_range_lu,
            analyzed_duration_seconds, intro_end_seconds, outro_start_seconds,
            leading_silence_seconds, trailing_silence_seconds,
            energy_curve_hop_seconds, energy_curve_sample_count,
            energy_curve_min, energy_curve_max, energy_curve_mean, energy_curve_stddev,
            vocal_probability, mood_happy_score, mood_aggressive_score,
            mood_relaxed_score, mood_sad_score,
            analyzed_at
        FROM sonara
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()

    sonara_core_dict: dict | None = None
    if sonara_row is not None:
        (
            s_detected_bpm, s_raw_bpm, s_bpm_confidence,
            s_onset_density, s_beat_count, s_tempo_variability,
            s_beat_grid_offset, s_beat_grid_stability, s_bpm_candidates_json,
            s_key_name, s_key_camelot, s_key_confidence,
            s_predominant_chord, s_chord_changes, s_key_candidates_json,
            s_energy_score, s_energy_level, s_danceability, s_valence,
            s_acousticness, s_dissonance,
            s_spectral_centroid, s_spectral_bandwidth, s_spectral_rolloff,
            s_spectral_flatness, s_zero_crossing,
            s_rms_mean, s_rms_max, s_integrated_loudness, s_dynamic_range,
            s_true_peak, s_replay_gain, s_max_momentary, s_loudness_range,
            s_analyzed_duration, s_intro_end, s_outro_start,
            s_leading_silence, s_trailing_silence,
            s_curve_hop, s_curve_count,
            s_curve_min, s_curve_max, s_curve_mean, s_curve_stddev,
            s_vocal_prob, s_mood_happy, s_mood_aggressive,
            s_mood_relaxed, s_mood_sad,
            s_analyzed_at,
        ) = sonara_row

        sonara_core_dict = {
            "detected_bpm": s_detected_bpm,
            "raw_bpm": s_raw_bpm,
            "bpm_confidence": s_bpm_confidence,
            "onset_density_per_second": s_onset_density,
            "beat_count": s_beat_count,
            "tempo_variability": s_tempo_variability,
            "beat_grid_offset_seconds": s_beat_grid_offset,
            "beat_grid_stability": s_beat_grid_stability,
            "bpm_candidates": _decode_json_list(s_bpm_candidates_json),
            "detected_key_name": s_key_name,
            "detected_key_camelot": s_key_camelot,
            "key_confidence": s_key_confidence,
            "predominant_chord": s_predominant_chord,
            "chord_changes_per_second": s_chord_changes,
            "key_candidates": _decode_json_list(s_key_candidates_json),
            "energy_score": s_energy_score,
            "energy_level": s_energy_level,
            "danceability_score": s_danceability,
            "valence_score": s_valence,
            "acousticness_score": s_acousticness,
            "dissonance_score": s_dissonance,
            "spectral_centroid_hz": s_spectral_centroid,
            "spectral_bandwidth_hz": s_spectral_bandwidth,
            "spectral_rolloff_hz": s_spectral_rolloff,
            "spectral_flatness": s_spectral_flatness,
            "zero_crossing_rate": s_zero_crossing,
            "rms_mean": s_rms_mean,
            "rms_max": s_rms_max,
            "integrated_loudness_lufs": s_integrated_loudness,
            "dynamic_range_db": s_dynamic_range,
            "true_peak_dbtp": s_true_peak,
            "replay_gain_db": s_replay_gain,
            "max_momentary_loudness_lufs": s_max_momentary,
            "loudness_range_lu": s_loudness_range,
            "analyzed_duration_seconds": s_analyzed_duration,
            "intro_end_seconds": s_intro_end,
            "outro_start_seconds": s_outro_start,
            "leading_silence_seconds": s_leading_silence,
            "trailing_silence_seconds": s_trailing_silence,
            "energy_curve_hop_seconds": s_curve_hop,
            "energy_curve_sample_count": s_curve_count,
            "energy_curve_min": s_curve_min,
            "energy_curve_max": s_curve_max,
            "energy_curve_mean": s_curve_mean,
            "energy_curve_stddev": s_curve_stddev,
            "vocal_probability": s_vocal_prob,
            "mood_happy_score": s_mood_happy,
            "mood_aggressive_score": s_mood_aggressive,
            "mood_relaxed_score": s_mood_relaxed,
            "mood_sad_score": s_mood_sad,
            # Timbre vector summaries — dim only, no raw bytes
            "vector_summaries": [
                {"vector_type": vtype, "dim": dim}
                for vtype, dim in _SONARA_TIMBRE_BLOBS
            ],
            "analyzed_at": s_analyzed_at,
        }

    # --- MAEST scores ---
    maest_row = core_conn.execute(
        """
        SELECT syncopated_rhythm, genres_json, analyzed_at
        FROM maest_scores
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()

    maest_dict: dict | None = None
    if maest_row is not None:
        syncopated_raw = maest_row[0]
        maest_dict = {
            "syncopated_rhythm": bool(syncopated_raw) if syncopated_raw is not None else None,
            "genres": _decode_json_list(maest_row[1]),
            "analyzed_at": maest_row[2],
        }

    # --- Embedding summaries from sidecar (no raw bytes) ---
    embeddings: list[dict] = []
    for table, family in _SIDECAR_EMBEDDING_TABLES:
        emb_row = artifacts_conn.execute(
            f"SELECT contract_hash, dim, normalization, analyzed_at FROM {table} WHERE track_id = ?",  # noqa: S608
            (track_id,),
        ).fetchone()
        if emb_row is not None:
            # Resolve model_name and model_version from Core contracts (no hash exposed)
            contract_row = core_conn.execute(
                "SELECT model_name, model_version FROM contracts WHERE contract_hash = ? LIMIT 1",
                (emb_row[0],),
            ).fetchone()
            model_name = contract_row[0] if contract_row else ""
            model_version = contract_row[1] if contract_row else None
            embeddings.append({
                "analysis_family": family,
                "model_name": model_name,
                "model_version": model_version,
                "dim": emb_row[1],
                "normalization": emb_row[2],
                "analyzed_at": emb_row[3],
            })

    # --- Classifier score details ---
    cs_rows = core_conn.execute(
        """
        SELECT classifier_key, score, predicted_class, score_bucket, confidence,
               probabilities_json, feature_set, model_id, analyzed_at
        FROM classifier_scores
        WHERE track_id = ?
        ORDER BY classifier_key
        """,
        (track_id,),
    ).fetchall()

    classifier_scores_detail: list[dict] = []
    for row in cs_rows:
        classifier_scores_detail.append({
            "classifier_key": row[0],
            "score": row[1],
            "predicted_class": row[2],
            "score_bucket": row[3],
            "confidence": row[4],
            "probabilities": _decode_json_dict(row[5]),
            "feature_set": row[6],
            "model_id": row[7],
            "analyzed_at": row[8],
        })

    # Classifier summary (same as summary function)
    classifier_scores_summary = [
        {
            "classifier_key": d["classifier_key"],
            "score": d["score"],
            "predicted_class": d["predicted_class"],
            "score_bucket": d["score_bucket"],
            "confidence": d["confidence"],
        }
        for d in classifier_scores_detail
    ]

    # --- optional_outputs ---
    timeline_row = artifacts_conn.execute(
        "SELECT payload_json FROM sonara_timeline WHERE track_id = ? LIMIT 1",
        (track_id,),
    ).fetchone()
    timeline_fields: list[str] = []
    if timeline_row is not None:
        payload = _decode_json_dict(timeline_row[0])
        timeline_fields = [k for k in payload.keys() if isinstance(k, str)]

    optional_outputs = {
        "timeline_fields": timeline_fields,
        "sonara_embedding_available": analysis_coverage["sonara_embedding"],
        "audio_fingerprint_available": analysis_coverage["fingerprint"],
    }

    return {
        # Summary fields
        "track_id": t_track_id,
        "file_path": t_file_path,
        "title": title,
        "artist": artist,
        "album": album,
        "tag_bpm": tag_bpm,
        "tag_key": tag_key,
        "audio_duration_seconds": t_audio_duration_seconds,
        "liked": liked,
        "analysis_coverage": analysis_coverage,
        "classifier_scores": classifier_scores_summary,
        # Detail sub-models
        "file": file_technical,
        "file_tags": file_tags_dict,
        "sonara_core": sonara_core_dict,
        "maest": maest_dict,
        "embeddings": embeddings,
        "classifier_scores_detail": classifier_scores_detail,
        "optional_outputs": optional_outputs,
    }

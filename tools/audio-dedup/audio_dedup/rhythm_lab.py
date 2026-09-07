from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable

from dj_track_similarity.track_models import TrackIdentity

from . import report_selection as report_selection_module
from . import values as values_module


def rhythm_lab_impact_payload(
    rhythm_lab_db: Path | None,
    candidates: Iterable[dict[str, object]],
) -> dict[str, object]:
    candidate_rows = tuple(candidates)
    identities = report_selection_module._unique_identities(
        report_selection_module._candidate_identity(candidate)
        for candidate in candidate_rows
    )
    ids = tuple(sorted(identity.track_id for identity in identities))
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False) if rhythm_lab_db is not None else None
    payload: dict[str, object] = {
        "database_path": str(selected_db) if selected_db is not None else None,
        "database_exists": bool(selected_db and selected_db.exists()),
        "safe_candidate_track_ids": list(ids),
        "affected_track_count": 0,
        "affected_row_count": 0,
        "affected_rows": [],
    }
    payload["summary"] = rhythm_lab_summary(payload)
    if not ids or selected_db is None or not selected_db.exists():
        return payload

    affected_rows: list[dict[str, object]] = []
    connection = _connect_readonly(selected_db)
    try:
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        wanted_columns = (
            "catalog_uuid",
            "track_uuid",
            "classifier_key",
            "label",
            "selected_path",
            "feature_set",
            "model_artifact",
            "confidence",
        )
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            table_columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()]
            if not _has_identity_columns(table_columns):
                continue
            selected_columns = [column for column in wanted_columns if column in table_columns]
            select_sql = ", ".join(_quote_sqlite_identifier(column) for column in selected_columns)
            for chunk in values_module._chunks(list(identities), 200):
                identity_sql, parameters = _identity_predicate(chunk)
                rows = connection.execute(
                    f"""
                    SELECT {select_sql}
                    FROM {quoted_table}
                    WHERE {identity_sql}
                    ORDER BY catalog_uuid, track_uuid
                    """,
                    parameters,
                ).fetchall()
                for row in rows:
                    affected_rows.append(
                        {
                            "action": "DELETE ON APPLY",
                            "table_name": table_name,
                            "catalog_uuid": str(row["catalog_uuid"]),
                            "track_uuid": str(row["track_uuid"]),
                            "classifier_key": row["classifier_key"] if "classifier_key" in row.keys() else None,
                            "label": row["label"] if "label" in row.keys() else None,
                            "path": row["selected_path"] if "selected_path" in row.keys() else None,
                            "feature_set": row["feature_set"] if "feature_set" in row.keys() else None,
                            "model_artifact": row["model_artifact"] if "model_artifact" in row.keys() else None,
                            "confidence": values_module._round_float(row["confidence"]) if "confidence" in row.keys() else None,
                        }
                    )
    finally:
        connection.close()

    affected_rows.sort(
        key=lambda row: (
            str(row["catalog_uuid"]),
            str(row["track_uuid"]),
            str(row["table_name"]),
            str(row.get("classifier_key") or ""),
            str(row.get("feature_set") or ""),
            str(row.get("model_artifact") or ""),
        )
    )
    payload["affected_rows"] = affected_rows
    payload["affected_track_count"] = len(
        {
            (
                str(row["catalog_uuid"]),
                str(row["track_uuid"]),
            )
            for row in affected_rows
        }
    )
    payload["affected_row_count"] = len(affected_rows)
    payload["summary"] = rhythm_lab_summary(payload)
    return payload


def rhythm_lab_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "safe_candidate_count": len(payload.get("safe_candidate_track_ids", [])),
        "database_exists": bool(payload.get("database_exists", False)),
        "affected_track_count": int(payload.get("affected_track_count", 0) or 0),
        "affected_row_count": int(payload.get("affected_row_count", 0) or 0),
    }


def rhythm_lab_summary_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = rhythm_lab_summary(payload)
    return (
        f"safe_candidates={int(summary.get('safe_candidate_count', 0) or 0)} "
        f"database_exists={values_module._bool_text(bool(summary.get('database_exists', False)))} "
        f"affected_tracks={int(summary.get('affected_track_count', 0) or 0)} "
        f"affected_rows={int(summary.get('affected_row_count', 0) or 0)}"
    )


def rhythm_lab_cli_summary(payload: dict[str, object]) -> str:
    rhythm_lab = payload.get("rhythm_lab", {})
    if not isinstance(rhythm_lab, dict):
        return "Rhythm Lab: unavailable"
    return f"Rhythm Lab: {rhythm_lab_summary_text(rhythm_lab)}"


def cleanup_rhythm_lab_database(
    rhythm_lab_db: Path | None,
    identities: Iterable[TrackIdentity],
) -> int:
    selected_identities = report_selection_module._unique_identities(identities)
    if not selected_identities or rhythm_lab_db is None:
        return 0
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False)
    if not selected_db.exists():
        return 0
    deleted_rows = 0
    connection = sqlite3.connect(selected_db)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()}
            if not _has_identity_columns(columns):
                continue
            for chunk in values_module._chunks(list(selected_identities), 200):
                identity_sql, parameters = _identity_predicate(chunk)
                cursor = connection.execute(
                    f"DELETE FROM {quoted_table} WHERE {identity_sql}",
                    parameters,
                )
                deleted_rows += int(cursor.rowcount if cursor.rowcount is not None else 0)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()
    return deleted_rows


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _has_identity_columns(columns: Iterable[str]) -> bool:
    return {
        "catalog_uuid",
        "track_uuid",
    }.issubset(set(columns))


def _identity_predicate(
    identities: list[TrackIdentity],
) -> tuple[str, tuple[object, ...]]:
    if not identities:
        raise ValueError("At least one identity is required")
    predicates: list[str] = []
    parameters: list[object] = []
    for identity in identities:
        predicates.append(
            "(catalog_uuid = ? AND track_uuid = ?)"
        )
        parameters.extend(
            (
                identity.catalog_uuid,
                identity.track_uuid,
            )
        )
    return " OR ".join(predicates), tuple(parameters)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{Path(path).resolve(strict=False).as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection

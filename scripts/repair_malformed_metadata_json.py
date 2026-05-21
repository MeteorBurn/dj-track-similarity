from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time repair for tracks.metadata_json values that are not valid JSON."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("dj-track-similarity.sqlite"),
        help="Path to the SQLite database. Defaults to dj-track-similarity.sqlite in the current directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Replace invalid tracks.metadata_json values with '{}'. Without this flag the script only reports rows.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped .bak copy before applying changes.",
    )
    args = parser.parse_args()

    db_path = args.db.expanduser().resolve(strict=False)
    if not db_path.is_file():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tracks'"
        ).fetchone()
        if table is None:
            print(f"tracks table not found in {db_path}", file=sys.stderr)
            return 1

        rows = connection.execute(
            """
            SELECT id, path, substr(metadata_json, 1, 120) AS metadata_preview
            FROM tracks
            WHERE NOT json_valid(metadata_json)
            ORDER BY id
            """
        ).fetchall()

        if not rows:
            print(f"no malformed tracks.metadata_json rows found in {db_path}")
            return 0

        print(f"malformed tracks.metadata_json rows: {len(rows)}")
        for row in rows:
            print(f"id={row['id']} path={row['path']} preview={row['metadata_preview']!r}")

        if not args.apply:
            print("dry-run only; rerun with --apply to repair salvageable JSON or replace unrecoverable values with '{}'")
            return 0

        if not args.no_backup:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = db_path.with_name(f"{db_path.name}.{timestamp}.bak")
            with sqlite3.connect(backup_path) as backup_connection:
                connection.backup(backup_connection)
            print(f"backup created: {backup_path}")

        for row in rows:
            repaired_json = _repair_metadata_json(str(row["metadata_preview"]), row["id"], connection)
            connection.execute(
                """
                UPDATE tracks
                SET metadata_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (repaired_json, row["id"]),
            )
        print(f"repaired rows: {len(rows)}")

    return 0


def _repair_metadata_json(preview: str, track_id: int, connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
    raw = str(row["metadata_json"] if row is not None else preview)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "{}"
    sanitized = _json_safe_value(parsed)
    if not isinstance(sanitized, dict):
        return "{}"
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _json_safe_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


if __name__ == "__main__":
    raise SystemExit(main())

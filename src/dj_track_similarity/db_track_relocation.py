"""Relocation planning and path writes within a caller-owned transaction."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from .db_search_fts import upsert_track_search_fts
from .track_models import MissingRelocationFile, RelocationChange, RelocationConflict


def _relocated_path(
    file_path: str,
    *,
    old_root: str,
    new_root: str,
    path_key: Callable[[str], str],
) -> str | None:
    file_path_key = path_key(file_path)
    old_root_key = path_key(old_root)
    if file_path_key == old_root_key:
        return new_root
    prefix = f"{old_root_key}/"
    if not file_path_key.startswith(prefix):
        return None
    return f"{new_root}/{file_path[len(prefix):]}"


def _plan_relocation(
    rows: Sequence[sqlite3.Row],
    *,
    old_root: str,
    new_root: str,
    path_key: Callable[[str], str],
) -> tuple[
    list[RelocationChange],
    list[RelocationConflict],
    list[MissingRelocationFile],
]:
    provisional: list[RelocationChange] = []
    for row in rows:
        old_path = str(row[2])
        new_path = _relocated_path(
            old_path,
            old_root=old_root,
            new_root=new_root,
            path_key=path_key,
        )
        if new_path is None:
            continue
        provisional.append(
            RelocationChange(
                track_id=int(row[0]),
                track_uuid=str(row[1]),
                old_path=old_path,
                new_path=new_path,
            )
        )

    moving_ids = {change["track_id"] for change in provisional}
    existing_by_path = {
        path_key(str(row[2])): int(row[0])
        for row in rows
    }
    planned_by_path: dict[str, int] = {}
    conflicts: list[RelocationConflict] = []
    missing_files: list[MissingRelocationFile] = []
    for change in provisional:
        new_path_key = path_key(change["new_path"])
        existing_track_id = existing_by_path.get(new_path_key)
        if (
            existing_track_id is not None
            and existing_track_id != change["track_id"]
            and existing_track_id not in moving_ids
        ):
            conflicts.append(
                RelocationConflict(
                    **change,
                    existing_track_id=existing_track_id,
                )
            )
        planned_track_id = planned_by_path.get(new_path_key)
        if (
            planned_track_id is not None
            and planned_track_id != change["track_id"]
        ):
            conflicts.append(
                RelocationConflict(
                    **change,
                    existing_track_id=planned_track_id,
                )
            )
        planned_by_path[new_path_key] = change["track_id"]
        if not Path(change["new_path"]).is_file():
            missing_files.append(
                MissingRelocationFile(
                    track_id=change["track_id"],
                    path=change["new_path"],
                )
            )
    return provisional, conflicts, missing_files


def _temporary_relocation_path(
    old_path: str,
    occupied_paths: set[str],
) -> str:
    while True:
        candidate = f"{old_path}.relocating-{uuid.uuid4().hex}"
        if candidate not in occupied_paths:
            return candidate


def _apply_relocation_paths(
    connection: sqlite3.Connection,
    rows: Sequence[sqlite3.Row],
    changes: Sequence[RelocationChange],
    timestamp: str,
) -> None:
    occupied_paths = {
        str(row[2])
        for row in rows
    } | {
        change["new_path"]
        for change in changes
    }
    temporary_paths: dict[int, str] = {}
    for change in changes:
        temporary_path = _temporary_relocation_path(
            change["old_path"],
            occupied_paths,
        )
        occupied_paths.add(temporary_path)
        temporary_paths[change["track_id"]] = temporary_path
        cursor = connection.execute(
            """
            UPDATE tracks
            SET file_path = ?,
                updated_at = ?
            WHERE track_id = ?
              AND track_uuid = ?
              AND file_path = ?
            """,
            (
                temporary_path,
                timestamp,
                change["track_id"],
                change["track_uuid"],
                change["old_path"],
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                "Track identity changed during relocation: "
                f"{change['track_id']}"
            )
    for change in changes:
        cursor = connection.execute(
            """
            UPDATE tracks
            SET file_path = ?,
                updated_at = ?
            WHERE track_id = ?
              AND track_uuid = ?
              AND file_path = ?
            """,
            (
                change["new_path"],
                timestamp,
                change["track_id"],
                change["track_uuid"],
                temporary_paths[change["track_id"]],
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                "Track identity changed during relocation: "
                f"{change['track_id']}"
            )
        upsert_track_search_fts(
            connection,
            change["track_id"],
        )

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Callable, Collection, Iterable

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.tracks import canonical_file_path
from dj_track_similarity.track_models import TrackIdentity

from . import config as config_module
from . import models as models_module
from . import report_selection as report_selection_module
from . import rhythm_lab as rhythm_lab_module
from . import track_loading as track_loading_module


def apply_duplicate_deletions(
    *,
    db_path: Path | None = None,
    database: LibraryDatabase | None = None,
    root: Path,
    payload: dict[str, object],
    rhythm_lab_db: Path | None = None,
    selected_track_ids: Collection[int] | None = None,
    deletion_mode: str = config_module.DELETION_MODE_PERMANENT,
) -> models_module.ApplyResult:
    selected_database = track_loading_module._resolve_database(database=database, db_path=db_path)
    remove_file = _file_remover(deletion_mode)
    root_text = canonical_file_path(root)
    deleted_ids: list[int] = []
    deleted_paths: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    if selected_track_ids is None:
        candidates = report_selection_module.safe_delete_candidates(payload)
        retained_paths = _keeper_retained_paths(payload)
        retained_missing_reason = "keeper file is missing on disk"
    else:
        candidates = report_selection_module.selected_delete_candidates(payload, selected_track_ids)
        retained_paths = _selection_retained_paths(
            payload,
            {report_selection_module._candidate_track_id(candidate) for candidate in candidates},
        )
        retained_missing_reason = "group would lose every copy"
    retained_on_disk: dict[str, bool] = {}
    deleted_identities: list[TrackIdentity] = []
    for candidate in candidates:
        track_id = report_selection_module._candidate_track_id(candidate)
        path_text = str(candidate.get("path", ""))
        if not track_loading_module._path_matches(path_text, root_text, []):
            skipped.append(f"track_id={track_id}: path outside root")
            continue
        try:
            expected = report_selection_module._candidate_identity(candidate)
        except (KeyError, TypeError, ValueError) as error:
            skipped.append(f"track_id={track_id}: invalid report identity ({error})")
            continue
        try:
            current = selected_database.get_track_file_states_by_ids(
                (track_id,),
                include_missing=True,
            )[0]
        except (IndexError, KeyError, ValueError):
            skipped.append(f"track_id={track_id}: track identity unavailable")
            continue
        if (
            current.catalog_uuid != expected.catalog_uuid
            or current.track_uuid != expected.track_uuid
            or canonical_file_path(current.file_path)
            != canonical_file_path(path_text)
        ):
            skipped.append(f"track_id={track_id}: report identity is stale")
            continue
        try:
            reported_size = int(candidate["size"])
            reported_modified_ns = int(candidate["file_modified_ns"])
        except (KeyError, TypeError, ValueError):
            skipped.append(f"track_id={track_id}: report file facts are missing")
            continue
        if (
            current.file_size_bytes != reported_size
            or current.file_modified_ns != reported_modified_ns
        ):
            skipped.append(f"track_id={track_id}: report file facts are stale")
            continue
        file_path = Path(path_text)
        if not file_path.exists():
            skipped.append(f"track_id={track_id}: file missing")
            continue
        if not file_path.is_file():
            skipped.append(f"track_id={track_id}: path is not a file")
            continue
        if not _any_path_on_disk(retained_paths.get(track_id, ()), retained_on_disk):
            skipped.append(f"track_id={track_id}: {retained_missing_reason}")
            continue
        try:
            remove_file(file_path)
            removal = selected_database.remove_deleted_track(
                expected=expected,
                file_path=path_text,
            )
            if not removal.removed:
                failed.append(
                    f"track_id={track_id}: exact database row was already absent"
                )
                continue
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            failed.append(f"track_id={track_id}: {error}")
            continue
        deleted_ids.append(track_id)
        deleted_identities.append(expected)
        deleted_paths.append(path_text)
    selected_rhythm_lab_db = config_module.DEFAULT_RHYTHM_LAB_DB if rhythm_lab_db is None else rhythm_lab_db
    try:
        rhythm_lab_deleted_rows = rhythm_lab_module.cleanup_rhythm_lab_database(
            selected_rhythm_lab_db,
            deleted_identities,
        )
    except sqlite3.Error as error:
        rhythm_lab_deleted_rows = 0
        failed.append(f"rhythm_lab_cleanup: {error}")
    return models_module.ApplyResult(
        deleted_track_ids=tuple(deleted_ids),
        deleted_paths=tuple(deleted_paths),
        skipped=tuple(skipped),
        failed=tuple(failed),
        rhythm_lab_deleted_rows=rhythm_lab_deleted_rows,
    )

def _keeper_retained_paths(payload: dict[str, object]) -> dict[int, tuple[str, ...]]:
    """Copy that must survive each safe delete: the report's suggested keeper."""
    retained: dict[int, tuple[str, ...]] = {}
    for group in report_selection_module._payload_groups(payload):
        keeper = group.get("suggested_keeper")
        keeper_path = str(keeper.get("path", "")) if isinstance(keeper, dict) else ""
        if not keeper_path:
            continue
        for candidate in report_selection_module._entry_list(group, "candidate_deletes"):
            retained[report_selection_module._candidate_track_id(candidate)] = (keeper_path,)
    return retained


def _selection_retained_paths(
    payload: dict[str, object],
    deletion_targets: Collection[int],
) -> dict[int, tuple[str, ...]]:
    """Copies that survive an explicit selection, per group.

    A reviewer may delete the suggested keeper, so the surviving set is whatever
    the selection left behind rather than one nominated file.
    """
    retained: dict[int, tuple[str, ...]] = {}
    for group in report_selection_module._payload_groups(payload):
        members = report_selection_module._group_member_entries(group)
        survivors: list[str] = []
        for entry in members:
            if report_selection_module._candidate_track_id(entry) in deletion_targets:
                continue
            path_text = str(entry.get("path", ""))
            if path_text:
                survivors.append(path_text)
        surviving_paths = tuple(survivors)
        for entry in members:
            retained[report_selection_module._candidate_track_id(entry)] = surviving_paths
    return retained


def _any_path_on_disk(paths: Iterable[str], cache: dict[str, bool]) -> bool:
    for path_text in paths:
        on_disk = cache.get(path_text)
        if on_disk is None:
            on_disk = bool(path_text) and Path(path_text).is_file()
            cache[path_text] = on_disk
        if on_disk:
            return True
    return False


def _file_remover(deletion_mode: str) -> Callable[[Path], None]:
    """Resolve how a confirmed duplicate leaves the disk.

    Trash mode never falls back to an unlink. Silently destroying a file the
    caller asked to send to the recycle bin is worse than refusing the run, so a
    missing dependency fails here instead of downgrading per file.
    """
    if deletion_mode == config_module.DELETION_MODE_PERMANENT:
        return Path.unlink
    if deletion_mode != config_module.DELETION_MODE_TRASH:
        raise ValueError(f"Unsupported deletion mode: {deletion_mode}")
    try:
        from send2trash import send2trash
    except ImportError as error:
        raise RuntimeError(
            "Recycle bin deletion needs the 'send2trash' package; "
            "install it or delete permanently"
        ) from error

    def send_file_to_trash(path: Path) -> None:
        send2trash(str(path))

    return send_file_to_trash

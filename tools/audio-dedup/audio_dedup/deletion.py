from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import stat
from typing import Callable, Collection, Iterable

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.analysis_candidates import require_sonara_timeline
from dj_track_similarity.db.tracks import canonical_file_path
from dj_track_similarity.rhythm_lab_collections import sonara_content_key
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
    path_filter: str = "",
    payload: dict[str, object],
    rhythm_lab_db: Path | None = None,
    selected_track_ids: Collection[int],
    deletion_mode: str = config_module.DELETION_MODE_PERMANENT,
) -> models_module.ApplyResult:
    """Delete the copies a reviewer selected, inside the filter they reviewed under.

    ``path_filter`` is the same fragment the review filtered by, so a copy the
    reviewer could not see on screen cannot be deleted by a request that names
    it anyway. An empty filter reviews the whole report and deletes anywhere.
    """
    selected_database = track_loading_module._resolve_database(database=database, db_path=db_path)
    # A row is removed only after its file left the disk, so a library that
    # cannot remove rows refuses the whole run before any file is touched.
    with closing(selected_database.connect()) as connection:
        require_sonara_timeline(connection)
    remove_file = _file_remover(deletion_mode)
    selected_filter = str(path_filter).strip().replace("\\", "/").lower()
    deleted_ids: list[int] = []
    deleted_paths: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    candidates = report_selection_module.selected_delete_candidates(payload, selected_track_ids)
    retained_entries = _selection_retained_entries(
        payload,
        {report_selection_module._candidate_track_id(candidate) for candidate in candidates},
    )
    retained_missing_reason = "group would lose every copy"
    deleted_identities: list[TrackIdentity] = []
    deleted_files: list[tuple[str, str]] = []
    for candidate in candidates:
        track_id = report_selection_module._candidate_track_id(candidate)
        path_text = str(candidate.get("path", ""))
        if selected_filter and not track_loading_module._path_matches(path_text, [selected_filter]):
            skipped.append(f"track_id={track_id}: path outside the review filter")
            continue
        try:
            expected = _require_current_report_file(selected_database, candidate)
        except (OSError, KeyError, TypeError, ValueError) as error:
            skipped.append(f"track_id={track_id}: {error}")
            continue
        file_path = Path(path_text)
        if not _any_current_copy(selected_database, retained_entries.get(track_id, ())):
            skipped.append(f"track_id={track_id}: {retained_missing_reason}")
            continue
        try:
            # The fingerprint goes with the library row, so the content key
            # other libraries' Rhythm Lab rows carry is read first.
            fingerprint = selected_database.get_sonara_fingerprints_by_ids((track_id,)).get(track_id)
            content_key = None if fingerprint is None else sonara_content_key(*fingerprint)
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
        if content_key is not None:
            deleted_files.append((content_key, path_text))
        deleted_paths.append(path_text)
    selected_rhythm_lab_db = config_module.DEFAULT_RHYTHM_LAB_DB if rhythm_lab_db is None else rhythm_lab_db
    try:
        rhythm_lab_deleted_rows = rhythm_lab_module.cleanup_rhythm_lab_database(
            selected_rhythm_lab_db,
            deleted_identities,
            deleted_files,
        )
    except (OSError, sqlite3.Error) as error:
        rhythm_lab_deleted_rows = 0
        failed.append(f"rhythm_lab_cleanup: {error}")
    return models_module.ApplyResult(
        deleted_track_ids=tuple(deleted_ids),
        deleted_paths=tuple(deleted_paths),
        skipped=tuple(skipped),
        failed=tuple(failed),
        rhythm_lab_deleted_rows=rhythm_lab_deleted_rows,
    )

def _require_current_report_file(
    database: LibraryDatabase,
    entry: dict[str, object],
) -> TrackIdentity:
    """Bind a report entry to both its current library row and on-disk file."""
    expected = report_selection_module._candidate_identity(entry)
    current = database.get_track_file_states_by_ids((expected.track_id,))[0]
    path_text = str(entry.get("path", ""))
    if (
        current.catalog_uuid != expected.catalog_uuid
        or current.track_uuid != expected.track_uuid
        or canonical_file_path(current.file_path) != canonical_file_path(path_text)
    ):
        raise ValueError("report identity is stale")
    reported_facts = (int(entry["size"]), int(entry["file_modified_ns"]))
    if (current.file_size_bytes, current.file_modified_ns) != reported_facts:
        raise ValueError("report file facts are stale")
    file_stat = Path(path_text).stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError("path is not a file")
    if (file_stat.st_size, file_stat.st_mtime_ns) != reported_facts:
        raise ValueError("source file changed after the report")
    return expected


def _selection_retained_entries(
    payload: dict[str, object],
    deletion_targets: Collection[int],
) -> dict[int, tuple[dict[str, object], ...]]:
    """Copies that survive an explicit selection, per group.

    A reviewer may delete the suggested keeper, so the surviving set is whatever
    the selection left behind rather than one nominated file.
    """
    retained: dict[int, tuple[dict[str, object], ...]] = {}
    for group in report_selection_module._payload_groups(payload):
        members = report_selection_module._group_member_entries(group)
        survivors: list[dict[str, object]] = []
        for entry in members:
            if report_selection_module._candidate_track_id(entry) in deletion_targets:
                continue
            survivors.append(entry)
        surviving_entries = tuple(survivors)
        for entry in members:
            retained[report_selection_module._candidate_track_id(entry)] = surviving_entries
    return retained


def _any_current_copy(
    database: LibraryDatabase,
    entries: Iterable[dict[str, object]],
) -> bool:
    for entry in entries:
        try:
            _require_current_report_file(database, entry)
        except (OSError, KeyError, TypeError, ValueError):
            continue
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

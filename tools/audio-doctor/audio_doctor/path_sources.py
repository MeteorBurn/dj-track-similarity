from __future__ import annotations

from collections.abc import Iterable
import os
import re
from pathlib import Path, PureWindowsPath

from . import config as config_module
from . import models as models_module


def collect_paths(
    logs: list[Path],
    paths: list[Path],
    *,
    folders: list[Path] | None = None,
    db_paths: list[Path] | None = None,
    since: str | None,
    until: str | None,
) -> list[Path]:
    collected: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        add_path(collected, seen, path)
    for folder in folders or []:
        for path in paths_from_folder(folder):
            add_path(collected, seen, path)
    for path in db_paths or []:
        add_path(collected, seen, path)
    for log_path in logs:
        for path in paths_from_log(log_path, since=since, until=until):
            add_path(collected, seen, path)
    return collected


def collect_db_paths(dbs: list[Path], *, db_roots: list[Path], file_root: Path | None) -> tuple[list[Path], int]:
    paths: list[Path] = []
    missing = 0
    for db_path in dbs:
        database_paths, database_missing = collect_repository_paths(
            _track_path_records_from_db(db_path),
            db_roots=db_roots,
            file_root=file_root,
        )
        paths.extend(database_paths)
        missing += database_missing
    return paths, missing


def collect_repository_paths(
    track_paths: Iterable[models_module.TrackPathRecord],
    *,
    db_roots: list[Path],
    file_root: Path | None,
) -> tuple[list[Path], int]:
    """Resolve typed repository paths and count files absent on disk."""

    existing: list[Path] = []
    missing = 0
    for path in paths_from_track_records(
        track_paths,
        db_roots=db_roots,
        file_root=file_root,
    ):
        if path.exists():
            existing.append(path)
        else:
            missing += 1
    return existing, missing


def paths_from_track_records(
    track_paths: Iterable[models_module.TrackPathRecord],
    *,
    db_roots: list[Path],
    file_root: Path | None,
) -> list[Path]:
    """Map canonical ``TrackPath.file_path`` values to local audio paths."""

    result: list[Path] = []
    for track_path in track_paths:
        path_text = track_path.file_path
        resolved_path = remap_db_track_path(
            path_text,
            db_roots=db_roots,
            file_root=file_root,
        )
        if (
            resolved_path is not None
            and resolved_path.suffix.lower() in config_module.AUDIO_EXTENSIONS
        ):
            result.append(resolved_path)
    return result


def _track_path_records_from_db(db_path: Path) -> list[models_module.TrackPathRecord]:
    if not db_path.exists():
        raise models_module.RepairError(f"Database does not exist: {db_path}")
    try:
        from dj_track_similarity.database import LibraryDatabase

        database = LibraryDatabase(db_path)
        return database.list_track_paths(include_missing=True)
    except Exception as error:
        raise models_module.RepairError(f"Could not read database tracks: {db_path}: {error}") from error


def remap_db_track_path(path_text: str, *, db_roots: list[Path], file_root: Path | None) -> Path | None:
    if not db_roots:
        return Path(path_text)
    track_path = PureWindowsPath(path_text)
    for db_root in db_roots:
        root_path = PureWindowsPath(str(db_root))
        try:
            relative_path = track_path.relative_to(root_path)
        except ValueError:
            continue
        if file_root is not None:
            return file_root.joinpath(*relative_path.parts)
        return Path(path_text)
    return None


def paths_from_folder(folder: Path) -> list[Path]:
    if not folder.exists():
        raise models_module.RepairError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise models_module.RepairError(f"Not a folder: {folder}")
    return sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in config_module.AUDIO_EXTENSIONS),
        key=lambda path: os.path.normcase(str(path)),
    )


def add_path(collected: list[Path], seen: set[str], path: Path) -> None:
    key = os.path.normcase(str(path))
    if key not in seen:
        seen.add(key)
        collected.append(path)


def paths_from_log(log_path: Path, *, since: str | None = None, until: str | None = None) -> list[Path]:
    if not log_path.exists():
        raise models_module.RepairError(f"Log file does not exist: {log_path}")
    paths: list[Path] = []
    pattern = re.compile(r"path=(.*?) error=" + re.escape(config_module.READBACK_FAILURE))
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line_in_time_range(line, since=since, until=until):
                continue
            if "Genre tag apply failed" not in line or config_module.READBACK_FAILURE not in line:
                continue
            match = pattern.search(line)
            if match:
                paths.append(Path(match.group(1)))
    return paths


def line_in_time_range(line: str, *, since: str | None, until: str | None) -> bool:
    if since is None and until is None:
        return True
    timestamp = line[:16]
    if since is not None and timestamp < since[:16]:
        return False
    if until is not None and timestamp >= until[:16]:
        return False
    return True

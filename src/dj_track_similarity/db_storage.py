"""Filesystem topology for the library and optional Evaluation sidecar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageDatabasePaths:
    """Optional sidecars belonging to one library catalog."""

    evaluation: Path


def storage_database_paths(library_path: str | Path) -> StorageDatabasePaths:
    """Return canonical optional sidecar paths for *library_path*.

    ``library.sqlite`` maps to ``library.evaluation.sqlite``. Evaluation is
    path metadata only; resolving this path never creates the optional file.
    """

    resolved = Path(library_path).expanduser().resolve(strict=False)
    stem = resolved.stem if resolved.suffix else resolved.name
    return StorageDatabasePaths(
        evaluation=resolved.with_name(f"{stem}.evaluation.sqlite"),
    )

"""Filesystem topology for the current SQLite storage set."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageDatabasePaths:
    """Required and optional databases belonging to one Core catalog."""

    artifacts: Path
    evaluation: Path


def storage_database_paths(core_path: str | Path) -> StorageDatabasePaths:
    """Return canonical sidecar paths for *core_path*.

    ``library.sqlite`` maps to ``library.artifacts.sqlite`` and
    ``library.evaluation.sqlite``.  Evaluation is path metadata only; resolving
    this path never creates the optional database.
    """

    resolved = Path(core_path).expanduser().resolve(strict=False)
    stem = resolved.stem if resolved.suffix else resolved.name
    return StorageDatabasePaths(
        artifacts=resolved.with_name(f"{stem}.artifacts.sqlite"),
        evaluation=resolved.with_name(f"{stem}.evaluation.sqlite"),
    )


def migration_recovery_path(core_path: str | Path) -> Path:
    """Return the durable marker used by explicit pair migration recovery."""

    resolved = Path(core_path).expanduser().resolve(strict=False)
    return resolved.with_name(f".{resolved.name}.migration-recovery.json")

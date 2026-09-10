"""Filesystem topology for the library and optional Evaluation sidecar."""

from __future__ import annotations

from pathlib import Path


def evaluation_database_path(library_path: str | Path) -> Path:
    """Return the canonical Evaluation sidecar path for *library_path*.

    ``library.sqlite`` maps to ``library.evaluation.sqlite``. Evaluation is
    path metadata only; resolving this path never creates the optional file.
    """

    resolved = Path(library_path).expanduser().resolve(strict=False)
    stem = resolved.stem if resolved.suffix else resolved.name
    return resolved.with_name(f"{stem}.evaluation.sqlite")

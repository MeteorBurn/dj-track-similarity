"""Staging directory ownership shared by the SONARA and ML staged pipelines.

Both pipelines copy candidates into a per-job directory, stamp it with the
owner PID, and sweep directories left behind by processes that are gone. Only
the directory prefix differs, so the ownership rules live here once.

What each pipeline does *inside* its directory stays with it: SONARA hands
paths to a process pool, ML decodes and runs inference in this process, and
they copy differently on purpose.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path


LOGGER = logging.getLogger(__name__)

DEFERRED_STAGING_CLEANUP_WINERRORS = frozenset({32, 64})


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_orphaned_staging(root: Path, *, prefix: str) -> None:
    """Remove only ``prefix`` directories whose recorded owner process is gone.

    A directory without a readable ``.owner`` marker is removed only when it is
    already empty, so files nobody claimed are left alone.
    """

    if not root.exists():
        return
    for path in root.glob(f"{prefix}*"):
        if not path.is_dir():
            continue
        try:
            owner = int((path / ".owner").read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            try:
                path.rmdir()
            except OSError:
                pass
            continue
        if process_exists(owner):
            continue
        LOGGER.info(
            "Removing orphaned staging directory: %s (owner PID %d)", path, owner
        )
        shutil.rmtree(path, ignore_errors=True)

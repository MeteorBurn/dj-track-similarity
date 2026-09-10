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
import sys
from pathlib import Path


LOGGER = logging.getLogger(__name__)

DEFERRED_STAGING_CLEANUP_WINERRORS = frozenset({32, 64})

_WINDOWS = sys.platform == "win32"

if _WINDOWS:  # pragma: no cover - exercised on the platform that needs it
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE = 0x00100000
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x00001000
    _WAIT_OBJECT_0 = 0x00000000
    _ERROR_ACCESS_DENIED = 5

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL


def process_exists(pid: int) -> bool:
    """Report whether *pid* still names a running process.

    ``os.kill(pid, 0)`` is the POSIX answer and the wrong one on Windows: it
    succeeds for a process that has already exited while its record is still
    around, so a dead staging owner reads as alive and its directory is never
    swept. Out of range it raises ``OSError`` instead of answering.

    On Windows the process handle answers directly. A handle that is signalled
    belongs to a process that has exited; a handle that times out belongs to one
    still running. That reading, unlike an exit code, cannot be confused with a
    process whose own exit code happens to be ``STILL_ACTIVE``.
    """

    if pid <= 0 or pid > 0xFFFFFFFF:
        return False
    if _WINDOWS:  # pragma: no cover - exercised on the platform that needs it
        handle = _kernel32.OpenProcess(
            _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            return _kernel32.WaitForSingleObject(handle, 0) != _WAIT_OBJECT_0
        finally:
            _kernel32.CloseHandle(handle)
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

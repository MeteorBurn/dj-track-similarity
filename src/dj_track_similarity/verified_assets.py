"""Mutation-safe bindings for model assets loaded through path-only APIs."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType


class VerifiedAssetBinding:
    """A private verified copy whose files cannot be reopened for mutation.

    Windows is the primary runtime.  Each copied file is held through a
    read-only handle that permits other readers but denies writers and delete
    sharing until model deserialization completes.  Read-only permissions,
    advisory shared locks, and a final digest check provide the corresponding
    fail-closed boundary on other platforms.
    """

    def __init__(
        self,
        *,
        root: Path,
        primary_path: Path,
        expected_sha256: Mapping[str, str],
        temporary_directory: tempfile.TemporaryDirectory[str],
    ) -> None:
        self.root = root
        self.path = primary_path
        self._expected_sha256 = dict(expected_sha256)
        self._temporary_directory = temporary_directory
        self._guards: list[object] = []
        try:
            for relative_name in sorted(self._expected_sha256):
                copied_path = self.root / relative_name
                copied_path.chmod(stat.S_IREAD)
                self._guards.append(_open_read_only_guard(copied_path))
        except BaseException:
            self.close(verify=False)
            raise

    def __enter__(self) -> VerifiedAssetBinding:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.close(verify=exc_type is None)
        return False

    def close(self, *, verify: bool = True) -> None:
        verification_error: BaseException | None = None
        if verify:
            try:
                _verify_bound_files(self.root, self._expected_sha256)
            except BaseException as error:
                verification_error = error
        for guard in reversed(self._guards):
            try:
                _close_guard(guard)
            except OSError:
                pass
        self._guards.clear()
        self._temporary_directory.cleanup()
        if verification_error is not None:
            raise verification_error


def bind_verified_file(
    source: str | Path,
    *,
    expected_sha256: str,
    description: str,
) -> VerifiedAssetBinding:
    source_path = Path(source)
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="djts-verified-model-"
    )
    root = Path(temporary_directory.name)
    target = root / source_path.name
    try:
        _copy_verified(
            source_path,
            target,
            expected_sha256=expected_sha256,
            description=description,
        )
        return VerifiedAssetBinding(
            root=root,
            primary_path=target,
            expected_sha256={source_path.name: expected_sha256},
            temporary_directory=temporary_directory,
        )
    except BaseException:
        temporary_directory.cleanup()
        raise


def bind_verified_snapshot(
    source_root: str | Path,
    *,
    expected_sha256: Mapping[str, str],
    description: str,
) -> VerifiedAssetBinding:
    source_path = Path(source_root)
    temporary_directory = tempfile.TemporaryDirectory(
        prefix="djts-verified-snapshot-"
    )
    root = Path(temporary_directory.name)
    try:
        for relative_name, digest in expected_sha256.items():
            _copy_verified(
                source_path / relative_name,
                root / relative_name,
                expected_sha256=digest,
                description=f"{description}/{relative_name}",
            )
        return VerifiedAssetBinding(
            root=root,
            primary_path=root,
            expected_sha256=expected_sha256,
            temporary_directory=temporary_directory,
        )
    except BaseException:
        temporary_directory.cleanup()
        raise


def _copy_verified(
    source: Path,
    target: Path,
    *,
    expected_sha256: str,
    description: str,
) -> None:
    if not source.is_file():
        raise RuntimeError(
            f"Pinned model asset is unavailable: {description} ({source})"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as input_file, target.open("xb") as output_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
            output_file.write(chunk)
        output_file.flush()
        os.fsync(output_file.fileno())
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Pinned model asset SHA-256 mismatch for {description}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


def _verify_bound_files(
    root: Path,
    expected_sha256: Mapping[str, str],
) -> None:
    for relative_name, expected in expected_sha256.items():
        path = root / relative_name
        digest = hashlib.sha256()
        with path.open("rb") as asset:
            for chunk in iter(lambda: asset.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise RuntimeError(
                "Verified model asset changed during deserialization: "
                f"{relative_name}; expected {expected}, got {actual}"
            )


def _open_read_only_guard(path: Path) -> object:
    if os.name == "nt":
        return _open_windows_read_only_guard(path)

    file_handle = path.open("rb")
    try:
        import fcntl

        fcntl.flock(file_handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BaseException:
        file_handle.close()
        raise
    return file_handle


def _open_windows_read_only_guard(path: Path) -> object:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001,  # FILE_SHARE_READ; deliberately deny write/delete sharing
        None,
        3,  # OPEN_EXISTING
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return ("windows", kernel32, handle)


def _close_guard(guard: object) -> None:
    if isinstance(guard, tuple) and guard and guard[0] == "windows":
        _marker, kernel32, handle = guard
        if not kernel32.CloseHandle(handle):
            import ctypes

            raise ctypes.WinError(ctypes.get_last_error())
        return
    close = getattr(guard, "close", None)
    if callable(close):
        close()

from __future__ import annotations

import hashlib
from pathlib import Path

from ..verified_assets import (
    VerifiedAssetBinding,
    bind_verified_file,
    bind_verified_snapshot,
)


_MODELS_ROOT = Path(__file__).resolve().parents[3] / "models"


def _local_model_path(model_directory: str, filename: str | None = None) -> Path:
    """Resolve assets exclusively inside this checkout's model store."""

    root = _MODELS_ROOT.resolve()
    path = root / model_directory
    if filename is not None:
        path /= filename
    path = path.resolve()
    if path == root or not path.is_relative_to(root):
        raise RuntimeError(f"Model asset path is outside the local model store: {path}")
    return path


def _bind_verified_local_checkpoint(
    *,
    model_directory: str,
    repo_id: str,
    filename: str,
    revision: str,
    expected_sha256: str,
) -> VerifiedAssetBinding:
    """Bind a pinned checkpoint from models/, without consulting Hub caches."""

    path = _local_model_path(model_directory, filename)
    if not path.is_file():
        raise RuntimeError(
            f"Local model file is missing: {path} ({repo_id}@{revision}). "
            "Automatic model downloads are disabled; restore the pinned file "
            f"in models/{model_directory}/."
        )
    _verify_checkpoint_sha256(
        path,
        expected_sha256=expected_sha256,
        description=f"{repo_id}@{revision}/{filename}",
    )
    return bind_verified_file(
        path,
        expected_sha256=expected_sha256,
        description=f"{repo_id}@{revision}/{filename}",
    )

def _local_only_from_pretrained_proxy(
    loader,
    *,
    snapshot_path: Path,
    expected_source: str,
    description: str,
):
    """Return the narrow loader surface expected by pinned laion-clap."""

    load = getattr(loader, "from_pretrained", None)
    if not callable(load):
        raise RuntimeError(f"{description} loader has no from_pretrained")
    verified_path = str(snapshot_path)

    class LocalOnlyLoader:
        @staticmethod
        def from_pretrained(source, *args, **kwargs):
            if source != expected_source:
                raise RuntimeError(
                    f"{description} requested unexpected source {source!r}"
                )
            local_only = kwargs.pop("local_files_only", True)
            if local_only is not True:
                raise RuntimeError(
                    f"{description} attempted a non-local model load"
                )
            return load(
                verified_path,
                *args,
                local_files_only=True,
                **kwargs,
            )

    return LocalOnlyLoader

def _bind_verified_local_snapshot(
    *,
    model_directory: str,
    repo_id: str,
    revision: str,
    required_files: tuple[str, ...],
    expected_sha256: tuple[tuple[str, str], ...],
    checkpoint_filename: str,
    expected_checkpoint_sha256: str,
) -> VerifiedAssetBinding:
    """Bind the pinned files in models/, without remote or cache resolution."""

    snapshot_path = _local_model_path(model_directory)
    missing = [
        file_name
        for file_name in required_files
        if not _local_model_path(model_directory, file_name).is_file()
    ]
    if missing:
        raise RuntimeError(
            "Pinned model snapshot is incomplete for "
            f"{repo_id}@{revision} at {snapshot_path}; missing={missing}. "
            "Automatic model downloads are disabled."
        )
    expected_by_name = dict(expected_sha256)
    if tuple(expected_by_name) != required_files:
        raise RuntimeError(
            "Pinned model snapshot digest manifest does not match required files "
            f"for {repo_id}@{revision}"
        )
    if expected_by_name.get(checkpoint_filename) != expected_checkpoint_sha256:
        raise RuntimeError(
            "Pinned model snapshot checkpoint digest does not match the "
            f"production checkpoint identity for {repo_id}@{revision}"
        )
    _verify_checkpoint_sha256(
        snapshot_path / checkpoint_filename,
        expected_sha256=expected_checkpoint_sha256,
        description=f"{repo_id}@{revision}/{checkpoint_filename}",
    )
    return bind_verified_snapshot(
        snapshot_path,
        expected_sha256=expected_by_name,
        description=f"{repo_id}@{revision}",
    )

def _verify_checkpoint_sha256(
    path: str | Path,
    *,
    expected_sha256: str,
    description: str,
) -> None:
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise RuntimeError(
            f"Local checkpoint is unavailable: {description} ({checkpoint_path}). "
            "Automatic model downloads are disabled."
        )
    digest = hashlib.sha256()
    with checkpoint_path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Pinned checkpoint SHA-256 mismatch for {description}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

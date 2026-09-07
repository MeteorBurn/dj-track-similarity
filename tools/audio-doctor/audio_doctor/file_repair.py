from __future__ import annotations

from collections.abc import Callable
import hashlib
import os
import shutil
from pathlib import Path

from . import config as config_module
from . import container_repair as container_repair_module
from . import inspection as inspection_module
from . import models as models_module


def repair_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> models_module.FileRepairResult:
    suffix = path.suffix.lower()
    if suffix in {".wav", ".wave"}:
        return repair_wave_file(
            path,
            apply_changes=apply_changes,
            backup_dir=backup_dir,
            no_backup=no_backup,
            keep_id3=keep_id3,
        )
    if suffix in {".aif", ".aiff"}:
        return repair_aiff_file(path, apply_changes=apply_changes, backup_dir=backup_dir, no_backup=no_backup)
    inspection = inspection_module.inspect_file(path)
    return models_module.FileRepairResult(path=path, status=inspection.status, message=inspection.message, mutagen_summary=inspection.tag_summary)


def repair_wave_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> models_module.FileRepairResult:
    backup_path = None
    repair_actions: list[str] = []
    apply_actions: list[str] = []
    try:
        data = path.read_bytes()
        original_payload_hash = container_repair_module.data_payload_hash(data)
        repaired = container_repair_module.repair_wave_bytes(data, keep_id3=keep_id3)
        repair_actions = list(repaired.actions)
        repaired_payload_hash = container_repair_module.data_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            expected_payload_hash = container_repair_module.aligned_pcm_data_payload_hash(data)
            if (
                not any(action.startswith("trimmed incomplete PCM data") for action in repair_actions)
                or expected_payload_hash != repaired_payload_hash
            ):
                raise models_module.RepairError("audio data payload would change; refusing to write")
        if is_cosmetic_only_wave_repair(repaired):
            inspection = inspection_module.inspect_file(path)
            if inspection.status != "ok":
                return models_module.FileRepairResult(
                    path=path,
                    status=inspection.status,
                    message=inspection.message,
                    actions=repair_actions,
                    original_size=repaired.original_size,
                    repaired_size=repaired.repaired_size,
                    id3_seen=repaired.id3_seen,
                    id3_removed=repaired.id3_removed,
                    mutagen_summary=inspection.tag_summary,
                )
            return models_module.FileRepairResult(
                path=path,
                status="notice",
                message="cosmetic trailing zero padding",
                actions=["dropped trailing zero padding bytes"],
                original_size=len(data),
                repaired_size=len(data),
                id3_seen=repaired.id3_seen,
                id3_removed=repaired.id3_removed,
                mutagen_summary=repaired.mutagen_summary,
            )

        status = "ok"
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                record_backup_created(apply_actions, backup_path)
                post_write_inspection = apply_repaired_file(
                    path,
                    repaired.data,
                    backup_path=backup_path,
                    structural_verify=verify_repaired_file,
                    actions=apply_actions,
                )
                if post_write_inspection.tag_summary:
                    repaired.mutagen_summary = post_write_inspection.tag_summary
                status = "repaired"

        if status == "ok":
            inspection = inspection_module.inspect_file(path)
            return models_module.FileRepairResult(
                path=path,
                status=inspection.status,
                message=inspection.message,
                actions=repair_actions + apply_actions,
                backup_path=backup_path,
                original_size=repaired.original_size,
                repaired_size=repaired.repaired_size,
                id3_seen=repaired.id3_seen,
                id3_removed=repaired.id3_removed,
                mutagen_summary=inspection.tag_summary,
            )

        return models_module.FileRepairResult(
            path=path,
            status=status,
            message="ok",
            actions=repair_actions + apply_actions,
            backup_path=backup_path,
            original_size=repaired.original_size,
            repaired_size=repaired.repaired_size,
            id3_seen=repaired.id3_seen,
            id3_removed=repaired.id3_removed,
            mutagen_summary=repaired.mutagen_summary,
        )
    except Exception as error:
        return models_module.FileRepairResult(
            path=path,
            status="failed",
            message=str(error),
            actions=repair_actions + apply_actions,
            backup_path=backup_path,
        )


def is_cosmetic_only_wave_repair(repaired: models_module.ByteRepairResult) -> bool:
    if not repaired.changed:
        return False
    if repaired.id3_removed:
        return False
    if not repaired.actions:
        return False
    if any(not action.startswith("dropped trailing zero padding bytes") for action in repaired.actions):
        return False
    return bool(repaired.mutagen_summary and repaired.mutagen_summary.startswith("mutagen ok"))


def repair_aiff_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
) -> models_module.FileRepairResult:
    backup_path = None
    repair_actions: list[str] = []
    apply_actions: list[str] = []
    try:
        data = path.read_bytes()
        if not container_repair_module.has_empty_aiff_id3_chunks(data):
            inspection = inspection_module.inspect_file(path)
            status = inspection.status
            return models_module.FileRepairResult(
                path=path,
                status=status,
                message=inspection.message,
                original_size=len(data),
                repaired_size=len(data),
                mutagen_summary=inspection.tag_summary,
            )
        original_payload_hash = container_repair_module.aiff_sound_payload_hash(data)
        repaired = container_repair_module.repair_aiff_bytes(data)
        repair_actions = list(repaired.actions)
        repaired_payload_hash = container_repair_module.aiff_sound_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            raise models_module.RepairError("audio sound payload would change; refusing to write")

        status = "ok"
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                record_backup_created(apply_actions, backup_path)
                post_write_inspection = apply_repaired_file(
                    path,
                    repaired.data,
                    backup_path=backup_path,
                    structural_verify=verify_repaired_aiff_file,
                    actions=apply_actions,
                )
                if post_write_inspection.tag_summary:
                    repaired.mutagen_summary = post_write_inspection.tag_summary
                status = "repaired"

        return models_module.FileRepairResult(
            path=path,
            status=status,
            message="ok",
            actions=repair_actions + apply_actions,
            backup_path=backup_path,
            original_size=repaired.original_size,
            repaired_size=repaired.repaired_size,
            id3_seen=repaired.id3_seen,
            id3_removed=repaired.id3_removed,
            mutagen_summary=repaired.mutagen_summary,
        )
    except Exception as error:
        if apply_changes:
            return models_module.FileRepairResult(
                path=path,
                status="failed",
                message=str(error),
                actions=repair_actions + apply_actions,
                backup_path=backup_path,
            )
        inspection = inspection_module.inspect_file(path)
        if inspection.status in {"tag-error", "suspicious"}:
            return models_module.FileRepairResult(path=path, status=inspection.status, message=inspection.message)
        return models_module.FileRepairResult(path=path, status="failed", message=str(error))


def verify_repaired_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise models_module.RepairError("repaired file is not RIFF/WAVE")
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise models_module.RepairError("repaired RIFF size does not match file size")
    container_repair_module.data_payload_hash(data)
    container_repair_module.validate_pcm_data_block_alignment(data)
    summary = container_repair_module.mutagen_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise models_module.RepairError(summary)


def verify_repaired_aiff_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise models_module.RepairError("repaired file is not AIFF/AIFC")
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        raise models_module.RepairError("repaired FORM size does not match file size")
    container_repair_module.aiff_sound_payload_hash(data)
    summary = container_repair_module.mutagen_aiff_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise models_module.RepairError(summary)


def apply_repaired_file(
    path: Path,
    data: bytes,
    *,
    backup_path: Path | None,
    structural_verify: Callable[[Path], None],
    actions: list[str],
) -> models_module.FileInspectionResult:
    try:
        write_repaired_file(path, data)
        actions.append("repaired bytes written")
        structural_verify(path)
        actions.append("container verification passed")
        inspection = verify_post_write_inspection(path)
        actions.append("post-write inspection passed")
    except Exception:
        restore_backup(path, backup_path, actions=actions)
        delete_backup(backup_path, actions=actions)
        raise
    delete_backup(backup_path, actions=actions)
    return inspection


def verify_post_write_inspection(path: Path) -> models_module.FileInspectionResult:
    inspection = inspection_module.inspect_file(path)
    if inspection.status != "ok":
        raise models_module.RepairError(f"post-write verification failed: {inspection.status}: {inspection.message}")
    if not inspection.tag_summary or not inspection.tag_summary.startswith("mutagen ok"):
        detail = inspection.tag_summary or "missing Mutagen tag readback"
        raise models_module.RepairError(f"post-write tag verification failed: {detail}")
    return inspection


def record_backup_created(actions: list[str], backup_path: Path | None) -> None:
    if backup_path is None:
        actions.append("backup skipped")
    else:
        actions.append(f"backup created: {backup_path}")


def restore_backup(path: Path, backup_path: Path | None, *, actions: list[str]) -> None:
    if backup_path is None:
        actions.append("backup restore skipped: no backup")
        return
    try:
        shutil.copy2(backup_path, path)
    except Exception as error:
        actions.append(f"backup restore failed: {backup_path}: {error}")
        raise
    actions.append(f"backup restored: {backup_path}")


def delete_backup(backup_path: Path | None, *, actions: list[str]) -> None:
    if backup_path is None:
        return
    try:
        backup_path.unlink()
    except Exception as error:
        actions.append(f"backup delete failed: {backup_path}: {error}")
        raise
    actions.append(f"backup deleted: {backup_path}")


def create_backup(path: Path, *, backup_dir: Path | None, no_backup: bool) -> Path | None:
    if no_backup:
        return None
    target_dir = backup_dir or config_module.DEFAULT_BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(path).encode("utf-8", errors="replace")).hexdigest()[:12]
    backup_path = unique_path(target_dir / f"{path.stem}.{digest}{path.suffix}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.name}.{index}")
        if not candidate.exists():
            return candidate
    raise models_module.RepairError(f"Could not allocate unique backup path near {path}")


def write_repaired_file(path: Path, data: bytes) -> None:
    temp_path = path.with_name(f"{path.name}.repair-{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

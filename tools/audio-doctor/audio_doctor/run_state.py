from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from . import config as config_module
from . import models as models_module
from . import result_formatting as result_formatting_module


def resolve_state_path(state_path: Path | None, sources: list[str | Path]) -> Path:
    if state_path is not None:
        return state_path
    normalized_sources = normalize_state_sources(sources)
    signature = source_signature(normalized_sources)
    digest = hashlib.sha1(signature.encode("utf-8", errors="replace")).hexdigest()[:12]
    return config_module.DEFAULT_RUN_DIR / f"state.{source_state_label(normalized_sources)}.{digest}.json"


def normalize_state_sources(sources: list[str | Path]) -> list[str]:
    normalized: list[str] = []
    for source in sources:
        if isinstance(source, Path):
            normalized.append(f"folder:{source.resolve()}")
        else:
            normalized.append(source)
    return normalized


def state_sources(folders: list[Path], dbs: list[Path]) -> list[str]:
    sources = [f"folder:{folder.resolve()}" for folder in folders]
    sources.extend(f"db:{db.resolve()}" for db in dbs)
    return sources


def source_signature(sources: list[str]) -> str:
    return "\n".join(sorted(os.path.normcase(source) for source in sources))


def source_state_label(sources: list[str]) -> str:
    if len(sources) == 1:
        source_type, _, source_value = sources[0].partition(":")
        name = Path(source_value).resolve().name or Path(source_value).resolve().anchor.rstrip(":\\")
        if source_type == "folder":
            return safe_filename_part(name)
        return safe_filename_part(f"{source_type}-{name}")
    digest = hashlib.sha1(source_signature(sources).encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"multiple_{digest}"


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "folder"


def load_state(state_path: Path, sources: list[str]) -> dict[str, object]:
    if not state_path.exists():
        return new_state(sources)
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return new_state(sources)
    if not isinstance(raw, dict):
        return new_state(sources)
    files = raw.get("files")
    if not isinstance(files, dict):
        raw["files"] = {}
    raw.setdefault("version", 2)
    raw["sources"] = sources
    raw["folders"] = [source.removeprefix("folder:") for source in sources if source.startswith("folder:")]
    return raw


def new_state(sources: list[str]) -> dict[str, object]:
    return {
        "version": 2,
        "sources": sources,
        "folders": [source.removeprefix("folder:") for source in sources if source.startswith("folder:")],
        "updated_at": None,
        "files": {},
    }


def state_key(path: Path) -> str:
    return hashlib.sha1(state_key_source(path).encode("utf-8", errors="replace")).hexdigest()


def state_key_source(path: Path) -> str:
    resolved = path.resolve()
    return os.path.normcase(str(resolved.parent / resolved.name))


def state_entry_for_path(state: dict[str, object], path: Path) -> dict[str, object] | None:
    files = state.get("files")
    if not isinstance(files, dict):
        return None
    entry = files.get(state_key(path))
    if isinstance(entry, dict):
        return entry
    return None


def state_entry_text(entry: dict[str, object], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) else None


def state_entry_int(entry: dict[str, object], key: str) -> int | None:
    value = entry.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def state_entry_status(entry: dict[str, object]) -> str | None:
    status = state_entry_text(entry, "status")
    if status is None:
        return None
    return status.upper()


def state_entry_reason(entry: dict[str, object]) -> str | None:
    reason = state_entry_text(entry, "reason")
    if not reason:
        return None
    return result_formatting_module.normalize_reason_filter(reason)


def state_entry_current(state: dict[str, object], path: Path, *, apply_changes: bool) -> bool:
    entry = state_entry_for_path(state, path)
    if entry is None:
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if entry.get("size") != stat.st_size or state_modified_at(entry) != int(stat.st_mtime):
        return False
    status = state_entry_status(entry)
    if status is None:
        return False
    if apply_changes:
        if entry.get("mode") == "apply":
            return status not in {"FAILED", "REPAIRABLE"}
        return status != "REPAIRABLE"
    return True


def state_entry_reason_matches(state: dict[str, object], path: Path, reasons: set[str]) -> bool:
    entry = state_entry_for_path(state, path)
    if entry is None:
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if entry.get("size") != stat.st_size or state_modified_at(entry) != int(stat.st_mtime):
        return False
    reason = state_entry_reason(entry)
    return reason is not None and reason in reasons


def state_modified_at(entry: dict[str, object]) -> int | None:
    value = entry.get("modified_at")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def update_state_entry(state: dict[str, object], path: Path, result: models_module.FileRepairResult, *, apply_changes: bool) -> None:
    files = state.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        state["files"] = files
    stat = path.stat()
    files[state_key(path)] = {
        "title": path.name,
        "path": str(path),
        "size": stat.st_size,
        "checked_at": int(time.time()),
        "modified_at": int(stat.st_mtime),
        "mode": "apply" if apply_changes else "dry-run",
        "message": result_message(result),
        "status": result.status.upper(),
        "reason": result_formatting_module.result_reason(result),
    }
    state["updated_at"] = int(time.time())


def result_message(result: models_module.FileRepairResult) -> str:
    if result.status == "ok" and result.message == "ok":
        return "checked"
    if result.status == "repairable" and result.message == "ok":
        return "repair_available"
    if result.status == "repaired" and result.message == "ok":
        return "repair_applied"
    return result.message


def save_state(state_path: Path, state: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, state_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

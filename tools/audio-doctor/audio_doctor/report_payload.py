from __future__ import annotations

import re
from pathlib import Path

from . import config as config_module
from . import models as models_module
from . import result_formatting as result_formatting_module
from . import run_state as run_state_module


def build_report_payload(
    run_result: models_module.RepairRunResult,
    *,
    generated_at: str,
    sources: list[str],
    folders: list[Path],
    dbs: list[Path],
    logs: list[Path],
    explicit_paths: list[Path],
    reason_filters: list[str],
) -> dict[str, object]:
    processed_results = [
        file_result_payload(result, apply_changes=run_result.apply_changes) for result in run_result.results
    ]
    state_results = [state_result_payload(result) for result in run_result.skipped_state_results]
    results = processed_results + state_results
    status_counts = summarize_report_status_counts(results)
    reason_counts = summarize_report_reason_counts(results)
    return {
        "mode": "apply" if run_result.apply_changes else "dry-run",
        "generated_at": generated_at,
        "source_counts": {
            "paths": len(explicit_paths),
            "folders": len(folders),
            "databases": len(dbs),
            "logs": len(logs),
        },
        "sources": {
            "paths": [str(path) for path in explicit_paths],
            "folders": [str(path) for path in folders],
            "databases": [str(path) for path in dbs],
            "logs": [str(path) for path in logs],
            "state_sources": sources,
        },
        "options": {
            "keep_id3": run_result.keep_id3,
            "workers": run_result.workers,
            "backup_dir": str(run_result.backup_dir) if run_result.backup_dir is not None else str(config_module.DEFAULT_BACKUP_DIR),
            "no_backup": run_result.no_backup,
            "reason_filters": reason_filters,
        },
        "state": {
            "enabled": run_result.state_mode,
            "path": str(run_result.state_path) if run_result.state_path is not None else None,
            "skipped_from_state": run_result.skipped_from_state,
            "skipped_by_reason": run_result.skipped_by_reason,
            "included_in_report": len(state_results),
        },
        "total_collected": run_result.total_collected,
        "processed_count": len(run_result.results),
        "state_result_count": len(state_results),
        "result_count": len(results),
        "missing_db_files": run_result.missing_db_files,
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "problem_summary": [{"problem": problem, "count": count} for problem, count in summarize_report_problem_types(results)],
        "results": results,
    }


def file_result_payload(result: models_module.FileRepairResult, *, apply_changes: bool) -> dict[str, object]:
    reason = result_formatting_module.result_reason(result)
    payload: dict[str, object] = {
        "source": "processed",
        "action": repair_report_action(result),
        "path": str(result.path),
        "status": result.status,
        "status_label": result.status.upper(),
        "reason": reason,
        "message": run_state_module.result_message(result),
        "detail": result.message,
        "mode": "apply" if apply_changes else "dry-run",
        "original_size": result.original_size,
        "repaired_size": result.repaired_size,
        "size_delta": result.repaired_size - result.original_size if result.original_size or result.repaired_size else 0,
        "id3_seen": result.id3_seen,
        "id3_removed": result.id3_removed,
        "backup_path": str(result.backup_path) if result.backup_path is not None else None,
        "mutagen_summary": result.mutagen_summary,
        "primary_action": result_formatting_module.primary_action(result.actions) if result.actions else None,
        "actions": list(result.actions),
        "checked_at": None,
        "modified_at": None,
    }
    return payload


def state_result_payload(result: models_module.StateRepairResult) -> dict[str, object]:
    entry = result.entry
    status_label = run_state_module.state_entry_status(entry) or "UNKNOWN"
    status = status_label.lower()
    reason = run_state_module.state_entry_reason(entry)
    size = run_state_module.state_entry_int(entry, "size") or 0
    message = run_state_module.state_entry_text(entry, "message") or ""
    mode = run_state_module.state_entry_text(entry, "mode") or ""
    return {
        "source": "state",
        "action": state_report_action(status),
        "path": str(result.path),
        "status": status,
        "status_label": status_label,
        "reason": reason,
        "message": message,
        "detail": message,
        "mode": mode,
        "original_size": size,
        "repaired_size": size,
        "size_delta": 0,
        "id3_seen": 0,
        "id3_removed": 0,
        "backup_path": None,
        "mutagen_summary": None,
        "primary_action": None,
        "actions": [],
        "checked_at": run_state_module.state_entry_int(entry, "checked_at"),
        "modified_at": run_state_module.state_entry_int(entry, "modified_at"),
    }


def repair_report_action(result: models_module.FileRepairResult) -> str:
    if result.status == "repairable":
        return "REPAIR AVAILABLE"
    if result.status == "repaired":
        return "REPAIRED"
    if result.status == "ok":
        return "NO ACTION"
    if result.status == "notice":
        return "NOTICE"
    if result.status == "failed":
        return "FAILED"
    if result.status == "unsupported":
        return "INSPECT ONLY"
    return "REVIEW MANUALLY"


def state_report_action(status: str) -> str:
    if status == "repaired":
        return "ALREADY REPAIRED"
    if status == "ok":
        return "OK"
    if status == "repairable":
        return "REPAIR AVAILABLE"
    if status == "notice":
        return "NOTICE"
    if status == "failed":
        return "FAILED"
    if status == "unsupported":
        return "INSPECT ONLY"
    return "REVIEW MANUALLY"


def summarize_report_status_counts(results: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = result.get("status")
        if not isinstance(status, str) or not status:
            continue
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def summarize_report_reason_counts(results: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        reason = result.get("reason")
        if isinstance(reason, str) and reason:
            counts[reason] = counts.get(reason, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def summarize_report_problem_types(results: list[dict[str, object]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        problem = report_result_problem_summary(result)
        if problem is None:
            continue
        counts[problem] = counts.get(problem, 0) + 1
    return sorted(counts.items())


def report_result_problem_summary(result: dict[str, object]) -> str | None:
    status = result.get("status")
    reason = result.get("reason")
    if not isinstance(status, str) or not isinstance(reason, str) or not reason:
        return None
    message = result.get("detail") or result.get("message") or ""
    if not isinstance(message, str):
        message = str(message)
    if status in {"repairable", "repaired"}:
        path_value = result.get("path")
        path = Path(path_value) if isinstance(path_value, str) else Path("")
        summary_result = models_module.FileRepairResult(path=path, status=status, message=message)
        return f"repairable[{reason}]: {result_formatting_module.repairable_reason_description(reason, summary_result)}"
    if status == "notice":
        return f"notice[{reason}]: {message}"
    if status == "suspicious":
        extension_match = re.search(r"extension=(\.[^\s]+) detected=([^\s]+)", message)
        if extension_match:
            return (
                f"suspicious[{reason}]: extension mismatch: {extension_match.group(1)} "
                f"detected as {extension_match.group(2)}"
            )
        codec_match = re.search(r"extension=(\.[^\s]+) detected_codec=([^\s]+)", message)
        if codec_match:
            return (
                f"suspicious[{reason}]: codec mismatch: {codec_match.group(1)} "
                f"codec {codec_match.group(2)}"
            )
        return f"suspicious[{reason}]: {message}"
    return f"{status}[{reason}]: {message}"

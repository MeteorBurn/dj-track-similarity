from __future__ import annotations

import re
from pathlib import Path

from . import models as models_module

STATUS_COLORS = {
    "ok": "32",
    "notice": "34",
    "repairable": "33",
    "repaired": "32",
    "suspicious": "35",
    "tag-error": "31",
    "broken": "31",
    "failed": "31",
    "unsupported": "90",
}


class RunReporter:
    def __init__(self, log_path: Path | None) -> None:
        self._handle = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = log_path.open("w", encoding="utf-8", errors="replace")

    def line(self, text: str, *, log_text: str | None = None) -> None:
        print(text)
        if self._handle is not None:
            self._handle.write((log_text if log_text is not None else text) + "\n")
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def format_result(
    result: models_module.FileRepairResult,
    *,
    dry_run: bool,
    index: int | None = None,
    total: int | None = None,
    color: bool = False,
) -> str:
    counter = f"[{index}/{total}]" if index is not None and total is not None else "[?/?]"
    status = format_status(result.status, color=color)
    fields = [f"{counter} {status}", f"mode={'dry-run' if dry_run else 'apply'}", f"file={result.path}"]
    if result.original_size or result.repaired_size:
        fields.append(f"size={result.original_size}->{result.repaired_size}")
    if result.id3_seen or result.id3_removed:
        fields.append(f"id3={result.id3_seen}/{result.id3_removed}")
    if result.backup_path is not None:
        fields.append(f"backup={result.backup_path}")
    if result.status in {"failed", "suspicious", "tag-error", "broken", "unsupported", "notice"}:
        fields.append(f"problem={result.message}")
    if result.actions:
        if dry_run:
            fields.append(f"action={primary_action(result.actions)}")
        else:
            fields.append(f"actions={'; '.join(result.actions)}")
    return " | ".join(fields)


def primary_action(actions: list[str]) -> str:
    for action in actions:
        if action.startswith("shrunk oversized data chunk"):
            return action
        if action.startswith("removed empty ID3 chunk"):
            return action
        if action.startswith("removed ID3 chunk"):
            return action
    return actions[0]


def format_status(status: str, *, color: bool) -> str:
    label = status.upper()
    if not color:
        return label
    code = STATUS_COLORS.get(status)
    if code is None:
        return label
    return f"\x1b[{code}m{label}\x1b[0m"


def summarize_problem_types(results: list[models_module.FileRepairResult]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        problem = result_problem_summary(result)
        if problem is None:
            continue
        counts[problem] = counts.get(problem, 0) + 1
    return sorted(counts.items())


def result_reason(result: models_module.FileRepairResult) -> str | None:
    if result.status == "ok":
        return None
    if result.status in {"repairable", "repaired"}:
        return uppercase_reason(repairable_reason(result))
    if result.status == "notice":
        return "NOTICE"
    if result.status == "suspicious":
        extension_match = re.search(r"extension=(\.[^\s]+) detected=([^\s]+)", result.message)
        if extension_match:
            return "EXTENSION_MISMATCH"
        codec_match = re.search(r"extension=(\.[^\s]+) detected_codec=([^\s]+)", result.message)
        if codec_match:
            return "CODEC_MISMATCH"
        return "SUSPICIOUS"
    if result.status == "tag-error":
        return "TAG_ERROR"
    if result.status == "failed":
        return "FAILED"
    if result.status == "broken":
        return "BROKEN"
    if result.status == "unsupported":
        return "UNSUPPORTED"
    return result.status.replace("-", "_").upper()


def uppercase_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    return reason.upper()


def normalize_reason_filter(reason: str) -> str:
    return reason.strip().upper()


def repairable_reason(result: models_module.FileRepairResult) -> str | None:
    if result.status not in {"repairable", "repaired"}:
        return None
    joined_actions = " | ".join(result.actions)
    suffix = result.path.suffix.lower()
    if suffix in {".wav", ".wave"} and "trimmed incomplete PCM data tail" in joined_actions:
        return "incomplete_pcm_tail"
    if suffix in {".wav", ".wave"} and "shrunk oversized data chunk" in joined_actions:
        return "oversized_data"
    if suffix in {".wav", ".wave"} and "removed duplicate/unselected ID3 chunks" in joined_actions:
        return "duplicate_id3"
    if suffix in {".aif", ".aiff", ".aifc"} and "removed empty ID3 chunk" in joined_actions:
        return "empty_id3"
    if suffix in {".wav", ".wave"}:
        return "container_normalization"
    if suffix in {".aif", ".aiff", ".aifc"}:
        return "container_normalization"
    return "repairable"


def result_problem_summary(result: models_module.FileRepairResult) -> str | None:
    reason = result_reason(result)
    if reason is None:
        return None
    if result.status in {"repairable", "repaired"}:
        return f"repairable[{reason}]: {repairable_reason_description(reason, result)}"
    if result.status == "notice":
        return f"notice[{reason}]: {result.message}"
    if result.status == "suspicious":
        extension_match = re.search(r"extension=(\.[^\s]+) detected=([^\s]+)", result.message)
        if extension_match:
            return (
                f"suspicious[{reason}]: extension mismatch: {extension_match.group(1)} "
                f"detected as {extension_match.group(2)}"
            )
        codec_match = re.search(r"extension=(\.[^\s]+) detected_codec=([^\s]+)", result.message)
        if codec_match:
            return (
                f"suspicious[{reason}]: codec mismatch: {codec_match.group(1)} "
                f"codec {codec_match.group(2)}"
            )
        return f"suspicious[{reason}]: {result.message}"
    return f"{result.status}[{reason}]: {result.message}"


def repairable_reason_description(reason: str, result: models_module.FileRepairResult) -> str:
    reason = reason.lower()
    suffix = result.path.suffix.lower()
    if reason == "incomplete_pcm_tail":
        return "WAV incomplete PCM frame at the end of the data chunk"
    if reason == "oversized_data":
        return "WAV oversized data chunk before ID3 chunk"
    if reason == "duplicate_id3":
        return "WAV duplicate/unselected ID3 chunks"
    if reason == "empty_id3":
        return "AIFF empty ID3 chunks"
    if reason == "container_normalization" and suffix in {".wav", ".wave"}:
        return "WAV container/tag chunk normalization"
    if reason == "container_normalization" and suffix in {".aif", ".aiff", ".aifc"}:
        return "AIFF container/tag chunk normalization"
    return result.message


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

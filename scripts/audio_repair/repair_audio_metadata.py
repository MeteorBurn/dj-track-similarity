from __future__ import annotations

import argparse
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
from html import escape
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PureWindowsPath


READBACK_FAILURE = "Genre tag was not readable after WAV save:"
ID3_CHUNK_IDS = {b"id3 ", b"ID3 "}
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = SCRIPT_DIR / "reports"
DEFAULT_RUN_DIR = SCRIPT_DIR / "state"
DEFAULT_BACKUP_DIR = SCRIPT_DIR / "backups"
AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".alac",
    ".aac",
    ".aifc",
    ".ape",
    ".dff",
    ".dsf",
    ".flac",
    ".mka",
    ".m4a",
    ".oga",
    ".ogg",
    ".opus",
    ".mp3",
    ".mp4",
    ".tta",
    ".wav",
    ".wave",
    ".wma",
    ".wv",
}
EXPECTED_FORMAT_BY_EXTENSION = {
    ".aif": {"aiff"},
    ".aiff": {"aiff"},
    ".aifc": {"aiff"},
    ".aac": {"aac"},
    ".alac": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".ape": {"ape"},
    ".dff": {"dsf"},
    ".dsf": {"dsf"},
    ".flac": {"flac"},
    ".mka": {"matroska,webm", "matroska"},
    ".m4a": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".mp3": {"mp3"},
    ".mp4": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".oga": {"ogg"},
    ".ogg": {"ogg"},
    ".opus": {"ogg"},
    ".tta": {"tta"},
    ".wav": {"wav"},
    ".wave": {"wav"},
    ".wma": {"asf"},
    ".wv": {"wv"},
}
EXPECTED_CODECS_BY_EXTENSION = {
    ".aac": {"aac"},
    ".aif": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aiff": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aifc": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".ape": {"ape"},
    ".dff": {"dsd_lsbf", "dsd_msbf"},
    ".dsf": {"dsd_lsbf", "dsd_msbf"},
    ".flac": {"flac"},
    ".m4a": {"aac", "alac"},
    ".mp3": {"mp3"},
    ".mp4": {"aac", "alac", "mp3"},
    ".oga": {"vorbis", "opus", "flac"},
    ".ogg": {"vorbis", "opus"},
    ".opus": {"opus"},
    ".tta": {"tta"},
    ".wav": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wave": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wma": {"wmav1", "wmav2", "wmapro", "wmall", "wmalossless"},
    ".wv": {"wavpack"},
}
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
EXCEL_CELL_TEXT_LIMIT = 32767
MUTAGEN_KEY_TEXT_LIMIT = 160


class RepairError(Exception):
    pass


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: bytes
    payload: bytes
    source_start: int
    source_end: int


@dataclass
class ByteRepairResult:
    changed: bool
    data: bytes
    actions: list[str] = field(default_factory=list)
    id3_seen: int = 0
    id3_removed: int = 0
    original_size: int = 0
    repaired_size: int = 0
    mutagen_summary: str | None = None


@dataclass
class FileRepairResult:
    path: Path
    status: str
    message: str
    actions: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    original_size: int = 0
    repaired_size: int = 0
    id3_seen: int = 0
    id3_removed: int = 0
    mutagen_summary: str | None = None


@dataclass(frozen=True)
class FileInspectionResult:
    path: Path
    status: str
    message: str
    detected_format: str | None = None
    detected_codec: str | None = None
    tag_summary: str | None = None


@dataclass(frozen=True)
class RepairRunResult:
    exit_code: int
    results: list[FileRepairResult]
    total_collected: int
    skipped_from_state: int
    skipped_by_reason: int
    missing_db_files: int
    state_path: Path | None
    state_mode: bool
    apply_changes: bool
    keep_id3: str
    backup_dir: Path | None
    no_backup: bool
    workers: int


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    xlsx_path: Path
    log_path: Path
    payload: dict[str, object]


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


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    if args.file_root is not None and not args.db_roots:
        print("--file-root requires at least one --db-root.", file=sys.stderr)
        return 2
    db_paths, missing_db_files = collect_db_paths(args.dbs, db_roots=args.db_roots, file_root=args.file_root)
    all_paths = collect_paths(
        args.logs,
        args.paths,
        folders=args.folders,
        db_paths=db_paths,
        since=args.since,
        until=args.until,
    )
    if not all_paths:
        print("No audio paths found. Pass paths, --folder, --db, or --log with readback failures.", file=sys.stderr)
        return 2

    keep_id3 = args.keep_id3
    apply_changes = args.apply
    if apply_changes and args.backup_dir and args.no_backup:
        print("--backup-dir and --no-backup cannot be used together.", file=sys.stderr)
        return 2
    use_color = should_use_color(args.color)
    state_mode = bool(args.folders or args.dbs)
    sources = state_sources(args.folders, args.dbs)
    state: dict[str, object] | None = None
    state_path: Path | None = None
    skipped_from_state = 0
    skipped_by_reason = 0
    paths = list(all_paths)
    if args.reasons and not state_mode:
        print("--reason can only be used with --folder or --db state.", file=sys.stderr)
        return 2
    reason_filters = {normalize_reason_filter(reason) for reason in args.reasons}
    if state_mode:
        state_path = resolve_state_path(args.state, sources)
        state = load_state(state_path, sources)
        pending_paths: list[Path] = []
        for path in all_paths:
            if reason_filters and not state_entry_reason_matches(state, path, reason_filters):
                skipped_by_reason += 1
                continue
            if state_entry_current(state, path, apply_changes=apply_changes):
                skipped_from_state += 1
            else:
                pending_paths.append(path)
        paths = pending_paths
    if args.limit is not None:
        paths = paths[: args.limit]

    reporter = RunReporter(None if args.no_file_log or args.file_log is None else Path(args.file_log))
    try:
        run_result = run_paths(
            paths,
            all_paths=all_paths,
            skipped_from_state=skipped_from_state,
            reporter=reporter,
            use_color=use_color,
            apply_changes=apply_changes,
            backup_dir=args.backup_dir,
            no_backup=args.no_backup,
            keep_id3=keep_id3,
            state=state,
            state_path=state_path,
            state_mode=state_mode,
            summary_only=args.summary_only,
            workers=args.workers,
            skipped_by_reason=skipped_by_reason,
            missing_db_files=missing_db_files,
        )
        if not args.no_report:
            report = write_report_bundle(
                out_dir=args.out_dir,
                run_result=run_result,
                sources=sources,
                folders=args.folders,
                dbs=args.dbs,
                logs=args.logs,
                explicit_paths=args.paths,
                reason_filters=sorted(reason_filters),
            )
            reporter.line(f"json={report.json_path}")
            reporter.line(f"xlsx={report.xlsx_path}")
            reporter.line(f"log={report.log_path}")
        return run_result.exit_code
    finally:
        reporter.close()


def run_paths(
    paths: list[Path],
    *,
    all_paths: list[Path],
    skipped_from_state: int,
    reporter: RunReporter,
    use_color: bool,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    state: dict[str, object] | None,
    state_path: Path | None,
    state_mode: bool,
    summary_only: bool,
    workers: int,
    skipped_by_reason: int,
    missing_db_files: int,
) -> RepairRunResult:
    if state_mode:
        reporter.line(f"Total tracks: {len(all_paths)}")
        if missing_db_files:
            reporter.line(f"Missing DB files: {missing_db_files}")
        if state_path is not None:
            reporter.line(f"State file: {state_path}")
        reporter.line(f"Already checked from state: {skipped_from_state}")
        if skipped_by_reason:
            reporter.line(f"Skipped by reason filter: {skipped_by_reason}")
        reporter.line(f"Pending tracks: {len(paths)}")
    else:
        reporter.line(f"Total tracks: {len(paths)}")

    results: list[FileRepairResult] = []
    total = len(paths)
    indexed_results = process_paths(
        paths,
        apply_changes=apply_changes,
        backup_dir=backup_dir,
        no_backup=no_backup,
        keep_id3=keep_id3,
        workers=workers,
    )
    for index, path, result in indexed_results:
        results.append(result)
        if state is not None and state_path is not None:
            update_state_entry(state, path, result, apply_changes=apply_changes)
            save_state(state_path, state)
        if not summary_only:
            reporter.line(
                format_result(result, dry_run=not apply_changes, index=index, total=total, color=use_color),
                log_text=format_result(result, dry_run=not apply_changes, index=index, total=total, color=False),
            )

    failed = sum(1 for result in results if result.status == "failed")
    changed = sum(1 for result in results if result.status == "repaired")
    repairable = sum(1 for result in results if result.status == "repairable")
    notice = sum(1 for result in results if result.status == "notice")
    suspicious = sum(1 for result in results if result.status == "suspicious")
    tag_error = sum(1 for result in results if result.status == "tag-error")
    ok = sum(1 for result in results if result.status == "ok")
    problem_counts = summarize_problem_types(results)
    summary = (
        "Summary: "
        f"total={len(results)} repaired={changed} repairable={repairable} "
        f"notice={notice} ok={ok} suspicious={suspicious} "
        f"tag-error={tag_error} failed={failed}"
    )
    if state_mode:
        summary += f" skipped-state={skipped_from_state}"
        if skipped_by_reason:
            summary += f" skipped-reason={skipped_by_reason}"
    reporter.line(summary)
    if problem_counts:
        reporter.line("Problem summary:")
        for problem, count in problem_counts:
            reporter.line(f"{problem}: {count}")
    return RepairRunResult(
        exit_code=1 if failed else 0,
        results=results,
        total_collected=len(all_paths),
        skipped_from_state=skipped_from_state,
        skipped_by_reason=skipped_by_reason,
        missing_db_files=missing_db_files,
        state_path=state_path,
        state_mode=state_mode,
        apply_changes=apply_changes,
        keep_id3=keep_id3,
        backup_dir=backup_dir,
        no_backup=no_backup,
        workers=workers,
    )


def process_paths(
    paths: list[Path],
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    workers: int,
) -> Iterator[tuple[int, Path, FileRepairResult]]:
    worker_count = max(1, workers)
    if apply_changes or worker_count == 1 or len(paths) <= 1:
        for index, path in enumerate(paths, start=1):
            yield (
                index,
                path,
                repair_file(
                    path,
                    apply_changes=apply_changes,
                    backup_dir=backup_dir,
                    no_backup=no_backup,
                    keep_id3=keep_id3,
                ),
            )
        return

    def check_one(item: tuple[int, Path]) -> tuple[int, Path, FileRepairResult]:
        index, path = item
        return (
            index,
            path,
            repair_file(
                path,
                apply_changes=False,
                backup_dir=backup_dir,
                no_backup=no_backup,
                keep_id3=keep_id3,
            ),
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        yield from executor.map(check_one, enumerate(paths, start=1))


def write_report_bundle(
    *,
    out_dir: Path,
    run_result: RepairRunResult,
    sources: list[str],
    folders: list[Path],
    dbs: list[Path],
    logs: list[Path],
    explicit_paths: list[Path],
    reason_filters: list[str],
) -> ReportResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    generated_at = now.isoformat(timespec="seconds")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    json_path = _unique_report_path(out_dir / f"audio_repair_report_{stamp}.json")
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    payload = build_report_payload(
        run_result,
        generated_at=generated_at,
        sources=sources,
        folders=folders,
        dbs=dbs,
        logs=logs,
        explicit_paths=explicit_paths,
        reason_filters=reason_filters,
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_xlsx_report(xlsx_path, payload)
    write_text_log(log_path, payload)
    return ReportResult(json_path=json_path, xlsx_path=xlsx_path, log_path=log_path, payload=payload)


def build_report_payload(
    run_result: RepairRunResult,
    *,
    generated_at: str,
    sources: list[str],
    folders: list[Path],
    dbs: list[Path],
    logs: list[Path],
    explicit_paths: list[Path],
    reason_filters: list[str],
) -> dict[str, object]:
    results = [file_result_payload(result, apply_changes=run_result.apply_changes) for result in run_result.results]
    status_counts = summarize_status_counts(run_result.results)
    reason_counts = summarize_reason_counts(run_result.results)
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
            "backup_dir": str(run_result.backup_dir) if run_result.backup_dir is not None else str(DEFAULT_BACKUP_DIR),
            "no_backup": run_result.no_backup,
            "reason_filters": reason_filters,
        },
        "state": {
            "enabled": run_result.state_mode,
            "path": str(run_result.state_path) if run_result.state_path is not None else None,
            "skipped_from_state": run_result.skipped_from_state,
            "skipped_by_reason": run_result.skipped_by_reason,
        },
        "total_collected": run_result.total_collected,
        "processed_count": len(run_result.results),
        "result_count": len(run_result.results),
        "missing_db_files": run_result.missing_db_files,
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "problem_summary": [
            {"problem": problem, "count": count}
            for problem, count in summarize_problem_types(run_result.results)
        ],
        "results": results,
    }


def file_result_payload(result: FileRepairResult, *, apply_changes: bool) -> dict[str, object]:
    reason = result_reason(result)
    payload: dict[str, object] = {
        "action": repair_report_action(result),
        "path": str(result.path),
        "status": result.status,
        "status_label": result.status.upper(),
        "reason": reason,
        "message": result_message(result),
        "detail": result.message,
        "mode": "apply" if apply_changes else "dry-run",
        "original_size": result.original_size,
        "repaired_size": result.repaired_size,
        "size_delta": result.repaired_size - result.original_size if result.original_size or result.repaired_size else 0,
        "id3_seen": result.id3_seen,
        "id3_removed": result.id3_removed,
        "backup_path": str(result.backup_path) if result.backup_path is not None else None,
        "mutagen_summary": result.mutagen_summary,
        "primary_action": primary_action(result.actions) if result.actions else None,
        "actions": list(result.actions),
    }
    return payload


def repair_report_action(result: FileRepairResult) -> str:
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


def summarize_status_counts(results: list[FileRepairResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def summarize_reason_counts(results: list[FileRepairResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        reason = result_reason(result)
        if reason is None:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def write_xlsx_report(path: Path, payload: dict[str, object]) -> None:
    sheets = [
        ("Summary", _summary_sheet_rows(payload)),
        ("Results", _results_sheet_rows(payload)),
        ("Problems", _problems_sheet_rows(payload)),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _xlsx_writestr(archive, "[Content_Types].xml", _xlsx_content_types(len(sheets)))
        _xlsx_writestr(archive, "_rels/.rels", _xlsx_root_rels())
        _xlsx_writestr(archive, "docProps/app.xml", _xlsx_app_props())
        _xlsx_writestr(archive, "docProps/core.xml", _xlsx_core_props(str(payload["generated_at"])))
        _xlsx_writestr(archive, "xl/workbook.xml", _xlsx_workbook_xml([name for name, _ in sheets]))
        _xlsx_writestr(archive, "xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(sheets)))
        _xlsx_writestr(archive, "xl/styles.xml", _xlsx_styles_xml())
        for index, (name, rows) in enumerate(sheets, start=1):
            _xlsx_writestr(archive, f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(name, rows))


def _xlsx_writestr(archive: zipfile.ZipFile, filename: str, content: str) -> None:
    info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content)


def _summary_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    state = payload.get("state", {})
    options = payload.get("options", {})
    source_counts = payload.get("source_counts", {})
    status_counts = payload.get("status_counts", {})
    reason_counts = payload.get("reason_counts", {})
    assert isinstance(state, dict)
    assert isinstance(options, dict)
    assert isinstance(source_counts, dict)
    assert isinstance(status_counts, dict)
    assert isinstance(reason_counts, dict)
    rows: list[list[object]] = [
        ["Audio repair summary"],
        ["Generated at", payload["generated_at"]],
        ["Mode", payload["mode"]],
        ["Total collected", payload["total_collected"]],
        ["Processed results", payload["result_count"]],
        ["Missing DB files", payload["missing_db_files"]],
        ["State enabled", state.get("enabled", False)],
        ["State file", state.get("path") or ""],
        ["Skipped from state", state.get("skipped_from_state", 0)],
        ["Skipped by reason", state.get("skipped_by_reason", 0)],
        ["Keep ID3 policy", options.get("keep_id3", "")],
        ["Workers", options.get("workers", "")],
        ["Backup directory", options.get("backup_dir", "")],
        ["No backup", options.get("no_backup", False)],
        [],
        ["Input source", "Count"],
    ]
    for label, key in (("Paths", "paths"), ("Folders", "folders"), ("Databases", "databases"), ("Logs", "logs")):
        rows.append([label, source_counts.get(key, 0)])
    rows.extend([[], ["Status", "Count"]])
    for status, count in status_counts.items():
        rows.append([status, count])
    rows.extend([[], ["Reason", "Count"]])
    for reason, count in reason_counts.items():
        rows.append([reason, count])
    return rows


def _results_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "action",
            "status",
            "reason",
            "path",
            "message",
            "detail",
            "original_size",
            "repaired_size",
            "size_delta",
            "id3_seen",
            "id3_removed",
            "primary_action",
            "backup_path",
            "mutagen_summary",
        ]
    ]
    for result in payload["results"]:  # type: ignore[index]
        assert isinstance(result, dict)
        rows.append(
            [
                result.get("action", ""),
                result.get("status_label", ""),
                result.get("reason", ""),
                result.get("path", ""),
                result.get("message", ""),
                result.get("detail", ""),
                result.get("original_size", 0),
                result.get("repaired_size", 0),
                result.get("size_delta", 0),
                result.get("id3_seen", 0),
                result.get("id3_removed", 0),
                result.get("primary_action", ""),
                result.get("backup_path", ""),
                result.get("mutagen_summary", ""),
            ]
        )
    return rows


def _problems_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [["problem", "count"]]
    for problem in payload.get("problem_summary", []):
        if not isinstance(problem, dict):
            continue
        rows.append([problem.get("problem", ""), problem.get("count", 0)])
    return rows


def _xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''


def _xlsx_root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _xlsx_app_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>dj-track-similarity</Application>
</Properties>'''


def _xlsx_core_props(generated_at: str) -> str:
    timestamp = generated_at if generated_at.endswith("Z") else f"{generated_at}Z"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Audio repair report</dc:title>
<dc:creator>dj-track-similarity</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">{escape(timestamp)}</dcterms:created>
</cp:coreProperties>'''


def _xlsx_workbook_xml(sheet_names: list[str]) -> str:
    sheets = "\n".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheets}
</sheets>
</workbook>'''


def _xlsx_workbook_rels(sheet_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{"".join(rels)}
</Relationships>'''


def _xlsx_styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="11"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1B5E20"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFB71C1C"/><name val="Calibri"/></font>
</fonts>
<fills count="6">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEBEE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F2FD"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD1D5DB"/></left><right style="thin"><color rgb="FFD1D5DB"/></right><top style="thin"><color rgb="FFD1D5DB"/></top><bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_sheet_xml(name: str, rows: list[list[object]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    col_widths = _xlsx_column_widths(rows, max_cols)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(col_widths, start=1)
    )
    sheet_views = ""
    if len(rows) > 1:
        sheet_views = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    rows_xml = "\n".join(_xlsx_row_xml(row, row_index, name) for row_index, row in enumerate(rows, start=1))
    dimension = f"A1:{_xlsx_col_name(max_cols)}{max(1, len(rows))}"
    auto_filter = f'<autoFilter ref="A1:{_xlsx_col_name(max_cols)}1"/>' if len(rows) > 1 else ""
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
{sheet_views}
<cols>{cols_xml}</cols>
<sheetData>
{rows_xml}
</sheetData>
{auto_filter}
</worksheet>'''


def _xlsx_row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    height = ' ht="26" customHeight="1"' if row_index == 1 else ""
    cells = "".join(_xlsx_cell_xml(value, row_index, col_index, _xlsx_style_id(value, row_index, sheet_name)) for col_index, value in enumerate(row, start=1))
    return f'<row r="{row_index}"{height}>{cells}</row>'


def _xlsx_cell_xml(value: object, row_index: int, col_index: int, style_id: int) -> str:
    ref = f"{_xlsx_col_name(col_index)}{row_index}"
    style = f' s="{style_id}"'
    if value is None:
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(xml_safe_text(str(value), limit=EXCEL_CELL_TEXT_LIMIT))
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>'


def xml_safe_text(text: str, *, limit: int | None = None) -> str:
    safe = "".join(char if is_xml_character(char) else escaped_codepoint(char) for char in text)
    if limit is None or len(safe) <= limit:
        return safe
    suffix = f" ... [truncated; original {len(safe)} chars]"
    if len(suffix) >= limit:
        return suffix[:limit]
    return safe[: limit - len(suffix)] + suffix


def is_xml_character(char: str) -> bool:
    codepoint = ord(char)
    if codepoint in {0x9, 0xA, 0xD}:
        return True
    if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
        return False
    return (
        0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def escaped_codepoint(char: str) -> str:
    codepoint = ord(char)
    if codepoint <= 0xFF:
        return f"\\x{codepoint:02x}"
    if codepoint <= 0xFFFF:
        return f"\\u{codepoint:04x}"
    return f"\\U{codepoint:08x}"


def _xlsx_style_id(value: object, row_index: int, sheet_name: str) -> int:
    if row_index == 1 and sheet_name == "Summary":
        return 2
    if row_index == 1:
        return 1
    if value in {"NO ACTION", "REPAIRED"}:
        return 3
    if value in {"REVIEW MANUALLY", "FAILED"}:
        return 4
    return 5


def _xlsx_column_widths(rows: list[list[object]], max_cols: int) -> list[int]:
    widths: list[int] = []
    for col_index in range(max_cols):
        max_len = 10
        for row in rows:
            if col_index >= len(row):
                continue
            value = row[col_index]
            text = "" if value is None else str(value)
            max_len = max(max_len, min(80, len(text)))
        widths.append(max(12, min(72, max_len + 3)))
    return widths


def _xlsx_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def write_text_log(path: Path, payload: dict[str, object]) -> None:
    status_counts = payload.get("status_counts", {})
    reason_counts = payload.get("reason_counts", {})
    state = payload.get("state", {})
    assert isinstance(status_counts, dict)
    assert isinstance(reason_counts, dict)
    assert isinstance(state, dict)
    lines = [
        f"audio_repair {payload['mode']} run",
        f"generated_at={payload['generated_at']}",
        f"total_collected={payload['total_collected']}",
        f"processed_count={payload['processed_count']}",
        f"missing_db_files={payload['missing_db_files']}",
        f"state_enabled={state.get('enabled', False)}",
        f"state_file={state.get('path') or ''}",
        f"skipped_from_state={state.get('skipped_from_state', 0)}",
        f"skipped_by_reason={state.get('skipped_by_reason', 0)}",
    ]
    lines.extend(f"status_count_{status}={count}" for status, count in status_counts.items())
    lines.extend(f"reason_count_{reason}={count}" for reason, count in reason_counts.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unique_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique report path for {path}")


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect audio metadata/container issues and repair known safe Mutagen ID3 chunk failures. "
            "Dry-run is read-only and does not copy or write audio files."
        )
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Audio files to inspect or repair.")
    parser.add_argument(
        "--folder",
        dest="folders",
        action="append",
        type=Path,
        default=[],
        help="Folder to scan recursively for supported audio extensions.",
    )
    parser.add_argument(
        "--log",
        dest="logs",
        action="append",
        type=Path,
        default=[],
        help="Project log file. Only post-save readback-failed WAV paths are extracted.",
    )
    parser.add_argument(
        "--db",
        dest="dbs",
        action="append",
        type=Path,
        default=[],
        help="SQLite library database to read tracks.path values from.",
    )
    parser.add_argument(
        "--db-root",
        dest="db_roots",
        action="append",
        type=Path,
        default=[],
        help="Only use database paths under this root. Also acts as the source root for --file-root remapping.",
    )
    parser.add_argument(
        "--file-root",
        type=Path,
        help="Filesystem root that replaces each matching --db-root before checking files.",
    )
    parser.add_argument(
        "--since",
        help="Only use log lines at or after this timestamp, for example: 2026-05-21 20:26.",
    )
    parser.add_argument(
        "--until",
        help="Only use log lines before this timestamp, for example: 2026-05-21 20:36.",
    )
    parser.add_argument("--apply", action="store_true", help="Write repaired files. Default is dry-run.")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directory for full-file backups used only with --apply. Default: scripts/audio_repair/backups.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Apply without making full-file backups. Use only after a separate backup exists.",
    )
    parser.add_argument(
        "--keep-id3",
        choices=("first", "last", "none"),
        default="first",
        help="For WAV repair, which readable top-level ID3 chunk to keep after repair. Default: first.",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N collected paths.")
    parser.add_argument("--summary-only", action="store_true", help="Print only the final summary.")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize status labels. Default: auto.",
    )
    parser.add_argument(
        "--file-log",
        type=Path,
        help="Optional console transcript log path overwritten on every run. The structured run log is written with the report bundle.",
    )
    parser.add_argument("--no-file-log", action="store_true", help="Do not write the optional console transcript log.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for JSON, XLSX, and structured log reports. Default: scripts/audio_repair/reports.",
    )
    parser.add_argument("--no-report", action="store_true", help="Do not write the JSON/XLSX/log report bundle.")
    parser.add_argument(
        "--state",
        type=Path,
        help=(
            "Folder/DB-mode state file. Default is derived from the resolved --folder/--db source(s) "
            "and stored in scripts/audio_repair/state."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel dry-run workers. --apply always runs sequentially.",
    )
    parser.add_argument(
        "--reason",
        dest="reasons",
        action="append",
        default=[],
        help=(
            "Folder/DB-mode state reason to process. Use after a dry-run with --apply to repair only "
            "one stored reason. Can be repeated. Match the exact reason from the state file."
        ),
    )
    return parser.parse_args(argv)


def collect_paths(
    logs: list[Path],
    paths: list[Path],
    *,
    folders: list[Path] | None = None,
    db_paths: list[Path] | None = None,
    since: str | None,
    until: str | None,
) -> list[Path]:
    collected: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        add_path(collected, seen, path)
    for folder in folders or []:
        for path in paths_from_folder(folder):
            add_path(collected, seen, path)
    for path in db_paths or []:
        add_path(collected, seen, path)
    for log_path in logs:
        for path in paths_from_log(log_path, since=since, until=until):
            add_path(collected, seen, path)
    return collected


def collect_db_paths(dbs: list[Path], *, db_roots: list[Path], file_root: Path | None) -> tuple[list[Path], int]:
    paths: list[Path] = []
    missing = 0
    for db_path in dbs:
        for db_track_path in paths_from_db(db_path, db_roots=db_roots, file_root=file_root):
            if db_track_path.exists():
                paths.append(db_track_path)
            else:
                missing += 1
    return paths, missing


def paths_from_db(db_path: Path, *, db_roots: list[Path], file_root: Path | None) -> list[Path]:
    if not db_path.exists():
        raise RepairError(f"Database does not exist: {db_path}")
    rows: list[str] = []
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            rows = [row[0] for row in connection.execute("SELECT path FROM tracks ORDER BY path") if isinstance(row[0], str)]
    except sqlite3.Error as error:
        raise RepairError(f"Could not read database tracks: {db_path}: {error}") from error

    result: list[Path] = []
    for path_text in rows:
        resolved_path = remap_db_track_path(path_text, db_roots=db_roots, file_root=file_root)
        if resolved_path is not None and resolved_path.suffix.lower() in AUDIO_EXTENSIONS:
            result.append(resolved_path)
    return result


def remap_db_track_path(path_text: str, *, db_roots: list[Path], file_root: Path | None) -> Path | None:
    if not db_roots:
        return Path(path_text)
    track_path = PureWindowsPath(path_text)
    for db_root in db_roots:
        root_path = PureWindowsPath(str(db_root))
        try:
            relative_path = track_path.relative_to(root_path)
        except ValueError:
            continue
        if file_root is not None:
            return file_root.joinpath(*relative_path.parts)
        return Path(path_text)
    return None


def resolve_state_path(state_path: Path | None, sources: list[str | Path]) -> Path:
    if state_path is not None:
        return state_path
    normalized_sources = normalize_state_sources(sources)
    signature = source_signature(normalized_sources)
    digest = hashlib.sha1(signature.encode("utf-8", errors="replace")).hexdigest()[:12]
    return DEFAULT_RUN_DIR / f"state.{source_state_label(normalized_sources)}.{digest}.json"


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


def folder_signature(folders: list[Path]) -> str:
    return source_signature(state_sources(folders, []))


def folder_state_label(folders: list[Path]) -> str:
    return source_state_label(state_sources(folders, []))


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
    if apply_changes:
        return entry.get("mode") == "apply"
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
    reason = entry.get("reason")
    return isinstance(reason, str) and normalize_reason_filter(reason) in reasons


def state_modified_at(entry: dict[str, object]) -> int | None:
    value = entry.get("modified_at")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def update_state_entry(state: dict[str, object], path: Path, result: FileRepairResult, *, apply_changes: bool) -> None:
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
        "reason": result_reason(result),
    }
    state["updated_at"] = int(time.time())


def result_message(result: FileRepairResult) -> str:
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


def paths_from_folder(folder: Path) -> list[Path]:
    if not folder.exists():
        raise RepairError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise RepairError(f"Not a folder: {folder}")
    return sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda path: os.path.normcase(str(path)),
    )


def add_path(collected: list[Path], seen: set[str], path: Path) -> None:
    key = os.path.normcase(str(path))
    if key not in seen:
        seen.add(key)
        collected.append(path)


def paths_from_log(log_path: Path, *, since: str | None = None, until: str | None = None) -> list[Path]:
    if not log_path.exists():
        raise RepairError(f"Log file does not exist: {log_path}")
    paths: list[Path] = []
    pattern = re.compile(r"path=(.*?) error=" + re.escape(READBACK_FAILURE))
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line_in_time_range(line, since=since, until=until):
                continue
            if "Genre tag apply failed" not in line or READBACK_FAILURE not in line:
                continue
            match = pattern.search(line)
            if match:
                paths.append(Path(match.group(1)))
    return paths


def line_in_time_range(line: str, *, since: str | None, until: str | None) -> bool:
    if since is None and until is None:
        return True
    timestamp = line[:16]
    if since is not None and timestamp < since[:16]:
        return False
    if until is not None and timestamp >= until[:16]:
        return False
    return True


def inspect_file(path: Path) -> FileInspectionResult:
    if not path.exists():
        return FileInspectionResult(path=path, status="failed", message="file does not exist")
    suffix = path.suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        return FileInspectionResult(path=path, status="unsupported", message=f"unsupported extension={suffix}")

    detected_format = detect_format_from_header(path)
    probe_format, probe_codec = probe_file(path)
    display_format = probe_format or detected_format
    expected_formats = EXPECTED_FORMAT_BY_EXTENSION.get(suffix)
    if detected_format and expected_formats and detected_format not in expected_formats:
        return FileInspectionResult(
            path=path,
            status="suspicious",
            message=f"extension={suffix} detected={detected_format}",
            detected_format=detected_format,
            detected_codec=probe_codec,
        )
    if probe_codec:
        expected_codecs = EXPECTED_CODECS_BY_EXTENSION.get(suffix)
        if expected_codecs and probe_codec not in expected_codecs:
            return FileInspectionResult(
                path=path,
                status="suspicious",
                message=f"extension={suffix} detected_codec={probe_codec}",
                detected_format=display_format,
                detected_codec=probe_codec,
            )

    tag_summary = read_mutagen_tag_summary(path)
    if tag_summary.startswith("mutagen error:"):
        if suffix in {".aif", ".aiff"} and has_empty_aiff_id3_chunks(path.read_bytes()):
            return FileInspectionResult(
                path=path,
                status="repairable",
                message="AIFF has empty ID3 chunks that prevent Mutagen tag reads",
                detected_format=display_format,
                detected_codec=probe_codec,
                tag_summary=tag_summary,
            )
        return FileInspectionResult(
            path=path,
            status="tag-error",
            message=tag_summary,
            detected_format=display_format,
            detected_codec=probe_codec,
            tag_summary=tag_summary,
        )

    if display_format is None:
        return FileInspectionResult(path=path, status="broken", message="audio format was not detected")
    return FileInspectionResult(
        path=path,
        status="ok",
        message="ok",
        detected_format=display_format,
        detected_codec=probe_codec,
        tag_summary=tag_summary,
    )


def detect_format_from_header(path: Path) -> str | None:
    header = path.read_bytes()[:64]
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"FORM") and header[8:12] in {b"AIFF", b"AIFC"}:
        return "aiff"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"MAC "):
        return "ape"
    if header.startswith(b"wvpk"):
        return "wv"
    if header.startswith(b"TTA"):
        return "tta"
    if header.startswith(b"DSD "):
        return "dsf"
    if header.startswith(b"FRM8"):
        return "dsf"
    if header.startswith(b"0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xcel"):
        return "asf"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0:
        return "aac"
    if b"ftyp" in header[:16]:
        return "mp4"
    return None


def probe_file(path: Path) -> tuple[str | None, str | None]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None, None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-hide_banner",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "format=format_name:stream=codec_name",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception:
        return None, None
    if result.returncode != 0:
        return None, None
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not values:
        return None, None
    codec = values[0]
    fmt = values[-1] if len(values) > 1 else None
    return fmt, codec


def read_mutagen_tag_summary(path: Path) -> str:
    try:
        from mutagen import File as MutagenFile
    except Exception as error:
        return f"mutagen unavailable: {error}"
    try:
        audio = MutagenFile(path)
    except Exception as error:
        return f"mutagen error: {error}"
    if audio is None:
        return "mutagen error: unsupported audio tag format"
    tags = getattr(audio, "tags", None)
    if tags is None:
        return "mutagen ok tags=no"
    keys = sorted(str(key) for key in tags.keys())
    return f"mutagen ok tags=yes keys={','.join(keys[:8])}"


def repair_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> FileRepairResult:
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
    inspection = inspect_file(path)
    return FileRepairResult(path=path, status=inspection.status, message=inspection.message, mutagen_summary=inspection.tag_summary)


def repair_wave_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> FileRepairResult:
    try:
        data = path.read_bytes()
        original_payload_hash = data_payload_hash(data)
        repaired = repair_wave_bytes(data, keep_id3=keep_id3)
        repaired_payload_hash = data_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            raise RepairError("audio data payload would change; refusing to write")
        if is_cosmetic_only_wave_repair(repaired):
            return FileRepairResult(
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
        backup_path = None
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                write_repaired_file(path, repaired.data)
                verify_repaired_file(path)
                status = "repaired"

        return FileRepairResult(
            path=path,
            status=status,
            message="ok",
            actions=repaired.actions,
            backup_path=backup_path,
            original_size=repaired.original_size,
            repaired_size=repaired.repaired_size,
            id3_seen=repaired.id3_seen,
            id3_removed=repaired.id3_removed,
            mutagen_summary=repaired.mutagen_summary,
        )
    except Exception as error:
        return FileRepairResult(path=path, status="failed", message=str(error))


def is_cosmetic_only_wave_repair(repaired: ByteRepairResult) -> bool:
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
) -> FileRepairResult:
    try:
        data = path.read_bytes()
        if not has_empty_aiff_id3_chunks(data):
            inspection = inspect_file(path)
            status = inspection.status
            return FileRepairResult(
                path=path,
                status=status,
                message=inspection.message,
                original_size=len(data),
                repaired_size=len(data),
                mutagen_summary=inspection.tag_summary,
            )
        original_payload_hash = aiff_sound_payload_hash(data)
        repaired = repair_aiff_bytes(data)
        repaired_payload_hash = aiff_sound_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            raise RepairError("audio sound payload would change; refusing to write")

        status = "ok"
        backup_path = None
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                write_repaired_file(path, repaired.data)
                verify_repaired_aiff_file(path)
                status = "repaired"

        return FileRepairResult(
            path=path,
            status=status,
            message="ok",
            actions=repaired.actions,
            backup_path=backup_path,
            original_size=repaired.original_size,
            repaired_size=repaired.repaired_size,
            id3_seen=repaired.id3_seen,
            id3_removed=repaired.id3_removed,
            mutagen_summary=repaired.mutagen_summary,
        )
    except Exception as error:
        inspection = inspect_file(path)
        if inspection.status in {"tag-error", "suspicious"}:
            return FileRepairResult(path=path, status=inspection.status, message=inspection.message)
        return FileRepairResult(path=path, status="failed", message=str(error))


def repair_wave_bytes(data: bytes, *, keep_id3: str = "first") -> ByteRepairResult:
    if keep_id3 not in {"first", "last", "none"}:
        raise RepairError(f"Unsupported keep-id3 mode: {keep_id3}")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RepairError("not a RIFF/WAVE file")

    chunks, actions = parse_chunks_for_repair(data)
    id3_indices = [index for index, chunk in enumerate(chunks) if is_id3_chunk(chunk)]
    keep_index: int | None = None
    if keep_id3 == "first" and id3_indices:
        keep_index = id3_indices[0]
    elif keep_id3 == "last" and id3_indices:
        keep_index = id3_indices[-1]

    rebuilt = bytearray(b"RIFF\x00\x00\x00\x00WAVE")
    id3_removed = 0
    for index, chunk in enumerate(chunks):
        if is_id3_chunk(chunk):
            if keep_index is None or index != keep_index or not chunk.payload.startswith(b"ID3"):
                id3_removed += 1
                actions.append(
                    f"removed ID3 chunk at offset {chunk.source_start} size {len(chunk.payload)}"
                )
                continue

        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "little"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "little")
    repaired = bytes(rebuilt)
    changed = repaired != data
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        actions.append("normalized RIFF root size")
    if id3_removed:
        actions.append(f"removed duplicate/unselected ID3 chunks: {id3_removed}")

    return ByteRepairResult(
        changed=changed,
        data=repaired,
        actions=dedupe(actions),
        id3_seen=len(id3_indices),
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_summary(repaired),
    )


def repair_aiff_bytes(data: bytes) -> ByteRepairResult:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("not an AIFF/AIFC file")

    chunks, actions = parse_aiff_chunks(data)
    id3_seen = sum(1 for chunk in chunks if chunk.chunk_id == b"ID3 ")
    rebuilt = bytearray(data[:12])
    id3_removed = 0
    for chunk in chunks:
        if chunk.chunk_id == b"ID3 " and not chunk.payload:
            id3_removed += 1
            actions.append(f"removed empty ID3 chunk at offset {chunk.source_start}")
            continue
        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "big"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "big")
    repaired = bytes(rebuilt)
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        actions.append("normalized FORM root size")
    if id3_removed:
        actions.append(f"removed empty ID3 chunks: {id3_removed}")

    return ByteRepairResult(
        changed=repaired != data,
        data=repaired,
        actions=dedupe(actions),
        id3_seen=id3_seen,
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_aiff_summary(repaired),
    )


def parse_aiff_chunks(data: bytes) -> tuple[list[ParsedChunk], list[str]]:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("not an AIFF/AIFC file")
    chunks: list[ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            raise RepairError(f"invalid AIFF chunk ID at offset {pos}: {chunk_id!r}")
        size = int.from_bytes(data[pos + 4 : pos + 8], "big")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if padded_end > len(data):
            raise RepairError(f"truncated AIFF chunk at offset {pos}: {chunk_id!r}")
        chunks.append(
            ParsedChunk(
                chunk_id=chunk_id,
                payload=data[data_offset:unpadded_end],
                source_start=pos,
                source_end=padded_end,
            )
        )
        pos = padded_end
    if not any(chunk.chunk_id == b"SSND" for chunk in chunks):
        raise RepairError("no SSND chunk found")
    return chunks, actions


def has_empty_aiff_id3_chunks(data: bytes) -> bool:
    try:
        chunks, _ = parse_aiff_chunks(data)
    except RepairError:
        return False
    return any(chunk.chunk_id == b"ID3 " and not chunk.payload for chunk in chunks)


def parse_chunks_for_repair(data: bytes) -> tuple[list[ParsedChunk], list[str]]:
    chunks: list[ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    found_data = False

    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break

        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            if found_data:
                marker = find_next_id3_chunk(data, pos)
                if marker is not None:
                    actions.append(f"dropped invalid bytes at offset {pos} size {marker - pos}")
                    pos = marker
                    continue
                actions.append(f"dropped unparseable tail at offset {pos} size {len(data) - pos}")
                break
            raise RepairError(f"invalid chunk ID before audio data at offset {pos}: {chunk_id!r}")

        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)

        if chunk_id == b"LIST" and size < 4 and found_data:
            actions.append(f"removed invalid empty LIST chunk at offset {pos}")
            pos = unpadded_end
            continue

        if padded_end > len(data):
            if chunk_id == b"data":
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                        )
                    )
                    actions.append(
                        f"shrunk oversized data chunk at offset {pos} "
                        f"from declared size {size} to {len(payload)}"
                    )
                    found_data = True
                    pos = marker
                    continue
            if found_data:
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                        )
                    )
                    actions.append(
                        f"shrunk oversized {chunk_id.decode('ascii', 'replace').strip()} "
                        f"chunk at offset {pos} before ID3 offset {marker}"
                    )
                    if chunk_id == b"data":
                        found_data = True
                    pos = marker
                    continue
            actions.append(f"dropped truncated tail at offset {pos} size {len(data) - pos}")
            break

        source_end = padded_end
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            source_end = unpadded_end
            actions.append(
                f"inserted missing RIFF padding after odd-sized "
                f"{chunk_id.decode('ascii', 'replace').strip()} chunk at offset {pos}"
            )

        payload = data[data_offset:unpadded_end]
        chunks.append(ParsedChunk(chunk_id=chunk_id, payload=payload, source_start=pos, source_end=source_end))
        if chunk_id == b"data":
            found_data = True
        pos = source_end

    if not any(chunk.chunk_id == b"data" for chunk in chunks):
        raise RepairError("no data chunk found")
    return chunks, actions


def data_payload_hash(data: bytes) -> str:
    return hashlib.sha256(data_payload(data)).hexdigest()


def data_payload(data: bytes) -> bytes:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            break
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if chunk_id == b"data":
            if unpadded_end <= len(data):
                return data[data_offset:unpadded_end]
            marker = find_next_id3_chunk(data, data_offset)
            if marker is not None and marker > data_offset:
                return data[data_offset:marker]
            break
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            pos = unpadded_end
        else:
            pos = padded_end
    raise RepairError("no readable data chunk found")


def aiff_sound_payload_hash(data: bytes) -> str:
    return hashlib.sha256(aiff_sound_payload(data)).hexdigest()


def aiff_sound_payload(data: bytes) -> bytes:
    chunks, _ = parse_aiff_chunks(data)
    for chunk in chunks:
        if chunk.chunk_id == b"SSND":
            return chunk.payload
    raise RepairError("no readable SSND chunk found")


def is_id3_chunk(chunk: ParsedChunk) -> bool:
    return chunk.chunk_id in ID3_CHUNK_IDS


def is_valid_chunk_id(chunk_id: bytes) -> bool:
    return len(chunk_id) == 4 and all(32 <= byte <= 126 for byte in chunk_id)


def looks_like_chunk_at(data: bytes, pos: int) -> bool:
    if pos + 8 > len(data):
        return False
    chunk_id = data[pos : pos + 4]
    if not is_valid_chunk_id(chunk_id):
        return False
    size = int.from_bytes(data[pos + 4 : pos + 8], "little")
    if chunk_id in ID3_CHUNK_IDS:
        return data[pos + 8 : pos + 11] == b"ID3"
    if chunk_id == b"LIST" and size < 4:
        return True
    return pos + 8 + size + (size % 2) <= len(data) + 1


def find_next_id3_chunk(data: bytes, start: int) -> int | None:
    best: int | None = None
    for marker in ID3_CHUNK_IDS:
        pos = data.find(marker, start)
        while pos != -1:
            if pos + 11 <= len(data) and data[pos + 8 : pos + 11] == b"ID3":
                if best is None or pos < best:
                    best = pos
                break
            pos = data.find(marker, pos + 1)
    return best


def mutagen_summary(data: bytes) -> str | None:
    try:
        from mutagen.wave import WAVE
    except Exception:
        return None
    try:
        audio = WAVE(BytesIO(data))
    except Exception as error:
        return f"mutagen error: {error}"
    length = getattr(getattr(audio, "info", None), "length", None)
    if audio.tags is None:
        return f"mutagen ok length={length:.3f} tags=no" if isinstance(length, float) else "mutagen ok tags=no"
    keys = sorted(mutagen_key_label(key) for key in audio.tags.keys())
    return (
        f"mutagen ok length={length:.3f} tags=yes keys={','.join(keys[:8])}"
        if isinstance(length, float)
        else f"mutagen ok tags=yes keys={','.join(keys[:8])}"
    )


def mutagen_aiff_summary(data: bytes) -> str | None:
    try:
        from mutagen.aiff import AIFF
    except Exception:
        return None
    try:
        audio = AIFF(BytesIO(data))
    except Exception as error:
        return f"mutagen error: {error}"
    length = getattr(getattr(audio, "info", None), "length", None)
    if audio.tags is None:
        return f"mutagen ok length={length:.3f} tags=no" if isinstance(length, float) else "mutagen ok tags=no"
    keys = sorted(mutagen_key_label(key) for key in audio.tags.keys())
    return (
        f"mutagen ok length={length:.3f} tags=yes keys={','.join(keys[:8])}"
        if isinstance(length, float)
        else f"mutagen ok tags=yes keys={','.join(keys[:8])}"
    )


def mutagen_key_label(key: object) -> str:
    return xml_safe_text(str(key), limit=MUTAGEN_KEY_TEXT_LIMIT)


def verify_repaired_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RepairError("repaired file is not RIFF/WAVE")
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise RepairError("repaired RIFF size does not match file size")
    data_payload_hash(data)
    summary = mutagen_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise RepairError(summary)


def verify_repaired_aiff_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("repaired file is not AIFF/AIFC")
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        raise RepairError("repaired FORM size does not match file size")
    aiff_sound_payload_hash(data)
    summary = mutagen_aiff_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise RepairError(summary)


def create_backup(path: Path, *, backup_dir: Path | None, no_backup: bool) -> Path | None:
    if no_backup:
        return None
    target_dir = backup_dir or DEFAULT_BACKUP_DIR
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
    raise RepairError(f"Could not allocate unique backup path near {path}")


def write_repaired_file(path: Path, data: bytes) -> None:
    temp_path = path.with_name(f"{path.name}.repair-{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def format_result(
    result: FileRepairResult,
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
        fields.append(f"action={primary_action(result.actions)}")
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


def should_use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def summarize_problem_types(results: list[FileRepairResult]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        problem = result_problem_summary(result)
        if problem is None:
            continue
        counts[problem] = counts.get(problem, 0) + 1
    return sorted(counts.items())


def result_reason(result: FileRepairResult) -> str | None:
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


def repairable_reason(result: FileRepairResult) -> str | None:
    if result.status not in {"repairable", "repaired"}:
        return None
    joined_actions = " | ".join(result.actions)
    suffix = result.path.suffix.lower()
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


def result_problem_summary(result: FileRepairResult) -> str | None:
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


def repairable_reason_description(reason: str, result: FileRepairResult) -> str:
    reason = reason.lower()
    suffix = result.path.suffix.lower()
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


if __name__ == "__main__":
    raise SystemExit(main())

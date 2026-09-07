from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as config_module
from . import core as core_module
from . import models as models_module
from . import path_sources as path_sources_module
from . import report_files as report_files_module
from . import result_formatting as result_formatting_module
from . import run_state as run_state_module


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    if args.file_root is not None and not args.db_roots:
        print("--file-root requires at least one --db-root.", file=sys.stderr)
        return 2
    db_paths, missing_db_files = path_sources_module.collect_db_paths(args.dbs, db_roots=args.db_roots, file_root=args.file_root)
    all_paths = path_sources_module.collect_paths(
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
    sources = run_state_module.state_sources(args.folders, args.dbs)
    state: dict[str, object] | None = None
    state_path: Path | None = None
    skipped_from_state = 0
    skipped_by_reason = 0
    skipped_state_results: list[models_module.StateRepairResult] = []
    paths = list(all_paths)
    if args.reasons and not state_mode:
        print("--reason can only be used with --folder or --db state.", file=sys.stderr)
        return 2
    reason_filters = {result_formatting_module.normalize_reason_filter(reason) for reason in args.reasons}
    if state_mode:
        state_path = run_state_module.resolve_state_path(args.state, sources)
        state = run_state_module.load_state(state_path, sources)
        pending_paths: list[Path] = []
        for path in all_paths:
            if reason_filters and not run_state_module.state_entry_reason_matches(state, path, reason_filters):
                skipped_by_reason += 1
                continue
            if run_state_module.state_entry_current(state, path, apply_changes=apply_changes):
                skipped_from_state += 1
                entry = run_state_module.state_entry_for_path(state, path)
                if entry is not None:
                    skipped_state_results.append(models_module.StateRepairResult(path=path, entry=dict(entry)))
            else:
                pending_paths.append(path)
        paths = pending_paths
    if args.limit is not None:
        paths = paths[: args.limit]

    reporter = result_formatting_module.RunReporter(None if args.no_file_log or args.file_log is None else Path(args.file_log))
    try:
        run_result = core_module.run_paths(
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
            skipped_state_results=skipped_state_results,
        )
        if not args.no_report:
            report = report_files_module.write_report_bundle(
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
        help="SQLite library database to read tracks.file_path values from.",
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
        help="Directory for full-file backups used only with --apply. Default: tools/audio-doctor/data/backups.",
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
        default=config_module.DEFAULT_OUT_DIR,
        help="Directory for JSON, XLSX, and structured log reports. Default: tools/audio-doctor/data/reports.",
    )
    parser.add_argument("--no-report", action="store_true", help="Do not write the JSON/XLSX/log report bundle.")
    parser.add_argument(
        "--state",
        type=Path,
        help=(
            "Folder/DB-mode state file. Default is derived from the resolved --folder/--db source(s) "
            "and stored in tools/audio-doctor/data/state."
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


def should_use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
import time

from . import config as config_module
from . import core as core_module
from . import deletion as deletion_module
from . import report_files as report_files_module
from . import report_selection as report_selection_module
from . import rhythm_lab as rhythm_lab_module


class ConsoleProgressReporter:
    def __init__(self, *, refresh_seconds: float = 1.0) -> None:
        self.refresh_seconds = max(0.0, float(refresh_seconds))
        self._last_message: str | None = None
        self._last_rendered_at: float | None = None
        self._has_active_line = False

    def __call__(self, processed: int, total: int, message: str) -> None:
        now = time.monotonic()
        completed = total > 0 and processed >= total
        phase_changed = message != self._last_message
        due = (
            self._last_rendered_at is None
            or now - self._last_rendered_at >= self.refresh_seconds
        )
        if not (phase_changed or completed or due):
            return
        if total > 0:
            percent = max(0.0, min(100.0, (processed / total) * 100.0))
            rendered = f"{message}: {percent:.1f}% ({processed}/{total})"
        else:
            rendered = f"{message}..."
        sys.stdout.write(f"\r{rendered}")
        sys.stdout.flush()
        self._last_message = message
        self._last_rendered_at = now
        self._has_active_line = True

    def finish(self) -> None:
        if self._has_active_line:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._has_active_line = False


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    progress_reporter = ConsoleProgressReporter()
    try:
        result = core_module.run_report(
            db_path=args.db,
            root=args.root,
            path_contains=args.path_contains,
            preset_name=args.preset,
            min_score=args.min_score,
            min_similarity=args.min_similarity,
            limit_groups=args.limit_groups,
            out_dir=args.out_dir,
            sources=args.sources,
            weights=config_module.parse_weight_arguments(args.weights),
            mode=args.mode,
            skip_spectral=args.skip_spectral,
            progress_callback=progress_reporter,
        )
        progress_reporter.finish()
        retrieval = result.payload.get("fingerprint_retrieval", {})
        if args.mode == config_module.MODE_FINGERPRINT and not retrieval.get("valid_stored_fingerprint_count"):
            print(
                "Warning: fingerprint mode found 0 valid stored SONARA fingerprints in scope, "
                "so this empty report does not prove the scope has no duplicates. "
                "Analyze SONARA fingerprints first or rerun with --embedding."
            )
        apply_result = None
        if args.apply:
            candidates = report_selection_module.safe_delete_candidates(result.payload)
            if not candidates:
                print("Apply requested, but no safe delete candidates were found.")
            elif confirm_apply(candidates, args.db, args.root):
                apply_result = deletion_module.apply_duplicate_deletions(
                    db_path=args.db,
                    root=args.root,
                    payload=result.payload,
                )
                result.payload["mode"] = "apply"
                result.payload["apply_result"] = report_files_module.apply_result_payload(apply_result)
                report_files_module._write_report_files(result, apply_result=apply_result)
            else:
                print("Apply cancelled; reports were written but no files or database rows were deleted.")
    except (FileNotFoundError, OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        progress_reporter.finish()
        print(f"audio_dedup failed: {error}", file=sys.stderr)
        return 2
    if args.apply and apply_result is not None:
        print(
            "Apply run complete. "
            f"groups={result.groups} deleted={len(apply_result.deleted_track_ids)} "
            f"skipped={len(apply_result.skipped)} failed={len(apply_result.failed)} "
            f"rhythm_lab_deleted_rows={apply_result.rhythm_lab_deleted_rows}"
        )
    else:
        print(
            "Report-only run complete. "
            f"groups={result.groups} safe_candidates={report_selection_module._safe_candidate_count(result.payload)}"
        )
    print(rhythm_lab_module.rhythm_lab_cli_summary(result.payload))
    print(f"json={result.json_path.resolve()}")
    print(f"xlsx={result.xlsx_path.resolve()}")
    print(f"log={result.log_path.resolve()}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find likely duplicate audio tracks from an existing dj-track-similarity SQLite database. "
            "By default it is report-only; --apply prompts before deleting safe candidates."
        )
    )
    parser.add_argument("--db", type=Path, default=config_module.DEFAULT_DB, help="Project SQLite database. Default: <repo>/database/volumes.sqlite.")
    parser.add_argument("--root", type=Path, required=True, help="Only include DB tracks inside this stored path root.")
    parser.add_argument(
        "--path-contains",
        action="append",
        default=[],
        help="Additional case-insensitive substring filter on stored track paths. Can be repeated.",
    )
    parser.add_argument("--preset", choices=("safe", "balanced", "aggressive"), default="safe")
    parser.add_argument("--min-score", type=float, help="Override the preset duplicate score threshold.")
    parser.add_argument("--min-similarity", type=float, help="Override the preset content-similarity threshold.")
    parser.add_argument(
        "--source",
        dest="sources",
        action="append",
        choices=config_module.SUPPORTED_EMBEDDINGS,
        help="Enable one embedding family. Can be repeated; default: all families.",
    )
    parser.add_argument(
        "--weight",
        dest="weights",
        action="append",
        default=[],
        metavar="FAMILY=VALUE",
        help="Set every enabled family weight. Repeat once per enabled --source.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fingerprint",
        dest="mode",
        action="store_const",
        const=config_module.MODE_FINGERPRINT,
        default=config_module.MODE_FINGERPRINT,
        help=(
            "Primary mode, also the default. Search duplicates exclusively from stored SONARA "
            "fingerprints: no embeddings are loaded, candidates come from fingerprint LSH only, "
            "and only the exact native match score forms groups. Every reported candidate stays "
            "manual-review."
        ),
    )
    mode_group.add_argument(
        "--embedding",
        dest="mode",
        action="store_const",
        const=config_module.MODE_EMBEDDING,
        help=(
            "Secondary mode. Score duplicates from the enabled embedding families with the "
            "preset score and similarity gates; exact fingerprint checks still add manual-review "
            "pairs, and this is the only mode that can produce safe delete candidates for "
            "--apply."
        ),
    )
    parser.add_argument(
        "--skip-spectral",
        action="store_true",
        help=(
            "Skip the ffmpeg spectral check of duplicate-group files that flags suspected "
            "transcodes (fake-bitrate copies) and steers keeper choice toward full-band audio."
        ),
    )
    parser.add_argument("--limit-groups", type=int, help="Write at most N duplicate groups.")
    parser.add_argument("--out-dir", type=Path, default=config_module.DEFAULT_OUT_DIR, help="Report output directory.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="After writing reports, prompt for confirmation and delete safe duplicate candidates plus their database rows.",
    )
    return parser.parse_args(argv)


def confirm_apply(candidates: list[dict[str, object]], db_path: Path, root: Path) -> bool:
    print("")
    print("DESTRUCTIVE APPLY REQUESTED")
    print(f"Database: {db_path}")
    print(f"Root: {root}")
    print(f"Safe duplicate candidates to delete: {len(candidates)}")
    print("This will delete audio files from disk and remove only successfully deleted tracks from SQLite.")
    print('Type exactly "APPLY DELETE" to continue:')
    try:
        response = input("> ")
    except EOFError:
        return False
    return response == "APPLY DELETE"


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())

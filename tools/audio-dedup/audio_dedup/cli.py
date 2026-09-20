from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
import time

from . import config as config_module
from . import core as core_module


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, remaining_seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {remaining_seconds:02d}s"


class ConsoleProgressReporter:
    """Rewrite one progress line carrying elapsed time and a step estimate.

    Elapsed time covers the whole run; the estimate covers only the step in
    flight. Steps count different things - tracks, candidate pairs, clusters -
    so the rate measured on one says nothing about the ones that follow, and a
    step that has just started is not estimated at all.
    """

    def __init__(self, *, refresh_seconds: float = 1.0) -> None:
        self.refresh_seconds = max(0.0, float(refresh_seconds))
        self._started_at = time.monotonic()
        self._last_message: str | None = None
        self._last_rendered_at: float | None = None
        self._step_started_at = self._started_at
        self._step_base_processed = 0
        self._line_width = 0
        self._has_active_line = False

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started_at

    def __call__(self, processed: int, total: int, message: str) -> None:
        now = time.monotonic()
        completed = total > 0 and processed >= total
        phase_changed = message != self._last_message
        if phase_changed or processed < self._step_base_processed:
            self._step_started_at = now
            self._step_base_processed = processed
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
        rendered += f" | elapsed {_format_duration(now - self._started_at)}"
        remaining = self._remaining_seconds(now, processed, total)
        if remaining is not None:
            rendered += f" | eta ~{_format_duration(remaining)}"
        # The line is rewritten in place, so a shorter render has to wipe what
        # the longer one left behind.
        previous_width = self._line_width
        self._line_width = len(rendered)
        rendered = rendered.ljust(previous_width)
        sys.stdout.write(f"\r{rendered}")
        sys.stdout.flush()
        self._last_message = message
        self._last_rendered_at = now
        self._has_active_line = True

    def _remaining_seconds(self, now: float, processed: int, total: int) -> float | None:
        done = processed - self._step_base_processed
        step_elapsed = now - self._step_started_at
        if done <= 0 or step_elapsed <= 0 or total <= processed:
            return None
        return (total - processed) * (step_elapsed / done)

    def finish(self) -> None:
        if self._has_active_line:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._has_active_line = False
            self._line_width = 0


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    progress_reporter = ConsoleProgressReporter()
    try:
        result = core_module.run_report(
            db_path=args.db,
            path_contains=args.path_contains,
            limit_groups=args.limit_groups,
            out_dir=args.out_dir,
            mode=args.mode,
            detect_fake_bitrate=args.detect_fake_bitrate,
            progress_callback=progress_reporter,
        )
        progress_reporter.finish()
        scan_seconds = progress_reporter.elapsed_seconds
        retrieval = result.payload.get("fingerprint_retrieval", {})
        if not retrieval.get("valid_stored_fingerprint_count"):
            print(
                f"Warning: {args.mode} mode found 0 valid stored SONARA fingerprints in scope, "
                "so this empty report does not prove the scope has no duplicates. "
                "Analyze SONARA fingerprints first."
            )
    except (FileNotFoundError, OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        progress_reporter.finish()
        print(f"audio_dedup failed: {error}", file=sys.stderr)
        return 2
    statistics = result.payload.get("statistics", {})
    candidate_count = statistics.get("candidate_count", 0) if isinstance(statistics, dict) else 0
    print(
        "Report-only run complete. "
        f"groups={result.groups} copies_to_review={candidate_count} "
        f"scan_elapsed={_format_duration(scan_seconds)}"
    )
    print(f"json={result.json_path.resolve()}")
    print(f"xlsx={result.xlsx_path.resolve()}")
    print(f"log={result.log_path.resolve()}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find duplicate audio tracks from the stored SONARA fingerprints of an existing "
            "dj-track-similarity SQLite database. The tool is report-only: deleting copies is "
            "the reviewer's explicit act in the browser."
        )
    )
    parser.add_argument("--db", type=Path, default=config_module.DEFAULT_DB, help="Project SQLite database. Default: <repo>/database/volumes.sqlite.")
    parser.add_argument(
        "--path-contains",
        action="append",
        default=[],
        help="Additional case-insensitive substring filter on stored track paths. Can be repeated.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--fingerprint-scan",
        dest="mode",
        action="store_const",
        const=config_module.MODE_FINGERPRINT_SCAN,
        default=config_module.MODE_FINGERPRINT_SCAN,
        help=(
            "Primary mode, also the default. The upstream SONARA duplicate recipe over stored "
            "fingerprints: each track is matched against the representatives seen so far and "
            "joins the first one scoring above "
            f"{config_module.SONARA_DUPLICATE_MIN_SIMILARITY:g}, with candidates bucketed by "
            "rounded duration."
        ),
    )
    mode_group.add_argument(
        "--fingerprint-lsh",
        dest="mode",
        action="store_const",
        const=config_module.MODE_FINGERPRINT_LSH,
        help=(
            "Same stored fingerprints, but candidates come from version-separated fingerprint "
            "LSH instead of duration buckets, so copies with different durations still pair up. "
            "The exact native match needs "
            f"{config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY:g} to form a group."
        ),
    )
    parser.add_argument(
        "--detect-fake-bitrate",
        action="store_true",
        help=(
            "Run the ffmpeg spectral check of duplicate-group files that flags suspected "
            "transcodes (fake-bitrate copies) and steers keeper choice toward full-band audio. "
            "Off by default because it decodes every file in every group."
        ),
    )
    parser.add_argument("--limit-groups", type=int, help="Write at most N duplicate groups.")
    parser.add_argument("--out-dir", type=Path, default=config_module.DEFAULT_OUT_DIR, help="Report output directory.")
    return parser.parse_args(argv)


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())

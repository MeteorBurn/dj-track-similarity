"""Back up and optimize one SQLite database from the command line.

The work lives in ``dj_track_similarity.db_optimize``, which the server's
optimization job runs as well; this script only parses arguments and prints
the report. ``--dry-run`` stops after the read-only inspection and the free
space check.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from dj_track_similarity.db_optimize import (
    DatabaseInspection,
    InspectedDatabaseFile,
    OptimizationError,
    OptimizationSummary,
    OptimizedDatabaseFile,
    _require_free_space,
    inspect_database,
    optimize_database,
)

__all__ = [
    "DatabaseInspection",
    "InspectedDatabaseFile",
    "OptimizationError",
    "OptimizationSummary",
    "OptimizedDatabaseFile",
    "inspect_database",
    "main",
    "optimize_database",
]


def _fail(reason: str) -> int:
    print(f"FAIL: {reason}", flush=True)
    return 1


def _print_inspection(inspection: DatabaseInspection) -> None:
    print(f"database={inspection.db_path}")
    print(f"database_kind={inspection.database_kind}")
    print(f"sqlite_version={sqlite3.sqlite_version}")
    print("dry_run=true")
    print(f"size_before={inspection.size}")
    print(f"compacted_estimate={inspection.compacted_bytes}")
    print(f"required_free_bytes={inspection.required_free_bytes}")
    free = "unknown" if inspection.free_bytes is None else inspection.free_bytes
    print(f"free_bytes={free}")
    for item in inspection.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.journal_mode={item.journal_mode}")
        print(f"{item.role}.size={item.size}")
        print(f"{item.role}.freelist_pages={item.freelist_pages}")
        print(f"{item.role}.fts5_tables={','.join(item.fts5_tables) or 'none'}")
        print(f"{item.role}.integrity={item.integrity}")


def _print_summary(summary: OptimizationSummary) -> None:
    print(f"database={summary.db_path}")
    print(f"database_kind={summary.database_kind}")
    print(f"sqlite_version={sqlite3.sqlite_version}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")
    for item in summary.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.backup={item.backup_path}")
        print(f"{item.role}.journal_mode={item.journal_mode}")
        print(f"{item.role}.size_before={item.size_before}")
        print(f"{item.role}.size_after={item.size_after}")
        if item.checkpoint is not None:
            print(f"{item.role}.checkpoint={item.checkpoint}")
            if item.checkpoint != "complete":
                print(
                    f"{item.role}.note=another connection holds the database; "
                    "the WAL folds back on its next checkpoint"
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Back up and optimize a dj-track-similarity SQLite database.",
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Verify the database set and report what the run would do "
            "without writing anything."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.dry_run:
            inspection = inspect_database(Path(args.db))
            _require_free_space(inspection)
            _print_inspection(inspection)
            return 0
        summary = optimize_database(Path(args.db))
    except (OptimizationError, sqlite3.Error, OSError, ValueError) as error:
        return _fail(str(error))
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

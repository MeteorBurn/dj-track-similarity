"""Read-only integrity QA for one library database and optional Evaluation data."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import ExitStack
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dj_track_similarity.db_schema import validate_library_schema  # noqa: E402
from dj_track_similarity.db_storage import storage_database_paths  # noqa: E402


class QAError(RuntimeError):
    """A user-facing database QA failure."""


def _fail(reason: str) -> int:
    print(f"FAIL: {reason}", flush=True)
    return 1


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _open_read_only(path: Path, label: str) -> sqlite3.Connection:
    if not path.is_file():
        raise QAError(f"{label} database not found: {path}")
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise QAError(f"cannot open {label} database {path}: {error}") from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    return connection


def _integrity_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    failures = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    if failures or not rows:
        detail = failures[0] if failures else "no result"
        raise QAError(f"{label} integrity_check failed: {detail}")


def _foreign_key_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        row = rows[0]
        raise QAError(
            f"{label} foreign-key violation: "
            f"table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
        )


def _run_qa(
    db_path: Path,
    evaluation_db_path: Path | None,
) -> int:
    library_path = _resolved(db_path)
    default_evaluation_path = storage_database_paths(library_path).evaluation
    evaluation_path = (
        _resolved(evaluation_db_path)
        if evaluation_db_path is not None
        else default_evaluation_path
    )

    with ExitStack() as stack:
        library = _open_read_only(library_path, "Library")
        stack.callback(library.close)
        _integrity_check(library, "Library")
        _foreign_key_check(library, "Library")
        try:
            catalog_uuid = validate_library_schema(
                library,
                database_path=str(library_path),
            )
        except RuntimeError as error:
            raise QAError(f"Library identity validation failed: {error}") from error
        track_count = int(library.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])

        evaluation_present = evaluation_path.is_file()
        if evaluation_path.exists() and not evaluation_present:
            raise QAError(f"Evaluation database path is not a file: {evaluation_path}")
        if evaluation_present:
            evaluation = _open_read_only(evaluation_path, "Evaluation")
            stack.callback(evaluation.close)
            _integrity_check(evaluation, "Evaluation")
            _foreign_key_check(evaluation, "Evaluation")

    print("QA PASSED", flush=True)
    print(
        f"Library: {library_path}, catalog_uuid={catalog_uuid}, tracks={track_count}",
        flush=True,
    )
    if evaluation_present:
        print(f"Evaluation: {evaluation_path}", flush=True)
    else:
        print(f"Evaluation: not present ({evaluation_path})", flush=True)
    return 0


def run_qa(
    db_path: Path,
    evaluation_db_path: Path | None = None,
) -> int:
    """Run read-only integrity QA without creating or changing any database."""

    try:
        return _run_qa(db_path, evaluation_db_path)
    except (QAError, sqlite3.Error, OSError, TypeError, ValueError) as error:
        return _fail(str(error))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only integrity QA for a library database.",
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the library SQLite database.",
    )
    parser.add_argument(
        "--evaluation-db",
        metavar="PATH",
        default=None,
        help=(
            "Optional Evaluation sidecar path. By default, library.sqlite "
            "uses adjacent library.evaluation.sqlite and absence is allowed."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_qa(
        db_path=Path(args.db),
        evaluation_db_path=(
            Path(args.evaluation_db) if args.evaluation_db is not None else None
        ),
    )


if __name__ == "__main__":
    sys.exit(main())

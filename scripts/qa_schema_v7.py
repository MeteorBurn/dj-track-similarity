"""End-to-end QA harness for a migrated v7 library.

Usage:
    python scripts/qa_schema_v7.py --db PATH [--artifacts-db PATH] [--evaluation-db PATH]

Exit codes:
    0  QA PASSED
    1  FAIL: <reason>

All diagnostic/error output goes to stderr.
The primary result line (QA PASSED or FAIL: ...) goes to stdout.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORE_USER_VERSION = 7
SIDECAR_USER_VERSION = 1

REQUIRED_CORE_TABLES = {
    "tracks",
    "file_tags",
    "contracts",
    "sonara",
    "maest_scores",
    "classifier_scores",
    "likes",
    "pair_feedback",
    "transition_feedback",
    "library_catalog",
    "library_settings",
    "track_search_fts",
}

ARTIFACTS_SIDECAR_TABLES = [
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "clap_embeddings",
    "sonara_similarity_embeddings",
    "sonara_timeline",
    "sonara_fingerprints",
]

SCORE_BUCKET_HIGH = 0.7
SCORE_BUCKET_MEDIUM = 0.3
FLOAT_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fail(reason: str) -> int:
    """Print FAIL line to stdout and return exit code 1."""
    print(f"FAIL: {reason}", flush=True)
    return 1


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _get_user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _integrity_check(conn: sqlite3.Connection) -> Optional[str]:
    """Return None if ok, else the first non-ok result line."""
    rows = conn.execute("PRAGMA integrity_check").fetchall()
    for row in rows:
        val = row[0]
        if val != "ok":
            return val
    return None


def _foreign_key_check(conn: sqlite3.Connection) -> Optional[str]:
    """Return None if no violations, else a description of the first violation."""
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        r = rows[0]
        return f"table={r[0]} rowid={r[1]} parent={r[2]} fkid={r[3]}"
    return None


def _get_table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','shadow') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _score_bucket(score: float) -> str:
    if score >= SCORE_BUCKET_HIGH:
        return "high"
    if score >= SCORE_BUCKET_MEDIUM:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Check functions — each returns (ok: bool, reason: str | None)
# ---------------------------------------------------------------------------


def check_core_user_version(core_conn: sqlite3.Connection, db_path: Path) -> tuple[bool, Optional[str]]:
    uv = _get_user_version(core_conn)
    if uv != CORE_USER_VERSION:
        return False, f"Core user_version={uv}, expected {CORE_USER_VERSION} (path: {db_path})"
    return True, None


def check_sidecar_user_version(conn: sqlite3.Connection, label: str, path: Path) -> tuple[bool, Optional[str]]:
    uv = _get_user_version(conn)
    if uv != SIDECAR_USER_VERSION:
        return False, f"{label} user_version={uv}, expected {SIDECAR_USER_VERSION} (path: {path})"
    return True, None


def check_integrity(conn: sqlite3.Connection, label: str) -> tuple[bool, Optional[str]]:
    result = _integrity_check(conn)
    if result is not None:
        return False, f"{label} integrity_check failed: {result}"
    return True, None


def check_foreign_keys(conn: sqlite3.Connection, label: str) -> tuple[bool, Optional[str]]:
    result = _foreign_key_check(conn)
    if result is not None:
        return False, f"{label} foreign_key_check violation: {result}"
    return True, None


def check_required_tables(core_conn: sqlite3.Connection) -> tuple[bool, Optional[str]]:
    present = _get_table_names(core_conn)
    missing = REQUIRED_CORE_TABLES - present
    if missing:
        return False, f"Core missing tables: {sorted(missing)}"
    return True, None


def check_library_catalog_singleton(core_conn: sqlite3.Connection) -> tuple[bool, Optional[str]]:
    count = core_conn.execute("SELECT COUNT(*) FROM library_catalog").fetchone()[0]
    if count != 1:
        return False, f"library_catalog has {count} rows, expected exactly 1"
    return True, None


def check_catalog_uuid_binding(
    core_conn: sqlite3.Connection,
    sidecar_conn: sqlite3.Connection,
    sidecar_label: str,
) -> tuple[bool, Optional[str]]:
    core_row = core_conn.execute(
        "SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1"
    ).fetchone()
    if core_row is None:
        return False, "library_catalog singleton missing in Core"
    core_uuid = core_row["catalog_uuid"]

    meta_row = sidecar_conn.execute(
        "SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1"
    ).fetchone()
    if meta_row is None:
        return False, f"{sidecar_label} storage_metadata singleton missing"
    sidecar_uuid = meta_row["catalog_uuid"]

    if core_uuid != sidecar_uuid:
        return False, (
            f"{sidecar_label} catalog_uuid mismatch: "
            f"Core={core_uuid!r} vs sidecar={sidecar_uuid!r}"
        )
    return True, None


def check_orphan_rows(
    artifacts_conn: sqlite3.Connection,
    core_conn: sqlite3.Connection,
) -> tuple[bool, Optional[str]]:
    """Check every artifacts sidecar table for orphaned track_id / contract_hash."""
    # Collect valid sets from Core
    valid_track_ids: set[int] = {
        r[0] for r in core_conn.execute("SELECT track_id FROM tracks").fetchall()
    }
    valid_contract_hashes: set[str] = {
        r[0] for r in core_conn.execute("SELECT contract_hash FROM contracts").fetchall()
    }

    present_tables = _get_table_names(artifacts_conn)

    for table in ARTIFACTS_SIDECAR_TABLES:
        if table not in present_tables:
            continue

        # Check track_id orphans
        rows = artifacts_conn.execute(f"SELECT track_id, contract_hash FROM {table}").fetchall()  # noqa: S608
        orphan_track_count = sum(1 for r in rows if r["track_id"] not in valid_track_ids)
        if orphan_track_count > 0:
            return False, f"orphaned {table} rows: {orphan_track_count} (track_id not in Core tracks)"

        # Check contract_hash orphans
        orphan_contract_count = sum(1 for r in rows if r["contract_hash"] not in valid_contract_hashes)
        if orphan_contract_count > 0:
            return False, f"orphaned {table} rows: {orphan_contract_count} (contract_hash not in Core contracts)"

    return True, None


def check_fts_integrity(core_conn: sqlite3.Connection) -> tuple[bool, Optional[str]]:
    """FTS row count must be <= tracks row count."""
    track_count = core_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    fts_count = core_conn.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0]

    if track_count > 0 and fts_count == 0:
        return False, f"track_search_fts is empty but Core has {track_count} tracks"
    if fts_count > track_count:
        return False, f"track_search_fts has {fts_count} rows but tracks has only {track_count}"
    return True, None


def check_classifier_invariants(core_conn: sqlite3.Connection) -> tuple[bool, Optional[str]]:
    """Verify semantic invariants for every classifier_scores row."""
    rows = core_conn.execute(
        """
        SELECT track_id, classifier_key, positive_label, predicted_class,
               score_bucket, score, confidence, probabilities_json
        FROM classifier_scores
        """
    ).fetchall()

    for row in rows:
        track_id = row["track_id"]
        classifier_key = row["classifier_key"]
        ctx = f"classifier_scores track_id={track_id} classifier_key={classifier_key!r}"

        # Parse probabilities
        try:
            probs: dict[str, float] = json.loads(row["probabilities_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            return False, f"{ctx}: invalid probabilities_json: {exc}"

        if not probs:
            return False, f"{ctx}: probabilities_json is empty"

        # Check predicted_class is the argmax (accept ties — just must be a max-value key)
        max_prob = max(probs.values())
        if probs.get(row["predicted_class"]) is None:
            return False, f"{ctx}: predicted_class={row['predicted_class']!r} not in probabilities_json keys"
        if abs(probs[row["predicted_class"]] - max_prob) > FLOAT_TOLERANCE:
            return False, (
                f"{ctx}: predicted_class={row['predicted_class']!r} has prob "
                f"{probs[row['predicted_class']]} but max is {max_prob}"
            )

        # Check score_bucket
        expected_bucket = _score_bucket(row["score"])
        if row["score_bucket"] != expected_bucket:
            return False, (
                f"{ctx}: score_bucket={row['score_bucket']!r} but score={row['score']} "
                f"implies bucket={expected_bucket!r}"
            )

        # Check score == probabilities_json[positive_label]
        positive_label = row["positive_label"]
        if positive_label not in probs:
            return False, f"{ctx}: positive_label={positive_label!r} not in probabilities_json keys"
        expected_score = probs[positive_label]
        if abs(row["score"] - expected_score) > FLOAT_TOLERANCE:
            return False, (
                f"{ctx}: score={row['score']} != probabilities_json[{positive_label!r}]={expected_score}"
            )

        # Check confidence == max(probabilities_json.values())
        expected_confidence = max_prob
        if abs(row["confidence"] - expected_confidence) > FLOAT_TOLERANCE:
            return False, (
                f"{ctx}: confidence={row['confidence']} != max(probabilities)={expected_confidence}"
            )

    return True, None


# ---------------------------------------------------------------------------
# Main QA runner
# ---------------------------------------------------------------------------


def run_qa(
    db_path: Path,
    artifacts_db_path: Optional[Path],
    evaluation_db_path: Optional[Path],
) -> int:
    """Run all QA checks. Returns 0 on pass, 1 on fail."""

    # Derive sidecar paths from Core path if not provided
    if artifacts_db_path is None:
        artifacts_db_path = db_path.parent / (db_path.name + ".artifacts.sqlite")
    if evaluation_db_path is None:
        evaluation_db_path = db_path.parent / (db_path.name + ".evaluation.sqlite")

    # --- Open Core ---
    if not db_path.exists():
        return _fail(f"Core database not found: {db_path}")

    try:
        core_conn = _open_ro(db_path)
    except sqlite3.Error as exc:
        return _fail(f"Cannot open Core database {db_path}: {exc}")

    # --- Schema integrity: Core ---
    ok, reason = check_core_user_version(core_conn, db_path)
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    ok, reason = check_integrity(core_conn, "Core")
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    ok, reason = check_foreign_keys(core_conn, "Core")
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    ok, reason = check_required_tables(core_conn)
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    ok, reason = check_library_catalog_singleton(core_conn)
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    # --- FTS integrity ---
    ok, reason = check_fts_integrity(core_conn)
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    # --- Classifier semantic invariants ---
    ok, reason = check_classifier_invariants(core_conn)
    if not ok:
        core_conn.close()
        return _fail(reason)  # type: ignore[arg-type]

    # Gather Core stats for output
    track_count = core_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    contract_count = core_conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]

    # --- Artifacts sidecar ---
    artifacts_present = artifacts_db_path.exists()
    artifacts_conn: Optional[sqlite3.Connection] = None
    artifacts_stats: dict[str, int] = {}

    if artifacts_present:
        try:
            artifacts_conn = _open_ro(artifacts_db_path)
        except sqlite3.Error as exc:
            core_conn.close()
            return _fail(f"Cannot open artifacts sidecar {artifacts_db_path}: {exc}")

        ok, reason = check_sidecar_user_version(artifacts_conn, "Artifacts sidecar", artifacts_db_path)
        if not ok:
            artifacts_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_integrity(artifacts_conn, "Artifacts sidecar")
        if not ok:
            artifacts_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_foreign_keys(artifacts_conn, "Artifacts sidecar")
        if not ok:
            artifacts_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_catalog_uuid_binding(core_conn, artifacts_conn, "Artifacts sidecar")
        if not ok:
            artifacts_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_orphan_rows(artifacts_conn, core_conn)
        if not ok:
            artifacts_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        # Gather stats
        present_tables = _get_table_names(artifacts_conn)
        for table in ARTIFACTS_SIDECAR_TABLES:
            if table in present_tables:
                artifacts_stats[table] = artifacts_conn.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                ).fetchone()[0]

        artifacts_conn.close()

    # --- Evaluation sidecar ---
    evaluation_present = evaluation_db_path.exists()
    evaluation_conn: Optional[sqlite3.Connection] = None
    evaluation_stats: dict[str, int] = {}

    if evaluation_present:
        try:
            evaluation_conn = _open_ro(evaluation_db_path)
        except sqlite3.Error as exc:
            core_conn.close()
            return _fail(f"Cannot open evaluation sidecar {evaluation_db_path}: {exc}")

        ok, reason = check_sidecar_user_version(evaluation_conn, "Evaluation sidecar", evaluation_db_path)
        if not ok:
            evaluation_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_integrity(evaluation_conn, "Evaluation sidecar")
        if not ok:
            evaluation_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_foreign_keys(evaluation_conn, "Evaluation sidecar")
        if not ok:
            evaluation_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        ok, reason = check_catalog_uuid_binding(core_conn, evaluation_conn, "Evaluation sidecar")
        if not ok:
            evaluation_conn.close()
            core_conn.close()
            return _fail(reason)  # type: ignore[arg-type]

        # Gather stats
        evaluation_stats["search_sessions"] = evaluation_conn.execute(
            "SELECT COUNT(*) FROM search_sessions"
        ).fetchone()[0]
        evaluation_conn.close()

    core_conn.close()

    # --- All checks passed — print summary ---
    print("QA PASSED", flush=True)
    print(f"Core: {db_path}, tracks={track_count}, contracts={contract_count}", flush=True)

    if artifacts_present:
        stats_str = ", ".join(f"{t}={artifacts_stats.get(t, 0)}" for t in ARTIFACTS_SIDECAR_TABLES)
        print(f"Artifacts sidecar: {artifacts_db_path}, {stats_str}", flush=True)
    else:
        print(f"Artifacts sidecar: not present ({artifacts_db_path})", flush=True)

    if evaluation_present:
        print(
            f"Evaluation sidecar: {evaluation_db_path}, "
            f"search_sessions={evaluation_stats.get('search_sessions', 0)}",
            flush=True,
        )
    else:
        print(f"Evaluation sidecar: not present ({evaluation_db_path})", flush=True)

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QA harness for a migrated v7 library database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the v7 Core SQLite database (required).",
    )
    parser.add_argument(
        "--artifacts-db",
        metavar="PATH",
        default=None,
        help=(
            "Path to the artifacts sidecar SQLite database. "
            "Defaults to <db>.artifacts.sqlite adjacent to --db."
        ),
    )
    parser.add_argument(
        "--evaluation-db",
        metavar="PATH",
        default=None,
        help=(
            "Path to the evaluation sidecar SQLite database. "
            "Defaults to <db>.evaluation.sqlite adjacent to --db."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    artifacts_db_path = Path(args.artifacts_db) if args.artifacts_db else None
    evaluation_db_path = Path(args.evaluation_db) if args.evaluation_db else None

    return run_qa(db_path, artifacts_db_path, evaluation_db_path)


if __name__ == "__main__":
    sys.exit(main())

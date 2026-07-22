"""Prepare-SONARA-release protocol.

Ordered 7-step protocol that safely clears all SONARA-derived data from the
Core database (and optional sidecar databases) before a new SONARA release is
activated.  Crash-safe: a ``sonara.preparing_receipt`` key in
``library_settings`` records the last completed step so the command can resume
after an unexpected interruption.

Steps
-----
1. Acquire cross-process write lock on Core + all existing sidecars.
2. Verify backups of Core + attached sidecars into ``backup_dir`` are complete.
3. Write a ``preparing`` receipt to ``library_settings``.
4. Clear ``sonara_similarity_embeddings``, ``sonara_timeline``,
   ``sonara_fingerprints`` — each in its own sidecar transaction.
5. Verify those sidecar rows are absent.
6. In one final Core transaction: DELETE FROM ``sonara``; DELETE FROM
   ``classifier_scores`` WHERE ``uses_sonara=1 AND sonara_release_hash <>
   new_release_hash``; UPDATE ``library_settings`` SET
   ``sonara.active_release_hash`` = new_release_hash; DELETE receipt.
7. Release lock.

MUST NOT clear: ``maest_scores``, ``maest_embeddings``, ``mert_embeddings``,
``muq_embeddings``, ``clap_embeddings``.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

LOGGER = logging.getLogger(__name__)

CONFIRM_STRING = "PREPARE SONARA RELEASE"
RECEIPT_KEY = "sonara.preparing_receipt"
ACTIVE_RELEASE_HASH_KEY = "sonara.active_release_hash"

# Sidecar output kinds → (sidecar_suffix, table_name)
_SIDECAR_MAP: dict[str, tuple[str, str]] = {
    "timeline": ("timeline", "sonara_timeline"),
    "embedding": ("artifacts", "sonara_similarity_embeddings"),
    "fingerprint": ("artifacts", "sonara_fingerprints"),
}

# Lock is process-local; cross-process safety relies on SQLite WAL + busy timeout.
_PREPARE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

class PrepareSonaraReleaseError(RuntimeError):
    """Raised when the prepare protocol cannot proceed."""


class LockHeldError(PrepareSonaraReleaseError):
    """Raised when the prepare lock is already held."""


def prepare_sonara_release(
    *,
    db_path: Path,
    backup_dir: Path,
    sonara_outputs: Sequence[str],
    new_release_hash: str,
    previous_release_hash: str | None = None,
) -> dict[str, object]:
    """Execute the ordered 7-step prepare protocol.

    Parameters
    ----------
    db_path:
        Path to the Core SQLite database.
    backup_dir:
        Directory that must exist and be writable; backups are written here.
    sonara_outputs:
        Subset of ``{"core", "timeline", "embedding", "fingerprint"}`` that
        are in use.  ``"core"`` is always implied.
    new_release_hash:
        The release hash that will become active after preparation.
    previous_release_hash:
        The currently-active release hash (read from DB if not supplied).

    Returns
    -------
    dict
        The final receipt (with ``step=7`` and ``finalized_at`` timestamp).
    """
    if not _PREPARE_LOCK.acquire(blocking=False):
        raise LockHeldError("prepare-sonara-release is already running in this process")
    try:
        return _run_protocol(
            db_path=db_path,
            backup_dir=backup_dir,
            sonara_outputs=list(sonara_outputs),
            new_release_hash=new_release_hash,
            previous_release_hash=previous_release_hash,
        )
    finally:
        _PREPARE_LOCK.release()


# ---------------------------------------------------------------------------
# Internal protocol
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open_core(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _read_receipt(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT setting_value FROM library_settings WHERE setting_key = ?",
        (RECEIPT_KEY,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def _write_receipt(conn: sqlite3.Connection, receipt: dict) -> None:
    value = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
    conn.execute(
        """
        INSERT INTO library_settings(setting_key, setting_value, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at    = excluded.updated_at
        """,
        (RECEIPT_KEY, value, _now_iso()),
    )


def _delete_receipt(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM library_settings WHERE setting_key = ?", (RECEIPT_KEY,))


def _read_active_hash(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT setting_value FROM library_settings WHERE setting_key = ?",
        (ACTIVE_RELEASE_HASH_KEY,),
    ).fetchone()
    return row[0] if row else None


def _sidecar_path(db_path: Path, suffix: str) -> Path:
    """Return the sidecar path for a given suffix, e.g. 'timeline' → library.timeline.sqlite."""
    stem = db_path.stem
    return db_path.parent / f"{stem}.{suffix}.sqlite"


def _run_protocol(
    *,
    db_path: Path,
    backup_dir: Path,
    sonara_outputs: list[str],
    new_release_hash: str,
    previous_release_hash: str | None,
) -> dict[str, object]:
    # -----------------------------------------------------------------------
    # Step 1 — Acquire lock (already held by caller via threading.Lock).
    #           Open Core and read any existing receipt for crash-resume.
    # -----------------------------------------------------------------------
    LOGGER.info("prepare-sonara-release: step 1 — opening core db=%s", db_path)
    core = _open_core(db_path)
    try:
        receipt = _read_receipt(core)
        resumed_from_step = 0

        if receipt is not None:
            resumed_from_step = int(receipt.get("step", 0))
            LOGGER.info(
                "prepare-sonara-release: crash-resume detected, last completed step=%d",
                resumed_from_step,
            )
            # Honour the hashes recorded in the receipt so we stay consistent.
            new_release_hash = receipt.get("new_release_hash", new_release_hash)  # type: ignore[assignment]
            if previous_release_hash is None:
                previous_release_hash = receipt.get("previous_release_hash")  # type: ignore[assignment]
        else:
            if previous_release_hash is None:
                previous_release_hash = _read_active_hash(core)

        # Collect sidecar paths that are relevant to the requested outputs.
        sidecar_paths: dict[str, Path] = {}  # suffix → path
        for output in sonara_outputs:
            if output == "core":
                continue
            info = _SIDECAR_MAP.get(output)
            if info is None:
                continue
            suffix, _ = info
            if suffix not in sidecar_paths:
                sidecar_paths[suffix] = _sidecar_path(db_path, suffix)

        # -----------------------------------------------------------------------
        # Step 2 — Verify backups (skip if already done in a prior run).
        # -----------------------------------------------------------------------
        if resumed_from_step < 2:
            LOGGER.info("prepare-sonara-release: step 2 — verifying backups into %s", backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            _backup_database(db_path, backup_dir / f"{db_path.name}.bak")
            for suffix, sp in sidecar_paths.items():
                if sp.exists():
                    _backup_database(sp, backup_dir / f"{sp.name}.bak")
            LOGGER.info("prepare-sonara-release: step 2 complete")
        else:
            LOGGER.info("prepare-sonara-release: step 2 skipped (already done)")

        # -----------------------------------------------------------------------
        # Step 3 — Write preparing receipt.
        # -----------------------------------------------------------------------
        if resumed_from_step < 3:
            LOGGER.info("prepare-sonara-release: step 3 — writing receipt")
            receipt = {
                "step": 3,
                "started_at": _now_iso(),
                "previous_release_hash": previous_release_hash,
                "new_release_hash": new_release_hash,
            }
            with core:
                _write_receipt(core, receipt)
            LOGGER.info("prepare-sonara-release: step 3 complete")
        else:
            LOGGER.info("prepare-sonara-release: step 3 skipped (already done)")

        # -----------------------------------------------------------------------
        # Step 4 — Clear sidecar tables (each in its own transaction).
        # -----------------------------------------------------------------------
        if resumed_from_step < 4:
            LOGGER.info("prepare-sonara-release: step 4 — clearing sidecar tables")
            _clear_sidecar_tables(sidecar_paths, sonara_outputs)
            receipt = dict(receipt or {})
            receipt["step"] = 4
            with core:
                _write_receipt(core, receipt)
            LOGGER.info("prepare-sonara-release: step 4 complete")
        else:
            LOGGER.info("prepare-sonara-release: step 4 skipped (already done)")

        # -----------------------------------------------------------------------
        # Step 5 — Verify sidecar rows are absent.
        # -----------------------------------------------------------------------
        if resumed_from_step < 5:
            LOGGER.info("prepare-sonara-release: step 5 — verifying sidecar rows absent")
            _verify_sidecar_empty(sidecar_paths, sonara_outputs)
            receipt = dict(receipt or {})
            receipt["step"] = 5
            with core:
                _write_receipt(core, receipt)
            LOGGER.info("prepare-sonara-release: step 5 complete")
        else:
            LOGGER.info("prepare-sonara-release: step 5 skipped (already done)")

        # -----------------------------------------------------------------------
        # Step 6 — Final Core transaction.
        # -----------------------------------------------------------------------
        LOGGER.info("prepare-sonara-release: step 6 — final core transaction")
        finalized_at = _now_iso()
        with core:
            core.execute("DELETE FROM sonara")
            core.execute(
                """
                DELETE FROM classifier_scores
                WHERE uses_sonara = 1
                  AND (sonara_release_hash IS NULL OR sonara_release_hash <> ?)
                """,
                (new_release_hash,),
            )
            core.execute(
                """
                INSERT INTO library_settings(setting_key, setting_value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at    = excluded.updated_at
                """,
                (ACTIVE_RELEASE_HASH_KEY, new_release_hash, finalized_at),
            )
            _delete_receipt(core)
        LOGGER.info("prepare-sonara-release: step 6 complete")

        # -----------------------------------------------------------------------
        # Step 7 — Release lock (handled by caller's finally block).
        # -----------------------------------------------------------------------
        LOGGER.info("prepare-sonara-release: step 7 — done")
        final_receipt: dict[str, object] = {
            "step": 7,
            "finalized_at": finalized_at,
            "previous_release_hash": previous_release_hash,
            "new_release_hash": new_release_hash,
        }
        return final_receipt

    finally:
        core.close()


# ---------------------------------------------------------------------------
# Sidecar helpers
# ---------------------------------------------------------------------------

def _clear_sidecar_tables(
    sidecar_paths: dict[str, Path],
    sonara_outputs: list[str],
) -> None:
    """Clear each relevant sidecar table in its own transaction."""
    cleared: set[tuple[str, str]] = set()  # (suffix, table) already cleared

    for output in sonara_outputs:
        if output == "core":
            continue
        info = _SIDECAR_MAP.get(output)
        if info is None:
            continue
        suffix, table = info
        if (suffix, table) in cleared:
            continue
        sp = sidecar_paths.get(suffix)
        if sp is None or not sp.exists():
            LOGGER.info("prepare-sonara-release: sidecar %s not found, skipping", suffix)
            cleared.add((suffix, table))
            continue
        conn = sqlite3.connect(str(sp), timeout=30)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            # Check if the table exists before trying to delete from it.
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                with conn:
                    conn.execute(f"DELETE FROM {table}")
                LOGGER.info("prepare-sonara-release: cleared %s in %s", table, sp.name)
            else:
                LOGGER.info("prepare-sonara-release: table %s not in %s, skipping", table, sp.name)
        finally:
            conn.close()
        cleared.add((suffix, table))


def _verify_sidecar_empty(
    sidecar_paths: dict[str, Path],
    sonara_outputs: list[str],
) -> None:
    """Assert each relevant sidecar table has zero rows."""
    verified: set[tuple[str, str]] = set()

    for output in sonara_outputs:
        if output == "core":
            continue
        info = _SIDECAR_MAP.get(output)
        if info is None:
            continue
        suffix, table = info
        if (suffix, table) in verified:
            continue
        sp = sidecar_paths.get(suffix)
        if sp is None or not sp.exists():
            verified.add((suffix, table))
            continue
        conn = sqlite3.connect(str(sp), timeout=30)
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count != 0:
                    raise PrepareSonaraReleaseError(
                        f"Sidecar table {table} in {sp.name} still has {count} rows after clearing"
                    )
        finally:
            conn.close()
        verified.add((suffix, table))


def _backup_database(src: Path, dst: Path) -> None:
    """Copy *src* to *dst* using SQLite online backup API."""
    LOGGER.info("prepare-sonara-release: backing up %s → %s", src.name, dst.name)
    src_conn = sqlite3.connect(str(src), timeout=30)
    dst_conn = sqlite3.connect(str(dst), timeout=30)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


# ---------------------------------------------------------------------------
# Validation helpers (used by CLI and API)
# ---------------------------------------------------------------------------

def validate_confirm(confirm: str) -> None:
    """Raise ValueError if the confirmation string is wrong."""
    if confirm != CONFIRM_STRING:
        raise ValueError(
            f"Confirmation string must be exactly \"{CONFIRM_STRING}\"; got \"{confirm}\""
        )


def validate_backup_dir(backup_dir: Path) -> None:
    """Raise ValueError if backup_dir does not exist or is not writable."""
    if not backup_dir.exists():
        raise ValueError(f"--backup-dir does not exist: {backup_dir}")
    if not backup_dir.is_dir():
        raise ValueError(f"--backup-dir is not a directory: {backup_dir}")
    probe = backup_dir / ".write_probe"
    try:
        probe.touch()
        probe.unlink()
    except OSError as exc:
        raise ValueError(f"--backup-dir is not writable: {backup_dir}: {exc}") from exc


VALID_SONARA_OUTPUTS = frozenset({"core", "timeline", "embedding", "fingerprint"})


def validate_sonara_outputs(outputs: list[str]) -> None:
    """Raise ValueError if any output name is unknown."""
    unknown = set(outputs) - VALID_SONARA_OUTPUTS
    if unknown:
        raise ValueError(
            f"Unknown --sonara-outputs values: {sorted(unknown)}. "
            f"Valid values: {sorted(VALID_SONARA_OUTPUTS)}"
        )

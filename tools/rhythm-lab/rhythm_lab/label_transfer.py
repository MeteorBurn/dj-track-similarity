"""Deterministic, lossless transfer of Rhythm Lab manual labels to v7.

Export and Core matching are read-only. Restore is dry-run by default and can
write a fresh canonical Lab database only when explicitly applied. Unresolved
records remain losslessly available in the recovery table and report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import ntpath
import os
from pathlib import Path
import posixpath
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from dj_track_similarity.classifier_manifest import (
    CLASSIFIER_PUBLICATION_POINTER_NAME,
    resolve_classifier_artifact_paths,
)


EXPORT_KIND = "rhythm_lab_label_export"
PREVIEW_KIND = "rhythm_lab_label_rebind_preview"
REBOUND_KIND = "rhythm_lab_label_rebound"
BUNDLE_FORMAT_VERSION = 3
SHA256_PREFIX = "sha256:"
MTIME_TOLERANCE_NS = 1_000_000

_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_PROFILE_COLUMNS = (
    "classifier_key",
    "profile_type",
    "name",
    "description",
    "artifact_dir",
    "artifact_prefix",
    "training_min_added",
    "positive_label",
    "negative_label",
    "archived_at",
    "created_at",
    "updated_at",
)
_PROFILE_LABEL_COLUMNS = (
    "classifier_key",
    "label_key",
    "display_name",
    "description",
    "role",
    "position",
    "created_at",
    "updated_at",
)
_MANUAL_LABEL_COLUMNS = (
    "classifier_key",
    "source_track_id",
    "path",
    "size",
    "mtime",
    "label",
    "note",
    "updated_at",
)
_CORE_TRACK_COLUMNS = (
    "track_id",
    "track_uuid",
    "file_path",
    "file_size_bytes",
    "file_modified_ns",
    "content_generation",
)


def canonical_path_key(path: str) -> str:
    """Return a lexical absolute-path key without touching the filesystem.

    Windows drive and UNC paths use ``ntpath.normpath`` plus ordinary Unicode
    ``lower`` (not ``casefold``), so names such as ``straße`` and ``strasse``
    remain distinct.  POSIX absolute paths remain case-sensitive.  This is
    deliberately lexical: symlink and hardlink aliases are not resolved, while
    UNC separators and ``.``/``..`` components are normalized.  Relative paths
    are rejected rather than guessed against a process working directory.
    """

    text = str(path)
    if not text.strip():
        raise ValueError("Cannot canonicalize an empty track path")
    if "\x00" in text:
        raise ValueError("Cannot canonicalize a track path containing NUL")
    if _WINDOWS_ABSOLUTE_PATH.match(text) or text.startswith(("\\\\", "//")):
        return ntpath.normpath(text).replace("\\", "/").lower()
    if text.startswith("/"):
        return posixpath.normpath(text)
    raise ValueError("Cannot canonicalize a relative track path")


def export_label_bundle(
    lab_db_path: str | Path,
    *,
    promoted_models_root: str | Path | None = None,
) -> dict[str, Any]:
    """Read manual truth from a Lab DB and return a sealed deterministic bundle."""

    with _read_snapshot(lab_db_path) as (connection, selected_lab_db):
        _require_columns(connection, "classifier_profiles", _PROFILE_COLUMNS)
        _require_columns(
            connection,
            "classifier_profile_labels",
            _PROFILE_LABEL_COLUMNS,
        )
        _require_columns(connection, "classifier_labels", _MANUAL_LABEL_COLUMNS)
        profiles = [
            _selected_row(row, _PROFILE_COLUMNS)
            for row in connection.execute(
                """
                SELECT classifier_key, profile_type, name, description,
                       artifact_dir, artifact_prefix, training_min_added,
                       positive_label, negative_label, archived_at,
                       created_at, updated_at
                FROM classifier_profiles
                ORDER BY classifier_key
                """
            ).fetchall()
        ]
        profile_label_definitions = [
            _selected_row(row, _PROFILE_LABEL_COLUMNS)
            for row in connection.execute(
                """
                SELECT classifier_key, label_key, display_name, description,
                       role, position, created_at, updated_at
                FROM classifier_profile_labels
                ORDER BY classifier_key, position, label_key
                """
            ).fetchall()
        ]
        manual_labels = [
            _manual_label_payload(row)
            for row in connection.execute(
                """
                SELECT classifier_key, source_track_id, path, size, mtime,
                       label, note, updated_at
                FROM classifier_labels
                """
            ).fetchall()
        ]
        profiles = _sort_records(profiles)
        profile_label_definitions = _sort_records(profile_label_definitions)
        manual_labels = _sort_records(manual_labels)
        source_snapshot = {
            "manual_labels": manual_labels,
            "profile_label_definitions": profile_label_definitions,
            "profiles": profiles,
        }
        source_database = _database_provenance(
            connection,
            selected_lab_db,
            snapshot_payload=source_snapshot,
        )

    profile_keys = [str(profile["classifier_key"]) for profile in profiles]
    promoted_root = (
        Path(promoted_models_root)
        if promoted_models_root is not None
        else _default_promoted_models_root()
    )
    promoted_models = _read_promoted_models(promoted_root)
    payload = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "kind": EXPORT_KIND,
        "manual_labels": manual_labels,
        "profile_label_definitions": profile_label_definitions,
        "profiles": profiles,
        "promoted_models": promoted_models,
        "source_database": source_database,
        "summary": _export_summary(
            profile_keys=profile_keys,
            profile_label_definitions=profile_label_definitions,
            manual_labels=manual_labels,
            promoted_models=promoted_models,
        ),
    }
    return _seal_bundle(payload)


def preview_rebind_bundle(
    export_bundle: Mapping[str, Any],
    core_db_path: str | Path,
) -> dict[str, Any]:
    """Resolve exported labels against v7 Core by canonical path only.

    Rows with no match, multiple canonical matches, or file metadata changes
    remain unresolved.  No data is written and no fallback matching is used.
    """

    source = _verified_bundle(export_bundle, expected_kind=EXPORT_KIND)
    with _read_snapshot(core_db_path) as (connection, selected_core_db):
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version != 7:
            raise ValueError(
                f"Expected a v7 Core database (user_version=7), got {user_version}"
            )
        _require_columns(connection, "library_catalog", ("catalog_uuid",))
        _require_columns(connection, "tracks", _CORE_TRACK_COLUMNS)
        catalog_rows = connection.execute(
            "SELECT catalog_uuid FROM library_catalog"
        ).fetchall()
        if len(catalog_rows) != 1:
            raise ValueError(
                "Expected exactly one library_catalog row in the v7 Core database"
            )
        catalog_uuid = str(catalog_rows[0]["catalog_uuid"])
        track_rows = connection.execute(
            """
            SELECT track_id, track_uuid, file_path, file_size_bytes,
                   file_modified_ns, content_generation
            FROM tracks
            ORDER BY track_id, track_uuid
            """
        ).fetchall()
        track_payloads = _sort_records(
            [
                _core_track_payload(row, catalog_uuid=catalog_uuid)
                for row in track_rows
            ]
        )
        target_database = _database_provenance(
            connection,
            selected_core_db,
            snapshot_payload={
                "catalog_uuid": catalog_uuid,
                "tracks": track_payloads,
            },
        )
        target_database["catalog_uuid"] = catalog_uuid

    tracks_by_path: dict[str, list[dict[str, Any]]] = {}
    for target in track_payloads:
        key = canonical_path_key(str(target["file_path"]))
        tracks_by_path.setdefault(key, []).append(target)
    for candidates in tracks_by_path.values():
        candidates[:] = _sort_records(candidates)

    outcomes = _sort_records([
        _rebind_outcome(label, tracks_by_path)
        for label in source["manual_labels"]
    ])
    counts = Counter(str(outcome["status"]) for outcome in outcomes)
    payload = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "kind": PREVIEW_KIND,
        "outcomes": outcomes,
        "source_bundle_sha256": source["bundle_sha256"],
        "summary": {
            "ambiguous": counts["ambiguous"],
            "changed_at_same_path": counts["changed_at_same_path"],
            "strong_match": counts["strong_match"],
            "total": len(outcomes),
            "unmatched": counts["unmatched"],
            "weak_match": counts["weak_match"],
        },
        "target_catalog_uuid": catalog_uuid,
        "target_database": target_database,
    }
    return _seal_bundle(payload)


def build_rebound_bundle(
    export_bundle: Mapping[str, Any],
    preview_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine an export and preview without dropping unresolved label rows."""

    source = _verified_bundle(export_bundle, expected_kind=EXPORT_KIND)
    preview = _verified_bundle(preview_bundle, expected_kind=PREVIEW_KIND)
    if preview.get("source_bundle_sha256") != source["bundle_sha256"]:
        raise ValueError("Preview does not belong to the supplied export bundle")

    manual_labels = source.get("manual_labels")
    outcomes = preview.get("outcomes")
    if not isinstance(manual_labels, list) or not isinstance(outcomes, list):
        raise ValueError("Bundle label collections must be JSON arrays")
    if len(manual_labels) != len(outcomes):
        raise ValueError("Preview does not contain exactly one outcome per label")
    outcomes_by_identity: dict[str, Mapping[str, Any]] = {}
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            raise ValueError("Preview outcome must be a JSON object")
        outcome_source = _required_mapping(
            outcome.get("source"),
            field="preview outcome source",
        )
        identity = _validate_manual_label(outcome_source)
        if identity in outcomes_by_identity:
            raise ValueError("Preview contains a duplicate source outcome")
        outcomes_by_identity[identity] = outcome

    rebound_labels: list[dict[str, Any]] = []
    unresolved_counts: Counter[str] = Counter()
    bound = 0
    for expected_source in manual_labels:
        if not isinstance(expected_source, Mapping):
            raise ValueError("Export label must be a JSON object")
        identity = _validate_manual_label(expected_source)
        outcome = outcomes_by_identity.get(identity)
        if outcome is None:
            raise ValueError("Preview is missing a source label outcome")
        outcome_source = outcome.get("source")
        if outcome_source != expected_source:
            raise ValueError("Preview label order or source payload does not match export")
        status = str(outcome.get("status") or "")
        if status not in {
            "strong_match",
            "weak_match",
            "unmatched",
            "ambiguous",
            "changed_at_same_path",
        }:
            raise ValueError(f"Unsupported rebind status: {status!r}")
        target = outcome.get("target")
        if status in {"strong_match", "weak_match"}:
            if not isinstance(target, Mapping):
                raise ValueError("Matched preview outcome is missing its target")
            binding = {
                "catalog_uuid": str(target["catalog_uuid"]),
                "content_generation": int(target["content_generation"]),
                "selected_path": str(target["file_path"]),
                "track_id": int(target["track_id"]),
                "track_uuid": str(target["track_uuid"]),
            }
            bound += 1
        else:
            binding = None
            unresolved_counts[status] += 1
        rebound_row: dict[str, Any] = {
            "binding": binding,
            "source": deepcopy(expected_source),
            "status": status,
        }
        for optional_key in ("candidates", "metadata_mismatches", "reason"):
            if optional_key in outcome:
                rebound_row[optional_key] = deepcopy(outcome[optional_key])
        if "target" in outcome:
            rebound_row["target_snapshot"] = deepcopy(outcome["target"])
        rebound_labels.append(rebound_row)
    rebound_labels = _sort_records(rebound_labels)

    payload = {
        "format_version": BUNDLE_FORMAT_VERSION,
        "kind": REBOUND_KIND,
        "labels": rebound_labels,
        "profile_label_definitions": deepcopy(source["profile_label_definitions"]),
        "profiles": deepcopy(source["profiles"]),
        "promoted_models": deepcopy(source["promoted_models"]),
        "source_database": deepcopy(source["source_database"]),
        "source_bundle_sha256": source["bundle_sha256"],
        "summary": {
            "bound": bound,
            "total": len(rebound_labels),
            "unresolved": len(rebound_labels) - bound,
            "unresolved_by_status": {
                key: unresolved_counts[key]
                for key in sorted(unresolved_counts)
            },
        },
        "target_catalog_uuid": str(preview["target_catalog_uuid"]),
        "target_database": deepcopy(preview["target_database"]),
    }
    return _seal_bundle(payload)


def restore_label_bundle(
    rebound_bundle: Mapping[str, Any],
    lab_db_path: str | Path,
    *,
    core_db_path: str | Path,
    apply: bool = False,
    accepted_record_ids: Iterable[str] = (),
    _failure_hook: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Preview or apply one rebound bundle to a canonical v7 Lab database.

    Strong matches are eligible automatically. Weak matches require their
    stable ``record_id`` in ``accepted_record_ids``. Every other source row,
    including a deterministic conflict loser, is stored losslessly in
    ``classifier_label_recovery`` when the plan is applied.
    """

    source = _verified_bundle(rebound_bundle, expected_kind=REBOUND_KIND)
    accepted = set(accepted_record_ids)
    labels = _mapping_list(source.get("labels"), field="labels")
    known_record_ids = {
        _required_text(
            _required_mapping(row.get("source"), field="label.source"),
            "record_id",
        )
        for row in labels
    }
    unknown_accepted = sorted(accepted - known_record_ids)
    if unknown_accepted:
        raise ValueError(
            "Accepted record ids are not present in the rebound bundle: "
            + ", ".join(unknown_accepted)
        )

    current_targets, current_core_database = _read_current_core_targets(core_db_path)
    plan = _build_restore_plan(
        source,
        accepted_record_ids=accepted,
        current_targets=current_targets,
    )
    target = _absolute_lexical_path(lab_db_path)
    if target.exists() and not target.is_file():
        raise ValueError("Rhythm Lab restore target must be a regular file path")
    report: dict[str, Any] = {
        "applied": False,
        "bundle_sha256": source["bundle_sha256"],
        "conflict_policy": (
            "latest source updated_at wins; equal timestamps use the "
            "lexicographically smallest record_id"
        ),
        "current_core_database": current_core_database,
        "records": plan["records"],
        "summary": plan["summary"],
        "target_lab_db": str(target),
    }
    if not apply:
        return report

    backup = _backup_restore_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Import lazily so export and Core preview remain independent read-only tools.
    from rhythm_lab.lab_db import RhythmLabDatabase

    lab_database = RhythmLabDatabase(target)
    connection = lab_database.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_recovery_table(connection)
        _restore_profiles(
            connection,
            profiles=_mapping_list(source.get("profiles"), field="profiles"),
            definitions=_mapping_list(
                source.get("profile_label_definitions"),
                field="profile_label_definitions",
            ),
        )
        record_ids = [
            str(row["record_id"])
            for row in plan["records"]
        ]
        if record_ids:
            connection.executemany(
                "DELETE FROM classifier_label_recovery WHERE record_id = ?",
                [(record_id,) for record_id in record_ids],
            )
        for item in plan["bound"]:
            source_row = item["source"]
            target_row = item["target"]
            connection.execute(
                """
                INSERT INTO classifier_labels(
                    classifier_key, catalog_uuid, track_uuid,
                    content_generation, selected_path, file_size_bytes,
                    file_modified_ns, label, note, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    classifier_key, catalog_uuid, track_uuid,
                    content_generation, selected_path
                ) DO UPDATE SET
                    file_size_bytes = excluded.file_size_bytes,
                    file_modified_ns = excluded.file_modified_ns,
                    label = excluded.label,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    source_row["classifier_key"],
                    target_row["catalog_uuid"],
                    target_row["track_uuid"],
                    target_row["content_generation"],
                    target_row["selected_path"],
                    target_row["file_size_bytes"],
                    target_row["file_modified_ns"],
                    source_row["label"],
                    source_row.get("note"),
                    source_row["updated_at"],
                ),
            )
        for item in plan["recovered"]:
            connection.execute(
                """
                INSERT INTO classifier_label_recovery(
                    record_id, source_bundle_sha256, classifier_key,
                    source_record_json, rebind_status, recovery_reason,
                    candidate_binding_json, source_updated_at, recovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(record_id) DO UPDATE SET
                    source_bundle_sha256 = excluded.source_bundle_sha256,
                    classifier_key = excluded.classifier_key,
                    source_record_json = excluded.source_record_json,
                    rebind_status = excluded.rebind_status,
                    recovery_reason = excluded.recovery_reason,
                    candidate_binding_json = excluded.candidate_binding_json,
                    source_updated_at = excluded.source_updated_at,
                    recovered_at = CURRENT_TIMESTAMP
                """,
                (
                    item["record_id"],
                    source["bundle_sha256"],
                    item["source"]["classifier_key"],
                    _canonical_json_text(item["source"]),
                    item["status"],
                    item["reason"],
                    (
                        _canonical_json_text(item["target"])
                        if item.get("target") is not None
                        else None
                    ),
                    item["source"]["updated_at"],
                ),
            )
        if _failure_hook is not None:
            _failure_hook()
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    report["applied"] = True
    report["backup"] = backup
    return report


def _build_restore_plan(
    bundle: Mapping[str, Any],
    *,
    accepted_record_ids: set[str],
    current_targets: set[tuple[Any, ...]],
) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    for row in _mapping_list(bundle.get("labels"), field="labels"):
        source = _required_mapping(row.get("source"), field="label.source")
        record_id = _required_text(source, "record_id")
        status = _required_text(row, "status")
        explicitly_accepted = record_id in accepted_record_ids
        if status == "strong_match" or (
            status == "weak_match" and explicitly_accepted
        ):
            binding = _required_mapping(row.get("binding"), field="label.binding")
            snapshot = _required_mapping(
                row.get("target_snapshot"),
                field="label.target_snapshot",
            )
            target = {
                "catalog_uuid": _required_text(binding, "catalog_uuid"),
                "content_generation": _required_int(
                    binding,
                    "content_generation",
                ),
                "file_modified_ns": _required_int(
                    snapshot,
                    "file_modified_ns",
                ),
                "file_size_bytes": _required_int(
                    snapshot,
                    "file_size_bytes",
                ),
                "selected_path": _required_text(
                    binding,
                    "selected_path",
                ),
                "track_uuid": _required_text(binding, "track_uuid"),
            }
            current_identity = (
                target["catalog_uuid"],
                target["track_uuid"],
                target["content_generation"],
                target["selected_path"],
                target["file_size_bytes"],
                target["file_modified_ns"],
            )
            if current_identity not in current_targets:
                recovered.append(
                    {
                        "reason": "current_core_identity_or_file_facts_changed",
                        "record_id": record_id,
                        "source": source,
                        "status": "stale_binding",
                        "target": target,
                    }
                )
                continue
            eligible.append(
                {
                    "accepted": explicitly_accepted and status != "strong_match",
                    "record_id": record_id,
                    "source": source,
                    "status": status,
                    "target": target,
                }
            )
            continue
        reason = str(row.get("reason") or status)
        if status == "weak_match":
            reason = "weak_match_requires_explicit_acceptance"
        recovered.append(
            {
                "reason": reason,
                "record_id": record_id,
                "source": source,
                "status": status,
                "target": (
                    deepcopy(row["target_snapshot"])
                    if isinstance(row.get("target_snapshot"), Mapping)
                    else None
                ),
            }
        )

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in eligible:
        target = item["target"]
        identity = (
            item["source"]["classifier_key"],
            target["catalog_uuid"],
            target["track_uuid"],
            target["content_generation"],
            target["selected_path"],
        )
        groups.setdefault(identity, []).append(item)

    bound: list[dict[str, Any]] = []
    conflict_groups = 0
    conflict_losers = 0
    for identity in sorted(groups):
        candidates = groups[identity]
        latest_updated_at = max(str(item["source"]["updated_at"]) for item in candidates)
        latest = [
            item
            for item in candidates
            if str(item["source"]["updated_at"]) == latest_updated_at
        ]
        winner = min(latest, key=lambda item: str(item["record_id"]))
        bound.append(winner)
        if len(candidates) > 1:
            conflict_groups += 1
        for loser in candidates:
            if loser is winner:
                continue
            conflict_losers += 1
            recovered.append(
                {
                    "reason": f"conflict_loser_to:{winner['record_id']}",
                    "record_id": loser["record_id"],
                    "source": loser["source"],
                    "status": "conflict",
                    "target": loser["target"],
                }
            )

    bound.sort(key=lambda item: str(item["record_id"]))
    recovered.sort(key=lambda item: str(item["record_id"]))
    records = [
        {
            "action": "bind",
            "record_id": item["record_id"],
            "status": item["status"],
        }
        for item in bound
    ] + [
        {
            "action": "recover",
            "reason": item["reason"],
            "record_id": item["record_id"],
            "status": item["status"],
        }
        for item in recovered
    ]
    records.sort(key=lambda item: str(item["record_id"]))
    summary = {
        "accepted_bound": sum(bool(item["accepted"]) for item in bound),
        "bound": len(bound),
        "conflict_groups": conflict_groups,
        "conflict_losers": conflict_losers,
        "manual_label_total": len(records),
        "profile_count": len(_mapping_list(bundle.get("profiles"), field="profiles")),
        "profile_label_definition_count": len(
            _mapping_list(
                bundle.get("profile_label_definitions"),
                field="profile_label_definitions",
            )
        ),
        "recovered": len(recovered),
        "strong_bound": sum(item["status"] == "strong_match" for item in bound),
    }
    if summary["bound"] + summary["recovered"] != summary["manual_label_total"]:
        raise AssertionError("Restore plan lost a manual label record")
    return {
        "bound": bound,
        "records": records,
        "recovered": recovered,
        "summary": summary,
    }


def _read_current_core_targets(
    core_db_path: str | Path,
) -> tuple[set[tuple[Any, ...]], dict[str, Any]]:
    with _read_snapshot(core_db_path) as (connection, selected_core_db):
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if user_version != 7:
            raise ValueError(
                f"Expected a v7 Core database (user_version=7), got {user_version}"
            )
        _require_columns(connection, "library_catalog", ("catalog_uuid",))
        _require_columns(connection, "tracks", _CORE_TRACK_COLUMNS)
        catalog_rows = connection.execute(
            "SELECT catalog_uuid FROM library_catalog"
        ).fetchall()
        if len(catalog_rows) != 1:
            raise ValueError(
                "Expected exactly one library_catalog row in the v7 Core database"
            )
        catalog_uuid = str(catalog_rows[0]["catalog_uuid"])
        track_payloads = _sort_records(
            [
                _core_track_payload(row, catalog_uuid=catalog_uuid)
                for row in connection.execute(
                    """
                    SELECT track_id, track_uuid, file_path, file_size_bytes,
                           file_modified_ns, content_generation
                    FROM tracks
                    ORDER BY track_id, track_uuid
                    """
                ).fetchall()
            ]
        )
        provenance = _database_provenance(
            connection,
            selected_core_db,
            snapshot_payload={
                "catalog_uuid": catalog_uuid,
                "tracks": track_payloads,
            },
        )
        provenance["catalog_uuid"] = catalog_uuid
    identities = {
        (
            row["catalog_uuid"],
            row["track_uuid"],
            row["content_generation"],
            row["file_path"],
            row["file_size_bytes"],
            row["file_modified_ns"],
        )
        for row in track_payloads
    }
    return identities, provenance


def _ensure_recovery_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS classifier_label_recovery (
            record_id TEXT PRIMARY KEY,
            source_bundle_sha256 TEXT NOT NULL,
            classifier_key TEXT NOT NULL,
            source_record_json TEXT NOT NULL CHECK(json_valid(source_record_json)),
            rebind_status TEXT NOT NULL,
            recovery_reason TEXT NOT NULL,
            candidate_binding_json TEXT CHECK(
                candidate_binding_json IS NULL OR json_valid(candidate_binding_json)
            ),
            source_updated_at TEXT NOT NULL,
            recovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(classifier_key)
                REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
        )
        """
    )


def _restore_profiles(
    connection: sqlite3.Connection,
    *,
    profiles: Sequence[Mapping[str, Any]],
    definitions: Sequence[Mapping[str, Any]],
) -> None:
    for row in profiles:
        connection.execute(
            """
            INSERT INTO classifier_profiles(
                classifier_key, profile_type, name, description, artifact_dir,
                artifact_prefix, training_min_added, positive_label,
                negative_label, archived_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(classifier_key) DO UPDATE SET
                profile_type = excluded.profile_type,
                name = excluded.name,
                description = excluded.description,
                artifact_dir = excluded.artifact_dir,
                artifact_prefix = excluded.artifact_prefix,
                training_min_added = excluded.training_min_added,
                positive_label = excluded.positive_label,
                negative_label = excluded.negative_label,
                archived_at = excluded.archived_at,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            tuple(row[column] for column in _PROFILE_COLUMNS),
        )
    for row in definitions:
        connection.execute(
            """
            INSERT INTO classifier_profile_labels(
                classifier_key, label_key, display_name, description, role,
                position, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(classifier_key, label_key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                role = excluded.role,
                position = excluded.position,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            tuple(row[column] for column in _PROFILE_LABEL_COLUMNS),
        )


def _backup_restore_target(target: Path) -> dict[str, Any] | None:
    companions = [target, Path(f"{target}-wal"), Path(f"{target}-shm")]
    existing = [path for path in companions if path.exists()]
    if not existing:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_dir = target.parent / f"{target.name}.restore-backup-{timestamp}"
    backup_dir.mkdir()
    copied: list[dict[str, str]] = []
    for source in existing:
        destination = backup_dir / source.name
        shutil.copy2(source, destination)
        copied.append(
            {
                "backup": str(destination),
                "source": str(source),
            }
        )
    return {
        "directory": str(backup_dir),
        "files": copied,
    }


def _canonical_json_text(payload: Any) -> str:
    return _canonical_json_bytes(payload).decode("utf-8")


def write_restore_report(
    report: Mapping[str, Any],
    output_path: str | Path,
    *,
    force: bool = False,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Atomically write a restore preview/application report."""

    target = _absolute_lexical_path(output_path)
    _reject_unsafe_output(target, protected_paths=protected_paths)
    if target.exists() and not force:
        raise FileExistsError(
            f"Output already exists; pass --force to replace it: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json_bytes(dict(report)) + b"\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return target


def write_bundle(
    bundle: Mapping[str, Any],
    output_path: str | Path,
    *,
    force: bool = False,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Verify and atomically write canonical JSON bytes.

    Existing files require ``force=True``.  ``protected_paths`` are fail-closed:
    neither they nor their SQLite ``-wal``/``-shm`` companions may be targeted,
    even through case-only names, symlinks, or existing hardlinks.
    """

    verified = _verified_bundle(bundle)
    target = _absolute_lexical_path(output_path)
    _reject_unsafe_output(target, protected_paths=protected_paths)
    if target.exists() and not force:
        raise FileExistsError(
            f"Output already exists; pass --force to replace it: {target}"
        )
    if target.exists() and not target.is_file():
        raise ValueError("Bundle output must be a regular file path")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json_bytes(verified) + b"\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return target


def read_bundle(path: str | Path) -> dict[str, Any]:
    """Read and verify one exported, preview, or rebound JSON bundle."""

    selected = Path(path).expanduser().resolve(strict=True)
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Bundle is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Bundle root must be a JSON object")
    return _verified_bundle(payload)


@contextmanager
def _read_snapshot(
    path: str | Path,
) -> Iterator[tuple[sqlite3.Connection, Path]]:
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_file():
        raise ValueError("SQLite input must be an existing file")
    connection = sqlite3.connect(
        f"{selected.as_uri()}?mode=ro",
        uri=True,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        # The first read pins the snapshot, including committed WAL frames.
        connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
        yield connection, selected
    finally:
        try:
            if connection.in_transaction:
                connection.rollback()
        finally:
            connection.close()


def _database_provenance(
    connection: sqlite3.Connection,
    database_path: Path,
    *,
    snapshot_payload: Mapping[str, Any],
) -> dict[str, Any]:
    schema_rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name, tbl_name
        """
    ).fetchall()
    schema_payload = [
        {
            "name": str(row["name"]),
            "sql": str(row["sql"]) if row["sql"] is not None else None,
            "table_name": str(row["tbl_name"]),
            "type": str(row["type"]),
        }
        for row in schema_rows
    ]
    wal_path = database_path.with_name(database_path.name + "-wal")
    return {
        "database_file_sha256": _file_sha256(database_path),
        "journal_mode": str(
            connection.execute("PRAGMA journal_mode").fetchone()[0]
        ).lower(),
        "read_mode": "mode=ro fixed read transaction",
        "schema_object_count": len(schema_payload),
        "schema_sha256": _sha256_payload(schema_payload),
        "snapshot_sha256": _sha256_payload(snapshot_payload),
        "user_version": int(
            connection.execute("PRAGMA user_version").fetchone()[0]
        ),
        "wal_file_sha256": (
            _file_sha256(wal_path)
            if wal_path.is_file() and wal_path.stat().st_size > 0
            else None
        ),
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return SHA256_PREFIX + digest.hexdigest()


def _sha256_payload(payload: Any) -> str:
    digest = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return SHA256_PREFIX + digest


def _sort_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    copied = [deepcopy(dict(record)) for record in records]
    return sorted(copied, key=_canonical_json_bytes)


def _absolute_lexical_path(path: str | Path) -> Path:
    selected = Path(path).expanduser()
    if not selected.is_absolute():
        selected = Path.cwd() / selected
    return Path(os.path.abspath(os.path.normpath(str(selected))))


def _path_alias_key(path: Path) -> str:
    resolved = path.resolve(strict=False)
    return ntpath.normpath(str(resolved)).replace("\\", "/").lower()


def _protected_path_variants(paths: Iterable[str | Path]) -> list[Path]:
    variants: list[Path] = []
    for raw_path in paths:
        selected = _absolute_lexical_path(raw_path)
        variants.extend(
            (
                selected,
                selected.with_name(selected.name + "-wal"),
                selected.with_name(selected.name + "-shm"),
            )
        )
    return variants


def _reject_unsafe_output(
    target: Path,
    *,
    protected_paths: Iterable[str | Path],
) -> None:
    lower_name = target.name.lower()
    if lower_name.endswith(".sqlite") or lower_name.endswith(("-wal", "-shm")):
        raise ValueError("Refusing to write a bundle to a SQLite or sidecar path")
    target_key = _path_alias_key(target)
    for protected in _protected_path_variants(protected_paths):
        if target_key == _path_alias_key(protected):
            raise ValueError("Refusing to overwrite an input or SQLite sidecar")
        if target.exists() and protected.exists():
            try:
                if os.path.samefile(target, protected):
                    raise ValueError(
                        "Refusing to overwrite an input through a filesystem alias"
                    )
            except OSError:
                # The lexical and resolved checks above remain authoritative when
                # a platform cannot query file identity.
                continue


def _require_columns(
    connection: sqlite3.Connection,
    table: str,
    required: Sequence[str],
) -> None:
    table_row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if table_row is None:
        raise ValueError(f"SQLite input is missing required table {table!r}")
    available = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    missing = [column for column in required if column not in available]
    if missing:
        raise ValueError(
            f"SQLite table {table!r} is missing required columns: "
            + ", ".join(missing)
        )


def _selected_row(row: sqlite3.Row, columns: Sequence[str]) -> dict[str, Any]:
    return {column: row[column] for column in columns}


def _manual_label_payload(row: sqlite3.Row) -> dict[str, Any]:
    path = str(row["path"]) if row["path"] is not None else None
    mtime = _finite_optional_float(row["mtime"], field="mtime")
    classifier_key = str(row["classifier_key"])
    source_track_id = int(row["source_track_id"])
    return {
        "canonical_path_key": canonical_path_key(path) if path is not None else None,
        "classifier_key": classifier_key,
        "label": str(row["label"]),
        "mtime": mtime,
        "note": row["note"],
        "path": path,
        "record_id": _manual_record_id(classifier_key, source_track_id),
        "size": int(row["size"]) if row["size"] is not None else None,
        "source_track_id": source_track_id,
        "updated_at": str(row["updated_at"]),
    }


def _manual_record_id(classifier_key: str, source_track_id: int) -> str:
    return _sha256_payload(
        {
            "classifier_key": classifier_key,
            "source_track_id": source_track_id,
        }
    )


def _finite_optional_float(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Manual label {field} must be finite when present")
    return number


def _read_promoted_models(root: Path) -> list[dict[str, Any]]:
    selected = root.expanduser().resolve(strict=False)
    if not selected.is_dir():
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    profile_dirs = sorted(
        {
            path.parent
            for path in (
                *selected.glob("*/model.json"),
                *selected.glob(f"*/{CLASSIFIER_PUBLICATION_POINTER_NAME}"),
            )
        },
        key=lambda path: path.relative_to(selected).as_posix().casefold(),
    )
    for profile_dir in profile_dirs:
        resolved = resolve_classifier_artifact_paths(
            profile_dir / "model.joblib"
        )
        manifest = resolved.metadata_path
        try:
            manifest_bytes = manifest.read_bytes()
            raw = json.loads(manifest_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Cannot read promoted classifier manifest {manifest.parent.name!r}"
            ) from error
        if not isinstance(raw, dict):
            raise ValueError("Promoted classifier manifest root must be an object")
        classifier_key = str(raw.get("classifier_key") or "").strip()
        feature_set = str(raw.get("feature_set") or "").strip()
        if not classifier_key or not feature_set:
            raise ValueError(
                "Promoted classifier manifest requires classifier_key and feature_set"
            )
        if classifier_key in seen:
            raise ValueError(
                f"Duplicate promoted classifier manifest for {classifier_key!r}"
            )
        seen.add(classifier_key)
        manifest_sha256 = (
            SHA256_PREFIX + hashlib.sha256(manifest_bytes).hexdigest()
        )
        artifact = resolved.model_path
        declared_artifact_sha256 = _optional_sha256(
            raw.get("artifact_hash"),
            field=f"promoted classifier {classifier_key!r} artifact_hash",
        )
        artifact_sha256 = _file_sha256(artifact) if artifact.is_file() else None
        if declared_artifact_sha256 is not None:
            if artifact_sha256 is None:
                raise ValueError(
                    f"Promoted model artifact is missing for {classifier_key!r}"
                )
            if artifact_sha256 != declared_artifact_sha256:
                raise ValueError(
                    f"Promoted model artifact SHA-256 mismatch for {classifier_key!r}"
                )
        raw_feature_names = raw.get("feature_names")
        feature_names_source: str | None = None
        if raw_feature_names is None and isinstance(raw.get("feature_manifest"), dict):
            raw_feature_names = raw["feature_manifest"].get("feature_names")
            if raw_feature_names is not None:
                feature_names_source = "manifest"
        elif raw_feature_names is not None:
            feature_names_source = "manifest"
        if raw_feature_names is None:
            raw_feature_names = _feature_names_from_promoted_artifact(
                artifact,
                classifier_key=classifier_key,
                declared_artifact_sha256=declared_artifact_sha256,
                feature_set=feature_set,
            )
            if raw_feature_names is not None:
                feature_names_source = "promoted_model_artifact"
        if raw_feature_names is None:
            feature_names = None
        elif isinstance(raw_feature_names, list) and all(
            isinstance(name, str) for name in raw_feature_names
        ):
            feature_names = list(raw_feature_names)
        else:
            raise ValueError(
                f"Promoted classifier {classifier_key!r} has invalid feature_names"
            )
        raw_label_order = raw.get("label_order")
        if raw_label_order is None:
            label_order = None
        elif isinstance(raw_label_order, list) and all(
            isinstance(label, str) for label in raw_label_order
        ):
            label_order = list(raw_label_order)
        else:
            raise ValueError(
                f"Promoted classifier {classifier_key!r} has invalid label_order"
            )
        feature_count = raw.get("feature_count")
        parsed_feature_count = (
            int(feature_count) if feature_count is not None else None
        )
        if (
            feature_names is not None
            and parsed_feature_count is not None
            and parsed_feature_count != len(feature_names)
        ):
            raise ValueError(
                f"Promoted classifier {classifier_key!r} feature_count does not "
                "match feature_names"
            )
        result.append(
            {
                "artifact_sha256": artifact_sha256,
                "classifier_key": classifier_key,
                "declared_artifact_sha256": declared_artifact_sha256,
                "feature_count": parsed_feature_count,
                "feature_names": feature_names,
                "feature_names_source": feature_names_source,
                "feature_set": feature_set,
                "label_order": label_order,
                "manifest_sha256": manifest_sha256,
                "manifest_version": (
                    int(raw["manifest_version"])
                    if raw.get("manifest_version") is not None
                    else None
                ),
            }
        )
    return _sort_records(result)


def _feature_names_from_promoted_artifact(
    artifact: Path,
    *,
    classifier_key: str,
    declared_artifact_sha256: str | None,
    feature_set: str,
) -> list[str] | None:
    if not artifact.is_file():
        return None
    if declared_artifact_sha256 is None:
        raise ValueError(
            f"Refusing to load promoted model artifact for {classifier_key!r} "
            "without a declared artifact_hash"
        )
    artifact_bytes = artifact.read_bytes()
    actual_artifact_sha256 = (
        SHA256_PREFIX + hashlib.sha256(artifact_bytes).hexdigest()
    )
    if actual_artifact_sha256 != declared_artifact_sha256:
        raise ValueError(
            f"Promoted model artifact SHA-256 mismatch for {classifier_key!r}"
        )
    try:
        from joblib import load

        payload = load(io.BytesIO(artifact_bytes))
    except Exception as error:
        raise ValueError(
            f"Cannot read promoted model artifact for {classifier_key!r}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(
            f"Promoted model artifact for {classifier_key!r} must contain an object"
        )
    if str(payload.get("classifier_key") or "") != classifier_key:
        raise ValueError(
            f"Promoted model artifact classifier identity mismatch for {classifier_key!r}"
        )
    if str(payload.get("feature_set") or "") != feature_set:
        raise ValueError(
            f"Promoted model artifact feature_set mismatch for {classifier_key!r}"
        )
    feature_names = payload.get("feature_names")
    if not isinstance(feature_names, list) or not all(
        isinstance(name, str) for name in feature_names
    ):
        raise ValueError(
            f"Promoted model artifact for {classifier_key!r} has invalid feature_names"
        )
    return list(feature_names)


def _optional_sha256(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", text):
        raise ValueError(f"{field} must be sha256 followed by 64 lowercase hex digits")
    return text


def _default_promoted_models_root() -> Path:
    return Path(__file__).resolve().parents[3] / "models" / "classifiers"


def _export_summary(
    *,
    profile_keys: Sequence[str],
    profile_label_definitions: Sequence[Mapping[str, Any]],
    manual_labels: Sequence[Mapping[str, Any]],
    promoted_models: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    profile_counts = Counter(
        str(label["classifier_key"]) for label in manual_labels
    )
    class_counts = Counter(
        (str(label["classifier_key"]), str(label["label"]))
        for label in manual_labels
    )
    defined_classes = {
        (str(row["classifier_key"]), str(row["label_key"]))
        for row in profile_label_definitions
    }
    class_keys = sorted(defined_classes | set(class_counts))
    distinct_paths = {
        str(label["canonical_path_key"])
        for label in manual_labels
        if label.get("canonical_path_key") is not None
    }
    return {
        "distinct_canonical_path_count": len(distinct_paths),
        "manual_label_count": len(manual_labels),
        "manual_labels_without_path": sum(
            label.get("canonical_path_key") is None for label in manual_labels
        ),
        "profile_count": len(profile_keys),
        "profile_label_definition_count": len(profile_label_definitions),
        "promoted_model_count": len(promoted_models),
        "counts_by_profile": [
            {
                "classifier_key": classifier_key,
                "count": profile_counts[classifier_key],
            }
            for classifier_key in sorted(profile_keys)
        ],
        "counts_by_profile_and_class": [
            {
                "classifier_key": classifier_key,
                "label": label,
                "count": class_counts[(classifier_key, label)],
            }
            for classifier_key, label in class_keys
        ],
    }


def _core_track_payload(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
) -> dict[str, Any]:
    return {
        "catalog_uuid": catalog_uuid,
        "content_generation": int(row["content_generation"]),
        "file_modified_ns": int(row["file_modified_ns"]),
        "file_path": str(row["file_path"]),
        "file_size_bytes": int(row["file_size_bytes"]),
        "track_id": int(row["track_id"]),
        "track_uuid": str(row["track_uuid"]),
    }


def _rebind_outcome(
    source_label: Mapping[str, Any],
    tracks_by_path: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    source = deepcopy(dict(source_label))
    path_key = source.get("canonical_path_key")
    if path_key is None:
        return {
            "candidates": [],
            "reason": "missing_path",
            "source": source,
            "status": "unmatched",
        }
    candidates = [
        deepcopy(dict(candidate))
        for candidate in tracks_by_path.get(str(path_key), ())
    ]
    if not candidates:
        return {
            "candidates": [],
            "reason": "no_exact_canonical_path_match",
            "source": source,
            "status": "unmatched",
        }
    if len(candidates) > 1:
        return {
            "candidates": candidates,
            "reason": "multiple_exact_canonical_path_matches",
            "source": source,
            "status": "ambiguous",
        }
    target = candidates[0]
    mismatches = _metadata_mismatches(source, target)
    if mismatches:
        return {
            "metadata_mismatches": mismatches,
            "source": source,
            "status": "changed_at_same_path",
            "target": target,
        }
    if source.get("size") is None and source.get("mtime") is None:
        return {
            "source": source,
            "status": "weak_match",
            "target": target,
        }
    return {
        "source": source,
        "status": "strong_match",
        "target": target,
    }


def _metadata_mismatches(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    source_size = source.get("size")
    if source_size is not None:
        actual_size = int(target["file_size_bytes"])
        expected_size = int(source_size)
        if actual_size != expected_size:
            result.append(
                {
                    "actual": actual_size,
                    "expected": expected_size,
                    "field": "file_size_bytes",
                }
            )
    source_mtime = source.get("mtime")
    if source_mtime is not None:
        expected_ns = int(round(float(source_mtime) * 1_000_000_000))
        actual_ns = int(target["file_modified_ns"])
        if abs(actual_ns - expected_ns) > MTIME_TOLERANCE_NS:
            result.append(
                {
                    "actual": actual_ns,
                    "expected": expected_ns,
                    "field": "file_modified_ns",
                    "tolerance_ns": MTIME_TOLERANCE_NS,
                }
            )
    return result


def _validate_export_bundle(bundle: Mapping[str, Any]) -> None:
    profiles = _mapping_list(bundle.get("profiles"), field="profiles")
    profile_labels = _mapping_list(
        bundle.get("profile_label_definitions"),
        field="profile_label_definitions",
    )
    manual_labels = _mapping_list(
        bundle.get("manual_labels"),
        field="manual_labels",
    )
    promoted_models = _mapping_list(
        bundle.get("promoted_models"),
        field="promoted_models",
    )
    _require_sorted(profiles, field="profiles")
    _require_sorted(profile_labels, field="profile_label_definitions")
    _require_sorted(manual_labels, field="manual_labels")
    _require_sorted(promoted_models, field="promoted_models")

    profile_keys = _unique_text_values(
        profiles,
        field="classifier_key",
        collection="profiles",
    )
    definition_keys: set[tuple[str, str]] = set()
    for row in profile_labels:
        classifier_key = _required_text(row, "classifier_key")
        label_key = _required_text(row, "label_key")
        if classifier_key not in profile_keys:
            raise ValueError("Profile label definition references an unknown profile")
        identity = (classifier_key, label_key)
        if identity in definition_keys:
            raise ValueError("Duplicate profile label definition")
        definition_keys.add(identity)

    _validate_manual_labels(
        manual_labels,
        profile_keys=profile_keys,
        definition_keys=definition_keys,
    )
    _validate_promoted_models(promoted_models, profile_keys=profile_keys)
    source_database = _required_mapping(
        bundle.get("source_database"),
        field="source_database",
    )
    _validate_database_provenance(source_database)
    expected_snapshot = {
        "manual_labels": manual_labels,
        "profile_label_definitions": profile_labels,
        "profiles": profiles,
    }
    if source_database["snapshot_sha256"] != _sha256_payload(expected_snapshot):
        raise ValueError("Source database snapshot SHA-256 is inconsistent")
    expected_summary = _export_summary(
        profile_keys=sorted(profile_keys),
        profile_label_definitions=profile_labels,
        manual_labels=manual_labels,
        promoted_models=promoted_models,
    )
    if bundle.get("summary") != expected_summary:
        raise ValueError("Export summary is inconsistent with bundle contents")


def _validate_preview_bundle(bundle: Mapping[str, Any]) -> None:
    _require_sha256(bundle.get("source_bundle_sha256"), field="source bundle")
    catalog_uuid = _required_text(bundle, "target_catalog_uuid")
    target_database = _required_mapping(
        bundle.get("target_database"),
        field="target_database",
    )
    _validate_database_provenance(target_database)
    if _required_text(target_database, "catalog_uuid") != catalog_uuid:
        raise ValueError("Target database catalog identity is inconsistent")
    outcomes = _mapping_list(bundle.get("outcomes"), field="outcomes")
    _require_sorted(outcomes, field="outcomes")
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    for outcome in outcomes:
        source = _required_mapping(outcome.get("source"), field="outcome.source")
        identity = _validate_manual_label(source)
        if identity in seen:
            raise ValueError("Preview contains a duplicate source label")
        seen.add(identity)
        status = _validate_outcome(outcome, catalog_uuid=catalog_uuid)
        counts[status] += 1
    expected_summary = {
        "ambiguous": counts["ambiguous"],
        "changed_at_same_path": counts["changed_at_same_path"],
        "strong_match": counts["strong_match"],
        "total": len(outcomes),
        "unmatched": counts["unmatched"],
        "weak_match": counts["weak_match"],
    }
    if bundle.get("summary") != expected_summary:
        raise ValueError("Preview summary is inconsistent with outcomes")


def _validate_rebound_bundle(bundle: Mapping[str, Any]) -> None:
    _require_sha256(bundle.get("source_bundle_sha256"), field="source bundle")
    catalog_uuid = _required_text(bundle, "target_catalog_uuid")
    profiles = _mapping_list(bundle.get("profiles"), field="profiles")
    profile_labels = _mapping_list(
        bundle.get("profile_label_definitions"),
        field="profile_label_definitions",
    )
    promoted_models = _mapping_list(
        bundle.get("promoted_models"),
        field="promoted_models",
    )
    labels = _mapping_list(bundle.get("labels"), field="labels")
    for field, records in (
        ("profiles", profiles),
        ("profile_label_definitions", profile_labels),
        ("promoted_models", promoted_models),
        ("labels", labels),
    ):
        _require_sorted(records, field=field)

    profile_keys = _unique_text_values(
        profiles,
        field="classifier_key",
        collection="profiles",
    )
    definition_keys: set[tuple[str, str]] = set()
    for row in profile_labels:
        classifier_key = _required_text(row, "classifier_key")
        label_key = _required_text(row, "label_key")
        if classifier_key not in profile_keys:
            raise ValueError("Profile label definition references an unknown profile")
        identity = (classifier_key, label_key)
        if identity in definition_keys:
            raise ValueError("Duplicate profile label definition")
        definition_keys.add(identity)
    _validate_promoted_models(promoted_models, profile_keys=profile_keys)

    seen: set[str] = set()
    source_labels: list[dict[str, Any]] = []
    unresolved_counts: Counter[str] = Counter()
    bound = 0
    for row in labels:
        source = _required_mapping(row.get("source"), field="label.source")
        identity = _validate_manual_label(
            source,
            profile_keys=profile_keys,
            definition_keys=definition_keys,
        )
        if identity in seen:
            raise ValueError("Rebound bundle contains a duplicate source label")
        seen.add(identity)
        source_labels.append(dict(source))
        status = str(row.get("status") or "")
        pseudo_outcome: dict[str, Any] = {
            "source": source,
            "status": status,
        }
        if "target_snapshot" in row:
            pseudo_outcome["target"] = row["target_snapshot"]
        for key in ("candidates", "metadata_mismatches", "reason"):
            if key in row:
                pseudo_outcome[key] = row[key]
        _validate_outcome(pseudo_outcome, catalog_uuid=catalog_uuid)
        binding = row.get("binding")
        if status in {"strong_match", "weak_match"}:
            target = _required_mapping(
                pseudo_outcome.get("target"),
                field="matched target",
            )
            expected_binding = {
                "catalog_uuid": str(target["catalog_uuid"]),
                "content_generation": int(target["content_generation"]),
                "selected_path": str(target["file_path"]),
                "track_id": int(target["track_id"]),
                "track_uuid": str(target["track_uuid"]),
            }
            if binding != expected_binding:
                raise ValueError("Rebound binding does not match its target snapshot")
            bound += 1
        else:
            if binding is not None:
                raise ValueError("Unresolved rebound label must not have a binding")
            unresolved_counts[status] += 1

    source_database = _required_mapping(
        bundle.get("source_database"),
        field="source_database",
    )
    target_database = _required_mapping(
        bundle.get("target_database"),
        field="target_database",
    )
    _validate_database_provenance(source_database)
    _validate_database_provenance(target_database)
    if _required_text(target_database, "catalog_uuid") != catalog_uuid:
        raise ValueError("Target database catalog identity is inconsistent")
    expected_source_snapshot = {
        "manual_labels": _sort_records(source_labels),
        "profile_label_definitions": profile_labels,
        "profiles": profiles,
    }
    if (
        source_database["snapshot_sha256"]
        != _sha256_payload(expected_source_snapshot)
    ):
        raise ValueError("Rebound source snapshot SHA-256 is inconsistent")
    expected_summary = {
        "bound": bound,
        "total": len(labels),
        "unresolved": len(labels) - bound,
        "unresolved_by_status": {
            key: unresolved_counts[key] for key in sorted(unresolved_counts)
        },
    }
    if bundle.get("summary") != expected_summary:
        raise ValueError("Rebound summary is inconsistent with labels")


def _validate_manual_labels(
    labels: Sequence[Mapping[str, Any]],
    *,
    profile_keys: set[str],
    definition_keys: set[tuple[str, str]],
) -> None:
    seen: set[str] = set()
    for row in labels:
        identity = _validate_manual_label(
            row,
            profile_keys=profile_keys,
            definition_keys=definition_keys,
        )
        if identity in seen:
            raise ValueError("Duplicate manual label record identity")
        seen.add(identity)


def _validate_manual_label(
    row: Mapping[str, Any],
    *,
    profile_keys: set[str] | None = None,
    definition_keys: set[tuple[str, str]] | None = None,
) -> str:
    classifier_key = _required_text(row, "classifier_key")
    label = _required_text(row, "label")
    source_track_id = _required_int(row, "source_track_id")
    record_id = _require_sha256(row.get("record_id"), field="manual label record")
    if record_id != _manual_record_id(classifier_key, source_track_id):
        raise ValueError("Manual label record identity is inconsistent")
    path = row.get("path")
    path_key = row.get("canonical_path_key")
    if path is None:
        if path_key is not None:
            raise ValueError("Pathless manual label must not have a canonical path key")
    else:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Manual label path must be non-empty when present")
        if not isinstance(path_key, str) or canonical_path_key(path) != path_key:
            raise ValueError("Manual label canonical path key is inconsistent")
    if profile_keys is not None and classifier_key not in profile_keys:
        raise ValueError("Manual label references an unknown profile")
    if (
        definition_keys is not None
        and (classifier_key, label) not in definition_keys
    ):
        raise ValueError("Manual label references an unknown profile label")
    size = row.get("size")
    if size is not None and (isinstance(size, bool) or int(size) < 0):
        raise ValueError("Manual label size must be non-negative")
    _finite_optional_float(row.get("mtime"), field="mtime")
    _required_text(row, "updated_at")
    return record_id


def _validate_promoted_models(
    rows: Sequence[Mapping[str, Any]],
    *,
    profile_keys: set[str],
) -> None:
    seen: set[str] = set()
    for row in rows:
        classifier_key = _required_text(row, "classifier_key")
        if classifier_key not in profile_keys:
            raise ValueError("Promoted model references an unknown profile")
        if classifier_key in seen:
            raise ValueError("Duplicate promoted model")
        seen.add(classifier_key)
        _required_text(row, "feature_set")
        _require_sha256(row.get("manifest_sha256"), field="manifest")
        artifact_sha256 = _optional_validated_sha256(
            row.get("artifact_sha256"),
            field="artifact",
        )
        declared_sha256 = _optional_validated_sha256(
            row.get("declared_artifact_sha256"),
            field="declared artifact",
        )
        if (
            artifact_sha256 is not None
            and declared_sha256 is not None
            and artifact_sha256 != declared_sha256
        ):
            raise ValueError("Promoted artifact hashes disagree")
        if declared_sha256 is not None and artifact_sha256 is None:
            raise ValueError("Declared promoted artifact hash has no artifact hash")
        feature_count = row.get("feature_count")
        if feature_count is not None and (
            isinstance(feature_count, bool)
            or not isinstance(feature_count, int)
            or feature_count < 0
        ):
            raise ValueError("Promoted feature_count must be non-negative")
        feature_names = row.get("feature_names")
        names_source = row.get("feature_names_source")
        if feature_names is None:
            if feature_count not in (None, 0):
                raise ValueError(
                    "Positive feature_count requires ordered feature_names"
                )
            if names_source is not None:
                raise ValueError("feature_names_source requires feature_names")
        else:
            if not isinstance(feature_names, list) or not all(
                isinstance(name, str) and name for name in feature_names
            ):
                raise ValueError("Promoted feature_names must be non-empty strings")
            if len(set(feature_names)) != len(feature_names):
                raise ValueError("Promoted feature_names must be unique")
            if feature_count is None or int(feature_count) != len(feature_names):
                raise ValueError("Promoted feature_count does not match feature_names")
            if names_source not in {"manifest", "promoted_model_artifact"}:
                raise ValueError("Unknown feature_names_source")
            if names_source == "promoted_model_artifact" and (
                artifact_sha256 is None or declared_sha256 is None
            ):
                raise ValueError(
                    "Artifact-derived feature_names require verified artifact hashes"
                )


def _validate_outcome(
    outcome: Mapping[str, Any],
    *,
    catalog_uuid: str,
) -> str:
    status = str(outcome.get("status") or "")
    allowed = {
        "strong_match",
        "weak_match",
        "changed_at_same_path",
        "unmatched",
        "ambiguous",
    }
    if status not in allowed:
        raise ValueError(f"Unsupported rebind status: {status!r}")
    source = _required_mapping(outcome.get("source"), field="outcome.source")
    _validate_manual_label(source)
    target_value = outcome.get("target")
    candidates_value = outcome.get("candidates")
    if status in {"strong_match", "weak_match", "changed_at_same_path"}:
        target = _required_mapping(target_value, field="outcome.target")
        _validate_target(
            target,
            catalog_uuid=catalog_uuid,
            expected_path_key=str(source["canonical_path_key"]),
        )
        calculated_mismatches = _metadata_mismatches(source, target)
        if status == "changed_at_same_path":
            if not calculated_mismatches:
                raise ValueError("Changed-at-same-path outcome has no metadata change")
            if outcome.get("metadata_mismatches") != calculated_mismatches:
                raise ValueError("Metadata mismatch evidence is inconsistent")
        else:
            if calculated_mismatches:
                raise ValueError("Auto-bind outcome contains changed file metadata")
            no_metadata = source.get("size") is None and source.get("mtime") is None
            if status == "weak_match" and not no_metadata:
                raise ValueError("Weak match must have no saved file metadata")
            if status == "strong_match" and no_metadata:
                raise ValueError("Strong match requires saved file metadata")
        if candidates_value not in (None, []):
            raise ValueError("Single-target outcome must not contain candidates")
    elif status == "ambiguous":
        if target_value is not None:
            raise ValueError("Ambiguous outcome must not select a target")
        candidates = _mapping_list(candidates_value, field="candidates")
        if len(candidates) < 2:
            raise ValueError("Ambiguous outcome requires multiple candidates")
        _require_sorted(candidates, field="candidates")
        for candidate in candidates:
            _validate_target(
                candidate,
                catalog_uuid=catalog_uuid,
                expected_path_key=str(source["canonical_path_key"]),
            )
    else:
        if target_value is not None:
            raise ValueError("Unmatched outcome must not select a target")
        if candidates_value != []:
            raise ValueError("Unmatched outcome candidates must be empty")
    return status


def _validate_target(
    target: Mapping[str, Any],
    *,
    catalog_uuid: str,
    expected_path_key: str,
) -> None:
    if _required_text(target, "catalog_uuid") != catalog_uuid:
        raise ValueError("Target catalog identity does not match preview catalog")
    if canonical_path_key(_required_text(target, "file_path")) != expected_path_key:
        raise ValueError("Target path does not match source canonical path")
    track_id = _required_int(target, "track_id")
    generation = _required_int(target, "content_generation")
    if track_id <= 0:
        raise ValueError("Target track_id must be positive")
    if generation <= 0:
        raise ValueError("Target content_generation must be positive")
    _required_text(target, "track_uuid")
    if _required_int(target, "file_size_bytes") < 0:
        raise ValueError("Target file_size_bytes must be non-negative")
    if _required_int(target, "file_modified_ns") < 0:
        raise ValueError("Target file_modified_ns must be non-negative")


def _validate_database_provenance(provenance: Mapping[str, Any]) -> None:
    _require_sha256(
        provenance.get("database_file_sha256"),
        field="database file",
    )
    _require_sha256(provenance.get("schema_sha256"), field="schema")
    _require_sha256(provenance.get("snapshot_sha256"), field="snapshot")
    _optional_validated_sha256(
        provenance.get("wal_file_sha256"),
        field="WAL file",
    )
    if provenance.get("read_mode") != "mode=ro fixed read transaction":
        raise ValueError("Database provenance has an unsupported read mode")
    if not isinstance(provenance.get("user_version"), int):
        raise ValueError("Database provenance user_version must be an integer")
    if not isinstance(provenance.get("schema_object_count"), int):
        raise ValueError("Database provenance schema_object_count must be an integer")
    _required_text(provenance, "journal_mode")


def _mapping_list(value: object, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{field} must be an array of objects")
    return [dict(item) for item in value]


def _required_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def _required_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _required_int(row: Mapping[str, Any], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _unique_text_values(
    rows: Sequence[Mapping[str, Any]],
    *,
    field: str,
    collection: str,
) -> set[str]:
    values = [_required_text(row, field) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"{collection} contains duplicate {field} values")
    return set(values)


def _require_sorted(
    records: Sequence[Mapping[str, Any]],
    *,
    field: str,
) -> None:
    if list(records) != _sort_records(records):
        raise ValueError(f"{field} is not in deterministic canonical order")


def _require_sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        value,
    ):
        raise ValueError(f"{field} SHA-256 is invalid")
    return value


def _optional_validated_sha256(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, field=field)


def _seal_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    clean = deepcopy(dict(payload))
    clean.pop("bundle_sha256", None)
    digest = hashlib.sha256(_canonical_json_bytes(clean)).hexdigest()
    clean["bundle_sha256"] = f"{SHA256_PREFIX}{digest}"
    return _verified_bundle(clean)


def _verified_bundle(
    bundle: Mapping[str, Any],
    *,
    expected_kind: str | None = None,
) -> dict[str, Any]:
    if not isinstance(bundle, Mapping):
        raise ValueError("Bundle root must be a JSON object")
    clean = deepcopy(dict(bundle))
    supplied_hash = clean.pop("bundle_sha256", None)
    if not isinstance(supplied_hash, str) or not supplied_hash.startswith(
        SHA256_PREFIX
    ):
        raise ValueError("Bundle is missing its SHA-256")
    expected_hash = (
        SHA256_PREFIX + hashlib.sha256(_canonical_json_bytes(clean)).hexdigest()
    )
    if supplied_hash != expected_hash:
        raise ValueError("Bundle SHA-256 does not match its payload")
    clean["bundle_sha256"] = supplied_hash
    if clean.get("format_version") != BUNDLE_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported bundle format version: {clean.get('format_version')!r}"
        )
    if expected_kind is not None and clean.get("kind") != expected_kind:
        raise ValueError(
            f"Expected bundle kind {expected_kind!r}, got {clean.get('kind')!r}"
        )
    kind = clean.get("kind")
    if kind == EXPORT_KIND:
        _validate_export_bundle(clean)
    elif kind == PREVIEW_KIND:
        _validate_preview_bundle(clean)
    elif kind == REBOUND_KIND:
        _validate_rebound_bundle(clean)
    else:
        raise ValueError(f"Unsupported bundle kind: {kind!r}")
    return clean


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _summary_output(bundle: Mapping[str, Any], output: Path) -> str:
    summary = bundle.get("summary")
    safe_summary: dict[str, Any] = {
        "bundle_sha256": bundle["bundle_sha256"],
        "kind": bundle["kind"],
        "output": str(output),
    }
    if isinstance(summary, Mapping):
        for key in (
            "manual_label_count",
            "distinct_canonical_path_count",
            "profile_count",
            "promoted_model_count",
            "total",
            "strong_match",
            "weak_match",
            "unmatched",
            "ambiguous",
            "changed_at_same_path",
            "bound",
            "unresolved",
        ):
            if key in summary:
                safe_summary[key] = summary[key]
    return json.dumps(safe_summary, ensure_ascii=False, sort_keys=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export, rebind, and explicitly restore Rhythm Lab manual labels"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--lab-db", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--promoted-models-root", type=Path)
    export_parser.add_argument("--force", action="store_true")

    preview_parser = subparsers.add_parser("preview")
    preview_parser.add_argument("--bundle", type=Path, required=True)
    preview_parser.add_argument("--core-db", type=Path, required=True)
    preview_parser.add_argument("--output", type=Path, required=True)
    preview_parser.add_argument("--force", action="store_true")

    rebound_parser = subparsers.add_parser("rebound")
    rebound_parser.add_argument("--bundle", type=Path, required=True)
    rebound_parser.add_argument("--preview", type=Path, required=True)
    rebound_parser.add_argument("--output", type=Path, required=True)
    rebound_parser.add_argument("--force", action="store_true")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--bundle", type=Path, required=True)
    restore_parser.add_argument("--core-db", type=Path, required=True)
    restore_parser.add_argument("--lab-db", type=Path, required=True)
    restore_parser.add_argument("--report", type=Path, required=True)
    restore_parser.add_argument(
        "--accept-record-id",
        action="append",
        default=[],
        help="Explicitly accept one weak-match record id; repeat as needed.",
    )
    restore_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the restore. Without this flag the command is read-only.",
    )
    restore_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    if args.command == "export":
        promoted_root = args.promoted_models_root or _default_promoted_models_root()
        bundle = export_label_bundle(
            args.lab_db,
            promoted_models_root=promoted_root,
        )
        protected_paths = [
            args.lab_db,
            *promoted_root.glob("*/model.json"),
            *promoted_root.glob("*/model.joblib"),
            *promoted_root.glob(f"*/{CLASSIFIER_PUBLICATION_POINTER_NAME}"),
            *promoted_root.glob("*/generations/*/model.json"),
            *promoted_root.glob("*/generations/*/model.joblib"),
        ]
    elif args.command == "preview":
        bundle = preview_rebind_bundle(
            read_bundle(args.bundle),
            args.core_db,
        )
        protected_paths = [args.bundle, args.core_db]
    elif args.command == "rebound":
        bundle = build_rebound_bundle(
            read_bundle(args.bundle),
            read_bundle(args.preview),
        )
        protected_paths = [args.bundle, args.preview]
    elif args.command == "restore":
        report = restore_label_bundle(
            read_bundle(args.bundle),
            args.lab_db,
            core_db_path=args.core_db,
            apply=bool(args.apply),
            accepted_record_ids=args.accept_record_id,
        )
        output = write_restore_report(
            report,
            args.report,
            force=bool(args.force),
            protected_paths=[args.bundle, args.core_db, args.lab_db],
        )
        print(
            json.dumps(
                {
                    "applied": report["applied"],
                    "output": str(output),
                    **dict(report["summary"]),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    else:  # pragma: no cover - argparse prevents this branch.
        raise AssertionError(f"Unhandled command: {args.command}")
    output = write_bundle(
        bundle,
        args.output,
        force=bool(args.force),
        protected_paths=protected_paths,
    )
    print(_summary_output(bundle, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

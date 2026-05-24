from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path


LEGACY_KEY = "brightness"
TARGET_KEY = "spectral_centroid_mean"


@dataclass(frozen=True)
class MigrationSummary:
    tracks_scanned: int
    tracks_updated: int
    moved: int
    conflicts: int
    skipped_without_sonara: int
    dry_run: bool = True


def migrate_database(db_path: Path, *, apply: bool = False) -> MigrationSummary:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    tracks_scanned = 0
    tracks_updated = 0
    moved = 0
    conflicts = 0
    skipped_without_sonara = 0
    updates: list[tuple[str, int]] = []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT id, metadata_json FROM tracks ORDER BY id").fetchall()
        for row in rows:
            tracks_scanned += 1
            metadata = _metadata_from_json(row["metadata_json"])
            sonara_features = metadata.get("sonara_features")
            if not isinstance(sonara_features, dict):
                skipped_without_sonara += 1
                continue
            if LEGACY_KEY not in sonara_features:
                continue
            if TARGET_KEY in sonara_features:
                conflicts += 1
                continue

            sonara_features[TARGET_KEY] = sonara_features.pop(LEGACY_KEY)
            moved += 1
            tracks_updated += 1
            updates.append((json.dumps(metadata, ensure_ascii=False, sort_keys=False, allow_nan=False), int(row["id"])))

        if updates and apply:
            connection.executemany(
                "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                updates,
            )

    return MigrationSummary(
        tracks_scanned=tracks_scanned,
        tracks_updated=tracks_updated,
        moved=moved,
        conflicts=conflicts,
        skipped_without_sonara=skipped_without_sonara,
        dry_run=not apply,
    )


def _metadata_from_json(value: object) -> dict[str, object]:
    try:
        metadata = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy metadata_json.sonara_features.brightness to "
            "metadata_json.sonara_features.spectral_centroid_mean."
        ),
    )
    parser.add_argument("db", nargs="?", type=Path, help="Path to dj-track-similarity SQLite database.")
    parser.add_argument("--db", dest="db_option", type=Path, help="Path to dj-track-similarity SQLite database.")
    parser.add_argument("--apply", action="store_true", help="Actually update metadata_json. Without this flag, only report counts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = args.db_option or args.db
    if db_path is None:
        raise SystemExit("Database path is required. Pass it as a positional argument or with --db.")
    summary = migrate_database(db_path, apply=args.apply)
    mode = "DRY RUN" if summary.dry_run else "APPLIED"
    print(
        f"{mode}: tracks_scanned={summary.tracks_scanned} tracks_updated={summary.tracks_updated} "
        f"moved={summary.moved} conflicts={summary.conflicts} "
        f"skipped_without_sonara={summary.skipped_without_sonara}"
    )
    if summary.conflicts:
        print(f"Conflicts were left unchanged because {TARGET_KEY} already exists.")
    if summary.dry_run:
        print("Run again with --apply to update these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

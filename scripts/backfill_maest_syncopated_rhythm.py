from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


SYNCOPATED_RHYTHM_GENRES = {
    "breakbeat",
    "breakcore",
    "breaks",
    "progressive breaks",
    "broken beat",
    "drum n bass",
    "jungle",
    "halftime",
    "juke",
    "uk garage",
    "speed garage",
    "bassline",
    "electro",
}


@dataclass(frozen=True)
class BackfillSummary:
    scanned: int
    updated: int
    skipped_without_maest: int
    syncopated_true: int
    syncopated_false: int
    dry_run: bool = True


def backfill_database(db_path: Path, *, apply: bool = False) -> BackfillSummary:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    scanned = 0
    updated = 0
    skipped_without_maest = 0
    syncopated_true = 0
    syncopated_false = 0
    updates: list[tuple[str, int]] = []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT id, metadata_json FROM tracks ORDER BY id").fetchall()
        for row in rows:
            scanned += 1
            metadata = _metadata_from_json(row["metadata_json"])
            raw_genres = metadata.get("maest_genres")
            if not isinstance(raw_genres, list):
                skipped_without_maest += 1
                continue

            flag = _has_syncopated_rhythm(raw_genres)
            if flag:
                syncopated_true += 1
            else:
                syncopated_false += 1

            next_metadata = _with_ordered_maest_fields(metadata, flag)
            next_json = json.dumps(next_metadata, ensure_ascii=False, sort_keys=False, allow_nan=False)
            if next_json != row["metadata_json"]:
                updated += 1
                updates.append((next_json, int(row["id"])))

        if updates and apply:
            connection.executemany(
                "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                updates,
            )

    return BackfillSummary(
        scanned=scanned,
        updated=updated,
        skipped_without_maest=skipped_without_maest,
        syncopated_true=syncopated_true,
        syncopated_false=syncopated_false,
        dry_run=not apply,
    )


def _metadata_from_json(value: object) -> dict[str, object]:
    try:
        metadata = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _with_ordered_maest_fields(metadata: dict[str, object], syncopated: bool) -> dict[str, object]:
    maest_model = metadata.get("maest_model")
    maest_genres = metadata.get("maest_genres")
    next_metadata = dict(metadata)
    for key in ("maest_model", "maest_genres", "maest_syncopated_rhythm"):
        next_metadata.pop(key, None)
    next_metadata["maest_model"] = maest_model
    next_metadata["maest_genres"] = maest_genres
    next_metadata["maest_syncopated_rhythm"] = syncopated
    return next_metadata


def _has_syncopated_rhythm(genres: list[object]) -> bool:
    for item in genres:
        if not isinstance(item, dict):
            continue
        label = _clean_maest_genre_label(item.get("label"))
        if label and label.lower() in SYNCOPATED_RHYTHM_GENRES:
            return True
    return False


def _clean_maest_genre_label(label: object) -> str | None:
    if label is None:
        return None
    text = str(label).replace("_", " ").strip()
    if "---" in text:
        text = text.rsplit("---", 1)[-1].strip()
    return text or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill metadata_json.maest_syncopated_rhythm for existing dj-track-similarity SQLite databases.",
    )
    parser.add_argument("db", type=Path, help="Path to dj-track-similarity SQLite database.")
    parser.add_argument("--apply", action="store_true", help="Actually update metadata_json. Without this flag, only report counts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = backfill_database(args.db, apply=args.apply)
    mode = "DRY RUN" if summary.dry_run else "APPLIED"
    print(
        f"{mode}: scanned={summary.scanned} updated={summary.updated} "
        f"skipped_without_maest={summary.skipped_without_maest} "
        f"syncopated_true={summary.syncopated_true} syncopated_false={summary.syncopated_false}"
    )
    if summary.dry_run:
        print("Run again with --apply to update these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

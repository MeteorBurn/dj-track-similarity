from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path


@dataclass(frozen=True)
class StripSonaraDescriptionsSummary:
    tracks_scanned: int
    tracks_updated: int
    descriptions_removed: int
    chord_sequences_removed: int
    dry_run: bool = True


def strip_sonara_descriptions(db_path: Path, *, apply: bool = False) -> StripSonaraDescriptionsSummary:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    tracks_scanned = 0
    tracks_updated = 0
    descriptions_removed = 0
    chord_sequences_removed = 0
    updates: list[tuple[str, int]] = []

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT id, metadata_json FROM tracks ORDER BY id").fetchall()
        for row in rows:
            tracks_scanned += 1
            metadata = _metadata_from_json(row["metadata_json"])
            sonara_features = metadata.get("sonara_features")
            if not isinstance(sonara_features, dict):
                continue

            descriptions_for_track = _strip_descriptions(sonara_features)
            chord_sequences_for_track = _strip_chord_sequence(sonara_features)
            if not descriptions_for_track and not chord_sequences_for_track:
                continue

            descriptions_removed += descriptions_for_track
            chord_sequences_removed += chord_sequences_for_track
            tracks_updated += 1
            updates.append((json.dumps(metadata, ensure_ascii=False, sort_keys=False, allow_nan=False), int(row["id"])))

        if updates and apply:
            connection.executemany(
                "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                updates,
            )

    return StripSonaraDescriptionsSummary(
        tracks_scanned=tracks_scanned,
        tracks_updated=tracks_updated,
        descriptions_removed=descriptions_removed,
        chord_sequences_removed=chord_sequences_removed,
        dry_run=not apply,
    )


def _metadata_from_json(value: object) -> dict[str, object]:
    try:
        metadata = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _strip_descriptions(sonara_features: dict[object, object]) -> int:
    removed = 0
    for payload in sonara_features.values():
        if isinstance(payload, dict) and "description" in payload:
            payload.pop("description", None)
            removed += 1
    return removed


def _strip_chord_sequence(sonara_features: dict[object, object]) -> int:
    if "chord_sequence" not in sonara_features:
        return 0
    sonara_features.pop("chord_sequence", None)
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove repeated Sonara feature description fields and full chord_sequence payloads from a dj-track-similarity SQLite database.",
    )
    parser.add_argument("db", type=Path, help="Path to dj-track-similarity SQLite database.")
    parser.add_argument("--apply", action="store_true", help="Actually update metadata_json. Without this flag, only report counts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = strip_sonara_descriptions(args.db, apply=args.apply)
    mode = "DRY RUN" if summary.dry_run else "APPLIED"
    print(
        f"{mode}: tracks_scanned={summary.tracks_scanned} tracks_updated={summary.tracks_updated} "
        f"descriptions_removed={summary.descriptions_removed} "
        f"chord_sequences_removed={summary.chord_sequences_removed}"
    )
    if summary.dry_run:
        print("Run again with --apply to update these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from dj_track_similarity.metadata_payload import metadata_from_json

from .lab_db import RhythmLabDatabase


@dataclass(frozen=True)
class ImportSummary:
    source_db: Path
    lab_db: Path
    scanned: int
    imported: int


def import_syncopated_subset(source_db: str | Path, lab_db: str | Path) -> ImportSummary:
    source_path = Path(source_db).expanduser().resolve(strict=False)
    if not source_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {source_path}")

    lab = RhythmLabDatabase(lab_db)
    with _read_only_connection(source_path) as source:
        source.row_factory = sqlite3.Row
        scanned = int(source.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
        rows = source.execute(
            """
            SELECT id, path, size, mtime, artist, title, album, bpm, musical_key,
                   energy, duration, metadata_json
            FROM tracks
            WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1
            ORDER BY id
            """
        ).fetchall()

    imported = _import_rows(lab, rows)

    return ImportSummary(source_path, lab.path, scanned, imported)


def import_non_sync_sample(source_db: str | Path, lab_db: str | Path, *, count: int = 944) -> ImportSummary:
    if count < 1:
        raise ValueError("count must be greater than zero")
    source_path = Path(source_db).expanduser().resolve(strict=False)
    if not source_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {source_path}")

    lab = RhythmLabDatabase(lab_db)
    existing_source_ids = lab.source_track_ids()
    selected_rows: list[sqlite3.Row] = []
    with _read_only_connection(source_path) as source:
        source.row_factory = sqlite3.Row
        scanned = int(source.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
        rows = source.execute(
            """
            SELECT id, path, size, mtime, artist, title, album, bpm, musical_key,
                   energy, duration, metadata_json
            FROM tracks
            WHERE COALESCE(json_extract(metadata_json, '$.maest_syncopated_rhythm'), 0) != 1
            ORDER BY random()
            """
        )
        for row in rows:
            if int(row["id"]) in existing_source_ids:
                continue
            selected_rows.append(row)
            if len(selected_rows) >= count:
                break

    imported = _import_rows(lab, selected_rows)
    return ImportSummary(source_path, lab.path, scanned, imported)


def _import_rows(lab: RhythmLabDatabase, rows: list[sqlite3.Row]) -> int:
    imported = 0
    for row in rows:
        metadata = metadata_from_json(row["metadata_json"])
        track_id = lab.library.upsert_track(
            path=str(row["path"]),
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            metadata=metadata,
            bpm=row["bpm"],
            musical_key=row["musical_key"],
            energy=row["energy"],
            duration=row["duration"],
        )
        lab.record_source_track(track_id, int(row["id"]))
        imported += 1
    return imported


def _read_only_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)

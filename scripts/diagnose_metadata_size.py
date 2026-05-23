from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import json
import sqlite3
from pathlib import Path


@dataclass(frozen=True)
class SizeStat:
    bytes: int = 0
    count: int = 0


@dataclass(frozen=True)
class RowSize:
    track_id: int
    bytes: int
    path: str


@dataclass(frozen=True)
class MetadataSizeReport:
    track_count: int
    metadata_total_bytes: int
    metadata_average_bytes: float
    metadata_max_bytes: int
    top_level: dict[str, SizeStat] = field(default_factory=dict)
    sonara_features: dict[str, SizeStat] = field(default_factory=dict)
    sonara_payload_fields: dict[str, SizeStat] = field(default_factory=dict)
    largest_rows: list[RowSize] = field(default_factory=list)


def diagnose_database(db_path: Path, *, top: int = 20) -> MetadataSizeReport:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {db_path}")

    top_level: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sonara_features: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sonara_payload_fields: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    largest_rows: list[RowSize] = []
    track_count = 0
    metadata_total_bytes = 0
    metadata_max_bytes = 0

    uri = "file:" + db_path.as_posix() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT id, path, metadata_json FROM tracks ORDER BY id")
        for row in rows:
            track_count += 1
            metadata_json = str(row["metadata_json"] or "{}")
            row_bytes = len(metadata_json.encode("utf-8"))
            metadata_total_bytes += row_bytes
            metadata_max_bytes = max(metadata_max_bytes, row_bytes)
            largest_rows.append(RowSize(track_id=int(row["id"]), bytes=row_bytes, path=str(row["path"])))

            metadata = _metadata_from_json(metadata_json)
            for key, value in metadata.items():
                _add_size(top_level, key, value)

            raw_sonara = metadata.get("sonara_features")
            if isinstance(raw_sonara, dict):
                for key, value in raw_sonara.items():
                    _add_size(sonara_features, str(key), value)
                    if isinstance(value, dict):
                        for payload_key, payload_value in value.items():
                            _add_size(sonara_payload_fields, str(payload_key), payload_value)

    average = metadata_total_bytes / track_count if track_count else 0.0
    return MetadataSizeReport(
        track_count=track_count,
        metadata_total_bytes=metadata_total_bytes,
        metadata_average_bytes=average,
        metadata_max_bytes=metadata_max_bytes,
        top_level=_finalize_stats(top_level, top),
        sonara_features=_finalize_stats(sonara_features, top),
        sonara_payload_fields=_finalize_stats(sonara_payload_fields, top),
        largest_rows=sorted(largest_rows, key=lambda item: item.bytes, reverse=True)[:top],
    )


def _metadata_from_json(value: str) -> dict[str, object]:
    try:
        metadata = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _add_size(target: dict[str, list[int]], key: str, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    target[key][0] += len(encoded)
    target[key][1] += 1


def _finalize_stats(values: dict[str, list[int]], top: int) -> dict[str, SizeStat]:
    rows = sorted(values.items(), key=lambda item: item[1][0], reverse=True)[:top]
    return {key: SizeStat(bytes=stats[0], count=stats[1]) for key, stats in rows}


def _format_bytes(value: int | float) -> str:
    units = ("B", "KB", "MB", "GB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _print_stats(title: str, stats: dict[str, SizeStat]) -> None:
    print(title)
    if not stats:
        print("  none")
        return
    for key, stat in stats.items():
        print(f"  {key}: {_format_bytes(stat.bytes)} across {stat.count} rows")


def print_report(report: MetadataSizeReport) -> None:
    print(f"tracks={report.track_count}")
    print(f"metadata_total={_format_bytes(report.metadata_total_bytes)}")
    print(f"metadata_average={_format_bytes(report.metadata_average_bytes)}")
    print(f"metadata_max={_format_bytes(report.metadata_max_bytes)}")
    _print_stats("top_level_keys", report.top_level)
    _print_stats("sonara_features", report.sonara_features)
    _print_stats("sonara_payload_fields", report.sonara_payload_fields)
    print("largest_metadata_rows")
    for row in report.largest_rows:
        print(f"  track_id={row.track_id} bytes={_format_bytes(row.bytes)} path={row.path.encode('unicode_escape').decode('ascii')}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only metadata_json size diagnostics for a dj-track-similarity SQLite database.")
    parser.add_argument("db", type=Path, help="Path to dj-track-similarity SQLite database.")
    parser.add_argument("--top", type=int, default=20, help="Number of largest keys/features/rows to print.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print_report(diagnose_database(args.db, top=max(1, args.top)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

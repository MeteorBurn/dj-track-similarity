"""Source-preserving intermediate report contract."""

from __future__ import annotations

from collections.abc import Sequence
import json
import os
from pathlib import Path
import subprocess

from .models import LocalEvidence, SourceResult, TrackInput
from .workbook_format import format_workbook
BASE_FIELDS = ("Title", "Artist", "Album", "Year", "Country", "Label", "Tags")


def build_report_contract(
    tracks: Sequence[tuple[TrackInput, LocalEvidence, Sequence[SourceResult]]], source_names: Sequence[str]
) -> dict[str, object]:
    """Build one flat, source-preserving data row per track."""

    columns = [
        "Track Name",
        "Genres",
        "MAEST Genres",
        *(_column(source, "Genres") for source in source_names),
        *BASE_FIELDS,
        *(_column(source, field) for source in source_names for field in BASE_FIELDS),
    ]
    rows: list[dict[str, str]] = []
    for track, local, results in tracks:
        by_name = {result.name: result for result in results}
        local_values = {"Track Name": _track_name(track.artist, track.title), "Title": _clean(track.title), "Artist": _clean(track.artist), "Album": _clean(track.album), "Year": str(track.year or ""), "Country": _clean(track.country), "Label": _clean(track.label), "Genres": _join(local.file_tags), "Tags": ""}
        row = {column: "" for column in columns}
        row["Track Name"] = local_values["Track Name"]
        row["Genres"] = local_values["Genres"]
        row["MAEST Genres"] = _maest(local.maest)
        for field in BASE_FIELDS:
            row[field] = local_values[field]
        for name in source_names:
            result = by_name.get(name)
            if result is None or result.record is None: continue
            record = result.record
            values = {"Title": _clean(record.title), "Artist": _clean(record.artist), "Album": _clean(record.album), "Year": str(record.year or ""), "Country": _clean(record.country), "Label": _clean(record.label), "Tags": _join(record.tags)}
            row[_column(name, "Genres")] = _join(record.genres)
            for field, value in values.items():
                row[_column(name, field)] = value
        rows.append(row)
    return {"sheet": "Metadata", "columns": columns, "rows": rows}


def _join(values: Sequence[str]) -> str: return "; ".join(_clean(value) for value in values[:3] if _clean(value))
def _maest(values: Sequence[tuple[str, float]]) -> str: return "; ".join(f"{_clean(label.rsplit('---', 1)[-1])} ({score:.0%})" for label, score in values[:3] if _clean(label))
def _column(source: str, field: str) -> str: return f"{source} {field}"
def _clean(value: str | None) -> str: return " ".join(value.split()) if value else ""
def _track_name(artist: str | None, title: str | None) -> str:
    artist, title = _clean(artist), _clean(title)
    return f"{artist} — {title}" if artist and title else title or artist


def write_workbook(
    contract: dict[str, object], output_path: Path, *, node_executable: Path, node_modules: Path | None = None
) -> None:
    """Run the tool-local artifact bridge with a non-secret contract file."""
    contract_path = output_path.with_suffix(".contract.json")
    contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    try:
        bridge = Path(__file__).resolve().parents[1] / "workbook_bridge.mjs"
        environment = dict(os.environ)
        if node_modules:
            environment["METADATA_ENRICHMENT_NODE_MODULES"] = str(node_modules)
        subprocess.run([str(node_executable), str(bridge), "write", str(contract_path), str(output_path)], check=True, env=environment)
        format_workbook(output_path)
    finally:
        contract_path.unlink(missing_ok=True)

"""Source-preserving intermediate report contract."""

from __future__ import annotations

from collections.abc import Sequence
import json
import os
from pathlib import Path
import subprocess

from .models import LocalEvidence, SourceResult, TrackInput
PRIMARY_FIELDS = ("Track Name", "Title", "Artist", "Album", "Year", "Country", "Label", "Genre", "Style", "Tags", "Duration")


def build_report_contract(
    tracks: Sequence[tuple[TrackInput, LocalEvidence, Sequence[SourceResult]]], source_names: Sequence[str]
) -> dict[str, object]:
    """Build serializable workbook data without merging service evidence."""

    columns = ["Field", "Local tags", *source_names, "MAEST"]
    blocks: list[dict[str, object]] = []
    for track, local, results in tracks:
        by_name = {result.name: result for result in results}
        rows = {field: {column: "" for column in columns[1:]} for field in PRIMARY_FIELDS}
        local_values = {"Track Name": track.track_name, "Title": track.title or "", "Artist": track.artist or "", "Album": track.album or "", "Year": str(track.year or ""), "Country": track.country or "", "Label": track.label or "", "Genre": _join(local.file_tags), "Duration": _duration(track.duration_seconds)}
        for field, value in local_values.items(): rows[field]["Local tags"] = value
        rows["Genre"]["MAEST"] = _maest(local.maest)
        for name in source_names:
            result = by_name.get(name)
            if result is None or result.record is None: continue
            record = result.record
            values = {"Track Name": _track_name(record.artist, record.title), "Title": record.title or "", "Artist": record.artist or "", "Album": record.album or "", "Year": str(record.year or ""), "Country": record.country or "", "Label": record.label or "", "Genre": _join(record.genres), "Style": _join(record.styles), "Tags": _join(record.tags), "Duration": _duration(record.duration_seconds)}
            for field, value in values.items(): rows[field][name] = value
        blocks.append({"track_name": track.track_name, "rows": rows})
    return {"sheet": "Metadata", "columns": columns, "primary_fields": list(PRIMARY_FIELDS), "tracks": blocks}


def _join(values: Sequence[str]) -> str: return "; ".join(values)
def _maest(values: Sequence[tuple[str, float]]) -> str: return "; ".join(f"{label} ({score:.0%})" for label, score in values[:3])
def _track_name(artist: str | None, title: str | None) -> str: return f"{artist} — {title}" if artist and title else title or artist or ""
def _duration(value: float | None) -> str:
    if value is None: return ""
    seconds = round(value); return f"{seconds // 60:02d}:{seconds % 60:02d}"


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
    finally:
        contract_path.unlink(missing_ok=True)

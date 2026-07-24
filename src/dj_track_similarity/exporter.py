"""Playlist export for typed v7 library rows."""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from pathlib import Path

from .library_models import ExportTrackRow


def export_tracks(
    name: str,
    tracks: Sequence[ExportTrackRow],
    output_dir: str | Path,
    format: str,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(name)

    if format == "m3u":
        path = output_path / f"{safe_name}.m3u"
        _write_m3u(path, tracks)
        return path
    if format == "csv":
        path = output_path / f"{safe_name}.csv"
        _write_csv(path, tracks)
        return path
    raise ValueError("format must be 'm3u' or 'csv'")


def _write_m3u(path: Path, tracks: Sequence[ExportTrackRow]) -> None:
    lines = ["#EXTM3U"]
    for track in tracks:
        lines.append(f"#EXTINF:-1,{track.display_name}")
        lines.append(track.file_path)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, tracks: Sequence[ExportTrackRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "artist",
                "title",
                "album",
                "tag_bpm",
                "tag_key",
                "sonara_bpm",
                "sonara_key",
                "sonara_energy",
                "file_path",
            ]
        )
        for track in tracks:
            writer.writerow(
                [
                    track.artist or "",
                    track.title or "",
                    track.album or "",
                    track.tag_bpm if track.tag_bpm is not None else "",
                    track.tag_key or "",
                    track.sonara_bpm
                    if track.sonara_bpm is not None
                    else "",
                    track.sonara_key or "",
                    track.sonara_energy
                    if track.sonara_energy is not None
                    else "",
                    track.file_path,
                ]
            )


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe.strip("_") or "playlist"

from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import Track


def export_tracks(name: str, tracks: list[Track], output_dir: str | Path, format: str) -> Path:
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


def _write_m3u(path: Path, tracks: list[Track]) -> None:
    lines = ["#EXTM3U"]
    for track in tracks:
        display = _display_name(track)
        lines.append(f"#EXTINF:-1,{display}")
        lines.append(track.path)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, tracks: list[Track]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["artist", "title", "bpm", "key", "energy", "path"])
        for track in tracks:
            writer.writerow(
                [
                    track.artist or "",
                    track.title or "",
                    track.bpm if track.bpm is not None else "",
                    track.musical_key or "",
                    track.energy if track.energy is not None else "",
                    track.path,
                ]
            )


def _display_name(track: Track) -> str:
    if track.artist and track.title:
        return f"{track.artist} - {track.title}"
    return track.title or Path(track.path).stem


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe.strip("_") or "playlist"

"""Input normalization without external requests."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile

from mutagen import File as MutagenFile

from .models import TrackInput


AUDIO_SUFFIXES = {".mp3", ".flac", ".m4a", ".aiff", ".aif", ".wav", ".ogg"}


def load_tracks(path: Path, *, node_executable: Path | None = None, node_modules: Path | None = None) -> list[TrackInput]:
    """Read supported track lists and local metadata without external requests."""

    suffix = path.suffix.lower()
    if path.is_dir():
        return _load_directory(path)
    if path.is_file() and suffix in AUDIO_SUFFIXES:
        return [_load_audio_file(path)]
    if suffix == ".csv":
        return _load_csv(path)
    if suffix == ".xlsx":
        return _load_xlsx(path, node_executable=node_executable, node_modules=node_modules)
    if suffix in {".m3u", ".m3u8"}:
        return _load_m3u(path)
    if suffix != ".txt":
        raise ValueError(f"unsupported input format: {path.suffix or '<none>'}")
    tracks: list[TrackInput] = []
    for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        artist, title = _split_track_line(line)
        if not artist or not title:
            raise ValueError(f"line {number} must contain Artist - Title")
        tracks.append(TrackInput(artist=artist, title=title))
    return tracks


def _split_track_line(line: str) -> tuple[str, str]:
    for delimiter in (" — ", " - "):
        if delimiter in line:
            artist, title = line.split(delimiter, maxsplit=1)
            return artist.strip(), title.strip()
    return "", ""


def _load_csv(path: Path) -> list[TrackInput]:
    with path.open("r", encoding="utf-8-sig", newline="") as input_file:
        rows = csv.DictReader(input_file)
        tracks: list[TrackInput] = []
        for row in rows:
            values = {(key or "").strip().casefold(): (value or "").strip() for key, value in row.items()}
            year = values.get("year")
            tracks.append(TrackInput(
                artist=values.get("artist") or None, title=values.get("title") or None,
                album=values.get("album") or None, country=values.get("country") or None,
                label=values.get("label") or None, year=int(year) if year and year.isdigit() else None,
            ))
    return tracks


def _load_m3u(path: Path) -> list[TrackInput]:
    tracks: list[TrackInput] = []
    pending_name = ""
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("#EXTINF:"):
            _, _, pending_name = line[8:].partition(",")
            pending_name = pending_name.strip()
        elif line and not line.startswith("#"):
            artist, title = _split_track_line(pending_name)
            tracks.append(TrackInput(artist=artist or None, title=title or pending_name or None, file_path=Path(line)))
            pending_name = ""
    return tracks


def _load_directory(path: Path) -> list[TrackInput]:
    return [_load_audio_file(audio_path) for audio_path in sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES)]


def _load_audio_file(audio_path: Path) -> TrackInput:
    try:
        metadata = MutagenFile(audio_path, easy=True)
    except Exception:
        metadata = None
    tags = metadata.tags if metadata and metadata.tags else {}
    def value(name: str):
        return tags.get(name, [None])[0] if isinstance(tags.get(name), list) else None

    fallback_artist, fallback_title = _split_track_line(audio_path.stem)
    tagged_artist, tagged_title = value("artist"), value("title")
    title = tagged_title or fallback_title or audio_path.stem
    if tagged_artist and tagged_title and fallback_title and tagged_title.casefold() == f"{tagged_artist} - {fallback_title}".casefold():
        title = fallback_title
    return TrackInput(
        title=title,
        artist=tagged_artist or fallback_artist or None,
        album=value("album"),
        file_path=audio_path,
    )


def _load_xlsx(path: Path, *, node_executable: Path | None, node_modules: Path | None) -> list[TrackInput]:
    if node_executable is None or node_modules is None:
        raise ValueError("XLSX input requires --node-executable and --node-modules")
    descriptor, temp_name = tempfile.mkstemp(prefix="audio-online-rows-", suffix=".json")
    os.close(descriptor)
    rows_path = Path(temp_name)
    try:
        bridge = Path(__file__).resolve().parents[1] / "workbook_bridge.mjs"
        environment = {**os.environ, "METADATA_ENRICHMENT_NODE_MODULES": str(node_modules)}
        subprocess.run([str(node_executable), str(bridge), "read", str(path), str(rows_path)], check=True, env=environment)
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
    finally:
        rows_path.unlink(missing_ok=True)
    tracks: list[TrackInput] = []
    for row in rows:
        values = {str(key).strip().casefold(): str(value).strip() for key, value in row.items()}
        year = values.get("year")
        tracks.append(TrackInput(artist=values.get("artist") or None, title=values.get("title") or None, album=values.get("album") or None, country=values.get("country") or None, label=values.get("label") or None, year=int(year) if year and year.isdigit() else None))
    return tracks

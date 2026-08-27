from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable, Iterable

from .spectral import LOSSY_EXTENSIONS, SpectralResult, analyze_file, skipped_result


LOSSLESS_EXTENSIONS = (
    ".flac",
    ".wav",
    ".wave",
    ".aif",
    ".aiff",
    ".aifc",
    ".alac",
    ".m4a",
    ".mp4",
)
AUDIO_EXTENSIONS = LOSSLESS_EXTENSIONS + LOSSY_EXTENSIONS
PROBE_TIMEOUT_SECONDS = 30


def main(argv: list[str] | None = None) -> int:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        files = collect_files(args.targets, args.list)
    except (OSError, ValueError) as error:
        print(f"spectral_check failed: {error}", file=sys.stderr)
        return 2
    if not files:
        print("spectral_check failed: no audio files to analyze", file=sys.stderr)
        return 2
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print(
            "spectral_check failed: ffmpeg and ffprobe must be on PATH",
            file=sys.stderr,
        )
        return 2
    rows = run_checks(files)
    write_output(rows, csv_path=args.csv)
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone fake-bitrate check: estimate each file's spectral cutoff with the "
            "Audio Dedup detector and flag suspected transcodes. Reads audio only; never "
            "writes or modifies files."
        )
    )
    parser.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="Audio files and/or directories (directories are scanned recursively).",
    )
    parser.add_argument(
        "--list",
        type=Path,
        help="Text file with one path per line; surrounding quotes are ignored.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Also write every verdict to this CSV file.",
    )
    return parser.parse_args(argv)


def collect_files(targets: Iterable[Path], list_file: Path | None) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()

    def add(candidate: Path) -> None:
        key = str(candidate).replace("\\", "/").casefold()
        if key not in seen:
            seen.add(key)
            files.append(candidate)

    for target in targets:
        if target.is_dir():
            for found in sorted(target.rglob("*")):
                if found.is_file() and found.suffix.casefold() in AUDIO_EXTENSIONS:
                    add(found)
        elif target.is_file():
            add(target)
        else:
            raise ValueError(f"target does not exist: {target}")
    if list_file is not None:
        for line in list_file.read_text(encoding="utf-8-sig").splitlines():
            text = line.strip().strip('"').strip("'").strip()
            if text:
                add(Path(text))
    return files


def run_checks(
    files: list[Path],
    *,
    analyzer: Callable[..., SpectralResult] | None = None,
    prober: Callable[[Path], tuple[int | None, float | None, int | None]] | None = None,
    progress_stream=None,
) -> list[dict[str, object]]:
    selected_analyzer = analyzer or analyze_file
    selected_prober = prober or probe_audio_facts
    stream = progress_stream if progress_stream is not None else sys.stdout
    rows: list[dict[str, object]] = []
    started = time.perf_counter()
    for index, path in enumerate(files, start=1):
        if not path.is_file():
            result = skipped_result("file not reachable")
        else:
            sample_rate, duration_seconds, bit_rate = selected_prober(path)
            result = selected_analyzer(
                str(path),
                sample_rate=sample_rate,
                duration_seconds=duration_seconds,
                declared_bitrate_bps=bit_rate,
            )
        if result.cutoff_hz is None:
            verdict = "skipped"
        elif result.suspected_transcode:
            verdict = "suspected_transcode"
        else:
            verdict = "clean"
        rows.append(
            {
                "path": str(path),
                "verdict": verdict,
                "cutoff_hz": result.cutoff_hz,
                "sharpness_db": result.sharpness_db,
                "sample_rate": result.sample_rate,
                "note": result.note,
            }
        )
        if index % 25 == 0 or index == len(files):
            elapsed = time.perf_counter() - started
            print(
                f"  {index}/{len(files)} analyzed ({elapsed:.0f}s)",
                file=stream,
                flush=True,
            )
    return rows


def write_output(rows: list[dict[str, object]], *, csv_path: Path | None) -> None:
    suspects = [row for row in rows if row["verdict"] == "suspected_transcode"]
    skipped = [row for row in rows if row["verdict"] == "skipped"]
    print(
        f"analyzed: {len(rows) - len(skipped)}  suspected transcodes: {len(suspects)}  "
        f"skipped: {len(skipped)}",
        flush=True,
    )
    for row in suspects:
        print(f"  {row['note']} | {row['path']}", flush=True)
    for row in skipped:
        print(f"  SKIPPED ({row['note']}): {row['path']}", flush=True)
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "path",
                    "verdict",
                    "cutoff_hz",
                    "sharpness_db",
                    "sample_rate",
                    "note",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"csv={csv_path.resolve()}", flush=True)


def probe_audio_facts(path: Path) -> tuple[int | None, float | None, int | None]:
    """Read sample rate, duration, and declared bitrate from the file itself."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,duration,bit_rate:format=duration,bit_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=True,
        )
        payload = json.loads(completed.stdout.decode("utf-8", errors="replace"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, None, None
    streams = payload.get("streams") or [{}]
    stream = streams[0] if isinstance(streams[0], dict) else {}
    container = payload.get("format") or {}
    sample_rate = _int_or_none(stream.get("sample_rate"))
    duration = _float_or_none(stream.get("duration")) or _float_or_none(
        container.get("duration")
    )
    bit_rate = _int_or_none(stream.get("bit_rate")) or _int_or_none(
        container.get("bit_rate")
    )
    return sample_rate, duration, bit_rate


def _int_or_none(value: object) -> int | None:
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_or_none(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

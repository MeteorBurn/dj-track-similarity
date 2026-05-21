from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path


READBACK_FAILURE = "Genre tag was not readable after WAV save:"
ID3_CHUNK_IDS = {b"id3 ", b"ID3 "}


class RepairError(Exception):
    pass


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: bytes
    payload: bytes
    source_start: int
    source_end: int
    note: str | None = None


@dataclass
class ByteRepairResult:
    changed: bool
    data: bytes
    actions: list[str] = field(default_factory=list)
    id3_seen: int = 0
    id3_removed: int = 0
    original_size: int = 0
    repaired_size: int = 0
    mutagen_summary: str | None = None


@dataclass
class FileRepairResult:
    path: Path
    status: str
    message: str
    actions: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    original_size: int = 0
    repaired_size: int = 0
    id3_seen: int = 0
    id3_removed: int = 0
    mutagen_summary: str | None = None


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    paths = collect_paths(args.logs, args.paths, since=args.since, until=args.until)
    if args.limit is not None:
        paths = paths[: args.limit]
    if not paths:
        print("No WAV paths found. Pass paths or --log with readback failures.", file=sys.stderr)
        return 2

    keep_id3 = args.keep_id3
    apply_changes = args.apply
    if apply_changes and args.backup_dir and args.no_backup:
        print("--backup-dir and --no-backup cannot be used together.", file=sys.stderr)
        return 2

    results: list[FileRepairResult] = []
    for path in paths:
        result = repair_file(
            path,
            apply_changes=apply_changes,
            backup_dir=args.backup_dir,
            no_backup=args.no_backup,
            keep_id3=keep_id3,
        )
        results.append(result)
        if not args.summary_only:
            print(format_result(result, dry_run=not apply_changes))

    failed = sum(1 for result in results if result.status == "failed")
    changed = sum(1 for result in results if result.status == "repaired")
    repairable = sum(1 for result in results if result.status == "repairable")
    unchanged = sum(1 for result in results if result.status == "unchanged")
    print(
        "Summary: "
        f"total={len(results)} repaired={changed} repairable={repairable} "
        f"unchanged={unchanged} failed={failed}"
    )
    return 1 if failed else 0


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair WAV files left with unreadable Mutagen ID3 chunks after "
            "'Genre tag was not readable after WAV save' failures."
        )
    )
    parser.add_argument("paths", nargs="*", type=Path, help="WAV files to inspect or repair.")
    parser.add_argument(
        "--log",
        dest="logs",
        action="append",
        type=Path,
        default=[],
        help="Project log file. Only readback-failed WAV paths are extracted.",
    )
    parser.add_argument(
        "--since",
        help="Only use log lines at or after this timestamp, for example: 2026-05-21 20:26.",
    )
    parser.add_argument(
        "--until",
        help="Only use log lines before this timestamp, for example: 2026-05-21 20:36.",
    )
    parser.add_argument("--apply", action="store_true", help="Write repaired files. Default is dry-run.")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directory for full-file backups. Defaults to a sidecar .bak next to each WAV.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Apply without making full-file backups. Use only after a separate backup exists.",
    )
    parser.add_argument(
        "--keep-id3",
        choices=("first", "last", "none"),
        default="first",
        help="Which readable top-level ID3 chunk to keep after repair. Default: first.",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N collected paths.")
    parser.add_argument("--summary-only", action="store_true", help="Print only the final summary.")
    return parser.parse_args(argv)


def collect_paths(logs: list[Path], paths: list[Path], *, since: str | None, until: str | None) -> list[Path]:
    collected: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        add_path(collected, seen, path)
    for log_path in logs:
        for path in paths_from_log(log_path, since=since, until=until):
            add_path(collected, seen, path)
    return collected


def add_path(collected: list[Path], seen: set[str], path: Path) -> None:
    key = os.path.normcase(str(path))
    if key not in seen:
        seen.add(key)
        collected.append(path)


def paths_from_log(log_path: Path, *, since: str | None = None, until: str | None = None) -> list[Path]:
    if not log_path.exists():
        raise RepairError(f"Log file does not exist: {log_path}")
    paths: list[Path] = []
    pattern = re.compile(r"path=(.*?) error=" + re.escape(READBACK_FAILURE))
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line_in_time_range(line, since=since, until=until):
                continue
            if "Genre tag apply failed" not in line or READBACK_FAILURE not in line:
                continue
            match = pattern.search(line)
            if match:
                paths.append(Path(match.group(1)))
    return paths


def line_in_time_range(line: str, *, since: str | None, until: str | None) -> bool:
    if since is None and until is None:
        return True
    timestamp = line[:16]
    if since is not None and timestamp < since[:16]:
        return False
    if until is not None and timestamp >= until[:16]:
        return False
    return True


def repair_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> FileRepairResult:
    try:
        data = path.read_bytes()
        original_payload_hash = data_payload_hash(data)
        repaired = repair_wave_bytes(data, keep_id3=keep_id3)
        repaired_payload_hash = data_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            raise RepairError("audio data payload would change; refusing to write")

        status = "unchanged"
        backup_path = None
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                write_repaired_file(path, repaired.data)
                verify_repaired_file(path)
                status = "repaired"

        return FileRepairResult(
            path=path,
            status=status,
            message="ok",
            actions=repaired.actions,
            backup_path=backup_path,
            original_size=repaired.original_size,
            repaired_size=repaired.repaired_size,
            id3_seen=repaired.id3_seen,
            id3_removed=repaired.id3_removed,
            mutagen_summary=repaired.mutagen_summary,
        )
    except Exception as error:
        return FileRepairResult(path=path, status="failed", message=str(error))


def repair_wave_bytes(data: bytes, *, keep_id3: str = "first") -> ByteRepairResult:
    if keep_id3 not in {"first", "last", "none"}:
        raise RepairError(f"Unsupported keep-id3 mode: {keep_id3}")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RepairError("not a RIFF/WAVE file")

    chunks, actions = parse_chunks_for_repair(data)
    id3_indices = [index for index, chunk in enumerate(chunks) if is_id3_chunk(chunk)]
    keep_index: int | None = None
    if keep_id3 == "first" and id3_indices:
        keep_index = id3_indices[0]
    elif keep_id3 == "last" and id3_indices:
        keep_index = id3_indices[-1]

    rebuilt = bytearray(b"RIFF\x00\x00\x00\x00WAVE")
    id3_removed = 0
    for index, chunk in enumerate(chunks):
        if is_id3_chunk(chunk):
            if keep_index is None or index != keep_index or not chunk.payload.startswith(b"ID3"):
                id3_removed += 1
                actions.append(
                    f"removed ID3 chunk at offset {chunk.source_start} size {len(chunk.payload)}"
                )
                continue

        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "little"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "little")
    repaired = bytes(rebuilt)
    changed = repaired != data
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        actions.append("normalized RIFF root size")
    if id3_removed:
        actions.append(f"removed duplicate/unselected ID3 chunks: {id3_removed}")

    return ByteRepairResult(
        changed=changed,
        data=repaired,
        actions=dedupe(actions),
        id3_seen=len(id3_indices),
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_summary(repaired),
    )


def parse_chunks_for_repair(data: bytes) -> tuple[list[ParsedChunk], list[str]]:
    chunks: list[ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    found_data = False

    while pos < len(data):
        if pos + 8 > len(data):
            if any(byte != 0 for byte in data[pos:]):
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break

        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            if found_data:
                marker = find_next_id3_chunk(data, pos)
                if marker is not None:
                    actions.append(f"dropped invalid bytes at offset {pos} size {marker - pos}")
                    pos = marker
                    continue
                actions.append(f"dropped unparseable tail at offset {pos} size {len(data) - pos}")
                break
            raise RepairError(f"invalid chunk ID before audio data at offset {pos}: {chunk_id!r}")

        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)

        if chunk_id == b"LIST" and size < 4 and found_data:
            actions.append(f"removed invalid empty LIST chunk at offset {pos}")
            pos = unpadded_end
            continue

        if padded_end > len(data):
            if chunk_id == b"data":
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                            note="shrunk oversized data chunk before ID3 chunk",
                        )
                    )
                    actions.append(
                        f"shrunk oversized data chunk at offset {pos} "
                        f"from declared size {size} to {len(payload)}"
                    )
                    found_data = True
                    pos = marker
                    continue
            if found_data:
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                            note="shrunk before ID3 chunk",
                        )
                    )
                    actions.append(
                        f"shrunk oversized {chunk_id.decode('ascii', 'replace').strip()} "
                        f"chunk at offset {pos} before ID3 offset {marker}"
                    )
                    if chunk_id == b"data":
                        found_data = True
                    pos = marker
                    continue
            actions.append(f"dropped truncated tail at offset {pos} size {len(data) - pos}")
            break

        source_end = padded_end
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            source_end = unpadded_end
            actions.append(
                f"inserted missing RIFF padding after odd-sized "
                f"{chunk_id.decode('ascii', 'replace').strip()} chunk at offset {pos}"
            )

        payload = data[data_offset:unpadded_end]
        chunks.append(ParsedChunk(chunk_id=chunk_id, payload=payload, source_start=pos, source_end=source_end))
        if chunk_id == b"data":
            found_data = True
        pos = source_end

    if not any(chunk.chunk_id == b"data" for chunk in chunks):
        raise RepairError("no data chunk found")
    return chunks, actions


def data_payload_hash(data: bytes) -> str:
    return hashlib.sha256(data_payload(data)).hexdigest()


def data_payload(data: bytes) -> bytes:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            break
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if chunk_id == b"data":
            if unpadded_end <= len(data):
                return data[data_offset:unpadded_end]
            marker = find_next_id3_chunk(data, data_offset)
            if marker is not None and marker > data_offset:
                return data[data_offset:marker]
            break
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            pos = unpadded_end
        else:
            pos = padded_end
    raise RepairError("no readable data chunk found")


def is_id3_chunk(chunk: ParsedChunk) -> bool:
    return chunk.chunk_id in ID3_CHUNK_IDS


def is_valid_chunk_id(chunk_id: bytes) -> bool:
    return len(chunk_id) == 4 and all(32 <= byte <= 126 for byte in chunk_id)


def looks_like_chunk_at(data: bytes, pos: int) -> bool:
    if pos + 8 > len(data):
        return False
    chunk_id = data[pos : pos + 4]
    if not is_valid_chunk_id(chunk_id):
        return False
    size = int.from_bytes(data[pos + 4 : pos + 8], "little")
    if chunk_id in ID3_CHUNK_IDS:
        return data[pos + 8 : pos + 11] == b"ID3"
    if chunk_id == b"LIST" and size < 4:
        return True
    return pos + 8 + size + (size % 2) <= len(data) + 1


def find_next_id3_chunk(data: bytes, start: int) -> int | None:
    best: int | None = None
    for marker in ID3_CHUNK_IDS:
        pos = data.find(marker, start)
        while pos != -1:
            if pos + 11 <= len(data) and data[pos + 8 : pos + 11] == b"ID3":
                if best is None or pos < best:
                    best = pos
                break
            pos = data.find(marker, pos + 1)
    return best


def mutagen_summary(data: bytes) -> str | None:
    try:
        from mutagen.wave import WAVE
    except Exception:
        return None
    try:
        audio = WAVE(BytesIO(data))
    except Exception as error:
        return f"mutagen error: {error}"
    length = getattr(getattr(audio, "info", None), "length", None)
    if audio.tags is None:
        return f"mutagen ok length={length:.3f} tags=no" if isinstance(length, float) else "mutagen ok tags=no"
    keys = sorted(str(key) for key in audio.tags.keys())
    return (
        f"mutagen ok length={length:.3f} tags=yes keys={','.join(keys[:8])}"
        if isinstance(length, float)
        else f"mutagen ok tags=yes keys={','.join(keys[:8])}"
    )


def verify_repaired_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RepairError("repaired file is not RIFF/WAVE")
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise RepairError("repaired RIFF size does not match file size")
    data_payload_hash(data)
    summary = mutagen_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise RepairError(summary)


def create_backup(path: Path, *, backup_dir: Path | None, no_backup: bool) -> Path | None:
    if no_backup:
        return None
    if backup_dir is None:
        backup_path = unique_path(path.with_name(path.name + ".mutagen-id3-repair.bak"))
    else:
        backup_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(str(path).encode("utf-8", errors="replace")).hexdigest()[:12]
        backup_path = unique_path(backup_dir / f"{path.stem}.{digest}{path.suffix}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.name}.{index}")
        if not candidate.exists():
            return candidate
    raise RepairError(f"Could not allocate unique backup path near {path}")


def write_repaired_file(path: Path, data: bytes) -> None:
    temp_path = path.with_name(f"{path.name}.repair-{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def format_result(result: FileRepairResult, *, dry_run: bool) -> str:
    prefix = "DRY-RUN" if dry_run else "APPLY"
    details = [
        prefix,
        result.status,
        str(result.path),
        f"size={result.original_size}->{result.repaired_size}",
        f"id3={result.id3_seen} removed={result.id3_removed}",
    ]
    if result.backup_path is not None:
        details.append(f"backup={result.backup_path}")
    if result.mutagen_summary:
        details.append(result.mutagen_summary)
    if result.actions:
        details.append("actions=" + " | ".join(result.actions))
    if result.status == "failed":
        details.append("error=" + result.message)
    return " ; ".join(details)


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

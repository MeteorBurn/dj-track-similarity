from __future__ import annotations

import argparse
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path


READBACK_FAILURE = "Genre tag was not readable after WAV save:"
ID3_CHUNK_IDS = {b"id3 ", b"ID3 "}
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RUN_DIR = SCRIPT_DIR / "audio_repair"
DEFAULT_BACKUP_DIR = DEFAULT_RUN_DIR / "backups"
DEFAULT_FILE_LOG = DEFAULT_RUN_DIR / "repair_audio_metadata.log"
AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".alac",
    ".aac",
    ".aifc",
    ".ape",
    ".dff",
    ".dsf",
    ".flac",
    ".mka",
    ".m4a",
    ".oga",
    ".ogg",
    ".opus",
    ".mp3",
    ".mp4",
    ".tta",
    ".wav",
    ".wave",
    ".wma",
    ".wv",
}
EXPECTED_FORMAT_BY_EXTENSION = {
    ".aif": {"aiff"},
    ".aiff": {"aiff"},
    ".aifc": {"aiff"},
    ".aac": {"aac"},
    ".alac": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".ape": {"ape"},
    ".dff": {"dsf"},
    ".dsf": {"dsf"},
    ".flac": {"flac"},
    ".mka": {"matroska,webm", "matroska"},
    ".m4a": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".mp3": {"mp3"},
    ".mp4": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".oga": {"ogg"},
    ".ogg": {"ogg"},
    ".opus": {"ogg"},
    ".tta": {"tta"},
    ".wav": {"wav"},
    ".wave": {"wav"},
    ".wma": {"asf"},
    ".wv": {"wv"},
}
EXPECTED_CODECS_BY_EXTENSION = {
    ".aac": {"aac"},
    ".aif": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aiff": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aifc": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".ape": {"ape"},
    ".dff": {"dsd_lsbf", "dsd_msbf"},
    ".dsf": {"dsd_lsbf", "dsd_msbf"},
    ".flac": {"flac"},
    ".m4a": {"aac", "alac"},
    ".mp3": {"mp3"},
    ".mp4": {"aac", "alac", "mp3"},
    ".oga": {"vorbis", "opus", "flac"},
    ".ogg": {"vorbis", "opus"},
    ".opus": {"opus"},
    ".tta": {"tta"},
    ".wav": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wave": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wma": {"wmav1", "wmav2", "wmapro", "wmall", "wmalossless"},
    ".wv": {"wavpack"},
}
STATUS_COLORS = {
    "ok": "32",
    "notice": "34",
    "repairable": "33",
    "repaired": "32",
    "suspicious": "35",
    "tag-error": "31",
    "broken": "31",
    "failed": "31",
    "unsupported": "90",
}


class RepairError(Exception):
    pass


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: bytes
    payload: bytes
    source_start: int
    source_end: int


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


@dataclass(frozen=True)
class FileInspectionResult:
    path: Path
    status: str
    message: str
    detected_format: str | None = None
    detected_codec: str | None = None
    tag_summary: str | None = None


class RunReporter:
    def __init__(self, log_path: Path | None) -> None:
        self._handle = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = log_path.open("w", encoding="utf-8", errors="replace")

    def line(self, text: str, *, log_text: str | None = None) -> None:
        print(text)
        if self._handle is not None:
            self._handle.write((log_text if log_text is not None else text) + "\n")
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    all_paths = collect_paths(args.logs, args.paths, folders=args.folders, since=args.since, until=args.until)
    if not all_paths:
        print("No audio paths found. Pass paths, --folder, or --log with readback failures.", file=sys.stderr)
        return 2

    keep_id3 = args.keep_id3
    apply_changes = args.apply
    if apply_changes and args.backup_dir and args.no_backup:
        print("--backup-dir and --no-backup cannot be used together.", file=sys.stderr)
        return 2
    use_color = should_use_color(args.color)
    folder_mode = bool(args.folders)
    state: dict[str, object] | None = None
    state_path: Path | None = None
    skipped_from_state = 0
    skipped_by_reason = 0
    paths = list(all_paths)
    if args.reasons and not folder_mode:
        print("--reason can only be used with --folder state.", file=sys.stderr)
        return 2
    if folder_mode:
        state_path = resolve_state_path(args.state, args.folders)
        state = load_state(state_path, args.folders)
        pending_paths: list[Path] = []
        for path in all_paths:
            if args.reasons and not state_entry_reason_matches(state, path, set(args.reasons)):
                skipped_by_reason += 1
                continue
            if state_entry_current(state, path, apply_changes=apply_changes):
                skipped_from_state += 1
            else:
                pending_paths.append(path)
        paths = pending_paths
    if args.limit is not None:
        paths = paths[: args.limit]

    reporter = RunReporter(None if args.no_file_log else Path(args.file_log))
    try:
        return run_paths(
            paths,
            all_paths=all_paths,
            skipped_from_state=skipped_from_state,
            reporter=reporter,
            use_color=use_color,
            apply_changes=apply_changes,
            backup_dir=args.backup_dir,
            no_backup=args.no_backup,
            keep_id3=keep_id3,
            state=state,
            state_path=state_path,
            folder_mode=folder_mode,
            summary_only=args.summary_only,
            workers=args.workers,
            skipped_by_reason=skipped_by_reason,
        )
    finally:
        reporter.close()


def run_paths(
    paths: list[Path],
    *,
    all_paths: list[Path],
    skipped_from_state: int,
    reporter: RunReporter,
    use_color: bool,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    state: dict[str, object] | None,
    state_path: Path | None,
    folder_mode: bool,
    summary_only: bool,
    workers: int,
    skipped_by_reason: int,
) -> int:
    if folder_mode:
        reporter.line(f"Total tracks: {len(all_paths)}")
        if state_path is not None:
            reporter.line(f"State file: {state_path}")
        reporter.line(f"Already checked from state: {skipped_from_state}")
        if skipped_by_reason:
            reporter.line(f"Skipped by reason filter: {skipped_by_reason}")
        reporter.line(f"Pending tracks: {len(paths)}")
    else:
        reporter.line(f"Total tracks: {len(paths)}")

    results: list[FileRepairResult] = []
    total = len(paths)
    indexed_results = process_paths(
        paths,
        apply_changes=apply_changes,
        backup_dir=backup_dir,
        no_backup=no_backup,
        keep_id3=keep_id3,
        workers=workers,
    )
    for index, path, result in indexed_results:
        results.append(result)
        if state is not None and state_path is not None:
            update_state_entry(state, path, result, apply_changes=apply_changes)
            save_state(state_path, state)
        if not summary_only:
            reporter.line(
                format_result(result, dry_run=not apply_changes, index=index, total=total, color=use_color),
                log_text=format_result(result, dry_run=not apply_changes, index=index, total=total, color=False),
            )

    failed = sum(1 for result in results if result.status == "failed")
    changed = sum(1 for result in results if result.status == "repaired")
    repairable = sum(1 for result in results if result.status == "repairable")
    notice = sum(1 for result in results if result.status == "notice")
    suspicious = sum(1 for result in results if result.status == "suspicious")
    tag_error = sum(1 for result in results if result.status == "tag-error")
    ok = sum(1 for result in results if result.status == "ok")
    problem_counts = summarize_problem_types(results)
    summary = (
        "Summary: "
        f"total={len(results)} repaired={changed} repairable={repairable} "
        f"notice={notice} ok={ok} suspicious={suspicious} "
        f"tag-error={tag_error} failed={failed}"
    )
    if folder_mode:
        summary += f" skipped-state={skipped_from_state}"
        if skipped_by_reason:
            summary += f" skipped-reason={skipped_by_reason}"
    reporter.line(summary)
    if problem_counts:
        reporter.line("Problem summary:")
        for problem, count in problem_counts:
            reporter.line(f"{problem}: {count}")
    return 1 if failed else 0


def process_paths(
    paths: list[Path],
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    workers: int,
) -> Iterator[tuple[int, Path, FileRepairResult]]:
    worker_count = max(1, workers)
    if apply_changes or worker_count == 1 or len(paths) <= 1:
        for index, path in enumerate(paths, start=1):
            yield (
                index,
                path,
                repair_file(
                    path,
                    apply_changes=apply_changes,
                    backup_dir=backup_dir,
                    no_backup=no_backup,
                    keep_id3=keep_id3,
                ),
            )
        return

    def check_one(item: tuple[int, Path]) -> tuple[int, Path, FileRepairResult]:
        index, path = item
        return (
            index,
            path,
            repair_file(
                path,
                apply_changes=False,
                backup_dir=backup_dir,
                no_backup=no_backup,
                keep_id3=keep_id3,
            ),
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        yield from executor.map(check_one, enumerate(paths, start=1))


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect audio metadata/container issues and repair known safe Mutagen ID3 chunk failures. "
            "Dry-run is read-only and does not copy or write audio files."
        )
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Audio files to inspect or repair.")
    parser.add_argument(
        "--folder",
        dest="folders",
        action="append",
        type=Path,
        default=[],
        help="Folder to scan recursively for supported audio extensions.",
    )
    parser.add_argument(
        "--log",
        dest="logs",
        action="append",
        type=Path,
        default=[],
        help="Project log file. Only post-save readback-failed WAV paths are extracted.",
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
        help="Directory for full-file backups used only with --apply. Default: scripts/audio_repair/backups.",
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
        help="For WAV repair, which readable top-level ID3 chunk to keep after repair. Default: first.",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N collected paths.")
    parser.add_argument("--summary-only", action="store_true", help="Print only the final summary.")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize status labels. Default: auto.",
    )
    parser.add_argument(
        "--file-log",
        type=Path,
        default=DEFAULT_FILE_LOG,
        help="File log path overwritten on every run. Default: scripts/audio_repair/repair_audio_metadata.log.",
    )
    parser.add_argument("--no-file-log", action="store_true", help="Do not write a file log.")
    parser.add_argument(
        "--state",
        type=Path,
        help=(
            "Folder-mode state file. Default is derived from the resolved --folder path(s) "
            "and stored in scripts/audio_repair."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel dry-run workers. --apply always runs sequentially.",
    )
    parser.add_argument(
        "--reason",
        dest="reasons",
        action="append",
        default=[],
        help=(
            "Folder-mode state reason to process. Use after a dry-run with --apply to repair only "
            "one stored reason. Can be repeated. Match the exact reason from the state file."
        ),
    )
    return parser.parse_args(argv)


def collect_paths(
    logs: list[Path],
    paths: list[Path],
    *,
    folders: list[Path] | None = None,
    since: str | None,
    until: str | None,
) -> list[Path]:
    collected: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        add_path(collected, seen, path)
    for folder in folders or []:
        for path in paths_from_folder(folder):
            add_path(collected, seen, path)
    for log_path in logs:
        for path in paths_from_log(log_path, since=since, until=until):
            add_path(collected, seen, path)
    return collected


def resolve_state_path(state_path: Path | None, folders: list[Path]) -> Path:
    if state_path is not None:
        return state_path
    signature = folder_signature(folders)
    digest = hashlib.sha1(signature.encode("utf-8", errors="replace")).hexdigest()[:12]
    return DEFAULT_RUN_DIR / f"state.{folder_state_label(folders)}.{digest}.json"


def folder_signature(folders: list[Path]) -> str:
    resolved = [str(folder.resolve()) for folder in folders]
    return "\n".join(sorted(os.path.normcase(path) for path in resolved))


def folder_state_label(folders: list[Path]) -> str:
    if len(folders) == 1:
        return safe_filename_part(folders[0].resolve().name or folders[0].resolve().anchor.rstrip(":\\"))
    digest = hashlib.sha1(folder_signature(folders).encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"multiple_{digest}"


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "folder"


def load_state(state_path: Path, folders: list[Path]) -> dict[str, object]:
    if not state_path.exists():
        return new_state(folders)
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return new_state(folders)
    if not isinstance(raw, dict):
        return new_state(folders)
    files = raw.get("files")
    if not isinstance(files, dict):
        raw["files"] = {}
    raw.setdefault("version", 2)
    raw["folders"] = [str(folder.resolve()) for folder in folders]
    return raw


def new_state(folders: list[Path]) -> dict[str, object]:
    return {
        "version": 2,
        "folders": [str(folder.resolve()) for folder in folders],
        "updated_at": None,
        "files": {},
    }


def state_key(path: Path) -> str:
    return hashlib.sha1(state_key_source(path).encode("utf-8", errors="replace")).hexdigest()


def state_key_source(path: Path) -> str:
    resolved = path.resolve()
    return os.path.normcase(str(resolved.parent / resolved.name))


def state_entry_for_path(state: dict[str, object], path: Path) -> dict[str, object] | None:
    files = state.get("files")
    if not isinstance(files, dict):
        return None
    entry = files.get(state_key(path))
    if isinstance(entry, dict):
        return entry
    return None


def state_entry_current(state: dict[str, object], path: Path, *, apply_changes: bool) -> bool:
    entry = state_entry_for_path(state, path)
    if entry is None:
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if entry.get("size") != stat.st_size or state_modified_at(entry) != int(stat.st_mtime):
        return False
    if apply_changes:
        return entry.get("mode") == "apply"
    return True


def state_entry_reason_matches(state: dict[str, object], path: Path, reasons: set[str]) -> bool:
    entry = state_entry_for_path(state, path)
    if entry is None:
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if entry.get("size") != stat.st_size or state_modified_at(entry) != int(stat.st_mtime):
        return False
    return entry.get("reason") in reasons


def state_modified_at(entry: dict[str, object]) -> int | None:
    value = entry.get("modified_at")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def update_state_entry(state: dict[str, object], path: Path, result: FileRepairResult, *, apply_changes: bool) -> None:
    files = state.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        state["files"] = files
    stat = path.stat()
    files[state_key(path)] = {
        "title": path.name,
        "path": str(path),
        "size": stat.st_size,
        "mode": "apply" if apply_changes else "dry-run",
        "message": result_message(result),
        "status": result.status,
        "reason": result_reason(result),
        "checked_at": int(time.time()),
        "modified_at": int(stat.st_mtime),
    }
    state["updated_at"] = int(time.time())


def result_message(result: FileRepairResult) -> str:
    if result.status == "ok" and result.message == "ok":
        return "checked"
    if result.status == "repairable" and result.message == "ok":
        return "repair_available"
    if result.status == "repaired" and result.message == "ok":
        return "repair_applied"
    return result.message


def save_state(state_path: Path, state: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, state_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def paths_from_folder(folder: Path) -> list[Path]:
    if not folder.exists():
        raise RepairError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise RepairError(f"Not a folder: {folder}")
    return sorted(
        (path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda path: os.path.normcase(str(path)),
    )


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


def inspect_file(path: Path) -> FileInspectionResult:
    if not path.exists():
        return FileInspectionResult(path=path, status="failed", message="file does not exist")
    suffix = path.suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        return FileInspectionResult(path=path, status="unsupported", message=f"unsupported extension={suffix}")

    detected_format = detect_format_from_header(path)
    probe_format, probe_codec = probe_file(path)
    display_format = probe_format or detected_format
    expected_formats = EXPECTED_FORMAT_BY_EXTENSION.get(suffix)
    if detected_format and expected_formats and detected_format not in expected_formats:
        return FileInspectionResult(
            path=path,
            status="suspicious",
            message=f"extension={suffix} detected={detected_format}",
            detected_format=detected_format,
            detected_codec=probe_codec,
        )
    if probe_codec:
        expected_codecs = EXPECTED_CODECS_BY_EXTENSION.get(suffix)
        if expected_codecs and probe_codec not in expected_codecs:
            return FileInspectionResult(
                path=path,
                status="suspicious",
                message=f"extension={suffix} detected_codec={probe_codec}",
                detected_format=display_format,
                detected_codec=probe_codec,
            )

    tag_summary = read_mutagen_tag_summary(path)
    if tag_summary.startswith("mutagen error:"):
        if suffix in {".aif", ".aiff"} and has_empty_aiff_id3_chunks(path.read_bytes()):
            return FileInspectionResult(
                path=path,
                status="repairable",
                message="AIFF has empty ID3 chunks that prevent Mutagen tag reads",
                detected_format=display_format,
                detected_codec=probe_codec,
                tag_summary=tag_summary,
            )
        return FileInspectionResult(
            path=path,
            status="tag-error",
            message=tag_summary,
            detected_format=display_format,
            detected_codec=probe_codec,
            tag_summary=tag_summary,
        )

    if display_format is None:
        return FileInspectionResult(path=path, status="broken", message="audio format was not detected")
    return FileInspectionResult(
        path=path,
        status="ok",
        message="ok",
        detected_format=display_format,
        detected_codec=probe_codec,
        tag_summary=tag_summary,
    )


def detect_format_from_header(path: Path) -> str | None:
    header = path.read_bytes()[:64]
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"FORM") and header[8:12] in {b"AIFF", b"AIFC"}:
        return "aiff"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"MAC "):
        return "ape"
    if header.startswith(b"wvpk"):
        return "wv"
    if header.startswith(b"TTA"):
        return "tta"
    if header.startswith(b"DSD "):
        return "dsf"
    if header.startswith(b"FRM8"):
        return "dsf"
    if header.startswith(b"0&\xb2u\x8ef\xcf\x11\xa6\xd9\x00\xaa\x00b\xcel"):
        return "asf"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "mp3"
    if len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0:
        return "aac"
    if b"ftyp" in header[:16]:
        return "mp4"
    return None


def probe_file(path: Path) -> tuple[str | None, str | None]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None, None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-hide_banner",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "format=format_name:stream=codec_name",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception:
        return None, None
    if result.returncode != 0:
        return None, None
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not values:
        return None, None
    codec = values[0]
    fmt = values[-1] if len(values) > 1 else None
    return fmt, codec


def read_mutagen_tag_summary(path: Path) -> str:
    try:
        from mutagen import File as MutagenFile
    except Exception as error:
        return f"mutagen unavailable: {error}"
    try:
        audio = MutagenFile(path)
    except Exception as error:
        return f"mutagen error: {error}"
    if audio is None:
        return "mutagen error: unsupported audio tag format"
    tags = getattr(audio, "tags", None)
    if tags is None:
        return "mutagen ok tags=no"
    keys = sorted(str(key) for key in tags.keys())
    return f"mutagen ok tags=yes keys={','.join(keys[:8])}"


def repair_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
) -> FileRepairResult:
    suffix = path.suffix.lower()
    if suffix in {".wav", ".wave"}:
        return repair_wave_file(
            path,
            apply_changes=apply_changes,
            backup_dir=backup_dir,
            no_backup=no_backup,
            keep_id3=keep_id3,
        )
    if suffix in {".aif", ".aiff"}:
        return repair_aiff_file(path, apply_changes=apply_changes, backup_dir=backup_dir, no_backup=no_backup)
    inspection = inspect_file(path)
    return FileRepairResult(path=path, status=inspection.status, message=inspection.message, mutagen_summary=inspection.tag_summary)


def repair_wave_file(
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
        if is_cosmetic_only_wave_repair(repaired):
            return FileRepairResult(
                path=path,
                status="notice",
                message="cosmetic trailing zero padding",
                actions=["dropped trailing zero padding bytes"],
                original_size=len(data),
                repaired_size=len(data),
                id3_seen=repaired.id3_seen,
                id3_removed=repaired.id3_removed,
                mutagen_summary=repaired.mutagen_summary,
            )

        status = "ok"
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


def is_cosmetic_only_wave_repair(repaired: ByteRepairResult) -> bool:
    if not repaired.changed:
        return False
    if repaired.id3_removed:
        return False
    if not repaired.actions:
        return False
    if any(not action.startswith("dropped trailing zero padding bytes") for action in repaired.actions):
        return False
    return bool(repaired.mutagen_summary and repaired.mutagen_summary.startswith("mutagen ok"))


def repair_aiff_file(
    path: Path,
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
) -> FileRepairResult:
    try:
        data = path.read_bytes()
        if not has_empty_aiff_id3_chunks(data):
            inspection = inspect_file(path)
            status = inspection.status
            return FileRepairResult(
                path=path,
                status=status,
                message=inspection.message,
                original_size=len(data),
                repaired_size=len(data),
                mutagen_summary=inspection.tag_summary,
            )
        original_payload_hash = aiff_sound_payload_hash(data)
        repaired = repair_aiff_bytes(data)
        repaired_payload_hash = aiff_sound_payload_hash(repaired.data)
        if original_payload_hash != repaired_payload_hash:
            raise RepairError("audio sound payload would change; refusing to write")

        status = "ok"
        backup_path = None
        if repaired.changed:
            status = "repairable"
            if apply_changes:
                backup_path = create_backup(path, backup_dir=backup_dir, no_backup=no_backup)
                write_repaired_file(path, repaired.data)
                verify_repaired_aiff_file(path)
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
        inspection = inspect_file(path)
        if inspection.status in {"tag-error", "suspicious"}:
            return FileRepairResult(path=path, status=inspection.status, message=inspection.message)
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


def repair_aiff_bytes(data: bytes) -> ByteRepairResult:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("not an AIFF/AIFC file")

    chunks, actions = parse_aiff_chunks(data)
    id3_seen = sum(1 for chunk in chunks if chunk.chunk_id == b"ID3 ")
    rebuilt = bytearray(data[:12])
    id3_removed = 0
    for chunk in chunks:
        if chunk.chunk_id == b"ID3 " and not chunk.payload:
            id3_removed += 1
            actions.append(f"removed empty ID3 chunk at offset {chunk.source_start}")
            continue
        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "big"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "big")
    repaired = bytes(rebuilt)
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        actions.append("normalized FORM root size")
    if id3_removed:
        actions.append(f"removed empty ID3 chunks: {id3_removed}")

    return ByteRepairResult(
        changed=repaired != data,
        data=repaired,
        actions=dedupe(actions),
        id3_seen=id3_seen,
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_aiff_summary(repaired),
    )


def parse_aiff_chunks(data: bytes) -> tuple[list[ParsedChunk], list[str]]:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("not an AIFF/AIFC file")
    chunks: list[ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            raise RepairError(f"invalid AIFF chunk ID at offset {pos}: {chunk_id!r}")
        size = int.from_bytes(data[pos + 4 : pos + 8], "big")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if padded_end > len(data):
            raise RepairError(f"truncated AIFF chunk at offset {pos}: {chunk_id!r}")
        chunks.append(
            ParsedChunk(
                chunk_id=chunk_id,
                payload=data[data_offset:unpadded_end],
                source_start=pos,
                source_end=padded_end,
            )
        )
        pos = padded_end
    if not any(chunk.chunk_id == b"SSND" for chunk in chunks):
        raise RepairError("no SSND chunk found")
    return chunks, actions


def has_empty_aiff_id3_chunks(data: bytes) -> bool:
    try:
        chunks, _ = parse_aiff_chunks(data)
    except RepairError:
        return False
    return any(chunk.chunk_id == b"ID3 " and not chunk.payload for chunk in chunks)


def parse_chunks_for_repair(data: bytes) -> tuple[list[ParsedChunk], list[str]]:
    chunks: list[ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    found_data = False

    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
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


def aiff_sound_payload_hash(data: bytes) -> str:
    return hashlib.sha256(aiff_sound_payload(data)).hexdigest()


def aiff_sound_payload(data: bytes) -> bytes:
    chunks, _ = parse_aiff_chunks(data)
    for chunk in chunks:
        if chunk.chunk_id == b"SSND":
            return chunk.payload
    raise RepairError("no readable SSND chunk found")


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


def mutagen_aiff_summary(data: bytes) -> str | None:
    try:
        from mutagen.aiff import AIFF
    except Exception:
        return None
    try:
        audio = AIFF(BytesIO(data))
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


def verify_repaired_aiff_file(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise RepairError("repaired file is not AIFF/AIFC")
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        raise RepairError("repaired FORM size does not match file size")
    aiff_sound_payload_hash(data)
    summary = mutagen_aiff_summary(data)
    if summary and summary.startswith("mutagen error:"):
        raise RepairError(summary)


def create_backup(path: Path, *, backup_dir: Path | None, no_backup: bool) -> Path | None:
    if no_backup:
        return None
    target_dir = backup_dir or DEFAULT_BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(path).encode("utf-8", errors="replace")).hexdigest()[:12]
    backup_path = unique_path(target_dir / f"{path.stem}.{digest}{path.suffix}.bak")
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


def format_result(
    result: FileRepairResult,
    *,
    dry_run: bool,
    index: int | None = None,
    total: int | None = None,
    color: bool = False,
) -> str:
    counter = f"[{index}/{total}]" if index is not None and total is not None else "[?/?]"
    status = format_status(result.status, color=color)
    fields = [f"{counter} {status}", f"mode={'dry-run' if dry_run else 'apply'}", f"file={result.path}"]
    if result.original_size or result.repaired_size:
        fields.append(f"size={result.original_size}->{result.repaired_size}")
    if result.id3_seen or result.id3_removed:
        fields.append(f"id3={result.id3_seen}/{result.id3_removed}")
    if result.backup_path is not None:
        fields.append(f"backup={result.backup_path}")
    if result.status in {"failed", "suspicious", "tag-error", "broken", "unsupported", "notice"}:
        fields.append(f"problem={result.message}")
    if result.actions:
        fields.append(f"action={primary_action(result.actions)}")
    return " | ".join(fields)


def primary_action(actions: list[str]) -> str:
    for action in actions:
        if action.startswith("shrunk oversized data chunk"):
            return action
        if action.startswith("removed empty ID3 chunk"):
            return action
        if action.startswith("removed ID3 chunk"):
            return action
    return actions[0]


def format_status(status: str, *, color: bool) -> str:
    label = status.upper()
    if not color:
        return label
    code = STATUS_COLORS.get(status)
    if code is None:
        return label
    return f"\x1b[{code}m{label}\x1b[0m"


def should_use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def summarize_problem_types(results: list[FileRepairResult]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        problem = result_problem_summary(result)
        if problem is None:
            continue
        counts[problem] = counts.get(problem, 0) + 1
    return sorted(counts.items())


def result_reason(result: FileRepairResult) -> str | None:
    if result.status == "ok":
        return None
    if result.status in {"repairable", "repaired"}:
        return repairable_reason(result)
    if result.status == "notice":
        return "notice"
    if result.status == "suspicious":
        extension_match = re.search(r"extension=(\.[^\s]+) detected=([^\s]+)", result.message)
        if extension_match:
            return "extension_mismatch"
        codec_match = re.search(r"extension=(\.[^\s]+) detected_codec=([^\s]+)", result.message)
        if codec_match:
            return "codec_mismatch"
        return "suspicious"
    if result.status == "tag-error":
        return "tag_error"
    if result.status == "failed":
        return "failed"
    if result.status == "broken":
        return "broken"
    if result.status == "unsupported":
        return "unsupported"
    return result.status.replace("-", "_")


def repairable_reason(result: FileRepairResult) -> str | None:
    if result.status not in {"repairable", "repaired"}:
        return None
    joined_actions = " | ".join(result.actions)
    suffix = result.path.suffix.lower()
    if suffix in {".wav", ".wave"} and "shrunk oversized data chunk" in joined_actions:
        return "oversized_data"
    if suffix in {".wav", ".wave"} and "removed duplicate/unselected ID3 chunks" in joined_actions:
        return "duplicate_id3"
    if suffix in {".aif", ".aiff", ".aifc"} and "removed empty ID3 chunk" in joined_actions:
        return "empty_id3"
    if suffix in {".wav", ".wave"}:
        return "container"
    if suffix in {".aif", ".aiff", ".aifc"}:
        return "container"
    return "repairable"


def result_problem_summary(result: FileRepairResult) -> str | None:
    reason = result_reason(result)
    if reason is None:
        return None
    if result.status in {"repairable", "repaired"}:
        return f"repairable[{reason}]: {repairable_reason_description(reason, result)}"
    if result.status == "notice":
        return f"notice[{reason}]: {result.message}"
    if result.status == "suspicious":
        extension_match = re.search(r"extension=(\.[^\s]+) detected=([^\s]+)", result.message)
        if extension_match:
            return (
                f"suspicious[{reason}]: extension mismatch: {extension_match.group(1)} "
                f"detected as {extension_match.group(2)}"
            )
        codec_match = re.search(r"extension=(\.[^\s]+) detected_codec=([^\s]+)", result.message)
        if codec_match:
            return (
                f"suspicious[{reason}]: codec mismatch: {codec_match.group(1)} "
                f"codec {codec_match.group(2)}"
            )
        return f"suspicious[{reason}]: {result.message}"
    return f"{result.status}[{reason}]: {result.message}"


def repairable_reason_description(reason: str, result: FileRepairResult) -> str:
    suffix = result.path.suffix.lower()
    if reason == "oversized_data":
        return "WAV oversized data chunk before ID3 chunk"
    if reason == "duplicate_id3":
        return "WAV duplicate/unselected ID3 chunks"
    if reason == "empty_id3":
        return "AIFF empty ID3 chunks"
    if reason == "container" and suffix in {".wav", ".wave"}:
        return "WAV container/tag chunk normalization"
    if reason == "container" and suffix in {".aif", ".aiff", ".aifc"}:
        return "AIFF container/tag chunk normalization"
    return result.message


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

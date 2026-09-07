from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import config as config_module
from . import container_repair as container_repair_module
from . import models as models_module


def inspect_file(path: Path) -> models_module.FileInspectionResult:
    if not path.exists():
        return models_module.FileInspectionResult(path=path, status="failed", message="file does not exist")
    suffix = path.suffix.lower()
    if suffix not in config_module.AUDIO_EXTENSIONS:
        return models_module.FileInspectionResult(path=path, status="unsupported", message=f"unsupported extension={suffix}")

    detected_format = detect_format_from_header(path)
    probe_format, probe_codec = probe_file(path)
    display_format = probe_format or detected_format
    expected_formats = config_module.EXPECTED_FORMAT_BY_EXTENSION.get(suffix)
    format_mismatch = bool(detected_format and expected_formats and detected_format not in expected_formats)
    expected_codecs = config_module.EXPECTED_CODECS_BY_EXTENSION.get(suffix)
    codec_mismatch = bool(probe_codec and expected_codecs and probe_codec not in expected_codecs)

    decode_error = full_decode_error(path)
    if decode_error is not None:
        return models_module.FileInspectionResult(
            path=path,
            status="failed",
            message=f"full FFmpeg decode failed: {decode_error}",
            detected_format=display_format,
            detected_codec=probe_codec,
        )
    if format_mismatch:
        return models_module.FileInspectionResult(
            path=path,
            status="suspicious",
            message=f"extension={suffix} detected={detected_format}",
            detected_format=display_format,
            detected_codec=probe_codec,
        )
    if codec_mismatch:
        return models_module.FileInspectionResult(
            path=path,
            status="suspicious",
            message=f"extension={suffix} detected_codec={probe_codec}",
            detected_format=display_format,
            detected_codec=probe_codec,
        )

    tag_summary = read_mutagen_tag_summary(path)
    if tag_summary.startswith("mutagen error:"):
        if suffix in {".aif", ".aiff"} and container_repair_module.has_empty_aiff_id3_chunks(path.read_bytes()):
            return models_module.FileInspectionResult(
                path=path,
                status="repairable",
                message="AIFF has empty ID3 chunks that prevent Mutagen tag reads",
                detected_format=display_format,
                detected_codec=probe_codec,
                tag_summary=tag_summary,
            )
        return models_module.FileInspectionResult(
            path=path,
            status="tag-error",
            message=tag_summary,
            detected_format=display_format,
            detected_codec=probe_codec,
            tag_summary=tag_summary,
        )

    if display_format is None:
        return models_module.FileInspectionResult(path=path, status="broken", message="audio format was not detected")
    return models_module.FileInspectionResult(
        path=path,
        status="ok",
        message="ok",
        detected_format=display_format,
        detected_codec=probe_codec,
        tag_summary=tag_summary,
    )


def full_decode_error(path: Path) -> str | None:
    """Return a strict full-decode error, or ``None`` when FFmpeg reads all audio."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return "ffmpeg is not available"
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-xerror",
                "-nostdin",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config_module.FULL_DECODE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"timed out after {config_module.FULL_DECODE_TIMEOUT_SECONDS} seconds"
    except OSError as error:
        return str(error)
    if result.returncode == 0:
        return None
    return next(
        (line.strip() for line in result.stderr.splitlines() if line.strip()),
        f"ffmpeg exited with status {result.returncode}",
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

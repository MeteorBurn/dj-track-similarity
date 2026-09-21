from __future__ import annotations

import logging
import time
from pathlib import Path

from dj_track_similarity.audio.ffmpeg_runtime import load_project_pyav

from . import config as config_module
from . import container_repair as container_repair_module
from . import models as models_module


# libav reports through this logger; without a handler Python prints its lines to
# stderr past the report, and every failure then reads the same.
logging.getLogger("libav").addHandler(logging.NullHandler())


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
    """Return a strict full-decode error, or ``None`` when FFmpeg reads all audio.

    Every packet of the first audio stream has to decode, and nothing is discarded:
    this is the check that separates a healthy file from a damaged one. Only the
    decode decides. An error libav reports while reading tags or an attached
    picture is not one, exactly as ``ffmpeg -xerror`` keeps going after it. The
    captured log supplies the wording when the decode does fail, and the
    elapsed-time check replaces the timeout a subprocess used to provide.
    """

    try:
        av = load_project_pyav()
    except RuntimeError as error:
        return str(error)
    deadline = time.monotonic() + config_module.FULL_DECODE_TIMEOUT_SECONDS
    av.logging.set_level(av.logging.ERROR)
    # Repeat folding holds a message back until the next distinct one arrives, which
    # would deliver one file's error into the next file's report.
    av.logging.set_skip_repeated(False)
    logged: list[tuple[int, str, str]] = []
    try:
        with av.open(str(path), mode="r", metadata_errors="replace") as container:
            streams = container.streams.audio
            if not streams:
                return "no audio stream"
            with av.logging.Capture(local=True) as logged:
                for packet in container.demux(streams[0]):
                    if time.monotonic() > deadline:
                        return (
                            "timed out after "
                            f"{config_module.FULL_DECODE_TIMEOUT_SECONDS} seconds"
                        )
                    # A packet the demuxer marked corrupt is a failure even when the
                    # decoder swallows it: a file truncated on a frame boundary
                    # decodes cleanly and is still damaged.
                    if packet.is_corrupt:
                        return _logged_error(logged) or "corrupt input packet in stream 0"
                    packet.decode()
    except (av.FFmpegError, OSError, ValueError) as error:
        return _logged_error(logged) or str(error)
    return None


def _logged_error(logged: list[tuple[int, str, str]]) -> str | None:
    for _level, component, message in logged:
        text = message.strip()
        if text:
            return f"[{component}] {text}" if component else text
    return None


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
    """Read the container format and the first audio codec, as ffprobe named them.

    The codec has to be the canonical name (``mp3``), not the decoder that libav
    picked for it (``mp3float``), because the expected-codec tables speak the
    canonical vocabulary.
    """

    try:
        av = load_project_pyav()
        with av.open(str(path), mode="r", metadata_errors="replace") as container:
            container_format = container.format.name or None
            streams = container.streams.audio
            if not streams:
                return container_format, None
            return container_format, streams[0].codec_context.codec.canonical_name
    except Exception:
        return None, None


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

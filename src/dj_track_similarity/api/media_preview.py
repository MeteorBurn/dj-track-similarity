from __future__ import annotations

import logging
import math
import re
import struct
import tempfile
import wave
from collections.abc import Generator, Iterator
from contextlib import closing
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import anyio
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from starlette.types import Receive, Scope, Send

from ..audio.ffmpeg_runtime import load_project_pyav

if TYPE_CHECKING:
    from av.audio.frame import AudioFrame
    from av.audio.stream import AudioStream
    from av.container import InputContainer
    from av.packet import Packet


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}
BROWSER_PREVIEW_TRANSCODE_SUFFIXES = AIFF_PREVIEW_SUFFIXES | {
    ".dff",
    ".dsd",
    ".dsf",
    ".flac",
    ".ape",
    ".wv",
    ".m4b",
    ".m4r",
    ".tak",
    ".tta",
    ".wma",
}
BROWSER_SAFE_WAV_SAMPLE_WIDTH = 2
PREVIEW_SAMPLE_RATE = 44_100
_PREVIEW_CHANNELS = 2
_PREVIEW_FRAME_BYTES = _PREVIEW_CHANNELS * BROWSER_SAFE_WAV_SAMPLE_WIDTH
_CHUNK_FRAMES = 16_384
_WAV_STREAM_HEADER = struct.pack(
    "<4sI4s4sIHHIIHH4sI",
    b"RIFF", 0xFFFFFFFF, b"WAVE", b"fmt ", 16, 1, _PREVIEW_CHANNELS,
    PREVIEW_SAMPLE_RATE, PREVIEW_SAMPLE_RATE * _PREVIEW_FRAME_BYTES,
    _PREVIEW_FRAME_BYTES, 16, b"data", 0xFFFFFFFF,
)


class AudioPreviewError(RuntimeError):
    """Raised when an audio preview response cannot be prepared."""


def preview_duration_seconds(path: Path) -> float | None:
    """Read source duration without decoding the whole track."""
    try:
        av = load_project_pyav()
        with av.open(str(path), metadata_errors="replace") as container:
            stream = _audio_stream(container)
            return _source_duration(container, stream)
    except (OSError, RuntimeError, ValueError) as error:
        raise AudioPreviewError(f"Audio preview failed: {error}") from error


def streaming_wav_response(path: Path, *, start: float = 0.0) -> StreamingResponse:
    """Prime audio before sending headers, then decode only as the client reads."""
    chunks = _pcm_chunks(path, start=start)
    try:
        first_chunk = next(chunks)
    except StopIteration as error:
        chunks.close()
        raise AudioPreviewError("Audio preview failed: no decodable audio samples") from error
    except (OSError, RuntimeError, ValueError) as error:
        chunks.close()
        raise AudioPreviewError(f"Audio preview failed: {error}") from error
    return _WavStreamingResponse(chunks, first_chunk)


class _WavStreamingResponse(StreamingResponse):
    def __init__(self, chunks: Generator[bytes, None, None], first_chunk: bytes) -> None:
        self._pcm = chunks

        def body() -> Iterator[bytes]:
            # Streaming WAV has no promised size, even if source metadata has a duration.
            yield _WAV_STREAM_HEADER
            yield first_chunk
            yield from chunks

        super().__init__(body(), media_type="audio/wav", headers={"Cache-Control": "no-store"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # BackgroundTask is skipped on ASGI send errors; always release the source here.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self._pcm.close)


def _audio_stream(container: InputContainer) -> AudioStream:
    if not container.streams.audio:
        raise AudioPreviewError("No audio stream found")
    return container.streams.audio[0]


def _source_duration(container: InputContainer, stream: AudioStream) -> float | None:
    if stream.duration is not None and stream.time_base is not None:
        duration = float(stream.duration * stream.time_base)
    elif container.duration is not None:
        duration = container.duration / 1_000_000
    else:
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def _pcm_chunks(path: Path, *, start: float = 0.0) -> Generator[bytes, None, None]:
    if not math.isfinite(start) or start < 0:
        raise AudioPreviewError("Preview start must be a finite nonnegative number")
    av = load_project_pyav()
    with av.open(str(path), metadata_errors="replace", options={"err_detect": "ignore_err"}) as container:
        stream = _audio_stream(container)
        duration = _source_duration(container, stream)
        if duration is not None and start >= duration:
            raise AudioPreviewError("Preview start is at or beyond the end of the audio")
        origin = float(stream.start_time * stream.time_base) if stream.start_time is not None else 0.0
        if start > 0:
            container.seek(int((origin + start) / stream.time_base), stream=stream, backward=True)
        position = round(start * PREVIEW_SAMPLE_RATE)
        warned_timestamp = False
        for frame in _resampled_frames(container, stream, av, path):
            frame_start = (
                round((float(frame.pts * frame.time_base) - origin) * PREVIEW_SAMPLE_RATE)
                if frame.pts is not None and frame.time_base is not None else position
            )
            outside_source = duration is not None and frame_start > math.ceil(duration * PREVIEW_SAMPLE_RATE)
            unknown_jump = duration is None and frame_start - position > 30 * PREVIEW_SAMPLE_RATE
            if outside_source or unknown_jump:
                if not warned_timestamp:
                    LOGGER.warning("Audio preview ignored an implausible timestamp jump path=%s", path)
                    warned_timestamp = True
                frame_start = position
            frame_end = frame_start + frame.samples
            if frame_end <= position:
                continue
            while position < frame_start:
                count = min(frame_start - position, _CHUNK_FRAMES)
                yield bytes(count * _PREVIEW_FRAME_BYTES)
                position += count
            # Trim seek pre-roll and overlaps on the original timeline, after resampling.
            samples = memoryview(frame.planes[0])
            while position < frame_end:
                count = min(frame_end - position, _CHUNK_FRAMES)
                offset = (position - frame_start) * _PREVIEW_FRAME_BYTES
                yield bytes(samples[offset:offset + count * _PREVIEW_FRAME_BYTES])
                position += count


def _resampled_frames(
    container: InputContainer, stream: AudioStream, av: ModuleType, path: Path,
) -> Iterator[AudioFrame]:
    resampler = av.AudioResampler(format="s16", layout="stereo", rate=PREVIEW_SAMPLE_RATE)
    skipped = 0
    try:
        try:
            for packet in container.demux(stream):
                packet = _complete_pcm_packet(packet, stream, av)
                if packet is None:
                    continue
                try:
                    for frame in packet.decode():
                        yield from resampler.resample(frame)
                except av.FFmpegError:
                    skipped += 1
        except av.FFmpegError as error:
            LOGGER.warning("Audio preview reached unreadable container data path=%s error=%s", path, error)
        try:
            yield from resampler.resample(None)
        except av.FFmpegError:
            skipped += 1
    finally:
        if skipped:
            LOGGER.warning("Audio preview skipped %d damaged audio packets path=%s", skipped, path)


def _complete_pcm_packet(packet: Packet, stream: AudioStream, av: ModuleType) -> Packet | None:
    # Decoded s24 samples use s32 storage, so derive packed source width from the codec.
    pcm = re.fullmatch(r"pcm_[suf](8|16|24|32|64)(?:le|be)?", stream.codec_context.name)
    if pcm is None or not packet.size:
        return packet
    frame_bytes = int(pcm[1]) // 8 * stream.codec_context.channels
    remainder = packet.size % frame_bytes
    if not remainder:
        return packet
    complete_size = packet.size - remainder
    if not complete_size:
        return None
    repaired = av.Packet(bytes(packet)[:complete_size])
    repaired.stream = stream
    repaired.pts = packet.pts
    repaired.dts = packet.dts
    repaired.time_base = packet.time_base
    repaired.duration = packet.duration
    return repaired


def requires_browser_preview_transcode(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BROWSER_PREVIEW_TRANSCODE_SUFFIXES:
        return True
    if suffix == ".wav":
        return not _is_browser_safe_wav(path)
    return False


def transcoded_wav_file_response(path: Path) -> FileResponse:
    """Keep Rhythm Lab's finite, browser-seekable file response using the shared decoder."""
    with tempfile.NamedTemporaryFile(prefix="dj-sim-preview-", suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        wrote_samples = False
        with closing(_pcm_chunks(path)) as chunks, wave.open(str(temp_path), "wb") as audio:
            audio.setnchannels(_PREVIEW_CHANNELS)
            audio.setsampwidth(BROWSER_SAFE_WAV_SAMPLE_WIDTH)
            audio.setframerate(PREVIEW_SAMPLE_RATE)
            for chunk in chunks:
                audio.writeframesraw(chunk)
                wrote_samples = True
        if not wrote_samples:
            raise AudioPreviewError("No decodable audio samples")
    except (OSError, RuntimeError, ValueError) as error:
        _delete_temp_file(temp_path)
        message = f"Audio preview failed: {error}"
        LOGGER.warning("Direct preview transcode failed path=%s error=%s", path, message)
        raise AudioPreviewError(message) from error
    return FileResponse(
        temp_path,
        media_type="audio/wav",
        filename=f"{path.stem}.wav",
        content_disposition_type="inline",
        background=BackgroundTask(_delete_temp_file, temp_path),
    )
def _is_browser_safe_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as audio:
            return (
                audio.getsampwidth() == BROWSER_SAFE_WAV_SAMPLE_WIDTH
                and audio.getnchannels() > 0
                and audio.getframerate() > 0
            )
    except (EOFError, OSError, wave.Error):
        return False


def _delete_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("Failed to delete temporary preview file: %s", path)

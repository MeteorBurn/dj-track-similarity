from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from .ffmpeg_runtime import load_project_pyav


LOGGER = logging.getLogger(__name__)
_FORMAT_OPTIONS = {"fflags": "+discardcorrupt+genpts"}
_CODEC_OPTIONS = {"err_detect": "ignore_err"}


def load_tolerant_mono_audio(path: str | Path) -> tuple[np.ndarray, int, str]:
    """Decode valid audio frames through the bundled FFmpeg/PyAV runtime.

    A malformed packet is discarded after FFmpeg has emitted all preceding valid
    frames. The caller receives source-rate mono float32 PCM for further use.
    """

    av = load_project_pyav()
    audio_path = Path(path)
    chunks: list[np.ndarray] = []
    sample_rate: int | None = None
    discarded_packets = 0

    try:
        with av.open(str(audio_path), mode="r", options=_FORMAT_OPTIONS) as container:
            if not container.streams.audio:
                raise RuntimeError(f"FFmpeg found no audio stream: {audio_path}")
            stream = container.streams.audio[0]
            codec_options = dict(stream.codec_context.options)
            codec_options.update(_CODEC_OPTIONS)
            stream.codec_context.options = codec_options
            resampler = av.audio.resampler.AudioResampler(
                format="flt",
                rate=None,
            )

            for packet in container.demux(stream):
                try:
                    decoded_frames = packet.decode()
                except av.error.InvalidDataError as error:
                    discarded_packets += 1
                    LOGGER.debug(
                        "Discarding malformed audio packet path=%s error=%s",
                        audio_path,
                        error,
                    )
                    continue
                for decoded_frame in decoded_frames:
                    sample_rate = int(decoded_frame.sample_rate)
                    _append_resampled_frames(chunks, resampler.resample(decoded_frame))
            _append_resampled_frames(chunks, resampler.resample(None))
    except av.FFmpegError as error:
        raise RuntimeError(f"FFmpeg shared-library decode failed: {audio_path}: {error}") from error

    if sample_rate is None or sample_rate <= 0 or not chunks:
        raise RuntimeError(f"FFmpeg shared-library decode produced no audio: {audio_path}")

    detail = "PyAV shared FFmpeg tolerant decode (mono float32)"
    if discarded_packets:
        detail += f"; discarded_corrupt_packets={discarded_packets}"
        LOGGER.warning(
            "Recovered audio after discarding malformed packets path=%s discarded=%d",
            audio_path,
            discarded_packets,
        )
    return np.concatenate(chunks), sample_rate, detail


def _append_resampled_frames(chunks: list[np.ndarray], frames: Any) -> None:
    for frame in frames:
        channels = len(frame.layout.channels)
        if channels <= 0:
            raise RuntimeError("FFmpeg decoded audio frame without channels")
        samples = np.asarray(frame.to_ndarray(), dtype=np.float32)
        if frame.format.is_planar:
            samples = samples.reshape(channels, -1).mean(axis=0, dtype=np.float32)
        else:
            samples = samples.reshape(-1, channels).mean(axis=1, dtype=np.float32)
        samples = samples.copy()
        if samples.size:
            chunks.append(samples)

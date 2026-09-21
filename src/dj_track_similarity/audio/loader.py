from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .decoder import load_tolerant_mono_audio
from .ffmpeg_runtime import configure_shared_ffmpeg_runtime

if TYPE_CHECKING:
    from torch import Tensor

@dataclass(frozen=True)
class DecodedAudio:
    path: str
    audio: Tensor
    sample_rate: int
    detail: str


def load_decoded_audio(path: str | Path) -> DecodedAudio:
    audio_path = Path(path)
    audio, sample_rate, detail = _load_with_torchcodec(audio_path)
    return DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail=detail)


def load_decoded_audio_with_ffmpeg(path: str | Path) -> DecodedAudio:
    """Decode one ML recovery source through shared FFmpeg into a tensor-backed value.

    TorchCodec has already failed on this path, so the recovery attempt has to reach a
    different decoder. Corrupt packets are discarded and the surrounding valid frames
    are kept.
    """

    audio, sample_rate, detail = _load_with_shared_ffmpeg(Path(path))
    return DecodedAudio(
        path=str(path),
        audio=audio,
        sample_rate=sample_rate,
        detail=detail,
    )


def load_audio_mono_with_ffmpeg(path: str | Path) -> tuple[np.ndarray, int, str]:
    """Decode one SONARA recovery source through shared FFmpeg to mono float32 PCM."""

    return load_tolerant_mono_audio(path)


def _load_with_torchcodec(path: Path) -> tuple[Tensor, int, str]:
    configure_shared_ffmpeg_runtime()
    import torch
    from torchcodec.decoders import AudioDecoder

    # Every model reference mixes to mono as the channel mean. FFmpeg's own
    # stereo-to-mono matrix skips its normalization for float output and yields
    # (L+R)/sqrt(2), 3 dB louder and past full scale, so decode native channels.
    decoded = AudioDecoder(str(path)).get_all_samples()
    if decoded.data.ndim != 2 or decoded.data.shape[0] <= 0:
        raise RuntimeError(
            f"TorchCodec produced an unexpected audio shape: {decoded.data.shape}"
        )
    if decoded.data.dtype != torch.float32:
        raise RuntimeError(
            f"TorchCodec produced an unexpected audio dtype: {decoded.data.dtype}"
        )
    audio = decoded.data.mean(dim=0)
    if audio.numel() == 0:
        raise RuntimeError("TorchCodec produced no decoded audio")
    sample_rate = int(decoded.sample_rate)
    if sample_rate <= 0:
        raise RuntimeError("TorchCodec produced an invalid sample rate")
    return (
        audio,
        sample_rate,
        "torchcodec 0.16 decode (arithmetic channel mean)",
    )


def _load_with_shared_ffmpeg(path: Path) -> tuple[Tensor, int, str]:
    import torch

    audio, sample_rate, detail = load_tolerant_mono_audio(path)
    return torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)), sample_rate, detail

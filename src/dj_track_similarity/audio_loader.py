from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING
import wave

from mutagen import File as MutagenFile
import numpy as np

if TYPE_CHECKING:
    from torch import Tensor

from .dependencies import FFMPEG_ENV_VAR

INVALID_AUDIO_STREAM_MESSAGE = "Invalid audio stream: ffmpeg could not decode audio"
# FFmpeg's default stereo -> mono matrix uses equal-power coefficients and can
# raise correlated stereo material by about 3 dB. The pan filter's ``<`` form
# renormalizes the active input terms, so every present channel contributes
# exactly 1 / channel_count. FFmpeg ignores cN terms that are absent from the
# input, which keeps one deterministic expression valid for mono through its
# 64-channel maximum.
FFMPEG_ARITHMETIC_MONO_FILTER = "pan=mono|c0<" + "+".join(f"c{index}" for index in range(64))


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


def load_audio_mono_with_ffmpeg(path: str | Path) -> tuple[np.ndarray, int, str]:
    """Decode one source through FFmpeg to mono float32 PCM.

    This deliberately bypasses native WAV readers. Callers use it when a
    decoder-specific fallback must exercise FFmpeg rather than whichever
    native reader happens to accept the container.
    """

    return _load_with_ffmpeg(Path(path))


def _load_with_torchcodec(path: Path) -> tuple[Tensor, int, str]:
    import torch
    from torchcodec.decoders import AudioDecoder

    decoded = AudioDecoder(str(path), num_channels=1).get_all_samples()
    if decoded.data.ndim != 2 or decoded.data.shape[0] != 1:
        raise RuntimeError(
            f"TorchCodec produced an unexpected mono audio shape: {decoded.data.shape}"
        )
    audio = decoded.data[0]
    if audio.dtype != torch.float32:
        raise RuntimeError(
            f"TorchCodec produced an unexpected audio dtype: {audio.dtype}"
        )
    if audio.numel() == 0:
        raise RuntimeError("TorchCodec produced no decoded audio")
    sample_rate = int(decoded.sample_rate)
    if sample_rate <= 0:
        raise RuntimeError("TorchCodec produced an invalid sample rate")
    return (
        audio,
        sample_rate,
        "torchcodec 0.16 decode (num_channels=1)",
    )


def _load_with_ffmpeg(path: Path, *, target_sample_rate: int | None = None) -> tuple[np.ndarray, int, str]:
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError(f"ffmpeg executable not found on PATH or {FFMPEG_ENV_VAR}")
    sample_rate = int(target_sample_rate) if target_sample_rate is not None else _source_sample_rate(path, ffmpeg_path=ffmpeg)
    if sample_rate <= 0:
        raise ValueError("target_sample_rate must be greater than zero")
    command = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        FFMPEG_ARITHMETIC_MONO_FILTER,
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
    ]
    if target_sample_rate is not None:
        command.extend(["-ar", str(sample_rate)])
    command.append("-")
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(_invalid_audio_stream_message(stderr or f"ffmpeg exited with status {error.returncode}")) from error
    if not result.stdout:
        raise RuntimeError(_invalid_audio_stream_message("ffmpeg produced no decoded audio"))
    usable = len(result.stdout) - (len(result.stdout) % np.dtype(np.float32).itemsize)
    if usable <= 0:
        raise RuntimeError(_invalid_audio_stream_message("ffmpeg produced an incomplete float32 audio buffer"))
    audio = np.frombuffer(result.stdout[:usable], dtype=np.float32)
    detail = (
        "ffmpeg decode (arithmetic channel mean)"
        if target_sample_rate is None
        else f"ffmpeg decode @ {sample_rate} Hz (arithmetic channel mean)"
    )
    return audio.astype(np.float32, copy=False), sample_rate, detail


def _invalid_audio_stream_message(detail: str | None = None) -> str:
    detail = (detail or "").strip()
    if detail:
        return f"{INVALID_AUDIO_STREAM_MESSAGE}: {detail}"
    return INVALID_AUDIO_STREAM_MESSAGE


def _source_sample_rate(path: Path, *, ffmpeg_path: str) -> int:
    sample_rate = _source_sample_rate_from_file_metadata(path)
    if sample_rate is not None:
        return sample_rate
    sample_rate = _source_sample_rate_from_ffprobe(path, ffmpeg_path=ffmpeg_path)
    if sample_rate is not None:
        return sample_rate
    raise RuntimeError(_invalid_audio_stream_message())


def _source_sample_rate_from_file_metadata(path: Path) -> int | None:
    if path.suffix.lower() in {".wav", ".wave"}:
        try:
            with wave.open(str(path), "rb") as audio:
                sample_rate = int(audio.getframerate())
            if sample_rate > 0:
                return sample_rate
        except Exception:
            pass

    try:
        audio = MutagenFile(path)
    except Exception:
        return None
    info = getattr(audio, "info", None)
    sample_rate = getattr(info, "sample_rate", None)
    try:
        sample_rate = int(sample_rate)
    except (TypeError, ValueError):
        return None
    return sample_rate if sample_rate > 0 else None


def _source_sample_rate_from_ffprobe(path: Path, *, ffmpeg_path: str) -> int | None:
    ffprobe = _ffprobe_path(ffmpeg_path)
    if not ffprobe:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError):
        return None
    first_line = (result.stdout or b"").decode("utf-8", errors="replace").strip().splitlines()
    if not first_line:
        return None
    try:
        sample_rate = int(first_line[0].strip())
    except ValueError:
        return None
    return sample_rate if sample_rate > 0 else None


def _ffmpeg_path() -> str | None:
    configured = os.environ.get(FFMPEG_ENV_VAR)
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def _ffprobe_path(ffmpeg_path: str) -> str | None:
    resolved_ffmpeg = Path(ffmpeg_path)
    for name in ("ffprobe.exe", "ffprobe"):
        candidate = resolved_ffmpeg.with_name(name)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffprobe")

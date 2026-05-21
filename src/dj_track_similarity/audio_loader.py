from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import wave

import numpy as np

from .dependencies import FFMPEG_ENV_VAR

DEFAULT_FFMPEG_SAMPLE_RATE = 16_000


def load_audio_mono(
    path: str | Path,
    *,
    torchaudio_module: object | None = None,
    target_sample_rate: int | None = None,
) -> tuple[np.ndarray, int, str]:
    audio_path = Path(path)
    errors: list[str] = []
    if torchaudio_module is not None:
        try:
            return _load_with_torchaudio(audio_path, torchaudio_module)
        except Exception as error:
            errors.append(f"torchaudio: {error}")

    if audio_path.suffix.lower() in {".wav", ".wave"}:
        try:
            return _load_with_wave(audio_path)
        except Exception as error:
            errors.append(f"wave: {error}")

    try:
        audio, sample_rate, detail = _load_with_ffmpeg(audio_path, target_sample_rate=target_sample_rate)
        if errors:
            detail = f"{detail}; native decoders failed ({'; '.join(errors)})"
        return audio, sample_rate, detail
    except Exception as error:
        errors.append(f"ffmpeg: {error}")

    detail = "; ".join(errors) if errors else "no decoder available"
    raise RuntimeError(f"Unable to decode audio: {audio_path} ({detail})")


def _load_with_torchaudio(path: Path, torchaudio_module: object) -> tuple[np.ndarray, int, str]:
    waveform, sample_rate = torchaudio_module.load(str(path))
    audio = _tensor_to_numpy(waveform)
    if audio.ndim == 2:
        audio = audio.mean(axis=0)
    elif audio.ndim != 1:
        raise RuntimeError(f"Unsupported decoded audio shape: {audio.shape}")
    return audio.astype(np.float32, copy=False), int(sample_rate), "native torchaudio decode"


def _load_with_ffmpeg(path: Path, *, target_sample_rate: int | None = None) -> tuple[np.ndarray, int, str]:
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError(f"ffmpeg executable not found on PATH or {FFMPEG_ENV_VAR}")
    sample_rate = int(target_sample_rate or DEFAULT_FFMPEG_SAMPLE_RATE)
    command = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-",
    ]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"ffmpeg exited with status {error.returncode}") from error
    if not result.stdout:
        raise RuntimeError("ffmpeg produced no decoded audio")
    usable = len(result.stdout) - (len(result.stdout) % np.dtype(np.float32).itemsize)
    if usable <= 0:
        raise RuntimeError("ffmpeg produced an incomplete float32 audio buffer")
    audio = np.frombuffer(result.stdout[:usable], dtype=np.float32)
    return audio.astype(np.float32, copy=False), sample_rate, "ffmpeg decode"


def _ffmpeg_path() -> str | None:
    configured = os.environ.get(FFMPEG_ENV_VAR)
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def _load_with_wave(path: Path) -> tuple[np.ndarray, int, str]:
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        raw = audio.readframes(audio.getnframes())
    samples = _decode_pcm_bytes(raw, sample_width, channels)
    return samples, sample_rate, "native wave decode"


def _decode_pcm_bytes(raw: bytes, sample_width: int, channels: int) -> np.ndarray:
    usable = len(raw) - (len(raw) % (channels * sample_width))
    raw = raw[:usable]
    if not raw:
        raise RuntimeError("no PCM samples found")
    if sample_width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = data[:, 0].astype(np.int32) | (data[:, 1].astype(np.int32) << 8) | (data[:, 2].astype(np.int32) << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        samples = values.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"unsupported PCM sample width: {sample_width}")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32, copy=False)


def _tensor_to_numpy(value: object) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)

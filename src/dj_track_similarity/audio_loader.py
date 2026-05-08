from __future__ import annotations

from pathlib import Path
import wave

import numpy as np


def load_audio_mono(path: str | Path, *, torchaudio_module: object | None = None) -> tuple[np.ndarray, int, str]:
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
            audio, sample_rate, detail = _recover_malformed_wav(audio_path)
            if errors:
                detail = f"{detail}; native decoders failed ({'; '.join(errors)})"
            return audio, sample_rate, detail
        except Exception as error:
            errors.append(f"wav recovery: {error}")

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


def _load_with_wave(path: Path) -> tuple[np.ndarray, int, str]:
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        sample_rate = audio.getframerate()
        raw = audio.readframes(audio.getnframes())
    samples = _decode_pcm_bytes(raw, sample_width, channels)
    return samples, sample_rate, "native wave decode"


def _recover_malformed_wav(path: Path) -> tuple[np.ndarray, int, str]:
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("not a RIFF/WAVE file")

    fmt = _read_fmt_chunk(data)
    data_start = _find_recoverable_data_payload_start(data, fmt["block_align"])
    raw = data[data_start:]
    usable = len(raw) - (len(raw) % fmt["block_align"])
    if usable <= 0:
        raise RuntimeError("recovered data chunk has no aligned PCM payload")
    samples = _decode_pcm_bytes(raw[:usable], fmt["sample_width"], fmt["channels"])
    return (
        samples,
        fmt["sample_rate"],
        f"recovered malformed WAV PCM from offset {data_start} ({usable / 1_000_000:.1f} MB)",
    )


def _read_fmt_chunk(data: bytes) -> dict[str, int]:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        payload_start = pos + 8
        payload_end = payload_start + chunk_size
        if chunk_id == b"fmt ":
            if chunk_size < 16 or payload_end > len(data):
                raise RuntimeError("invalid fmt chunk")
            payload = data[payload_start:payload_end]
            audio_format = int.from_bytes(payload[0:2], "little")
            channels = int.from_bytes(payload[2:4], "little")
            sample_rate = int.from_bytes(payload[4:8], "little")
            block_align = int.from_bytes(payload[12:14], "little")
            bits_per_sample = int.from_bytes(payload[14:16], "little")
            sample_width = bits_per_sample // 8
            if audio_format != 1:
                raise RuntimeError(f"unsupported WAV format code {audio_format}")
            if channels <= 0 or sample_rate <= 0 or block_align <= 0 or sample_width not in {1, 2, 3, 4}:
                raise RuntimeError("invalid PCM fmt values")
            return {
                "channels": channels,
                "sample_rate": sample_rate,
                "block_align": block_align,
                "sample_width": sample_width,
            }
        chunk_end = payload_end + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data):
            break
        pos = chunk_end
    raise RuntimeError("fmt chunk not found")


def _find_recoverable_data_payload_start(data: bytes, block_align: int) -> int:
    start = 12
    while True:
        marker = data.find(b"data", start)
        if marker == -1:
            raise RuntimeError("data marker not found")
        size_start = marker + 4
        payload_start = marker + 8
        if payload_start <= len(data):
            declared_size = int.from_bytes(data[size_start:payload_start], "little")
            remaining = len(data) - payload_start
            if remaining > 0 and remaining >= min(declared_size, block_align):
                return payload_start
            if remaining > 0 and remaining >= block_align:
                return payload_start
        start = marker + 1


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

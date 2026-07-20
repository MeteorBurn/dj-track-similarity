from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import subprocess
import wave

from mutagen import File as MutagenFile
import numpy as np

from .dependencies import FFMPEG_ENV_VAR
from .logging_config import analysis_diagnostics_enabled

LOGGER = logging.getLogger(__name__)
INVALID_AUDIO_STREAM_MESSAGE = "Invalid audio stream: ffmpeg could not decode audio"
SONARA_DECODE_SAMPLE_RATE = 22_050


@dataclass(frozen=True)
class DecodedAudio:
    path: str
    audio: np.ndarray
    sample_rate: int
    detail: str


def load_decoded_audio(path: str | Path) -> DecodedAudio:
    audio_path = Path(path)
    if _is_mono_wave(audio_path):
        try:
            audio, sample_rate, detail = _load_with_wave(audio_path)
            return DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail=detail)
        except Exception as error:
            _log_decoder_failure("wave", audio_path, error)
    audio, sample_rate, detail = _load_with_ffmpeg(audio_path)
    return DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail=detail)


def load_sonara_decoded_audio(path: str | Path) -> DecodedAudio:
    """Decode the standalone SONARA job directly to its required mono PCM rate."""
    audio, sample_rate, detail = _load_with_ffmpeg(Path(path), target_sample_rate=SONARA_DECODE_SAMPLE_RATE)
    return DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail=detail)


def load_audio_mono(
    path: str | Path,
    *,
    torchaudio_module: object | None = None,
) -> tuple[np.ndarray, int, str]:
    audio_path = Path(path)
    errors: list[str] = []
    if torchaudio_module is not None:
        try:
            return _load_with_torchaudio(audio_path, torchaudio_module)
        except Exception as error:
            errors.append(f"torchaudio: {error}")
            _log_decoder_failure("torchaudio", audio_path, error)

    if audio_path.suffix.lower() in {".wav", ".wave"}:
        try:
            audio, sample_rate, detail = _load_with_wave(audio_path)
            if errors:
                _log_decoder_fallback_success("wave", audio_path, sample_rate, errors)
            return audio, sample_rate, detail
        except Exception as error:
            errors.append(f"wave: {error}")
            _log_decoder_failure("wave", audio_path, error)

    try:
        audio, sample_rate, detail = _load_with_ffmpeg(audio_path)
        if errors:
            detail = f"{detail}; native decoders failed ({'; '.join(errors)})"
            _log_decoder_fallback_success("ffmpeg", audio_path, sample_rate, errors)
        return audio, sample_rate, detail
    except Exception as error:
        errors.append(f"ffmpeg: {error}")
        _log_decoder_failure("ffmpeg", audio_path, error)

    detail = "; ".join(errors) if errors else "no decoder available"
    raise RuntimeError(f"Unable to decode audio: {audio_path} ({detail})")


def _log_decoder_failure(decoder: str, path: Path, error: Exception) -> None:
    if analysis_diagnostics_enabled():
        LOGGER.warning("Audio decoder failed decoder=%s path=%s error=%s", decoder, path, error)


def _log_decoder_fallback_success(decoder: str, path: Path, sample_rate: int, errors: list[str]) -> None:
    if analysis_diagnostics_enabled():
        LOGGER.warning(
            "Audio decode fallback succeeded decoder=%s path=%s sample_rate=%s failed_decoders=%s",
            decoder,
            path,
            sample_rate,
            "; ".join(errors),
        )


def torch_compatible_audio(audio: np.ndarray) -> np.ndarray:
    prepared = np.asarray(audio, dtype=np.float32)
    if not prepared.flags.writeable:
        return prepared.copy()
    return prepared


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
    detail = "ffmpeg decode" if target_sample_rate is None else f"ffmpeg decode @ {sample_rate} Hz"
    return audio.astype(np.float32, copy=False), sample_rate, detail


def _invalid_audio_stream_message(detail: str | None = None) -> str:
    detail = (detail or "").strip()
    if detail:
        return f"{INVALID_AUDIO_STREAM_MESSAGE}: {detail}"
    return INVALID_AUDIO_STREAM_MESSAGE


def _is_mono_wave(path: Path) -> bool:
    if path.suffix.lower() not in {".wav", ".wave"}:
        return False
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnchannels() == 1
    except Exception:
        return False


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

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torch import Tensor
from ..audio.loader import DecodedAudio

_RESAMPLER_LOCK = threading.RLock()

_RESAMPLERS: dict[tuple[int, int], object] = {}

def _prepare_windows(
    decoded_items: Sequence[DecodedAudio],
    *,
    target_rate: int,
    window_seconds: float,
    max_windows: int,
    pad: str,
    torch,
    torchaudio,
    model_label: str,
) -> tuple[list[list[int]], list, float]:
    """Decode-side windowing for adapters that select fixed waveform excerpts.

    MERT keeps a short track as a variable-length numpy window. MuQ zero-pads
    its windows and stacks the resulting tensors on the inference device.
    """

    if pad not in {"none", "zero"}:
        raise ValueError(f"unsupported window padding: {pad!r}")
    window_size = max(1, int(target_rate * window_seconds))
    track_windows: list[list[int]] = []
    all_windows: list = []
    prepare_started = time.perf_counter()
    for decoded in decoded_items:
        waveform = decoded.audio.to(dtype=torch.float32).unsqueeze(0)
        if decoded.sample_rate != target_rate:
            if torchaudio is None:
                raise RuntimeError(
                    f"{model_label} shared-audio analysis requires "
                    f"torchaudio resampling: {decoded.path}"
                )
            waveform = _resample_to(
                waveform,
                source_rate=decoded.sample_rate,
                target_rate=target_rate,
                torchaudio=torchaudio,
            ).to(dtype=torch.float32)
        waveform = waveform.squeeze(0).to(dtype=torch.float32)
        windows = _select_windows_torch(
            waveform,
            target_rate,
            window_seconds,
            max_windows,
            torch,
        )
        if not windows:
            raise ValueError(f"No audio windows could be extracted: {decoded.path}")
        window_indices: list[int] = []
        for window in windows:
            window_indices.append(len(all_windows))
            if pad == "zero":
                all_windows.append(
                    _pad_or_trim_audio_tensor(window, window_size, torch)
                )
            else:
                all_windows.append(window.cpu().numpy())
        track_windows.append(window_indices)
    return track_windows, all_windows, time.perf_counter() - prepare_started

def _pad_or_trim_audio_tensor(audio: Tensor, target_samples: int, torch) -> Tensor:
    window = audio.reshape(-1).to(dtype=torch.float32)
    if window.numel() > target_samples:
        return window[:target_samples]
    if window.numel() < target_samples:
        return torch.nn.functional.pad(window, (0, target_samples - window.numel()))
    return window

def _resample_to(waveform, *, source_rate: int, target_rate: int, torchaudio):
    """Resample through the kernel cached for this rate pair."""

    key = (int(source_rate), int(target_rate))
    resampler = _RESAMPLERS.get(key)
    if resampler is None:
        with _RESAMPLER_LOCK:
            resampler = _RESAMPLERS.get(key)
            if resampler is None:
                resampler = torchaudio.transforms.Resample(key[0], key[1])
                _RESAMPLERS[key] = resampler
    return resampler(waveform)

def _select_windows_torch(waveform, sample_rate: int, window_seconds: float, max_windows: int, torch):
    window_size = max(1, int(sample_rate * window_seconds))
    total = int(waveform.shape[-1])
    if total <= window_size:
        return [waveform]
    usable_start = int(total * 0.1)
    usable_end = int(total * 0.9)
    usable = max(window_size, usable_end - usable_start)
    if max_windows <= 1:
        starts = [usable_start + max(0, (usable - window_size) // 2)]
    else:
        starts = torch.linspace(usable_start, max(usable_start, usable_end - window_size), steps=max_windows).round().to(torch.int64).tolist()
    return [waveform[start : start + window_size] for start in starts]

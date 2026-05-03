from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np


class EmbeddingAdapter(Protocol):
    model_name: str
    dim: int

    def embed(self, path: str | Path) -> np.ndarray:
        ...

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        ...


class FakeEmbeddingAdapter:
    model_name = "fake-model"
    dim = 3

    def embed(self, path: str | Path) -> np.ndarray:
        digest = sum(bytearray(Path(path).as_posix().encode("utf-8")))
        vector = np.array([(digest % 17) + 1, (digest % 31) + 1, (digest % 43) + 1], dtype=np.float32)
        return vector / np.linalg.norm(vector)

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        return [self.embed(path) for path in paths]


class MertEmbeddingAdapter:
    model_name = "m-a-p/MERT-v1-95M"
    dim = 768

    def __init__(self, device: str | None = None, window_seconds: float = 5.0, max_windows: int = 5) -> None:
        self.device_name = device
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self._model = None
        self._processor = None
        self._torch = None
        self._torchaudio = None
        self.device = device

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None and self._processor is not None

        target_rate = int(self._processor.sampling_rate)
        track_windows: list[list[int]] = []
        all_windows = []
        for path in paths:
            waveform, sample_rate = torchaudio.load(str(path))
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            if sample_rate != target_rate:
                waveform = torchaudio.transforms.Resample(sample_rate, target_rate)(waveform)
            waveform = waveform.squeeze(0)
            windows = _select_windows_torch(waveform, target_rate, self.window_seconds, self.max_windows, torch)
            if not windows:
                raise ValueError(f"No audio windows could be extracted: {path}")
            window_indices = []
            for window in windows:
                window_indices.append(len(all_windows))
                all_windows.append(window.cpu().numpy())
            track_windows.append(window_indices)

        pooled_windows: list[np.ndarray] = []
        for start in range(0, len(all_windows), 16):
            window_batch = all_windows[start : start + 16]
            inputs = self._processor(window_batch, sampling_rate=target_rate, padding=True, return_tensors="pt")
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            with torch.no_grad():
                outputs = self._model(**inputs, output_hidden_states=True)
            hidden = torch.stack(outputs.hidden_states[-4:]).mean(dim=0)
            pooled = hidden.mean(dim=1).detach().cpu().numpy().astype(np.float32)
            pooled_windows.extend([pooled[index] for index in range(pooled.shape[0])])

        vectors = []
        for path, indices in zip(paths, track_windows):
            vector = np.mean(np.vstack([pooled_windows[index] for index in indices]), axis=0).astype(np.float32)
            norm = np.linalg.norm(vector)
            if norm == 0:
                raise ValueError(f"Model produced a zero vector: {path}")
            vectors.append(vector / norm)
        return vectors

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from transformers import AutoModel, Wav2Vec2FeatureExtractor

        self._torch = torch
        self._torchaudio = torchaudio
        self._processor = Wav2Vec2FeatureExtractor.from_pretrained(self.model_name, trust_remote_code=True)
        self.device = self._device()
        self._model = AutoModel.from_pretrained(self.model_name, trust_remote_code=True)
        self._model = self._model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        if self.device_name:
            return self.device_name
        return "cuda" if self._torch.cuda.is_available() else "cpu"


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

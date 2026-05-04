from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np


class EmbeddingAdapter(Protocol):
    embedding_key: str
    model_name: str
    dim: int

    def embed(self, path: str | Path) -> np.ndarray:
        ...

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        ...


class FakeEmbeddingAdapter:
    embedding_key = "mert"
    model_name = "fake-model"
    dim = 3

    def embed(self, path: str | Path) -> np.ndarray:
        digest = sum(bytearray(Path(path).as_posix().encode("utf-8")))
        vector = np.array([(digest % 17) + 1, (digest % 31) + 1, (digest % 43) + 1], dtype=np.float32)
        return vector / np.linalg.norm(vector)

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        return [self.embed(path) for path in paths]


class MertEmbeddingAdapter:
    embedding_key = "mert"
    model_name = "m-a-p/MERT-v1-95M"
    dim = 768

    def __init__(
        self,
        device: str | None = None,
        window_seconds: float = 5.0,
        max_windows: int = 5,
        inference_batch_size: int = 16,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._model = None
        self._processor = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None

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
        for start in range(0, len(all_windows), self.inference_batch_size):
            window_batch = all_windows[start : start + self.inference_batch_size]
            inputs = self._processor(window_batch, sampling_rate=target_rate, padding=True, return_tensors="pt")
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            with torch.inference_mode():
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
            if self.device_name == "cuda" and not self._torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
            return self.device_name
        return "cuda" if self._torch.cuda.is_available() else "cpu"


class ClapEmbeddingAdapter:
    embedding_key = "clap"
    model_name = "laion/clap-htsat-fused"
    dim = 512

    def __init__(
        self,
        device: str | None = None,
        window_seconds: float = 10.0,
        max_windows: int = 5,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._model = None
        self._processor = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None and self._processor is not None

        target_rate = int(getattr(self._processor.feature_extractor, "sampling_rate", 48000))
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
        for start in range(0, len(all_windows), self.inference_batch_size):
            batch = all_windows[start : start + self.inference_batch_size]
            inputs = _call_clap_audio_processor(self._processor, batch, target_rate)
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            with torch.inference_mode():
                features = self._model.get_audio_features(**inputs)
            pooled_windows.extend(_normalize_rows(features.detach().cpu().numpy().astype(np.float32)))

        vectors: list[np.ndarray] = []
        for indices in track_windows:
            vector = np.mean(np.vstack([pooled_windows[index] for index in indices]), axis=0).astype(np.float32)
            norm = np.linalg.norm(vector)
            if norm == 0:
                raise ValueError("Model produced a zero vector")
            vectors.append(vector / norm)
        return vectors

    def embed_text(self, text: str) -> np.ndarray:
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None and self._processor is not None
        inputs = self._processor(text=[text], return_tensors="pt", padding=True)
        inputs = {key: value.to(self._device()) for key, value in inputs.items()}
        with torch.inference_mode():
            features = self._model.get_text_features(**inputs)
        return _normalize_rows(features.detach().cpu().numpy().astype(np.float32))[0]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from transformers import ClapModel, ClapProcessor

        self._torch = torch
        self._torchaudio = torchaudio
        self._processor = ClapProcessor.from_pretrained(self.model_name)
        self.device = self._device()
        self._model = ClapModel.from_pretrained(self.model_name)
        self._model = self._model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        if self.device_name:
            if self.device_name == "cuda" and not self._torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
            return self.device_name
        return "cuda" if self._torch.cuda.is_available() else "cpu"


def adapter_factories():
    return {
        "mert": MertEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
        "fake": FakeEmbeddingAdapter,
    }


def adapter_embedding_key(adapter_name: str) -> str:
    factory = adapter_factories().get(adapter_name)
    return str(getattr(factory, "embedding_key", adapter_name)) if factory else adapter_name


def _normalize_rows(matrix: np.ndarray) -> list[np.ndarray]:
    vectors = []
    for row in matrix:
        vector = np.asarray(row, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError("Model produced a zero vector")
        vectors.append(vector / norm)
    return vectors


def _call_clap_audio_processor(processor, batch: list[np.ndarray], sampling_rate: int):
    return processor(audio=batch, sampling_rate=sampling_rate, return_tensors="pt", padding=True)


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

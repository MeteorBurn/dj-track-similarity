from __future__ import annotations

from pathlib import Path
import time
from typing import Protocol

import numpy as np

from .audio_loader import DecodedAudio, load_audio_mono, torch_compatible_audio
from .runtime import select_torch_device


class EmbeddingAdapter(Protocol):
    embedding_key: str
    model_name: str
    dim: int

    def embed(self, path: str | Path) -> np.ndarray:
        ...

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        ...


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
        self.last_batch_timing: dict[str, float | int] = {}

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None and self._processor is not None

        target_rate = int(self._processor.sampling_rate)
        decode_seconds = 0.0
        decoded_items: list[DecodedAudio] = []
        for path in paths:
            decode_started = time.perf_counter()
            audio, sample_rate, _decode_detail = load_audio_mono(
                path,
                torchaudio_module=torchaudio,
            )
            decode_seconds += time.perf_counter() - decode_started
            decoded_items.append(DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail="adapter decode"))
        return self._embed_decoded_items(decoded_items, target_rate=target_rate, decode_seconds=decode_seconds)

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        assert self._processor is not None
        return self._embed_decoded_items(decoded_items, target_rate=int(self._processor.sampling_rate), decode_seconds=0.0)

    def _embed_decoded_items(self, decoded_items: list[DecodedAudio], *, target_rate: int, decode_seconds: float) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None and self._processor is not None
        track_windows: list[list[int]] = []
        all_windows = []
        prepare_started = time.perf_counter()
        for decoded in decoded_items:
            waveform = torch.from_numpy(torch_compatible_audio(decoded.audio)).unsqueeze(0)
            if decoded.sample_rate != target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"MERT shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = torchaudio.transforms.Resample(decoded.sample_rate, target_rate)(waveform)
            waveform = waveform.squeeze(0)
            windows = _select_windows_torch(waveform, target_rate, self.window_seconds, self.max_windows, torch)
            if not windows:
                raise ValueError(f"No audio windows could be extracted: {decoded.path}")
            window_indices = []
            for window in windows:
                window_indices.append(len(all_windows))
                all_windows.append(window.cpu().numpy())
            track_windows.append(window_indices)
        prepare_seconds = time.perf_counter() - prepare_started

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            window_batch = all_windows[start : start + self.inference_batch_size]
            inputs = self._processor(window_batch, sampling_rate=target_rate, padding=True, return_tensors="pt")
            inputs = {key: value.to(self._device()) for key, value in inputs.items()}
            with torch.inference_mode():
                outputs = self._model(**inputs, output_hidden_states=True)
            hidden = torch.stack(outputs.hidden_states[-4:]).mean(dim=0)
            attention_mask = inputs.get("attention_mask")
            feature_mask_for = getattr(self._model, "_get_feature_vector_attention_mask", None)
            if attention_mask is not None and callable(feature_mask_for):
                feature_mask = feature_mask_for(hidden.shape[1], attention_mask)
                pooled_tensor = _masked_time_mean(hidden, feature_mask)
            else:
                pooled_tensor = hidden.mean(dim=1)
            pooled = pooled_tensor.detach().cpu().numpy().astype(np.float32)
            pooled_windows.extend([pooled[index] for index in range(pooled.shape[0])])
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "decode_seconds": decode_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        vectors = []
        for decoded, indices in zip(decoded_items, track_windows):
            vector = np.mean(np.vstack([pooled_windows[index] for index in indices]), axis=0).astype(np.float32)
            norm = np.linalg.norm(vector)
            if norm == 0:
                raise ValueError(f"Model produced a zero vector: {decoded.path}")
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
        return select_torch_device(self._torch, self.requested_device)


class MuqEmbeddingAdapter:
    embedding_key = "muq"
    model_name = "OpenMuQ/MuQ-large-msd-iter"
    dim = 1024
    target_rate = 24_000

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
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

        decode_seconds = 0.0
        decoded_items: list[DecodedAudio] = []
        for path in paths:
            decode_started = time.perf_counter()
            audio, sample_rate, _decode_detail = load_audio_mono(
                path,
                torchaudio_module=torchaudio,
            )
            decode_seconds += time.perf_counter() - decode_started
            decoded_items.append(DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail="adapter decode"))
        return self._embed_decoded_items(decoded_items, decode_seconds=decode_seconds)

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(decoded_items, decode_seconds=0.0)

    def _embed_decoded_items(self, decoded_items: list[DecodedAudio], *, decode_seconds: float) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        window_size = max(1, int(self.target_rate * self.window_seconds))
        track_windows: list[list[int]] = []
        all_windows: list[np.ndarray] = []
        prepare_started = time.perf_counter()
        for decoded in decoded_items:
            waveform = torch.from_numpy(torch_compatible_audio(decoded.audio)).to(dtype=torch.float32).unsqueeze(0)
            if decoded.sample_rate != self.target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"MuQ shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = torchaudio.transforms.Resample(decoded.sample_rate, self.target_rate)(waveform).to(dtype=torch.float32)
            waveform = waveform.squeeze(0).to(dtype=torch.float32)
            windows = _select_windows_torch(waveform, self.target_rate, self.window_seconds, self.max_windows, torch)
            if not windows:
                raise ValueError(f"No audio windows could be extracted: {decoded.path}")
            window_indices = []
            for window in windows:
                window_indices.append(len(all_windows))
                all_windows.append(_pad_or_trim_audio_window(window.detach().cpu().numpy(), window_size))
            track_windows.append(window_indices)
        prepare_seconds = time.perf_counter() - prepare_started

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            batch = np.stack(all_windows[start : start + self.inference_batch_size]).astype(np.float32)
            wavs = torch.from_numpy(batch).to(device=self._device(), dtype=torch.float32)
            with torch.inference_mode():
                outputs = self._model(wavs, output_hidden_states=True)
            hidden = getattr(outputs, "last_hidden_state", None)
            if hidden is None:
                raise ValueError("MuQ model output does not include last_hidden_state")
            pooled_tensor = hidden.mean(dim=1)
            pooled_windows.extend(_normalize_rows(pooled_tensor.detach().cpu().numpy().astype(np.float32)))
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "decode_seconds": decode_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        vectors: list[np.ndarray] = []
        for indices in track_windows:
            vector = np.mean(np.vstack([pooled_windows[index] for index in indices]), axis=0).astype(np.float32)
            norm = np.linalg.norm(vector)
            if not np.isfinite(norm) or norm == 0:
                raise ValueError("Model produced a zero vector")
            vectors.append(vector / norm)
        return vectors

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from muq import MuQ

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        self._model = MuQ.from_pretrained(self.model_name)
        to_float = getattr(self._model, "float", None)
        if callable(to_float):
            self._model = to_float()
        self._model = self._model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


class ClapEmbeddingAdapter:
    embedding_key = "clap"
    checkpoint_repo = "lukewys/laion_clap"
    checkpoint_filename = "music_audioset_epoch_15_esc_90.14.pt"
    model_name = f"{checkpoint_repo}/{checkpoint_filename}"
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
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def embed(self, path: str | Path) -> np.ndarray:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[str | Path]) -> list[np.ndarray]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

        target_rate = 48_000
        decode_seconds = 0.0
        decoded_items: list[DecodedAudio] = []
        for path in paths:
            decode_started = time.perf_counter()
            audio, sample_rate, _decode_detail = load_audio_mono(
                path,
                torchaudio_module=torchaudio,
            )
            decode_seconds += time.perf_counter() - decode_started
            decoded_items.append(DecodedAudio(path=str(path), audio=audio, sample_rate=sample_rate, detail="adapter decode"))
        return self._embed_decoded_items(decoded_items, target_rate=target_rate, decode_seconds=decode_seconds)

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(decoded_items, target_rate=48_000, decode_seconds=0.0)

    def _embed_decoded_items(self, decoded_items: list[DecodedAudio], *, target_rate: int, decode_seconds: float) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        window_size = max(1, int(target_rate * self.window_seconds))
        track_windows: list[list[int]] = []
        all_windows = []
        prepare_started = time.perf_counter()
        for decoded in decoded_items:
            waveform = torch.from_numpy(torch_compatible_audio(decoded.audio)).unsqueeze(0)
            if decoded.sample_rate != target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"CLAP shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = torchaudio.transforms.Resample(decoded.sample_rate, target_rate)(waveform)
            waveform = waveform.squeeze(0)
            windows = _select_windows_torch(waveform, target_rate, self.window_seconds, self.max_windows, torch)
            if not windows:
                raise ValueError(f"No audio windows could be extracted: {decoded.path}")
            window_indices = []
            for window in windows:
                window_indices.append(len(all_windows))
                all_windows.append(_repeatpad_or_trim_audio_window(window.cpu().numpy(), window_size))
            track_windows.append(window_indices)
        prepare_seconds = time.perf_counter() - prepare_started

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            batch = np.stack(all_windows[start : start + self.inference_batch_size]).astype(np.float32)
            with torch.inference_mode():
                features = self._model.get_audio_embedding_from_data(x=batch, use_tensor=False)
            pooled_windows.extend(_normalize_rows(_array_output_to_numpy(features)))
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "decode_seconds": decode_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

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
        assert torch is not None and self._model is not None
        with torch.inference_mode():
            features = self._model.get_text_embedding([text], use_tensor=False)
        return _normalize_rows(_array_output_to_numpy(features))[0]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        import laion_clap
        from huggingface_hub import hf_hub_download

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        checkpoint_path = hf_hub_download(repo_id=self.checkpoint_repo, filename=self.checkpoint_filename)
        self._model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base", device=torch.device(self.device))
        self._model.load_ckpt(checkpoint_path)

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


def adapter_factories():
    return {
        "mert": MertEmbeddingAdapter,
        "muq": MuqEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
    }


def adapter_embedding_key(adapter_name: str) -> str:
    factory = adapter_factories().get(adapter_name)
    return str(getattr(factory, "embedding_key", adapter_name)) if factory else adapter_name


def _normalize_rows(matrix: np.ndarray) -> list[np.ndarray]:
    vectors = []
    for row in matrix:
        vector = np.asarray(row, dtype=np.float32).reshape(-1)
        if not np.isfinite(vector).all():
            raise ValueError("Model produced a non-finite vector")
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("Model produced a zero vector")
        vectors.append(vector / norm)
    return vectors


def _masked_time_mean(hidden, feature_mask):
    if tuple(feature_mask.shape) != tuple(hidden.shape[:2]):
        raise ValueError(
            f"MERT feature mask shape {tuple(feature_mask.shape)} does not match hidden states {tuple(hidden.shape[:2])}"
        )
    mask = feature_mask.to(device=hidden.device, dtype=hidden.dtype).unsqueeze(-1)
    counts = mask.sum(dim=1).clamp_min(1.0)
    return (hidden * mask).sum(dim=1) / counts


def _array_output_to_numpy(output) -> np.ndarray:
    if hasattr(output, "detach"):
        output = output.detach().cpu().numpy()
    return np.asarray(output, dtype=np.float32)


def _pad_or_trim_audio_window(audio: np.ndarray, target_samples: int) -> np.ndarray:
    window = np.asarray(audio, dtype=np.float32).reshape(-1)
    if window.shape[0] > target_samples:
        return window[:target_samples]
    if window.shape[0] < target_samples:
        return np.pad(window, (0, target_samples - window.shape[0]))
    return window


def _repeatpad_or_trim_audio_window(audio: np.ndarray, target_samples: int) -> np.ndarray:
    window = np.asarray(audio, dtype=np.float32).reshape(-1)
    if window.shape[0] > target_samples:
        return window[:target_samples]
    if window.shape[0] == target_samples:
        return window
    if window.shape[0] == 0:
        return np.zeros(target_samples, dtype=np.float32)
    repeat_count = int(target_samples / window.shape[0])
    repeated = np.tile(window, repeat_count)
    if repeated.shape[0] < target_samples:
        repeated = np.pad(repeated, (0, target_samples - repeated.shape[0]))
    return repeated[:target_samples].astype(np.float32, copy=False)


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

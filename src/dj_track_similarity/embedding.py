from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import importlib
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING
import warnings

import numpy as np

if TYPE_CHECKING:
    from torch import Tensor

from .analysis_models import (
    CLAP_ADAPTER_REVISION,
    CLAP_CHECKPOINT_ID,
    CLAP_MODEL_NAME,
    CLAP_MODEL_REVISION,
    CLAP_PREPROCESSING,
    CLAP_TEXT_MODEL_NAME,
    CLAP_TEXT_MODEL_REVISION,
    CLAP_TEXT_SNAPSHOT_SHA256,
    MAEST_ADAPTER_REVISION,
    MAEST_CHECKPOINT_ID,
    MAEST_MODEL_NAME,
    MAEST_MODEL_VERSION,
    MAEST_PREPROCESSING,
    MERT_ADAPTER_REVISION,
    MERT_CHECKPOINT_ID,
    MERT_MODEL_NAME,
    MERT_MODEL_REVISION,
    MERT_PREPROCESSING,
    MERT_SNAPSHOT_SHA256,
    MUQ_ADAPTER_REVISION,
    MUQ_CHECKPOINT_ID,
    MUQ_MODEL_NAME,
    MUQ_MODEL_REVISION,
    MUQ_PREPROCESSING,
    MUQ_SNAPSHOT_SHA256,
    MULAN_ADAPTER_REVISION,
    MULAN_CHECKPOINT_ID,
    MULAN_MODEL_NAME,
    MULAN_MODEL_REVISION,
    MULAN_PREPROCESSING,
    MULAN_SNAPSHOT_SHA256,
    MULAN_TEXT_MODEL_NAME,
    MULAN_TEXT_MODEL_REVISION,
    MULAN_TEXT_SNAPSHOT_SHA256,
)
from .audio_loader import DecodedAudio
from .genres import rank_maest_genres
from .maest_windows import (
    MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS,
    MAEST_WINDOW_POSITIONS,
    MaestWindowContext,
    select_maest_window_starts,
)
from .runtime import select_torch_device
from .verified_assets import (
    VerifiedAssetBinding,
    bind_verified_file,
    bind_verified_snapshot,
)


_CLAP_CONSTRUCTION_LOCK = threading.RLock()
# Pinning MuQ-MuLan rebinds attributes on the shared ``muq`` package, so every
# construction that reads them has to serialise against it.
_MUQ_CONSTRUCTION_LOCK = threading.RLock()

# torchaudio's Resample is a module whose constructor builds the filter kernel,
# and every adapter built one per track. A library holds a handful of source
# rates, so a full run rebuilt the same few kernels tens of thousands of times
# per family. The kernel depends only on the rate pair, so a cached instance
# returns identical samples.
_RESAMPLER_LOCK = threading.RLock()
_RESAMPLERS: dict[tuple[int, int], object] = {}
_MUQ_WEIGHT_NORM_WARNING_SILENCED = False


@dataclass(frozen=True)
class MaestAnalysisResult:
    genres: list[dict[str, float | str]]
    embedding: np.ndarray


class MaestEmbeddingAdapter:
    embedding_key = "maest"
    adapter_revision = MAEST_ADAPTER_REVISION
    model_name = MAEST_MODEL_NAME
    checkpoint_release = "v0.0.0-beta"
    checkpoint_filename = "discogs-maest-30s-pw-129e-519l-swa.ckpt"
    checkpoint_url = (
        "https://github.com/palonso/MAEST/releases/download/"
        f"{checkpoint_release}/{checkpoint_filename}"
    )
    checkpoint_id = MAEST_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    model_version = MAEST_MODEL_VERSION
    preprocessing = MAEST_PREPROCESSING
    dim = 768
    target_rate = 16_000
    input_seconds = 30.0
    analysis_window_positions = MAEST_WINDOW_POSITIONS
    pooling = "distilled-token-mean+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"

    def __init__(
        self,
        device: str | None = None,
        top_k: int = 3,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = (
            None if self.requested_device == "auto" else self.requested_device
        )
        self.top_k = max(1, int(top_k))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "input_seconds": self.input_seconds,
            "analysis_window_positions": self.analysis_window_positions,
            "top_k": self.top_k,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "structure-aware-main-range-centered-20-50-80",
            "window_context": "sonara-current-generation-optional",
            "window_fallback": "main-range->non-silent-range->full-duration",
            "window_dedup_tolerance_seconds": MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS,
            "short_audio": "right-zero-pad-to-30s",
            "model_input": "raw-waveform-melspectrogram-input-false",
            "score_activation": "sigmoid-logits",
            "score_pooling": "window-mean-then-top-k",
            "dtype": "float32",
            "device_precision": "float32-eval",
            "checkpoint_release": self.checkpoint_release,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def analyze_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        window_contexts: Sequence[MaestWindowContext | None] | None = None,
    ) -> list[MaestAnalysisResult]:
        self._load_model()
        torch = self._torch
        assert torch is not None
        contexts = (
            [None] * len(decoded_items)
            if window_contexts is None
            else list(window_contexts)
        )
        if len(contexts) != len(decoded_items):
            raise ValueError("MAEST window context count does not match track count")

        prepared: list[object] = []
        window_track_indexes: list[int] = []
        prepare_started = time.perf_counter()
        for track_index, (decoded, context) in enumerate(zip(decoded_items, contexts)):
            windows = self._prepare_audio_windows_from_audio(
                decoded.path,
                decoded.audio,
                decoded.sample_rate,
                window_context=context,
            )
            prepared.extend(windows)
            window_track_indexes.extend([track_index] * len(windows))
        prepare_seconds = time.perf_counter() - prepare_started
        return self._analyze_prepared_batch(
            prepared,
            window_track_indexes,
            expected_tracks=len(decoded_items),
            prepare_seconds=prepare_seconds,
        )

    def _analyze_prepared_batch(
        self,
        prepared: Sequence[object],
        window_track_indexes: Sequence[int],
        *,
        expected_tracks: int,
        prepare_seconds: float,
    ) -> list[MaestAnalysisResult]:
        torch = self._torch
        assert torch is not None and self._model is not None
        device = self._device()
        _move_maest_runtime_modules(self._model, device)

        score_rows: list[list[float]] = []
        embedding_rows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        with torch.inference_mode():
            for start in range(0, len(prepared), self.inference_batch_size):
                chunk = prepared[start : start + self.inference_batch_size]
                audio_batch = torch.stack(chunk, dim=0).to(device)
                logits, embeddings = self._model(
                    audio_batch,
                    melspectrogram_input=False,
                )
                score_rows.extend(
                    _maest_score_rows(
                        torch.sigmoid(logits),
                        expected_rows=len(chunk),
                    )
                )
                embedding_rows.extend(
                    _maest_embedding_rows(embeddings, expected_rows=len(chunk))
                )
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": expected_tracks,
            "windows": len(prepared),
        }

        labels = [str(label) for label in getattr(self._model, "labels")]
        genres_by_track = rank_maest_genres(
            labels,
            score_rows,
            window_track_indexes,
            expected_tracks=expected_tracks,
            top_k=self.top_k,
        )
        averaged_embeddings = _average_maest_embeddings(
            embedding_rows,
            window_track_indexes,
            expected_tracks=expected_tracks,
        )
        return [
            MaestAnalysisResult(
                genres=genres,
                embedding=embedding,
            )
            for genres, embedding in zip(genres_by_track, averaged_embeddings)
        ]

    def _prepare_audio_windows_from_audio(
        self,
        path: str | Path,
        audio_values: Tensor,
        sample_rate: int,
        *,
        window_context: MaestWindowContext | None = None,
    ) -> list[object]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None
        audio = audio_values.to(dtype=torch.float32).unsqueeze(0)
        if sample_rate != self.target_rate:
            if torchaudio is None:
                raise RuntimeError(
                    "MAEST shared-audio analysis requires torchaudio resampling: "
                    f"{path}"
                )
            audio = _resample_to(
                audio,
                source_rate=sample_rate,
                target_rate=self.target_rate,
                torchaudio=torchaudio,
            )
        audio = audio.squeeze(0)
        target_samples = int(self.target_rate * self.input_seconds)
        if audio.numel() < target_samples:
            return [
                torch.nn.functional.pad(
                    audio,
                    (0, target_samples - audio.numel()),
                )
            ]

        starts = select_maest_window_starts(
            audio.numel() / self.target_rate,
            self.input_seconds,
            window_context,
        )
        windows: list[object] = []
        for start_seconds in starts:
            start = max(0, int(self.target_rate * start_seconds))
            segment = audio[start : start + target_samples]
            if segment.numel() < target_samples:
                segment = torch.nn.functional.pad(
                    segment,
                    (0, target_samples - segment.numel()),
                )
            windows.append(segment)
        return windows or [audio[:target_samples]]

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from maest_infer import get_maest

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        _ensure_verified_maest_checkpoint(
            torch,
            checkpoint_url=self.checkpoint_url,
            checkpoint_filename=self.checkpoint_filename,
            expected_sha256=self.checkpoint_sha256,
        )
        self._model = get_maest(arch=self.model_name).to(self.device).eval()
        _move_maest_runtime_modules(self._model, self.device)

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


class MertEmbeddingAdapter:
    embedding_key = "mert"
    adapter_revision = MERT_ADAPTER_REVISION
    model_name = MERT_MODEL_NAME
    model_revision = MERT_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "pytorch_model.bin"
    checkpoint_id = MERT_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MERT_PREPROCESSING
    dim = 768
    target_rate = 24_000
    hidden_layers = (9, 10, 11, 12)
    pooling = "last-4-layer-mean+masked-time-mean+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = (
        "config.json",
        "configuration_MERT.py",
        "modeling_MERT.py",
        "preprocessor_config.json",
        checkpoint_filename,
    )
    snapshot_sha256 = MERT_SNAPSHOT_SHA256

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

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "max_windows": self.max_windows,
            "hidden_layers": self.hidden_layers,
            "pooling": self.pooling,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "single-variable-length-window",
            "processor_normalization": "wav2vec2-do-normalize",
            "processor_padding": "right-zero-with-attention-mask",
            "dtype": "float32",
            "device_precision": "float32-eval-no-autocast",
            "model_revision": self.model_revision,
            "remote_code_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        assert self._processor is not None
        return self._embed_decoded_items(
            decoded_items,
            target_rate=int(self._processor.sampling_rate),
        )

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
        *,
        target_rate: int,
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None and self._processor is not None
        track_windows: list[list[int]] = []
        all_windows = []
        prepare_started = time.perf_counter()
        for decoded in decoded_items:
            waveform = decoded.audio.to(dtype=torch.float32).unsqueeze(0)
            if decoded.sample_rate != target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"MERT shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = _resample_to(
                    waveform,
                    source_rate=decoded.sample_rate,
                    target_rate=target_rate,
                    torchaudio=torchaudio,
                )
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
        from huggingface_hub import snapshot_download
        from transformers import AutoModel, Wav2Vec2FeatureExtractor

        self._torch = torch
        self._torchaudio = torchaudio
        binding = _download_verified_hf_snapshot(
            snapshot_download,
            repo_id=self.model_name,
            revision=self.model_revision,
            required_files=self.snapshot_files,
            expected_sha256=self.snapshot_sha256,
            checkpoint_filename=self.checkpoint_filename,
            expected_checkpoint_sha256=self.checkpoint_sha256,
        )
        with binding as verified:
            snapshot_path = str(verified.path)
            processor = Wav2Vec2FeatureExtractor.from_pretrained(
                snapshot_path,
                local_files_only=True,
            )
            if int(processor.sampling_rate) != self.target_rate:
                raise RuntimeError(
                    "Local MERT processor sample rate does not match the "
                    "configured adapter input: "
                    f"expected {self.target_rate}, got {processor.sampling_rate}"
                )
            self.device = self._device()
            model = AutoModel.from_pretrained(
                snapshot_path,
                trust_remote_code=True,
                local_files_only=True,
                use_safetensors=False,
            )
        to_float = getattr(model, "float", None)
        if callable(to_float):
            model = to_float()
        self._processor = processor
        self._model = model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


class MuqEmbeddingAdapter:
    embedding_key = "muq"
    adapter_revision = MUQ_ADAPTER_REVISION
    model_name = MUQ_MODEL_NAME
    model_revision = MUQ_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "model.safetensors"
    checkpoint_id = MUQ_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MUQ_PREPROCESSING
    dim = 1024
    target_rate = 24_000
    pooling = "last-hidden-time-mean+per-window-l2+window-mean+l2"
    dtype = "float32"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = ("config.json", checkpoint_filename)
    snapshot_sha256 = MUQ_SNAPSHOT_SHA256

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

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "max_windows": self.max_windows,
            "pooling": self.pooling,
            "dtype": self.dtype,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "right-zero-pad-to-window",
            "device_precision": "float32-eval-no-autocast-no-compile",
            "model_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(decoded_items)

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        track_windows, all_windows, prepare_seconds = _prepare_muq_compatible_windows(
            decoded_items,
            target_rate=self.target_rate,
            window_seconds=self.window_seconds,
            max_windows=self.max_windows,
            torch=torch,
            torchaudio=torchaudio,
            model_label="MuQ",
        )

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            wavs = torch.stack(
                all_windows[start : start + self.inference_batch_size],
                dim=0,
            ).to(device=self._device(), dtype=torch.float32)
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
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }

        return _average_l2_window_embeddings(pooled_windows, track_windows)

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from huggingface_hub import snapshot_download
        import muq

        _silence_muq_weight_norm_deprecation()
        self._torch = torch
        self._torchaudio = torchaudio
        binding = _download_verified_hf_snapshot(
            snapshot_download,
            repo_id=self.model_name,
            revision=self.model_revision,
            required_files=self.snapshot_files,
            expected_sha256=self.snapshot_sha256,
            checkpoint_filename=self.checkpoint_filename,
            expected_checkpoint_sha256=self.checkpoint_sha256,
        )
        with binding as verified, _MUQ_CONSTRUCTION_LOCK:
            # Read under the lock: MuQ-MuLan construction rebinds this
            # attribute to a proxy that only accepts its own snapshot.
            MuQ = muq.MuQ
            self.device = self._device()
            model = MuQ.from_pretrained(
                str(verified.path),
                local_files_only=True,
            )
        to_float = getattr(model, "float", None)
        if callable(to_float):
            model = to_float()
        self._model = model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


class MuqMulanEmbeddingAdapter:
    embedding_key = "mulan"
    adapter_revision = MULAN_ADAPTER_REVISION
    model_name = MULAN_MODEL_NAME
    model_revision = MULAN_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "model.safetensors"
    checkpoint_id = MULAN_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = MULAN_PREPROCESSING
    dim = 512
    target_rate = 24_000
    pooling = "mulan-audio-latent+per-window-l2+window-mean+l2"
    dtype = "float32"
    encoding = "float32-le"
    normalization = "l2"
    snapshot_files = ("config.json", checkpoint_filename)
    snapshot_sha256 = MULAN_SNAPSHOT_SHA256
    text_model_name = MULAN_TEXT_MODEL_NAME
    text_model_revision = MULAN_TEXT_MODEL_REVISION
    text_snapshot_files = tuple(
        file_name for file_name, _digest in MULAN_TEXT_SNAPSHOT_SHA256
    )
    text_snapshot_sha256 = MULAN_TEXT_SNAPSHOT_SHA256
    text_checkpoint_filename = "model.safetensors"
    text_checkpoint_sha256 = dict(text_snapshot_sha256)[text_checkpoint_filename]
    audio_model_name = MUQ_MODEL_NAME
    audio_model_revision = MUQ_MODEL_REVISION
    audio_snapshot_files = tuple(
        file_name for file_name, _digest in MUQ_SNAPSHOT_SHA256
    )
    audio_snapshot_sha256 = MUQ_SNAPSHOT_SHA256
    audio_checkpoint_filename = "model.safetensors"
    audio_checkpoint_sha256 = dict(audio_snapshot_sha256)[
        audio_checkpoint_filename
    ]

    def __init__(
        self,
        device: str | None = None,
        window_seconds: float = 10.0,
        max_windows: int = 5,
        inference_batch_size: int = 8,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = (
            None if self.requested_device == "auto" else self.requested_device
        )
        self.window_seconds = window_seconds
        self.max_windows = max_windows
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "max_windows": self.max_windows,
            "pooling": self.pooling,
            "dtype": self.dtype,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "right-zero-pad-to-window",
            "device_precision": "float32-eval-no-autocast-no-compile",
            "model_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files,
            "snapshot_sha256": self.snapshot_sha256,
            "text_model_name": self.text_model_name,
            "text_model_revision": self.text_model_revision,
            "text_snapshot_files": self.text_snapshot_files,
            "text_snapshot_sha256": self.text_snapshot_sha256,
            "text_loader_policy": (
                "verified-private-snapshot-local-files-only"
            ),
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(
        self,
        decoded_items: list[DecodedAudio],
    ) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(decoded_items)

    def embed_text(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[np.ndarray]:
        """Embed a prompt bank one prompt per forward pass.

        The upstream text tower pads a batch to its longest prompt and then
        mean-pools its own transformer over every position, padding included,
        so a batched vector shifts with whatever else shares the batch
        (measured cosine 0.9952 against the unbatched vector). One prompt per
        forward keeps a prompt's vector identical in every bank it appears in.
        """

        prompts = list(texts)
        if not prompts:
            return []
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None
        embedded: list[np.ndarray] = []
        for prompt in prompts:
            with torch.inference_mode():
                output = self._model(texts=[prompt])
            embedded.extend(
                _normalized_embedding_rows(
                    output,
                    expected_rows=1,
                    expected_dim=self.dim,
                    model_label="MuQ-MuLan text",
                )
            )
        return embedded

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        track_windows, all_windows, prepare_seconds = _prepare_muq_compatible_windows(
            decoded_items,
            target_rate=self.target_rate,
            window_seconds=self.window_seconds,
            max_windows=self.max_windows,
            torch=torch,
            torchaudio=torchaudio,
            model_label="MuQ-MuLan",
        )

        pooled_windows: list[np.ndarray] = []
        inference_started = time.perf_counter()
        for start in range(0, len(all_windows), self.inference_batch_size):
            wavs = torch.stack(
                all_windows[start : start + self.inference_batch_size],
                dim=0,
            ).to(
                device=self._device(),
                dtype=torch.float32,
            )
            with torch.inference_mode():
                output = self._model(wavs=wavs)
            pooled_windows.extend(
                _normalized_embedding_rows(
                    output,
                    expected_rows=int(wavs.shape[0]),
                    expected_dim=self.dim,
                    model_label="MuQ-MuLan audio",
                )
            )
        inference_seconds = time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": len(all_windows),
        }
        return _average_l2_window_embeddings(pooled_windows, track_windows)

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from huggingface_hub import snapshot_download
        from muq import MuQMuLan

        _silence_muq_weight_norm_deprecation()
        self._torch = torch
        self._torchaudio = torchaudio
        with ExitStack() as assets:
            verified = assets.enter_context(
                _download_verified_hf_snapshot(
                    snapshot_download,
                    repo_id=self.model_name,
                    revision=self.model_revision,
                    required_files=self.snapshot_files,
                    expected_sha256=self.snapshot_sha256,
                    checkpoint_filename=self.checkpoint_filename,
                    expected_checkpoint_sha256=self.checkpoint_sha256,
                )
            )
            verified_text_snapshot = assets.enter_context(
                _download_verified_hf_snapshot(
                    snapshot_download,
                    repo_id=self.text_model_name,
                    revision=self.text_model_revision,
                    required_files=self.text_snapshot_files,
                    expected_sha256=self.text_snapshot_sha256,
                    checkpoint_filename=self.text_checkpoint_filename,
                    expected_checkpoint_sha256=self.text_checkpoint_sha256,
                )
            )
            verified_audio_snapshot = assets.enter_context(
                _download_verified_hf_snapshot(
                    snapshot_download,
                    repo_id=self.audio_model_name,
                    revision=self.audio_model_revision,
                    required_files=self.audio_snapshot_files,
                    expected_sha256=self.audio_snapshot_sha256,
                    checkpoint_filename=self.audio_checkpoint_filename,
                    expected_checkpoint_sha256=self.audio_checkpoint_sha256,
                )
            )
            self.device = self._device()
            model = _construct_muq_mulan_with_pinned_towers(
                MuQMuLan,
                snapshot_path=verified.path,
                text_snapshot_path=verified_text_snapshot.path,
                audio_snapshot_path=verified_audio_snapshot.path,
            )
        to_float = getattr(model, "float", None)
        if callable(to_float):
            model = to_float()
        self._model = model.to(self.device).eval()

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


class ClapEmbeddingAdapter:
    embedding_key = "clap"
    checkpoint_repo = "lukewys/laion_clap"
    checkpoint_filename = "music_audioset_epoch_15_esc_90.14.pt"
    adapter_revision = CLAP_ADAPTER_REVISION
    model_name = CLAP_MODEL_NAME
    model_revision = CLAP_MODEL_REVISION
    model_version = model_revision
    checkpoint_id = CLAP_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = CLAP_PREPROCESSING
    dim = 512
    target_rate = 48_000
    amodel = "HTSAT-base"
    tmodel = "roberta"
    enable_fusion = False
    pooling = "clap-audio+per-window-l2+window-mean+l2"
    encoding = "float32-le"
    normalization = "l2"
    text_model_name = CLAP_TEXT_MODEL_NAME
    text_model_revision = CLAP_TEXT_MODEL_REVISION
    text_snapshot_files = tuple(
        file_name for file_name, _digest in CLAP_TEXT_SNAPSHOT_SHA256
    )
    text_snapshot_sha256 = CLAP_TEXT_SNAPSHOT_SHA256
    text_checkpoint_filename = "model.safetensors"
    text_checkpoint_sha256 = dict(text_snapshot_sha256)[text_checkpoint_filename]

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

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "window_seconds": self.window_seconds,
            "max_windows": self.max_windows,
            "pooling": self.pooling,
            "amodel": self.amodel,
            "tmodel": self.tmodel,
            "enable_fusion": self.enable_fusion,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "repeat-whole-window-then-right-zero-pad",
            "input_quantization": "laion-clap-float32-int16-float32",
            "text_model_class": "RobertaModel",
            "text_tokenizer_class": "RobertaTokenizer",
            "text_loader_policy": (
                "verified-private-snapshot-local-files-only"
            ),
            "dtype": "float32",
            "device_precision": "fp32-eval",
            "model_revision": self.model_revision,
            "checkpoint_filename": self.checkpoint_filename,
            "text_model_name": self.text_model_name,
            "text_model_revision": self.text_model_revision,
            "text_snapshot_files": self.text_snapshot_files,
            "text_snapshot_sha256": self.text_snapshot_sha256,
        }

    def preflight(self) -> None:
        """Verify model assets and construct the configured loader."""

        self._load_model()

    def embed_decoded_batch(self, decoded_items: list[DecodedAudio]) -> list[np.ndarray]:
        self._load_model()
        return self._embed_decoded_items(
            decoded_items,
            target_rate=self.target_rate,
        )

    def _embed_decoded_items(
        self,
        decoded_items: list[DecodedAudio],
        *,
        target_rate: int,
    ) -> list[np.ndarray]:
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and self._model is not None
        window_size = max(1, int(target_rate * self.window_seconds))
        track_windows: list[list[int]] = []
        all_windows = []
        prepare_started = time.perf_counter()
        for decoded in decoded_items:
            waveform = decoded.audio.to(dtype=torch.float32).unsqueeze(0)
            if decoded.sample_rate != target_rate:
                if torchaudio is None:
                    raise RuntimeError(f"CLAP shared-audio analysis requires torchaudio resampling: {decoded.path}")
                waveform = _resample_to(
                    waveform,
                    source_rate=decoded.sample_rate,
                    target_rate=target_rate,
                    torchaudio=torchaudio,
                )
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
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[np.ndarray]:
        """Embed a whole prompt bank in one forward pass."""

        prompts = list(texts)
        if not prompts:
            return []
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None
        with torch.inference_mode():
            features = self._model.get_text_embedding(prompts, use_tensor=False)
        return _normalized_embedding_rows(
            features,
            expected_rows=len(prompts),
            expected_dim=self.dim,
            model_label="CLAP text",
        )

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        import laion_clap
        from huggingface_hub import hf_hub_download, snapshot_download
        from transformers import RobertaModel, RobertaTokenizer

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        with ExitStack() as assets:
            verified_checkpoint = assets.enter_context(
                _download_verified_hf_checkpoint(
                    hf_hub_download,
                    repo_id=self.checkpoint_repo,
                    filename=self.checkpoint_filename,
                    revision=self.model_revision,
                    expected_sha256=self.checkpoint_sha256,
                )
            )
            verified_text_snapshot = assets.enter_context(
                _download_verified_hf_snapshot(
                    snapshot_download,
                    repo_id=self.text_model_name,
                    revision=self.text_model_revision,
                    required_files=self.text_snapshot_files,
                    expected_sha256=self.text_snapshot_sha256,
                    checkpoint_filename=self.text_checkpoint_filename,
                    expected_checkpoint_sha256=self.text_checkpoint_sha256,
                )
            )
            model = _construct_clap_module_with_pinned_text_model(
                laion_clap.CLAP_Module,
                tokenizer_loader=RobertaTokenizer,
                model_loader=RobertaModel,
                snapshot_path=verified_text_snapshot.path,
                enable_fusion=self.enable_fusion,
                amodel=self.amodel,
                tmodel=self.tmodel,
                device=torch.device(self.device),
            )
            model.load_ckpt(str(verified_checkpoint.path), verbose=False)
        self._model = model

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


def _silence_muq_weight_norm_deprecation() -> None:
    """muq builds its conformer with the deprecated torch weight_norm helper."""

    global _MUQ_WEIGHT_NORM_WARNING_SILENCED
    if _MUQ_WEIGHT_NORM_WARNING_SILENCED:
        return
    warnings.filterwarnings(
        "ignore",
        message=r".*torch\.nn\.utils\.weight_norm.* is deprecated.*",
        category=FutureWarning,
    )
    _MUQ_WEIGHT_NORM_WARNING_SILENCED = True


def _ensure_verified_maest_checkpoint(
    torch_module,
    *,
    checkpoint_url: str,
    checkpoint_filename: str,
    expected_sha256: str,
) -> Path:
    """Populate and verify the torch-hub cache before maest-infer loads it."""

    checkpoint_dir = Path(torch_module.hub.get_dir()) / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / checkpoint_filename
    if not checkpoint_path.exists():
        torch_module.hub.download_url_to_file(
            checkpoint_url,
            str(checkpoint_path),
            hash_prefix=expected_sha256,
            progress=True,
        )
    _verify_checkpoint_sha256(
        checkpoint_path,
        expected_sha256=expected_sha256,
        description=checkpoint_url,
    )
    return checkpoint_path


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    melspectrogram = getattr(model, "melspectrogram", None)
    if melspectrogram is None and callable(init_melspectrogram):
        init_melspectrogram()
    melspectrogram = getattr(model, "melspectrogram", None)
    move = getattr(melspectrogram, "to", None)
    if callable(move):
        move(device)


def _maest_score_rows(values: object, *, expected_rows: int) -> list[list[float]]:
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()

    shape = getattr(values, "shape", None)
    if shape is not None and len(shape) >= 2:
        rows = [
            [float(score) for score in row] for row in values  # type: ignore[union-attr]
        ]
        if len(rows) != expected_rows:
            raise ValueError(
                "MAEST batch output shape does not match the requested batch size"
            )
        return rows

    flat = _maest_float_list(values)
    if expected_rows == 1:
        return [flat]
    raise ValueError("MAEST batch output shape does not include per-track rows")


def _maest_float_list(values: object) -> list[float]:
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()
    reshape = getattr(values, "reshape", None)
    if callable(reshape):
        values = reshape(-1)
    return [float(value) for value in values]  # type: ignore[union-attr]


def _maest_embedding_rows(
    values: object,
    *,
    expected_rows: int,
) -> list[np.ndarray]:
    if values is None:
        raise ValueError("MAEST model did not return embeddings")
    detach = getattr(values, "detach", None)
    if callable(detach):
        values = detach()
    cpu = getattr(values, "cpu", None)
    if callable(cpu):
        values = cpu()
    numpy = getattr(values, "numpy", None)
    if callable(numpy):
        values = numpy()
    array = np.asarray(values, dtype=np.float32)
    if array.ndim == 3:
        array = array.mean(axis=1)
    if array.ndim != 2:
        raise ValueError(f"Unsupported MAEST embedding shape: {array.shape}")
    if array.shape[0] != expected_rows:
        raise ValueError(
            "MAEST embedding row count does not match audio window count"
        )
    return [array[index].astype(np.float32, copy=True) for index in range(array.shape[0])]


def _average_maest_embeddings(
    rows: Sequence[np.ndarray],
    window_track_indexes: Sequence[int],
    *,
    expected_tracks: int,
) -> list[np.ndarray]:
    grouped: dict[int, list[np.ndarray]] = defaultdict(list)
    for row, track_index in zip(rows, window_track_indexes):
        grouped[track_index].append(row)

    embeddings: list[np.ndarray] = []
    for track_index in range(expected_tracks):
        track_rows = grouped.get(track_index, [])
        if not track_rows:
            raise ValueError("MAEST did not produce embeddings for every track")
        vector = np.mean(np.vstack(track_rows), axis=0).astype(np.float32)
        if not np.isfinite(vector).all():
            raise ValueError("MAEST model produced non-finite embeddings")
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 0.0:
            raise ValueError("MAEST model produced a zero embedding")
        embeddings.append(np.asarray(vector / norm, dtype=np.float32))
    return embeddings


def adapter_factories():
    return {
        "maest": MaestEmbeddingAdapter,
        "mert": MertEmbeddingAdapter,
        "muq": MuqEmbeddingAdapter,
        "mulan": MuqMulanEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
    }


def _download_verified_hf_checkpoint(
    download,
    *,
    repo_id: str,
    filename: str,
    revision: str,
    expected_sha256: str,
) -> VerifiedAssetBinding:
    """Resolve and privately bind one exact Hub file for deserialization."""

    checkpoint_path = str(
        download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            local_files_only=False,
        )
    )
    path = Path(checkpoint_path)
    _verify_checkpoint_sha256(
        path,
        expected_sha256=expected_sha256,
        description=f"{repo_id}@{revision}/{filename}",
    )
    return bind_verified_file(
        path,
        expected_sha256=expected_sha256,
        description=f"{repo_id}@{revision}/{filename}",
    )


def _construct_clap_module_with_pinned_text_model(
    clap_module_type,
    *,
    tokenizer_loader,
    model_loader,
    snapshot_path: Path,
    enable_fusion: bool,
    amodel: str,
    tmodel: str,
    device,
):
    """Construct laion-clap without permitting its floating RoBERTa loads."""

    with _CLAP_CONSTRUCTION_LOCK:
        hook_module = importlib.import_module(clap_module_type.__module__)
        create_model = getattr(hook_module, "create_model", None)
        create_model_globals = getattr(create_model, "__globals__", None)
        clap_model_type = (
            create_model_globals.get("CLAP")
            if isinstance(create_model_globals, dict)
            else None
        )
        if clap_model_type is None:
            raise RuntimeError(
                "Pinned laion-clap internals do not expose the expected CLAP "
                "model constructor"
            )
        clap_model_module = importlib.import_module(
            clap_model_type.__module__
        )

        original_tokenizer_loader = getattr(
            hook_module,
            "RobertaTokenizer",
            None,
        )
        original_model_loader = getattr(
            clap_model_module,
            "RobertaModel",
            None,
        )
        if not callable(
            getattr(original_tokenizer_loader, "from_pretrained", None)
        ):
            raise RuntimeError(
                "Pinned laion-clap internals do not expose RobertaTokenizer"
            )
        if not callable(
            getattr(original_model_loader, "from_pretrained", None)
        ):
            raise RuntimeError(
                "Pinned laion-clap internals do not expose RobertaModel"
            )

        tokenizer_proxy = _local_only_from_pretrained_proxy(
            tokenizer_loader,
            snapshot_path=snapshot_path,
            expected_source=CLAP_TEXT_MODEL_NAME,
            description="CLAP RobertaTokenizer",
        )
        model_proxy = _local_only_from_pretrained_proxy(
            model_loader,
            snapshot_path=snapshot_path,
            expected_source=CLAP_TEXT_MODEL_NAME,
            description="CLAP RobertaModel",
        )

        hook_module.RobertaTokenizer = tokenizer_proxy
        clap_model_module.RobertaModel = model_proxy
        try:
            return clap_module_type(
                enable_fusion=enable_fusion,
                amodel=amodel,
                tmodel=tmodel,
                device=device,
            )
        finally:
            hook_module.RobertaTokenizer = original_tokenizer_loader
            clap_model_module.RobertaModel = original_model_loader


def _construct_muq_mulan_with_pinned_towers(
    mulan_module_type,
    *,
    snapshot_path: Path,
    text_snapshot_path: Path,
    audio_snapshot_path: Path,
):
    """Construct MuQ-MuLan without permitting its floating tower loads.

    The upstream text tower resolves ``xlm-roberta-base`` from the ambient Hub
    cache twice: the encoder while the model is built, and the tokenizer lazily
    on the first text embedding. The audio tower resolves
    ``OpenMuQ/MuQ-large-msd-iter`` the same way, through the ``muq`` package
    namespace. All three are bound to their verified snapshots here, and the
    tokenizer is materialised while that binding is still installed so no later
    call can reach the Hub.
    """

    with _MUQ_CONSTRUCTION_LOCK:
        text_module = importlib.import_module("muq.muq_mulan.models.text")
        muq_module = importlib.import_module("muq")
        original_tokenizer_loader = getattr(text_module, "AutoTokenizer", None)
        original_model_loader = getattr(text_module, "XLMRobertaModel", None)
        original_audio_loader = getattr(muq_module, "MuQ", None)
        if not callable(
            getattr(original_tokenizer_loader, "from_pretrained", None)
        ):
            raise RuntimeError(
                "Pinned muq internals do not expose AutoTokenizer"
            )
        if not callable(getattr(original_model_loader, "from_pretrained", None)):
            raise RuntimeError(
                "Pinned muq internals do not expose XLMRobertaModel"
            )
        if not callable(getattr(original_audio_loader, "from_pretrained", None)):
            raise RuntimeError("Pinned muq internals do not expose MuQ")

        text_module.AutoTokenizer = _local_only_from_pretrained_proxy(
            original_tokenizer_loader,
            snapshot_path=text_snapshot_path,
            expected_source=MULAN_TEXT_MODEL_NAME,
            description="MuQ-MuLan XLM-R tokenizer",
        )
        text_module.XLMRobertaModel = _local_only_from_pretrained_proxy(
            original_model_loader,
            snapshot_path=text_snapshot_path,
            expected_source=MULAN_TEXT_MODEL_NAME,
            description="MuQ-MuLan XLM-R encoder",
        )
        muq_module.MuQ = _local_only_from_pretrained_proxy(
            original_audio_loader,
            snapshot_path=audio_snapshot_path,
            expected_source=MUQ_MODEL_NAME,
            description="MuQ-MuLan audio tower",
        )
        try:
            model = mulan_module_type.from_pretrained(
                str(snapshot_path),
                local_files_only=True,
            )
            _materialize_mulan_text_tokenizer(model)
            return model
        finally:
            text_module.AutoTokenizer = original_tokenizer_loader
            text_module.XLMRobertaModel = original_model_loader
            muq_module.MuQ = original_audio_loader


def _materialize_mulan_text_tokenizer(model: object) -> None:
    """Load the lazy tokenizer while the verified loaders are still bound."""

    mulan = getattr(model, "mulan_module", None)
    text_tower = getattr(mulan, "text", None)
    if text_tower is None or not hasattr(text_tower, "tokenizer"):
        raise RuntimeError(
            "Pinned muq internals do not expose the MuQ-MuLan text tower"
        )
    if text_tower.tokenizer is None:
        raise RuntimeError(
            "MuQ-MuLan tokenizer did not load from the verified snapshot"
        )


def _local_only_from_pretrained_proxy(
    loader,
    *,
    snapshot_path: Path,
    expected_source: str,
    description: str,
):
    """Return the narrow loader surface expected by pinned laion-clap."""

    load = getattr(loader, "from_pretrained", None)
    if not callable(load):
        raise RuntimeError(f"{description} loader has no from_pretrained")
    verified_path = str(snapshot_path)

    class LocalOnlyLoader:
        @staticmethod
        def from_pretrained(source, *args, **kwargs):
            if source != expected_source:
                raise RuntimeError(
                    f"{description} requested unexpected source {source!r}"
                )
            local_only = kwargs.pop("local_files_only", True)
            if local_only is not True:
                raise RuntimeError(
                    f"{description} attempted a non-local model load"
                )
            return load(
                verified_path,
                *args,
                local_files_only=True,
                **kwargs,
            )

    return LocalOnlyLoader


def _download_verified_hf_snapshot(
    download,
    *,
    repo_id: str,
    revision: str,
    required_files: tuple[str, ...],
    expected_sha256: tuple[tuple[str, str], ...],
    checkpoint_filename: str,
    expected_checkpoint_sha256: str,
) -> VerifiedAssetBinding:
    """Resolve and privately bind every runtime-loaded snapshot asset."""

    snapshot_path = Path(
        download(
            repo_id=repo_id,
            revision=revision,
            allow_patterns=list(required_files),
            local_files_only=False,
        )
    )
    missing = [
        file_name
        for file_name in required_files
        if not (snapshot_path / file_name).is_file()
    ]
    if missing:
        raise RuntimeError(
            "Pinned model snapshot is incomplete for "
            f"{repo_id}@{revision}; missing={missing}"
        )
    expected_by_name = dict(expected_sha256)
    if tuple(expected_by_name) != required_files:
        raise RuntimeError(
            "Pinned model snapshot digest manifest does not match required files "
            f"for {repo_id}@{revision}"
        )
    if expected_by_name.get(checkpoint_filename) != expected_checkpoint_sha256:
        raise RuntimeError(
            "Pinned model snapshot checkpoint digest does not match the "
            f"production checkpoint identity for {repo_id}@{revision}"
        )
    _verify_checkpoint_sha256(
        snapshot_path / checkpoint_filename,
        expected_sha256=expected_checkpoint_sha256,
        description=f"{repo_id}@{revision}/{checkpoint_filename}",
    )
    return bind_verified_snapshot(
        snapshot_path,
        expected_sha256=expected_by_name,
        description=f"{repo_id}@{revision}",
    )


def _verify_checkpoint_sha256(
    path: str | Path,
    *,
    expected_sha256: str,
    description: str,
) -> None:
    checkpoint_path = Path(path)
    if not checkpoint_path.is_file():
        raise RuntimeError(
            f"Pinned checkpoint is unavailable after download: {description} ({checkpoint_path})"
        )
    digest = hashlib.sha256()
    with checkpoint_path.open("rb") as checkpoint:
        for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Pinned checkpoint SHA-256 mismatch for {description}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


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


def _normalized_embedding_rows(
    output,
    *,
    expected_rows: int,
    expected_dim: int,
    model_label: str,
) -> list[np.ndarray]:
    matrix = _array_output_to_numpy(output)
    if matrix.shape != (expected_rows, expected_dim):
        raise ValueError(
            f"{model_label} output shape {matrix.shape} does not match "
            f"({expected_rows}, {expected_dim})"
        )
    return _normalize_rows(matrix)


def _average_l2_window_embeddings(
    pooled_windows: Sequence[np.ndarray],
    track_windows: Sequence[Sequence[int]],
) -> list[np.ndarray]:
    vectors: list[np.ndarray] = []
    for indices in track_windows:
        vector = np.mean(
            np.vstack([pooled_windows[index] for index in indices]),
            axis=0,
        ).astype(np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("Model produced a zero vector")
        vectors.append(vector / norm)
    return vectors


def _prepare_muq_compatible_windows(
    decoded_items: Sequence[DecodedAudio],
    *,
    target_rate: int,
    window_seconds: float,
    max_windows: int,
    torch,
    torchaudio,
    model_label: str,
) -> tuple[list[list[int]], list[Tensor], float]:
    window_size = max(1, int(target_rate * window_seconds))
    track_windows: list[list[int]] = []
    all_windows: list[Tensor] = []
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
        window_indices = []
        for window in windows:
            window_indices.append(len(all_windows))
            all_windows.append(
                _pad_or_trim_audio_tensor(
                    window,
                    window_size,
                    torch,
                )
            )
        track_windows.append(window_indices)
    return track_windows, all_windows, time.perf_counter() - prepare_started


def _pad_or_trim_audio_tensor(audio: Tensor, target_samples: int, torch) -> Tensor:
    window = audio.reshape(-1).to(dtype=torch.float32)
    if window.numel() > target_samples:
        return window[:target_samples]
    if window.numel() < target_samples:
        return torch.nn.functional.pad(window, (0, target_samples - window.numel()))
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

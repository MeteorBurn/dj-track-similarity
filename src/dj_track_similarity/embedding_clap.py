from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .analysis_models import (
    CLAP_ADAPTER_REVISION,
    CLAP_CHECKPOINT_ID,
    CLAP_MODEL_NAME,
    CLAP_MODEL_REVISION,
    CLAP_PREPROCESSING,
    CLAP_TEXT_MODEL_NAME,
    CLAP_TEXT_MODEL_REVISION,
    CLAP_TEXT_SNAPSHOT_SHA256,
)
from .audio_loader import DecodedAudio
from .embedding_audio import _prepare_windows
from .embedding_loading import (
    _download_verified_hf_checkpoint,
    _download_verified_hf_snapshot,
    _local_only_from_pretrained_proxy,
)
from .embedding_numerics import (
    _array_output_to_numpy,
    _normalize_rows,
    _normalized_embedding_rows,
)
from .runtime import select_torch_device

_CLAP_CONSTRUCTION_LOCK = threading.RLock()

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
        track_windows, all_windows, prepare_seconds = _prepare_windows(
            decoded_items,
            target_rate=target_rate,
            window_seconds=self.window_seconds,
            max_windows=self.max_windows,
            pad="repeat",
            torch=torch,
            torchaudio=torchaudio,
            model_label="CLAP",
        )

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

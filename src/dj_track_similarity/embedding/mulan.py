from __future__ import annotations

import importlib
import json
import threading
import time
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..analysis_models import (
    MULAN_ADAPTER_REVISION,
    MULAN_CHECKPOINT_ID,
    MULAN_MODEL_NAME,
    MULAN_MODEL_REVISION,
    MULAN_PREPROCESSING,
    MULAN_SNAPSHOT_SHA256,
    MULAN_TEXT_MODEL_NAME,
    MULAN_TEXT_MODEL_REVISION,
    MULAN_TEXT_SNAPSHOT_SHA256,
    MUQ_MODEL_NAME,
    MUQ_MODEL_REVISION,
    MUQ_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from .audio import _resample_to
from .loading import (
    _bind_verified_local_snapshot,
    _local_only_from_pretrained_proxy,
)
from .muq import _MUQ_CONSTRUCTION_LOCK, _silence_muq_weight_norm_deprecation
from .numerics import _normalized_embedding_rows
from ..runtime import select_torch_device


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
    clip_seconds = 10.0
    pooling = "mulan-audio-latent+per-clip-l2+all-clips-mean+l2"
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
        inference_batch_size: int = 16,
    ) -> None:
        self.requested_device = device or "auto"
        self.device_name = (
            None if self.requested_device == "auto" else self.requested_device
        )
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._load_lock = threading.RLock()
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None
        self.last_batch_timing: dict[str, float | int] = {}

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "adapter_revision": self.adapter_revision,
            "sample_rate_hz": self.target_rate,
            "clip_seconds": self.clip_seconds,
            "inference_batch_size": self.inference_batch_size,
            "audio_input": "full-track",
            "pooling": self.pooling,
            "dtype": self.dtype,
            "channel_downmix": "torchcodec-num-channels-1",
            "decoder": "shared-torchcodec-0.16",
            "resampler": "torchaudio",
            "clip_selection": "upstream-consecutive-nonoverlapping",
            "tail_padding": "upstream-append-track-start-once",
            "clip_batching": "native-audio-latents-bounded-by-inference-batch-size",
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
        vectors: list[np.ndarray] = []
        prepare_seconds = 0.0
        inference_seconds = 0.0
        clip_count = 0
        for decoded in decoded_items:
            prepare_started = time.perf_counter()
            waveform = decoded.audio.to(dtype=torch.float32).unsqueeze(0)
            if waveform.numel() == 0:
                raise ValueError(f"No audio samples could be extracted: {decoded.path}")
            if decoded.sample_rate != self.target_rate:
                if torchaudio is None:
                    raise RuntimeError(
                        "MuQ-MuLan shared-audio analysis requires "
                        f"torchaudio resampling: {decoded.path}"
                    )
                waveform = _resample_to(
                    waveform,
                    source_rate=decoded.sample_rate,
                    target_rate=self.target_rate,
                    torchaudio=torchaudio,
                )
            waveform = waveform.to(
                device=self._device(),
                dtype=torch.float32,
            )
            prepare_seconds += time.perf_counter() - prepare_started

            inference_started = time.perf_counter()
            with torch.inference_mode():
                # Preserve the native clips (including tail wrapping) and
                # per-clip normalization; only bound the audio tower batches.
                clips = self._model._get_all_clips(waveform[0])
                clip_count += len(clips)
                clip_latents = []
                for clip_batch in clips.split(self.inference_batch_size):
                    latents = self._model.mulan_module.get_audio_latents(clip_batch)
                    if tuple(latents.shape) != (len(clip_batch), self.dim):
                        raise ValueError("MuQ-MuLan must return one latent per native clip")
                    clip_latents.append(latents)
                output = torch.cat(clip_latents, dim=0).mean(dim=0, keepdim=True)
                del clips, clip_batch, latents, clip_latents
            vectors.extend(
                _normalized_embedding_rows(
                    output,
                    expected_rows=1,
                    expected_dim=self.dim,
                    model_label="MuQ-MuLan audio",
                )
            )
            inference_seconds += time.perf_counter() - inference_started
        self.last_batch_timing = {
            "prepare_seconds": prepare_seconds,
            "inference_seconds": inference_seconds,
            "tracks": len(decoded_items),
            "windows": clip_count,
        }
        return vectors

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from muq import MuQMuLan

            _silence_muq_weight_norm_deprecation()
            self._torch = torch
            self._torchaudio = torchaudio
            with ExitStack() as assets:
                verified = assets.enter_context(
                    _bind_verified_local_snapshot(
                        model_directory="mulan",
                        repo_id=self.model_name,
                        revision=self.model_revision,
                        required_files=self.snapshot_files,
                        expected_sha256=self.snapshot_sha256,
                        checkpoint_filename=self.checkpoint_filename,
                        expected_checkpoint_sha256=self.checkpoint_sha256,
                    )
                )
                verified_text_snapshot = assets.enter_context(
                    _bind_verified_local_snapshot(
                        model_directory="mulan-text",
                        repo_id=self.text_model_name,
                        revision=self.text_model_revision,
                        required_files=self.text_snapshot_files,
                        expected_sha256=self.text_snapshot_sha256,
                        checkpoint_filename=self.text_checkpoint_filename,
                        expected_checkpoint_sha256=self.text_checkpoint_sha256,
                    )
                )
                verified_audio_snapshot = assets.enter_context(
                    _bind_verified_local_snapshot(
                        model_directory="muq",
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
            model = _load_local_mulan_checkpoint(mulan_module_type, snapshot_path)
            _materialize_mulan_text_tokenizer(model)
            return model
        finally:
            text_module.AutoTokenizer = original_tokenizer_loader
            text_module.XLMRobertaModel = original_model_loader
            muq_module.MuQ = original_audio_loader

def _load_local_mulan_checkpoint(model_type, snapshot_path: Path):
    """Load verified files through PyTorch's weight-norm compatibility hooks.

    Older safetensors.load_model versions compare raw key names before those
    hooks run, rejecting this checkpoint's legacy positional-convolution keys.
    PyTorch performs the conversion and then strictly validates the full state.
    """

    from safetensors.torch import load_file

    with (snapshot_path / "config.json").open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    model = model_type(config=config)
    state_dict = load_file(str(snapshot_path / "model.safetensors"), device="cpu")
    model.load_state_dict(state_dict, strict=True)
    return model.eval()


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

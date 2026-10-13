"""Offline runtime adapted from the pinned SheetSage2 model and window loop.

Upstream: m-a-p/SheetSage2, b83c3d79a6d98bcffaf8f9ed112c90aa887887bc.
The accompanying model LICENSE (CC BY-NC 4.0) and THIRD_PARTY_NOTICES.md
are required local assets. Native tokenizer, grammar, stitching and export stay intact.
"""

from __future__ import annotations

import importlib
import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from transformers import BartConfig
from transformers.models.bart.modeling_bart import BartDecoder, BartLearnedPositionalEmbedding

from .contracts import EmbeddingCancelledError

_PROJECTIONS = ("query_proj", "key_proj", "value_proj", "out_proj")


class _BatchPositions(BartLearnedPositionalEmbedding):
    """BART's learned positions, indexed by each unpadded sequence position."""

    row_positions = None

    def forward(self, input_ids, past_key_values_length=0, position_ids=None):
        if self.row_positions is not None:
            return F.embedding(self.row_positions + self.offset, self.weight)
        return super().forward(input_ids, past_key_values_length, position_ids)


@contextmanager
def _local_modules(sheet_path: Path, base_path: Path):
    """Load already-verified source directly, without a persistent module cache."""
    name = f"_djts_sheetsage2_{uuid.uuid4().hex}"
    package = ModuleType(name)
    package.__path__ = [str(sheet_path), str(base_path)]
    sys.modules[name] = package
    try:
        yield lambda module: importlib.import_module(f"{name}.{module}")
    finally:
        for key in tuple(sys.modules):
            if key == name or key.startswith(name + "."):
                del sys.modules[key]


def load_local_runtime(sheet_path: Path, base_path: Path):
    from safetensors.torch import load_file, load_model

    config = json.loads((sheet_path / "config.json").read_text(encoding="utf-8"))
    base_config = json.loads((base_path / "config.json").read_text(encoding="utf-8"))
    if config["weights_format"] != "adapter" or config["sampling_rate"] != 24_000:
        raise ValueError("SheetSage2 requires its pinned 24 kHz adapter checkpoint")
    for key, expected in config["backbone_config"].items():
        if key in base_config and key not in ("transformers_version", "architectures", "torch_dtype"):
            if base_config[key] != expected:
                raise ValueError(f"SheetSage2 base architecture mismatch: {key}")
    with _local_modules(sheet_path, base_path) as module, torch.device("cpu"):
        tokenizer_class = module("tokenization_sheetsage2").SheetSage2Tokenizer
        generation = module("generation_sheetsage2")
        exports = module("exports_sheetsage2")
        mert_config = module("configuration_mert2").MERT2Config(**base_config)
        mert_config._attn_implementation = "sdpa"
        mert_class = module("modeling_mert2").MERT2Model
        tokenizer = tokenizer_class(config["input_audio_length"], config["time_hz"],
                                    config["tokenizer_schema_version"],
                                    expected_fingerprint=config["tokenizer_fingerprint"])
        if tokenizer.n_tokens != config["vocab_size"]:
            raise ValueError("SheetSage2 tokenizer vocabulary does not match its checkpoint")
        model = SheetSage2Runtime(config, tokenizer).float()
        load_model(model, str(sheet_path / "model.safetensors"), strict=True, device="cpu")
        encoder = mert_class(mert_config).float()
        # Torchaudio's Hann buffer is a storage view, not a tied parameter.
        encoder.load_state_dict(load_file(str(base_path / "model.safetensors"), device="cpu"), strict=True)
        model.encoder = encoder
        model.merge_lora()
        return model.eval().requires_grad_(False), generation, exports


class SheetSage2Runtime(nn.Module):
    """Native weights/operations with explicit BART 5 construction and local loading."""

    def __init__(self, config: dict, tokenizer) -> None:
        super().__init__()
        self.config = SimpleNamespace(**config)
        self.tokenizer = tokenizer
        self.max_output_seq_len = config["max_output_seq_len"]
        width = config["backbone_config"]["hidden_size"]
        self.encoder = None
        self.adapter = nn.Module()
        self.adapter.layers = nn.ModuleList()
        for _ in range(config["backbone_config"]["num_hidden_layers"]):
            layer = nn.Module()
            layer.attn = nn.Module()
            for name in _PROJECTIONS:
                projection = nn.Module()
                projection.lora_A = nn.Linear(width, config["lora_rank"], bias=False)
                projection.lora_B = nn.Linear(config["lora_rank"], width, bias=False)
                setattr(layer.attn, name, projection)
            self.adapter.layers.append(layer)
        self.layer_weight = nn.Parameter(torch.zeros(len(self.adapter.layers) + 1))
        self.encoder_projection = nn.Linear(width, config["hidden_size"])
        decoder_config = BartConfig(
            vocab_size=config["vocab_size"], d_model=config["hidden_size"],
            decoder_layers=config["decoder_layers"], decoder_attention_heads=config["num_attention_heads"],
            decoder_ffn_dim=config["intermediate_size"], max_position_embeddings=self.max_output_seq_len,
            dropout=config["decoder_dropout"], attention_dropout=config["decoder_dropout"],
            activation_dropout=config["decoder_dropout"], activation_function="gelu",
            pad_token_id=config["pad_token_id"], bos_token_id=config["bos_token_id"],
            eos_token_id=config["eos_token_id"], is_encoder_decoder=True, use_cache=True,
        )
        decoder_config._attn_implementation = "sdpa"
        self.token_embedding = nn.Embedding(config["vocab_size"], config["hidden_size"],
                                            padding_idx=config["pad_token_id"])
        self.decoder = BartDecoder(decoder_config)
        positions = _BatchPositions(self.max_output_seq_len, config["hidden_size"])
        positions.weight = self.decoder.embed_positions.weight
        self.decoder.embed_positions = positions
        self.decoder.embed_tokens.weight = self.token_embedding.weight
        self.decoder.gradient_checkpointing_disable()
        self.output_projection = nn.Linear(config["hidden_size"], config["vocab_size"], bias=False)
        self.output_projection.weight = self.token_embedding.weight

    @torch.no_grad()
    def merge_lora(self) -> None:
        if self.encoder is None or self.adapter is None:
            raise RuntimeError("Load the independent MERT encoder and adapters before merging")
        if len(self.encoder.layers) != len(self.adapter.layers):
            raise ValueError("SheetSage2 adapter and encoder layer counts differ")
        scale = self.config.lora_alpha / self.config.lora_rank
        with torch.autocast("cpu", enabled=False):
            for layer, adapter in zip(self.encoder.layers, self.adapter.layers, strict=True):
                for name in _PROJECTIONS:
                    projection, update = getattr(layer.attn, name), getattr(adapter.attn, name)
                    if any(value.device.type != "cpu" or value.dtype != torch.float32
                           for value in (projection.weight, update.lora_A.weight, update.lora_B.weight)):
                        raise ValueError("SheetSage2 LoRA must be merged on CPU in float32")
                    projection.weight.add_((update.lora_B.weight @ update.lora_A.weight) * scale)
        self.adapter = None

    def encode_and_pool(self, audio, *, window_start, accept_start, accept_end, cancelled=None):
        memory, sums, weights, valid = self.encode_and_pool_batch(
            audio, window_starts=[window_start], accept_starts=[accept_start],
            accept_ends=[accept_end], sample_lengths=[audio.shape[1]], cancelled=cancelled,
        )
        if not valid[0]:
            raise ValueError("SheetSage2 produced invalid hidden states or decoder memory")
        return memory, sums[0], weights[0]

    def encode_and_pool_batch(self, audio, *, window_starts, accept_starts, accept_ends,
                              sample_lengths, cancelled=None):
        if self.encoder is None or self.adapter is not None:
            raise RuntimeError("SheetSage2 encoder is not loaded and merged")
        if audio.ndim != 2 or audio.shape[0] < 1:
            raise ValueError("SheetSage2 requires a batch of waveforms")
        samples = audio.shape[1]
        full_samples = round(self.config.input_audio_length * self.config.sampling_rate)
        if not self.encoder.config.minimum_input_samples <= samples <= full_samples:
            raise ValueError("SheetSage2 audio length is outside its encoder window")
        _check_cancelled(cancelled)
        waveform = F.pad(audio.float(), (0, full_samples - samples))
        stride = self.encoder.config.inputs_to_logits_ratio
        if full_samples % stride:
            waveform = F.pad(waveform, (0, stride - full_samples % stride))
        mel = self.encoder.feature_extractor(waveform)
        weight_dtype = self.encoder.subsampling_module[0].convnext_layers[0].depthwise_block[1].weight.dtype
        hidden = self.encoder.subsampling_module(mel.to(dtype=weight_dtype))
        weights = torch.softmax(self.layer_weight, dim=0)
        mixed = hidden * weights[0]
        positions = self.encoder.embed_positions(hidden)
        frame_weights = np.stack([
            accepted_frame_weights(hidden.shape[1], stride / self.config.sampling_rate, start,
                                   accept_start, accept_end, length / self.config.sampling_rate)
            for start, accept_start, accept_end, length in
            zip(window_starts, accept_starts, accept_ends, sample_lengths, strict=True)
        ])
        weight_sum = frame_weights.sum(axis=1)
        if np.any(weight_sum <= 0):
            raise ValueError("SheetSage2 accepted region contains no valid encoder frames")
        frame_weights = torch.as_tensor(frame_weights, dtype=torch.float32, device=hidden.device)
        sums = []
        for weight, layer in zip(weights[1:], self.encoder.layers, strict=True):
            _check_cancelled(cancelled)
            hidden = layer(hidden, positions)
            mixed = mixed + hidden * weight
            if hidden.ndim != 3 or hidden.shape[:2] != frame_weights.shape:
                raise ValueError("SheetSage2 encoder changed the frame shape")
            sums.append((hidden.float() * frame_weights[:, :, None]).sum(dim=1))
        memory = self.encoder_projection(mixed)
        pooled = torch.stack(sums, dim=1)
        valid = torch.isfinite(memory).flatten(1).all(1) & torch.isfinite(pooled).flatten(1).all(1)
        # One small host transfer, after all layers; frame tensors remain on device.
        summary = torch.cat((pooled.flatten(1), valid[:, None].float()), dim=1).cpu().numpy()
        return memory, summary[:, :-1].reshape(pooled.shape).astype(np.float64), weight_sum, summary[:, -1].astype(bool)

    def decode(self, memory, decoder_input_ids, use_cache=False, past_key_values=None,
               attention_mask=None, position_ids=None, last_logits_only=False):
        mask = attention_mask
        if mask is None and past_key_values is None:
            mask = decoder_input_ids != self.tokenizer.pad_token
        self.decoder.embed_positions.row_positions = position_ids
        try:
            output = self.decoder(
                input_ids=decoder_input_ids, attention_mask=mask, encoder_hidden_states=memory,
                encoder_attention_mask=None, past_key_values=past_key_values, use_cache=use_cache,
                output_hidden_states=False, return_dict=True,
            )
        finally:
            self.decoder.embed_positions.row_positions = None
        hidden = output.last_hidden_state[:, -1:] if last_logits_only else output.last_hidden_state
        return self.output_projection(hidden), output.past_key_values


def generate_batch(model, generation, memory, prompts, prefixes, stops, *, dtype=None,
                   cancelled=None, result_callback=None):
    """Native grammar/greedy decoding with independent padded prefixes and stops."""
    tokenizer = model.tokenizer
    outputs, states = [], []
    for prefix in prefixes:
        tokens = list(prefix) if prefix is not None else tokenizer.prompt_prefix(prompts)
        if not tokens or tokens[0] != tokenizer.sos_token:
            raise ValueError("SheetSage2 generation prefix must begin with SOS")
        if tokens[-1] == tokenizer.eos_token:
            tokens.pop()
        state = generation.PromptGrammarState(tokenizer)
        for token in tokens[tokens.index(tokenizer.out_token) + 1:]:
            state.update(token)
        outputs.append(tokens)
        states.append(state)
    active = list(range(len(outputs)))
    max_prefix = max(map(len, outputs))
    decoder_input = torch.tensor([[tokenizer.pad_token] * (max_prefix - len(tokens)) + tokens
                                  for tokens in outputs], device=memory.device)
    mask = decoder_input != tokenizer.pad_token
    positions = (mask.long().cumsum(1) - 1).clamp_min(0)
    cache = None
    results = [None] * len(outputs)
    while active:
        _check_cancelled(cancelled)
        with generation.inference_autocast(memory.device, dtype):
            logits, cache = model.decode(memory, decoder_input, use_cache=True, past_key_values=cache,
                                         attention_mask=mask, position_ids=positions, last_logits_only=True)
        logits = logits[:, -1].float()
        allowed = torch.stack([states[index].allowed(logits.device) for index in active])
        masked = logits.masked_fill(~allowed, float("-inf"))
        selected = masked.argmax(-1)
        valid = torch.isfinite(logits).all(-1) & torch.isfinite(masked).any(-1)
        # The grammar and termination share the same token and validity transfer.
        decisions = torch.stack((selected, valid.long()), dim=1).tolist()
        keep = []
        for row, (index, (token, finite)) in enumerate(zip(active, decisions, strict=True)):
            error, reason = None, None
            if not finite:
                error = ValueError("SheetSage2 produced invalid decoder logits")
            elif len(outputs[index]) >= model.max_output_seq_len:
                error = ValueError("SheetSage2 generation reached the token limit before completion")
            else:
                outputs[index].append(token)
                if states[index].update(token):
                    reason = "eos"
                elif (stops[index] is not None and tokenizer.time_token_start <= token < tokenizer.time_token_end
                      and tokenizer.token_to_time_id(token) / tokenizer.time_hz >= stops[index]):
                    outputs[index].append(tokenizer.eos_token)
                    reason = "time_boundary"
                elif len(outputs[index]) >= model.max_output_seq_len:
                    error = ValueError("SheetSage2 generation reached the token limit before completion")
            if error is not None or reason is not None:
                result = error if error is not None else (torch.tensor(outputs[index]), reason)
                results[index] = result
                if result_callback is not None:
                    result_callback(index, result)
            else:
                keep.append(row)
        if not keep:
            break
        old_size = len(active)
        decoder_input = selected[:, None]
        mask = torch.cat((mask, torch.ones((old_size, 1), dtype=torch.bool, device=mask.device)), dim=1)
        positions = mask.long().sum(1, keepdim=True) - 1
        if len(keep) != old_size:
            indices = torch.tensor(keep, device=memory.device)
            active = [active[row] for row in keep]
            decoder_input, mask, positions = (value.index_select(0, indices)
                                               for value in (decoder_input, mask, positions))
            memory = memory.index_select(0, indices)
            cache = generation.select_cache_batch(cache, indices, old_size)
    return results


def accepted_frame_weights(frame_count, frame_seconds, window_start, accept_start, accept_end, real_seconds):
    """Time-cell intersections exclude padded and already accepted overlap samples."""
    starts = float(window_start) + np.arange(frame_count, dtype=np.float64) * frame_seconds
    stops = np.minimum(starts + frame_seconds, float(window_start) + real_seconds)
    return np.maximum(0.0, np.minimum(stops, accept_end) - np.maximum(starts, accept_start))


def sliding_window_plan(duration, window_seconds=300.0, overlap_seconds=200.0, lookahead_seconds=100.0):
    if not duration > 0 or not 0 <= lookahead_seconds <= overlap_seconds < window_seconds:
        raise ValueError("Require positive duration and 0 <= lookahead <= overlap < window")
    start, accepted, result = 0.0, 0.0, []
    while True:
        last = start + window_seconds >= duration - 1e-6
        accept_end = duration if last else start + window_seconds - lookahead_seconds
        result.append(dict(start=start, end=min(duration, start + window_seconds),
                           accept_start=accepted, accept_end=accept_end, prefix_end=accepted,
                           generation_stop=None if last else window_seconds - lookahead_seconds))
        if last:
            return result
        accepted = accept_end
        start = min(start + window_seconds - overlap_seconds, duration - window_seconds)


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise EmbeddingCancelledError("SheetSage2 analysis cancelled")

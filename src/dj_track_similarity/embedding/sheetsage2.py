"""Local SheetSage2 analysis, with adapted encoder layers from the same pass."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ..analysis.sheetsage2_features import derive_sheetsage2_features, validate_sheetsage2_timeline
from ..analysis_models import (
    MERT_V2_CHECKPOINT_ID, MERT_V2_MODEL_NAME, MERT_V2_MODEL_REVISION,
    MERT_V2_SNAPSHOT_SHA256, SHEETSAGE2_CHECKPOINT_ID, SHEETSAGE2_EMBEDDING_DIM,
    SHEETSAGE2_MODEL_NAME, SHEETSAGE2_MODEL_REVISION, SHEETSAGE2_PREPROCESSING,
    SHEETSAGE2_SNAPSHOT_SHA256,
)
from ..audio.loader import DecodedAudio
from ..runtime import select_torch_device
from .audio import _resample_to
from .contracts import EmbeddingCancelledError
from .loading import _bind_verified_local_snapshot


@dataclass(frozen=True, slots=True)
class SheetSage2AnalysisResult:
    timeline: dict[str, object]
    features: dict[str, object]
    layer_embeddings: tuple[np.ndarray, ...]


class SheetSage2Adapter:
    embedding_key = "sheetsage2"
    model_name = SHEETSAGE2_MODEL_NAME
    model_revision = SHEETSAGE2_MODEL_REVISION
    model_version = model_revision
    checkpoint_filename = "model.safetensors"
    checkpoint_id = SHEETSAGE2_CHECKPOINT_ID
    checkpoint_sha256 = checkpoint_id.removeprefix("sha256:")
    preprocessing = SHEETSAGE2_PREPROCESSING
    dim = SHEETSAGE2_EMBEDDING_DIM
    target_rate = input_sample_rate = 24_000
    snapshot_sha256 = SHEETSAGE2_SNAPSHOT_SHA256
    snapshot_files = tuple(name for name, _ in snapshot_sha256)
    normalization = "l2"
    encoding = "float32-le"

    def __init__(self, device: str | None = None, inference_batch_size: int = 1) -> None:
        self.requested_device = device or "auto"
        self.inference_batch_size = max(1, int(inference_batch_size))
        self.device: str | None = None
        self._load_lock = threading.RLock()
        self._inference_lock = threading.Lock()
        self._model = self._generation = self._exports = self._torch = self._torchaudio = None

    def runtime_parameters(self) -> dict[str, object]:
        return {
            "sample_rate_hz": self.target_rate, "window_seconds": 300.0,
            "overlap_seconds": 200.0, "lookahead_seconds": 100.0,
            "preset": "default", "channel_downmix": "arithmetic-mean",
            "decoder": "shared-torchcodec-0.16", "inference_batch_size": self.inference_batch_size,
            "processor_normalization": "none-preserve-waveform-amplitude",
            "chord_spelling": "upstream-local-key-midpoint",
            "embedding_layers": list(range(1, 25)), "default_layer": 24,
            "layer_pooling": "accepted-time-overlap-weighted-frame-mean+per-layer-l2",
            "track_accumulation": "cpu-float64", "dtype": "float32",
            "device_precision": "cuda-native-bfloat16-forward-autocast-otherwise-float32",
            "attn_implementation": "sdpa", "model_revision": self.model_revision,
            "base_model_revision": MERT_V2_MODEL_REVISION,
            "checkpoint_filename": self.checkpoint_filename,
            "snapshot_files": self.snapshot_files, "snapshot_sha256": self.snapshot_sha256,
        }

    def preflight(self) -> None:
        self._load_model()

    def _load_model(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            import torchaudio
            from .sheetsage2_runtime import load_local_runtime

            device = select_torch_device(torch, self.requested_device)
            # Both complete manifests are checked before any checkpoint is deserialized.
            with _bind_verified_local_snapshot(
                model_directory="sheetsage2", repo_id=self.model_name, revision=self.model_revision,
                required_files=self.snapshot_files, expected_sha256=self.snapshot_sha256,
                checkpoint_filename=self.checkpoint_filename, expected_checkpoint_sha256=self.checkpoint_sha256,
            ) as sheet, _bind_verified_local_snapshot(
                model_directory="mert-v2", repo_id=MERT_V2_MODEL_NAME, revision=MERT_V2_MODEL_REVISION,
                required_files=tuple(name for name, _ in MERT_V2_SNAPSHOT_SHA256),
                expected_sha256=MERT_V2_SNAPSHOT_SHA256, checkpoint_filename="model.safetensors",
                expected_checkpoint_sha256=MERT_V2_CHECKPOINT_ID.removeprefix("sha256:"),
            ) as base:
                model, generation, exports = load_local_runtime(sheet.path, base.path)
                model = model.float().to(device).eval().requires_grad_(False)
            self._torch, self._torchaudio = torch, torchaudio
            self.device, self._generation, self._exports, self._model = device, generation, exports, model

    def analyze_decoded_batch(
        self, decoded_items: Sequence[DecodedAudio], *, cancelled: Callable[[], bool] | None = None,
        result_callback: Callable[[int, SheetSage2AnalysisResult | Exception], None] | None = None,
    ) -> list[SheetSage2AnalysisResult | Exception]:
        from .sheetsage2_runtime import sliding_window_plan

        _check_cancelled(cancelled)
        self._load_model()
        torch = self._torch
        assert torch is not None and self._model is not None and self._generation is not None
        results = [None] * len(decoded_items)

        def publish(index, result):
            results[index] = result
            if result_callback is not None:
                result_callback(index, result)

        with self._inference_lock, torch.inference_mode():
            pending = []
            for index, decoded in enumerate(decoded_items):
                _check_cancelled(cancelled)
                try:
                    audio = decoded.audio.to(dtype=torch.float32)
                    if audio.ndim != 1 or audio.numel() == 0 or not torch.isfinite(audio).all().item():
                        raise ValueError(f"SheetSage2 requires finite nonempty mono audio: {decoded.path}")
                    if decoded.sample_rate != self.target_rate:
                        audio = _resample_to(audio.unsqueeze(0), source_rate=decoded.sample_rate,
                                             target_rate=self.target_rate, torchaudio=self._torchaudio).squeeze(0)
                    if audio.numel() < 1025:
                        raise ValueError("SheetSage2 requires at least 1025 samples at 24000 Hz")
                    duration = audio.numel() / self.target_rate
                    pending.append(dict(index=index, audio=audio.cpu(), duration=duration,
                                        plan=sliding_window_plan(duration), stitched=[], windows=[], warnings=[],
                                        sums=np.zeros((24, self.dim), dtype=np.float64), weight=0.0))
                except Exception as error:
                    publish(index, error)
            while pending:
                _check_cancelled(cancelled)
                batch = pending[:self.inference_batch_size]
                del pending[:len(batch)]
                next_windows = self._analyze_windows(batch, cancelled, publish)
                pending.extend(next_windows)
        return results

    def _analyze_windows(self, batch, cancelled, publish):
        from .sheetsage2_runtime import generate_batch

        torch, model, generation = self._torch, self._model, self._generation
        prompts = model.tokenizer.normalize_prompts(generation.FULL_TASK_PROMPTS)
        dtype = (torch.bfloat16 if str(self.device).startswith("cuda")
                 and torch.cuda.is_bf16_supported(including_emulation=False) else None)
        prepared, segments, prefixes, bases, stops = [], [], [], [], []
        for state in batch:
            _check_cancelled(cancelled)
            try:
                index = len(state["windows"])
                window = state["plan"][index]
                prefix, base = None, 0
                if index:
                    _, prefix, base = generation.build_overlap_prefix_tokens(
                        state["stitched"], model.tokenizer, prompts, window["start"], window["prefix_end"],
                    )
                    if prefix is not None and len(prefix) >= model.max_output_seq_len - 128:
                        raise ValueError("SheetSage2 overlap prefix fills the decoder context")
                start_sample = round(window["start"] * self.target_rate)
                segments.append(state["audio"][start_sample:start_sample + 300 * self.target_rate])
                prefixes.append(prefix)
                bases.append(base)
                stops.append(window["generation_stop"] if window["generation_stop"] is not None
                             else min(state["duration"] - window["start"], 300.0))
                prepared.append(state)
            except Exception as error:
                publish(state["index"], error)
        if not prepared:
            return []
        windows = [state["plan"][len(state["windows"])] for state in prepared]
        audio = torch.nn.utils.rnn.pad_sequence(segments, batch_first=True).to(self.device)
        try:
            with generation.inference_autocast(audio.device, dtype):
                memory, sums, weights, valid = model.encode_and_pool_batch(
                    audio, window_starts=[round(window["start"] * self.target_rate) / self.target_rate
                                          for window in windows],
                    accept_starts=[window["accept_start"] for window in windows],
                    accept_ends=[window["accept_end"] for window in windows],
                    sample_lengths=[segment.numel() for segment in segments], cancelled=cancelled,
                )
        except EmbeddingCancelledError:
            raise
        except Exception as error:
            for state in prepared:
                publish(state["index"], error)
            return []
        keep = []
        for row, state in enumerate(prepared):
            if not valid[row] or sums[row].shape != state["sums"].shape or not np.isfinite(sums[row]).all() or weights[row] <= 0:
                publish(state["index"], ValueError("SheetSage2 produced invalid encoder layer sums or memory"))
            else:
                state["sums"] += sums[row]
                state["weight"] += weights[row]
                keep.append(row)
        next_windows, completed = [], set()
        callback_error = None

        def finish(row, generated):
            nonlocal callback_error
            original = keep[row]
            state, window = prepared[original], windows[original]
            completed.add(row)
            result = generated
            if not isinstance(result, Exception):
                tokens, reason = result
                try:
                    self._accept_window(state, window, prefixes[original], bases[original], tokens, reason)
                    if len(state["windows"]) == len(state["plan"]):
                        result = self._finish_track(state, prompts, dtype, cancelled)
                    else:
                        next_windows.append(state)
                        return
                except EmbeddingCancelledError:
                    raise
                except Exception as error:
                    result = error
            try:
                publish(state["index"], result)
            except Exception as error:
                callback_error = error
                raise

        if keep:
            selected_memory = memory if len(keep) == len(prepared) else memory[keep]
            try:
                generate_batch(model, generation, selected_memory, prompts,
                               [prefixes[row] for row in keep], [stops[row] for row in keep], dtype=dtype,
                               cancelled=cancelled, result_callback=finish)
            except EmbeddingCancelledError:
                raise
            except Exception as error:
                # A callback failure must propagate; never publish the same track twice.
                if callback_error is error:
                    raise
                for row in range(len(keep)):
                    if row not in completed:
                        finish(row, error)
        return next_windows

    def _accept_window(self, state, window, prefix, base, tokens, reason):
        generation, model = self._generation, self._model
        index, duration = len(state["windows"]), state["duration"]
        decoded, warning = generation.decode_generated_tokens(model.tokenizer, tokens, "audio", index)
        anchors = [(event["subbeat"], event["values"]["timestamp"]) for event in decoded["events"]
                   if event["values"].get("timestamp") is not None]
        if not anchors:
            raise ValueError("SheetSage2 window has no timestamp anchors")
        if any(right[1] < left[1] for left, right in zip(anchors, anchors[1:])):
            raise ValueError("SheetSage2 window has backward timestamp anchors")
        if warning:
            state["warnings"].append(warning["error"])
        lookup = generation.event_time_map(decoded, 300.0)
        accepted = generation.stitched_window_events(
            decoded, lookup, window["start"], window["accept_start"], window["accept_end"],
            duration, index, global_subbeat_base=base or 0,
        )
        state["stitched"].extend(accepted)
        state["windows"].append(dict(window, window_index=index, prefix_tokens=0 if prefix is None else len(prefix),
                                    tokens=len(tokens), events=len(decoded["events"]), accepted_events=len(accepted),
                                    termination=reason))

    def _finish_track(self, state, prompts, dtype, cancelled):
        track_weight, track_sum = state["weight"], state["sums"]
        stitched, duration = state["stitched"], state["duration"]
        if track_weight <= 0:
            raise ValueError("SheetSage2 produced no valid encoder frames")
        pooled = track_sum / track_weight
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        if not np.isfinite(norms).all() or np.any(norms == 0):
            raise ValueError("SheetSage2 produced zero or nonfinite layer embeddings")
        stitched.sort(key=lambda event: (event["time"], event["global_subbeat"]))
        timeline = validate_sheetsage2_timeline({
            "duration_s": duration, "model_revision": self.model_revision,
            "base_model_revision": MERT_V2_MODEL_REVISION,
            "parameters": dict(self.runtime_parameters(), prompts=list(prompts),
                               inference_dtype="bfloat16" if dtype else "float32"),
            "events": _canonical_events(stitched, duration, self._exports),
            "windows": state["windows"], "warnings": state["warnings"],
        })
        _check_cancelled(cancelled)
        return SheetSage2AnalysisResult(timeline, derive_sheetsage2_features(timeline),
                                       tuple((pooled / norms).astype(np.float32)))


def _canonical_events(stitched, duration: float, exports) -> list[dict[str, object]]:
    result = []
    meter = None
    # Of several labels at one time only the last has a positive length.
    labeled = {field: {} for field in ("chord", "key", "structure")}
    for source in stitched:
        values = source["values"]
        event = {"time_s": float(source["time"]), "global_subbeat": int(source["global_subbeat"]),
                 "window_index": int(source["window_index"]), "source_subbeat": int(source["source_subbeat"]),
                 "timestamp_anchor": "timestamp" in values}
        if "rhythm" in values:
            rhythm = values["rhythm"]
            if "meter" in rhythm:
                meter = rhythm["meter"]
            event["rhythm"] = {
                "numerator": int(meter[0]) if meter else None, "denominator": int(meter[1]) if meter else None,
                "eighth_position": int(rhythm["eighth_position"]), "timestamp_anchor": "timestamp" in values,
            }
        for field, by_time in labeled.items():
            if field in values:
                by_time[event["time_s"]] = event
        if values.get("melody") is not None:
            event["melody"] = [
                {"pitch_midi": int(note["pitch"]), "source_track": "vocal" if note["track"] == 0 else "instrumental",
                 "start_s": event["time_s"], "end_s": min(duration, float(note["end_time"])),
                 "duration_steps": int(note["duration_steps"]), "duration_bin": int(note["duration_bin"])}
                for note in values["melody"]
                if min(duration, float(note["end_time"])) > event["time_s"]
            ]
        result.append(event)

    # The native export order: raw intervals, canonical keys, then chord spelling by
    # the key at each chord midpoint. Equal neighbours merge only afterwards.
    rows = {field: exports.interval_rows(stitched, field, duration) for field in labeled}
    rows["key"] = [[start, end, exports.normalize_key_name(key)] for start, end, key in rows["key"]]
    rows["chord"] = exports.correct_chord_rows(rows["chord"], rows["key"])
    for field, by_time in labeled.items():
        previous = None
        for start, end, label in rows[field]:
            if previous is not None and previous["label"] == label:
                previous["end_s"] = end
            else:
                previous = by_time[start][field] = {"label": label, "end_s": end}
    return result


def _check_cancelled(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise EmbeddingCancelledError("SheetSage2 analysis cancelled")

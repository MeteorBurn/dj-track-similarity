from __future__ import annotations

import re
from pathlib import Path

from .audio_loader import load_audio_mono
from .runtime import select_torch_device


class MaestGenreAdapter:
    model_name = "discogs-maest-30s-pw-129e-519l"
    analysis_offset_seconds = 60.0

    def __init__(self, device: str | None = None, top_k: int = 3) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.top_k = max(1, int(top_k))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None

    def predict(self, path: str | Path) -> list[dict[str, float | str]]:
        return self.predict_batch([path])[0]

    def predict_batch(self, paths: list[str | Path]) -> list[list[dict[str, float | str]]]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

        prepared = [self._prepare_audio(path) for path in paths]
        device = self._device()
        audio_batch = torch.stack(prepared, dim=0).to(device)
        _move_maest_runtime_modules(self._model, device)

        with torch.inference_mode():
            logits, _embeddings = self._model(audio_batch, melspectrogram_input=False)

        activations = torch.sigmoid(logits)
        rows = _to_score_rows(activations, expected_rows=len(paths))
        label_values = [str(label) for label in getattr(self._model, "labels")]
        return [_rank_genres(label_values, scores, self.top_k) for scores in rows]

    def _prepare_audio(self, path: str | Path):
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None

        audio_values, sample_rate, _decode_detail = load_audio_mono(
            path,
            torchaudio_module=torchaudio,
            target_sample_rate=16000,
        )
        audio = torch.from_numpy(audio_values).unsqueeze(0)
        if sample_rate != 16000:
            audio = torchaudio.transforms.Resample(sample_rate, 16000)(audio)
        audio = audio.squeeze(0)
        target_samples = int(16000 * _input_seconds(self.model_name))
        if audio.numel() < target_samples:
            audio = torch.nn.functional.pad(audio, (0, target_samples - audio.numel()))
        elif audio.numel() > target_samples:
            start = int(16000 * self.analysis_offset_seconds)
            if start >= audio.numel():
                start = 0
            segment = audio[start : start + target_samples]
            if segment.numel() < target_samples:
                segment = torch.nn.functional.pad(segment, (0, target_samples - segment.numel()))
            audio = segment
        return audio

    def _load_model(self) -> None:
        if self._model is not None:
            return
        import torch
        import torchaudio
        from maest_infer import get_maest

        self._torch = torch
        self._torchaudio = torchaudio
        self.device = self._device()
        self._model = get_maest(arch=self.model_name)
        self._model = self._model.to(self.device).eval()
        _move_maest_runtime_modules(self._model, self.device)

    def _device(self) -> str:
        assert self._torch is not None
        if self.device:
            return self.device
        return select_torch_device(self._torch, self.requested_device)


def genre_adapter_factories():
    return {"maest": MaestGenreAdapter}


def _move_maest_runtime_modules(model: object, device: str) -> None:
    init_melspectrogram = getattr(model, "init_melspectrogram", None)
    if callable(init_melspectrogram):
        init_melspectrogram()
    for attribute in ("melspectrogram",):
        module = getattr(model, attribute, None)
        move = getattr(module, "to", None)
        if callable(move):
            move(device)


def _input_seconds(model_name: str) -> float:
    match = re.search(r"-(5|10|20|30)s-", model_name)
    return float(match.group(1)) if match else 30.0


def _to_float_list(values: object) -> list[float]:
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


def _to_score_rows(values: object, *, expected_rows: int) -> list[list[float]]:
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
        rows = [[float(score) for score in row] for row in values]  # type: ignore[union-attr]
        if len(rows) != expected_rows:
            raise ValueError("MAEST batch output shape does not match the requested batch size")
        return rows

    flat = _to_float_list(values)
    if expected_rows == 1:
        return [flat]
    raise ValueError("MAEST batch output shape does not include per-track rows")


def _rank_genres(labels: list[str], scores: list[float], top_k: int) -> list[dict[str, float | str]]:
    ranked = sorted(zip(labels, scores), key=lambda item: item[1], reverse=True)
    return [{"label": label, "score": float(score)} for label, score in ranked[:top_k]]

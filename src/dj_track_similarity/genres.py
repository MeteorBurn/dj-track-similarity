from __future__ import annotations

import re
from pathlib import Path

from .runtime import select_torch_device


class MaestGenreAdapter:
    model_name = "discogs-maest-30s-pw-129e-519l"

    def __init__(self, device: str | None = None, top_k: int = 3) -> None:
        self.requested_device = device or "auto"
        self.device_name = None if self.requested_device == "auto" else self.requested_device
        self.top_k = max(1, int(top_k))
        self._model = None
        self._torch = None
        self._torchaudio = None
        self.device: str | None = None

    def predict(self, path: str | Path) -> list[dict[str, float | str]]:
        self._load_model()
        torch = self._torch
        torchaudio = self._torchaudio
        assert torch is not None and torchaudio is not None and self._model is not None

        audio, sample_rate = torchaudio.load(str(path))
        if audio.shape[0] > 1:
            audio = audio.mean(dim=0, keepdim=True)
        if sample_rate != 16000:
            audio = torchaudio.transforms.Resample(sample_rate, 16000)(audio)
        audio = audio.squeeze(0)
        target_samples = int(16000 * _input_seconds(self.model_name))
        if audio.numel() < target_samples:
            audio = torch.nn.functional.pad(audio, (0, target_samples - audio.numel()))
        elif audio.numel() > target_samples:
            start = max(0, (audio.numel() - target_samples) // 2)
            audio = audio[start : start + target_samples]
        device = self._device()
        audio = audio.to(device)
        _move_maest_runtime_modules(self._model, device)

        with torch.inference_mode():
            activations, labels = self._model.predict_labels(audio)

        scores = _to_float_list(activations)
        label_values = [str(label) for label in labels]
        ranked = sorted(zip(label_values, scores), key=lambda item: item[1], reverse=True)
        return [{"label": label, "score": float(score)} for label, score in ranked[: self.top_k]]

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

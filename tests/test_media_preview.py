from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import torch

from dj_track_similarity import media_preview


def test_transcoded_wav_preview_uses_torchcodec_without_executable(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "track.aiff"
    source.write_bytes(b"aiff fixture")
    calls: dict[str, object] = {}

    class FakeAudioDecoder:
        def __init__(self, source_path: str, *, sample_rate: int, num_channels: int) -> None:
            calls["decoder"] = (source_path, sample_rate, num_channels)

        def get_all_samples(self) -> SimpleNamespace:
            return SimpleNamespace(data=torch.zeros((2, 4), dtype=torch.float32), sample_rate=44_100)

    class FakeAudioEncoder:
        def __init__(self, samples: torch.Tensor, *, sample_rate: int) -> None:
            calls["encoder"] = (samples.shape, sample_rate)

        def to_file(self, destination: Path) -> None:
            Path(destination).write_bytes(b"RIFFfake-wav")

    decoders_module = ModuleType("torchcodec.decoders")
    decoders_module.AudioDecoder = FakeAudioDecoder
    encoders_module = ModuleType("torchcodec.encoders")
    encoders_module.AudioEncoder = FakeAudioEncoder
    monkeypatch.setitem(sys.modules, "torchcodec.decoders", decoders_module)
    monkeypatch.setitem(sys.modules, "torchcodec.encoders", encoders_module)
    response = media_preview.transcoded_wav_file_response(source)

    assert calls["decoder"] == (str(source), 44_100, 2)
    assert calls["encoder"] == ((2, 4), 44_100)
    assert Path(response.path).read_bytes() == b"RIFFfake-wav"
    response.background.func(*response.background.args)

from pathlib import Path
import sys
import types
from types import SimpleNamespace
import wave

import numpy as np
import pytest

import dj_track_similarity.audio_loader as audio_loader
from dj_track_similarity.audio_loader import (
    load_audio_mono_with_ffmpeg,
    load_decoded_audio,
    load_decoded_audio_with_ffmpeg,
)


def _write_pcm_wav(path: Path, *, sample_rate: int = 44_100) -> bytes:
    samples = np.array(
        [
            [0, 0],
            [1024, -1024],
            [2048, -2048],
            [4096, -4096],
        ],
        dtype="<i2",
    )
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return samples.tobytes()


def _write_mono_pcm_wav(path: Path, *, sample_rate: int = 44_100) -> bytes:
    samples = np.array([0, 1024, -2048, 4096], dtype="<i2")
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return samples.tobytes()


def _write_identical_stereo_pcm_wav(path: Path, *, sample_rate: int = 44_100) -> np.ndarray:
    mono = np.array([0, 8192, 16384, 24576, 29490, -29490, -16384, -8192], dtype="<i2")
    samples = np.column_stack((mono, mono))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return mono.astype(np.float32) / 32768.0


def test_load_decoded_audio_preserves_native_sample_rate(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path, sample_rate=44_100)

    result = load_decoded_audio(audio_path)

    assert result.path == str(audio_path)
    assert result.sample_rate == 44_100
    assert torch.equal(result.audio, torch.zeros(4, dtype=torch.float32))
    assert result.detail == "torchcodec 0.16 decode (num_channels=1)"


def test_load_decoded_audio_requests_torchcodec_mono_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"encoded audio")
    decoded_tensor = torch.tensor([[0.5, 0.0, 0.0]], dtype=torch.float32)

    class FakeAudioDecoder:
        def __init__(self, source: str, *, num_channels: int) -> None:
            if source != str(audio_path):
                raise AssertionError(f"unexpected TorchCodec source: {source}")
            if num_channels != 1:
                raise AssertionError(f"unexpected channel count: {num_channels}")

        @staticmethod
        def get_all_samples():
            return SimpleNamespace(
                data=decoded_tensor,
                sample_rate=48_000,
            )

    torchcodec_module = types.ModuleType("torchcodec")
    decoders_module = types.ModuleType("torchcodec.decoders")
    decoders_module.AudioDecoder = FakeAudioDecoder
    torchcodec_module.decoders = decoders_module
    monkeypatch.setitem(sys.modules, "torchcodec", torchcodec_module)
    monkeypatch.setitem(sys.modules, "torchcodec.decoders", decoders_module)
    result = load_decoded_audio(audio_path)

    assert result.path == str(audio_path)
    assert result.sample_rate == 48_000
    assert isinstance(result.audio, torch.Tensor)
    assert result.audio.dtype == torch.float32
    assert result.audio.data_ptr() == decoded_tensor.data_ptr()
    assert torch.equal(result.audio, torch.tensor([0.5, 0.0, 0.0]))
    assert result.detail == "torchcodec 0.16 decode (num_channels=1)"


def test_load_decoded_audio_does_not_bypass_torchcodec_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"encoded audio")

    class FailingAudioDecoder:
        def __init__(self, source: str, *, num_channels: int) -> None:
            raise RuntimeError("unsupported test codec")

    torchcodec_module = types.ModuleType("torchcodec")
    decoders_module = types.ModuleType("torchcodec.decoders")
    decoders_module.AudioDecoder = FailingAudioDecoder
    torchcodec_module.decoders = decoders_module
    monkeypatch.setitem(sys.modules, "torchcodec", torchcodec_module)
    monkeypatch.setitem(sys.modules, "torchcodec.decoders", decoders_module)
    with pytest.raises(RuntimeError, match="unsupported test codec"):
        load_decoded_audio(audio_path)


def test_shared_ffmpeg_decode_uses_arithmetic_mean_for_correlated_stereo(tmp_path: Path) -> None:
    audio_path = tmp_path / "correlated-stereo.wav"
    expected = _write_identical_stereo_pcm_wav(audio_path)

    audio, sample_rate, _detail = load_audio_mono_with_ffmpeg(audio_path)

    assert sample_rate == 44_100
    assert audio.shape == expected.shape
    assert np.allclose(audio, expected, atol=1e-6)
    assert float(np.max(np.abs(audio))) < 1.0


def test_load_decoded_audio_uses_torchcodec_for_mono_wav(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.wav"
    _write_mono_pcm_wav(audio_path, sample_rate=44_100)

    result = load_decoded_audio(audio_path)

    assert result.sample_rate == 44_100
    assert result.audio.dtype == torch.float32
    assert result.audio.shape == (4,)
    assert result.detail == "torchcodec 0.16 decode (num_channels=1)"


@pytest.mark.ml
@pytest.mark.skipif(
    sys.platform != "win32" or sys.version_info[:2] != (3, 10),
    reason="the CUDA TorchCodec wheel is pinned for Windows Python 3.10",
)
def test_installed_torchcodec_cuda_wheel_decodes_real_wav(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    torchcodec = pytest.importorskip("torchcodec")
    from torchcodec.decoders import AudioDecoder

    audio_path = tmp_path / "torchcodec-smoke.wav"
    _write_mono_pcm_wav(audio_path, sample_rate=44_100)

    assert torch.version.cuda == "13.0"
    assert torch.cuda.is_available()
    assert torchcodec.__version__.startswith("0.16.0+cu")

    decoded = AudioDecoder(str(audio_path), num_channels=1).get_all_samples()
    result = load_decoded_audio(audio_path)
    expected = torch.tensor([0.0, 1024.0, -2048.0, 4096.0], dtype=torch.float32) / 32768.0

    assert decoded.sample_rate == 44_100
    assert decoded.data.shape == (1, 4)
    assert decoded.data.dtype == torch.float32
    assert torch.allclose(decoded.data[0], expected)
    assert result.sample_rate == 44_100
    assert torch.allclose(result.audio, expected)
    assert result.detail == "torchcodec 0.16 decode (num_channels=1)"


def test_shared_ffmpeg_fallback_uses_manual_arithmetic_mean_without_subprocess(
    monkeypatch, tmp_path: Path
) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"encoded audio")

    class FakeAudioDecoder:
        def __init__(self, source: str) -> None:
            assert source == str(audio_path)

        @staticmethod
        def get_all_samples():
            return SimpleNamespace(
                data=torch.tensor([[0.25, -0.5], [0.25, 0.5]], dtype=torch.float32),
                sample_rate=48_000,
            )

    torchcodec_module = types.ModuleType("torchcodec")
    decoders_module = types.ModuleType("torchcodec.decoders")
    decoders_module.AudioDecoder = FakeAudioDecoder
    torchcodec_module.decoders = decoders_module
    monkeypatch.setitem(sys.modules, "torchcodec", torchcodec_module)
    monkeypatch.setitem(sys.modules, "torchcodec.decoders", decoders_module)
    mono, sample_rate, detail = load_audio_mono_with_ffmpeg(audio_path)
    decoded = load_decoded_audio_with_ffmpeg(audio_path)

    assert not hasattr(audio_loader, "subprocess")
    assert sample_rate == 48_000
    assert np.array_equal(mono, np.asarray([0.25, 0.0], dtype=np.float32))
    assert detail == "torchcodec shared FFmpeg decode (arithmetic channel mean)"
    assert torch.equal(decoded.audio, torch.tensor([0.25, 0.0], dtype=torch.float32))
    assert decoded.sample_rate == 48_000

from pathlib import Path
import shutil
import subprocess
import sys
import types
from types import SimpleNamespace
import wave

import numpy as np
import pytest

import dj_track_similarity.audio_loader as audio_loader
from dj_track_similarity.audio_loader import (
    DecodedAudioWindows,
    load_audio_mono_with_ffmpeg,
    load_decoded_audio,
    load_decoded_audio_windows,
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
    monkeypatch.setattr(
        audio_loader,
        "_load_with_ffmpeg",
        lambda path: (_ for _ in ()).throw(
            AssertionError("FFmpeg must not run after TorchCodec succeeds")
        ),
    )

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
    monkeypatch.setattr(
        audio_loader,
        "_load_with_ffmpeg",
        lambda path: (_ for _ in ()).throw(
            AssertionError("shared ML decoding must not bypass TorchCodec")
        ),
    )

    with pytest.raises(RuntimeError, match="unsupported test codec"):
        load_decoded_audio(audio_path)


def test_load_decoded_audio_windows_reads_only_model_requested_ranges(
    monkeypatch,
    tmp_path: Path,
) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"encoded audio")
    range_calls: list[tuple[float, float]] = []

    class FakeAudioDecoder:
        metadata = SimpleNamespace(duration_seconds=120.0)

        def __init__(self, source: str, *, sample_rate: int, num_channels: int) -> None:
            assert source == str(audio_path)
            assert sample_rate == 24_000
            assert num_channels == 1

        def get_samples_played_in_range(self, start_seconds: float, stop_seconds: float):
            range_calls.append((start_seconds, stop_seconds))
            return SimpleNamespace(
                data=torch.ones((1, 24_000), dtype=torch.float32),
                sample_rate=24_000,
            )

    torchcodec_module = types.ModuleType("torchcodec")
    decoders_module = types.ModuleType("torchcodec.decoders")
    decoders_module.AudioDecoder = FakeAudioDecoder
    torchcodec_module.decoders = decoders_module
    monkeypatch.setitem(sys.modules, "torchcodec", torchcodec_module)
    monkeypatch.setitem(sys.modules, "torchcodec.decoders", decoders_module)

    result = load_decoded_audio_windows(
        audio_path,
        sample_rate=24_000,
        window_seconds=10.0,
        window_starts=lambda duration: (duration * 0.1, duration * 0.5),
    )

    assert isinstance(result, DecodedAudioWindows)
    assert result.path == str(audio_path)
    assert result.sample_rate == 24_000
    assert [window.shape for window in result.windows] == [(24_000,), (24_000,)]
    assert range_calls == [(12.0, 22.0), (60.0, 70.0)]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required for the integration check")
def test_ffmpeg_decode_uses_arithmetic_mean_for_correlated_stereo(tmp_path: Path) -> None:
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


def test_load_audio_mono_with_ffmpeg_bypasses_native_wave(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    _write_mono_pcm_wav(audio_path)
    expected = np.asarray([0.1, -0.2], dtype=np.float32)

    monkeypatch.setattr(
        audio_loader,
        "_load_with_ffmpeg",
        lambda path: (expected, 48_000, "ffmpeg decode"),
    )

    audio, sample_rate, detail = load_audio_mono_with_ffmpeg(audio_path)

    assert sample_rate == 48_000
    assert np.array_equal(audio, expected)
    assert detail == "ffmpeg decode"


def test_ffmpeg_decode_pins_first_audio_stream_and_disables_non_audio(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"not real mp3 bytes")
    decoded = np.array([0.1, -0.2, 0.3], dtype=np.float32)
    commands = []

    def fake_run(command, *, check, stdout, stderr):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=decoded.tobytes(), stderr=b"")

    monkeypatch.setattr(
        audio_loader,
        "shutil",
        SimpleNamespace(which=lambda name: "ffmpeg" if name == "ffmpeg" else None),
        raising=False,
    )
    monkeypatch.setattr(audio_loader, "_source_sample_rate", lambda path, *, ffmpeg_path: 44_100)
    monkeypatch.setattr(audio_loader, "subprocess", SimpleNamespace(run=fake_run, PIPE=subprocess.PIPE), raising=False)

    audio, sample_rate, detail = load_audio_mono_with_ffmpeg(audio_path)

    assert sample_rate == 44_100
    assert np.allclose(audio, decoded)
    assert "ffmpeg decode" in detail
    command = commands[0]
    assert "-nostdin" in command
    assert command[command.index("-map") + 1] == "0:a:0"
    assert "-vn" in command
    assert "-sn" in command
    assert "-dn" in command
    assert command[command.index("-af") + 1] == audio_loader.FFMPEG_ARITHMETIC_MONO_FILTER
    assert "-ar" not in command


def test_ffmpeg_decode_reports_invalid_audio_stream_when_source_rate_is_unknown(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "broken.flac"
    audio_path.write_bytes(b"not real flac bytes")

    monkeypatch.setattr(
        audio_loader,
        "shutil",
        SimpleNamespace(which=lambda name: "ffmpeg" if name == "ffmpeg" else None),
        raising=False,
    )
    monkeypatch.setattr(audio_loader, "_source_sample_rate_from_file_metadata", lambda path: None)
    monkeypatch.setattr(audio_loader, "_source_sample_rate_from_ffprobe", lambda path, *, ffmpeg_path: None)

    with pytest.raises(RuntimeError, match="Invalid audio stream: ffmpeg could not decode audio"):
        load_audio_mono_with_ffmpeg(audio_path)


def test_ffmpeg_decode_reports_invalid_audio_stream_when_ffmpeg_fails(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "broken.aiff"
    audio_path.write_bytes(b"not real aiff bytes")

    def fake_run(command, *, check, stdout, stderr):
        raise subprocess.CalledProcessError(1, command, stderr=b"Invalid data found when processing input")

    monkeypatch.setattr(
        audio_loader,
        "shutil",
        SimpleNamespace(which=lambda name: "ffmpeg" if name == "ffmpeg" else None),
        raising=False,
    )
    monkeypatch.setattr(audio_loader, "_source_sample_rate", lambda path, *, ffmpeg_path: 44_100)
    monkeypatch.setattr(audio_loader, "subprocess", SimpleNamespace(run=fake_run, PIPE=subprocess.PIPE, CalledProcessError=subprocess.CalledProcessError), raising=False)

    with pytest.raises(RuntimeError, match="Invalid audio stream: ffmpeg could not decode audio"):
        load_audio_mono_with_ffmpeg(audio_path)

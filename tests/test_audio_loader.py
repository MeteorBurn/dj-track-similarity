from pathlib import Path
import inspect
import logging
import subprocess
from types import SimpleNamespace
import wave

import numpy as np
import pytest

import dj_track_similarity.audio_loader as audio_loader
from dj_track_similarity.audio_loader import load_audio_mono, load_decoded_audio, torch_compatible_audio
from dj_track_similarity.logging_config import set_analysis_diagnostics_enabled


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


def _make_malformed_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44_100)
        audio.writeframes(
            np.array(
                [
                    [1000, 3000],
                    [-2000, 2000],
                    [4000, -1000],
                ],
                dtype="<i2",
            ).tobytes()
        )
    data = path.read_bytes()
    data_offset = data.index(b"data")
    payload = data[data_offset + 8 :]
    fmt_chunk = data[12:data_offset]
    malformed = (
        data[:12]
        + fmt_chunk
        + b"JUNK"
        + (4).to_bytes(4, "little")
        + b"\x00\x00\x00\x00"
        + b"\x00"
        + b"data"
        + (len(payload) + 1024).to_bytes(4, "little")
        + payload
    )
    riff_size = len(malformed) - 8
    malformed = malformed[:4] + riff_size.to_bytes(4, "little") + malformed[8:]
    path.write_bytes(malformed)


def test_load_audio_mono_reads_normal_wav_with_native_backend(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path)

    audio, sample_rate, detail = load_audio_mono(audio_path)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert audio.shape == (4,)
    assert "native" in detail


def test_load_decoded_audio_preserves_native_sample_rate(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path, sample_rate=44_100)
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

    result = load_decoded_audio(audio_path)

    assert result.path == str(audio_path)
    assert result.sample_rate == 44_100
    assert np.allclose(result.audio, decoded)
    assert "-ar" not in commands[0]


def test_load_decoded_audio_exposes_only_one_decode_mode() -> None:
    assert list(inspect.signature(load_decoded_audio).parameters) == ["path"]


def test_torch_compatible_audio_copies_readonly_float32_buffers() -> None:
    readonly = np.frombuffer(np.asarray([0.1, -0.2, 0.3], dtype=np.float32).tobytes(), dtype=np.float32)

    prepared = torch_compatible_audio(readonly)

    assert prepared.dtype == np.float32
    assert prepared.flags.writeable
    assert np.allclose(prepared, readonly)
    assert not np.shares_memory(prepared, readonly)


def test_load_audio_mono_uses_native_rate_ffmpeg_when_native_wav_decode_fails(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "malformed.wav"
    _make_malformed_wave(audio_path)
    decoded = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    def fake_run(command, *, check, stdout, stderr):
        assert command[:2] == ["ffmpeg", "-v"]
        assert "-f" in command
        assert command[command.index("-f") + 1] == "f32le"
        assert command[-1] == "-"
        return subprocess.CompletedProcess(command, 0, stdout=decoded.tobytes(), stderr=b"")

    monkeypatch.setattr(
        audio_loader,
        "shutil",
        SimpleNamespace(which=lambda name: "ffmpeg" if name == "ffmpeg" else None),
        raising=False,
    )
    monkeypatch.setattr(audio_loader, "_source_sample_rate", lambda path, *, ffmpeg_path: 44_100)
    monkeypatch.setattr(audio_loader, "subprocess", SimpleNamespace(run=fake_run, PIPE=subprocess.PIPE), raising=False)

    audio, sample_rate, detail = load_audio_mono(audio_path)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert np.allclose(audio, decoded)
    assert "ffmpeg decode" in detail
    assert "wave:" in detail
    assert "recovered malformed WAV" not in detail


def test_load_audio_mono_suppresses_decoder_diagnostics_by_default(tmp_path: Path, caplog) -> None:
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path)

    class FailingTorchaudio:
        @staticmethod
        def load(path: str):
            raise RuntimeError("TorchCodec is required for load_with_torchcodec")

    with caplog.at_level(logging.WARNING, logger="dj_track_similarity.audio_loader"):
        audio, sample_rate, detail = load_audio_mono(audio_path, torchaudio_module=FailingTorchaudio)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert "native wave decode" in detail
    assert "Audio decoder failed" not in caplog.text
    assert "Audio decode fallback succeeded" not in caplog.text


def test_load_audio_mono_logs_wave_fallback_when_diagnostics_enabled(tmp_path: Path, caplog) -> None:
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path)

    class FailingTorchaudio:
        @staticmethod
        def load(path: str):
            raise RuntimeError("TorchCodec is required for load_with_torchcodec")

    set_analysis_diagnostics_enabled(True)
    try:
        with caplog.at_level(logging.WARNING, logger="dj_track_similarity.audio_loader"):
            audio, sample_rate, detail = load_audio_mono(audio_path, torchaudio_module=FailingTorchaudio)
    finally:
        set_analysis_diagnostics_enabled(None)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert "native wave decode" in detail
    assert "Audio decoder failed decoder=torchaudio" in caplog.text
    assert "Audio decode fallback succeeded decoder=wave" in caplog.text


def test_load_audio_mono_rejects_unknown_malformed_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "broken.wav"
    audio_path.write_bytes(b"RIFF\x10\x00\x00\x00WAVEfmt ")

    with pytest.raises(RuntimeError, match="Unable to decode audio"):
        load_audio_mono(audio_path)


def test_load_audio_mono_logs_decoder_fallback_errors(monkeypatch, tmp_path: Path, caplog) -> None:
    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"not real mp3 bytes")
    decoded = np.array([0.25, -0.5, 0.75], dtype=np.float32)

    class FailingTorchaudio:
        @staticmethod
        def load(path: str):
            raise RuntimeError("TorchCodec is required for load_with_torchcodec")

    def fake_run(command, *, check, stdout, stderr):
        assert command[:2] == ["ffmpeg", "-v"]
        assert "-f" in command
        assert command[command.index("-f") + 1] == "f32le"
        assert "-ar" not in command
        assert command[-1] == "-"
        return subprocess.CompletedProcess(command, 0, stdout=decoded.tobytes(), stderr=b"")

    monkeypatch.setattr(
        audio_loader,
        "shutil",
        SimpleNamespace(which=lambda name: "ffmpeg" if name == "ffmpeg" else None),
        raising=False,
    )
    monkeypatch.setattr(audio_loader, "_source_sample_rate", lambda path, *, ffmpeg_path: 44_100)
    monkeypatch.setattr(audio_loader, "subprocess", SimpleNamespace(run=fake_run, PIPE=subprocess.PIPE), raising=False)

    set_analysis_diagnostics_enabled(True)
    try:
        with caplog.at_level(logging.WARNING, logger="dj_track_similarity.audio_loader"):
            audio, sample_rate, detail = load_audio_mono(audio_path, torchaudio_module=FailingTorchaudio)
    finally:
        set_analysis_diagnostics_enabled(None)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert np.allclose(audio, decoded)
    assert "ffmpeg decode" in detail
    assert "TorchCodec is required" in detail
    assert "Audio decoder failed decoder=torchaudio" in caplog.text
    assert "Audio decode fallback succeeded decoder=ffmpeg" in caplog.text
    assert str(audio_path) in caplog.text

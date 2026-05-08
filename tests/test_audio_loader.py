from pathlib import Path
import wave

import numpy as np
import pytest

from dj_track_similarity.audio_loader import load_audio_mono


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


def test_load_audio_mono_recovers_malformed_wav_with_shifted_data_marker(tmp_path: Path) -> None:
    audio_path = tmp_path / "malformed.wav"
    _make_malformed_wave(audio_path)

    audio, sample_rate, detail = load_audio_mono(audio_path)

    assert sample_rate == 44_100
    assert audio.dtype == np.float32
    assert audio.shape == (3,)
    assert np.allclose(audio, np.array([2000, 0, 1500], dtype=np.float32) / 32768.0)
    assert "recovered malformed WAV" in detail


def test_load_audio_mono_rejects_unknown_malformed_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "broken.wav"
    audio_path.write_bytes(b"RIFF\x10\x00\x00\x00WAVEfmt ")

    with pytest.raises(RuntimeError, match="Unable to decode audio"):
        load_audio_mono(audio_path)

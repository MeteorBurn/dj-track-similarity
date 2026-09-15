from fractions import Fraction
from pathlib import Path
import sys
import types
import wave

import numpy as np
import pytest

from dj_track_similarity.audio.loader import (
    load_audio_mono_with_ffmpeg,
    load_decoded_audio,
    load_decoded_audio_with_ffmpeg,
)
from dj_track_similarity.audio.ffmpeg_runtime import load_project_pyav


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


def _write_identical_stereo_pcm_wav(path: Path, *, sample_rate: int = 44_100) -> np.ndarray:
    mono = np.array([0, 8192, 16384, 24576, 29490, -29490, -16384, -8192], dtype="<i2")
    samples = np.column_stack((mono, mono))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(samples.tobytes())
    return mono.astype(np.float32) / 32768.0


def _write_flac_with_corrupt_packet(path: Path, *, sample_rate: int = 44_100) -> int:
    """Write a FLAC file whose middle packet fails its checksum.

    FLAC checksums every frame, so flipping payload bytes damages exactly one packet
    and leaves the frames around it decodable.
    """

    av = load_project_pyav()
    total = sample_rate
    tone = np.arange(total, dtype=np.float32) / sample_rate
    samples = (np.sin(2 * np.pi * 440 * tone) * 0.5 * 32767).astype("<i2")

    intact = path.with_name(f"{path.stem}-intact.flac")
    with av.open(str(intact), mode="w") as container:
        stream = container.add_stream("flac", rate=sample_rate)
        stream.format = "s16"
        stream.layout = "mono"
        for start in range(0, total, 4096):
            frame = av.AudioFrame.from_ndarray(
                samples[start : start + 4096].reshape(1, -1),
                format="s16",
                layout="mono",
            )
            frame.sample_rate = sample_rate
            frame.pts = start
            frame.time_base = Fraction(1, sample_rate)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)

    encoded = bytearray(intact.read_bytes())
    middle = len(encoded) // 2
    for offset in range(middle, middle + 64):
        encoded[offset] ^= 0xFF
    path.write_bytes(bytes(encoded))
    return total


def _append_non_utf8_riff_info_tag(path: Path) -> None:
    """Append a RIFF INFO tag whose value is not valid UTF-8.

    Taggers do write Latin-1 payloads into RIFF INFO, and FFmpeg hands those bytes
    back untouched, so the container metadata cannot be decoded as UTF-8.
    """

    value = b"Caf\xb5 Del Mar\x00"  # 0xb5 never starts a valid UTF-8 sequence
    info = b"INFO" + b"INAM" + len(value).to_bytes(4, "little") + value
    raw = bytearray(path.read_bytes())
    raw += b"LIST" + len(info).to_bytes(4, "little") + info
    raw[4:8] = (len(raw) - 8).to_bytes(4, "little")
    path.write_bytes(bytes(raw))


def test_load_decoded_audio_preserves_native_sample_rate(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    audio_path = tmp_path / "track.wav"
    _write_pcm_wav(audio_path, sample_rate=44_100)

    result = load_decoded_audio(audio_path)

    assert result.path == str(audio_path)
    assert result.sample_rate == 44_100
    assert torch.equal(result.audio, torch.zeros(4, dtype=torch.float32))
    assert result.detail == "torchcodec 0.16 decode (num_channels=1)"


def test_load_decoded_audio_does_not_bypass_torchcodec_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
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


def test_ml_fallback_recovers_audio_when_torchcodec_rejects_a_corrupt_packet(
    tmp_path: Path,
) -> None:
    """The ML recovery decoder has to survive what the primary decoder rejects.

    TorchCodec aborts the whole file on the first malformed packet, so the fallback
    must reach a different decoder and keep the valid frames around the damage.
    """

    torch = pytest.importorskip("torch")
    AudioDecoder = pytest.importorskip("torchcodec.decoders").AudioDecoder
    audio_path = tmp_path / "corrupt.flac"
    intact_samples = _write_flac_with_corrupt_packet(audio_path)

    with pytest.raises(Exception):
        AudioDecoder(str(audio_path), num_channels=1).get_all_samples()

    decoded = load_decoded_audio_with_ffmpeg(audio_path)

    assert isinstance(decoded.audio, torch.Tensor)
    assert decoded.audio.dtype == torch.float32
    assert decoded.sample_rate == 44_100
    assert 0 < decoded.audio.numel() < intact_samples
    assert "discarded_corrupt_packets=" in decoded.detail


def test_shared_ffmpeg_decode_survives_non_utf8_container_tags(tmp_path: Path) -> None:
    """Unreadable container tags must not fail a track whose audio decodes.

    PyAV decodes container metadata on open, and this decoder never reads it, so a
    tag FFmpeg cannot hand back as UTF-8 has to stay invisible to the caller.
    """

    audio_path = tmp_path / "non-utf8-tag.wav"
    expected = _write_identical_stereo_pcm_wav(audio_path)
    _append_non_utf8_riff_info_tag(audio_path)

    av = load_project_pyav()
    with pytest.raises(UnicodeDecodeError):
        av.open(str(audio_path), mode="r")

    audio, sample_rate, _detail = load_audio_mono_with_ffmpeg(audio_path)

    assert sample_rate == 44_100
    assert audio.shape == expected.shape
    assert np.allclose(audio, expected, atol=1e-6)

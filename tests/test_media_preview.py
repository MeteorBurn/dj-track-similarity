from __future__ import annotations

import struct
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import anyio
import av
import pytest
from starlette.requests import ClientDisconnect

from dj_track_similarity.api import media_preview


def _write_wav(path: Path, *, frames: int, width: int = 2) -> bytes:
    pcm = b"".join(struct.pack("<hh", index, -index) for index in range(frames))
    source_pcm = pcm if width == 2 else b"".join(
        (value << 8).to_bytes(3, "little", signed=True)
        for index in range(frames) for value in (index, -index)
    )
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(width)
        audio.setframerate(44_100)
        audio.writeframes(source_pcm)
    return pcm


async def _read_response(response) -> bytes:
    chunks = []

    async def send(message):
        if message["type"] == "http.response.body":
            chunks.append(message["body"])

    async def receive():
        return {"type": "http.disconnect"}

    await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    return b"".join(chunks)


@pytest.fixture(autouse=True)
def _shared_pyav_without_processes(monkeypatch, tmp_path):
    monkeypatch.setattr(media_preview, "load_project_pyav", lambda: av)
    monkeypatch.setattr(media_preview.tempfile, "tempdir", str(tmp_path))

    def forbidden_process(*_args, **_kwargs):
        pytest.fail("Preview must decode through shared libraries without a subprocess")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)


def test_finite_preview_recovers_incomplete_pcm_tail_without_modifying_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "incomplete.wav"
    expected_pcm = _write_wav(source, frames=10_001, width=3)
    damaged = bytearray(source.read_bytes() + b"\x00\x00")
    struct.pack_into("<I", damaged, 4, len(damaged) - 8)
    struct.pack_into("<I", damaged, 40, len(damaged) - 44)
    source.write_bytes(damaged)

    response = media_preview.transcoded_wav_file_response(source)
    preview = Path(response.path)
    try:
        with wave.open(str(preview), "rb") as audio:
            assert audio.getnframes() == 10_001
            assert audio.readframes(audio.getnframes()) == expected_pcm
        assert source.read_bytes() == damaged
    finally:
        response.background.func(*response.background.args)
    assert not preview.exists()


@pytest.mark.parametrize("fail_on_message", [1, 3])
def test_streaming_preview_decodes_incrementally_and_closes_on_disconnect(
    monkeypatch, tmp_path: Path, fail_on_message: int,
) -> None:
    source = tmp_path / "stream.wav"
    _write_wav(source, frames=20_000)
    state = {"exhausted": False, "closed": False}

    class TrackedContainer:
        def __init__(self, *args, **kwargs):
            self.container = av.open(*args, **kwargs)
            self.streams = self.container.streams
            self.duration = self.container.duration

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.container.close()
            state["closed"] = True

        def demux(self, stream):
            yield from self.container.demux(stream)
            state["exhausted"] = True

    monkeypatch.setattr(media_preview, "load_project_pyav", lambda: SimpleNamespace(
        open=TrackedContainer, AudioResampler=av.AudioResampler,
        Packet=av.Packet, FFmpegError=av.FFmpegError,
    ))
    response = media_preview.streaming_wav_response(source)
    assert state == {"exhausted": False, "closed": False}

    async def disconnect():
        messages = 0

        async def send(_message):
            nonlocal messages
            messages += 1
            if messages == fail_on_message:
                raise OSError("client disconnected")

        async def receive():
            return {"type": "http.disconnect"}

        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    anyio.run(disconnect)
    assert state == {"exhausted": False, "closed": True}


def test_streaming_preview_recovers_packets_on_source_timeline_and_trims_seek(
    monkeypatch, tmp_path: Path,
) -> None:
    source = tmp_path / "damaged-packet.wav"
    expected_pcm = _write_wav(source, frames=20_000)
    original = source.read_bytes()
    damaged_span = []

    class BrokenPacket:
        def __init__(self, packet):
            self.packet = packet

        def __getattr__(self, name):
            return getattr(self.packet, name)

        def decode(self):
            raise av.InvalidDataError(1094995529, "damaged packet")

    class DamagedContainer:
        def __init__(self, *args, **kwargs):
            self.container = av.open(*args, **kwargs)
            self.streams = self.container.streams
            self.duration = self.container.duration

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.container.close()

        def demux(self, stream):
            for index, packet in enumerate(self.container.demux(stream)):
                if index == 1:
                    damaged_span.extend((packet.pts, packet.pts + packet.duration))
                    yield BrokenPacket(packet)
                else:
                    yield packet

    monkeypatch.setattr(media_preview, "load_project_pyav", lambda: SimpleNamespace(
        open=DamagedContainer, AudioResampler=av.AudioResampler,
        Packet=av.Packet, FFmpegError=av.FFmpegError,
    ))
    response = media_preview.streaming_wav_response(source)
    body = anyio.run(_read_response, response)
    gap_start, gap_end = (sample * 4 for sample in damaged_span)
    assert body[:4] == b"RIFF"
    assert body[8:12] == b"WAVE"
    assert body[44:] == expected_pcm[:gap_start] + bytes(gap_end - gap_start) + expected_pcm[gap_end:]
    assert "content-length" not in response.headers
    assert "accept-ranges" not in response.headers

    monkeypatch.setattr(media_preview, "load_project_pyav", lambda: av)
    start = 12_345.25 / 44_100
    seeked = anyio.run(_read_response, media_preview.streaming_wav_response(source, start=start))
    assert seeked[44:] == expected_pcm[12_345 * 4:]
    assert source.read_bytes() == original

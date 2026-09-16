from __future__ import annotations

import hashlib
from http.client import IncompleteRead
import importlib.util
import io
from pathlib import Path
import sys

import pytest


@pytest.fixture
def downloader():
    path = Path(__file__).resolve().parents[1] / "scripts" / "download_models.py"
    spec = importlib.util.spec_from_file_location("download_models_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __init__(self, data, *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data)), **(headers or {})}


def test_installs_verified_bytes_and_skips_them_on_repeat(downloader, monkeypatch, tmp_path):
    payload = b"synthetic model weights"
    target = tmp_path / "models" / "model.bin"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(downloader, "urlopen", lambda *_args, **_kwargs: Response(payload))
    assert downloader.download_file("https://example.test/model", target, digest)
    assert target.read_bytes() == payload
    assert list(target.parent.iterdir()) == [target]

    def forbidden(*_args, **_kwargs):
        pytest.fail("A valid installed asset must not be downloaded again")

    monkeypatch.setattr(downloader, "urlopen", forbidden)
    assert not downloader.download_file("https://example.test/model", target, digest)


def test_interrupted_transfer_preserves_target_then_resumes(downloader, monkeypatch, tmp_path):
    payload = b"new model checkpoint"
    target = tmp_path / "model.bin"
    target.write_bytes(b"previous target")
    digest = hashlib.sha256(payload).hexdigest()
    partial = target.with_name(f"{target.name}.{digest[:12]}.part")

    class InterruptedResponse(Response):
        def read(self, size):
            if self.tell():
                raise IncompleteRead(b"", len(payload) - 5)
            return super().read(5)

    monkeypatch.setattr(
        downloader, "urlopen", lambda *_args, **_kwargs: InterruptedResponse(payload)
    )
    monkeypatch.setattr(sys, "argv", [downloader.__file__])
    monkeypatch.setattr(
        downloader, "model_assets", lambda: [("https://example.test/model", target, digest)]
    )
    assert downloader.main() == 1
    assert target.read_bytes() == b"previous target"
    assert partial.read_bytes() == payload[:5]

    def resume(request, **_kwargs):
        assert request.headers["Range"] == "bytes=5-"
        return Response(
            payload[5:],
            status=206,
            headers={"Content-Range": f"bytes 5-{len(payload) - 1}/{len(payload)}"},
        )

    monkeypatch.setattr(downloader, "urlopen", resume)
    assert downloader.download_file("https://example.test/model", target, digest)
    assert target.read_bytes() == payload
    assert not partial.exists()


def test_bad_digest_cannot_replace_existing_target(downloader, monkeypatch, tmp_path):
    target = tmp_path / "model.bin"
    target.write_bytes(b"previous target")
    digest = hashlib.sha256(b"pinned content").hexdigest()
    monkeypatch.setattr(
        downloader, "urlopen", lambda *_args, **_kwargs: Response(b"corrupt download")
    )
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        downloader.download_file("https://example.test/model", target, digest)
    assert target.read_bytes() == b"previous target"
    assert list(tmp_path.iterdir()) == [target]

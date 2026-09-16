"""Install the exact local model assets required by the application adapters."""

from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPException
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.loading import _local_model_path
from dj_track_similarity.embedding.maest import MaestEmbeddingAdapter
from dj_track_similarity.embedding.mert import MertEmbeddingAdapter
from dj_track_similarity.embedding.mert_v2 import MertV2EmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter
from dj_track_similarity.embedding.muq import MuqEmbeddingAdapter


_CHUNK_SIZE = 1024 * 1024


def _file_digest(path: Path):
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    return digest


def model_assets():
    """Use the adapters' identities and manifests, including their text towers."""

    maest = MaestEmbeddingAdapter
    yield (
        maest.checkpoint_url,
        _local_model_path("maest", maest.checkpoint_filename),
        maest.checkpoint_sha256,
    )
    for directory, adapter in (
        ("mert", MertEmbeddingAdapter),
        ("mert-v2", MertV2EmbeddingAdapter),
        ("muq", MuqEmbeddingAdapter),
        ("mulan", MuqMulanEmbeddingAdapter),
    ):
        base = f"https://huggingface.co/{adapter.model_name}/resolve/{adapter.model_revision}"
        for filename, digest in adapter.snapshot_sha256:
            yield f"{base}/{filename}", _local_model_path(directory, filename), digest
    clap = ClapEmbeddingAdapter
    yield (
        f"https://huggingface.co/{clap.checkpoint_repo}/resolve/"
        f"{clap.model_revision}/{clap.checkpoint_filename}",
        _local_model_path("clap", clap.checkpoint_filename),
        clap.checkpoint_sha256,
    )
    for directory, adapter in (
        ("mulan/text", MuqMulanEmbeddingAdapter),
        ("clap/text", ClapEmbeddingAdapter),
    ):
        base = (
            f"https://huggingface.co/{adapter.text_model_name}/resolve/"
            f"{adapter.text_model_revision}"
        )
        for filename, digest in adapter.text_snapshot_sha256:
            yield f"{base}/{filename}", _local_model_path(directory, filename), digest


def download_file(url: str, target: Path, expected_sha256: str) -> bool:
    """Resume a partial transfer; publish only bytes matching the pinned digest."""

    if target.is_file() and _file_digest(target).hexdigest() == expected_sha256:
        print(f"Verified: {target}", flush=True)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.{expected_sha256[:12]}.part")
    digest = _file_digest(partial)
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset and digest.hexdigest() == expected_sha256:
        partial.replace(target)
        return True
    headers = {"User-Agent": "dj-track-similarity-model-installer"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    print(f"Downloading: {target} (resume at {offset:,} bytes)", flush=True)
    try:
        response = urlopen(Request(url, headers=headers), timeout=60)
    except HTTPError as error:
        if error.code != 416 or not offset:
            raise
        error.close()
        # An invalid/oversized partial file cannot be resumed.
        headers.pop("Range")
        response = urlopen(Request(url, headers=headers), timeout=60)
    with response:
        if response.status == 206:
            byte_range = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+|\*)",
                response.headers.get("Content-Range", ""),
            )
            if byte_range is None or int(byte_range[1]) != offset:
                raise RuntimeError(f"Invalid resume response for {target}")
        elif response.status == 200:
            offset = 0
            digest = hashlib.sha256()
        else:
            raise RuntimeError(f"Unexpected HTTP status {response.status} for {target}")
        content_length = response.headers.get("Content-Length")
        expected_size = offset + int(content_length) if content_length else None
        received = offset
        last_progress = time.monotonic()
        with partial.open("ab" if offset else "wb") as destination:
            while chunk := response.read(_CHUNK_SIZE):
                destination.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if time.monotonic() - last_progress >= 5:
                    total = f" / {expected_size:,}" if expected_size is not None else ""
                    print(f"  {received:,}{total} bytes", flush=True)
                    last_progress = time.monotonic()
        if expected_size is not None and received != expected_size:
            raise RuntimeError(
                f"Incomplete download for {target}: {received:,}/{expected_size:,} bytes. "
                "Run the installer again to resume."
            )
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        partial.unlink()
        raise RuntimeError(
            f"SHA-256 mismatch for {target}: expected {expected_sha256}, got {actual_sha256}. "
            "The existing target was preserved."
        )
    partial.replace(target)
    print(f"Installed: {target}", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        assets = list(model_assets())
        installed = sum(download_file(*asset) for asset in assets)
    except (OSError, HTTPException, URLError, RuntimeError) as error:
        print(f"Model installation failed: {error}", file=sys.stderr)
        print("Run the installer again to resume unfinished downloads.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Model installation interrupted; run again to resume.", file=sys.stderr)
        return 130
    print(f"Model assets ready: {len(assets)} verified, {installed} installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

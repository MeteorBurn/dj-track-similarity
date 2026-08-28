"""Embed the labelled pool with one LAION-CLAP checkpoint into a sidecar file.

Comparing CLAP checkpoints needs library audio embedded by each candidate: a
different checkpoint is a different joint space, so stored vectors cannot stand
in for it. Only the Rhythm Lab labelled pool is embedded, because that is the
pool `text_prompt_benchmark.py` scores on, and it is two orders of magnitude
smaller than the library.

The script reads audio and both databases and writes exactly one thing: the
``.npz`` sidecar named by ``--out``. It never writes to the library database, to
``classifier_scores``, or to any audio file, so a candidate checkpoint never
reaches production storage on the strength of an experiment.

The candidate checkpoints live in the same Hub repo and revision as the
production one and share its architecture, so they load through the production
adapter with the checkpoint file swapped. Each is pinned by SHA-256 here for the
same reason the production checkpoint is: an unpinned research run measures
whatever the Hub served that day.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
import time

import numpy as np
from numpy.typing import NDArray

from dj_track_similarity.audio_loader import (
    DecodedAudio,
    load_decoded_audio,
    load_decoded_audio_with_ffmpeg,
)
from dj_track_similarity.embedding import ClapEmbeddingAdapter

FloatArray = NDArray[np.float32]

DEFAULT_LABELS = Path("tools/rhythm-lab/database/rhythm_lab.sqlite")

# Checkpoints of the production architecture (HTSAT-base + roberta, no fusion)
# published in the repo the production checkpoint already comes from. The
# production entry repeats CLAP_CHECKPOINT_ID so a drifting pin fails loudly
# here instead of quietly comparing two different incumbents.
CHECKPOINTS: dict[str, str] = {
    "music_audioset_epoch_15_esc_90.14.pt": (
        "fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"
    ),
    "music_speech_audioset_epoch_15_esc_89.98.pt": (
        "51c68f12f9d7ea25fdaaccf741ec7f81e93ee594455410f3bca4f47f88d8e006"
    ),
}


def build_adapter(checkpoint: str, *, device: str) -> ClapEmbeddingAdapter:
    """Return the production adapter with one checkpoint file swapped in."""

    expected_sha256 = CHECKPOINTS.get(checkpoint)
    if expected_sha256 is None:
        raise SystemExit(
            f"unpinned checkpoint {checkpoint!r}; known: {', '.join(sorted(CHECKPOINTS))}"
        )
    adapter = ClapEmbeddingAdapter(device=device)
    if checkpoint != ClapEmbeddingAdapter.checkpoint_filename:
        adapter.checkpoint_filename = checkpoint
        adapter.checkpoint_sha256 = expected_sha256
    elif adapter.checkpoint_sha256 != expected_sha256:
        raise SystemExit(
            "the production checkpoint digest moved; update CHECKPOINTS before "
            "comparing against it"
        )
    return adapter


def labelled_tracks(
    db_path: Path,
    labels_path: Path,
) -> list[tuple[int, str]]:
    """Resolve the labelled pool to ``(track_id, file_path)``, sorted by id."""

    with sqlite3.connect(_read_only_uri(db_path), uri=True) as connection:
        track_id_of_uuid = dict(
            connection.execute("select track_uuid, track_id from tracks")
        )
        path_of_track = dict(
            connection.execute("select track_id, file_path from tracks")
        )
        track_id_of_path = {
            _path_key(file_path): track_id
            for track_id, file_path in path_of_track.items()
        }
    with sqlite3.connect(_read_only_uri(labels_path), uri=True) as connection:
        label_rows = connection.execute(
            "select track_uuid, selected_path from classifier_labels"
        ).fetchall()

    # A rescan regenerates track UUIDs, so resolve by UUID first and fall back
    # to the stored path, exactly as text_prompt_benchmark.py does.
    track_ids: set[int] = set()
    for track_uuid, selected_path in label_rows:
        track_id = track_id_of_uuid.get(track_uuid)
        if track_id is None and selected_path:
            track_id = track_id_of_path.get(_path_key(selected_path))
        if track_id is not None:
            track_ids.add(track_id)
    return [(track_id, path_of_track[track_id]) for track_id in sorted(track_ids)]


def decode_track(path: str) -> DecodedAudio | None:
    """Decode one track the way the analysis runners do, or report the failure.

    TorchCodec rejects a few files in this library outright. Production answers
    that with the shared FFmpeg decoder, which keeps the valid frames around a
    corrupt packet, so a research pass has to reach for it too or it measures a
    different, quietly smaller pool.
    """

    try:
        return load_decoded_audio(path)
    except Exception as torchcodec_error:  # noqa: BLE001 - decoder raises broadly
        try:
            return load_decoded_audio_with_ffmpeg(path)
        except Exception as ffmpeg_error:  # noqa: BLE001 - same
            print(
                f"undecodable, skipped: {path}\n"
                f"  torchcodec: {torchcodec_error}\n"
                f"  ffmpeg: {ffmpeg_error}",
                file=sys.stderr,
            )
            return None


def stored_vectors(db_path: Path, track_ids: list[int]) -> dict[int, FloatArray]:
    """Read the production checkpoint's vectors straight out of the library.

    Recomputing them reproduces the stored blobs exactly, so the incumbent arm
    is built by reading rather than by burning an hour of GPU on a known answer.
    """

    with sqlite3.connect(_read_only_uri(db_path), uri=True) as connection:
        rows = connection.execute(
            "select track_id, embedding_blob from clap_embeddings"
        ).fetchall()
    wanted = set(track_ids)
    return {
        int(track_id): np.frombuffer(blob, dtype=np.float32)
        for track_id, blob in rows
        if int(track_id) in wanted
    }


def write_sidecar(
    out_path: Path,
    *,
    track_ids: list[int],
    vectors: list[FloatArray],
    checkpoint: str,
) -> None:
    matrix = np.asarray(np.vstack(vectors), dtype=np.float32)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out_path,
        track_ids=np.asarray(track_ids, dtype=np.int64),
        vectors=matrix,
        checkpoint=np.asarray(checkpoint),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Library database to read.")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument(
        "--checkpoint",
        required=True,
        choices=sorted(CHECKPOINTS),
        help="LAION-CLAP checkpoint file to embed with.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Sidecar .npz to write.")
    parser.add_argument(
        "--source",
        choices=("audio", "stored"),
        default="audio",
        help=(
            "audio: decode and embed. stored: copy the library's existing"
            " vectors, which only answers for the production checkpoint."
        ),
    )
    parser.add_argument(
        "--mirror",
        type=Path,
        help=(
            "Restrict the pool to the track ids of another sidecar, so two arms"
            " are scored on exactly the same tracks."
        ),
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Tracks decoded and embedded per forward pass.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Embed only the first N of the pool. For probes, not for a report.",
    )
    args = parser.parse_args(argv)

    if args.source == "stored" and args.checkpoint != ClapEmbeddingAdapter.checkpoint_filename:
        raise SystemExit(
            "--source stored only answers for"
            f" {ClapEmbeddingAdapter.checkpoint_filename}; the library holds no"
            f" {args.checkpoint} vectors"
        )

    pool = labelled_tracks(args.db, args.labels)
    if args.mirror is not None:
        with np.load(args.mirror, allow_pickle=False) as payload:
            mirrored = {int(track_id) for track_id in payload["track_ids"]}
        pool = [entry for entry in pool if entry[0] in mirrored]
        if len(pool) != len(mirrored):
            raise SystemExit(
                f"{args.mirror} names {len(mirrored)} tracks but only"
                f" {len(pool)} are in this labelled pool"
            )
    if args.limit > 0:
        pool = pool[: args.limit]
    if not pool:
        raise SystemExit("no labelled track resolved against this library")

    if args.source == "stored":
        available = stored_vectors(args.db, [track_id for track_id, _path in pool])
        embedded_ids = [track_id for track_id, _path in pool if track_id in available]
        vectors = [available[track_id] for track_id in embedded_ids]
        skipped = len(pool) - len(embedded_ids)
    else:
        missing = [path for _track_id, path in pool if not Path(path).is_file()]
        if missing:
            raise SystemExit(
                f"{len(missing)} labelled audio files are missing, first: {missing[0]}"
            )
        adapter = build_adapter(args.checkpoint, device=args.device)
        print(f"loading {args.checkpoint}", file=sys.stderr)
        adapter.preflight()

        embedded_ids = []
        vectors = []
        skipped = 0
        started = time.perf_counter()
        batch_size = max(1, args.batch_size)
        for offset in range(0, len(pool), batch_size):
            batch = pool[offset : offset + batch_size]
            decodable: list[tuple[int, DecodedAudio]] = []
            for track_id, path in batch:
                decoded = decode_track(path)
                if decoded is None:
                    skipped += 1
                    continue
                decodable.append((track_id, decoded))
            if not decodable:
                continue
            batch_vectors = adapter.embed_decoded_batch(
                [decoded for _track_id, decoded in decodable]
            )
            for (track_id, _decoded), vector in zip(decodable, batch_vectors):
                embedded_ids.append(track_id)
                vectors.append(np.asarray(vector, dtype=np.float32))
            done = len(embedded_ids)
            elapsed = time.perf_counter() - started
            print(
                f"{done}/{len(pool)} tracks · {elapsed:.0f}s elapsed · "
                f"{elapsed / done:.2f}s per track",
                file=sys.stderr,
            )

    if not embedded_ids:
        raise SystemExit("no track could be embedded")
    write_sidecar(
        args.out,
        track_ids=embedded_ids,
        vectors=vectors,
        checkpoint=args.checkpoint,
    )
    # Never a silent truncation: a pool that shrank is a different pool, and
    # the other arm has to be mirrored onto this one before anything is read.
    print(
        f"wrote {len(embedded_ids)} vectors to {args.out}"
        + (f"; {skipped} tracks skipped" if skipped else "")
    )
    return 0


def _path_key(file_path: str) -> str:
    return file_path.replace("\\", "/").casefold()


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve(strict=False).as_uri()}?mode=ro"


if __name__ == "__main__":
    raise SystemExit(main())

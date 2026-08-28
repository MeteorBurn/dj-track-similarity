from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

import clap_checkpoint_embed as embed_script  # noqa: E402
import text_prompt_benchmark as benchmark  # noqa: E402

from dj_track_similarity.embedding import ClapEmbeddingAdapter  # noqa: E402


def test_only_pinned_checkpoints_can_be_embedded() -> None:
    """An unpinned checkpoint measures whatever the Hub served that day."""

    with pytest.raises(SystemExit):
        embed_script.build_adapter("630k-audioset-best.pt", device="cpu")


def test_a_candidate_checkpoint_swaps_the_file_and_its_digest_together() -> None:
    candidate = "music_speech_audioset_epoch_15_esc_89.98.pt"

    adapter = embed_script.build_adapter(candidate, device="cpu")

    assert adapter.checkpoint_filename == candidate
    assert adapter.checkpoint_sha256 == embed_script.CHECKPOINTS[candidate]
    # The candidate rides the production repo and revision, so a digest is the
    # only thing standing between the run and a different set of weights.
    assert adapter.checkpoint_repo == ClapEmbeddingAdapter.checkpoint_repo
    assert adapter.model_revision == ClapEmbeddingAdapter.model_revision


def test_the_production_checkpoint_keeps_the_digest_the_adapter_ships() -> None:
    adapter = embed_script.build_adapter(
        ClapEmbeddingAdapter.checkpoint_filename,
        device="cpu",
    )

    assert adapter.checkpoint_sha256 == ClapEmbeddingAdapter.checkpoint_sha256


def test_labelled_pool_resolves_by_uuid_and_falls_back_to_path(tmp_path: Path) -> None:
    library = tmp_path / "library.sqlite"
    labels = tmp_path / "labels.sqlite"
    audio = tmp_path / "kept.wav"
    audio.write_bytes(b"kept")
    renamed = tmp_path / "renamed.wav"
    renamed.write_bytes(b"renamed")
    _write_library(
        library,
        [(1, "uuid-kept", str(audio)), (2, "uuid-new", str(renamed))],
    )
    # The second label carries a stale UUID from before a rescan, so only its
    # stored path can still reach the track.
    _write_labels(
        labels,
        [("uuid-kept", ""), ("uuid-gone", str(renamed)), ("uuid-missing", "")],
    )

    pool = embed_script.labelled_tracks(library, labels)

    assert pool == [(1, str(audio)), (2, str(renamed))]


def test_sidecar_round_trips_into_the_benchmark_matrix(tmp_path: Path) -> None:
    sidecar = tmp_path / "candidate.npz"
    checkpoint = "music_speech_audioset_epoch_15_esc_89.98.pt"
    embed_script.write_sidecar(
        sidecar,
        track_ids=[7, 3],
        vectors=[
            np.asarray([3.0, 0.0, 0.0], dtype=np.float32),
            np.asarray([0.0, 0.0, 4.0], dtype=np.float32),
        ],
        checkpoint=checkpoint,
    )

    matrix, row_of_track = benchmark._load_sidecar_matrix(sidecar, checkpoint)

    assert row_of_track == {7: 0, 3: 1}
    np.testing.assert_allclose(matrix[0], [1.0, 0.0, 0.0])
    np.testing.assert_allclose(matrix[1], [0.0, 0.0, 1.0])


def test_a_sidecar_is_refused_for_the_checkpoint_that_did_not_write_it(
    tmp_path: Path,
) -> None:
    """Text and audio towers of one checkpoint are one space; crossing them
    compares nothing, so the mismatch has to fail rather than print numbers."""

    sidecar = tmp_path / "candidate.npz"
    embed_script.write_sidecar(
        sidecar,
        track_ids=[1],
        vectors=[np.asarray([1.0, 0.0], dtype=np.float32)],
        checkpoint="music_speech_audioset_epoch_15_esc_89.98.pt",
    )

    with pytest.raises(SystemExit):
        benchmark._load_sidecar_matrix(
            sidecar,
            ClapEmbeddingAdapter.checkpoint_filename,
        )


def test_a_candidate_checkpoint_without_a_sidecar_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        benchmark.main(
            [
                "--db",
                str(tmp_path / "library.sqlite"),
                "--clap-checkpoint",
                "music_speech_audioset_epoch_15_esc_89.98.pt",
            ]
        )


def test_undecodable_audio_falls_back_to_ffmpeg_then_is_skipped(monkeypatch) -> None:
    """Production answers a TorchCodec refusal with FFmpeg, so a research pass
    that only tries TorchCodec would measure a quietly smaller pool."""

    recovered = object()
    monkeypatch.setattr(
        embed_script,
        "load_decoded_audio",
        _raising(RuntimeError("Invalid data found when processing input")),
    )
    monkeypatch.setattr(
        embed_script,
        "load_decoded_audio_with_ffmpeg",
        lambda _path: recovered,
    )
    assert embed_script.decode_track("broken.flac") is recovered

    monkeypatch.setattr(
        embed_script,
        "load_decoded_audio_with_ffmpeg",
        _raising(RuntimeError("no valid frames")),
    )
    assert embed_script.decode_track("broken.flac") is None


def test_stored_vectors_are_refused_for_a_checkpoint_the_library_never_ran(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        embed_script.main(
            [
                "--db",
                str(tmp_path / "library.sqlite"),
                "--checkpoint",
                "music_speech_audioset_epoch_15_esc_89.98.pt",
                "--source",
                "stored",
                "--out",
                str(tmp_path / "out.npz"),
            ]
        )


def _raising(error: Exception):
    def _raise(_path):
        raise error

    return _raise


def _write_library(path: Path, rows: list[tuple[int, str, str]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table tracks (track_id integer primary key,"
            " track_uuid text, file_path text)"
        )
        connection.executemany("insert into tracks values (?, ?, ?)", rows)


def _write_labels(path: Path, rows: list[tuple[str, str]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table classifier_labels (track_uuid text, selected_path text)"
        )
        connection.executemany("insert into classifier_labels values (?, ?)", rows)

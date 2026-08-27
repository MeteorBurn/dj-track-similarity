from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup import core, spectral_check  # noqa: E402
from audio_dedup.spectral import (  # noqa: E402
    SpectralResult,
    TRANSCODE_MIN_SHARPNESS_DB,
    estimate_cutoff,
)


def test_estimate_cutoff_flags_brickwall_but_not_full_band_noise() -> None:
    rng = np.random.default_rng(20260827)
    sample_rate = 44_100
    noise = rng.standard_normal(sample_rate * 20).astype(np.float32)

    spectrum = np.fft.rfft(noise)
    frequencies = np.fft.rfftfreq(noise.size, d=1.0 / sample_rate)
    spectrum[frequencies > 16_000.0] = 0.0
    walled = np.fft.irfft(spectrum, n=noise.size).astype(np.float32)

    full_band = estimate_cutoff(noise, sample_rate)
    transcoded = estimate_cutoff(walled, sample_rate)

    assert not full_band.suspected_transcode
    assert full_band.cutoff_hz is not None and full_band.cutoff_hz >= 21_000.0
    assert transcoded.suspected_transcode
    assert transcoded.cutoff_hz is not None and 15_000.0 <= transcoded.cutoff_hz <= 16_600.0
    assert (
        transcoded.sharpness_db is not None
        and transcoded.sharpness_db >= TRANSCODE_MIN_SHARPNESS_DB
    )

    quiet_highs = walled.copy()
    hat = rng.standard_normal(sample_rate // 10).astype(np.float32)
    spectrum_hat = np.fft.rfft(hat)
    hat_frequencies = np.fft.rfftfreq(hat.size, d=1.0 / sample_rate)
    spectrum_hat[hat_frequencies < 16_000.0] = 0.0
    hat = np.fft.irfft(spectrum_hat, n=hat.size).astype(np.float32) * 0.25
    for start in range(0, quiet_highs.size - hat.size, sample_rate * 2):
        quiet_highs[start : start + hat.size] += hat
    sparse_full_band = estimate_cutoff(quiet_highs, sample_rate)
    assert not sparse_full_band.suspected_transcode
    assert sparse_full_band.cutoff_hz is not None and sparse_full_band.cutoff_hz >= 21_000.0

    honest_lossy = estimate_cutoff(
        walled,
        sample_rate,
        container_lossless=False,
        declared_bitrate_bps=128_000,
    )
    fake_lossy = estimate_cutoff(
        walled,
        sample_rate,
        container_lossless=False,
        declared_bitrate_bps=320_000,
    )
    assert not honest_lossy.suspected_transcode
    assert "matches declared 128 kbps" in honest_lossy.note
    assert fake_lossy.suspected_transcode
    assert "below declared 320 kbps" in fake_lossy.note


def test_spectral_check_script_reports_verdicts_and_csv(tmp_path: Path) -> None:
    import io

    fake_flac = tmp_path / "fake.flac"
    honest_mp3 = tmp_path / "honest.mp3"
    fake_flac.write_bytes(b"x")
    honest_mp3.write_bytes(b"x")
    listing = tmp_path / "files.txt"
    listing.write_text(f'"{fake_flac}"\n\n{honest_mp3}\n', encoding="utf-8")

    files = spectral_check.collect_files([], listing)
    assert files == [fake_flac, honest_mp3]

    def fake_analyzer(
        path: str,
        *,
        sample_rate: int | None,
        duration_seconds: float | None,
        declared_bitrate_bps: int | None = None,
    ) -> SpectralResult:
        assert sample_rate == 44_100 and duration_seconds == 300.0
        suspected = path.endswith("fake.flac")
        return SpectralResult(
            cutoff_hz=16_000.0 if suspected else 21_500.0,
            sharpness_db=40.0 if suspected else None,
            sample_rate=sample_rate,
            suspected_transcode=suspected,
            note="brickwall at 16.0 kHz (~128 kbps class)" if suspected else "full band",
        )

    rows = spectral_check.run_checks(
        files,
        analyzer=fake_analyzer,
        prober=lambda _path: (44_100, 300.0, 1_000_000),
        progress_stream=io.StringIO(),
    )
    assert [row["verdict"] for row in rows] == ["suspected_transcode", "clean"]

    csv_path = tmp_path / "out.csv"
    spectral_check.write_output(rows, csv_path=csv_path)
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "path,verdict,cutoff_hz,sharpness_db,sample_rate,note"
    assert "suspected_transcode" in lines[1] and "16000.0" in lines[1]
    assert "clean" in lines[2]


def test_suspected_transcode_loses_keepership_and_is_labeled() -> None:
    def _track(track_id: int, path: str) -> core.TrackRecord:
        return core.TrackRecord(
            track_id=track_id,
            path=path,
            size=40_000_000,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=300.0,
            metadata={},
            embeddings={},
        )

    tracks = [
        _track(1, "C:/music/fake.flac"),
        _track(2, "C:/music/true.wav"),
    ]
    spectral_map = {
        1: SpectralResult(
            cutoff_hz=16_000.0,
            sharpness_db=60.0,
            sample_rate=44_100,
            suspected_transcode=True,
            note="brickwall at 16.0 kHz",
        ),
        2: SpectralResult(
            cutoff_hz=21_800.0,
            sharpness_db=None,
            sample_rate=44_100,
            suspected_transcode=False,
            note="full band",
        ),
    }

    assert core.choose_keeper(tracks, spectral_results=spectral_map).track_id == 2
    assert core.choose_keeper(tracks).track_id == 1

    config = core.resolve_preset("safe", min_score=None)
    groups = core.find_duplicate_groups(
        tracks,
        config,
        limit_groups=None,
        candidate_sources={(1, 2): ("fingerprint_lsh",)},
        fingerprint_scores={(1, 2): 0.97},
    )
    payload = core.build_report(
        groups,
        tracks,
        config,
        root=Path("C:/music"),
        path_contains=[],
        spectral_results=spectral_map,
    )

    group_payload = payload["groups"][0]
    keeper_payload = group_payload["suggested_keeper"]
    candidate = group_payload["candidate_deletes"][0]
    assert keeper_payload["track_id"] == 2
    assert keeper_payload["suspected_transcode"] is False
    assert any("transcoded" in line for line in keeper_payload["why_keep"])
    assert candidate["track_id"] == 1
    assert candidate["suspected_transcode"] is True
    assert candidate["spectral_note"] == "brickwall at 16.0 kHz"
    assert any("transcoded" in line for line in candidate["why_delete_or_review"])
    assert payload["spectral_analysis"]["suspected_transcode_count"] == 1

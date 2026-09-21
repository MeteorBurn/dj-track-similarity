from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
import pytest

TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup import config as config_module  # noqa: E402

from audio_dedup import keeper as keeper_module  # noqa: E402

from audio_dedup import models as models_module  # noqa: E402

from audio_dedup import report_payload as report_payload_module  # noqa: E402

from audio_dedup import scoring as scoring_module  # noqa: E402

from audio_dedup import spectral_check  # noqa: E402
from audio_dedup.spectral import (  # noqa: E402
    SpectralResult,
    TRANSCODE_MIN_SHARPNESS_DB,
    analyze_file,
    estimate_cutoff,
    skipped_result,
)


def test_analyze_file_decodes_through_the_shared_libraries(monkeypatch, tmp_path: Path) -> None:
    def forbidden_process(*_args, **_kwargs):
        pytest.fail("the spectral check must decode in process, not through a program")

    monkeypatch.setattr(subprocess, "run", forbidden_process)
    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    rate = 44_100
    samples = np.random.default_rng(20260921).standard_normal(rate * 4) * 0.08
    spectrum = np.fft.rfft(samples)
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / rate)
    spectrum[frequencies > 16_000.0] = 0.0
    lows = np.fft.irfft(spectrum, n=samples.size)
    highs = samples - lows
    stereo = np.column_stack((lows + highs, lows - highs))
    audio_path = tmp_path / "tone.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((stereo * 32_767.0).astype("<i2").tobytes())

    result = analyze_file(str(audio_path), duration_seconds=4.0)

    assert result.sample_rate == rate
    assert result.cutoff_hz is not None and result.cutoff_hz >= 21_000.0
    assert result.suspected_transcode is False

    # The codec, not its container suffix, determines the lossy expectation.
    from dj_track_similarity.audio.ffmpeg_runtime import load_project_pyav

    av = load_project_pyav()
    encoded_results = []
    for suffix, container_format in (("aac", "adts"), ("m4a", "mp4")):
        encoded_path = tmp_path / f"encoded.{suffix}"
        with av.open(str(encoded_path), "w", format=container_format) as container:
            stream = container.add_stream("aac", rate=rate)
            stream.bit_rate = 128_000
            stream.layout = "mono"
            for start in range(0, samples.size, 1024):
                frame = av.AudioFrame.from_ndarray(
                    lows[None, start : start + 1024].astype(np.float32),
                    format="fltp", layout="mono",
                )
                frame.sample_rate = rate
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode(None):
                container.mux(packet)
        encoded_results.append(analyze_file(
            str(encoded_path), duration_seconds=4.0,
        ))
    assert all(item.cutoff_hz is not None for item in encoded_results)
    assert not any(item.suspected_transcode for item in encoded_results)
    assert abs(encoded_results[0].cutoff_hz - encoded_results[1].cutoff_hz) < 200.0


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
    assert fake_lossy.suspected_transcode

    # An uncalibrated bitrate does not provide evidence for a transcode verdict.
    unchecked_lossy = estimate_cutoff(
        walled,
        sample_rate,
        container_lossless=False,
        declared_bitrate_bps=96_000,
    )
    assert unchecked_lossy.suspected_transcode is None
    missing_bitrate = estimate_cutoff(walled, sample_rate, container_lossless=False)
    assert missing_bitrate.suspected_transcode is None

    unknown_codec = estimate_cutoff(walled, sample_rate, container_lossless=None)
    assert unknown_codec.cutoff_hz == transcoded.cutoff_hz
    assert unknown_codec.suspected_transcode is None


def test_spectral_check_script_reports_verdicts_and_csv(tmp_path: Path) -> None:
    import io

    fake_flac = tmp_path / "fake.flac"
    honest_mp3 = tmp_path / "honest.mp3"
    unknown_file = tmp_path / "unknown.m4a"
    fake_flac.write_bytes(b"x")
    honest_mp3.write_bytes(b"x")
    unknown_file.write_bytes(b"x")
    listing = tmp_path / "files.txt"
    listing.write_text(f'"{fake_flac}"\n\n{honest_mp3}\n{unknown_file}\n', encoding="utf-8")

    files = spectral_check.collect_files([], listing)
    assert files == [fake_flac, honest_mp3, unknown_file]

    def fake_analyzer(
        path: str,
        *,
        duration_seconds: float | None,
    ) -> SpectralResult:
        assert duration_seconds == 300.0
        suspected = None if path.endswith("unknown.m4a") else path.endswith("fake.flac")
        return SpectralResult(
            cutoff_hz=16_000.0 if suspected else 21_500.0,
            sharpness_db=40.0 if suspected else None,
            sample_rate=44_100,
            suspected_transcode=suspected,
            note="brickwall at 16.0 kHz (~128 kbps class)" if suspected else "full band",
        )

    rows = spectral_check.run_checks(
        files,
        analyzer=fake_analyzer,
        prober=lambda _path: (44_100, 300.0, 1_000_000),
        progress_stream=io.StringIO(),
    )
    assert [row["verdict"] for row in rows] == ["suspected_transcode", "clean", "inconclusive"]

    csv_path = tmp_path / "out.csv"
    spectral_check.write_output(rows, csv_path=csv_path)
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "path,verdict,cutoff_hz,sharpness_db,sample_rate,note"
    assert "suspected_transcode" in lines[1] and "16000.0" in lines[1]
    assert "clean" in lines[2]
    assert "inconclusive" in lines[3]


def test_lossless_wall_is_judged_against_the_file_s_own_ceiling() -> None:
    """A 48 kHz container must not be judged by a 44.1 kHz number.

    Opus walls at about 20.3 kHz and decodes at 48 kHz, so against the 44.1 kHz
    calibration it reads as honest. Against its own Nyquist it does not. The
    44.1 kHz side of the same rule must not move.
    """
    rng = np.random.default_rng(20260921)

    def walled(sample_rate: int, cutoff_hz: float) -> np.ndarray:
        noise = rng.standard_normal(sample_rate * 20).astype(np.float32)
        spectrum = np.fft.rfft(noise)
        frequencies = np.fft.rfftfreq(noise.size, d=1.0 / sample_rate)
        spectrum[frequencies > cutoff_hz] = 0.0
        return np.fft.irfft(spectrum, n=noise.size).astype(np.float32)

    opus_like = estimate_cutoff(walled(48_000, 20_300.0), 48_000)
    assert opus_like.suspected_transcode

    # The same wall inside a 44.1 kHz file sits above that file's own ceiling and
    # stays unflagged, which is the calibrated behaviour this must not disturb.
    honest_44k = estimate_cutoff(walled(44_100, 19_900.0), 44_100)
    assert not honest_44k.suspected_transcode


def test_bandwidth_does_not_establish_the_original_sample_rate() -> None:
    from scipy.signal import resample_poly

    rng = np.random.default_rng(20260921)
    results = []
    for source_rate in (96_000, 48_000):
        samples = rng.standard_normal(source_rate * 4).astype(np.float32)
        spectrum = np.fft.rfft(samples)
        frequencies = np.fft.rfftfreq(samples.size, d=1.0 / source_rate)
        spectrum[frequencies > 20_000.0] = 0.0
        filtered = np.fft.irfft(spectrum, n=samples.size).astype(np.float32)
        if source_rate == 48_000:
            filtered = resample_poly(filtered, 2, 1)
        result = estimate_cutoff(filtered, 96_000)
        assert result.cutoff_hz is not None and 19_000.0 <= result.cutoff_hz <= 21_000.0
        results.append(result)

    # Both native band-limited audio and resampled audio have this spectrum.
    # Neither permits asserting an exact source rate such as 44.1 kHz.
    assert all(result.effective_source_rate_hz is None for result in results)


def test_suspected_transcode_loses_keepership_and_is_labeled() -> None:
    def _track(track_id: int, path: str) -> models_module.TrackRecord:
        return models_module.TrackRecord(
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
        )

    # The fake is the copy the library would otherwise prefer: it wins the format
    # key with nothing measured, so the flip below is the spectral verdict rather
    # than a container preference.
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

    assert keeper_module.choose_keeper(tracks, spectral_results=spectral_map).track_id == 2
    assert keeper_module.choose_keeper(tracks).track_id == 1

    groups = scoring_module.groups_from_fingerprint_pairs(
        tracks,
        {(1, 2): 0.97},
    )
    payload = report_payload_module.build_report(
        groups,
        tracks,
        mode=config_module.MODE_FINGERPRINT_LSH,
        path_contains=[],
        spectral_results=spectral_map,
    )

    group_payload = payload["groups"][0]
    keeper_payload = group_payload["suggested_keeper"]
    candidate = group_payload["candidate_deletes"][0]
    assert keeper_payload["track_id"] == 2
    assert keeper_payload["suspected_transcode"] is False
    assert candidate["track_id"] == 1
    assert candidate["suspected_transcode"] is True
    assert candidate["spectral_note"] == "brickwall at 16.0 kHz"
    assert payload["spectral_analysis"]["suspected_transcode_count"] == 1
    assert payload["statistics"]["fake_bitrate_candidate_count"] == 1
    assert payload["statistics"]["fake_bitrate_group_count"] == 1

    # Unavailable analysis is not evidence of a clean or full-band copy.
    unknown_codec = SpectralResult(
        cutoff_hz=22_050.0, sharpness_db=None, sample_rate=44_100,
        suspected_transcode=None, note="unknown codec",
    )
    for unavailable in (None, skipped_result("decode failed"), unknown_codec):
        unavailable_map = {2: spectral_map[1]}
        if unavailable is not None:
            unavailable_map[1] = unavailable
        assert keeper_module.choose_keeper(tracks, spectral_results=unavailable_map).track_id == 2
        unavailable_payload = report_payload_module.build_report(
            groups, tracks, mode=config_module.MODE_FINGERPRINT_LSH,
            path_contains=[], spectral_results=unavailable_map,
        )["groups"][0]
        assert unavailable_payload["suggested_keeper"]["track_id"] == 2
        assert unavailable_payload["quality_comparison_requires_review"] is True
        assert unavailable_payload["candidate_deletes"][0]["spectral_cutoff_hz"] == (
            unavailable.cutoff_hz if unavailable is not None else None
        )

    # A lossy verdict must not discard the measured bandwidth and let declared
    # bitrate choose the narrower of two suspect copies.
    lossy_tracks = [
        replace(tracks[0], path="C:/music/narrow.mp3", metadata={"bit_rate_bps": 320_000}),
        replace(tracks[1], path="C:/music/wider.mp3", metadata={"bit_rate_bps": 256_000}),
    ]
    suspect_map = {1: spectral_map[1], 2: replace(spectral_map[1], cutoff_hz=18_000.0)}
    assert keeper_module.choose_keeper(lossy_tracks).track_id == 1
    assert keeper_module.choose_keeper(lossy_tracks, spectral_results=suspect_map).track_id == 2
    suspect_payload = report_payload_module.build_report(
        groups, lossy_tracks, mode=config_module.MODE_FINGERPRINT_LSH,
        path_contains=[], spectral_results=suspect_map,
    )["groups"][0]
    assert suspect_payload["suggested_keeper"]["track_id"] == 2
    assert suspect_payload["suggested_keeper"]["spectral_cutoff_hz"] == 18_000.0
    assert suspect_payload["candidate_deletes"][0]["spectral_cutoff_hz"] == 16_000.0


def test_group_the_comparator_cannot_judge_is_review_only() -> None:
    """A group the measurements cannot rank is handed over, not deleted inside.

    Two encodes of one master measure within a fraction of a unit of each other,
    so a wider spread means different masterings and preferring one is a taste
    call. A container that does not prove its codec, and a group mixing DSD with
    PCM, are the same situation from the other side: the facts on file cannot
    rank the copies at all.
    """

    def _track(track_id: int, path: str, dynamic_range: float) -> models_module.TrackRecord:
        return models_module.TrackRecord(
            track_id=track_id,
            path=path,
            size=40_000_000 + track_id,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=300.0,
            metadata={
                "sample_rate_hz": 44_100,
                "bit_depth": 16,
                "bit_rate_bps": 852_000,
                "channel_count": 2,
                "sonara_features": {
                    "dynamic_range_db": dynamic_range,
                    "loudness_lufs": -9.0,
                    "loudness_range_lu": 8.0,
                },
            },
        )

    original = _track(1, "C:/music/original.flac", 12.4)
    remaster = _track(2, "C:/music/remaster.flac", 8.1)
    near_copy = _track(3, "C:/music/near.flac", 11.0)

    assert keeper_module.is_same_master([original, near_copy]) is True
    assert keeper_module.is_same_master([original, remaster]) is False
    # Inside one master the wider range still ranks; across masters it does not.
    assert keeper_module.choose_keeper([original, near_copy]).track_id == 1

    groups = scoring_module.groups_from_fingerprint_pairs(
        [original, remaster],
        {(1, 2): 0.99},
    )
    payload = report_payload_module.build_report(
        groups,
        [original, remaster],
        mode=config_module.MODE_FINGERPRINT_LSH,
        path_contains=[],
    )

    group_payload = payload["groups"][0]
    candidate = group_payload["candidate_deletes"][0]
    assert group_payload["possible_different_master"] is True
    assert group_payload["quality_comparison_requires_review"] is True
    assert any("possible different master" in reason for reason in candidate["review_reasons"])

    # An extension names a container, not the codec inside it, and DSD does not
    # compare to PCM by depth and rate. Both leave the comparator with nothing.
    ambiguous = _track(4, "C:/music/copy.m4a", 12.4)
    dsd = _track(5, "C:/music/copy.dsf", 12.4)
    assert keeper_module.keeper_review_reasons([original, near_copy]) == []
    assert keeper_module.keeper_review_reasons([original, ambiguous]) != []
    assert keeper_module.keeper_review_reasons([original, dsd]) != []

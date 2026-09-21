from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import numpy as np

from dj_track_similarity.audio.ffmpeg_runtime import load_project_pyav

from .progress import _raise_if_cancelled

SPECTRAL_SEGMENT_SECONDS = 24.0
SPECTRAL_WINDOW_POSITIONS = (0.15, 0.5, 0.8)
SPECTRAL_WINDOW_SAMPLES = 2048
SPECTRAL_REFERENCE_BAND_HZ = (1_000.0, 8_000.0)
SPECTRAL_ENERGY_FLOOR_DB = 50.0
SPECTRAL_LOUD_FRAME_WINDOW_DB = 30.0
SPECTRAL_SMOOTH_HZ = 180.0
SPECTRAL_SHARPNESS_GAP_HZ = 300.0
SPECTRAL_SHARPNESS_SPAN_HZ = 1_500.0
# Calibrated 2026-08-27 against a Fakin' The Funk reference over 1000 library
# files (37 confirmed transcodes): 10 false alarms / 5 misses, every miss in
# the ~224-256 kbps class. Raising the ceiling or the sharpness gate re-misses
# 128-192 kbps fakes; lowering them flags dark but honest masters.
TRANSCODE_MAX_CUTOFF_HZ = 19_450.0
# That calibration is a 44.1 kHz measurement, and a 48 kHz file judged against it
# is judged against a ceiling that is not its own: Opus walls at ~20.3 kHz and
# decodes at 48 kHz, so the absolute form flagged 0 of 14 Opus transcodes. The
# share of Nyquist travels instead. Measured 2026-09-21 on 300 of the library's
# 3 791 lossless-container files at 48 kHz: the absolute form found 5 walls, the
# share found 20, and each of the 15 it added carried an encoder-shaped wall at
# 20.0-20.8 kHz with 15-69 dB of sharpness. Genuine 48 kHz masters sit far above
# it, with a 24.0 kHz median cutoff and a 21.4 kHz tenth percentile.
#
# The scale stops at 48 kHz because the evidence does. An encoder picks its
# lowpass from the bitrate, as an absolute frequency, and no lossy format runs
# above 48 kHz, so there is no such thing as a 42 kHz encoder wall to look for.
# Scaling on to 96 kHz only moved the line past genuine hi-res: it took the flag
# count on the library's 146 hi-res files from 4 to 26.
TRANSCODE_CALIBRATION_NYQUIST_HZ = 22_050.0
TRANSCODE_MAX_SCALED_NYQUIST_HZ = 24_000.0
TRANSCODE_MIN_SHARPNESS_DB = 14.0
FULL_BAND_MIN_CUTOFF_HZ = 21_000.0
DECODE_TIMEOUT_SECONDS = 120
# Boundaries sit in the gaps between the classes measured in the Fakin' The Funk
# reference, which pairs a cutoff with the real bitrate it came from: 128 kbps
# spans 16000-16891 Hz, 160 spans 16938-17717, 192 spans 18019-18709, and
# 224 and 256 overlap at 18881-19549, so they share one label.
CUTOFF_BITRATE_CLASSES = (
    (19_800.0, "~320 kbps class"),
    (18_795.0, "~224-256 kbps class"),
    (17_868.0, "~192 kbps class"),
    (16_915.0, "~160 kbps class"),
    (15_200.0, "~128 kbps class"),
    (0.0, "<=112 kbps class"),
)
DECLARED_BITRATE_MIN_CUTOFF_HZ = (
    (320_000, 19_800.0),
    (256_000, 18_800.0),
    (224_000, 18_300.0),
    (192_000, 17_600.0),
    (160_000, 16_600.0),
    (128_000, 15_200.0),
)

@dataclass(frozen=True)
class SpectralResult:
    """Spectral evidence for one duplicate-group file; a heuristic, never a deletion verdict."""

    cutoff_hz: float | None
    sharpness_db: float | None
    sample_rate: int | None
    suspected_transcode: bool | None
    note: str
    # Retained for saved-report compatibility. Bandwidth cannot establish the
    # source sample rate, so new measurements leave this unset.
    effective_source_rate_hz: float | None = None


@dataclass(frozen=True)
class _DecodedWindow:
    samples: np.ndarray  # channels, samples; never summed across channels
    sample_rate: int
    container_lossless: bool | None
    bit_rate: int | None


def skipped_result(note: str) -> SpectralResult:
    return SpectralResult(
        cutoff_hz=None,
        sharpness_db=None,
        sample_rate=None,
        effective_source_rate_hz=None,
        suspected_transcode=False,
        note=note,
    )


def decoder_available() -> bool:
    try:
        load_project_pyav()
    except RuntimeError:
        return False
    return True


def analyze_file(
    path: str,
    *,
    duration_seconds: float | None,
    should_cancel: Callable[[], bool] | None = None,
) -> SpectralResult:
    """Measure duplicate-copy bandwidth using decoded stream facts and channel power."""
    if duration_seconds is not None and duration_seconds > SPECTRAL_SEGMENT_SECONDS:
        starts = sorted(
            {
                max(0.0, duration_seconds * position - SPECTRAL_SEGMENT_SECONDS / 2.0)
                for position in SPECTRAL_WINDOW_POSITIONS
            }
        )
    else:
        starts = [0.0]
    window_results: list[SpectralResult] = []
    skip_note = "decode failed"
    for start_seconds in starts:
        _raise_if_cancelled(should_cancel)
        try:
            decoded = _pyav_decode(path, start_seconds, should_cancel=should_cancel)
        except (OSError, ValueError):
            continue
        _raise_if_cancelled(should_cancel)
        samples = decoded.samples
        if samples.shape[-1] < SPECTRAL_WINDOW_SAMPLES * 4:
            skip_note = "decoded segment too short"
            continue
        if not np.all(np.isfinite(samples)) or float(np.max(np.abs(samples))) <= 0.0:
            skip_note = "decoded segment is silent or invalid"
            continue
        window_results.append(
            estimate_cutoff(
                samples,
                decoded.sample_rate,
                container_lossless=decoded.container_lossless,
                declared_bitrate_bps=decoded.bit_rate,
            )
        )
    _raise_if_cancelled(should_cancel)
    if not window_results:
        return skipped_result(skip_note)
    # Use the widest observed window; this is bandwidth evidence, not proof of
    # the file's encoding or mastering history.
    return max(window_results, key=lambda result: result.cutoff_hz or 0.0)


def estimate_cutoff(
    samples: np.ndarray,
    sample_rate: int,
    *,
    container_lossless: bool | None = True,
    declared_bitrate_bps: int | None = None,
) -> SpectralResult:
    """Locate the highest sustained frequency and how brickwalled the drop above it is.

    The segment's loud frames are averaged in linear power, so sparse but real
    highs (hi-hats, crashes) keep a full-band file above the floor while the
    faint transient bleed above an encoder's lowpass stays under it. The floor
    sits SPECTRAL_ENERGY_FLOOR_DB below the 1-8 kHz reference median.
    """
    if sample_rate <= 0:
        return skipped_result("unknown sample rate")
    if samples.ndim not in (1, 2) or samples.shape[-1] < SPECTRAL_WINDOW_SAMPLES * 4:
        return skipped_result("decoded segment too short")
    frames_db, frequencies = _frame_spectra_db(
        samples.astype(np.float32, copy=False),
        sample_rate,
    )
    bin_hz = float(frequencies[1] - frequencies[0])
    smooth_bins = max(1, int(round(SPECTRAL_SMOOTH_HZ / bin_hz)))
    smoothed_frames = _box_smooth_rows(frames_db, smooth_bins)

    reference_mask = (frequencies >= SPECTRAL_REFERENCE_BAND_HZ[0]) & (
        frequencies <= SPECTRAL_REFERENCE_BAND_HZ[1]
    )
    if not np.any(reference_mask):
        return skipped_result("reference band missing")
    frame_references = np.median(smoothed_frames[:, reference_mask], axis=1)
    loud_enough = frame_references >= (
        float(frame_references.max()) - SPECTRAL_LOUD_FRAME_WINDOW_DB
    )
    if not np.any(loud_enough):
        return skipped_result("no band above floor")
    loud_power = np.power(10.0, smoothed_frames[loud_enough] / 10.0)
    smoothed = 10.0 * np.log10(np.maximum(loud_power.mean(axis=0), 1e-20))
    energy_reference = float(np.median(smoothed[reference_mask]))
    above_floor = smoothed >= energy_reference - SPECTRAL_ENERGY_FLOOR_DB
    above_floor[frequencies <= 0] = False
    if not np.any(above_floor):
        return skipped_result("no band above floor")
    cutoff_hz = float(frequencies[np.flatnonzero(above_floor)[-1]])

    nyquist = sample_rate / 2.0
    sharpness_db: float | None = None
    below_mask = (
        frequencies >= cutoff_hz - SPECTRAL_SHARPNESS_SPAN_HZ
    ) & (frequencies <= cutoff_hz - SPECTRAL_SHARPNESS_GAP_HZ)
    above_mask = (
        frequencies >= cutoff_hz + SPECTRAL_SHARPNESS_GAP_HZ
    ) & (frequencies <= cutoff_hz + SPECTRAL_SHARPNESS_SPAN_HZ)
    if np.any(below_mask) and np.any(above_mask):
        sharpness_db = float(
            np.mean(smoothed[below_mask]) - np.mean(smoothed[above_mask])
        )

    brickwall = (
        nyquist - cutoff_hz > SPECTRAL_SHARPNESS_SPAN_HZ
        and sharpness_db is not None
        and sharpness_db >= TRANSCODE_MIN_SHARPNESS_DB
    )
    full_band_floor = min(FULL_BAND_MIN_CUTOFF_HZ, nyquist - SPECTRAL_SHARPNESS_GAP_HZ)
    if brickwall and cutoff_hz < full_band_floor:
        note = f"brickwall at {cutoff_hz / 1000.0:.1f} kHz ({_bitrate_class(cutoff_hz)})"
    elif cutoff_hz >= full_band_floor:
        note = "full band"
    else:
        note = f"rolls off near {cutoff_hz / 1000.0:.1f} kHz"

    if container_lossless is True:
        scaled_nyquist = min(nyquist, TRANSCODE_MAX_SCALED_NYQUIST_HZ)
        max_cutoff_hz = TRANSCODE_MAX_CUTOFF_HZ * (
            scaled_nyquist / TRANSCODE_CALIBRATION_NYQUIST_HZ
        )
        suspected = brickwall and cutoff_hz < max_cutoff_hz
    elif container_lossless is False:
        expected_cutoff = _declared_min_cutoff(declared_bitrate_bps)
        suspected = None if expected_cutoff is None else brickwall and cutoff_hz < expected_cutoff
        # Below the table nothing was compared, so the note claims no relation.
        if expected_cutoff is not None and brickwall:
            relation = "below" if suspected else "matches"
            note = f"{note}, {relation} declared {declared_bitrate_bps // 1000} kbps"
        elif expected_cutoff is None:
            note = f"{note}, declared bitrate unavailable or outside comparison range"
    else:
        suspected = None
        note = f"{note}, codec quality class unknown"
    return SpectralResult(
        cutoff_hz=round(cutoff_hz, 1),
        sharpness_db=None if sharpness_db is None else round(sharpness_db, 1),
        sample_rate=int(sample_rate),
        suspected_transcode=bool(suspected) if suspected is not None else None,
        note=note,
    )


def _bitrate_class(cutoff_hz: float) -> str:
    for threshold_hz, label in CUTOFF_BITRATE_CLASSES:
        if cutoff_hz >= threshold_hz:
            return label
    return CUTOFF_BITRATE_CLASSES[-1][1]


def _declared_min_cutoff(declared_bitrate_bps: int | None) -> float | None:
    if declared_bitrate_bps is None or declared_bitrate_bps <= 0:
        return None
    for min_bitrate_bps, min_cutoff_hz in DECLARED_BITRATE_MIN_CUTOFF_HZ:
        if declared_bitrate_bps >= min_bitrate_bps:
            return min_cutoff_hz
    return None


def _box_smooth_rows(rows: np.ndarray, kernel_bins: int) -> np.ndarray:
    if kernel_bins <= 1:
        return rows.astype(np.float64, copy=False)
    pad_left = kernel_bins // 2
    pad_right = kernel_bins - 1 - pad_left
    padded = np.pad(rows, ((0, 0), (pad_left, pad_right)), mode="edge")
    cumulative = np.concatenate(
        [
            np.zeros((rows.shape[0], 1), dtype=np.float64),
            np.cumsum(padded, axis=1, dtype=np.float64),
        ],
        axis=1,
    )
    return (cumulative[:, kernel_bins:] - cumulative[:, :-kernel_bins]) / kernel_bins


def _frame_spectra_db(
    samples: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray]:
    channels = np.atleast_2d(samples)
    window_count = channels.shape[-1] // SPECTRAL_WINDOW_SAMPLES
    trimmed = channels[:, : window_count * SPECTRAL_WINDOW_SAMPLES]
    windows = trimmed.reshape(channels.shape[0], window_count, SPECTRAL_WINDOW_SAMPLES)
    hann = np.hanning(SPECTRAL_WINDOW_SAMPLES).astype(np.float32)
    spectra = np.abs(np.fft.rfft(windows * hann, axis=-1))
    power = np.square(spectra, dtype=np.float64).mean(axis=0)
    frames_db = 10.0 * np.log10(np.maximum(power, 1e-20))
    frequencies = np.fft.rfftfreq(SPECTRAL_WINDOW_SAMPLES, d=1.0 / sample_rate)
    return frames_db, frequencies


def _pyav_decode(
    path: str, start_seconds: float, *, should_cancel: Callable[[], bool] | None = None,
) -> _DecodedWindow:
    """Decode one planar float32 segment without mixing channels or changing rate.

    The segment has to line up with the window the caller asked for, so the
    decoder starts before it and the run-up is dropped here. The FFT uses the
    decoded rate, independently of potentially stale catalog metadata.
    """

    try:
        av = load_project_pyav()
    except RuntimeError as error:
        # One unusable window skips a window; it must not abort the run.
        raise ValueError(f"FFmpeg runtime unavailable: {error}") from error
    deadline = time.monotonic() + DECODE_TIMEOUT_SECONDS
    chunks: list[list[np.ndarray]] = []
    collected = 0
    wanted = 0
    skip: int | None = None
    try:
        with av.open(path, mode="r", metadata_errors="replace") as container:
            streams = container.streams.audio
            if not streams:
                raise ValueError(f"no audio stream: {path}")
            stream = streams[0]
            codec = stream.codec_context.codec
            codec_lossless = (
                bool(codec.lossless) if codec.lossless != codec.lossy else None
            )
            bit_rate = stream.bit_rate if stream.bit_rate and stream.bit_rate > 0 else None
            rate = stream.codec_context.sample_rate
            resampler = av.AudioResampler(format="fltp")
            origin = (
                float(stream.start_time * stream.time_base)
                if stream.start_time is not None
                else 0.0
            )
            # The start keeps the millisecond precision it had as an FFmpeg
            # argument, and it travels in microseconds from here on: seconds in
            # floating point land half a sample off and move the whole window.
            start_microseconds = round((origin + round(start_seconds, 3)) * 1_000_000)
            start = start_microseconds / 1_000_000
            # Even a seek to zero matters: an AAC stream decoded from the seek lands
            # on different samples than one decoded from the first packet.
            container.seek(int(start / stream.time_base), stream=stream, backward=True)
            for frame in container.decode(stream):
                _raise_if_cancelled(should_cancel)
                if time.monotonic() > deadline:
                    raise ValueError(
                        f"decode timed out after {DECODE_TIMEOUT_SECONDS} seconds: {path}"
                    )
                if skip is None:
                    rate = frame.sample_rate
                    # Both points become sample indices before they are subtracted,
                    # each rounded half away from zero the way FFmpeg rescales a
                    # timestamp.
                    target = (start_microseconds * rate + 500_000) // 1_000_000
                    frame_index = (
                        int(frame.pts * frame.time_base * rate) if frame.pts is not None else target
                    )
                    skip = max(0, target - frame_index)
                    wanted = int(SPECTRAL_SEGMENT_SECONDS * rate + 0.5)
                for resampled in resampler.resample(frame):
                    dropped = min(skip or 0, resampled.samples)
                    skip -= dropped
                    take = min(resampled.samples - dropped, wanted - collected)
                    if take:
                        if not chunks:
                            chunks = [[] for _ in resampled.planes]
                        for channel, plane in enumerate(resampled.planes):
                            # The views retain their AV buffers until the final
                            # contiguous array is filled, without per-frame copies.
                            samples = np.frombuffer(
                                plane, dtype=np.float32, count=resampled.samples,
                            )
                            chunks[channel].append(samples[dropped : dropped + take])
                        collected += take
                if collected >= wanted:
                    break
    except av.FFmpegError as error:
        raise ValueError(f"segment decode failed: {path}: {error}") from error
    samples = np.empty((len(chunks) or 1, collected), dtype=np.float32)
    for channel, parts in enumerate(chunks):
        np.concatenate(parts, out=samples[channel])
    return _DecodedWindow(samples, rate, codec_lossless, bit_rate)

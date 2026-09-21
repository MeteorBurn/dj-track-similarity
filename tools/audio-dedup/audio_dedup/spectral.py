from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import numpy as np

from dj_track_similarity.audio.ffmpeg_runtime import load_project_pyav


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
LOSSY_EXTENSIONS = (".mp3", ".aac", ".ogg", ".oga", ".opus", ".wma")
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

# An upsampled file keeps the ceiling of the rate it came from: content stops at
# that rate's Nyquist and the band above is empty rather than rolled off, because
# nothing ever populated it. Measured 2026-09-21 over every hi-res file in the
# library (146 above 48 kHz): genuine masters carry -12 to -58 dB above 22.05 kHz
# relative to the band below it, upsampled ones -63 to -105 dB. The gate sits in
# that gap. 16 of the 146 measured as upsampled, 10 of the 26 declaring 192 kHz.
UPSAMPLE_VOID_DB = 60.0
UPSAMPLE_SOURCE_RATES_HZ = (44_100, 48_000, 88_200, 96_000)
UPSAMPLE_REFERENCE_BAND_BELOW_HZ = (12_000.0, 2_000.0)
UPSAMPLE_VOID_GAP_HZ = 250.0
UPSAMPLE_MIN_VOID_WIDTH_HZ = 1_000.0


@dataclass(frozen=True)
class SpectralResult:
    """Spectral evidence for one duplicate-group file; a heuristic, never a deletion verdict."""

    cutoff_hz: float | None
    sharpness_db: float | None
    sample_rate: int | None
    suspected_transcode: bool
    note: str
    # None when nothing lower was established: either the file fills its own
    # band or the check did not run.
    effective_source_rate_hz: float | None = None


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
    sample_rate: int | None,
    duration_seconds: float | None,
    declared_bitrate_bps: int | None = None,
    decoder: Callable[[str, float], bytes] | None = None,
) -> SpectralResult:
    """Estimate the effective frequency cutoff of one audio file from a mid-track segment."""
    if sample_rate is None or sample_rate <= 0:
        return skipped_result("unknown sample rate")
    selected_decoder = decoder or _pyav_decode
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
        try:
            payload = selected_decoder(path, start_seconds)
        except (OSError, ValueError):
            continue
        samples = np.frombuffer(payload, dtype="<f4")
        if samples.size < SPECTRAL_WINDOW_SAMPLES * 4:
            skip_note = "decoded segment too short"
            continue
        if not np.all(np.isfinite(samples)) or float(np.max(np.abs(samples))) <= 0.0:
            skip_note = "decoded segment is silent or invalid"
            continue
        window_results.append(
            estimate_cutoff(
                samples,
                int(sample_rate),
                container_lossless=not path.casefold().endswith(LOSSY_EXTENSIONS),
                declared_bitrate_bps=declared_bitrate_bps,
            )
        )
    if not window_results:
        return skipped_result(skip_note)
    # The widest window decides: one full-band window proves the file was never
    # band-limited, while a true transcode stays walled in every window.
    return max(window_results, key=lambda result: result.cutoff_hz or 0.0)


def estimate_cutoff(
    samples: np.ndarray,
    sample_rate: int,
    *,
    container_lossless: bool = True,
    declared_bitrate_bps: int | None = None,
) -> SpectralResult:
    """Locate the highest sustained frequency and how brickwalled the drop above it is.

    The segment's loud frames are averaged in linear power, so sparse but real
    highs (hi-hats, crashes) keep a full-band file above the floor while the
    faint transient bleed above an encoder's lowpass stays under it. The floor
    sits SPECTRAL_ENERGY_FLOOR_DB below the 1-8 kHz reference median.
    """
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
    source_rate_hz = _effective_source_rate_hz(smoothed, frequencies, sample_rate)
    full_band_floor = min(FULL_BAND_MIN_CUTOFF_HZ, nyquist - SPECTRAL_SHARPNESS_GAP_HZ)
    if brickwall and cutoff_hz < full_band_floor:
        note = f"brickwall at {cutoff_hz / 1000.0:.1f} kHz ({_bitrate_class(cutoff_hz)})"
    elif cutoff_hz >= full_band_floor:
        note = "full band"
    else:
        note = f"rolls off near {cutoff_hz / 1000.0:.1f} kHz"

    if source_rate_hz is not None:
        source_ceiling_hz = source_rate_hz / 2.0
        if cutoff_hz >= source_ceiling_hz:
            note = f"content stops at {source_ceiling_hz / 1000.0:.1f} kHz"
        note = f"{note}, upsampled from {source_rate_hz / 1000.0:.1f} kHz"

    if container_lossless:
        scaled_nyquist = min(nyquist, TRANSCODE_MAX_SCALED_NYQUIST_HZ)
        max_cutoff_hz = TRANSCODE_MAX_CUTOFF_HZ * (
            scaled_nyquist / TRANSCODE_CALIBRATION_NYQUIST_HZ
        )
        suspected = brickwall and cutoff_hz < max_cutoff_hz
    else:
        expected_cutoff = _declared_min_cutoff(declared_bitrate_bps)
        suspected = (
            brickwall
            and expected_cutoff is not None
            and cutoff_hz < expected_cutoff
        )
        # Below the table nothing was compared, so the note claims no relation.
        if expected_cutoff is not None and brickwall:
            relation = "below" if suspected else "matches"
            note = f"{note}, {relation} declared {declared_bitrate_bps // 1000} kbps"
    return SpectralResult(
        cutoff_hz=round(cutoff_hz, 1),
        sharpness_db=None if sharpness_db is None else round(sharpness_db, 1),
        sample_rate=int(sample_rate),
        effective_source_rate_hz=source_rate_hz,
        suspected_transcode=bool(suspected),
        note=note,
    )


def _effective_source_rate_hz(
    spectrum_db: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
) -> float | None:
    """The lower rate this content actually came from, or None when it fills its own band.

    Upsampling cannot invent content above the source Nyquist, so it leaves a
    void there rather than the gradual roll-off a real recording has. Candidates
    are tried from the lowest rate upwards, so the narrowest genuine ceiling wins
    and a master that merely runs out of energy higher up keeps its own rate.

    This is evidence for ranking copies, never authority to delete one.
    """
    nyquist = sample_rate / 2.0
    below_hz, above_hz = UPSAMPLE_REFERENCE_BAND_BELOW_HZ
    for source_rate_hz in UPSAMPLE_SOURCE_RATES_HZ:
        if source_rate_hz >= sample_rate:
            break
        source_nyquist = source_rate_hz / 2.0
        void_start_hz = source_nyquist + UPSAMPLE_VOID_GAP_HZ
        if nyquist - void_start_hz < UPSAMPLE_MIN_VOID_WIDTH_HZ:
            continue
        reference_mask = (frequencies >= source_nyquist - below_hz) & (
            frequencies <= source_nyquist - above_hz
        )
        void_mask = frequencies >= void_start_hz
        if not np.any(reference_mask) or not np.any(void_mask):
            continue
        drop_db = float(
            np.mean(spectrum_db[void_mask]) - np.mean(spectrum_db[reference_mask])
        )
        if drop_db < -UPSAMPLE_VOID_DB:
            return float(source_rate_hz)
    return None


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
    window_count = samples.size // SPECTRAL_WINDOW_SAMPLES
    trimmed = samples[: window_count * SPECTRAL_WINDOW_SAMPLES]
    windows = trimmed.reshape(window_count, SPECTRAL_WINDOW_SAMPLES)
    hann = np.hanning(SPECTRAL_WINDOW_SAMPLES).astype(np.float32)
    spectra = np.abs(np.fft.rfft(windows * hann, axis=1))
    power = np.square(spectra, dtype=np.float64)
    frames_db = 10.0 * np.log10(np.maximum(power, 1e-20))
    frequencies = np.fft.rfftfreq(SPECTRAL_WINDOW_SAMPLES, d=1.0 / sample_rate)
    return frames_db, frequencies


def _pyav_decode(path: str, start_seconds: float) -> bytes:
    """Decode one mono float32 segment at the file's own sample rate, in process.

    The segment has to line up with the window the caller asked for, so the
    decoder starts before it and the run-up is dropped here. The mix down to mono
    stays FFmpeg's own rematrix, and nothing is resampled: the frequency axis of
    the caller's FFT is the source rate.
    """

    try:
        av = load_project_pyav()
    except RuntimeError as error:
        # One unusable window skips a window; it must not abort the run.
        raise ValueError(f"FFmpeg runtime unavailable: {error}") from error
    deadline = time.monotonic() + DECODE_TIMEOUT_SECONDS
    chunks: list[np.ndarray] = []
    collected = 0
    wanted = 0
    skip: int | None = None
    try:
        with av.open(path, mode="r", metadata_errors="replace") as container:
            streams = container.streams.audio
            if not streams:
                raise ValueError(f"no audio stream: {path}")
            stream = streams[0]
            resampler = av.AudioResampler(format="flt", layout="mono", rate=None)
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
                    samples = np.asarray(resampled.to_ndarray(), dtype=np.float32).reshape(-1)
                    if skip:
                        dropped = min(skip, samples.size)
                        samples = samples[dropped:]
                        skip -= dropped
                    if samples.size:
                        chunks.append(samples.copy())
                        collected += samples.size
                if collected >= wanted:
                    break
    except av.FFmpegError as error:
        raise ValueError(f"segment decode failed: {path}: {error}") from error
    if not chunks:
        return b""
    return np.concatenate(chunks)[:wanted].tobytes()

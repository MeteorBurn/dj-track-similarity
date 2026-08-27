from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import Callable

import numpy as np


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
TRANSCODE_MIN_SHARPNESS_DB = 14.0
FULL_BAND_MIN_CUTOFF_HZ = 21_000.0
DECODE_TIMEOUT_SECONDS = 120
LOSSY_EXTENSIONS = (".mp3", ".aac", ".ogg", ".oga", ".opus", ".wma")
CUTOFF_BITRATE_CLASSES = (
    (19_800.0, "~320 kbps class"),
    (18_300.0, "~192-256 kbps class"),
    (16_800.0, "~160-192 kbps class"),
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
    suspected_transcode: bool
    note: str


def skipped_result(note: str) -> SpectralResult:
    return SpectralResult(
        cutoff_hz=None,
        sharpness_db=None,
        sample_rate=None,
        suspected_transcode=False,
        note=note,
    )


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


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
    selected_decoder = decoder or _ffmpeg_decode
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
        except (OSError, subprocess.SubprocessError, ValueError):
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
    full_band_floor = min(FULL_BAND_MIN_CUTOFF_HZ, nyquist - SPECTRAL_SHARPNESS_GAP_HZ)
    if brickwall and cutoff_hz < full_band_floor:
        note = f"brickwall at {cutoff_hz / 1000.0:.1f} kHz ({_bitrate_class(cutoff_hz)})"
    elif cutoff_hz >= full_band_floor:
        note = "full band"
    else:
        note = f"rolls off near {cutoff_hz / 1000.0:.1f} kHz"

    if container_lossless:
        suspected = brickwall and cutoff_hz < TRANSCODE_MAX_CUTOFF_HZ
    else:
        expected_cutoff = _declared_min_cutoff(declared_bitrate_bps)
        suspected = (
            brickwall
            and expected_cutoff is not None
            and cutoff_hz < expected_cutoff
        )
        if declared_bitrate_bps and brickwall:
            relation = "below" if suspected else "matches"
            note = f"{note}, {relation} declared {declared_bitrate_bps // 1000} kbps"
    return SpectralResult(
        cutoff_hz=round(cutoff_hz, 1),
        sharpness_db=None if sharpness_db is None else round(sharpness_db, 1),
        sample_rate=int(sample_rate),
        suspected_transcode=bool(suspected),
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
    window_count = samples.size // SPECTRAL_WINDOW_SAMPLES
    trimmed = samples[: window_count * SPECTRAL_WINDOW_SAMPLES]
    windows = trimmed.reshape(window_count, SPECTRAL_WINDOW_SAMPLES)
    hann = np.hanning(SPECTRAL_WINDOW_SAMPLES).astype(np.float32)
    spectra = np.abs(np.fft.rfft(windows * hann, axis=1))
    power = np.square(spectra, dtype=np.float64)
    frames_db = 10.0 * np.log10(np.maximum(power, 1e-20))
    frequencies = np.fft.rfftfreq(SPECTRAL_WINDOW_SAMPLES, d=1.0 / sample_rate)
    return frames_db, frequencies


def _ffmpeg_decode(path: str, start_seconds: float) -> bytes:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{SPECTRAL_SEGMENT_SECONDS:.3f}",
        "-i",
        path,
        "-map",
        "a:0",
        "-ac",
        "1",
        "-f",
        "f32le",
        "-",
    ]
    completed = subprocess.run(
        command,
        shell=False,
        capture_output=True,
        timeout=DECODE_TIMEOUT_SECONDS,
        check=True,
    )
    return completed.stdout

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Callable, Mapping

from .spectral import (
    SpectralResult,
)

from . import models as models_module
from . import scoring as scoring_module
from . import values as values_module

# Deterministic library-format preference, not an audio-quality rank.
# Equal lossless PCM samples are equal audio; this key runs only after stronger
# signal/resolution evidence has tied. FLAC leads because it is compact, tagged
# well, and broadly supported; AIFF then WAV are kept as uncompressed fallbacks.
FORMAT_RANKS = {
    ".flac": 60,
    ".aif": 59,
    ".aiff": 59,
    ".wav": 58,
    ".wave": 58,
    ".alac": 57,
    ".wv": 56,
    ".ape": 55,
    ".tak": 55,
    ".tta": 55,
    # DSD is not ranked against PCM by resolution; mixed DSD/non-DSD groups
    # are forced to review below. These values only settle ties within DSD.
    ".dsf": 54,
    ".dff": 53,
    ".dsd": 53,
    # AIFF-C may contain different codec types, so it is treated as ambiguous
    # for automatic keeper quality decisions below.
    ".aifc": 50,
    # Lossy, where the declared bitrate has already ranked the pair and this
    # only breaks a tie between two copies at the same rate.
    ".m4a": 42,
    ".mp4": 40,
    ".mp3": 25,
    ".aac": 24,
    ".ogg": 23,
    ".oga": 23,
    ".opus": 23,
    ".wma": 20,
}
MEASURED_BANDWIDTH_STEP_HZ = 250
# Two copies of one master measure a few tenths of a decibel apart, and that
# noise must never decide a keeper. A loudness-war remaster differs by whole
# decibels, which is the only difference these keys are meant to see.
DYNAMIC_RANGE_STEP_DB = 1.0
LOUDNESS_RANGE_STEP_LU = 1.0
# Beyond these the copies are no longer two encodes of one master but two
# masters, and which master is better is a taste call, not a measurement.
MASTER_LOUDNESS_TOLERANCE_LU = 2.0
MASTER_DYNAMIC_RANGE_TOLERANCE_DB = 3.0
MASTER_LOUDNESS_RANGE_TOLERANCE_LU = 3.0
LOSSLESS_SUFFIXES = {
    ".flac",
    ".wav",
    ".wave",
    ".aif",
    ".aiff",
    ".aifc",
    ".alac",
    ".ape",
    ".wv",
    ".tak",
    ".tta",
    ".dff",
    ".dsd",
    ".dsf",
}

DSD_SUFFIXES = {".dff", ".dsd", ".dsf"}
AMBIGUOUS_CODEC_SUFFIXES = {".m4a", ".mp4", ".aifc"}
# Keys that decide nothing about the audio: they only make a complete tie
# resolve to one copy, so they are stated only when nothing else can be.
TIE_BREAK_KEEPER_KEYS = frozenset({"file date", "scan order"})
# The card answers "why this copy" at a glance. The keys come in strength order,
# so the first few carry the answer and the rest are detail nobody reads.
MAX_KEEPER_REASON_LINES = 3


@dataclass(frozen=True)
class KeeperKey:
    """One key of the keeper comparator, with the line that states it."""

    label: str
    value: Callable[[models_module.TrackRecord], float]
    describe: Callable[[models_module.TrackRecord], str]


def _statement(label: str, show: Callable[[models_module.TrackRecord], str]):
    def render(keeper: models_module.TrackRecord) -> str:
        return f"Best {label} in group: {show(keeper)}."

    return render


def keeper_keys(
    tracks: list[models_module.TrackRecord],
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> list[KeeperKey]:
    """The comparator as data, so the ranking and its explanation cannot drift.

    Measured evidence outranks everything a file says about itself: a copy the
    spectrum caught as a transcode loses first, then the wider measured band
    wins. Only where nothing contradicts the files do their own facts decide, in
    the owner order: lossless before lossy, lossy bitrate, bit depth, sample
    rate, true peak, dynamic range, loudness range, format, file size, tags, DJ
    tags. Modification time and id follow to make a complete tie deterministic.

    A key sits out where its meaning does not hold for this group: the two range
    keys across two masters, resolution across a mixed DSD group, and everything
    a container cannot prove where the codec is ambiguous. A key that sits out
    returns one constant for every copy, so it can neither rank nor explain.
    """
    verdicts = dict(spectral_results or {})
    same_master = is_same_master(tracks)
    mixed_dsd_family = _has_mixed_dsd_family(tracks)
    ambiguous_codec = any(has_ambiguous_codec_container(track) for track in tracks)
    same_container = len({Path(track.path).suffix.casefold() for track in tracks}) == 1

    def full_band(track: models_module.TrackRecord) -> int:
        result = verdicts.get(track.track_id)
        return 0 if result is not None and result.suspected_transcode else 1

    def measured_bandwidth(track: models_module.TrackRecord) -> int:
        """Measured spectral cutoff in whole steps — the one figure tags cannot fake.

        A file can declare 48 kHz and 2048 kbps while carrying 128 kbps of audio;
        every declared number in that file is a lie, and only the spectrum tells
        the truth. Within a duplicate group the copies are the same recording, so
        a lower cutoff means bandwidth lost in that copy's encoding chain rather
        than a dark master, which is what makes this comparable here and not
        across the library.

        Quantised because two copies of one recording at different sample rates
        land on different FFT bins and measure a little apart; that noise must
        not decide a keeper. The step stays small enough to separate a wall left
        by a 320 kbps source from a genuine roll-off just under 44.1 kHz Nyquist,
        which is only a few hundred hertz apart and is precisely the gap the
        calibrated transcode flag is not allowed to judge.
        """
        result = verdicts.get(track.track_id)
        if result is None or result.suspected_transcode or result.cutoff_hz is None:
            return 0
        return int(result.cutoff_hz // MEASURED_BANDWIDTH_STEP_HZ)

    def lossless(track: models_module.TrackRecord) -> int:
        return 0 if ambiguous_codec else int(is_lossless(track))

    def bitrate(track: models_module.TrackRecord) -> int:
        """The stated bitrate, wherever it compares like with like.

        One container across the group is what makes the rate a fact about the
        audio: every copy states it the same way, so the higher one carries more
        of the recording. Across containers it measures packing instead — a FLAC
        and the WAV of one master state very different rates while holding
        identical samples — so only lossy copies compare there.
        """
        if ambiguous_codec:
            return 0
        if same_container:
            return declared_bit_rate_bps(track)
        return lossy_bit_rate_bps(track)

    def bit_depth(track: models_module.TrackRecord) -> int:
        return 0 if mixed_dsd_family else declared_bit_depth(track)

    def sample_rate(track: models_module.TrackRecord) -> int:
        return 0 if mixed_dsd_family else declared_sample_rate_hz(track)

    def dynamic_range(track: models_module.TrackRecord) -> int:
        return dynamic_range_rank(track) if same_master else 0

    def loudness_range(track: models_module.TrackRecord) -> int:
        return loudness_range_rank(track) if same_master else 0

    def format_preference(track: models_module.TrackRecord) -> int:
        return 0 if ambiguous_codec else format_rank(track.path)


    def show_bandwidth(track: models_module.TrackRecord) -> str:
        result = verdicts.get(track.track_id)
        if result is None or result.cutoff_hz is None:
            return "not measured"
        return f"{result.cutoff_hz / 1000:.1f} kHz"

    def show_true_peak(track: models_module.TrackRecord) -> str:
        peak = _sonara_float(track, "true_peak_dbtp")
        return "unmeasured" if peak is None else f"{peak:.1f} dBTP"

    def show_dj_tags(track: models_module.TrackRecord) -> str:
        tags = [
            name
            for name, present in (
                ("BPM", track.bpm is not None and float(track.bpm) > 0.0),
                ("Key", bool(track.musical_key and track.musical_key.strip())),
            )
            if present
        ]
        return " + ".join(tags) if tags else "none"

    return [
        KeeperKey(
            "spectrum",
            full_band,
            lambda keeper: "Full-band spectrum in group.",
        ),
        KeeperKey(
            "measured bandwidth",
            measured_bandwidth,
            _statement("measured bandwidth", show_bandwidth),
        ),
        KeeperKey("compression", lossless, lambda keeper: "Lossless in group."),
        KeeperKey(
            "bitrate",
            bitrate,
            _statement("bitrate", lambda track: f"{round(bitrate(track) / 1000)} kbps"),
        ),
        KeeperKey(
            "bit depth",
            bit_depth,
            _statement("bit depth", lambda track: f"{bit_depth(track)}-bit"),
        ),
        KeeperKey(
            "sample rate",
            sample_rate,
            _statement("sample rate", lambda track: f"{sample_rate(track):,} Hz"),
        ),
        KeeperKey("true peak", true_peak_rank, _statement("true peak", show_true_peak)),
        KeeperKey(
            "dynamic range",
            dynamic_range,
            _statement("dynamic range", lambda track: f"{dynamic_range(track)} dB"),
        ),
        KeeperKey(
            "loudness range",
            loudness_range,
            _statement("loudness range", lambda track: f"{loudness_range(track)} LU"),
        ),
        KeeperKey(
            "format rank",
            format_preference,
            _statement("format rank", lambda track: f"{format_preference(track)}"),
        ),
        KeeperKey(
            "file size",
            lambda track: float(track.size),
            _statement("file size", lambda track: f"{track.size / 1024 / 1024:.1f} MB"),
        ),
        KeeperKey(
            "tag completeness",
            metadata_completeness,
            _statement("tag completeness", lambda track: f"{metadata_completeness(track)} fields"),
        ),
        KeeperKey("DJ tags", dj_metadata_completeness, _statement("DJ tags", show_dj_tags)),
        KeeperKey(
            "file date",
            lambda track: float(track.mtime),
            lambda keeper: "Every compared fact ties; newest file in group.",
        ),
        KeeperKey(
            "scan order",
            lambda track: -float(track.track_id),
            lambda keeper: "Every compared fact ties; scanned first in group.",
        ),
    ]


def choose_keeper(
    tracks: list[models_module.TrackRecord],
    *,
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> models_module.TrackRecord:
    if not tracks:
        raise ValueError("Cannot choose a keeper from an empty group")
    keys = keeper_keys(tracks, spectral_results)
    return max(tracks, key=lambda track: tuple(key.value(track) for key in keys))


def format_rank(path: str) -> int:
    return FORMAT_RANKS.get(Path(path).suffix.casefold(), 0)


def is_lossless(track: models_module.TrackRecord) -> bool:
    """Project-level lossless classification available from the stored suffix.

    TrackRecord does not currently expose the decoded codec name, so ambiguous
    containers are handled by a separate review gate and never trusted for
    automatic deletion quality decisions.
    """
    return Path(track.path).suffix.casefold() in LOSSLESS_SUFFIXES


def is_dsd(track: models_module.TrackRecord) -> bool:
    return Path(track.path).suffix.casefold() in DSD_SUFFIXES


def has_ambiguous_codec_container(track: models_module.TrackRecord) -> bool:
    return Path(track.path).suffix.casefold() in AMBIGUOUS_CODEC_SUFFIXES


def _has_mixed_dsd_family(tracks: list[models_module.TrackRecord]) -> bool:
    if not tracks:
        return False
    has_dsd = any(is_dsd(track) for track in tracks)
    has_non_dsd = any(not is_dsd(track) for track in tracks)
    return has_dsd and has_non_dsd


def declared_bit_rate_bps(track: models_module.TrackRecord) -> int:
    """The bitrate the file states, exactly as the copy line shows it."""
    return max(0, _optional_metadata_int(track, "bit_rate_bps") or 0)


def declared_bit_depth(track: models_module.TrackRecord) -> int:
    return max(0, _optional_metadata_int(track, "bit_depth") or 0)


def declared_sample_rate_hz(track: models_module.TrackRecord) -> int:
    return max(0, _optional_metadata_int(track, "sample_rate_hz") or 0)


def lossy_bit_rate_bps(track: models_module.TrackRecord) -> int:
    """Declared bitrate, compared only between lossy copies.

    Between two lossless copies the bitrate measures packing rather than audio:
    a FLAC and the WAV of one master state very different rates while carrying
    identical samples, so lossless copies stay out of this key entirely and the
    resolution keys below decide them.
    """
    if is_lossless(track):
        return 0
    return declared_bit_rate_bps(track)


def _sonara_float(track: models_module.TrackRecord, field_name: str) -> float | None:
    features = track.metadata.get("sonara_features")
    if not isinstance(features, Mapping):
        return None
    try:
        value = float(features[field_name])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def true_peak_rank(track: models_module.TrackRecord) -> int:
    """Peak integrity: clean beats unknown beats measured over 0 dBTP.

    A value at or below 0 dBTP has measured true-peak headroom. A value above
    0 dBTP indicates intersample overs and higher clipping risk during playback,
    conversion, or later processing; it does not by itself prove stored sample
    clipping. Missing analysis stays between those two known states.
    """
    value = _sonara_float(track, "true_peak_dbtp")
    if value is None:
        return 1
    return 2 if value <= 0.0 else 0


def master_difference_reasons(tracks: list[models_module.TrackRecord]) -> list[str]:
    """Signs that the copies are different masters, not different encodes.

    Loudness survives repacking: two encodes of one master measure within a
    fraction of a unit of each other, while a remaster is louder, flatter, or
    both. Where the group disagrees this much it is still the same recording,
    but choosing between its masters is the reviewer's taste and not a
    measurement, so the tool stops ranking on those two keys and refuses to
    delete anything inside the group.
    """
    checks = (
        ("integrated loudness", "loudness_lufs", MASTER_LOUDNESS_TOLERANCE_LU, "LU"),
        ("dynamic range", "dynamic_range_db", MASTER_DYNAMIC_RANGE_TOLERANCE_DB, "dB"),
        ("loudness range", "loudness_range_lu", MASTER_LOUDNESS_RANGE_TOLERANCE_LU, "LU"),
    )
    reasons: list[str] = []
    for label, field_name, tolerance, unit in checks:
        values = [
            value
            for value in (_sonara_float(track, field_name) for track in tracks)
            if value is not None
        ]
        if len(values) < 2:
            continue
        spread = max(values) - min(values)
        if spread > tolerance:
            reasons.append(f"possible different master: {label} differs by {spread:.1f} {unit}")
    return reasons


def is_same_master(tracks: list[models_module.TrackRecord]) -> bool:
    return not master_difference_reasons(tracks)


def format_comparison_review_reasons(tracks: list[models_module.TrackRecord]) -> list[str]:
    """Return cases where stored container facts cannot safely rank audio quality."""
    reasons: list[str] = []
    ambiguous = sorted(
        {
            Path(track.path).suffix.casefold()
            for track in tracks
            if has_ambiguous_codec_container(track)
        }
    )
    if ambiguous:
        reasons.append(
            "codec is not stored for ambiguous container(s): "
            + ", ".join(ambiguous)
            + "; lossless/lossy quality class cannot be proven from extension"
        )
    if _has_mixed_dsd_family(tracks):
        reasons.append(
            "mixed DSD/non-DSD duplicate group: bit depth and sample rate are not "
            "directly comparable across encoding families"
        )
    return reasons


def keeper_review_reasons(tracks: list[models_module.TrackRecord]) -> list[str]:
    return master_difference_reasons(tracks) + format_comparison_review_reasons(tracks)


def dynamic_range_rank(track: models_module.TrackRecord) -> int:
    """Dynamic range in whole decibels, quantised against measurement noise."""
    value = _sonara_float(track, "dynamic_range_db")
    if value is None:
        return 0
    return int(value // DYNAMIC_RANGE_STEP_DB)


def loudness_range_rank(track: models_module.TrackRecord) -> int:
    """Loudness range in whole units, quantised against measurement noise."""
    value = _sonara_float(track, "loudness_range_lu")
    if value is None:
        return 0
    return int(value // LOUDNESS_RANGE_STEP_LU)


def dj_metadata_completeness(track: models_module.TrackRecord) -> int:
    """Count useful DJ tags without ranking their musical values."""
    count = 0
    if track.bpm is not None and math.isfinite(float(track.bpm)) and float(track.bpm) > 0.0:
        count += 1
    if track.musical_key is not None and track.musical_key.strip():
        count += 1
    return count


def size_per_second(track: models_module.TrackRecord) -> float:
    if not track.duration or track.duration <= 0:
        return 0.0
    return float(track.size) / float(track.duration)


def metadata_completeness(track: models_module.TrackRecord) -> int:
    count = 0
    for value in (track.artist, track.title, track.album, track.duration):
        if value not in (None, ""):
            count += 1
    if track.metadata.get("genre") or track.metadata.get("genres"):
        count += 1
    return count


def confidence_category(score: float, config: models_module.PresetConfig) -> str:
    if score >= max(0.98, config.min_score):
        return "high"
    if score >= max(0.94, config.min_score):
        return "medium"
    return "review"


def _optional_metadata_int(track: models_module.TrackRecord, field_name: str) -> int | None:
    try:
        return int(track.metadata[field_name])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError):
        return None


def _keeper_reason_lines(
    keeper: models_module.TrackRecord,
    tracks: list[models_module.TrackRecord],
    spectral_results: Mapping[int, SpectralResult] | None = None,
) -> list[str]:
    """Everything this copy has over the closest other one, in comparator order.

    The comparison is against the runner-up, so each line is a fact the reviewer
    can check between the two cards in front of them. Keys the copies tie on say
    nothing and are left out; date and id say nothing about the audio at all, so
    they appear only where no real key separates the copies. The strongest few
    are enough to answer the question, so the list stops at three.
    """
    others = [track for track in tracks if track.track_id != keeper.track_id]
    if not others:
        return []
    keys = keeper_keys(tracks, spectral_results)
    runner_up = max(others, key=lambda track: tuple(key.value(track) for key in keys))
    lines = [
        key.describe(keeper)
        for key in keys
        if key.label not in TIE_BREAK_KEEPER_KEYS
        and key.value(keeper) > key.value(runner_up)
    ]
    if lines:
        return lines[:MAX_KEEPER_REASON_LINES]
    deciding = _deciding_key(keys, keeper, runner_up)
    return [deciding.describe(keeper)] if deciding is not None else []


def _deciding_key(
    keys: list[KeeperKey],
    keeper: models_module.TrackRecord,
    rival: models_module.TrackRecord,
) -> KeeperKey | None:
    """The first key where the two copies differ, which is the one that decided."""
    for key in keys:
        if key.value(keeper) != key.value(rival):
            return key
    return None


def _candidate_reason_lines(
    candidate: models_module.TrackRecord,
    keeper: models_module.TrackRecord,
    pair: models_module.PairEvidence | None,
    config: models_module.PresetConfig,
    *,
    safe: bool,
    reasons: list[str],
) -> list[str]:
    if not safe:
        return [f"Manual review required: {reason}." for reason in reasons] or [
            "Manual review required before deleting this file."
        ]
    lines = [
        f"Direct score vs keeper meets threshold: {values_module._format_float(pair.score if pair else None)} >= {values_module._format_float(config.direct_keeper_score)}.",
        f"Content similarity meets threshold: {values_module._format_float(pair.content_similarity if pair else None)} >= {values_module._format_float(config.min_similarity)}.",
    ]
    if pair and pair.duration_diff_seconds is not None:
        lines.append(f"Duration difference is {values_module._format_float(pair.duration_diff_seconds)} seconds.")
    return lines


def _candidate_safety(pair: models_module.PairEvidence | None, config: models_module.PresetConfig, *, ambiguous: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if ambiguous:
        reasons.append("ambiguous chain")
    if pair is None:
        reasons.append("weak direct keeper match")
    else:
        if pair.candidate_sources == ("fingerprint_lsh",):
            if pair.fingerprint_similarity is not None:
                reasons.append(
                    f"SONARA fingerprint-only candidate: exact fingerprint match "
                    f"{values_module._format_float(pair.fingerprint_similarity)} is strong duplicate evidence, but "
                    "fingerprint evidence alone never authorizes automatic deletion"
                )
            else:
                reasons.append("SONARA fingerprint-only candidate requires manual review")
        if pair.score < config.direct_keeper_score:
            reasons.append("weak direct keeper match")
        if not scoring_module._passes_content_similarity(pair, config):
            reasons.append("content similarity below threshold")
        if pair.duration_diff_ratio is not None and pair.duration_diff_ratio > config.strict_duration_ratio:
            reasons.append("duration mismatch")
        reasons.extend(pair.blocked_reasons)
    return not reasons, sorted(set(reasons))

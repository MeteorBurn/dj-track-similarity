"""Current unversioned SONARA analysis selection and value constants."""

from __future__ import annotations

SONARA_ANALYSIS_MODE = "playlist"
SONARA_SAMPLE_RATE = 22_050
# Default analysis range only. SONARA accepts any bounds, and each run passes
# its own pair, so these are a starting point rather than a fixed project value.
# 70-180 matches the Rekordbox range.
DEFAULT_SONARA_BPM_MIN = 70.0
DEFAULT_SONARA_BPM_MAX = 180.0
SONARA_VOCALNESS_MODEL_SELECTOR = "bundled"
SONARA_UNIT_INTERVAL_EPSILON = 0.001
SONARA_UNIT_INTERVAL_FIELDS = (
    "acousticness",
    "aggression_confidence",
    "aggression_forcefulness",
    "aggression_harshness",
    "aggression_rhythm",
    "aggression_score",
    "aggression_tension",
    "bpm_confidence",
    "danceability",
    "dissonance",
    "energy",
    "energy_curve[]",
    "grid_stability",
    "key_candidates[].score",
    "key_confidence",
    "mood_aggressive",
    "mood_happy",
    "mood_relaxed",
    "mood_sad",
    "spectral_flatness_mean",
    "valence",
    "vocalness",
    "zero_crossing_rate",
)

SONARA_CORE_REQUESTED_FEATURES = (
    "bpm",
    "beats",
    "rms",
    "dynamic_range",
    "centroid",
    "zcr",
    "onset_density",
    "bandwidth",
    "rolloff",
    "flatness",
    "contrast",
    "mfcc",
    "chroma",
    "chords",
    "dissonance",
    "energy",
    "danceability",
    "key",
    "valence",
    "acousticness",
    "tempo_curve",
    "beatgrid",
    "structure",
    "loudness",
    "silence",
    "key_candidates",
    "vocalness",
    "aggression",
    "mood",
)


def sonara_requested_features() -> tuple[str, ...]:
    return (*SONARA_CORE_REQUESTED_FEATURES, "embedding", "fingerprint")

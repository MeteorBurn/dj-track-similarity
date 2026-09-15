"""Current unversioned SONARA analysis selection and value constants."""

from __future__ import annotations

from types import MappingProxyType

SONARA_ANALYSIS_MODE = "playlist"
SONARA_SAMPLE_RATE = 22_050
# BPM analysis ranges of common DJ tools, selectable by name on the CLI and API.
# Each spans at least an octave, which tempo folding needs.
SONARA_BPM_PRESETS = MappingProxyType(
    {
        "rekordbox": (70.0, 180.0),
        "virtual-dj": (80.0, 240.0),
        "mixed-in-key": (79.0, 192.0),
    }
)
# Default analysis range only. SONARA accepts any bounds, and each run passes
# its own pair, so this is a starting point rather than a fixed project value.
DEFAULT_SONARA_BPM_PRESET = "mixed-in-key"
DEFAULT_SONARA_BPM_MIN, DEFAULT_SONARA_BPM_MAX = SONARA_BPM_PRESETS[DEFAULT_SONARA_BPM_PRESET]
SONARA_VOCALNESS_MODEL_SELECTOR = "bundled"
SONARA_UNIT_INTERVAL_EPSILON = 0.001

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

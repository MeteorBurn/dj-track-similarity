"""Current unversioned SONARA analysis selection and value constants."""

from __future__ import annotations

from collections.abc import Sequence


SONARA_ANALYSIS_MODE = "playlist"
SONARA_SAMPLE_RATE = 22_050
SONARA_BPM_MIN = 70
SONARA_BPM_MAX = 180
SONARA_VOCALNESS_MODEL_SELECTOR = "bundled"
SONARA_EMBEDDING_DIM = 48
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
    "segments[].energy",
    "spectral_flatness_mean",
    "valence",
    "vocalness",
    "zero_crossing_rate",
)

SONARA_OUTPUT_KINDS = ("core", "timeline", "embedding", "fingerprint")
DEFAULT_SONARA_OUTPUTS = ("core",)

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
SONARA_TIMELINE_REQUESTED_FEATURES = (
    "beats",
    "onsets",
    "chords",
    "tempo_curve",
    "beatgrid",
    "structure",
    "loudness",
)
SONARA_EMBEDDING_REQUESTED_FEATURES = ("embedding",)
SONARA_FINGERPRINT_REQUESTED_FEATURES = ("fingerprint",)

_REQUESTED_FEATURES_BY_OUTPUT = {
    "core": SONARA_CORE_REQUESTED_FEATURES,
    "timeline": SONARA_TIMELINE_REQUESTED_FEATURES,
    "embedding": SONARA_EMBEDDING_REQUESTED_FEATURES,
    "fingerprint": SONARA_FINGERPRINT_REQUESTED_FEATURES,
}


def normalize_sonara_outputs(
    outputs: Sequence[str] | None,
) -> tuple[str, ...]:
    if outputs is None:
        return DEFAULT_SONARA_OUTPUTS
    selected: set[str] = {"core"}
    saw_value = False
    for output in outputs:
        if not isinstance(output, str) or not output.strip():
            raise ValueError("SONARA output must be a non-empty string")
        clean = output.strip().lower()
        saw_value = True
        if clean not in SONARA_OUTPUT_KINDS:
            raise ValueError(
                f"unsupported SONARA output {output!r}; "
                f"expected one of {SONARA_OUTPUT_KINDS}"
            )
        selected.add(clean)
    if not saw_value:
        raise ValueError("SONARA outputs must not be empty")
    return tuple(kind for kind in SONARA_OUTPUT_KINDS if kind in selected)


def sonara_requested_features() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                feature
                for output_kind in SONARA_OUTPUT_KINDS
                for feature in _REQUESTED_FEATURES_BY_OUTPUT[output_kind]
            }
        )
    )

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.classifier.sonara_features import (
    SONARA_CLASSIFIER_SCALAR_ALIASES,
    SONARA_CLASSIFIER_VECTOR_ALIASES,
    SONARA_CLASSIFIER_VECTOR_DIMS,
)

from .lab_db import RhythmLabDatabase
from .source_db import MERT_V2_DEFAULT_LAYER, SourceDatabase, SourceTrack


# The only recipe universe: any duplicate-free subset is a valid feature set,
# and its canonical string lists the sources in this owner-mandated order
# (the UI mirrors it). MERT-v2 stores 24 layers; a source token may select one
# as "mert_v2@<layer>". The bare token is the layer Rhythm Lab has always read,
# so existing artifacts keep matching.
SUPPORTED_FEATURE_SOURCES = ("sonara", "maest", "mert", "mert_v2", "muq", "mulan", "clap")
_LAYERED_FAMILIES = ("mert_v2",)
_SONARA_CORE_SCALAR_FIELDS = (
    "bpm",
    "onset_density",
    "n_beats",
    "rms_mean",
    "rms_max",
    "loudness_lufs",
    "dynamic_range_db",
    "spectral_centroid_mean",
    "zero_crossing_rate",
    "duration_sec",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "chord_change_rate",
    "dissonance",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
)
_SONARA_CURRENT_EXTRA_SCALAR_FIELDS = (
    "bpm_raw",
    "bpm_confidence",
    "tempo_variability",
    "key_confidence",
    "energy_level",
    "intro_end_sec",
    "outro_start_sec",
    "energy_curve_min",
    "energy_curve_max",
    "energy_curve_mean",
    "energy_curve_stddev",
    "true_peak_db",
    "replaygain_db",
    "loudness_momentary_max_db",
    "loudness_range_lu",
    "grid_offset_sec",
    "grid_stability",
    "leading_silence_sec",
    "trailing_silence_sec",
)
# These are SONARA's deterministic mood summaries, not bundled model outputs.
_SONARA_MOOD_SCALAR_FIELDS = (
    "mood_happy",
    "mood_aggressive",
    "mood_relaxed",
    "mood_sad",
)
# Keep the baseline independent of SONARA's bundled learned outputs:
# vocal_probability and the aggression score family are intentionally excluded.
SONARA_SCALAR_FIELDS = (
    *_SONARA_CORE_SCALAR_FIELDS,
    *_SONARA_CURRENT_EXTRA_SCALAR_FIELDS,
    *_SONARA_MOOD_SCALAR_FIELDS,
)
SONARA_VECTOR_FIELDS = {
    name: SONARA_CLASSIFIER_VECTOR_DIMS[stored_name]
    for name, stored_name in SONARA_CLASSIFIER_VECTOR_ALIASES.items()
}
SONARA_FEATURE_NAMES = (
    *(f"sonara:{field}" for field in SONARA_SCALAR_FIELDS),
    *(
        f"sonara:{field}:{index}"
        for field, length in SONARA_VECTOR_FIELDS.items()
        for index in range(length)
    ),
)
_SONARA_ATTRIBUTES = {
    field: SONARA_CLASSIFIER_SCALAR_ALIASES.get(field, field)
    for field in SONARA_SCALAR_FIELDS
}


@dataclass(frozen=True)
class FeatureMatrix:
    tracks: tuple[SourceTrack, ...]
    labels: list[str]
    matrix: np.ndarray
    feature_names: list[str]
    skipped_identities: tuple[str, ...]
    source_dimensions: Mapping[str, int]


def build_labeled_feature_matrix(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    feature_set: str,
    *,
    classifier_key: str,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
    return build_labeled_feature_matrix_from_sources(
        source,
        labels,
        feature_set,
    )


def build_labeled_feature_matrix_from_sources(
    source: SourceDatabase,
    labels: RhythmLabDatabase,
    feature_set: str,
) -> FeatureMatrix:
    """Training rows for the labels whose content is sighted in ``source``.

    Each labelled content trains from one representative track (the lowest
    sighted ``track_id``) that stores every source of the recipe; a label whose
    representative lacks a source, or whose fingerprint no longer hashes to the
    label's key, is skipped.
    """

    labels.sync_track_sightings(source)
    labels_by_identity = labels.training_labels(catalog_uuid=str(source.catalog_uuid))
    representatives = labels.representative_sightings(
        source.catalog_uuid,
        labels_by_identity,
    )
    tracks = source.tracks_by_ids(
        representatives.values(),
        required_sources=feature_sources(feature_set),
    )
    return build_feature_matrix(
        source,
        feature_set,
        labels_by_identity=labels_by_identity,
        tracks=tuple(tracks.values()),
    )


def build_feature_matrix(
    source: SourceDatabase,
    feature_set: str,
    *,
    labels_by_identity: Mapping[str, str],
    tracks: Sequence[SourceTrack] | None = None,
    embedding_cache: dict[str, tuple[int, dict[int, np.ndarray]]] | None = None,
    expected_feature_names: object | None = None,
) -> FeatureMatrix:
    """Feature rows for ``labels_by_identity`` (``content_key -> label``) from ``tracks``."""

    sources = feature_sources(feature_set)
    scalar_fields = _sonara_scalar_fields()
    current_tracks = tuple(tracks if tracks is not None else source.list_tracks())
    by_identity = {
        track.content_key: track for track in current_tracks if track.content_key
    }
    cache = embedding_cache if embedding_cache is not None else {}
    selected_track_ids = tuple(track.track_id for track in current_tracks)
    embeddings = {
        family: _cached_embedding_vectors(
            source,
            family,
            cache,
            track_ids=selected_track_ids,
        )
        for family in sources
        if family != "sonara"
    }
    feature_names = _feature_names(
        sources,
        scalar_fields=scalar_fields,
        embeddings=embeddings,
    )
    expected = _parse_feature_names(expected_feature_names)
    if expected is not None and set(expected) != set(feature_names):
        raise ValueError(
            "feature_names артефакта не совпадают с текущими размерностями источников"
        )
    selected_tracks: list[SourceTrack] = []
    rows: list[np.ndarray] = []
    labels: list[str] = []
    skipped: list[str] = []
    for identity, label in labels_by_identity.items():
        track = by_identity.get(identity)
        if track is None:
            skipped.append(identity)
            continue
        row = _track_features(
            track,
            sources,
            scalar_fields=scalar_fields,
            embeddings=embeddings,
        )
        if row is None:
            skipped.append(identity)
            continue
        selected_tracks.append(track)
        rows.append(row)
        labels.append(str(label))
    matrix = (
        np.vstack(rows).astype(np.float32, copy=False)
        if rows
        else np.empty((0, len(feature_names)), dtype=np.float32)
    )
    if expected is not None and expected != feature_names:
        # Columns follow the artifact's own family order (older artifacts
        # predate the canonical order); the model was fitted on that layout.
        position = {name: index for index, name in enumerate(feature_names)}
        matrix = matrix[:, [position[name] for name in expected]]
        feature_names = expected
    return FeatureMatrix(
        tracks=tuple(selected_tracks),
        labels=labels,
        matrix=matrix,
        feature_names=feature_names,
        skipped_identities=tuple(skipped),
        source_dimensions=MappingProxyType(
            {
                source: (
                    len(_sonara_feature_names(scalar_fields))
                    if source == "sonara"
                    else embeddings[source][0]
                )
                for source in sources
            }
        ),
    )


def _track_features(
    track: SourceTrack,
    sources: tuple[str, ...],
    *,
    scalar_fields: tuple[str, ...],
    embeddings: Mapping[str, tuple[int, dict[int, np.ndarray]]],
) -> np.ndarray | None:
    parts: list[np.ndarray] = []
    if "sonara" in sources:
        values = _sonara_features(track, scalar_fields=scalar_fields)
        if values is None:
            return None
        parts.append(values)
    for family in sources:
        if family == "sonara":
            continue
        vector = embeddings[family][1].get(track.track_id)
        if vector is None:
            return None
        parts.append(vector)
    return np.concatenate(parts).astype(np.float32, copy=False) if parts else None


def _sonara_features(
    track: SourceTrack,
    *,
    scalar_fields: tuple[str, ...],
) -> np.ndarray | None:
    features = track.sonara_features
    if features is None:
        return None
    values: list[float] = []
    for field in scalar_fields:
        value = getattr(features, _SONARA_ATTRIBUTES[field])
        number = _finite_float_or_none(value)
        if number is None:
            return None
        values.append(number)
    for field, length in SONARA_VECTOR_FIELDS.items():
        vector = getattr(features, field)
        if len(vector) != length:
            return None
        converted = [_finite_float_or_none(value) for value in vector]
        if any(value is None for value in converted):
            return None
        values.extend(float(value) for value in converted if value is not None)
    return np.asarray(values, dtype=np.float32)


def _cached_embedding_vectors(
    source: SourceDatabase,
    family: str,
    cache: dict[str, tuple[int, dict[int, np.ndarray]]],
    *,
    track_ids: Sequence[int],
) -> tuple[int, dict[int, np.ndarray]]:
    cached = cache.get(family)
    missing_ids = (
        list(track_ids)
        if cached is None
        else [track_id for track_id in track_ids if track_id not in cached[1]]
    )
    if cached is None or missing_ids:
        loaded = load_source_embeddings(source, family, track_ids=missing_ids)
        loaded_vectors = {
            track.track_id: loaded.matrix[index].astype(np.float32, copy=True)
            for index, track in enumerate(loaded.tracks)
        }
        if cached is None:
            cache[family] = (loaded.dimension, loaded_vectors)
        else:
            if loaded.dimension != cached[0]:
                raise ValueError(
                    f"Размерность {family.upper()} изменилась во время построения признаков"
                )
            cached[1].update(loaded_vectors)
    return cache[family]


def _parse_feature_names(value: object) -> list[str] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("feature_names должен быть непустым упорядоченным списком уникальных строк")
    return list(value)


def feature_sources(feature_set: str) -> tuple[str, ...]:
    """Validate a ``"+"``-joined recipe and return its sources in canonical order."""

    clean = str(feature_set or "").strip().lower()
    return _canonical_sources(
        tuple(part.strip() for part in clean.split("+") if part.strip())
    )


def canonical_feature_set(sources: Iterable[str]) -> str:
    """Return the canonical ``"a+b"`` string for a validated set of sources."""

    return "+".join(
        _canonical_sources(tuple(str(source).strip().lower() for source in sources))
    )


def _canonical_sources(raw: tuple[str, ...]) -> tuple[str, ...]:
    if not raw:
        raise ValueError("Укажите набор признаков")
    parsed = [_parse_feature_source(token) for token in raw]
    canonical = [_source_token(family, layer) for family, layer in parsed]
    duplicates = sorted(
        source for source in set(canonical) if canonical.count(source) > 1
    )
    if duplicates:
        raise ValueError(f"Источник признаков повторяется: {', '.join(duplicates)}")
    ordered = sorted(
        zip(parsed, canonical),
        key=lambda item: (SUPPORTED_FEATURE_SOURCES.index(item[0][0]), item[0][1]),
    )
    return tuple(token for _parsed, token in ordered)


def _parse_feature_source(token: str) -> tuple[str, int]:
    family, separator, layer_text = token.partition("@")
    if family not in SUPPORTED_FEATURE_SOURCES:
        raise ValueError(f"Неподдерживаемый источник признаков: {family or token}")
    if not separator:
        return family, MERT_V2_DEFAULT_LAYER if family in _LAYERED_FAMILIES else 0
    if family not in _LAYERED_FAMILIES:
        raise ValueError(f"{family.upper()} не хранит слои эмбеддинга: {token}")
    if not layer_text.isdigit() or int(layer_text) < 1 or str(int(layer_text)) != layer_text:
        raise ValueError(f"Слой {family.upper()} должен быть положительным целым числом: {token}")
    return family, int(layer_text)


def _source_token(family: str, layer: int) -> str:
    if family in _LAYERED_FAMILIES and layer != MERT_V2_DEFAULT_LAYER:
        return f"{family}@{layer}"
    return family


def split_feature_source(source: str) -> tuple[str, int | None]:
    """``"mert_v2@12"`` -> ``("mert_v2", 12)``; ``"mert_v2"``/``"sonara"`` -> layer ``None`` (stored default)."""

    family, layer = _parse_feature_source(str(source).strip().lower())
    if family in _LAYERED_FAMILIES and layer != MERT_V2_DEFAULT_LAYER:
        return family, layer
    return family, None


def source_family(source: str) -> str:
    return split_feature_source(source)[0]


def available_feature_sources(feature_states: Mapping[str, object]) -> tuple[str, ...]:
    """Families whose stored data is current, in canonical order (bare tokens only)."""

    return tuple(
        source
        for source in SUPPORTED_FEATURE_SOURCES
        if _feature_state_payload(feature_states.get(source), source=source)["status"]
        == "current"
    )


def source_availability_error(
    source: str,
    available: Sequence[str],
    mert_v2_layers: Sequence[int] = (),
) -> str | None:
    """Why one recipe token cannot be trained from this library, or ``None``."""

    family, layer = split_feature_source(source)
    if family not in available:
        return f"Данные {family.upper()} не сохранены в этой библиотеке"
    if layer is not None and layer not in tuple(mert_v2_layers):
        return f"Слой {layer} {family.upper()} не сохранён в этой библиотеке"
    return None


def stored_mert_v2_layers(source: SourceDatabase) -> tuple[int, ...]:
    """Layers with stored MERT-v2 rows in this library, ascending."""

    return tuple(sorted({int(layer) for layer in source.mert_v2_stored_layers()}))


def load_source_embeddings(
    source: SourceDatabase,
    token: str,
    *,
    track_ids: Sequence[int] | None,
):
    """Load one recipe token's vectors; ``mert_v2@N`` reads layer N, bare tokens the default."""

    family, layer = split_feature_source(token)
    if layer is None:
        return source.load_embedding_matrix(family, track_ids=track_ids)  # type: ignore[arg-type]
    return source.load_embedding_matrix(family, track_ids=track_ids, layer=layer)  # type: ignore[arg-type]


def default_feature_set(available: Sequence[str]) -> str | None:
    """The recipe that uses every available source; ``None`` when nothing is stored."""

    return canonical_feature_set(available) if available else None


def artifact_feature_compatibility(
    *,
    feature_set: str,
    feature_names: object,
) -> tuple[bool, str | None]:
    """Check an artifact's feature_names against its recipe and the current specs.

    The family order inside ``feature_names`` is the artifact's own: artifacts
    trained before the canonical order stay valid, and the main app derives the
    column layout from the names. Each family block must be contiguous and
    complete, and the set of families must equal the recipe.
    """

    try:
        required_sources = feature_sources(feature_set)
    except ValueError as error:
        return False, str(error)
    if (
        not isinstance(feature_names, list)
        or not feature_names
        or any(not isinstance(name, str) or ":" not in name for name in feature_names)
    ):
        return False, "Артефакт не содержит корректного упорядоченного списка feature_names."
    blocks: dict[str, tuple[str, ...]] = {}
    for token, names in groupby(feature_names, key=lambda name: str(name).partition(":")[0]):
        if token in blocks:
            return False, "В feature_names артефакта источники признаков перемешаны; переобучите модель."
        blocks[token] = tuple(names)
    if set(blocks) != set(required_sources):
        return False, "feature_names артефакта не соответствуют выбранному рецепту признаков."
    for token in required_sources:
        block = blocks[token]
        if token == "sonara":
            if block != SONARA_FEATURE_NAMES:
                return False, "Артефакт обучен на устаревшем рецепте SONARA; переобучите модель."
            continue
        dimension = current_embedding_spec(source_family(token)).dimension
        if block != tuple(f"{token}:{index}" for index in range(dimension)):
            return (
                False,
                f"Блок {token.upper()} артефакта не соответствует текущему эмбеддингу "
                f"размерности {dimension}; переобучите модель.",
            )
    return True, None


def artifact_source_readiness(
    *,
    feature_set: str,
    feature_names: object,
    feature_states: Mapping[str, object],
) -> tuple[bool, str | None]:
    """Compatibility plus current stored data for every source the artifact needs."""

    compatible, reason = artifact_feature_compatibility(
        feature_set=feature_set,
        feature_names=feature_names,
    )
    if not compatible:
        return False, reason
    for source in feature_sources(feature_set):
        family = source_family(source)
        state = _feature_state_payload(feature_states.get(family), source=family)
        if state["status"] != "current":
            return (
                False,
                str(state["reason"] or f"Данные источника {family.upper()} недоступны ({state['status']})."),
            )
    return True, None


def feature_recipe_readiness(
    feature_set: str,
    feature_states: Mapping[str, object],
) -> dict[str, object]:
    """Describe readiness strictly for the selected feature recipe."""

    required_sources = feature_sources(feature_set)
    selected_states: dict[str, dict[str, object]] = {}
    blocking: list[dict[str, object]] = []
    for source in required_sources:
        family = source_family(source)
        state = _feature_state_payload(feature_states.get(family), source=family)
        selected_states[source] = state
        if state["status"] != "current":
            blocking.append({"source": source, **state})
    return {
        "feature_set": str(feature_set).strip().lower(),
        "required_sources": list(required_sources),
        "ready": not blocking,
        "sources": selected_states,
        "blocking": blocking,
    }


def _feature_state_payload(value: object, *, source: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        status = str(value.get("status") or "missing")
        reason = value.get("reason")
    else:
        status = str(getattr(value, "status", "missing"))
        reason = getattr(value, "reason", None)
    if status not in {"current", "missing"}:
        status = "missing"
        reason = f"Состояние признаков {source.upper()} неизвестно."
    return {
        "status": status,
        "reason": None if reason is None else str(reason),
    }


def _sonara_scalar_fields() -> tuple[str, ...]:
    return SONARA_SCALAR_FIELDS


def _feature_names(
    sources: tuple[str, ...],
    *,
    scalar_fields: tuple[str, ...],
    embeddings: Mapping[str, tuple[int, dict[int, np.ndarray]]],
) -> list[str]:
    names = _sonara_feature_names(scalar_fields) if "sonara" in sources else []
    for family in sources:
        if family != "sonara":
            names.extend(f"{family}:{index}" for index in range(embeddings[family][0]))
    return names


def _sonara_feature_names(scalar_fields: tuple[str, ...]) -> list[str]:
    if scalar_fields != SONARA_SCALAR_FIELDS:
        raise ValueError("SONARA feature schema must use the current scalar fields")
    return list(SONARA_FEATURE_NAMES)


def _finite_float_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

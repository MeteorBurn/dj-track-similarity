"""Physical SONARA descriptors of a whole track, grouped into musical facets.

Every value is a SONARA measurement (Core scalars and vectors, Timeline curves)
or fixed arithmetic over one. The heuristic Perceptual, Mood, Aggression and
Vocalness outputs are never read.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Facet:
    key: str
    label: str
    weight: float
    description: str


@dataclass(frozen=True, slots=True)
class Descriptor:
    key: str
    facet: str
    label: str
    unit: str
    note: str = ""


# Facet weights are fixed before any search. Tempo and pitch class are the two
# properties a DJ changes on the deck, so they count at a quarter.
FACETS: tuple[Facet, ...] = (
    Facet("groove", "Ритм и грув", 1.0, "плотность и регулярность атак, их место внутри доли"),
    Facet("dynamics", "Динамика и развитие", 1.0, "громкость, размах, брейки и форма энергии по треку"),
    Facet("spectrum", "Спектр и текстура", 1.0, "яркость, шумность, контраст в 7 полосах"),
    Facet("timbre", "Тембр", 1.0, "огибающая спектра MFCC 1–12; c0 (громкость) исключён"),
    Facet("harmony", "Гармония и лад", 1.0, "лад по хроме и аккордам, диссонанс, гармонический ритм, профиль от тоники"),
    Facet("pitch", "Высота (тоника)", 0.25, "классы высот без транспонирования; вес снижен"),
    Facet("tempo", "Темп", 0.25, "BPM SONARA; вес снижен, SONARA сворачивает октавы"),
)

INTERVALS = ("I", "♭II", "II", "♭III", "III", "IV", "♯IV", "V", "♭VI", "VI", "♭VII", "VII")
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

DESCRIPTORS: tuple[Descriptor, ...] = (
    Descriptor("bpm", "tempo", "BPM", "уд/мин", "SONARA, свёрнут в диапазон библиотеки"),
    Descriptor("onset_density", "groove", "Плотность атак", "атак/с"),
    Descriptor("onsets_per_beat", "groove", "Атак на долю", "шт"),
    Descriptor("phase_on", "groove", "Атаки на доле", "доля", "у самого удара бита"),
    Descriptor("phase_e", "groove", "Атаки на 2-й 1/16", "доля", "четверть доли после бита"),
    Descriptor("phase_and", "groove", "Атаки на «и»", "доля", "середина доли, офбит"),
    Descriptor("phase_a", "groove", "Атаки на 4-й 1/16", "доля", "перед следующим битом"),
    Descriptor("ioi_cv", "groove", "Нерегулярность атак", "CV", "разброс промежутков между атаками"),
    Descriptor("beat_grid_stability", "groove", "Стабильность сетки", "0–1"),
    Descriptor("tempo_variability", "groove", "Плавание темпа", "уд/мин"),
    Descriptor("lufs", "dynamics", "Громкость", "LUFS", "интегральная; зависит и от мастеринга"),
    Descriptor("loudness_range", "dynamics", "Диапазон громкости", "LU"),
    Descriptor("dynamic_range", "dynamics", "Динамический диапазон", "дБ"),
    Descriptor("energy_std", "dynamics", "Колебания энергии", "σ"),
    Descriptor("energy_p50", "dynamics", "Энергия, медиана", "0–1", "по кривой энергии всего трека"),
    Descriptor("energy_span", "dynamics", "Размах энергии p10–p90", "0–1"),
    Descriptor("break_depth", "dynamics", "Глубина брейков", "0–1", "p95−p5 энергии, сглаженной за 8 с"),
    Descriptor("break_share", "dynamics", "Доля брейков", "доля", "время ниже 75% пиковой энергии"),
    Descriptor("segment_rate", "dynamics", "Смены частей", "в минуту", "сегменты структуры SONARA"),
    Descriptor("centroid", "spectrum", "Яркость (центроид)", "Гц"),
    Descriptor("bandwidth", "spectrum", "Ширина спектра", "Гц"),
    Descriptor("rolloff", "spectrum", "Срез верхов (rolloff)", "Гц"),
    Descriptor("flatness", "spectrum", "Шумность (flatness)", "0–1"),
    Descriptor("zcr", "spectrum", "Переходы через ноль", "0–1"),
    *(Descriptor(f"contrast_{i}", "spectrum", f"Контраст, полоса {i}", "дБ",
                 "низ" if i == 1 else "верх" if i == 7 else "") for i in range(1, 8)),
    *(Descriptor(f"mfcc_{i}", "timbre", f"MFCC {i}", "") for i in range(1, 13)),
    Descriptor("mode_chroma", "harmony", "Мажорность по хроме", "r", "корреляция с мажором минус с минором"),
    Descriptor("minor_share", "harmony", "Минорные аккорды", "доля", "по времени, аккорды SONARA"),
    Descriptor("chord_entropy", "harmony", "Разнообразие аккордов", "бит"),
    Descriptor("chord_rate", "harmony", "Смены аккордов", "в секунду"),
    Descriptor("dissonance", "harmony", "Диссонанс", "0–1"),
    Descriptor("key_clarity", "harmony", "Ясность тональности", "r", "корреляция хромы с лучшим шаблоном"),
    *(Descriptor(f"interval_{i}", "harmony", f"Ступень {INTERVALS[i]}", "доля", "хрома от тоники")
      for i in range(12)),
    *(Descriptor(f"pitch_{i}", "pitch", f"Класс {PITCH_CLASSES[i]}", "доля") for i in range(12)),
)
DESCRIPTOR_KEYS = tuple(item.key for item in DESCRIPTORS)
FACET_KEYS = tuple(facet.key for facet in FACETS)
FACET_OF = np.array([FACET_KEYS.index(item.facet) for item in DESCRIPTORS])

_CORE_SCALARS = {
    "bpm": "detected_bpm",
    "onset_density": "onset_density_per_second",
    "beat_grid_stability": "beat_grid_stability",
    "tempo_variability": "tempo_variability",
    "lufs": "integrated_loudness_lufs",
    "loudness_range": "loudness_range_lu",
    "dynamic_range": "dynamic_range_db",
    "energy_std": "energy_curve_stddev",
    "centroid": "spectral_centroid_hz",
    "bandwidth": "spectral_bandwidth_hz",
    "rolloff": "spectral_rolloff_hz",
    "flatness": "spectral_flatness",
    "zcr": "zero_crossing_rate",
    "dissonance": "dissonance_score",
    "chord_rate": "chord_changes_per_second",
}


@dataclass(frozen=True, slots=True)
class TonalCentre:
    tonic: str
    mode: str


def describe(core: Mapping[str, object], timeline: Mapping[str, object] | None) -> tuple[np.ndarray, TonalCentre]:
    """One track's descriptor vector in ``DESCRIPTOR_KEYS`` order; unknown values are NaN."""

    values: dict[str, float] = {key: _number(core.get(column)) for key, column in _CORE_SCALARS.items()}
    contrast = _vector(core.get("spectral_contrast_mean_blob"), 7)
    mfcc = _vector(core.get("mfcc_mean_blob"), 13)
    values |= {f"contrast_{i + 1}": contrast[i] for i in range(7)}
    values |= {f"mfcc_{i}": mfcc[i] for i in range(1, 13)}
    tonal, centre = _tonal(_vector(core.get("chroma_mean_blob"), 12))
    values |= tonal
    if timeline is not None:
        values |= _timeline(timeline, _number(core.get("analyzed_duration_seconds")))
    return np.array([values.get(key, math.nan) for key in DESCRIPTOR_KEYS], dtype=np.float64), centre


def _number(value: object) -> float:
    if value is None:
        return math.nan
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) else math.nan


def _vector(value: object, size: int) -> np.ndarray:
    if value is None:
        return np.full(size, math.nan)
    vector = np.asarray(value, dtype=np.float64).reshape(-1)
    return vector if vector.size == size else np.full(size, math.nan)


def _tonal(chroma: np.ndarray) -> tuple[dict[str, float], TonalCentre]:
    total = float(np.sum(chroma))
    if not math.isfinite(total) or total <= 0:
        return {}, TonalCentre("—", "—")
    pcp = chroma / total
    best, major_best, minor_best = (-2.0, 0, "major"), -2.0, -2.0
    for shift in range(12):
        rolled = np.roll(pcp, -shift)
        major = float(np.corrcoef(rolled, _KK_MAJOR)[0, 1])
        minor = float(np.corrcoef(rolled, _KK_MINOR)[0, 1])
        major_best, minor_best = max(major_best, major), max(minor_best, minor)
        best = max(best, (major, shift, "major"), (minor, shift, "minor"))
    rotated = np.roll(pcp, -best[1])
    values = {f"pitch_{i}": float(pcp[i]) for i in range(12)}
    values |= {f"interval_{i}": float(rotated[i]) for i in range(12)}
    values["mode_chroma"] = major_best - minor_best
    values["key_clarity"] = best[0]
    return values, TonalCentre(PITCH_CLASSES[best[1]], best[2])


def smoothed_energy(energy: np.ndarray, hop: float) -> np.ndarray:
    width = max(1, round(8.0 / hop))
    if energy.size < width:
        return energy
    return np.convolve(energy, np.ones(width) / width, mode="valid")


def _timeline(timeline: Mapping[str, object], duration: float) -> dict[str, float]:
    out: dict[str, float] = {}
    beats = np.asarray(timeline.get("beats") or [], dtype=np.float64)
    onsets = np.asarray(timeline.get("onsets") or [], dtype=np.float64)
    if beats.size >= 8 and onsets.size >= 8:
        inside = onsets[(onsets >= beats[0]) & (onsets < beats[-1])]
        index = np.searchsorted(beats, inside, side="right") - 1
        phase = (inside - beats[index]) / (beats[index + 1] - beats[index])
        bins = np.floor(phase * 4 + 0.5).astype(int) % 4
        shares = np.bincount(bins, minlength=4) / max(len(bins), 1)
        out |= {"phase_on": shares[0], "phase_e": shares[1], "phase_and": shares[2], "phase_a": shares[3]}
        out["onsets_per_beat"] = len(inside) / (beats.size - 1)
    if onsets.size >= 8:
        gaps = np.diff(onsets)
        if np.mean(gaps) > 0:
            out["ioi_cv"] = float(np.std(gaps) / np.mean(gaps))
    energy = np.asarray(timeline.get("energy_curve") or [], dtype=np.float64)
    hop = float(timeline.get("energy_curve_hop_seconds") or 0.5)  # type: ignore[arg-type]
    if energy.size >= 32:
        smooth = smoothed_energy(energy, hop)
        p95, p05 = np.quantile(smooth, 0.95), np.quantile(smooth, 0.05)
        out["energy_p50"] = float(np.median(energy))
        out["energy_span"] = float(np.quantile(energy, 0.9) - np.quantile(energy, 0.1))
        out["break_depth"] = float(p95 - p05)
        if p95 > 0:
            out["break_share"] = float(np.mean(smooth < 0.75 * p95))
    segments = timeline.get("segments") or []
    if segments and duration > 0:
        out["segment_rate"] = len(segments) / duration * 60.0  # type: ignore[arg-type]
    weights: dict[str, float] = {}
    for event in timeline.get("chord_events") or []:  # type: ignore[union-attr]
        weights[event["label"]] = weights.get(event["label"], 0.0) + event["end_sec"] - event["start_sec"]
    total = sum(weights.values())
    if total > 0:
        probabilities = np.array([value / total for value in weights.values() if value > 0])
        out["minor_share"] = sum(v for k, v in weights.items() if k.endswith("m")) / total
        out["chord_entropy"] = float(-(probabilities * np.log2(probabilities)).sum())
    return out

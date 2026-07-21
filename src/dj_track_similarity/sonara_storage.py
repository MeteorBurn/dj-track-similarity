from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SonaraCoreStorage:
    features: dict[str, object]
    bpm: float | None
    musical_key: str | None
    energy: float | None
    duration: float | None
    model_name: str
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object] | None


@dataclass(frozen=True)
class SonaraTimelineStorage:
    timeline: dict[str, object]
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object]


@dataclass(frozen=True)
class SonaraRepresentationsStorage:
    embedding: np.ndarray
    fingerprint: dict[str, object]
    embedding_version: str | None
    fingerprint_version: str | None
    model_name: str
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object]


@dataclass(frozen=True)
class SonaraAnalysisStorage:
    track_id: int
    core: SonaraCoreStorage | None = None
    timeline: SonaraTimelineStorage | None = None
    representations: SonaraRepresentationsStorage | None = None

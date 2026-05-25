from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from .database import LibraryDatabase
from .models import Track
from .sonara_similarity_scoring import optional_float, unwrap_feature_value


CLASSIFIER_NAME = "break_energy"
BREAK_ENERGY_LABEL = "broken"
STRAIGHT_LABEL = "straight"


def default_break_energy_model_path() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "classifiers" / "break-energy" / "model.joblib"


def analyze_break_energy(
    db: LibraryDatabase,
    *,
    model_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    path = Path(model_path) if model_path is not None else default_break_energy_model_path()
    scorer = BreakEnergyScorer(db, path)

    tracks = db.list_tracks(include_metadata=True)

    scored = 0
    skipped = 0
    for track in tracks:
        if limit is not None and scored >= max(0, int(limit)):
            break
        result = scorer.score_track(track)
        if result is None:
            skipped += 1
            continue
        scorer.save_score(track, result)
        scored += 1

    return {
        "classifier": CLASSIFIER_NAME,
        "scored": scored,
        "skipped": skipped,
        "model": str(path),
    }


class BreakEnergyScorer:
    def __init__(self, db: LibraryDatabase, model_path: str | Path | None = None) -> None:
        self.db = db
        self.path = Path(model_path) if model_path is not None else default_break_energy_model_path()
        self.payload = _load_payload(self.path)
        self.model = self.payload["model"]
        self.feature_names = [str(name) for name in self.payload.get("feature_names", [])]
        if not self.feature_names:
            raise ValueError("Break Energy model artifact does not contain feature_names")
        self.feature_set = str(self.payload.get("feature_set") or "combined")
        self.mert_vectors = _embedding_vectors(db, "mert")
        self.maest_vectors = _embedding_vectors(db, "maest")

    @property
    def model_name(self) -> str:
        return str(self.path)

    def score_track(self, track: Track) -> dict[str, float] | None:
        row = _track_feature_row(
            track,
            self.feature_names,
            mert_vectors=self.mert_vectors,
            maest_vectors=self.maest_vectors,
        )
        if row is None:
            return None
        probability = _predict_probabilities(self.model, row.reshape(1, -1), self.payload)[0]
        score = float(probability.get(BREAK_ENERGY_LABEL, 0.0))
        straight = float(probability.get(STRAIGHT_LABEL, 0.0))
        return {"break_energy": score, "straight_energy": straight}

    def save_score(self, track: Track, probabilities: dict[str, float]) -> None:
        score = float(probabilities.get("break_energy", 0.0))
        straight = float(probabilities.get("straight_energy", 0.0))
        self.db.save_classifier_score(
            track.id,
            classifier=CLASSIFIER_NAME,
            score=score,
            label=_score_label(score),
            confidence=max(score, straight),
            probabilities={"break_energy": score, "straight_energy": straight},
            feature_set=self.feature_set,
            model_id=str(self.path),
        )


def _load_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Break Energy model not found: {path}")
    try:
        import joblib
    except ImportError as error:  # pragma: no cover - dependency is installed in supported envs.
        raise RuntimeError("Break Energy analysis requires joblib") from error
    payload = joblib.load(path)
    if not isinstance(payload, dict) or "model" not in payload:
        raise ValueError("Break Energy model artifact must be a joblib payload with a model")
    return payload


def _track_feature_row(
    track: Track,
    feature_names: Iterable[str],
    *,
    mert_vectors: dict[int, np.ndarray],
    maest_vectors: dict[int, np.ndarray],
) -> np.ndarray | None:
    values: list[float] = []
    metadata = track.metadata or {}
    sonara = metadata.get("sonara_features")
    for name in feature_names:
        source, _, key = name.partition(":")
        if source == "sonara":
            if not isinstance(sonara, dict):
                return None
            values.append(_sonara_feature_value(sonara, key))
            continue
        if source == "mert":
            vector = mert_vectors.get(track.id)
            if vector is None:
                return None
            values.append(_vector_value(vector, key))
            continue
        if source == "maest":
            vector = maest_vectors.get(track.id)
            if vector is None:
                return None
            values.append(_vector_value(vector, key))
            continue
        raise ValueError(f"Unsupported Break Energy feature: {name}")
    return np.asarray(values, dtype=np.float32)


def _sonara_feature_value(features: dict[str, object], key: str) -> float:
    field, separator, index_text = key.rpartition(":")
    if separator and index_text.isdigit():
        raw = unwrap_feature_value(features.get(field))
        if isinstance(raw, (list, tuple)):
            index = int(index_text)
            if 0 <= index < len(raw):
                number = optional_float(raw[index])
                return float(number) if number is not None else 0.0
        return 0.0
    number = optional_float(unwrap_feature_value(features.get(key)))
    return float(number) if number is not None else 0.0


def _vector_value(vector: np.ndarray, index_text: str) -> float:
    index = int(index_text)
    if index < 0 or index >= int(vector.shape[0]):
        return 0.0
    return float(vector[index])


def _embedding_vectors(db: LibraryDatabase, embedding_key: str) -> dict[int, np.ndarray]:
    tracks, matrix = db.load_embedding_matrix(embedding_key)
    return {track.id: matrix[index].astype(np.float32, copy=True) for index, track in enumerate(tracks)}


def _predict_probabilities(model: object, matrix: np.ndarray, payload: dict[str, object]) -> list[dict[str, float]]:
    label_order = [str(label) for label in payload.get("label_order", [BREAK_ENERGY_LABEL, STRAIGHT_LABEL])]
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        raw = np.asarray(predict_proba(matrix), dtype=np.float64)
        classes = [str(label) for label in getattr(model, "classes_", label_order)]
        return [
            {label: float(raw[row_index, classes.index(label)]) if label in classes else 0.0 for label in label_order}
            for row_index in range(raw.shape[0])
        ]
    predictions = [str(label) for label in model.predict(matrix)]
    return [{label: 1.0 if label == predicted else 0.0 for label in label_order} for predicted in predictions]


def _score_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"

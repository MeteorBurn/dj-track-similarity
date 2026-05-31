from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .database import LibraryDatabase
from .models import Track
from .sonara_similarity_scoring import optional_float, unwrap_feature_value


def classifier_artifact_slug(classifier_key: str) -> str:
    return classifier_key.strip().replace("_", "-")


def default_classifier_model_path(classifier_key: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "models"
        / "classifiers"
        / classifier_artifact_slug(classifier_key)
        / "model.joblib"
    )


def default_classifier_models_root() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "classifiers"


def promoted_classifiers(root: str | Path | None = None) -> list[dict[str, object]]:
    models_root = Path(root) if root is not None else default_classifier_models_root()
    if not models_root.exists():
        return []
    classifiers: list[dict[str, object]] = []
    for metadata_path in sorted(models_root.glob("*/model.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        classifier_key = str(metadata.get("classifier_key") or "").strip()
        if not classifier_key:
            continue
        model_path = metadata_path.with_name("model.joblib")
        if not model_path.exists():
            continue
        classifiers.append(
            {
                "classifier_key": classifier_key,
                "name": str(metadata.get("profile_name") or classifier_key.replace("_", " ").title()),
                "artifact_prefix": metadata_path.parent.name,
                "positive_label": metadata.get("positive_label"),
                "label_order": metadata.get("label_order", []),
                "model_path": str(model_path),
                "metadata_path": str(metadata_path),
            }
        )
    return classifiers


def analyze_classifier(
    db: LibraryDatabase,
    *,
    classifier: str,
    model_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    scorer = ClassifierScorer(db, classifier=classifier, model_path=model_path)
    tracks = db.list_tracks_missing_classifier(classifier, limit=limit)

    scored = 0
    skipped = 0
    for track in tracks:
        result = scorer.score_track(track)
        if result is None:
            skipped += 1
            continue
        scorer.save_score(track, result)
        scored += 1

    return {
        "classifier": scorer.classifier_key,
        "scored": scored,
        "skipped": skipped,
        "model": str(scorer.path),
    }


class ClassifierScorer:
    def __init__(
        self,
        db: LibraryDatabase,
        *,
        classifier: str,
        model_path: str | Path | None = None,
    ) -> None:
        self.db = db
        self.classifier_key = classifier
        self.path = Path(model_path) if model_path is not None else default_classifier_model_path(classifier)
        self.payload = _load_payload(self.path)
        artifact_classifier = str(self.payload.get("classifier_key") or classifier)
        if artifact_classifier != classifier:
            raise ValueError(f"Expected artifact for classifier {classifier!r}, got {artifact_classifier!r}")
        self.classifier_key = artifact_classifier
        self.model = self.payload["model"]
        self.feature_names = [str(name) for name in self.payload.get("feature_names", [])]
        if not self.feature_names:
            raise ValueError(f"{self.classifier_key} model artifact does not contain feature_names")
        self.feature_set = str(self.payload.get("feature_set") or "combined")
        self.label_order = [str(label) for label in self.payload.get("label_order", [])]
        if not self.label_order:
            raise ValueError(f"{self.classifier_key} model artifact does not contain label_order")
        self.positive_label = str(self.payload.get("positive_label") or self.label_order[0])
        self.needs_mert = any(name.startswith("mert:") for name in self.feature_names)
        self.needs_maest = any(name.startswith("maest:") for name in self.feature_names)
        self.mert_vectors = _embedding_vectors(db, "mert")
        self.maest_vectors = _embedding_vectors(db, "maest")

    @property
    def model_name(self) -> str:
        return str(self.path)

    def score_track(self, track: Track) -> dict[str, float] | None:
        self._load_recent_embedding_vectors(track.id)
        row = _track_feature_row(
            track,
            self.feature_names,
            mert_vectors=self.mert_vectors,
            maest_vectors=self.maest_vectors,
        )
        if row is None:
            return None
        return _predict_probabilities(self.model, row.reshape(1, -1), self.label_order)[0]

    def _load_recent_embedding_vectors(self, track_id: int) -> None:
        if self.needs_mert and track_id not in self.mert_vectors:
            vector = self.db.embedding_vector(track_id, "mert")
            if vector is not None:
                self.mert_vectors[track_id] = vector.astype(np.float32, copy=False)
        if self.needs_maest and track_id not in self.maest_vectors:
            vector = self.db.embedding_vector(track_id, "maest")
            if vector is not None:
                self.maest_vectors[track_id] = vector.astype(np.float32, copy=False)

    def save_score(self, track: Track, probabilities: dict[str, float]) -> None:
        score = float(probabilities.get(self.positive_label, 0.0))
        confidence = max(probabilities.values()) if probabilities else score
        self.db.save_classifier_score(
            track.id,
            classifier=self.classifier_key,
            score=score,
            label=_score_label(score),
            confidence=float(confidence),
            probabilities=probabilities,
            feature_set=self.feature_set,
            model_id=str(self.path),
        )


def _load_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Classifier model not found: {path}")
    try:
        import joblib
    except ImportError as error:  # pragma: no cover - dependency is installed in supported envs.
        raise RuntimeError("Classifier analysis requires joblib") from error
    payload = joblib.load(path)
    if not isinstance(payload, dict) or "model" not in payload:
        raise ValueError("Classifier model artifact must be a joblib payload with a model")
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
        raise ValueError(f"Unsupported classifier feature: {name}")
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
    return {track.id: matrix[index].astype(np.float32, copy=False) for index, track in enumerate(tracks)}


def _predict_probabilities(model: object, matrix: np.ndarray, label_order: list[str]) -> list[dict[str, float]]:
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

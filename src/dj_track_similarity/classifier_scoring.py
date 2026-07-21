from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .classifier_manifest import (
    ClassifierManifestSummary,
    classifier_manifest_api_fields,
    classifier_manifest_path,
    load_classifier_manifest_summary,
    require_scoring_compatible_manifest,
)
from .database import LibraryDatabase
from .models import Track
from .sonara_contract import (
    feature_set_uses_sonara,
    sonara_analysis_is_compatible,
    sonara_analysis_signatures_match,
)
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
    artifact_dirs = sorted({path.parent for path in (*models_root.glob("*/model.joblib"), *models_root.glob("*/model.json"))})
    for artifact_dir in artifact_dirs:
        model_path = artifact_dir / "model.joblib"
        metadata_path = artifact_dir / "model.json"
        classifier_key = _classifier_key_from_metadata_or_slug(metadata_path, artifact_dir.name)
        summary = load_classifier_manifest_summary(
            model_path,
            expected_classifier_key=classifier_key,
            metadata_path=metadata_path,
        )
        classifiers.append(_promoted_classifier_payload(summary, model_path_exists=model_path.exists()))
    return classifiers


@dataclass(frozen=True)
class ClassifierRequirements:
    classifier_key: str
    model_path: Path
    model_id: str
    feature_set: str
    feature_names: tuple[str, ...]
    required_inputs: tuple[str, ...]
    sonara_analysis_signature: dict[str, object] | None


def load_classifier_requirements(
    classifier: str,
    *,
    model_path: str | Path | None = None,
) -> ClassifierRequirements:
    path = Path(model_path) if model_path is not None else default_classifier_model_path(classifier)
    manifest = _scoring_manifest(path, classifier=classifier, require_default_manifest=model_path is None)
    payload = _load_payload(path)
    _validate_payload_against_manifest(payload, manifest, classifier)
    feature_names = tuple(str(name) for name in payload.get("feature_names", []))
    if not feature_names:
        raise ValueError(f"{classifier} model artifact does not contain feature_names")
    feature_set = str(payload.get("feature_set") or "combined")
    required = set(manifest.required_inputs if manifest is not None else ())
    for source in ("sonara", "mert", "maest", "clap"):
        if any(name.startswith(f"{source}:") for name in feature_names):
            required.add(source)
    if feature_set_uses_sonara(feature_set):
        required.add("sonara")
    ordered_inputs = tuple(source for source in ("sonara", "mert", "maest", "clap") if source in required)
    signature = dict(manifest.sonara_analysis_signature) if manifest and manifest.sonara_analysis_signature else None
    if "sonara" in ordered_inputs and signature is None:
        raise ValueError(f"{classifier} uses SONARA inputs but has no compatible SONARA analysis signature")
    model_id = manifest.model_id if manifest is not None and manifest.model_id else str(path)
    return ClassifierRequirements(
        classifier_key=classifier,
        model_path=path,
        model_id=model_id,
        feature_set=feature_set,
        feature_names=feature_names,
        required_inputs=ordered_inputs,
        sonara_analysis_signature=signature,
    )


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

    result: dict[str, object] = {
        "classifier": scorer.classifier_key,
        "scored": scored,
        "skipped": skipped,
        "model": str(scorer.path),
    }
    if scorer.manifest_warnings:
        result["warnings"] = list(scorer.manifest_warnings)
    return result


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
        self.manifest = _scoring_manifest(self.path, classifier=classifier, require_default_manifest=model_path is None)
        self.manifest_warnings = tuple(self.manifest.warnings) if self.manifest is not None else ()
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
        self.needs_sonara = feature_set_uses_sonara(self.feature_set) or any(
            name.startswith("sonara:") for name in self.feature_names
        )
        _validate_payload_against_manifest(self.payload, self.manifest, self.classifier_key)
        if self.needs_sonara and (self.manifest is None or self.manifest.sonara_analysis_signature is None):
            raise ValueError(
                f"{self.classifier_key} uses SONARA inputs but has no compatible SONARA analysis signature"
            )
        self.needs_mert = any(name.startswith("mert:") for name in self.feature_names)
        self.needs_maest = any(name.startswith("maest:") for name in self.feature_names)
        self.needs_clap = any(name.startswith("clap:") for name in self.feature_names)
        self.mert_vectors = _embedding_vectors(db, "mert")
        self.maest_vectors = _embedding_vectors(db, "maest")
        self.clap_vectors = _embedding_vectors(db, "clap")

    @property
    def model_name(self) -> str:
        return str(self.path)

    def score_track(self, track: Track) -> dict[str, float] | None:
        if self.needs_sonara and not sonara_analysis_is_compatible(
            track.metadata,
            self.manifest.sonara_analysis_signature if self.manifest is not None else None,
        ):
            return None
        self._load_recent_embedding_vectors(track.id)
        row = _track_feature_row(
            track,
            self.feature_names,
            mert_vectors=self.mert_vectors,
            maest_vectors=self.maest_vectors,
            clap_vectors=self.clap_vectors,
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
        if self.needs_clap and track_id not in self.clap_vectors:
            vector = self.db.embedding_vector(track_id, "clap")
            if vector is not None:
                self.clap_vectors[track_id] = vector.astype(np.float32, copy=False)

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
            model_id=self.manifest.model_id if self.manifest is not None and self.manifest.model_id else str(self.path),
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


def _scoring_manifest(
    path: Path,
    *,
    classifier: str,
    require_default_manifest: bool,
) -> ClassifierManifestSummary | None:
    metadata_path = classifier_manifest_path(path)
    if require_default_manifest or metadata_path.exists():
        return require_scoring_compatible_manifest(path, expected_classifier_key=classifier, metadata_path=metadata_path)
    return None


def _validate_payload_against_manifest(
    payload: dict[str, object],
    manifest: ClassifierManifestSummary | None,
    classifier_key: str,
) -> None:
    if manifest is None or manifest.status != "valid":
        return
    feature_set = str(payload.get("feature_set") or "")
    if manifest.feature_set and feature_set != manifest.feature_set:
        raise ValueError(f"{classifier_key} model artifact feature_set does not match model.json")
    label_order = tuple(str(label) for label in payload.get("label_order", []))
    if manifest.label_order and label_order != manifest.label_order:
        raise ValueError(f"{classifier_key} model artifact label_order does not match model.json")
    positive_label = str(payload.get("positive_label") or "")
    if manifest.positive_label and positive_label != manifest.positive_label:
        raise ValueError(f"{classifier_key} model artifact positive_label does not match model.json")
    feature_names = [str(name) for name in payload.get("feature_names", [])]
    if manifest.feature_count is not None and feature_names and len(feature_names) != manifest.feature_count:
        raise ValueError(f"{classifier_key} model artifact feature count does not match model.json")
    if feature_set_uses_sonara(feature_set):
        payload_signature = payload.get("sonara_analysis_signature")
        if not sonara_analysis_signatures_match(payload_signature, manifest.sonara_analysis_signature):
            raise ValueError(f"{classifier_key} model artifact SONARA analysis signature does not match model.json")


def _classifier_key_from_metadata_or_slug(metadata_path: Path, artifact_slug: str) -> str:
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata, dict):
            classifier_key = str(metadata.get("classifier_key") or "").strip()
            if classifier_key:
                return classifier_key
    return artifact_slug.strip().replace("-", "_")


def _promoted_classifier_payload(summary: ClassifierManifestSummary, *, model_path_exists: bool) -> dict[str, object]:
    payload = {
        "classifier_key": summary.classifier_key,
        "name": str(summary.profile_name or summary.classifier_key.replace("_", " ").title()),
        "artifact_prefix": summary.artifact_prefix or summary.model_path.parent.name,
        "positive_label": summary.positive_label,
        "label_order": list(summary.label_order),
        "feature_set": summary.feature_set,
        "feature_count": summary.feature_count,
        "model_path": str(summary.model_path),
        "metadata_path": str(summary.metadata_path) if summary.metadata_path is not None and summary.metadata_path.exists() else None,
        **classifier_manifest_api_fields(summary),
    }
    if not model_path_exists:
        payload["manifest_status"] = "invalid"
        payload["manifest_errors"] = [*payload["manifest_errors"], "model.joblib is missing"]
        payload["is_scoring_compatible"] = False
    elif summary.status == "legacy":
        payload["manifest_errors"] = [
            *payload["manifest_errors"],
            "model.json is missing; promote the artifact again before scoring",
        ]
        payload["is_scoring_compatible"] = False
    return payload


def _track_feature_row(
    track: Track,
    feature_names: Iterable[str],
    *,
    mert_vectors: dict[int, np.ndarray],
    maest_vectors: dict[int, np.ndarray],
    clap_vectors: dict[int, np.ndarray],
) -> np.ndarray | None:
    values: list[float] = []
    metadata = track.metadata or {}
    sonara = metadata.get("sonara_features")
    for name in feature_names:
        source, _, key = name.partition(":")
        if source == "sonara":
            if not isinstance(sonara, dict):
                return None
            value = _sonara_feature_value(sonara, key)
            if value is None:
                return None
            values.append(value)
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
        if source == "clap":
            vector = clap_vectors.get(track.id)
            if vector is None:
                return None
            values.append(_vector_value(vector, key))
            continue
        raise ValueError(f"Unsupported classifier feature: {name}")
    return np.asarray(values, dtype=np.float32)


def _sonara_feature_value(features: dict[str, object], key: str) -> float | None:
    field, separator, index_text = key.rpartition(":")
    if separator and index_text.isdigit():
        raw = unwrap_feature_value(features.get(field))
        if isinstance(raw, (list, tuple)):
            index = int(index_text)
            if 0 <= index < len(raw):
                number = optional_float(raw[index])
                return float(number) if number is not None else None
        return None
    number = optional_float(unwrap_feature_value(features.get(key)))
    return float(number) if number is not None else None


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

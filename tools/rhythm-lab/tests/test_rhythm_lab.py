from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import fields, replace
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import joblib
import numpy as np
import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.analysis_models import current_embedding_spec  # noqa: E402
from dj_track_similarity.db.ddl import create_library_schema  # noqa: E402
from dj_track_similarity.db.schema import insert_library  # noqa: E402
from dj_track_similarity.library_models import AnalysisCoverage  # noqa: E402
from dj_track_similarity.classifier.sonara_features import (  # noqa: E402
    resolve_sonara_classifier_feature,
)
from dj_track_similarity.rhythm_lab_collections import (  # noqa: E402
    RhythmLabCollections,
    sonara_content_key,
)
from rhythm_lab import cli as cli_module  # noqa: E402
from rhythm_lab import ablation as ablation_module  # noqa: E402
from rhythm_lab import features as feature_module  # noqa: E402
from rhythm_lab import training as training_module  # noqa: E402
from rhythm_lab.artifact_io import artifact_sha256  # noqa: E402
from rhythm_lab.cli import (  # noqa: E402
    PromotionError,
    build_parser,
    promote_profile_model,
)
from rhythm_lab.features import (  # noqa: E402
    SONARA_FEATURE_NAMES,
    SONARA_SCALAR_FIELDS,
    SONARA_VECTOR_FIELDS,
    artifact_feature_compatibility,
    available_feature_sources,
    build_feature_matrix,
    canonical_feature_set,
    default_feature_set,
    feature_recipe_readiness,
    feature_sources,
)
from rhythm_lab.lab_db import RhythmLabDatabase  # noqa: E402
from rhythm_lab.predictions import _predict_probabilities  # noqa: E402
from rhythm_lab.source_db import (  # noqa: E402
    SourceEmbeddingMatrix,
    SourceFeatureState,
    SourceSonaraFeatures,
    SourceTrack,
)
from rhythm_lab.training import train_feature_set  # noqa: E402
from rhythm_lab.web_app import (  # noqa: E402
    TrainingProgress,
    _bind_artifact_source_readiness,
    _training_readiness,
    cleanup_training_artifacts,
)


NOW = "2026-07-24T10:00:00.000000Z"


def _fingerprint_base64(index: int) -> str:
    """Deterministic valid base64 of 8 bytes; distinct per index."""

    return base64.b64encode(bytes([index % 256, 7]) * 4).decode("ascii")


def _content_key(index: int) -> str:
    return sonara_content_key(1, _fingerprint_base64(index))


def _track(index: int) -> SourceTrack:
    return SourceTrack(
        catalog_uuid="catalog-current",
        track_id=index,
        track_uuid=f"track-{index}",
        file_path=f"C:/music/{index}.wav",
        file_size_bytes=1_000 + index,
        file_modified_ns=2_000 + index,
        audio_duration_seconds=180.0,
        file_tags=None,
        liked=False,
        sonara_features=None,
        maest=None,
        analysis_coverage=AnalysisCoverage(),
        content_key=_content_key(index),
    )


def _fake_library(
    path: Path,
    tracks: list[tuple[int, str, int]],
    *,
    catalog_uuid: str = "catalog-current",
) -> Path:
    """A minimal real library: ``(track_id, track_uuid, fingerprint index)`` rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        create_library_schema(connection)
        insert_library(connection, catalog_uuid, created_at=NOW)
        for track_id, track_uuid, index in tracks:
            connection.execute(
                """
                INSERT INTO tracks(
                    track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (track_id, track_uuid, f"C:/music/{index}.wav", 1_000 + index, 2_000 + index, NOW, NOW, NOW),
            )
            connection.execute(
                """
                INSERT INTO sonara_fingerprints(
                    track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (track_id, track_uuid, _fingerprint_base64(index), NOW),
            )
    return path


def _ready_library(root: Path, track_count: int = 4) -> Path:
    return _fake_library(
        root / "library.sqlite",
        [(index, f"track-{index}", index) for index in range(1, track_count + 1)],
    )


def _queue_item(track: SourceTrack, *, priority: float) -> dict[str, object]:
    return {
        "content_key": track.content_key,
        "catalog_uuid": track.catalog_uuid,
        "track_uuid": track.track_uuid,
        "selected_path": track.file_path,
        "score": 0.5,
        "priority": priority,
        "reason": {"source": "test"},
    }


def _create_profile(
    path: Path,
    *,
    classifier_key: str = "focused",
    artifact_dir: Path | None = None,
) -> RhythmLabDatabase:
    database = RhythmLabDatabase(path)
    database.create_profile(
        classifier_key=classifier_key,
        name=classifier_key.replace("_", " ").title(),
        artifact_dir=artifact_dir,
        # Fixtures label a handful of tracks; the product default is 100 per class.
        training_min_labels=2,
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
            {"key": "review", "name": "Review", "role": "review"},
        ],
    )
    return RhythmLabDatabase(path, classifier_key=classifier_key)


def _train_artifact(
    artifact_dir: Path,
    *,
    classifier_key: str = "focused",
    progress_callback=None,
):
    matrix = np.asarray(
        [[float(index % 2), float((index + 1) % 2)] for index in range(20)],
        dtype=np.float32,
    )
    labels = ["yes" if index % 2 == 0 else "no" for index in range(20)]
    return train_feature_set(
        matrix,
        labels,
        feature_names=["mulan:0", "mulan:1"],
        feature_set="mulan",
        artifact_dir=artifact_dir,
        label_order=["yes", "no"],
        positive_label="yes",
        artifact_prefix=classifier_key.replace("_", "-"),
        classifier_key=classifier_key,
        progress_callback=progress_callback,
    )


def test_training_progress_reports_lifecycle() -> None:
    progress = TrainingProgress()

    assert progress.snapshot("focused")["status"] == "idle"
    progress.start("focused", operation="train-refresh", stage="Preparing")
    progress.update("focused", stage="Cross-validation fold 1/5", percent=31)
    running = progress.snapshot("focused")
    assert running == {
        "operation": "train-refresh",
        "status": "running",
        "stage": "Cross-validation fold 1/5",
        "percent": 31,
        "error": None,
    }

    progress.complete("focused", stage="Complete")
    assert progress.snapshot("focused")["percent"] == 100
    progress.start("focused", operation="train-refresh", stage="Preparing")
    progress.fail("focused", error=RuntimeError("source unavailable"))
    failed = progress.snapshot("focused")
    assert failed["status"] == "failed"
    assert failed["error"] == "source unavailable"


def test_ablation_benchmark_reports_progress_across_profile_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(
        classifier_key="focused",
        name="Focused",
        artifact_dir=tmp_path / "artifacts",
    )
    monkeypatch.setattr(ablation_module, "_selected_profiles", lambda *_args: ([profile], []))
    monkeypatch.setattr(ablation_module, "SourceDatabase", lambda _path: _ReadyFeatureSource())

    def fake_profile_benchmark(*_args, **kwargs):
        assert kwargs["strategy"] == "custom"
        kwargs["progress_callback"]("Cross-validation fold 5/5", 10, 10)
        return {"classifier_key": "focused", "winner": None}

    monkeypatch.setattr(ablation_module, "benchmark_profile_ablation", fake_profile_benchmark)
    events: list[tuple[str, int, int]] = []

    report = ablation_module.run_ablation_benchmark(
        tmp_path / "source.sqlite",
        tmp_path / "labels.sqlite",
        profile_keys=("focused",),
        strategy="custom",
        feature_sets=("mulan",),
        progress_callback=lambda stage, completed, total: events.append((stage, completed, total)),
    )

    assert events[0] == ("Focused: Cross-validation fold 5/5", 10, 11)
    assert events[-1] == ("Benchmark complete", 11, 11)
    assert report["strategy"] == "custom"
    assert report["available_sources"] == ["sonara", "maest", "muq", "mulan", "clap"]
    assert report["planned_runs"] == 1
    assert Path(str(report["output_path"])).parent == profile.artifact_dir


def test_greedy_benchmark_adds_sources_only_beyond_cv_noise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = _create_profile(tmp_path / "lab.sqlite", artifact_dir=tmp_path / "artifacts")
    labels.set_label(_track(1), "yes")
    labels.set_label(_track(2), "no")
    library = _ready_library(tmp_path)
    monkeypatch.setattr(ablation_module, "SourceDatabase", lambda _path: _ReadyFeatureSource(library))
    # (mean, std) per feature set: every round keeps the best strict improvement;
    # the fourth round's only candidate (0.83) does not beat 0.84, so greedy stops
    # there and never enumerates the rest of the grid. The winner is the metric maximum.
    scripted = {
        "sonara": (0.70, 0.02),
        "mulan": (0.60, 0.02),
        "maest": (0.50, 0.02),
        "clap": (0.40, 0.02),
        "sonara+mulan": (0.80, 0.05),
        "sonara+maest": (0.71, 0.02),
        "sonara+clap": (0.65, 0.02),
        "sonara+maest+mulan": (0.84, 0.02),
        "sonara+mulan+clap": (0.82, 0.02),
        "sonara+maest+mulan+clap": (0.83, 0.02),
    }
    trained: list[str] = []

    def fake_train_row(_source, _labels, _tracks, _cache, _profile, _dir, feature_set, **kwargs):
        trained.append(feature_set)
        mean, std = scripted[feature_set]
        return {
            "feature_set": feature_set,
            "status": "trained",
            "trained_rows": 2,
            "skipped_rows": 0,
            "metrics": {"cross_validation": {"macro_f1_mean": mean, "macro_f1_std": std}},
        }

    monkeypatch.setattr(ablation_module, "_train_feature_set_row", fake_train_row)
    monkeypatch.setattr(
        ablation_module,
        "available_feature_sources",
        lambda _states: ("sonara", "mulan", "maest", "clap"),
    )

    report = ablation_module.benchmark_profile_ablation(
        tmp_path / "source.sqlite",
        tmp_path / "lab.sqlite",
        "focused",
        artifact_dir=tmp_path / "artifacts",
        strategy="greedy",
    )

    # Singles run in canonical family order; later rounds add candidates in the
    # order the library lists them, and every set is named canonically.
    assert trained == [
        "sonara",
        "maest",
        "mulan",
        "clap",
        "sonara+mulan",
        "sonara+maest",
        "sonara+clap",
        "sonara+maest+mulan",
        "sonara+mulan+clap",
        "sonara+maest+mulan+clap",
    ]
    assert report["winner"]["feature_set"] == "sonara+maest+mulan"
    assert [row["feature_set"] for row in report["results"]] == trained

    custom = ablation_module.benchmark_profile_ablation(
        tmp_path / "source.sqlite",
        tmp_path / "lab.sqlite",
        "focused",
        artifact_dir=tmp_path / "artifacts",
        strategy="custom",
        feature_sets=("mulan+sonara", "sonara+muq"),
    )

    assert [row["feature_set"] for row in custom["results"]] == ["sonara+mulan", "sonara+muq"]
    assert custom["results"][1]["status"] == "unavailable"
    assert custom["results"][1]["error"] == "MUQ data is not stored in this library"
    assert custom["winner"]["feature_set"] == "sonara+mulan"

    # Layers strategy: one run per layer the library reports.
    assert feature_module.stored_mert_v2_layers(_ReadyFeatureSource(library)) == ()
    layered_source = _ReadyFeatureSource(library)
    layered_source.mert_v2_stored_layers = lambda: (12, 6, 24)  # type: ignore[attr-defined]
    monkeypatch.setattr(ablation_module, "SourceDatabase", lambda _path: layered_source)
    monkeypatch.setattr(ablation_module, "available_feature_sources", lambda _states: ("sonara", "mert_v2"))
    scripted.update({"mert_v2@6": (0.55, 0.02), "mert_v2@12": (0.66, 0.02), "mert_v2": (0.61, 0.02)})
    trained.clear()

    layers = ablation_module.benchmark_profile_ablation(
        tmp_path / "source.sqlite",
        tmp_path / "lab.sqlite",
        "focused",
        artifact_dir=tmp_path / "artifacts",
        strategy="layers",
    )

    assert trained == ["mert_v2@6", "mert_v2@12", "mert_v2"]
    assert layers["winner"]["feature_set"] == "mert_v2@12"
    stale_layer = ablation_module.benchmark_profile_ablation(
        tmp_path / "source.sqlite",
        tmp_path / "lab.sqlite",
        "focused",
        artifact_dir=tmp_path / "artifacts",
        strategy="custom",
        feature_sets=("sonara+mert_v2@3",),
    )
    assert stale_layer["results"][0]["error"] == "MERT_V2 layer 3 is not stored in this library"


class _ConstantClassifier:
    def __init__(self, label: str, *, classes_: list[str]) -> None:
        self.label = label
        self.classes_ = np.asarray(classes_)

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray([self.label] * len(matrix))


def _sonara_features() -> SourceSonaraFeatures:
    values: dict[str, object] = {}
    text_fields = {
        "detected_key_name",
        "detected_key_camelot",
        "predominant_chord",
    }
    vector_lengths = {
        "mfcc_mean": 13,
        "chroma_mean": 12,
        "spectral_contrast_mean": 7,
    }
    for field in fields(SourceSonaraFeatures):
        if field.name in vector_lengths:
            values[field.name] = tuple(
                float(index + 1) for index in range(vector_lengths[field.name])
            )
        elif field.name == "analyzed_at":
            values[field.name] = "2026-07-24T10:00:00.000000Z"
        elif field.name in text_fields:
            values[field.name] = "fixture"
        else:
            values[field.name] = 1.0
    return SourceSonaraFeatures(**values)  # type: ignore[arg-type]


class _FeatureSource:
    def __init__(self) -> None:
        self.track = replace(
            _track(1),
            sonara_features=_sonara_features(),
        )
        self.specifications = {
            family: current_embedding_spec(family)
            for family in ("mulan", "maest", "clap", "muq", "mulan", "mert_v2")
        }
        self.layers: dict[str, int | None] = {}

    def list_tracks(self) -> list[SourceTrack]:
        return [self.track]

    def load_embedding_matrix(
        self,
        family: str,
        *,
        track_ids: object | None = None,
        layer: int | None = None,
    ) -> SourceEmbeddingMatrix:
        self.layers[family] = layer
        specification = self.specifications[family]
        family_value = float(("mulan", "maest", "clap", "muq", "mulan", "mert_v2").index(family) + 2)
        tracks = (
            (self.track,)
            if track_ids is None or self.track.track_id in set(track_ids)  # type: ignore[arg-type]
            else ()
        )
        matrix = np.full(
            (len(tracks), specification.dimension),
            family_value,
            dtype=np.float32,
        )
        matrix.setflags(write=False)
        return SourceEmbeddingMatrix(
            family=family,  # type: ignore[arg-type]
            dimension=specification.dimension,
            normalization=specification.normalization,
            tracks=tracks,
            matrix=matrix,
            not_ready_track_ids=(),
        )


@pytest.mark.parametrize(
    ("feature_set", "expected_sources"),
    (
        ("muq", ("muq",)),
        ("sonara+muq", ("sonara", "muq")),
        ("mulan+muq", ("muq", "mulan")),
        (
            "sonara+mulan+maest+clap+muq",
            ("sonara", "maest", "muq", "mulan", "clap"),
        ),
        (
            "sonara+mert_v2+maest+clap+muq+mulan",
            ("sonara", "maest", "mert_v2", "muq", "mulan", "clap"),
        ),
    ),
)
def test_muq_feature_sets_extract_current_structural_dimensions(
    feature_set: str,
    expected_sources: tuple[str, ...],
) -> None:
    source = _FeatureSource()

    result = build_feature_matrix(
        source,  # type: ignore[arg-type]
        feature_set,
        labels_by_identity={str(source.track.content_key): "yes"},
    )

    assert tuple(result.source_dimensions) == expected_sources
    assert result.matrix.shape == (1, len(result.feature_names))
    if "sonara" in expected_sources:
        sonara_count = len(SONARA_SCALAR_FIELDS) + sum(SONARA_VECTOR_FIELDS.values())
        assert result.feature_names[: len(SONARA_SCALAR_FIELDS)] == [
            f"sonara:{field}" for field in SONARA_SCALAR_FIELDS
        ]
        assert sum(name.startswith("sonara:") for name in result.feature_names) == (
            sonara_count
        )
    for family in ("mulan", "maest", "clap", "muq", "mulan"):
        expected_count = (
            source.specifications[family].dimension
            if family in expected_sources
            else 0
        )
        names = [
            name for name in result.feature_names if name.startswith(f"{family}:")
        ]
        assert names == [f"{family}:{index}" for index in range(expected_count)]
    if "muq" in expected_sources:
        assert result.matrix[0, result.feature_names.index("muq:0")] == pytest.approx(
            5.0
        )


def test_recipe_readiness_requires_only_selected_current_sources() -> None:
    states = {
        source: SourceFeatureState(
            status="current",
            reason=None,
        )
        for source in ("sonara", "mulan", "maest", "clap")
    }
    states["muq"] = SourceFeatureState(
        status="missing",
        reason="MuQ vectors are missing.",
    )

    sonara_mulan_maest = feature_recipe_readiness("sonara+mulan+maest", states)
    muq = feature_recipe_readiness("muq", states)
    sonara_muq = feature_recipe_readiness("sonara+muq", states)

    assert sonara_mulan_maest["required_sources"] == ["sonara", "maest", "mulan"]
    assert sonara_mulan_maest["ready"] is True
    assert muq["ready"] is False
    assert muq["blocking"] == [
        {
            "source": "muq",
            "status": "missing",
            "reason": "MuQ vectors are missing.",
        }
    ]
    assert sonara_muq["ready"] is False
    mert_v2 = feature_recipe_readiness("mert_v2", states)
    assert mert_v2["required_sources"] == ["mert_v2"]
    assert mert_v2["ready"] is False
    assert mert_v2["blocking"][0]["source"] == "mert_v2"
    states["mert_v2"] = SourceFeatureState(status="current", reason=None)
    assert feature_recipe_readiness("mert_v2", states)["ready"] is True

    # Recipes are plain source sets: any order in, canonical order out, mert_v2 included.
    assert canonical_feature_set(("mert_v2", "maest", "sonara")) == "sonara+maest+mert_v2"
    assert feature_sources("MERT_V2+sonara") == ("sonara", "mert_v2")
    assert feature_recipe_readiness("mert_v2+sonara", states)["required_sources"] == ["sonara", "mert_v2"]
    with pytest.raises(ValueError, match="Duplicate feature source"):
        canonical_feature_set(("sonara", "sonara"))

    # MERT-v2 layer token: bare = stored default layer 24; other layers are their own source.
    assert canonical_feature_set(("mert_v2@24",)) == "mert_v2"
    assert feature_sources("MERT_V2@12+sonara") == ("sonara", "mert_v2@12")
    assert feature_sources("mert_v2+mert_v2@6+mert_v2@12") == ("mert_v2@6", "mert_v2@12", "mert_v2")
    for invalid in ("mulan@12", "mert_v2@0", "mert_v2@x", "mert_v2@012", "mert_v2+mert_v2@24"):
        with pytest.raises(ValueError):
            feature_sources(invalid)
    layered = feature_recipe_readiness("mert_v2@12", states)
    assert layered["required_sources"] == ["mert_v2@12"]
    assert layered["ready"] is True
    source = _FeatureSource()
    identity = {str(source.track.content_key): "yes"}
    at_12 = build_feature_matrix(source, "mert_v2@12+sonara", labels_by_identity=identity)  # type: ignore[arg-type]
    assert source.layers == {"mert_v2": 12}
    assert at_12.feature_names[-1024:] == [f"mert_v2@12:{index}" for index in range(1024)]
    assert dict(at_12.source_dimensions) == {"sonara": len(SONARA_FEATURE_NAMES), "mert_v2@12": 1024}
    assert artifact_feature_compatibility(feature_set="sonara+mert_v2@12", feature_names=at_12.feature_names) == (True, None)
    assert artifact_feature_compatibility(feature_set="sonara+mert_v2", feature_names=at_12.feature_names)[0] is False
    default = build_feature_matrix(source, "mert_v2", labels_by_identity=identity)  # type: ignore[arg-type]
    assert source.layers == {"mert_v2": None}
    assert default.feature_names[:2] == ["mert_v2:0", "mert_v2:1"]

    # Compatibility is order-agnostic: artifacts trained under an older family
    # order keep their own contiguous, complete blocks, and prediction follows them.
    sonara_block = [name for name in at_12.feature_names if name.startswith("sonara:")]
    layer_block = [name for name in at_12.feature_names if name.startswith("mert_v2@12:")]
    old_order = [*layer_block, *sonara_block]
    assert artifact_feature_compatibility(feature_set="sonara+mert_v2@12", feature_names=old_order) == (True, None)
    interleaved = [*layer_block[:1], *sonara_block, *layer_block[1:]]
    assert "interleave" in str(artifact_feature_compatibility(feature_set="sonara+mert_v2@12", feature_names=interleaved)[1])
    assert "embedding dimension" in str(artifact_feature_compatibility(feature_set="sonara+mert_v2@12", feature_names=[*layer_block[:-1], *sonara_block])[1])
    reordered = build_feature_matrix(source, "sonara+mert_v2@12", labels_by_identity=identity, expected_feature_names=old_order)  # type: ignore[arg-type]
    assert reordered.feature_names == old_order
    np.testing.assert_array_equal(reordered.matrix[0, : len(layer_block)], at_12.matrix[0, -len(layer_block) :])
    np.testing.assert_array_equal(reordered.matrix[0, len(layer_block) :], at_12.matrix[0, : len(sonara_block)])
    with pytest.raises(ValueError, match="do not match current source dimensions"):
        build_feature_matrix(source, "sonara+mert_v2@12", labels_by_identity=identity, expected_feature_names=old_order[:-1])  # type: ignore[arg-type]

    available = available_feature_sources(states)
    assert available == ("sonara", "maest", "mert_v2", "mulan", "clap")
    assert default_feature_set(available) == "sonara+maest+mert_v2+mulan+clap"
    assert default_feature_set(()) is None

    plan = ablation_module.benchmark_plan
    count = ablation_module.planned_run_count
    assert plan(available, "singles") == available
    assert plan(available, "singles+all") == (*available, "sonara+maest+mert_v2+mulan+clap")
    assert plan(("mulan",), "singles+all") == ("mulan",)
    assert plan(available, "greedy") == available
    full = plan(available, "full")
    assert full[0] == "sonara+maest+mert_v2+mulan+clap"
    assert len(full) == len(set(full)) == 2 ** len(available) - 1
    assert plan(available, "custom", ("mert_v2+sonara", "clap")) == ("sonara+mert_v2", "clap")
    with pytest.raises(ValueError, match="MUQ data is not stored"):
        plan(available, "custom", ("sonara+muq",))
    assert count(available, "singles") == 5
    assert count(available, "singles+all") == 6
    assert count(available, "full") == 31
    assert count(available, "greedy") == 15
    assert count((), "singles+all") == 0

    # Layers come from the library, never from a constant; plans only use stored ones.
    layers = (6, 24, 12)
    assert plan(available, "layers", mert_v2_layers=layers) == ("mert_v2@6", "mert_v2@12", "mert_v2")
    assert count(available, "layers", mert_v2_layers=layers) == 3
    assert plan(available, "layers+all", mert_v2_layers=layers) == (
        "mert_v2@6",
        "mert_v2@12",
        "mert_v2",
        "sonara+maest+mert_v2@6+mulan+clap",
        "sonara+maest+mert_v2@12+mulan+clap",
        "sonara+maest+mert_v2+mulan+clap",
    )
    assert plan(("mert_v2",), "layers+all", mert_v2_layers=(24,)) == ("mert_v2",)
    assert plan(available, "custom", ("sonara+mert_v2@12",), mert_v2_layers=layers) == ("sonara+mert_v2@12",)
    with pytest.raises(ValueError, match="MERT_V2 layer 12 is not stored"):
        plan(available, "custom", ("sonara+mert_v2@12",), mert_v2_layers=(24,))
    with pytest.raises(ValueError, match="MERT_V2 data is not stored"):
        plan(("sonara", "mulan"), "layers", mert_v2_layers=layers)
    assert "mert_v2@12" not in plan(available, "full", mert_v2_layers=layers)


def test_artifact_with_missing_muq_data_is_not_refreshable_but_stays_promotable() -> None:
    summary = {
        "by_feature": [
            {
                "feature_set": "muq",
                "latest_model": "muq.joblib",
                "feature_names": _embedding_feature_names("muq"),
                "macro_f1_mean": 0.9,
            }
        ],
        "promotion_options": [],
        "latest_promotable": None,
    }

    stale = _bind_artifact_source_readiness(
        summary,
        {
            "muq": SourceFeatureState(
                status="missing",
                reason="MuQ vectors are missing.",
            )
        },
    )

    # Refresh needs the data; promotion only needs a compatible spec.
    assert stale["promotion_options"][0]["source_data_ready"] is False
    assert stale["promotion_options"][0]["source_data_reason"] == (
        "MuQ vectors are missing."
    )
    assert stale["promotion_options"][0]["spec_compatible"] is True
    assert stale["latest_promotable"]["feature_set"] == "muq"

    current = _bind_artifact_source_readiness(
        summary,
        {
            "muq": SourceFeatureState(
                status="current",
                reason=None,
            )
        },
    )

    assert current["promotion_options"][0]["source_data_ready"] is True
    assert current["promotion_options"][0]["source_data_reason"] is None
    assert current["latest_promotable"]["feature_set"] == "muq"


def test_artifact_with_the_previous_sonara_schema_is_not_promotable() -> None:
    summary = {
        "by_feature": [
            {
                "feature_set": "sonara+mulan",
                "latest_model": "sonara-mulan.joblib",
                "feature_names": ["sonara:bpm", "mulan:0"],
                "macro_f1_mean": 0.9,
            }
        ],
        "promotion_options": [],
        "latest_promotable": None,
    }

    current = _bind_artifact_source_readiness(
        summary,
        {
            "sonara": SourceFeatureState(status="current", reason=None),
            "mulan": SourceFeatureState(status="current", reason=None),
        },
    )

    row = current["by_feature"][0]
    assert row["spec_compatible"] is False
    assert row["source_data_ready"] is False
    assert row["spec_reason"] == row["source_data_reason"] == (
        "Artifact was trained with an older SONARA recipe; retrain it."
    )
    assert current["latest_promotable"] is None
    assert tuple(SONARA_FEATURE_NAMES) != ("sonara:bpm",)


def test_current_rhythm_lab_sonara_recipe_is_scoring_supported() -> None:
    assert all(
        resolve_sonara_classifier_feature(name.removeprefix("sonara:")) is not None
        for name in SONARA_FEATURE_NAMES
    )


def test_serve_parser_forwards_expected_source_catalog_uuid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite"
    labels = tmp_path / "labels.sqlite"
    expected_catalog_uuid = "catalog-current"
    args = build_parser().parse_args(
        [
            "serve",
            "--source",
            str(source),
            "--source-catalog-uuid",
            expected_catalog_uuid,
            "--labels",
            str(labels),
            "--host",
            "127.0.0.1",
            "--port",
            "8777",
        ]
    )
    calls: dict[str, object] = {}

    def fake_create_app(
        source_path: Path,
        *,
        labels_db_path: Path,
        source_catalog_uuid: str,
    ) -> object:
        calls["create_app"] = (
            source_path,
            labels_db_path,
            source_catalog_uuid,
        )
        return object()

    def fake_run(app: object, **kwargs: object) -> None:
        calls["run"] = (app, kwargs)

    import uvicorn
    from rhythm_lab import web_app

    monkeypatch.setattr(web_app, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    # A launcher-bound source that does not exist fails before the app is built.
    with pytest.raises(FileNotFoundError, match="catalog-current"):
        args.func(args)
    assert calls == {}

    source.write_bytes(b"")
    args.func(args)

    assert calls["create_app"] == (source, labels, expected_catalog_uuid)
    _, run_kwargs = calls["run"]
    assert run_kwargs["host"] == "127.0.0.1"
    assert run_kwargs["port"] == 8777


_V1_LABELS_DDL = """
    CREATE TABLE classifier_labels (
        classifier_key TEXT NOT NULL,
        catalog_uuid TEXT NOT NULL,
        track_uuid TEXT NOT NULL,
        selected_path TEXT NOT NULL,
        file_size_bytes INTEGER NOT NULL,
        file_modified_ns INTEGER NOT NULL,
        label TEXT NOT NULL,
        note TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(classifier_key, catalog_uuid, track_uuid, selected_path)
    )
"""


def test_explicit_legacy_labels_path_fails_closed_without_mutation(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(_V1_LABELS_DDL)
        connection.execute(
            """
            INSERT INTO classifier_labels (
                classifier_key, catalog_uuid, track_uuid, selected_path,
                file_size_bytes, file_modified_ns, label, note, updated_at
            ) VALUES (
                'legacy-profile', 'catalog-old', 'uuid-7', 'C:/Music/legacy.wav',
                1234, 5678, 'positive', 'preserve me', '2026-07-01T00:00:00Z'
            )
            """
        )
    wal_path = Path(f"{legacy_path}-wal")
    shm_path = Path(f"{legacy_path}-shm")
    wal_path.write_bytes(b"preserved legacy WAL")
    shm_path.write_bytes(b"preserved legacy SHM")
    before = {
        path: path.read_bytes()
        for path in (legacy_path, wal_path, shm_path)
    }

    with pytest.raises(
        RuntimeError,
        match=r"legacy track identity.*migrate-content-identity.*migrate the database",
    ):
        RhythmLabDatabase(legacy_path)

    assert {
        path: path.read_bytes()
        for path in (legacy_path, wal_path, shm_path)
    } == before
    with sqlite3.connect(
        f"file:{legacy_path.as_posix()}?mode=ro&immutable=1",
        uri=True,
    ) as connection:
        rows = connection.execute(
            """
            SELECT classifier_key, catalog_uuid, track_uuid, label, note
            FROM classifier_labels
            """
        ).fetchall()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert rows == [
        (
            "legacy-profile",
            "catalog-old",
            "uuid-7",
            "positive",
            "preserve me",
        )
    ]
    assert tables == {"classifier_labels"}


def test_wal_visible_legacy_schema_is_rejected_before_any_ddl(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    setup = sqlite3.connect(legacy_path)
    try:
        assert setup.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
        setup.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        setup.execute("INSERT INTO sentinel(value) VALUES ('base')")
        setup.commit()
        setup.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        setup.close()

    reader = sqlite3.connect(legacy_path)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT value FROM sentinel").fetchall() == [
            ("base",)
        ]

        writer = sqlite3.connect(legacy_path)
        try:
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute(_V1_LABELS_DDL)
            writer.execute(
                """
                INSERT INTO classifier_labels (
                    classifier_key, catalog_uuid, track_uuid, selected_path,
                    file_size_bytes, file_modified_ns, label
                ) VALUES ('wal-profile', 'catalog-old', 'uuid-21', 'C:/Music/wal.wav', 1, 2, 'positive')
                """
            )
            writer.commit()
        finally:
            writer.close()

        wal_path = Path(f"{legacy_path}-wal")
        shm_path = Path(f"{legacy_path}-shm")
        assert wal_path.stat().st_size > 0
        assert shm_path.stat().st_size > 0
        before = {
            path: path.read_bytes()
            for path in (legacy_path, wal_path)
        }
        shm_size_before = shm_path.stat().st_size

        with pytest.raises(RuntimeError, match="legacy track identity.*migrate-content-identity"):
            RhythmLabDatabase(legacy_path)

        # The SHM file is SQLite's transient WAL index; validation reads may
        # update its read marks. Durable database and WAL bytes must not change.
        assert {
            path: path.read_bytes()
            for path in (legacy_path, wal_path)
        } == before
        assert shm_path.stat().st_size == shm_size_before
        with sqlite3.connect(
            f"file:{legacy_path.as_posix()}?mode=ro",
            uri=True,
        ) as observer:
            tables = {
                str(row[0])
                for row in observer.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            rows = observer.execute(
                "SELECT classifier_key, catalog_uuid, track_uuid, label "
                "FROM classifier_labels"
            ).fetchall()
        assert tables == {"sentinel", "classifier_labels"}
        assert rows == [
            ("wal-profile", "catalog-old", "uuid-21", "positive")
        ]
    finally:
        reader.close()


def test_lab_database_connections_use_wal_and_runtime_pragmas(tmp_path: Path) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")

    with database.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 2
        assert connection.execute("PRAGMA cache_size").fetchone()[0] == -32768


def test_collection_connections_use_wal_and_runtime_pragmas(tmp_path: Path) -> None:
    collections = RhythmLabCollections(tmp_path / "lab.sqlite")

    with collections.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 2
        assert connection.execute("PRAGMA cache_size").fetchone()[0] == -32768


def test_profile_creation_update_archive_and_unique_names(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    profile = focused.get_profile()

    assert profile.training_label_keys == ("yes", "no")
    assert profile.label_keys == ("yes", "no", "review")
    assert profile.training_min_labels == 2
    updated = focused.update_profile(
        "focused",
        name="Focused Updated",
        training_min_added=12,
        training_min_labels=150,
    )
    assert updated.name == "Focused Updated"
    assert updated.training_min_added == 12
    assert updated.training_min_labels == 150
    # The per-class label minimum is an absolute count of at least 2.
    with pytest.raises(ValueError, match="at least 2"):
        focused.update_profile("focused", training_min_labels=1)
    with pytest.raises(ValueError, match="must be an integer"):
        focused.update_profile("focused", training_min_labels="many")  # type: ignore[arg-type]

    root = RhythmLabDatabase(path)
    with pytest.raises(ValueError, match="already exists"):
        root.create_profile(
            classifier_key="duplicate",
            name="focused updated",
            labels=[
                {"key": "up", "name": "Up", "role": "positive"},
                {"key": "down", "name": "Down", "role": "negative"},
            ],
        )
    root.archive_profile("focused")
    assert root.list_profiles() == []
    assert root.list_profiles(include_archived=True)[0].archived_at is not None
    plain = root.create_profile(
        classifier_key="plain",
        name="Plain",
        labels=[
            {"key": "up", "name": "Up", "role": "positive"},
            {"key": "down", "name": "Down", "role": "negative"},
        ],
    )
    assert plain.training_min_labels == 100


def test_multiclass_profile_uses_all_class_labels_for_training(
    tmp_path: Path,
) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")
    profile = database.create_profile(
        classifier_key="mood",
        profile_type="multiclass",
        name="Mood",
        labels=[
            {"key": "bright", "name": "Bright", "role": "class"},
            {"key": "dark", "name": "Dark", "role": "class"},
            {"key": "neutral", "name": "Neutral", "role": "class"},
        ],
    )

    assert profile.training_label_keys == ("bright", "dark", "neutral")


def test_labels_use_current_track_identity_and_remain_profile_scoped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    track = _track(1)
    # The same file scanned into another library: another catalog and uuid,
    # the same fingerprint, hence the same content key.
    elsewhere = replace(track, catalog_uuid="catalog-other", track_uuid="other-1", file_path="D:/copy/1.wav")

    focused.set_label(track, "yes", note="manual")
    other.set_label(track, "no")

    assert focused.label_for_track(track).label == "yes"
    assert other.label_for_track(track).label == "no"
    focused.set_label(elsewhere, "no")
    assert focused.label_counts() == {"no": 1}
    assert focused.label_for_track(track).last_track_uuid == "other-1"
    focused.set_label(track, None)
    assert focused.label_for_track(elsewhere) is None
    assert other.label_for_track(track).label == "no"
    with pytest.raises(ValueError, match="no SONARA fingerprint"):
        focused.set_label(replace(track, content_key=None), "yes")


def test_label_rename_migrates_labels_predictions_and_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    database = _create_profile(path)
    track = _track(1)
    database.set_label(track, "yes")
    database.save_prediction(
        track,
        feature_set="mulan",
        model_artifact="old.joblib",
        label="yes",
        confidence=0.8,
        probabilities={"yes": 0.8, "no": 0.2},
    )
    database.record_training_checkpoint(
        {"yes": 1, "no": 0},
        model_artifact="old.joblib",
    )

    profile = database.rename_label_key("focused", "yes", "positive")

    assert profile.positive_label == "positive"
    assert database.label_counts() == {"positive": 1}
    assert database.predictions()[0]["label"] == "positive"
    assert database.predictions()[0]["probabilities"] == {
        "no": 0.2,
        "positive": 0.8,
    }
    assert database.training_checkpoint()["counts"] == {
        "no": 0,
        "positive": 1,
    }


def test_queue_upsert_state_transitions_and_profile_isolation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    first = _track(1)
    second = _track(2)

    assert focused.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=1), _queue_item(second, priority=2)],
    ) == 2
    assert focused.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=9)],
    ) == 1
    other.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=3)],
    )

    focused_rows = focused.label_queue_items()
    assert [row["content_key"] for row in focused_rows] == [
        first.content_key,
        second.content_key,
    ]
    changed = focused.mark_queue_item(
        int(focused_rows[0]["id"]),
        state="accepted_for_labeling",
    )
    assert changed["state"] == "accepted_for_labeling"
    assert focused.clear_label_queue(state="accepted_for_labeling") == 1
    assert len(focused.label_queue_items()) == 1
    assert len(other.label_queue_items()) == 1


def test_predictions_preserve_precision_and_prune_only_selected_feature(
    tmp_path: Path,
) -> None:
    database = _create_profile(tmp_path / "lab.sqlite")
    track = _track(1)
    database.save_prediction(
        track,
        feature_set="mulan",
        model_artifact="old.joblib",
        label="yes",
        confidence=0.5000000001,
        probabilities={"yes": 0.5000000001, "no": 0.4999999999},
    )
    database.save_prediction(
        track,
        feature_set="mulan",
        model_artifact="new.joblib",
        label="yes",
        confidence=0.75,
        probabilities={"yes": 0.75, "no": 0.25},
    )
    database.save_prediction(
        track,
        feature_set="maest",
        model_artifact="other.joblib",
        label="no",
        confidence=0.9,
        probabilities={"yes": 0.1, "no": 0.9},
    )

    assert database.prune_predictions(
        feature_set="mulan",
        keep_model_artifact="new.joblib",
    ) == 1
    assert {
        (row["feature_set"], row["model_artifact"])
        for row in database.predictions()
    } == {
        ("mulan", "new.joblib"),
        ("maest", "other.joblib"),
    }


def test_profile_delete_is_scoped_to_the_selected_profile(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    focused.set_label(_track(1), "yes")
    other.set_label(_track(2), "no")

    deleted = focused.delete_profile(classifier_key="focused")

    assert deleted.classifier_key == "focused"
    assert RhythmLabDatabase(path).list_profiles()[0].classifier_key == "other"
    assert other.label_counts() == {"no": 1}


def test_training_checkpoint_counts_are_profile_scoped_and_catalog_global(
    tmp_path: Path,
) -> None:
    database = _create_profile(tmp_path / "lab.sqlite", artifact_dir=tmp_path / "artifacts")

    assert database.training_checkpoint() == {
        "counts": {"yes": 0, "no": 0},
        "model_artifact": None,
        "updated_at": None,
    }
    database.record_training_checkpoint(
        {"yes": 12, "no": 9, "ignored": 99},
        model_artifact="model.joblib",
    )

    checkpoint = database.training_checkpoint()
    assert checkpoint["counts"] == {"yes": 12, "no": 9}
    assert checkpoint["model_artifact"] == "model.joblib"
    assert checkpoint["updated_at"] is not None

    # Readiness records and compares the checkpoint against every label of the
    # profile ("total"), not only content sighted in the active library ("current").
    fresh = _create_profile(tmp_path / "fresh.sqlite", artifact_dir=tmp_path / "artifacts")
    for index, label in ((1, "yes"), (2, "yes"), (3, "no"), (4, "no"), (9, "yes")):
        fresh.set_label(_track(index), label)
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    _write_artifact(tmp_path / "artifacts", "focused-mulan-20260101T000000Z.joblib")
    source = _ReadyFeatureSource(_ready_library(tmp_path))  # tracks 1..4 sighted; 9 is not

    readiness = _training_readiness(
        fresh,
        artifact_dir=tmp_path / "artifacts",
        source=source,  # type: ignore[arg-type]
        feature_set="mulan",
    )

    assert readiness["current"] == {"yes": 2, "no": 2}
    assert readiness["total"] == {"yes": 3, "no": 2}
    assert readiness["last_trained"] == {"yes": 3, "no": 2}
    assert fresh.training_checkpoint()["counts"] == {"yes": 3, "no": 2}
    assert readiness["added"] == {"yes": 0, "no": 0}
    fresh.set_label(_track(10), "yes")
    after = _training_readiness(
        fresh,
        artifact_dir=tmp_path / "artifacts",
        source=source,  # type: ignore[arg-type]
        feature_set="mulan",
    )
    assert after["current"] == {"yes": 2, "no": 2}
    assert after["total"] == {"yes": 4, "no": 2}
    assert after["added"] == {"yes": 1, "no": 0}
    assert (after["label_threshold"], after["label_threshold_ready"]) == (2, True)
    assert after["label_threshold_reason"] is None

    # The profile's per-class minimum applies to labels resolvable in the open library.
    fresh.update_profile("focused", training_min_labels=3)
    short = _training_readiness(
        fresh,
        artifact_dir=tmp_path / "artifacts",
        source=source,  # type: ignore[arg-type]
        feature_set="mulan",
    )
    assert (short["label_threshold"], short["label_threshold_ready"], short["ready"]) == (3, False, False)
    assert "at least 3 labels per class" in short["label_threshold_reason"]
    assert "yes — 2 (4 total), no — 2 (2 total)" in short["label_threshold_reason"]
    fresh.update_profile("focused", training_min_labels=2)
    assert _training_readiness(
        fresh,
        artifact_dir=tmp_path / "artifacts",
        source=source,  # type: ignore[arg-type]
        feature_set="mulan",
    )["label_threshold_ready"] is True


def test_train_feature_set_binds_exact_bytes_and_features_to_metrics(
    tmp_path: Path,
) -> None:
    result = _train_artifact(tmp_path / "artifacts")
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))

    assert metrics["artifact_filename"] == result.artifact_path.name
    assert metrics["artifact_hash"] == artifact_sha256(
        result.artifact_path.read_bytes()
    )
    assert metrics["feature_count"] == 2
    assert metrics["feature_names"] == ["mulan:0", "mulan:1"]
    payload = joblib.load(result.artifact_path)
    assert payload["classifier_key"] == "focused"
    assert payload["feature_names"] == ["mulan:0", "mulan:1"]


def test_training_artifact_names_are_collision_safe(tmp_path: Path) -> None:
    first = _train_artifact(tmp_path / "artifacts")
    second = _train_artifact(tmp_path / "artifacts")

    assert first.artifact_path != second.artifact_path
    assert first.metrics_path != second.metrics_path
    assert first.artifact_path.is_file()
    assert second.artifact_path.is_file()
    assert re.search(
        r"-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{8}\.joblib$",
        first.artifact_path.name,
    )


def test_calibration_gate_failure_does_not_write_uncalibrated_artifact(
    tmp_path: Path,
) -> None:
    matrix = np.asarray(
        [[float(index), float(index % 2)] for index in range(20)],
        dtype=np.float32,
    )
    labels = ["yes" if index % 2 == 0 else "no" for index in range(20)]
    artifact_dir = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="usable training rows"):
        train_feature_set(
            matrix,
            labels,
            feature_names=["mulan:0", "mulan:1"],
            feature_set="mulan",
            artifact_dir=artifact_dir,
            label_order=["yes", "no"],
            positive_label="yes",
            artifact_prefix="focused",
            classifier_key="focused",
            calibrate=True,
            source_catalog_uuid="catalog-current",
        )

    assert not list(artifact_dir.glob("*.joblib"))
    assert not list(artifact_dir.glob("*.metrics.json"))


class _RecordingClassifier:
    def fit(self, matrix: np.ndarray, labels: list[str]):
        self.fit_rows = len(matrix)
        self.classes_ = np.asarray(sorted(set(labels)), dtype=object)
        return self

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray([self.classes_[0]] * len(matrix), dtype=object)

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        return np.tile(
            np.full(len(self.classes_), 1.0 / len(self.classes_)),
            (len(matrix), 1),
        )


def test_training_serializes_full_data_model_source_binding_and_block_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        training_module,
        "_make_model",
        lambda random_state, **_kwargs: _RecordingClassifier(),
    )
    matrix = np.asarray(
        [[float(index), 0.0, 1.0, 2.0, 3.0] for index in range(20)],
        dtype=np.float32,
    )
    labels = ["yes" if index % 2 == 0 else "no" for index in range(20)]
    feature_names = [
        "sonara:bpm",
        "mulan:0",
        "mulan:1",
        "mulan:2",
        "mulan:3",
    ]

    result = train_feature_set(
        matrix,
        labels,
        feature_names=feature_names,
        feature_set="sonara+mulan",
        artifact_dir=tmp_path,
        label_order=["yes", "no"],
        positive_label="yes",
        artifact_prefix="focused",
        classifier_key="focused",
        source_catalog_uuid="catalog-current",
        skipped_rows=3,
    )

    payload = joblib.load(result.artifact_path)
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    expected_weights = {
        "sonara": pytest.approx(np.sqrt(5.0 / 2.0)),
        "mulan": pytest.approx(np.sqrt(5.0 / 8.0)),
    }
    assert payload["model"].fit_rows == 20
    assert payload["source_catalog_uuid"] == "catalog-current"
    assert payload["feature_group_weights"] == expected_weights
    assert metrics["source_catalog_uuid"] == "catalog-current"
    assert metrics["feature_group_weights"] == expected_weights
    assert metrics["skipped_rows"] == 3
    assert result.skipped_rows == 3


class _ReadyFeatureSource:
    """Fake source over a real minimal library file, so sightings can sync."""

    catalog_uuid = "catalog-current"

    def __init__(
        self,
        path: Path | None = None,
        *,
        track_count: int = 4,
        missing_embedding_track_ids: frozenset[int] = frozenset(),
    ) -> None:
        self.path = path
        self.track_count = track_count
        self.missing_embedding_track_ids = missing_embedding_track_ids

    def storage_signature(self) -> tuple[tuple[int, int], ...]:
        return ((0, 0), (-1, -1))

    def tracks_by_ids(
        self,
        track_ids: object,
        *,
        required_sources: object = None,
    ) -> dict[int, SourceTrack]:
        return {int(track_id): _track(int(track_id)) for track_id in track_ids}  # type: ignore[union-attr]

    def feature_states(self) -> dict[str, SourceFeatureState]:
        return {
            source: SourceFeatureState(status="current", reason=None)
            for source in ("sonara", "mulan", "maest", "clap", "muq", "mulan")
        }

    def feature_counts(self) -> dict[str, int]:
        return {
            source: self.track_count
            for source in ("sonara", "mulan", "maest", "clap", "muq", "mulan")
        }

    def count_tracks(self) -> int:
        return self.track_count

    def mert_v2_stored_layers(self) -> tuple[int, ...]:
        return ()

    def load_embedding_matrix(
        self,
        family: str,
        *,
        track_ids: object | None = None,
    ) -> SourceEmbeddingMatrix:
        specification = current_embedding_spec(family)
        selected_ids = (
            list(track_ids)  # type: ignore[arg-type]
            if track_ids is not None
            else list(range(1, self.track_count + 1))
        )
        tracks = tuple(
            _track(track_id)
            for track_id in selected_ids
            if track_id not in self.missing_embedding_track_ids
        )
        matrix = np.ones(
            (len(tracks), specification.dimension),
            dtype=np.float32,
        )
        matrix.setflags(write=False)
        return SourceEmbeddingMatrix(
            family=family,  # type: ignore[arg-type]
            dimension=specification.dimension,
            normalization=specification.normalization,
            tracks=tracks,
            matrix=matrix,
            not_ready_track_ids=tuple(
                track_id
                for track_id in selected_ids
                if track_id in self.missing_embedding_track_ids
            ),
        )


def test_explicit_retrain_uses_total_label_sufficiency_not_checkpoint_delta(
    tmp_path: Path,
) -> None:
    labels = _create_profile(tmp_path / "lab.sqlite", artifact_dir=tmp_path / "artifacts")
    labels.set_label(_track(1), "yes")
    labels.set_label(_track(2), "yes")
    labels.set_label(_track(3), "no")
    labels.set_label(_track(4), "no")
    labels.record_training_checkpoint(
        {"yes": 2, "no": 2},
        model_artifact="previous.joblib",
    )

    readiness = _training_readiness(
        labels,
        artifact_dir=tmp_path / "artifacts",
        source=_ReadyFeatureSource(_ready_library(tmp_path)),  # type: ignore[arg-type]
        feature_set="mulan",
    )

    assert readiness["labels_ready"] is True
    assert readiness["ready"] is True
    assert readiness["added"] == {"yes": 0, "no": 0}
    assert readiness["retrain_recommended"] is False
    assert readiness["minimum_training_rows"] == {"yes": 2, "no": 2}
    assert readiness["missing_training_rows"] == {"yes": 0, "no": 0}


def test_training_readiness_uses_only_rows_usable_by_selected_recipe(
    tmp_path: Path,
) -> None:
    labels = _create_profile(
        tmp_path / "lab.sqlite",
        artifact_dir=tmp_path / "artifacts",
    )
    labels.set_label(_track(1), "yes")
    labels.set_label(_track(2), "yes")
    labels.set_label(_track(3), "no")
    labels.set_label(_track(4), "no")

    readiness = _training_readiness(
        labels,
        artifact_dir=tmp_path / "artifacts",
        source=_ReadyFeatureSource(
            _ready_library(tmp_path),
            missing_embedding_track_ids=frozenset({1}),
        ),  # type: ignore[arg-type]
        feature_set="mulan",
    )

    assert readiness["current"] == {"yes": 2, "no": 2}
    assert readiness["usable"] == {"yes": 1, "no": 2}
    assert readiness["unusable"] == {"yes": 1, "no": 0}
    assert readiness["skipped_training_rows"] == 1
    assert readiness["labels_ready"] is False
    assert readiness["ready"] is False
    assert readiness["missing_training_rows"] == {"yes": 1, "no": 0}


def test_cli_training_promotion_and_calibration_default_to_current_recipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = build_parser()
    lab_path = tmp_path / "lab.sqlite"
    labels = _create_profile(lab_path, artifact_dir=tmp_path / "artifacts")
    calibration = parser.parse_args(
        ["calibration-report", "--profile", "focused", "--labels", str(lab_path)]
    )
    source = tmp_path / "library.sqlite"
    promote = parser.parse_args(
        ["promote", "--profile", "focused", "--labels", str(lab_path)]
    )

    # Promote and calibration-report default to the profile's own last recipe:
    # the training checkpoint first, otherwise the newest artifact, else an error.
    assert calibration.feature_set is None
    assert promote.feature_set is None
    with pytest.raises(SystemExit, match="train first or pass --feature-set"):
        calibration.func(calibration)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    older = _write_artifact(artifact_dir, "focused-sonara+mulan-20260101T000000Z.joblib")
    newest = _write_artifact(artifact_dir, "focused-mulan-20260102T000000Z.joblib")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    assert cli_module._profile_feature_set(labels, artifact_dir) == "mulan"
    labels.record_training_checkpoint({"yes": 0, "no": 0}, model_artifact=older)
    assert cli_module._profile_feature_set(labels, artifact_dir) == "sonara+mulan"
    assert newest.exists()

    # `train` defaults to every source the library stores and canonicalizes explicit recipes.
    stored = {"sonara", "mulan", "mert_v2"}
    monkeypatch.setattr(
        cli_module,
        "SourceDatabase",
        lambda path: SimpleNamespace(
            catalog_uuid="catalog-current",
            feature_states=lambda: {
                family: SourceFeatureState(
                    status="current" if family in stored else "missing",
                    reason=None,
                )
                for family in feature_module.SUPPORTED_FEATURE_SOURCES
            },
        ),
    )
    trained: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        cli_module,
        "benchmark_lab_database",
        lambda *args, **kwargs: trained.append(kwargs["feature_sets"]) or {},
    )
    train_args = ["train", "--profile", "focused", "--labels", str(lab_path), "--source", str(source)]
    train = parser.parse_args(train_args)
    assert train.feature_set is None
    train.func(train)
    explicit = parser.parse_args([*train_args, "--feature-set", "mert_v2+sonara"])
    explicit.func(explicit)
    assert trained == [("sonara+mert_v2+mulan",), ("sonara+mert_v2",)]
    invalid = parser.parse_args([*train_args, "--feature-set", "combined"])
    with pytest.raises(ValueError, match="Unsupported feature source"):
        invalid.func(invalid)

    ablation = parser.parse_args(["benchmark-ablation", "--profile", "focused"])
    assert (ablation.strategy, ablation.feature_set) == ("singles+all", None)
    layered = parser.parse_args(["benchmark-ablation", "--profile", "focused", "--strategy", "layers"])
    assert layered.strategy == "layers"
    explicit_layer = parser.parse_args([*train_args, "--feature-set", "mert_v2@12+sonara"])
    explicit_layer.func(explicit_layer)
    assert trained[-1] == ("sonara+mert_v2@12",)

    captured: dict[str, object] = {}

    def fake_promote(*args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "model_path": tmp_path / "model.joblib",
            "metadata_path": tmp_path / "metadata.json",
            "source_artifact": tmp_path / "source.joblib",
        }

    monkeypatch.setattr(cli_module, "promote_profile_model", fake_promote)
    promote.func(promote)

    assert captured["feature_set"] is None
    assert "expected_source_catalog_uuid" not in captured
    assert captured["require_calibration"] is True

    # The content-identity migration is a dry run unless --apply is given.
    migrate = parser.parse_args(["migrate-content-identity", "--library-db", str(source)])
    assert (migrate.lab_db, migrate.apply, migrate.skip_unresolved, migrate.rekey) == (
        cli_module.DEFAULT_LABELS_DB,
        False,
        False,
        False,
    )
    assert migrate.library_db == [source]


def _v1_lab_database(path: Path) -> None:
    """A pre-content-identity lab database with rows in every per-track table."""

    with sqlite3.connect(path) as connection:
        connection.executescript(
            f"""
            CREATE TABLE classifier_profiles (
                classifier_key TEXT PRIMARY KEY,
                profile_type TEXT NOT NULL DEFAULT 'binary',
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                artifact_dir TEXT NOT NULL,
                artifact_prefix TEXT NOT NULL,
                training_min_added INTEGER NOT NULL DEFAULT 50,
                positive_label TEXT NOT NULL,
                negative_label TEXT NOT NULL,
                archived_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE classifier_profile_labels (
                classifier_key TEXT NOT NULL,
                label_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(classifier_key, label_key),
                FOREIGN KEY(classifier_key) REFERENCES classifier_profiles(classifier_key) ON DELETE CASCADE
            );
            {_V1_LABELS_DDL};
            CREATE TABLE classifier_label_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                mode TEXT NOT NULL,
                score REAL,
                priority REAL NOT NULL,
                reason_json TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'suggested',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(classifier_key, catalog_uuid, track_uuid, selected_path, mode)
            );
            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                artist TEXT,
                title TEXT,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(classifier_key, catalog_uuid, track_uuid, selected_path, feature_set, model_artifact)
            );
            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL,
                model_artifact TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE review_collections (
                id INTEGER PRIMARY KEY,
                catalog_uuid TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'manual',
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(id, catalog_uuid)
            );
            CREATE TABLE review_collection_tracks (
                collection_id INTEGER NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                position INTEGER NOT NULL,
                score REAL,
                note TEXT,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(collection_id, catalog_uuid, track_uuid)
            );
            INSERT INTO classifier_profiles(classifier_key, name, artifact_dir, artifact_prefix, positive_label, negative_label)
            VALUES ('focused', 'Focused', 'C:/artifacts/focused', 'focused', 'yes', 'no'),
                   ('other', 'Other', 'C:/artifacts/other', 'other', 'yes', 'no');
            INSERT INTO classifier_profile_labels(classifier_key, label_key, display_name, role, position)
            VALUES ('focused', 'yes', 'Yes', 'positive', 0), ('focused', 'no', 'No', 'negative', 1),
                   ('other', 'yes', 'Yes', 'positive', 0), ('other', 'no', 'No', 'negative', 1);
            INSERT INTO classifier_labels(classifier_key, catalog_uuid, track_uuid, selected_path, file_size_bytes, file_modified_ns, label, note, updated_at)
            VALUES ('focused', 'catalog-a', 'a1', 'C:/music/1.wav', 1, 2, 'yes', '', '2026-01-01 00:00:00'),
                   ('focused', 'catalog-b', 'b1', 'E:/music/1.wav', 1, 2, 'no', 'later', '2026-02-01 00:00:00'),
                   ('focused', 'catalog-a', 'a2', 'C:/music/2.wav', 1, 2, 'yes', NULL, '2026-01-02 00:00:00'),
                   ('other', 'catalog-a', 'a1', 'C:/music/1.wav', 1, 2, 'yes', '', '2026-01-01 00:00:00'),
                   ('other', 'catalog-b', 'b1', 'E:/music/1.wav', 1, 2, 'yes', 'keep', '2026-03-01 00:00:00');
            INSERT INTO classifier_predictions(classifier_key, catalog_uuid, track_uuid, selected_path, feature_set, model_artifact, label, confidence, probabilities_json)
            VALUES ('focused', 'catalog-a', 'a1', 'C:/music/1.wav', 'mulan', 'old.joblib', 'yes', 0.9, '{{"yes": 0.9, "no": 0.1}}'),
                   ('focused', 'catalog-b', 'b1', 'E:/music/1.wav', 'mulan', 'old.joblib', 'yes', 0.8, '{{"yes": 0.8, "no": 0.2}}');
            INSERT INTO classifier_label_queue(classifier_key, catalog_uuid, track_uuid, selected_path, mode, priority, reason_json)
            VALUES ('focused', 'catalog-a', 'a2', 'C:/music/2.wav', 'uncertainty', 1.0, '{{}}');
            INSERT INTO classifier_training_checkpoints(classifier_key, counts_json, model_artifact)
            VALUES ('focused', '{{"yes": 2, "no": 1}}', 'old.joblib');
            """
        )


def test_content_identity_migration_dry_run_backup_dedupe_and_conflicts(
    tmp_path: Path,
) -> None:
    lab_path = tmp_path / "rhythm_lab.sqlite"
    _v1_lab_database(lab_path)
    # Content 1 lives in both libraries under different uuids; 2 only in A, 3 only in B.
    library_a = _fake_library(tmp_path / "a.sqlite", [(1, "a1", 1), (2, "a2", 2)], catalog_uuid="catalog-a")
    library_b = _fake_library(tmp_path / "b.sqlite", [(1, "b1", 1), (2, "b3", 3)], catalog_uuid="catalog-b")
    parser = build_parser()
    common = ["migrate-content-identity", "--lab-db", str(lab_path), "--library-db", str(library_a), "--library-db", str(library_b)]
    before_bytes = lab_path.read_bytes()

    dry = parser.parse_args([*common, "--report", str(tmp_path / "dry.json")])
    dry.func(dry)

    report = json.loads((tmp_path / "dry.json").read_text(encoding="utf-8"))
    assert report["mode"] == "dry-run"
    assert (report["labels"]["before"], report["labels"]["after"]) == (5, 3)
    assert report["labels"]["merged_groups"] == 2
    assert report["labels"]["unresolved"] == []
    [conflict] = report["labels"]["conflicts"]
    assert (conflict["classifier_key"], conflict["content_key"]) == ("focused", _content_key(1))
    assert conflict["winner"]["label"] == "no"
    assert [loser["label"] for loser in conflict["losers"]] == ["yes"]
    assert report["after"]["classifier_predictions"] == 0
    assert report["after"]["track_sightings"] == 4
    assert lab_path.read_bytes() == before_bytes
    assert not list(tmp_path.glob("rhythm_lab.sqlite.content-identity-backup-*"))
    with pytest.raises(SystemExit, match="already exists"):
        dry.func(dry)

    applied = parser.parse_args([*common, "--apply", "--report", str(tmp_path / "apply.json")])
    applied.func(applied)

    [backup_dir] = tmp_path.glob("rhythm_lab.sqlite.content-identity-backup-*")
    assert (backup_dir / "rhythm_lab.sqlite").read_bytes() == before_bytes
    report = json.loads((tmp_path / "apply.json").read_text(encoding="utf-8"))
    assert report["integrity"] == {"foreign_key_check": [], "integrity_check": "ok"}
    assert report["after"]["classifier_labels"] == 3
    assert report["after"]["classifier_label_queue"] == 0
    assert report["after"]["classifier_training_checkpoints"] == 0
    with sqlite3.connect(lab_path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        # Profiles carry over in place and gain the current DDL's column.
        assert "training_min_labels" in {
            row[1] for row in connection.execute("PRAGMA table_info(classifier_profiles)")
        }
    focused = RhythmLabDatabase(lab_path, classifier_key="focused")
    other = focused.scoped("other")
    assert focused.get_profile().training_min_labels == 100
    assert focused.label_counts() == {"no": 1, "yes": 1}
    assert focused.label_counts(catalog_uuid="catalog-a") == {"no": 1, "yes": 1}
    assert focused.label_counts(catalog_uuid="catalog-b") == {"no": 1}
    winner = focused.label_for_track(_track(1))
    assert (winner.label, winner.note, winner.last_track_uuid) == ("no", "later", "b1")
    merged = other.label_for_track(_track(1))
    assert (merged.label, merged.note, merged.updated_at) == ("yes", "keep", "2026-03-01 00:00:00")
    assert focused.predictions() == []
    assert focused.label_queue_items() == []
    assert focused.training_checkpoint()["model_artifact"] is None

    with pytest.raises(SystemExit, match="already uses content identity"):
        applied.func(parser.parse_args([*common, "--apply"]))


def _write_artifact(artifact_dir: Path, name: str) -> Path:
    path = artifact_dir / name
    path.write_bytes(b"artifact")
    return path


def _embedding_feature_names(token: str) -> list[str]:
    family = token.partition("@")[0]
    return [f"{token}:{index}" for index in range(current_embedding_spec(family).dimension)]


def test_artifact_readiness_is_gated_by_feature_spec_not_source_catalog() -> None:
    summary = {
        "by_feature": [
            {
                "feature_set": "mulan",
                "feature_names": _embedding_feature_names("mulan"),
                "source_catalog_uuid": "catalog-old",
                "latest_model": "model.joblib",
                "macro_f1_mean": 0.9,
            },
            {
                "feature_set": "clap",
                "feature_names": ["clap:0"],
                "source_catalog_uuid": "catalog-current",
                "latest_model": "short.joblib",
                "macro_f1_mean": 0.8,
            },
            {
                "feature_set": "mert_v2@12",
                "feature_names": _embedding_feature_names("mert_v2@12"),
                "source_catalog_uuid": "catalog-current",
                "latest_model": "layer12.joblib",
                "macro_f1_mean": 0.7,
            },
        ],
        "promotion_options": [],
    }
    states = {
        source: SourceFeatureState(status="current", reason=None)
        for source in ("mulan", "clap", "mert_v2")
    }

    bound = _bind_artifact_source_readiness(summary, states)

    by_feature = {row["feature_set"]: row for row in bound["by_feature"]}
    # Another library's artifact with full current feature names is usable.
    other_catalog = by_feature["mulan"]
    assert other_catalog["spec_compatible"] is True
    assert other_catalog["source_data_ready"] is True
    assert other_catalog["source_catalog_uuid"] == "catalog-old"
    # A truncated embedding block is neither promotable nor refreshable.
    short = by_feature["clap"]
    assert short["spec_compatible"] is False
    assert short["source_data_ready"] is False
    assert "current embedding dimension" in short["spec_reason"]
    # Non-default MERT-v2 layers train and predict in the lab but never promote.
    layered = by_feature["mert_v2@12"]
    assert layered["spec_compatible"] is False
    assert layered["spec_reason"] == (
        "The main app scores only MERT-v2 layer 24; layer 12 artifacts stay in the lab"
    )
    assert layered["source_data_ready"] is True
    assert bound["latest_promotable"]["feature_set"] == "mulan"


def test_promotion_requires_matching_profile_and_calibration_gate(
    tmp_path: Path,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_profile(lab_path)
    result = _train_artifact(tmp_path / "artifacts")

    with pytest.raises(PromotionError, match="calibration is required"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=result.artifact_path,
            target_root=tmp_path / "promoted",
            require_calibration=True,
        )

    payload = joblib.load(result.artifact_path)
    payload["classifier_key"] = "other"
    joblib.dump(payload, result.artifact_path)
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    metrics["artifact_hash"] = artifact_sha256(result.artifact_path.read_bytes())
    result.metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(PromotionError, match="Expected artifact for profile"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=result.artifact_path,
            target_root=tmp_path / "promoted",
        )


def test_predict_probabilities_preserves_high_confidence_precision() -> None:
    model = _ConstantClassifier("yes", classes_=["no", "yes"])

    probabilities = _predict_probabilities(
        model,
        np.zeros((2, 2), dtype=np.float32),
        ["no", "yes"],
    )

    assert probabilities == [
        {"no": 0.0, "yes": 1.0},
        {"no": 0.0, "yes": 1.0},
    ]


def test_artifact_cleanup_keeps_recent_and_protected_models(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    models = [
        root / f"focused-mulan-20260724T10000{index}Z.joblib"
        for index in range(4)
    ]
    for index, model in enumerate(models):
        model.write_bytes(f"model-{index}".encode())
        model.with_suffix(".metrics.json").write_text("{}", encoding="utf-8")

    result = cleanup_training_artifacts(
        root,
        protected_artifact=models[0],
        artifact_prefix="focused",
        keep_joblib_per_feature=2,
        keep_metrics_per_feature=2,
    )

    assert result == {"deleted_joblib": 1, "deleted_metrics": 2}
    assert models[0].exists()
    assert not models[1].exists()
    assert models[2].exists()
    assert models[3].exists()

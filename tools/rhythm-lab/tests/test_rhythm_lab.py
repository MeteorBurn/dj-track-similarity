from __future__ import annotations

import json
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
from dj_track_similarity.library_models import AnalysisCoverage  # noqa: E402
from dj_track_similarity.sonara_classifier_features import (  # noqa: E402
    resolve_sonara_classifier_feature,
)
from dj_track_similarity.rhythm_lab_collections import (  # noqa: E402
    RhythmLabCollections,
    default_rhythm_lab_labels_path,
)
from rhythm_lab import cli as cli_module  # noqa: E402
from rhythm_lab import ablation as ablation_module  # noqa: E402
from rhythm_lab import features as feature_module  # noqa: E402
from rhythm_lab import training as training_module  # noqa: E402
from rhythm_lab.artifact_io import artifact_sha256  # noqa: E402
from rhythm_lab.cli import (  # noqa: E402
    DEFAULT_LABELS_DB,
    PromotionError,
    build_parser,
    promote_profile_model,
)
from rhythm_lab.features import (  # noqa: E402
    ABLATION_FEATURE_SETS,
    DEFAULT_TRAINING_FEATURE_SET,
    FEATURE_RECIPE_OPTIONS,
    SONARA_FEATURE_NAMES,
    SONARA_SCALAR_FIELDS,
    SONARA_VECTOR_FIELDS,
    build_feature_matrix,
    feature_recipe_readiness,
    feature_sources,
)
from rhythm_lab.lab_db import (  # noqa: E402
    RhythmLabDatabase,
    TrackIdentity,
    _default_artifact_dir,
)
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
    _artifact_summary,
    _bind_artifact_source_readiness,
    _training_readiness,
    cleanup_training_artifacts,
    create_app,
)


def _track(index: int, *, generation: int = 1) -> SourceTrack:
    return SourceTrack(
        catalog_uuid="catalog-current",
        track_id=index,
        track_uuid=f"track-{index}",
        content_generation=generation,
        file_path=f"C:/music/{index}.wav",
        file_size_bytes=1_000 + index,
        file_modified_ns=2_000 + index,
        audio_duration_seconds=180.0,
        file_tags=None,
        liked=False,
        sonara_features=None,
        maest=None,
        analysis_coverage=AnalysisCoverage(),
    )


def _identity(track: SourceTrack) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=track.catalog_uuid,
        track_uuid=track.track_uuid,
        content_generation=track.content_generation,
        file_path=track.file_path,
    )


def _queue_item(track: SourceTrack, *, priority: float) -> dict[str, object]:
    return {
        "catalog_uuid": track.catalog_uuid,
        "track_uuid": track.track_uuid,
        "content_generation": track.content_generation,
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
        feature_names=["mert:0", "mert:1"],
        feature_set="mert",
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


@pytest.mark.parametrize("operation", ("refresh", "promote"))
def test_workflow_progress_reports_refresh_and_promotion(operation: str) -> None:
    progress = TrainingProgress()

    progress.start("focused", operation=operation, stage="Preparing")
    progress.update("focused", stage="Working", percent=62)
    progress.complete("focused", stage="Complete")

    assert progress.snapshot("focused") == {
        "operation": operation,
        "status": "completed",
        "stage": "Complete",
        "percent": 100,
        "error": None,
    }


def test_training_progress_callback_reports_holdout_cross_validation_and_artifact(
    tmp_path: Path,
) -> None:
    events: list[tuple[str, int, int]] = []

    _train_artifact(
        tmp_path / "artifacts",
        progress_callback=lambda stage, completed, total: events.append((stage, completed, total)),
    )

    assert events[0] == ("Fitting holdout model", 0, 8)
    assert any(stage == "Cross-validation fold 5/5" for stage, _, _ in events)
    assert events[-1] == ("Model artifact saved", 8, 8)


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

    def fake_profile_benchmark(*_args, **kwargs):
        kwargs["progress_callback"]("Cross-validation fold 5/5", 10, 10)
        return {"classifier_key": "focused", "winner": None}

    monkeypatch.setattr(ablation_module, "benchmark_profile_ablation", fake_profile_benchmark)
    events: list[tuple[str, int, int]] = []

    report = ablation_module.run_ablation_benchmark(
        tmp_path / "source.sqlite",
        tmp_path / "labels.sqlite",
        profile_keys=("focused",),
        feature_sets=("mert",),
        progress_callback=lambda stage, completed, total: events.append((stage, completed, total)),
    )

    assert events[0] == ("Focused: Cross-validation fold 5/5", 10, 11)
    assert events[-1] == ("Benchmark complete", 11, 11)
    assert Path(str(report["output_path"])).parent == profile.artifact_dir


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
            for family in ("mert", "maest", "clap", "muq")
        }

    def list_tracks(self) -> list[SourceTrack]:
        return [self.track]

    def load_embedding_matrix(
        self,
        family: str,
        *,
        track_ids: object | None = None,
    ) -> SourceEmbeddingMatrix:
        specification = self.specifications[family]
        family_value = float(("mert", "maest", "clap", "muq").index(family) + 2)
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
        ("mert+muq", ("mert", "muq")),
        (
            "sonara+mert+maest+clap+muq",
            ("sonara", "mert", "maest", "clap", "muq"),
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
        labels_by_identity={_identity(source.track): "yes"},
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
    for family in ("mert", "maest", "clap", "muq"):
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


def test_ablation_selection_uses_the_single_current_sonara_source() -> None:
    assert ABLATION_FEATURE_SETS == FEATURE_RECIPE_OPTIONS
    assert len(ABLATION_FEATURE_SETS) == 31
    assert all("sonara2" not in feature_set for feature_set in ABLATION_FEATURE_SETS)
    assert all("sonara2" not in feature_set for feature_set in FEATURE_RECIPE_OPTIONS)
    assert all(feature_set != "combined" for feature_set in (*ABLATION_FEATURE_SETS, *FEATURE_RECIPE_OPTIONS))
    with pytest.raises(ValueError, match="Unsupported feature source: sonara2"):
        feature_sources("sonara2")
    with pytest.raises(ValueError, match="Unsupported feature source: combined"):
        feature_sources("combined")


def test_recipe_readiness_requires_only_selected_current_sources() -> None:
    states = {
        source: SourceFeatureState(
            status="current",
            reason=None,
        )
        for source in ("sonara", "mert", "maest", "clap")
    }
    states["muq"] = SourceFeatureState(
        status="missing",
        reason="MuQ vectors are missing.",
    )

    sonara_mert_maest = feature_recipe_readiness("sonara+mert+maest", states)
    muq = feature_recipe_readiness("muq", states)
    sonara_muq = feature_recipe_readiness("sonara+muq", states)

    assert sonara_mert_maest["required_sources"] == ["sonara", "mert", "maest"]
    assert sonara_mert_maest["ready"] is True
    assert muq["ready"] is False
    assert muq["blocking"] == [
        {
            "source": "muq",
            "status": "missing",
            "reason": "MuQ vectors are missing.",
        }
    ]
    assert sonara_muq["ready"] is False
    assert FEATURE_RECIPE_OPTIONS[0] == DEFAULT_TRAINING_FEATURE_SET
    assert "sonara+mert+maest" in FEATURE_RECIPE_OPTIONS
    assert "combined" not in FEATURE_RECIPE_OPTIONS
    assert "muq" in FEATURE_RECIPE_OPTIONS
    assert "clap+muq" in FEATURE_RECIPE_OPTIONS
    assert "sonara+mert+maest+clap+muq" in FEATURE_RECIPE_OPTIONS


def test_artifact_with_missing_muq_data_is_not_promotable() -> None:
    summary = {
        "by_feature": [
            {
                "feature_set": "muq",
                "latest_model": "muq.joblib",
                "feature_names": ["muq:0", "muq:1"],
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

    assert stale["promotion_options"][0]["source_data_ready"] is False
    assert stale["promotion_options"][0]["source_data_reason"] == (
        "MuQ vectors are missing."
    )
    assert stale["latest_promotable"] is None

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
                "feature_set": "sonara+mert",
                "latest_model": "sonara-mert.joblib",
                "feature_names": ["sonara:bpm", "mert:0"],
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
            "mert": SourceFeatureState(status="current", reason=None),
        },
    )

    row = current["by_feature"][0]
    assert row["source_data_ready"] is False
    assert row["source_data_reason"] == (
        "Artifact was trained with an older SONARA recipe; retrain it."
    )
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

    args.func(args)

    assert calls["create_app"] == (source, labels, expected_catalog_uuid)
    _, run_kwargs = calls["run"]
    assert run_kwargs["host"] == "127.0.0.1"
    assert run_kwargs["port"] == 8777


def test_default_labels_path_is_shared_stable_path() -> None:
    args = build_parser().parse_args(["serve"])

    assert DEFAULT_LABELS_DB == default_rhythm_lab_labels_path()
    assert args.labels == DEFAULT_LABELS_DB
    assert args.labels.parent.name == "database"
    assert args.labels.name == "rhythm_lab.sqlite"


def test_explicit_legacy_labels_path_fails_closed_without_mutation(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                size INTEGER,
                mtime REAL,
                label TEXT NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (classifier_key, source_track_id, path)
            );
            INSERT INTO classifier_labels (
                classifier_key,
                source_track_id,
                path,
                size,
                mtime,
                label,
                note,
                updated_at
            ) VALUES (
                'legacy-profile',
                7,
                'C:/Music/legacy.wav',
                1234,
                5678.0,
                'positive',
                'preserve me',
                '2026-07-01T00:00:00Z'
            );
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
        match=r"legacy track identity.*migrate the database",
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
            SELECT classifier_key, source_track_id, path, label, note
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
            7,
            "C:/Music/legacy.wav",
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
            writer.execute(
                """
                CREATE TABLE classifier_labels (
                    classifier_key TEXT NOT NULL,
                    source_track_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    label TEXT NOT NULL
                )
                """
            )
            writer.execute(
                """
                INSERT INTO classifier_labels (
                    classifier_key,
                    source_track_id,
                    path,
                    label
                ) VALUES ('wal-profile', 21, 'C:/Music/wal.wav', 'positive')
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

        with pytest.raises(RuntimeError, match="legacy track identity"):
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
                "SELECT classifier_key, source_track_id, path, label "
                "FROM classifier_labels"
            ).fetchall()
        assert tables == {"sentinel", "classifier_labels"}
        assert rows == [
            ("wal-profile", 21, "C:/Music/wal.wav", "positive")
        ]
    finally:
        reader.close()


def test_web_app_creates_current_schema_at_stable_labels_path(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / DEFAULT_LABELS_DB.name

    app = create_app(labels_db_path=labels_path)

    assert app.title == "Rhythm Lab"
    assert labels_path.name == "rhythm_lab.sqlite"
    assert labels_path.exists()
    with sqlite3.connect(
        f"file:{labels_path.as_posix()}?mode=ro",
        uri=True,
    ) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(classifier_labels)"
            ).fetchall()
        }
    assert {
        "catalog_uuid",
        "track_uuid",
        "content_generation",
        "selected_path",
    }.issubset(columns)


def test_lab_database_starts_without_implicit_profiles(tmp_path: Path) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")

    assert database.list_profiles() == []
    with pytest.raises(ValueError, match="profile key is required"):
        database.get_profile()


def test_profile_default_artifact_directory_uses_profiles_root() -> None:
    assert _default_artifact_dir("voice_presence").parts[-2:] == (
        "profiles",
        "voice-presence",
    )


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


def test_lab_database_ensures_prediction_hot_path_indexes(tmp_path: Path) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")

    with database.connect() as connection:
        index_names = {
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = 'classifier_predictions'
                """
            ).fetchall()
        }
        assert "idx_classifier_predictions_latest" in index_names
        assert "idx_classifier_predictions_model" in index_names

        latest_plan = [
            str(row["detail"])
            for row in connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT rowid
                FROM classifier_predictions
                WHERE classifier_key = ?
                  AND catalog_uuid = ?
                ORDER BY track_uuid, content_generation, selected_path,
                         updated_at DESC, model_artifact DESC
                """,
                ("focused", "catalog-a"),
            ).fetchall()
        ]
        assert any("idx_classifier_predictions_latest" in detail for detail in latest_plan)

        model_plan = [
            str(row["detail"])
            for row in connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT rowid
                FROM classifier_predictions
                WHERE classifier_key = ?
                  AND feature_set = ?
                  AND model_artifact = ?
                """,
                ("focused", "mert", "model.joblib"),
            ).fetchall()
        ]
        assert any("idx_classifier_predictions_model" in detail for detail in model_plan)


def test_list_profiles_loads_profile_payloads_with_one_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "lab.sqlite"
    root = RhythmLabDatabase(path)
    _create_profile(path)
    root.create_profile(
        classifier_key="other",
        name="Other",
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
        ],
    )
    calls = 0
    real_connect = root.connect

    def recording_connect() -> sqlite3.Connection:
        nonlocal calls
        calls += 1
        return real_connect()

    monkeypatch.setattr(root, "connect", recording_connect)

    profiles = root.list_profiles()

    assert [profile.classifier_key for profile in profiles] == ["focused", "other"]
    assert calls == 1


def test_profile_creation_update_archive_and_unique_names(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    profile = focused.get_profile()

    assert profile.training_label_keys == ("yes", "no")
    assert profile.label_keys == ("yes", "no", "review")
    updated = focused.update_profile(
        "focused",
        name="Focused Updated",
        training_min_added=12,
    )
    assert updated.name == "Focused Updated"
    assert updated.training_min_added == 12

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

    focused.set_label(track, "yes", note="manual")
    other.set_label(track, "no")

    assert focused.label_for_track(_identity(track)).label == "yes"
    assert other.label_for_track(_identity(track)).label == "no"
    assert focused.label_for_track(
        _identity(_track(1, generation=2))
    ) is None

    focused.set_label(track, "no")
    assert focused.label_counts() == {"no": 1}
    focused.set_label(track, None)
    assert focused.label_for_track(_identity(track)) is None
    assert other.label_for_track(_identity(track)).label == "no"


def test_label_rename_migrates_labels_predictions_and_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    database = _create_profile(path)
    track = _track(1)
    database.set_label(track, "yes")
    database.save_prediction(
        track,
        feature_set="mert",
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
    assert [row["track_uuid"] for row in focused_rows] == [
        first.track_uuid,
        second.track_uuid,
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
        feature_set="mert",
        model_artifact="old.joblib",
        label="yes",
        confidence=0.5000000001,
        probabilities={"yes": 0.5000000001, "no": 0.4999999999},
    )
    database.save_prediction(
        track,
        feature_set="mert",
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
        feature_set="mert",
        keep_model_artifact="new.joblib",
    ) == 1
    assert {
        (row["feature_set"], row["model_artifact"])
        for row in database.predictions()
    } == {
        ("mert", "new.joblib"),
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


def test_training_checkpoint_tracks_only_current_profile_labels(
    tmp_path: Path,
) -> None:
    database = _create_profile(tmp_path / "lab.sqlite")

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
    assert metrics["feature_names"] == ["mert:0", "mert:1"]
    payload = joblib.load(result.artifact_path)
    assert payload["classifier_key"] == "focused"
    assert payload["feature_names"] == ["mert:0", "mert:1"]


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
            feature_names=["mert:0", "mert:1"],
            feature_set="mert",
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


def test_default_training_recipe_uses_current_sonara_and_all_embeddings() -> None:
    expected = "sonara+mert+maest+clap+muq"

    assert getattr(feature_module, "DEFAULT_TRAINING_FEATURE_SET", None) == expected
    assert expected in FEATURE_RECIPE_OPTIONS
    assert expected in ABLATION_FEATURE_SETS
    assert feature_sources(expected) == (
        "sonara",
        "mert",
        "maest",
        "clap",
        "muq",
    )


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
        "mert:0",
        "mert:1",
        "mert:2",
        "mert:3",
    ]

    result = train_feature_set(
        matrix,
        labels,
        feature_names=feature_names,
        feature_set="sonara+mert",
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
        "mert": pytest.approx(np.sqrt(5.0 / 8.0)),
    }
    assert payload["model"].fit_rows == 20
    assert payload["source_catalog_uuid"] == "catalog-current"
    assert payload["feature_group_weights"] == expected_weights
    assert metrics["source_catalog_uuid"] == "catalog-current"
    assert metrics["feature_group_weights"] == expected_weights
    assert metrics["skipped_rows"] == 3
    assert result.skipped_rows == 3


class _ReadyFeatureSource:
    catalog_uuid = "catalog-current"

    def __init__(
        self,
        *,
        track_count: int = 4,
        missing_embedding_track_ids: frozenset[int] = frozenset(),
    ) -> None:
        self.track_count = track_count
        self.missing_embedding_track_ids = missing_embedding_track_ids

    def feature_states(self) -> dict[str, SourceFeatureState]:
        return {
            source: SourceFeatureState(status="current", reason=None)
            for source in ("sonara", "mert", "maest", "clap", "muq")
        }

    def feature_counts(self) -> dict[str, int]:
        return {
            source: self.track_count
            for source in ("sonara", "mert", "maest", "clap", "muq")
        }

    def tracks_by_identities(
        self,
        identities: object,
    ) -> list[SourceTrack]:
        requested = list(identities)  # type: ignore[arg-type]
        return [
            _track(int(identity.track_uuid.rsplit("-", 1)[-1]))
            for identity in requested
            if identity.catalog_uuid == self.catalog_uuid
        ]

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
        source=_ReadyFeatureSource(),  # type: ignore[arg-type]
        feature_set="mert",
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
            missing_embedding_track_ids=frozenset({1}),
        ),  # type: ignore[arg-type]
        feature_set="mert",
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
    train = parser.parse_args(["train", "--profile", "focused"])
    calibration = parser.parse_args(
        ["calibration-report", "--profile", "focused"]
    )
    source = tmp_path / "library.sqlite"
    promote = parser.parse_args(
        [
            "promote",
            "--profile",
            "focused",
            "--source",
            str(source),
        ]
    )

    assert train.feature_set == DEFAULT_TRAINING_FEATURE_SET
    assert calibration.feature_set == DEFAULT_TRAINING_FEATURE_SET
    assert promote.feature_set == DEFAULT_TRAINING_FEATURE_SET

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli_module,
        "SourceDatabase",
        lambda path: SimpleNamespace(catalog_uuid="catalog-current"),
    )

    def fake_promote(*args: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "model_path": tmp_path / "model.joblib",
            "metadata_path": tmp_path / "metadata.json",
            "source_artifact": tmp_path / "source.joblib",
        }

    monkeypatch.setattr(cli_module, "promote_profile_model", fake_promote)
    promote.func(promote)

    assert captured["feature_set"] == DEFAULT_TRAINING_FEATURE_SET
    assert captured["expected_source_catalog_uuid"] == "catalog-current"
    assert captured["require_calibration"] is True


def test_artifact_readiness_rejects_a_different_source_catalog() -> None:
    summary = {
        "by_feature": [
            {
                "feature_set": "mert",
                "feature_names": ["mert:0"],
                "source_catalog_uuid": "catalog-old",
                "latest_model": "model.joblib",
            }
        ],
        "promotion_options": [],
    }
    states = {"mert": SourceFeatureState(status="current", reason=None)}

    rebound = _bind_artifact_source_readiness(
        summary,
        states,
        active_catalog_uuid="catalog-current",
    )

    option = rebound["promotion_options"][0]
    assert option["source_data_ready"] is False
    assert "catalog-old" in option["source_data_reason"]
    assert "catalog-current" in option["source_data_reason"]


def test_artifact_summary_surfaces_latest_calibrated_artifact(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    uncalibrated = artifact_dir / "focused-mert-20260807T100000Z.joblib"
    calibrated = artifact_dir / "focused-mert-20260807T110000Z.joblib"
    for artifact, calibration in (
        (uncalibrated, {"status": "uncalibrated", "method": None}),
        (calibrated, {"status": "calibrated", "method": "sigmoid"}),
    ):
        artifact.write_bytes(artifact.name.encode("utf-8"))
        artifact.with_suffix(".metrics.json").write_text(
            json.dumps(
                {
                    "feature_set": "mert",
                    "feature_names": ["mert:0"],
                    "source_catalog_uuid": "catalog-current",
                    "created_at": artifact.stem.rsplit("-", 1)[-1],
                    "production_calibration": calibration,
                }
            ),
            encoding="utf-8",
        )

    summary = _artifact_summary(artifact_dir, "focused")

    option = summary["promotion_options"][0]
    assert option["latest_model"] == str(calibrated)
    assert option["calibration_status"] == "calibrated"
    assert option["calibration_method"] == "sigmoid"


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
        root / f"focused-mert-20260724T10000{index}Z.joblib"
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

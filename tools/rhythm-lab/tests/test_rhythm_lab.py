from __future__ import annotations

import json
from dataclasses import fields, replace
from itertools import combinations
from pathlib import Path
import sqlite3
import sys

import joblib
import numpy as np
import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.analysis_models import current_embedding_spec  # noqa: E402
from dj_track_similarity.library_models import AnalysisCoverage  # noqa: E402
from dj_track_similarity.rhythm_lab_collections import (  # noqa: E402
    default_rhythm_lab_labels_path,
)
from rhythm_lab.artifact_io import artifact_sha256  # noqa: E402
from rhythm_lab.cli import (  # noqa: E402
    DEFAULT_LABELS_DB,
    PromotionError,
    build_parser,
    promote_profile_model,
)
from rhythm_lab.features import (  # noqa: E402
    ABLATION_FEATURE_SETS,
    FEATURE_RECIPE_OPTIONS,
    FEATURE_SETS,
    SONARA_SCALAR_FIELDS,
    SONARA_VECTOR_FIELDS,
    build_feature_matrix,
    feature_recipe_readiness,
    feature_sources,
)
from rhythm_lab.lab_db import RhythmLabDatabase, TrackIdentity  # noqa: E402
from rhythm_lab.predictions import _predict_probabilities  # noqa: E402
from rhythm_lab.source_db import (  # noqa: E402
    SourceEmbeddingMatrix,
    SourceFeatureState,
    SourceSonaraFeatures,
    SourceTrack,
)
from rhythm_lab.training import train_feature_set  # noqa: E402
from rhythm_lab.web_app import (  # noqa: E402
    _bind_artifact_source_readiness,
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
    )


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

    def load_embedding_matrix(self, family: str) -> SourceEmbeddingMatrix:
        specification = self.specifications[family]
        family_value = float(("mert", "maest", "clap", "muq").index(family) + 2)
        matrix = np.full((1, specification.dimension), family_value, dtype=np.float32)
        matrix.setflags(write=False)
        return SourceEmbeddingMatrix(
            family=family,  # type: ignore[arg-type]
            dimension=specification.dimension,
            normalization=specification.normalization,
            tracks=(self.track,),
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


def test_muq_defaults_preserve_legacy_combined_and_ablation_selection() -> None:
    legacy_ablation = tuple(
        "combined" if sources == ("sonara", "mert", "maest") else "+".join(sources)
        for sonara_source in ("", "sonara", "sonara2", "sonara2vocal")
        for size in range(0, 4)
        for embedding_sources in combinations(("mert", "maest", "clap"), size)
        if sonara_source or embedding_sources
        for sources in (
            ((sonara_source,) if sonara_source else ()) + embedding_sources,
        )
    )

    assert feature_sources("combined") == ("sonara", "mert", "maest")
    assert FEATURE_SETS == ("sonara", "mert", "maest", "muq", "combined")
    assert ABLATION_FEATURE_SETS[: len(legacy_ablation)] == legacy_ablation
    assert ABLATION_FEATURE_SETS[len(legacy_ablation) :] == (
        "muq",
        "sonara+muq",
        "mert+muq",
        "sonara+mert+maest+clap+muq",
    )


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

    combined = feature_recipe_readiness("combined", states)
    muq = feature_recipe_readiness("muq", states)
    sonara_muq = feature_recipe_readiness("sonara+muq", states)

    assert combined["required_sources"] == ["sonara", "mert", "maest"]
    assert combined["ready"] is True
    assert muq["ready"] is False
    assert muq["blocking"] == [
        {
            "source": "muq",
            "status": "missing",
            "reason": "MuQ vectors are missing.",
        }
    ]
    assert sonara_muq["ready"] is False
    assert FEATURE_RECIPE_OPTIONS[0] == "combined"
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


def test_default_labels_path_is_shared_greenfield_current_path() -> None:
    args = build_parser().parse_args(["serve"])

    assert DEFAULT_LABELS_DB == default_rhythm_lab_labels_path()
    assert args.labels == DEFAULT_LABELS_DB
    assert args.labels.name == "rhythm_lab_v7.sqlite"
    assert args.labels.name != "rhythm_lab.sqlite"


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
        match=r"rhythm_lab_v7\.sqlite.*label_transfer",
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


def test_web_app_uses_separate_current_labels_without_touching_legacy(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(
            "CREATE TABLE classifier_labels(source_track_id INTEGER, path TEXT)"
        )
        connection.execute(
            "INSERT INTO classifier_labels(source_track_id, path) VALUES (9, 'legacy.wav')"
        )
    legacy_before = legacy_path.read_bytes()
    labels_path = tmp_path / DEFAULT_LABELS_DB.name

    app = create_app(labels_db_path=labels_path)

    assert app.title == "Rhythm Lab"
    assert labels_path.exists()
    assert legacy_path.read_bytes() == legacy_before
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

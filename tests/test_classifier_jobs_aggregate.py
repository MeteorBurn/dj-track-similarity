from pathlib import Path

import numpy as np

from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import ClassifierRequirements
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_features import sonara_analysis_signatures_for_outputs


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={})


def _sonara(db: LibraryDatabase, track_id: int) -> None:
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128.0}},
        analysis_signature=sonara_analysis_signatures_for_outputs(["core"])["core"],
    )


def _embedding(db: LibraryDatabase, track_id: int, key: str) -> None:
    db.save_embedding(track_id, np.asarray([0.1, 0.2], dtype=np.float32), f"fake-{key}", embedding_key=key)


def _requirement(key: str, inputs: tuple[str, ...], model_id: str | None = None) -> ClassifierRequirements:
    return ClassifierRequirements(
        classifier_key=key,
        model_path=Path(f"{key}.joblib"),
        model_id=model_id or f"{key}-v2",
        feature_set="+".join(inputs),
        feature_names=tuple("sonara:bpm" if source == "sonara" else f"{source}:0" for source in inputs),
        required_inputs=inputs,
        sonara_analysis_signature=(
            sonara_analysis_signatures_for_outputs(["core"])["core"] if "sonara" in inputs else None
        ),
    )


class FakeScorer:
    manifest_warnings = ()

    def __init__(self, db: LibraryDatabase, key: str, model_id: str, feature_set: str) -> None:
        self.db = db
        self.key = key
        self.model_id = model_id
        self.feature_set = feature_set
        self.model_name = key

    def score_track(self, track):
        return {"positive": 0.8, "negative": 0.2}

    def save_score(self, track, probabilities) -> None:
        self.db.save_classifier_score(
            track.id,
            classifier=self.key,
            score=probabilities["positive"],
            label="positive",
            confidence=probabilities["positive"],
            probabilities=probabilities,
            feature_set=self.feature_set,
            model_id=self.model_id,
        )


def test_manifest_specific_readiness_filters_before_aggregate_total(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    all_ready = _track(db, tmp_path, "all.wav")
    sonara_only = _track(db, tmp_path, "sonara.wav")
    mert_only = _track(db, tmp_path, "mert.wav")
    _track(db, tmp_path, "none.wav")
    for track_id in (all_ready, sonara_only):
        _sonara(db, track_id)
    for track_id in (all_ready, mert_only):
        _embedding(db, track_id, "mert")
    requirements = {
        "sonara_only": _requirement("sonara_only", ("sonara",)),
        "mert_only": _requirement("mert_only", ("mert",)),
        "combined": _requirement("combined", ("sonara", "mert")),
    }

    manager = ClassifierJobManager(
        db,
        requirements_loader=requirements.__getitem__,
        scorer_factory=lambda key, path: FakeScorer(db, key, requirements[key].model_id, requirements[key].feature_set),
    )
    job_id = manager.create_job(classifiers=list(requirements))
    queued = manager.get(job_id)

    assert queued.total == 5
    assert queued.not_ready == 7
    assert queued.events[0].message == "CLASSIFIERS queued · profiles 3"
    assert queued.readiness["sonara_only"] == {"candidates": 4, "ready": 2, "not_ready": 2, "selected": 2}
    assert queued.readiness["combined"] == {"candidates": 4, "ready": 1, "not_ready": 3, "selected": 1}

    status = manager.run_job(job_id)
    assert status.state == "completed"
    assert status.analyzed == status.processed == 5
    assert [progress.analyzed for progress in status.model_progress.values()] == [2, 2, 1]


def test_aggregate_limit_caps_pairs_across_the_classifier_stage(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ("one.wav", "two.wav"):
        track_id = _track(db, tmp_path, name)
        _embedding(db, track_id, "mert")
    requirements = {
        key: _requirement(key, ("mert",))
        for key in ("first", "second")
    }
    manager = ClassifierJobManager(db, requirements_loader=requirements.__getitem__)

    job_id = manager.create_job(classifiers=list(requirements), limit=2)
    status = manager.get(job_id)

    assert status.total == 2
    assert status.readiness["first"]["selected"] == 2
    assert status.readiness["second"]["selected"] == 0


def test_stale_model_id_is_candidate_but_current_score_is_not(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    stale = _track(db, tmp_path, "stale.wav")
    current = _track(db, tmp_path, "current.wav")
    for track_id in (stale, current):
        _embedding(db, track_id, "mert")
    for track_id, model_id in ((stale, "old-model"), (current, "mert-only-v2")):
        db.save_classifier_score(
            track_id,
            classifier="mert_only",
            score=0.5,
            label="positive",
            confidence=0.5,
            probabilities={"positive": 0.5},
            feature_set="mert",
            model_id=model_id,
        )
    requirement = _requirement("mert_only", ("mert",), model_id="mert-only-v2")
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda key: requirement,
        scorer_factory=lambda key, path: FakeScorer(db, key, requirement.model_id, requirement.feature_set),
    )

    job_id = manager.create_job(classifiers=["mert_only"])
    assert manager.get(job_id).total == 1
    status = manager.run_job(job_id)

    assert status.analyzed == 1
    assert db.classifier_score(stale, "mert_only")["model_id"] == "mert-only-v2"
    assert db.classifier_score(current, "mert_only")["model_id"] == "mert-only-v2"


def test_classifier_job_never_decodes_audio_and_not_ready_is_not_failure(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "not-ready.wav")
    requirement = _requirement("combined", ("sonara", "mert"))
    manager = ClassifierJobManager(db, requirements_loader=lambda key: requirement)

    job_id = manager.create_job(classifiers=["combined"])
    status = manager.run_job(job_id)

    assert status.state == "completed"
    assert status.total == status.failed == status.processed == 0
    assert status.not_ready == 1


def test_missing_manifest_sonara_field_is_not_ready_before_job_total(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "missing-vocalness.wav")
    _sonara(db, track_id)
    base = _requirement("vocalness", ("sonara",))
    requirement = ClassifierRequirements(
        **{**base.__dict__, "feature_names": ("sonara:bpm", "sonara:vocalness")}
    )
    manager = ClassifierJobManager(db, requirements_loader=lambda key: requirement)

    job_id = manager.create_job(classifiers=["vocalness"])
    status = manager.run_job(job_id)

    assert status.total == status.processed == status.failed == 0
    assert status.not_ready == 1


def test_classifier_readiness_counts_in_one_query_without_materializing_tracks(tmp_path: Path) -> None:
    class CountingDatabase(LibraryDatabase):
        connect_calls = 0

        def connect(self):
            self.connect_calls += 1
            return super().connect()

        def list_classifier_candidates(self, *args, **kwargs):
            raise AssertionError("readiness must not materialize candidate tracks")

    db = CountingDatabase(tmp_path / "library.sqlite")
    ready_id = _track(db, tmp_path, "ready.wav")
    _track(db, tmp_path, "not-ready.wav")
    _sonara(db, ready_id)
    requirement = _requirement("sonara_only", ("sonara",))
    db.connect_calls = 0

    counts = db.classifier_candidate_readiness(
        "sonara_only",
        model_id=requirement.model_id,
        required_inputs=requirement.required_inputs,
        sonara_signature=requirement.sonara_analysis_signature,
        feature_names=requirement.feature_names,
    )

    assert counts == {"candidates": 2, "ready": 1, "not_ready": 1}
    assert db.connect_calls == 1

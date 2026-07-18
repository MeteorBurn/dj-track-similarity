from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema import SONARA_CLASSIFIER_REVISION_SETTING_KEY
from dj_track_similarity.sonara_contract import (
    SONARA_ANALYSIS_SIGNATURE_KEY,
    build_sonara_analysis_signature,
    expected_sonara_analysis_signature,
    feature_set_uses_sonara,
    sonara_analysis_signature_id,
    sonara_analysis_signature_errors,
    sonara_analysis_signatures_match,
)


def test_analysis_signature_is_deterministic_and_sorts_requested_profile() -> None:
    provenance = {
        "package_version": "0.2.4",
        "schema_version": 3,
        "mode": "playlist",
        "sample_rate": 22_050,
    }

    first = build_sonara_analysis_signature(
        requested_features=["vocalness", "bpm", "bpm", "structure"],
        provenance=provenance,
    )
    second = build_sonara_analysis_signature(
        requested_features=["structure", "bpm", "vocalness"],
        provenance=provenance,
    )

    assert first == second
    assert first["requested_features"] == ["bpm", "structure", "vocalness"]
    assert first["bpm_range"] == [79, 192]
    assert first["project_feature_revision"] == 1
    assert str(first["signature_id"]).startswith("sha256:")
    assert sonara_analysis_signature_errors(first) == ()


def test_analysis_signature_rejects_stale_contract_and_tampered_digest() -> None:
    signature = expected_sonara_analysis_signature([])
    stale = {**signature, "sonara_version": "0.2.3"}
    tampered = {**signature, "requested_features": ["vocalness"]}

    assert any("sonara_version" in error for error in sonara_analysis_signature_errors(stale))
    assert any("signature_id" in error for error in sonara_analysis_signature_errors(tampered))
    assert not sonara_analysis_signatures_match(signature, stale)


def test_sonara_feature_set_detection_covers_variants_and_combined() -> None:
    assert feature_set_uses_sonara("sonara")
    assert feature_set_uses_sonara("sonara2vocal+maest+clap")
    assert feature_set_uses_sonara("sonara_custom+mert")
    assert feature_set_uses_sonara("combined")
    assert not feature_set_uses_sonara("mert+maest+clap")


def test_profile_signature_mismatch_makes_sonara_analysis_candidate_stale(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "track.wav")
    base_signature = expected_sonara_analysis_signature([])
    full_signature = expected_sonara_analysis_signature(["structure", "vocalness"])
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128.0}},
        analysis_signature=base_signature,
    )

    assert db.list_analysis_candidates(
        ["sonara"],
        expected_sonara_signature=base_signature,
    ) == []
    stale = db.list_analysis_candidates(
        ["sonara"],
        expected_sonara_signature=full_signature,
    )

    assert [(candidate.id, candidate.missing_models, candidate.analyses) for candidate in stale] == [
        (track_id, ("sonara",), ()),
    ]


def test_scheduler_rejects_tampered_or_featureless_rows_even_with_expected_signature_id(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    tampered_id = _track(db, tmp_path, "tampered.wav")
    featureless_id = _track(db, tmp_path, "featureless.wav")
    signature = expected_sonara_analysis_signature([])
    for track_id in (tampered_id, featureless_id):
        db.save_sonara_features(track_id, {"bpm": {"value": 128.0}}, analysis_signature=signature)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE tracks
            SET metadata_json = json_set(
                metadata_json,
                '$.sonara_analysis_signature.sonara_version',
                '0.2.3'
            )
            WHERE id = ?
            """,
            (tampered_id,),
        )
        connection.execute(
            "UPDATE tracks SET metadata_json = json_remove(metadata_json, '$.sonara_features') WHERE id = ?",
            (featureless_id,),
        )

    stale = db.list_analysis_candidates(["sonara"], expected_sonara_signature=signature)

    assert [(candidate.id, candidate.missing_models, candidate.analyses) for candidate in stale] == [
        (featureless_id, ("sonara",), ()),
        (tampered_id, ("sonara",), ()),
    ]


def test_sonara_hot_rows_include_current_signature_and_exclude_stale_revision(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    current_id = _track(db, tmp_path, "current.wav")
    stale_id = _track(db, tmp_path, "stale.wav")
    current_signature = expected_sonara_analysis_signature([])
    stale_signature = {**current_signature, "project_feature_revision": 0}
    stale_signature["signature_id"] = sonara_analysis_signature_id(stale_signature)
    db.save_sonara_features(
        current_id,
        {"bpm": {"value": 128.0}},
        analysis_signature=current_signature,
    )
    db.save_sonara_features(
        stale_id,
        {"bpm": {"value": 129.0}},
        analysis_signature=stale_signature,
    )

    tracks, feature_rows = db.load_sonara_feature_rows()

    assert [track.id for track in tracks] == [current_id]
    assert feature_rows == [{"bpm": {"value": 128.0}}]


def test_save_sonara_features_replaces_and_deletes_curves_with_the_feature_update(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "track.wav")
    signature = expected_sonara_analysis_signature([])
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128.0}},
        analysis_signature=signature,
        curves={"energy_curve": {"value": [0.1, 0.2]}},
    )

    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 129.0}},
        analysis_signature=signature,
        curves={"energy_curve": {"value": [0.3]}, "downbeats": {"value": [1.0]}},
    )

    assert db.get_track(track_id).metadata["sonara_features"] == {"bpm": {"value": 129.0}}
    assert db.load_sonara_curves(track_id) == {
        "energy_curve": {"value": [0.3]},
        "downbeats": {"value": [1.0]},
    }

    with db.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_sonara_curve_update
            BEFORE UPDATE ON sonara_curves
            BEGIN
                SELECT RAISE(ABORT, 'curve update failed');
            END
            """
        )
    with pytest.raises(sqlite3.IntegrityError, match="curve update failed"):
        db.save_sonara_features(
            track_id,
            {"bpm": {"value": 999.0}},
            analysis_signature=signature,
            curves={"energy_curve": {"value": [9.9]}},
        )

    assert db.get_track(track_id).metadata["sonara_features"] == {"bpm": {"value": 129.0}}
    assert db.load_sonara_curves(track_id) == {
        "energy_curve": {"value": [0.3]},
        "downbeats": {"value": [1.0]},
    }
    with db.connect() as connection:
        connection.execute("DROP TRIGGER fail_sonara_curve_update")

    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 130.0}},
        analysis_signature=signature,
        curves={},
    )

    assert db.get_track(track_id).metadata["sonara_features"] == {"bpm": {"value": 130.0}}
    assert db.load_sonara_curves(track_id) is None


def test_sonara_reanalysis_invalidates_only_dependent_track_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "track.wav")
    signature = expected_sonara_analysis_signature([])
    db.save_sonara_features(track_id, {"bpm": {"value": 128.0}}, analysis_signature=signature)
    _save_score(db, track_id, "sonara_profile", feature_set="combined")
    _save_score(db, track_id, "embedding_profile", feature_set="mert+maest")

    db.save_sonara_features(track_id, {"bpm": {"value": 129.0}}, analysis_signature=signature)

    assert db.classifier_score(track_id, "sonara_profile") is None
    assert db.classifier_score(track_id, "embedding_profile") is not None


def test_sonara_reset_invalidates_dependent_scores_but_preserves_feedback(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_id = _track(db, tmp_path, "first.wav")
    second_id = _track(db, tmp_path, "second.wav")
    signature = expected_sonara_analysis_signature([])
    db.save_sonara_features(first_id, {"bpm": {"value": 128.0}}, analysis_signature=signature)
    _save_score(db, first_id, "sonara_profile", feature_set="sonara2vocal+maest")
    _save_score(db, first_id, "embedding_profile", feature_set="mert+maest")
    _save_pair_feedback(db, first_id, second_id)

    result = db.reset_analysis("sonara")

    assert result["classifier_scores_deleted"] == 1
    assert db.classifier_score(first_id, "sonara_profile") is None
    assert db.classifier_score(first_id, "embedding_profile") is not None
    assert SONARA_ANALYSIS_SIGNATURE_KEY not in db.get_track(first_id).metadata
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_pair_feedback").fetchone()[0] == 1


def test_database_revision_migration_invalidates_old_scores_once_without_feedback_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first_id = _track(db, tmp_path, "first.wav")
    second_id = _track(db, tmp_path, "second.wav")
    _save_score(db, first_id, "old_sonara", feature_set="combined")
    _save_score(db, first_id, "embedding_only", feature_set="mert+maest")
    _save_pair_feedback(db, first_id, second_id)
    with db.connect() as connection:
        connection.execute(
            "DELETE FROM library_settings WHERE key = ?",
            (SONARA_CLASSIFIER_REVISION_SETTING_KEY,),
        )

    migrated = LibraryDatabase(db_path)

    assert migrated.classifier_score(first_id, "old_sonara") is None
    assert migrated.classifier_score(first_id, "embedding_only") is not None
    with migrated.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_pair_feedback").fetchone()[0] == 1
        revision = connection.execute(
            "SELECT value FROM library_settings WHERE key = ?",
            (SONARA_CLASSIFIER_REVISION_SETTING_KEY,),
        ).fetchone()[0]
    assert revision == "1"


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": name})


def _save_score(db: LibraryDatabase, track_id: int, classifier: str, *, feature_set: str) -> None:
    db.save_classifier_score(
        track_id,
        classifier=classifier,
        score=0.75,
        label="high",
        confidence=0.75,
        probabilities={"yes": 0.75, "no": 0.25},
        feature_set=feature_set,
        model_id="test-model",
    )


def _save_pair_feedback(db: LibraryDatabase, first_id: int, second_id: int) -> None:
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO track_pair_feedback (
                seed_track_id, candidate_track_id, rating, reason_tags_json, notes, source
            ) VALUES (?, ?, 3, '[]', 'keep me', 'test')
            """,
            (first_id, second_id),
        )

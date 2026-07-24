from __future__ import annotations

import json
import hashlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys

import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB_ROOT))
MODULE_PATH = LAB_ROOT / "rhythm_lab" / "label_transfer.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "rhythm_lab_label_transfer_test_module",
    MODULE_PATH,
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
LABEL_TRANSFER = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = LABEL_TRANSFER
MODULE_SPEC.loader.exec_module(LABEL_TRANSFER)

build_rebound_bundle = LABEL_TRANSFER.build_rebound_bundle
canonical_path_key = LABEL_TRANSFER.canonical_path_key
export_label_bundle = LABEL_TRANSFER.export_label_bundle
preview_rebind_bundle = LABEL_TRANSFER.preview_rebind_bundle
read_bundle = LABEL_TRANSFER.read_bundle
restore_label_bundle = LABEL_TRANSFER.restore_label_bundle
write_bundle = LABEL_TRANSFER.write_bundle


LAB_SCHEMA = """
CREATE TABLE classifier_profiles (
    classifier_key TEXT PRIMARY KEY,
    profile_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    artifact_dir TEXT NOT NULL,
    artifact_prefix TEXT NOT NULL,
    training_min_added INTEGER NOT NULL,
    positive_label TEXT NOT NULL,
    negative_label TEXT NOT NULL,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE classifier_profile_labels (
    classifier_key TEXT NOT NULL,
    label_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    role TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(classifier_key, label_key)
);
CREATE TABLE classifier_labels (
    classifier_key TEXT NOT NULL,
    source_track_id INTEGER NOT NULL,
    path TEXT,
    size INTEGER,
    mtime REAL,
    label TEXT NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(classifier_key, source_track_id)
);
"""

V7_SCHEMA = """
PRAGMA user_version = 7;
CREATE TABLE library_catalog (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE tracks (
    track_id INTEGER PRIMARY KEY,
    track_uuid TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL UNIQUE,
    file_size_bytes INTEGER NOT NULL,
    file_modified_ns INTEGER NOT NULL,
    content_generation INTEGER NOT NULL
);
"""


def _create_lab_db(
    path: Path,
    *,
    labels: list[
        tuple[str, int, str | None, int | None, float | None, str, str | None, str]
    ],
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(LAB_SCHEMA)
    profiles = [
        (
            "alpha",
            "binary",
            "Alpha",
            "alpha description",
            "artifacts/alpha",
            "alpha",
            50,
            "yes",
            "no",
            None,
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
        ),
        (
            "beta",
            "binary",
            "Beta",
            "beta description",
            "artifacts/beta",
            "beta",
            25,
            "up",
            "down",
            None,
            "2026-01-03T00:00:00Z",
            "2026-01-04T00:00:00Z",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO classifier_profiles(
            classifier_key, profile_type, name, description, artifact_dir,
            artifact_prefix, training_min_added, positive_label, negative_label,
            archived_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        reversed(profiles),
    )
    profile_labels = [
        ("alpha", "yes", "Yes", "", "positive", 0, "2026-01-01", "2026-01-01"),
        ("alpha", "no", "No", "", "negative", 1, "2026-01-01", "2026-01-01"),
        ("beta", "up", "Up", "", "positive", 0, "2026-01-01", "2026-01-01"),
        ("beta", "down", "Down", "", "negative", 1, "2026-01-01", "2026-01-01"),
    ]
    connection.executemany(
        """
        INSERT INTO classifier_profile_labels(
            classifier_key, label_key, display_name, description, role, position,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        reversed(profile_labels),
    )
    connection.executemany(
        """
        INSERT INTO classifier_labels(
            classifier_key, source_track_id, path, size, mtime, label, note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        labels,
    )
    connection.commit()
    connection.close()


def _write_promoted_manifest(
    root: Path,
    *,
    classifier_key: str,
    feature_set: str,
    feature_names: list[str] | None,
    feature_count: int | None = None,
) -> None:
    target = root / classifier_key / "model.json"
    target.parent.mkdir(parents=True)
    payload: dict[str, object] = {
        "classifier_key": classifier_key,
        "feature_count": (
            feature_count if feature_count is not None else len(feature_names or [])
        ),
        "feature_set": feature_set,
        "manifest_version": 2,
    }
    if feature_names is not None:
        payload["feature_names"] = feature_names
    target.write_text(json.dumps(payload), encoding="utf-8")


def _write_promoted_artifact(
    root: Path,
    *,
    classifier_key: str,
    feature_set: str,
    feature_names: list[str],
) -> None:
    from joblib import dump

    dump(
        {
            "classifier_key": classifier_key,
            "feature_names": feature_names,
            "feature_set": feature_set,
            "model": None,
        },
        root / classifier_key / "model.joblib",
    )
    artifact_path = root / classifier_key / "model.joblib"
    artifact_hash = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    manifest_path = root / classifier_key / "model.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hash"] = artifact_hash
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _reseal(bundle: dict[str, object]) -> dict[str, object]:
    payload = json.loads(json.dumps(bundle))
    payload.pop("bundle_sha256", None)
    data = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload["bundle_sha256"] = "sha256:" + hashlib.sha256(data).hexdigest()
    return payload


def _create_v7_core(
    path: Path,
    tracks: list[tuple[int, str, str, int, int, int]],
    *,
    catalog_uuid: str = "catalog-test",
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(V7_SCHEMA)
    connection.execute(
        """
        INSERT INTO library_catalog(singleton_id, catalog_uuid, created_at, updated_at)
        VALUES (1, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        """,
        (catalog_uuid,),
    )
    connection.executemany(
        """
        INSERT INTO tracks(
            track_id, track_uuid, file_path, file_size_bytes,
            file_modified_ns, content_generation
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        tracks,
    )
    connection.commit()
    connection.close()


def _base_labels() -> list[
    tuple[str, int, str | None, int | None, float | None, str, str | None, str]
]:
    return [
        (
            "beta",
            900,
            "C:/Music/B.wav",
            200,
            20.0,
            "up",
            None,
            "2026-02-02T00:00:00Z",
        ),
        (
            "alpha",
            100,
            "C:/Music/A.wav",
            100,
            10.0,
            "yes",
            "manual note",
            "2026-02-01T00:00:00Z",
        ),
        (
            "alpha",
            900,
            "C:/Music/B.wav",
            200,
            20.0,
            "no",
            None,
            "2026-02-03T00:00:00Z",
        ),
    ]


def test_export_is_deterministic_and_preserves_counts_and_feature_order(
    tmp_path: Path,
) -> None:
    first_db = tmp_path / "first.sqlite"
    labels = _base_labels()
    _create_lab_db(first_db, labels=labels)
    promoted = tmp_path / "promoted"
    _write_promoted_manifest(
        promoted,
        classifier_key="alpha",
        feature_set="sonara+mert",
        feature_names=["sonara:bpm", "mert:0", "mert:1"],
    )
    _write_promoted_manifest(
        promoted,
        classifier_key="beta",
        feature_set="maest",
        feature_names=None,
    )

    first = export_label_bundle(first_db, promoted_models_root=promoted)
    second = export_label_bundle(first_db, promoted_models_root=promoted)

    assert first == second
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first["summary"] == {
        "distinct_canonical_path_count": 2,
        "manual_label_count": 3,
        "manual_labels_without_path": 0,
        "profile_count": 2,
        "profile_label_definition_count": 4,
        "promoted_model_count": 2,
        "counts_by_profile": [
            {"classifier_key": "alpha", "count": 2},
            {"classifier_key": "beta", "count": 1},
        ],
        "counts_by_profile_and_class": [
            {"classifier_key": "alpha", "label": "no", "count": 1},
            {"classifier_key": "alpha", "label": "yes", "count": 1},
            {"classifier_key": "beta", "label": "down", "count": 0},
            {"classifier_key": "beta", "label": "up", "count": 1},
        ],
    }
    assert all(
        row["record_id"].startswith("sha256:")
        and isinstance(row["source_track_id"], int)
        for row in first["manual_labels"]
    )
    promoted_by_key = {row["classifier_key"]: row for row in first["promoted_models"]}
    assert promoted_by_key["alpha"]["feature_names"] == [
        "sonara:bpm",
        "mert:0",
        "mert:1",
    ]
    assert promoted_by_key["beta"]["feature_names"] is None
    assert first["source_database"]["read_mode"] == "mode=ro fixed read transaction"
    assert first["source_database"]["database_file_sha256"].startswith("sha256:")
    assert first["source_database"]["schema_sha256"].startswith("sha256:")
    assert first["source_database"]["snapshot_sha256"].startswith("sha256:")

    first_path = tmp_path / "first.bundle.json"
    second_path = tmp_path / "second.bundle.json"
    write_bundle(first, first_path)
    write_bundle(second, second_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    assert read_bundle(first_path) == first


def test_preview_rebind_uses_canonical_path_not_shuffled_numeric_ids(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(
        core_db,
        [
            (71, "uuid-b", "c:\\music\\b.wav", 200, 20_000_000_000, 4),
            (3, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 7),
        ],
    )

    preview = preview_rebind_bundle(bundle, core_db)

    assert preview["summary"] == {
        "ambiguous": 0,
        "changed_at_same_path": 0,
        "strong_match": 3,
        "total": 3,
        "unmatched": 0,
        "weak_match": 0,
    }
    outcomes = preview["outcomes"]
    by_key = {
        (row["source"]["classifier_key"], row["source"]["canonical_path_key"]): row
        for row in outcomes
    }
    alpha_a = by_key[("alpha", canonical_path_key("C:/Music/A.wav"))]
    assert alpha_a["status"] == "strong_match"
    assert alpha_a["target"] == {
        "catalog_uuid": "catalog-test",
        "content_generation": 7,
        "file_modified_ns": 10_000_000_000,
        "file_path": "C:/Music/A.wav",
        "file_size_bytes": 100,
        "track_id": 3,
        "track_uuid": "uuid-a",
    }
    beta_b = by_key[("beta", canonical_path_key("C:/Music/B.wav"))]
    assert beta_b["target"]["track_id"] == 71
    assert beta_b["target"]["track_uuid"] == "uuid-b"
    assert beta_b["target"]["content_generation"] == 4


def test_export_recovers_ordered_feature_names_from_promoted_artifact(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    promoted = tmp_path / "promoted"
    names = ["maest:0", "maest:1", "clap:0"]
    _write_promoted_manifest(
        promoted,
        classifier_key="alpha",
        feature_set="maest+clap",
        feature_names=None,
        feature_count=len(names),
    )
    _write_promoted_artifact(
        promoted,
        classifier_key="alpha",
        feature_set="maest+clap",
        feature_names=names,
    )

    bundle = export_label_bundle(lab_db, promoted_models_root=promoted)

    assert len(bundle["promoted_models"]) == 1
    promoted_model = bundle["promoted_models"][0]
    assert promoted_model["classifier_key"] == "alpha"
    assert promoted_model["feature_count"] == 3
    assert promoted_model["feature_names"] == names
    assert promoted_model["feature_names_source"] == "promoted_model_artifact"
    assert promoted_model["feature_set"] == "maest+clap"
    assert (
        promoted_model["artifact_sha256"] == promoted_model["declared_artifact_sha256"]
    )
    assert promoted_model["manifest_sha256"].startswith("sha256:")


def test_preview_reports_missing_ambiguity_and_metadata_mismatch_without_loss(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    labels = [
        ("alpha", 1, "C:/Music/ok.wav", 10, 1.0, "yes", None, "2026-01-01"),
        ("alpha", 2, "C:/Music/missing.wav", 20, 2.0, "no", None, "2026-01-02"),
        ("alpha", 3, "C:/Music/case.wav", 30, 3.0, "yes", None, "2026-01-03"),
        ("beta", 4, "C:/Music/changed.wav", 40, 4.0, "up", None, "2026-01-04"),
        ("beta", 5, "C:/Music/weak.wav", None, None, "down", None, "2026-01-05"),
    ]
    _create_lab_db(lab_db, labels=labels)
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(
        core_db,
        [
            (4, "uuid-ok", "C:/Music/ok.wav", 10, 1_000_000_000, 1),
            (5, "uuid-case-1", "C:/Music/case.wav", 30, 3_000_000_000, 1),
            (6, "uuid-case-2", "c:/music/CASE.wav", 30, 3_000_000_000, 1),
            (7, "uuid-changed", "C:/Music/changed.wav", 41, 4_000_000_000, 2),
            (8, "uuid-weak", "C:/Music/weak.wav", 50, 5_000_000_000, 3),
        ],
    )

    preview = preview_rebind_bundle(bundle, core_db)

    assert preview["summary"] == {
        "ambiguous": 1,
        "changed_at_same_path": 1,
        "strong_match": 1,
        "total": 5,
        "unmatched": 1,
        "weak_match": 1,
    }
    outcomes = {row["source"]["path"]: row for row in preview["outcomes"]}
    assert outcomes["C:/Music/missing.wav"]["status"] == "unmatched"
    assert outcomes["C:/Music/case.wav"]["status"] == "ambiguous"
    assert len(outcomes["C:/Music/case.wav"]["candidates"]) == 2
    changed = outcomes["C:/Music/changed.wav"]
    assert changed["status"] == "changed_at_same_path"
    assert changed["metadata_mismatches"] == [
        {"actual": 41, "expected": 40, "field": "file_size_bytes"}
    ]
    assert outcomes["C:/Music/weak.wav"]["status"] == "weak_match"

    rebound = build_rebound_bundle(bundle, preview)
    assert rebound["summary"] == {
        "bound": 2,
        "total": 5,
        "unresolved": 3,
        "unresolved_by_status": {
            "ambiguous": 1,
            "changed_at_same_path": 1,
            "unmatched": 1,
        },
    }
    assert len(rebound["labels"]) == 5
    assert sum(row["binding"] is not None for row in rebound["labels"]) == 2
    changed_rebound = next(
        row
        for row in rebound["labels"]
        if row["source"]["path"] == "C:/Music/changed.wav"
    )
    assert changed_rebound["target_snapshot"]["track_uuid"] == "uuid-changed"


def test_rebound_bundle_bytes_and_hash_are_deterministic(tmp_path: Path) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(
        core_db,
        [
            (20, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 9),
            (10, "uuid-b", "C:/Music/B.wav", 200, 20_000_000_000, 8),
        ],
    )
    preview = preview_rebind_bundle(bundle, core_db)

    first = build_rebound_bundle(bundle, preview)
    second = build_rebound_bundle(bundle, preview)
    assert first == second
    first_path = tmp_path / "first.rebound.json"
    second_path = tmp_path / "second.rebound.json"
    write_bundle(first, first_path)
    write_bundle(second, second_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["bundle_sha256"] == second["bundle_sha256"]
    for row in first["labels"]:
        assert row["binding"]["catalog_uuid"] == "catalog-test"
        assert isinstance(row["binding"]["track_id"], int)
        assert isinstance(row["binding"]["track_uuid"], str)
        assert isinstance(row["binding"]["content_generation"], int)


def test_tampered_export_bundle_is_rejected(tmp_path: Path) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    bundle["manual_labels"][0]["label"] = "tampered"
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(core_db, [])

    with pytest.raises(ValueError, match="SHA-256"):
        preview_rebind_bundle(bundle, core_db)


def test_canonical_path_keys_are_lexical_absolute_and_not_casefolded() -> None:
    assert canonical_path_key("C:\\Music\\A\\..\\Track.wav") == (
        canonical_path_key("c:/music/track.WAV")
    )
    assert canonical_path_key("C:/Music/straße.wav") != canonical_path_key(
        "C:/Music/strasse.wav"
    )
    assert canonical_path_key("\\\\Server\\Share\\Folder\\..\\Track.wav") == (
        "//server/share/track.wav"
    )
    with pytest.raises(ValueError, match="relative"):
        canonical_path_key("Music/track.wav")


def test_lab_export_reads_committed_wal_frames_and_closes_snapshot(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    writer = sqlite3.connect(lab_db)
    assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.execute(
        """
        INSERT INTO classifier_labels(
            classifier_key, source_track_id, path, size, mtime, label, note, updated_at
        ) VALUES ('alpha', 1234, 'C:/Music/WAL.wav', 300, 30.0, 'yes', NULL, '2026-03-01')
        """
    )
    writer.commit()
    assert Path(str(lab_db) + "-wal").stat().st_size > 0

    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")

    assert bundle["summary"]["manual_label_count"] == 4
    assert bundle["source_database"]["wal_file_sha256"].startswith("sha256:")
    assert any(
        row["canonical_path_key"] == canonical_path_key("C:/Music/WAL.wav")
        for row in bundle["manual_labels"]
    )
    writer.close()
    renamed = tmp_path / "labels.closed.sqlite"
    lab_db.rename(renamed)
    assert renamed.is_file()


def test_core_preview_reads_committed_wal_frames_and_closes_snapshot(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    labels = [("alpha", 1, "C:/Music/WAL.wav", 300, 30.0, "yes", None, "2026-03-01")]
    _create_lab_db(lab_db, labels=labels)
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(core_db, [])
    writer = sqlite3.connect(core_db)
    assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint = 0")
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.execute(
        """
        INSERT INTO tracks(
            track_id, track_uuid, file_path, file_size_bytes,
            file_modified_ns, content_generation
        ) VALUES (77, 'uuid-wal', 'C:/Music/WAL.wav', 300, 30000000000, 6)
        """
    )
    writer.commit()
    assert Path(str(core_db) + "-wal").stat().st_size > 0

    preview = preview_rebind_bundle(bundle, core_db)

    assert preview["summary"]["strong_match"] == 1
    assert preview["outcomes"][0]["target"]["track_id"] == 77
    assert preview["outcomes"][0]["target"]["content_generation"] == 6
    assert preview["target_database"]["wal_file_sha256"].startswith("sha256:")
    writer.close()
    renamed = tmp_path / "library.closed.sqlite"
    core_db.rename(renamed)
    assert renamed.is_file()


def test_output_is_fail_closed_for_existing_and_input_aliases(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    bundle = export_label_bundle(lab_db, promoted_models_root=tmp_path / "none")
    output = tmp_path / "bundle.json"
    write_bundle(bundle, output, protected_paths=[lab_db])
    original_output = output.read_bytes()

    with pytest.raises(FileExistsError, match="--force"):
        write_bundle(bundle, output, protected_paths=[lab_db])
    write_bundle(bundle, output, force=True, protected_paths=[lab_db])
    assert output.read_bytes() == original_output

    protected = tmp_path / "Input.JSON"
    protected.write_bytes(b"do-not-overwrite")
    with pytest.raises(ValueError, match="input"):
        write_bundle(
            bundle,
            tmp_path / "input.json",
            force=True,
            protected_paths=[protected],
        )
    assert protected.read_bytes() == b"do-not-overwrite"

    with pytest.raises(ValueError, match="SQLite"):
        write_bundle(
            bundle,
            Path(str(lab_db) + "-wal"),
            force=True,
            protected_paths=[lab_db],
        )
    assert lab_db.is_file()

    hardlink_source = tmp_path / "hardlink-source.json"
    hardlink_source.write_bytes(b"hardlink-input")
    hardlink_alias = tmp_path / "hardlink-alias.json"
    os.link(hardlink_source, hardlink_alias)
    with pytest.raises(ValueError, match="alias"):
        write_bundle(
            bundle,
            hardlink_alias,
            force=True,
            protected_paths=[hardlink_source],
        )
    assert hardlink_source.read_bytes() == b"hardlink-input"

    symlink_source = tmp_path / "symlink-source.json"
    symlink_source.write_bytes(b"symlink-input")
    symlink_alias = tmp_path / "symlink-alias.json"
    try:
        symlink_alias.symlink_to(symlink_source)
    except OSError:
        pass
    else:
        with pytest.raises(ValueError, match="input|alias"):
            write_bundle(
                bundle,
                symlink_alias,
                force=True,
                protected_paths=[symlink_source],
            )
        assert symlink_source.read_bytes() == b"symlink-input"


def test_resealed_semantically_invalid_bundles_are_rejected(
    tmp_path: Path,
) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    promoted = tmp_path / "promoted"
    _write_promoted_manifest(
        promoted,
        classifier_key="alpha",
        feature_set="mert",
        feature_names=["mert:0", "mert:1"],
    )
    bundle = export_label_bundle(lab_db, promoted_models_root=promoted)
    core_db = tmp_path / "library.sqlite"
    _create_v7_core(
        core_db,
        [
            (1, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 1),
            (2, "uuid-b", "C:/Music/B.wav", 200, 20_000_000_000, 1),
        ],
    )

    bad_path = json.loads(json.dumps(bundle))
    bad_path["manual_labels"][0]["canonical_path_key"] = "c:/wrong.wav"
    with pytest.raises(ValueError, match="canonical path|canonical order"):
        preview_rebind_bundle(_reseal(bad_path), core_db)

    bad_summary = json.loads(json.dumps(bundle))
    bad_summary["summary"]["manual_label_count"] = 999
    with pytest.raises(ValueError, match="summary"):
        LABEL_TRANSFER._verified_bundle(_reseal(bad_summary))

    bad_feature_count = json.loads(json.dumps(bundle))
    bad_feature_count["promoted_models"][0]["feature_count"] = 99
    with pytest.raises(ValueError, match="feature_count"):
        LABEL_TRANSFER._verified_bundle(_reseal(bad_feature_count))

    bad_order = json.loads(json.dumps(bundle))
    bad_order["manual_labels"].reverse()
    with pytest.raises(ValueError, match="canonical order"):
        LABEL_TRANSFER._verified_bundle(_reseal(bad_order))

    preview = preview_rebind_bundle(bundle, core_db)
    bad_target_catalog = json.loads(json.dumps(preview))
    bad_target_catalog["target_database"]["catalog_uuid"] = "other-catalog"
    with pytest.raises(ValueError, match="catalog identity"):
        build_rebound_bundle(bundle, _reseal(bad_target_catalog))

    bad_catalog = json.loads(json.dumps(preview))
    bad_catalog["outcomes"][0]["target"]["catalog_uuid"] = "other-catalog"
    with pytest.raises(ValueError, match="catalog"):
        build_rebound_bundle(bundle, _reseal(bad_catalog))


def test_artifact_hash_is_verified_before_joblib_fallback(tmp_path: Path) -> None:
    lab_db = tmp_path / "labels.sqlite"
    _create_lab_db(lab_db, labels=_base_labels())
    promoted = tmp_path / "promoted"
    names = ["mert:0", "mert:1"]
    _write_promoted_manifest(
        promoted,
        classifier_key="alpha",
        feature_set="mert",
        feature_names=None,
        feature_count=len(names),
    )
    _write_promoted_artifact(
        promoted,
        classifier_key="alpha",
        feature_set="mert",
        feature_names=names,
    )
    bundle = export_label_bundle(lab_db, promoted_models_root=promoted)
    missing_hashes = json.loads(json.dumps(bundle))
    missing_hashes["promoted_models"][0]["artifact_sha256"] = None
    missing_hashes["promoted_models"][0]["declared_artifact_sha256"] = None
    with pytest.raises(ValueError, match="verified artifact hashes"):
        LABEL_TRANSFER._verified_bundle(_reseal(missing_hashes))

    artifact = promoted / "alpha" / "model.joblib"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        export_label_bundle(lab_db, promoted_models_root=promoted)


def test_lossless_recovery_restore_smoke(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy.sqlite"
    _create_lab_db(
        legacy_db,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                "old",
                "2026-02-01T00:00:00Z",
            ),
            (
                "alpha",
                2,
                "C:/Music/A.wav",
                100,
                10.0,
                "no",
                "new",
                "2026-02-02T00:00:00Z",
            ),
            (
                "alpha",
                3,
                None,
                None,
                None,
                "yes",
                "no path",
                "2026-02-03T00:00:00Z",
            ),
        ],
    )
    exported = export_label_bundle(
        legacy_db,
        promoted_models_root=tmp_path / "none",
    )
    assert len({row["record_id"] for row in exported["manual_labels"]}) == 3
    assert exported["summary"]["manual_labels_without_path"] == 1

    core_db = tmp_path / "core.sqlite"
    _create_v7_core(
        core_db,
        [(7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4)],
    )
    rebound = build_rebound_bundle(
        exported,
        preview_rebind_bundle(exported, core_db),
    )
    target = tmp_path / "fresh-lab.sqlite"
    preview = restore_label_bundle(
        rebound,
        target,
        core_db_path=core_db,
    )
    assert preview["applied"] is False
    assert not target.exists()
    assert preview["summary"]["bound"] == 1
    assert preview["summary"]["recovered"] == 2

    applied = restore_label_bundle(
        rebound,
        target,
        core_db_path=core_db,
        apply=True,
    )
    assert applied["summary"] == preview["summary"]
    connection = sqlite3.connect(target)
    assert (
        connection.execute("SELECT label FROM classifier_labels").fetchone()[0] == "no"
    )
    assert (
        connection.execute("SELECT COUNT(*) FROM classifier_label_recovery").fetchone()[
            0
        ]
        == 2
    )
    connection.close()

    rerun = restore_label_bundle(
        rebound,
        target,
        core_db_path=core_db,
        apply=True,
    )
    assert rerun["summary"] == applied["summary"]
    connection = sqlite3.connect(target)
    assert (
        connection.execute("SELECT COUNT(*) FROM classifier_labels").fetchone()[0] == 1
    )
    assert (
        connection.execute("SELECT COUNT(*) FROM classifier_label_recovery").fetchone()[
            0
        ]
        == 2
    )
    connection.close()

    connection = sqlite3.connect(core_db)
    connection.execute(
        "UPDATE tracks SET content_generation = 5 WHERE track_uuid = 'uuid-a'"
    )
    connection.commit()
    connection.close()
    stale_preview = restore_label_bundle(
        rebound,
        tmp_path / "never-created.sqlite",
        core_db_path=core_db,
    )
    assert stale_preview["summary"]["bound"] == 0
    assert stale_preview["summary"]["recovered"] == 3
    assert not (tmp_path / "never-created.sqlite").exists()


def test_restore_conflict_winner_is_deterministic_and_loser_is_recovered(
    tmp_path: Path,
) -> None:
    rebound, core_db = _restore_fixture(
        tmp_path,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                "first",
                "2026-02-01T00:00:00Z",
            ),
            (
                "alpha",
                2,
                "C:/Music/A.wav",
                100,
                10.0,
                "no",
                "second",
                "2026-02-01T00:00:00Z",
            ),
        ],
        tracks=[(7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4)],
    )
    target = tmp_path / "target.sqlite"
    strong_rows = [row for row in rebound["labels"] if row["status"] == "strong_match"]
    winner = min(str(row["source"]["record_id"]) for row in strong_rows)
    winner_label = next(
        row["source"]["label"]
        for row in strong_rows
        if row["source"]["record_id"] == winner
    )

    report = restore_label_bundle(rebound, target, core_db_path=core_db, apply=True)

    assert report["summary"]["conflict_groups"] == 1
    assert report["summary"]["conflict_losers"] == 1
    connection = sqlite3.connect(target)
    assert (
        connection.execute("SELECT label FROM classifier_labels").fetchone()[0]
        == winner_label
    )
    loser = connection.execute(
        "SELECT record_id, rebind_status, recovery_reason FROM classifier_label_recovery"
    ).fetchone()
    connection.close()
    assert loser == (
        next(
            str(row["source"]["record_id"])
            for row in strong_rows
            if row["source"]["record_id"] != winner
        ),
        "conflict",
        f"conflict_loser_to:{winner}",
    )


def test_restore_weak_match_requires_explicit_record_acceptance(tmp_path: Path) -> None:
    rebound, core_db = _restore_fixture(
        tmp_path,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                None,
                "2026-02-01T00:00:00Z",
            ),
            (
                "beta",
                2,
                "C:/Music/B.wav",
                None,
                None,
                "up",
                None,
                "2026-02-02T00:00:00Z",
            ),
        ],
        tracks=[
            (7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4),
            (8, "uuid-b", "C:/Music/B.wav", 200, 20_000_000_000, 4),
        ],
    )
    weak_record_id = next(
        row["source"]["record_id"]
        for row in rebound["labels"]
        if row["status"] == "weak_match"
    )

    default = restore_label_bundle(
        rebound, tmp_path / "default.sqlite", core_db_path=core_db
    )
    accepted = restore_label_bundle(
        rebound,
        tmp_path / "accepted.sqlite",
        core_db_path=core_db,
        accepted_record_ids=(weak_record_id,),
    )

    assert default["summary"] == {
        "accepted_bound": 0,
        "bound": 1,
        "conflict_groups": 0,
        "conflict_losers": 0,
        "manual_label_total": 2,
        "profile_count": 2,
        "profile_label_definition_count": 4,
        "recovered": 1,
        "strong_bound": 1,
    }
    assert accepted["summary"]["bound"] == 2
    assert accepted["summary"]["strong_bound"] == 1
    assert accepted["summary"]["accepted_bound"] == 1
    assert accepted["summary"]["recovered"] == 0


def test_restore_dry_run_does_not_modify_existing_lab_or_create_backup(
    tmp_path: Path,
) -> None:
    rebound, core_db = _restore_fixture(tmp_path, labels=_base_labels())
    target = tmp_path / "existing.sqlite"
    target.write_bytes(b"unchanged main")
    wal = Path(f"{target}-wal")
    shm = Path(f"{target}-shm")
    wal.write_bytes(b"unchanged wal")
    shm.write_bytes(b"unchanged shm")
    before = {path: path.read_bytes() for path in (target, wal, shm)}

    report = restore_label_bundle(rebound, target, core_db_path=core_db)

    assert report["applied"] is False
    assert {path: path.read_bytes() for path in before} == before
    assert not list(tmp_path.glob("existing.sqlite.restore-backup-*"))


def test_restore_failure_rolls_back_existing_lab_state(tmp_path: Path) -> None:
    rebound, core_db = _restore_fixture(tmp_path, labels=_base_labels())
    target = tmp_path / "existing.sqlite"
    _create_runtime_lab_db(target)
    connection = sqlite3.connect(target)
    connection.execute(
        """
        INSERT INTO classifier_profiles(
            classifier_key, profile_type, name, description, artifact_dir,
            artifact_prefix, training_min_added, positive_label, negative_label
        ) VALUES ('sentinel', 'binary', 'Sentinel', '', 'sentinel', 'sentinel', 1, 'yes', 'no')
        """
    )
    connection.commit()
    before = connection.execute(
        "SELECT classifier_key, name FROM classifier_profiles ORDER BY classifier_key"
    ).fetchall()
    connection.close()

    with pytest.raises(RuntimeError, match="fail after writes"):
        restore_label_bundle(
            rebound,
            target,
            core_db_path=core_db,
            apply=True,
            _failure_hook=lambda: (_ for _ in ()).throw(
                RuntimeError("fail after writes")
            ),
        )

    connection = sqlite3.connect(target)
    after = connection.execute(
        "SELECT classifier_key, name FROM classifier_profiles ORDER BY classifier_key"
    ).fetchall()
    labels = connection.execute("SELECT COUNT(*) FROM classifier_labels").fetchone()[0]
    recovery_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'classifier_label_recovery'"
    ).fetchone()
    connection.close()
    assert after == before
    assert labels == 0
    assert recovery_table is None


def test_restore_backs_up_existing_main_wal_and_shm_before_apply(
    tmp_path: Path,
) -> None:
    rebound, core_db = _restore_fixture(tmp_path, labels=_base_labels())
    target = tmp_path / "existing.sqlite"
    _create_runtime_lab_db(target)
    wal = Path(f"{target}-wal")
    shm = Path(f"{target}-shm")
    wal.write_bytes(b"wal snapshot")
    shm.write_bytes(b"shm snapshot")
    before = {path.name: path.read_bytes() for path in (target, wal, shm)}

    report = restore_label_bundle(rebound, target, core_db_path=core_db, apply=True)

    assert report["backup"] is not None
    backup_dir = Path(report["backup"]["directory"])
    assert {
        Path(item["backup"]).name: Path(item["backup"]).read_bytes()
        for item in report["backup"]["files"]
    } == before
    assert backup_dir.is_dir()


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("track_uuid", "uuid-changed"),
        ("content_generation", 5),
        ("file_path", "C:/Music/renamed.wav"),
        ("file_size_bytes", 101),
        ("file_modified_ns", 10_000_000_001),
    ],
)
def test_restore_apply_revalidates_current_core_target_identity_and_file_facts(
    tmp_path: Path,
    column: str,
    replacement: str | int,
) -> None:
    rebound, core_db = _restore_fixture(
        tmp_path,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                None,
                "2026-02-01T00:00:00Z",
            )
        ],
        tracks=[(7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4)],
    )
    connection = sqlite3.connect(core_db)
    connection.execute(
        f"UPDATE tracks SET {column} = ? WHERE track_id = 7", (replacement,)
    )
    connection.commit()
    connection.close()

    restore_label_bundle(
        rebound, tmp_path / "target.sqlite", core_db_path=core_db, apply=True
    )

    connection = sqlite3.connect(tmp_path / "target.sqlite")
    assert (
        connection.execute("SELECT COUNT(*) FROM classifier_labels").fetchone()[0] == 0
    )
    recovered = connection.execute(
        "SELECT rebind_status, recovery_reason FROM classifier_label_recovery"
    ).fetchone()
    connection.close()
    assert recovered == ("stale_binding", "current_core_identity_or_file_facts_changed")


def test_restore_apply_revalidates_catalog_and_preserves_core_bytes(
    tmp_path: Path,
) -> None:
    rebound, core_db = _restore_fixture(
        tmp_path,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                None,
                "2026-02-01T00:00:00Z",
            )
        ],
        tracks=[(7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4)],
    )
    connection = sqlite3.connect(core_db)
    connection.execute("UPDATE library_catalog SET catalog_uuid = 'catalog-changed'")
    connection.commit()
    connection.close()
    before = core_db.read_bytes()

    restore_label_bundle(
        rebound, tmp_path / "target.sqlite", core_db_path=core_db, apply=True
    )

    assert core_db.read_bytes() == before
    connection = sqlite3.connect(tmp_path / "target.sqlite")
    assert (
        connection.execute("SELECT COUNT(*) FROM classifier_labels").fetchone()[0] == 0
    )
    assert (
        connection.execute(
            "SELECT rebind_status FROM classifier_label_recovery"
        ).fetchone()[0]
        == "stale_binding"
    )
    connection.close()


def test_restore_counts_profiles_definitions_manual_recovery_and_is_idempotent(
    tmp_path: Path,
) -> None:
    rebound, core_db = _restore_fixture(
        tmp_path,
        labels=[
            (
                "alpha",
                1,
                "C:/Music/A.wav",
                100,
                10.0,
                "yes",
                None,
                "2026-02-01T00:00:00Z",
            ),
            ("alpha", 2, None, None, None, "no", None, "2026-02-02T00:00:00Z"),
        ],
        tracks=[(7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4)],
    )
    target = tmp_path / "target.sqlite"

    first = restore_label_bundle(rebound, target, core_db_path=core_db, apply=True)
    second = restore_label_bundle(rebound, target, core_db_path=core_db, apply=True)

    assert (
        first["summary"]
        == second["summary"]
        == {
            "accepted_bound": 0,
            "bound": 1,
            "conflict_groups": 0,
            "conflict_losers": 0,
            "manual_label_total": 2,
            "profile_count": 2,
            "profile_label_definition_count": 4,
            "recovered": 1,
            "strong_bound": 1,
        }
    )
    connection = sqlite3.connect(target)
    counts = tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "classifier_profiles",
            "classifier_profile_labels",
            "classifier_labels",
            "classifier_label_recovery",
        )
    )
    connection.close()
    assert counts == (2, 4, 1, 1)


def _restore_fixture(
    tmp_path: Path,
    *,
    labels: list[
        tuple[str, int, str | None, int | None, float | None, str, str | None, str]
    ],
    tracks: list[tuple[int, str, str, int, int, int]] | None = None,
) -> tuple[dict[str, object], Path]:
    source = tmp_path / "source.sqlite"
    _create_lab_db(source, labels=labels)
    core_db = tmp_path / "core.sqlite"
    _create_v7_core(
        core_db,
        tracks
        or [
            (7, "uuid-a", "C:/Music/A.wav", 100, 10_000_000_000, 4),
            (8, "uuid-b", "C:/Music/B.wav", 200, 20_000_000_000, 4),
        ],
    )
    exported = export_label_bundle(source, promoted_models_root=tmp_path / "none")
    return build_rebound_bundle(
        exported, preview_rebind_bundle(exported, core_db)
    ), core_db


def _create_runtime_lab_db(path: Path) -> None:
    from rhythm_lab.lab_db import RhythmLabDatabase

    connection = RhythmLabDatabase(path).connect()
    connection.close()

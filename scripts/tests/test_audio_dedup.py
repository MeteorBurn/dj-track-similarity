from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
import zipfile

import numpy as np
import pytest

from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    register_contract,
)
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import ACTIVE_CONTRACT_SETTING_PREFIX
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile


def _load_dedup_module():
    path = Path(__file__).resolve().parents[2] / "tools" / "audio-dedup" / "audio_dedup" / "core.py"
    spec = importlib.util.spec_from_file_location("audio_dedup", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _create_library_db(path: Path) -> None:
    LibraryDatabase(path)


def _create_rhythm_lab_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                selected_path TEXT NOT NULL,
                label TEXT NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid,
                    content_generation
                )
            );

            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                selected_path TEXT NOT NULL,
                artist TEXT,
                title TEXT,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid,
                    content_generation, feature_set, model_artifact
                )
            );

            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL
            );
            """
        )


def _current_embedding_fixture(
    family: str,
    values: list[float],
) -> tuple[ContractIdentity, np.ndarray]:
    contract = current_embedding_analysis_output(family).contract
    supplied = np.asarray(values, dtype="<f4")
    if supplied.ndim != 1 or supplied.size > contract.dim:
        raise ValueError(
            f"{family} fixture must contain at most {contract.dim} values"
        )
    vector = np.zeros(contract.dim, dtype="<f4")
    vector[: supplied.size] = supplied
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError(f"{family} fixture must have a finite positive norm")
    return contract, np.ascontiguousarray(vector / norm, dtype="<f4")


def _insert_track(
    db_path: Path,
    *,
    track_id: int,
    path: str,
    size: int = 10_000_000,
    mtime: float = 100.0,
    artist: str = "Artist",
    title: str = "Title",
    album: str | None = "Album",
    bpm: float | None = 128.0,
    musical_key: str | None = "8A",
    duration: float = 300.0,
    sonara: dict[str, object] | None = None,
    vectors: dict[str, list[float]] | None = None,
) -> None:
    database = LibraryDatabase(db_path)
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=path,
            file_size_bytes=size,
            file_modified_ns=int(mtime * 1_000_000_000),
            audio_duration_seconds=duration,
        ),
        tags=FileTags(
            artist=artist,
            title=title,
            album=album,
            tag_bpm=bpm,
            tag_key=musical_key,
            genres=("Test",),
        ),
        scanned_at="2026-07-24T00:00:00.000000Z",
    )
    identity = mutation.identity
    assert identity.track_id == track_id

    if sonara is not None:
        contract = ContractIdentity(
            analysis_family="sonara",
            output_kind="core",
            model_name="sonara-test",
            model_version="1",
            release_hash="sha256:test-sonara-release",
        )
        with database.connect() as connection:
            register_contract(connection, contract)
            connection.execute(
                """
                INSERT INTO library_settings(
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, '2026-07-24T00:00:00.000000Z')
                ON CONFLICT(setting_key) DO UPDATE
                SET setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.core",
                    contract.contract_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO sonara(
                    track_id, content_generation, contract_hash,
                    detected_bpm, onset_density_per_second,
                    energy_score, danceability_score, valence_score,
                    acousticness_score, spectral_centroid_hz,
                    integrated_loudness_lufs, dynamic_range_db,
                    mfcc_mean_blob, chroma_mean_blob,
                    spectral_contrast_mean_blob, analyzed_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    zeroblob(52), zeroblob(48), zeroblob(28),
                    '2026-07-24T00:00:00.000000Z'
                )
                """,
                (
                    identity.track_id,
                    identity.content_generation,
                    contract.contract_hash,
                    sonara.get("bpm"),
                    sonara.get("onset_density"),
                    sonara.get("energy"),
                    sonara.get("danceability"),
                    sonara.get("valence"),
                    sonara.get("acousticness"),
                    sonara.get("spectral_centroid_mean"),
                    sonara.get("loudness_lufs"),
                    sonara.get("dynamic_range_db"),
                ),
            )
            connection.commit()

    for key, values in (vectors or {}).items():
        contract, vector = _current_embedding_fixture(key, values)
        with database.connect() as connection:
            register_contract(connection, contract)
            connection.execute(
                """
                INSERT INTO library_settings(
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, '2026-07-24T00:00:00.000000Z')
                ON CONFLICT(setting_key) DO UPDATE
                SET setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.{key}.embedding",
                    contract.contract_hash,
                ),
            )
            connection.commit()
        with database.connect_artifacts() as connection:
            connection.execute(
                f"""
                INSERT INTO {key}_embeddings(
                    track_id, track_uuid, content_generation,
                    contract_hash, dim, normalization,
                    embedding_blob, analyzed_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?,
                    '2026-07-24T00:00:00.000000Z'
                )
                """,
                (
                    identity.track_id,
                    identity.track_uuid,
                    identity.content_generation,
                    contract.contract_hash,
                    contract.dim,
                    contract.normalization,
                    vector.tobytes(),
                ),
            )
            connection.commit()


def _identity_tuple(
    db_path: Path,
    track_id: int,
) -> tuple[str, str, int]:
    identity = LibraryDatabase(db_path).get_track_identity(track_id)
    assert identity is not None
    return (
        identity.catalog_uuid,
        identity.track_uuid,
        identity.content_generation,
    )


def test_root_filter_selects_only_tracks_inside_root(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/A/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstractedness/A/two.flac")
    _insert_track(db_path, track_id=3, path="N:/Volumes/Abstracted/A/three.flac")

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])

    assert [track.track_id for track in tracks] == [1]


def test_path_contains_additionally_filters_inside_root(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/Keep/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/Other/two.flac")

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=["keep"])

    assert [track.track_id for track in tracks] == [1]


def test_load_tracks_rejects_non_unit_l2_embedding(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    vectors = {
        "mert": [1.0, 0.0, 0.0],
        "maest": [0.0, 1.0, 0.0],
    }
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors=vectors,
    )

    mert_contract = current_embedding_analysis_output("mert").contract
    malformed = np.zeros(mert_contract.dim, dtype="<f4")
    malformed[0] = 2.0
    database = LibraryDatabase(db_path)
    with database.connect_artifacts() as connection:
        connection.execute(
            """
            UPDATE mert_embeddings
            SET embedding_blob = ?
            WHERE track_id = 1
            """,
            (malformed.tobytes(),),
        )
        connection.commit()

    tracks = dedup.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )

    assert len(tracks) == 1
    assert "mert" not in tracks[0].embeddings
    _maest_contract, expected_maest = _current_embedding_fixture(
        "maest",
        vectors["maest"],
    )
    np.testing.assert_array_equal(
        tracks[0].embeddings["maest"],
        expected_maest,
    )


def test_min_score_overrides_preset_threshold() -> None:
    dedup = _load_dedup_module()

    config = dedup.resolve_preset("safe", min_score=0.91)

    assert config.name == "safe"
    assert config.min_score == 0.91
    assert config.min_similarity == 0.985
    assert config.direct_keeper_score == 0.98


def test_presets_use_graduated_safe_delete_thresholds() -> None:
    dedup = _load_dedup_module()

    safe = dedup.resolve_preset("safe", min_score=None)
    balanced = dedup.resolve_preset("balanced", min_score=None)
    aggressive = dedup.resolve_preset("aggressive", min_score=None)

    assert safe.min_score == 0.965
    assert safe.min_similarity == 0.985
    assert safe.direct_keeper_score == 0.98
    assert balanced.min_score == 0.95
    assert balanced.min_similarity == 0.97
    assert balanced.direct_keeper_score == 0.97
    assert aggressive.min_score == 0.925
    assert aggressive.min_similarity == 0.94
    assert aggressive.direct_keeper_score == 0.965


def test_report_documents_audio_to_audio_clap_similarity_semantics(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    vectors = {
        "mert": [1.0, 0.0, 0.0],
        "maest": [1.0, 0.0, 0.0],
        "clap": [1.0, 0.0, 0.0],
    }
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/one.flac", vectors=vectors)
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/two.flac", vectors=vectors)

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = dedup.find_duplicate_groups(tracks, dedup.resolve_preset("safe", min_score=None), limit_groups=None)
    payload = dedup.build_report(groups, tracks, dedup.resolve_preset("safe", min_score=None), root=Path("M:/Volumes/Abstracted"), path_contains=[])

    semantics = payload["score_semantics"]
    assert semantics["clap_similarity"]["kind"] == "audio_to_audio_cosine"
    assert semantics["clap_similarity"]["text_search_comparable"] is False
    assert "text-to-audio" in semantics["clap_similarity"]["notes"]


def test_report_only_main_does_not_delete_files_or_mutate_database(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    first_path = audio_dir / "first.flac"
    second_path = audio_dir / "second.mp3"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _create_library_db(db_path)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(first_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(second_path), size=8_000_000, mtime=200, vectors=vectors)

    exit_code = dedup.main(["--db", str(db_path), "--root", str(audio_dir), "--out-dir", str(out_dir)])

    assert exit_code == 0
    assert first_path.exists()
    assert second_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2
    finally:
        connection.close()
    db_path.rename(tmp_path / "library-renamed.sqlite")
    report_paths = sorted(out_dir.glob("audio_dedup_report_*.json"))
    assert len(report_paths) == 1
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "report-only"
    assert payload["groups"][0]["suggested_keeper"]["track_id"] == 1
    assert payload["groups"][0]["candidate_deletes"][0]["track_id"] == 2
    assert payload["groups"][0]["candidate_deletes"][0]["safe_to_delete"] == "true_candidate"


def test_xlsx_summary_sheet_is_formatted_as_review_dashboard(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    payload = {
        "mode": "report-only",
        "generated_at": "2026-06-23T12:00:00",
        "database_path": "C:/db/library.sqlite",
        "root": "D:/Music",
        "path_contains": ["mastered"],
        "preset": "safe",
        "min_score": 0.965,
        "min_similarity": 0.985,
        "database_track_count": 25,
        "scoped_track_count": 10,
        "track_count": 10,
        "group_count": 2,
        "statistics": {
            "candidate_count": 3,
            "safe_candidate_count": 1,
            "review_candidate_count": 2,
            "confidence_counts": {"high": 1, "medium": 1, "review": 0},
            "embedding_coverage": {"mert": 10, "maest": 9, "clap": 4},
        },
        "rhythm_lab": {
            "database_path": "tools/rhythm-lab/data/rhythm_lab.sqlite",
            "database_exists": True,
            "affected_track_count": 1,
            "affected_row_count": 4,
            "affected_rows": [],
        },
        "groups": [],
    }
    path = tmp_path / "dedup.xlsx"

    dedup.write_xlsx_report(path, payload)

    with zipfile.ZipFile(path) as archive:
        summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = archive.read("xl/styles.xml").decode("utf-8")
    assert '<mergeCell ref="A1:E1"/>' in summary_xml
    assert '<mergeCell ref="A2:E2"/>' in summary_xml
    assert 'showGridLines="0"' in summary_xml
    assert 'Review workbook before deleting files' in summary_xml
    assert "Safe delete candidates" in summary_xml
    assert "Open the Candidates sheet and review every row before apply mode." in summary_xml
    assert 'fgColor rgb="FF111827"' in styles_xml


def test_keeper_selection_prefers_lossless_then_bitrate_proxy() -> None:
    dedup = _load_dedup_module()
    low_bitrate_flac = dedup.TrackRecord(
        track_id=1,
        path="M:/Volumes/Abstracted/a.flac",
        size=10_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )
    high_bitrate_flac = dedup.TrackRecord(
        track_id=2,
        path="M:/Volumes/Abstracted/b.flac",
        size=20_000_000,
        mtime=50.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )
    mp3 = dedup.TrackRecord(
        track_id=3,
        path="M:/Volumes/Abstracted/c.mp3",
        size=30_000_000,
        mtime=300.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )

    assert dedup.choose_keeper([low_bitrate_flac, high_bitrate_flac, mp3]).track_id == 2


def test_ambiguous_chain_group_is_report_only(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors={"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        vectors={"mert": [0.96, 0.28, 0.0], "maest": [0.96, 0.28, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=3,
        path="M:/Volumes/Abstracted/three.flac",
        vectors={"mert": [0.84, 0.5425864, 0.0], "maest": [0.84, 0.5425864, 0.0]},
    )

    config = dedup.resolve_preset("safe", min_score=0.925, min_similarity=0.8)
    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = dedup.find_duplicate_groups(tracks, config, limit_groups=None)
    payload = dedup.build_report(groups, tracks, config, root=Path("M:/Volumes/Abstracted"), path_contains=[])

    group = payload["groups"][0]
    assert {track["track_id"] for track in group["candidate_deletes"]} == {2, 3}
    assert all(track["safe_to_delete"] == "false" for track in group["candidate_deletes"])
    assert "ambiguous chain" in " ".join(group["blocked_reasons"])


def test_safe_preset_requires_content_similarity_not_only_overall_score(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    sonara = {"bpm": 128.0, "danceability": 0.8, "energy": 0.7, "valence": 0.5}
    near_but_not_duplicate = {"mert": [0.96, 0.28, 0.0], "maest": [0.96, 0.28, 0.0]}
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        sonara=sonara,
        vectors={"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        sonara=sonara,
        vectors=near_but_not_duplicate,
    )

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = dedup.find_duplicate_groups(tracks, dedup.resolve_preset("safe", min_score=None), limit_groups=None)

    assert groups == []


def test_tag_bpm_and_key_are_not_used_for_duplicate_scoring() -> None:
    dedup = _load_dedup_module()
    config = dedup.resolve_preset("safe", min_score=None)
    sonara = {"bpm": 128.0, "energy": 0.7, "onset_density": 0.4}
    left = dedup.TrackRecord(
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=90.0,
        musical_key="1A",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )
    right = dedup.TrackRecord(
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=180.0,
        musical_key="12B",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )

    evidence = dedup.score_pair(left, right, config)

    assert evidence.sonara_similarity == 1.0
    assert not hasattr(evidence, "bpm_diff")
    assert not hasattr(evidence, "key_match")


def test_sonara_similarity_reads_stored_feature_payload_values() -> None:
    dedup = _load_dedup_module()
    config = dedup.resolve_preset("safe", min_score=None)
    sonara = {
        "bpm": {"value": 128.0, "type": "float"},
        "energy": {"value": 0.7, "type": "float"},
        "onset_density": {"value": 0.4, "type": "float"},
    }
    left = dedup.TrackRecord(
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=90.0,
        musical_key="1A",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )
    right = dedup.TrackRecord(
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=180.0,
        musical_key="12B",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )

    evidence = dedup.score_pair(left, right, config)

    assert evidence.sonara_similarity == 1.0


def test_json_and_xlsx_reports_include_candidate_evidence(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    _create_library_db(db_path)
    vectors = {
        "mert": [1.0, 0.0, 0.0],
        "maest": [1.0, 0.0, 0.0],
        "clap": [1.0, 0.0, 0.0],
    }
    sonara = {"bpm": 128.0, "danceability": 0.8, "energy": 0.7, "valence": 0.5}
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        sonara=sonara,
        vectors=vectors,
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.mp3",
        size=8_000_000,
        sonara=sonara,
        vectors=vectors,
    )
    _insert_track(db_path, track_id=3, path="N:/Volumes/Other/three.flac", size=20_000_000, sonara=sonara, vectors=vectors)

    result = dedup.run_report(db_path=db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[], preset_name="safe", min_score=None, limit_groups=None, out_dir=out_dir)

    json_payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert json_payload["database_path"] == str(db_path.resolve())
    assert json_payload["database_track_count"] == 3
    assert json_payload["scoped_track_count"] == 2
    assert json_payload["track_count"] == 2
    assert json_payload["min_similarity"] == 0.985
    assert "content_similarity" in json_payload["groups"][0]["pairwise_evidence"][0]
    assert "mert_similarity" in json_payload["groups"][0]["pairwise_evidence"][0]
    assert "keeper_reasons" in json_payload["groups"][0]["suggested_keeper"]
    assert json_payload["groups"][0]["suggested_keeper"]["role"] == "KEEP"
    assert "content_length" not in json_payload["groups"][0]["suggested_keeper"]
    assert "duration_text" not in json_payload["groups"][0]["suggested_keeper"]
    assert "file_size_mb" not in json_payload["groups"][0]["suggested_keeper"]
    assert "audio_codec" not in json_payload["groups"][0]["suggested_keeper"]
    assert json_payload["groups"][0]["candidate_deletes"][0]["role"] == "DUPLICATE"
    assert json_payload["groups"][0]["candidate_deletes"][0]["decision"] == "delete_candidate"
    assert "content_length" not in json_payload["groups"][0]["candidate_deletes"][0]
    assert "duration_text" not in json_payload["groups"][0]["candidate_deletes"][0]
    assert "file_size_mb" not in json_payload["groups"][0]["candidate_deletes"][0]
    assert "audio_codec" not in json_payload["groups"][0]["candidate_deletes"][0]
    assert json_payload["groups"][0]["candidate_deletes"][0]["why_delete_or_review"]
    assert result.xlsx_path.exists()
    assert not result.xlsx_path.with_suffix(".csv").exists()
    with zipfile.ZipFile(result.xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        candidates_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "Candidates" in workbook_xml
    assert "DELETE CANDIDATE" in candidates_xml
    assert "one.flac" in candidates_xml
    assert "delete_content_length" not in candidates_xml
    assert "keeper_content_length" not in candidates_xml
    assert "delete_duration" not in candidates_xml
    assert "keeper_duration" not in candidates_xml
    assert "delete_duration_text" not in candidates_xml
    assert "keeper_duration_text" not in candidates_xml
    assert "file_size_mb" not in candidates_xml
    assert "audio_codec" not in candidates_xml
    assert "MPEG Audio Layer III" not in candidates_xml
    assert "mert_similarity" in candidates_xml
    assert "content_similarity_vs_keeper" in candidates_xml
    assert "Audio Dedup Report" in summary_xml
    assert str(db_path.resolve()) in summary_xml
    assert "Total tracks in database" in summary_xml
    assert "Tracks inside selected root" in summary_xml
    assert not list(out_dir.glob("audio_dedup_report_*.png"))


def test_report_includes_rhythm_lab_impact_for_safe_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(dedup, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    keeper_identity = _identity_tuple(db_path, 1)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid,
                content_generation, selected_path, label
            ) VALUES ('break_energy', ?, ?, ?, ?, ?)
            """,
            [
                (*keeper_identity, str(keeper_path), "keep_label"),
                (*duplicate_identity, str(duplicate_path), "delete_label"),
            ],
        )
        connection.execute(
            """
            INSERT INTO classifier_predictions(
                classifier_key, catalog_uuid, track_uuid,
                content_generation, selected_path, feature_set,
                model_artifact, label, confidence, probabilities_json
            )
            VALUES (
                'break_energy', ?, ?, ?, ?, 'combined',
                'model.joblib', 'delete_prediction', 0.9, '{}'
            )
            """,
            (*duplicate_identity, str(duplicate_path)),
        )

    result = dedup.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    impact = payload["rhythm_lab"]
    assert impact["database_path"] == str(rhythm_lab_db.resolve())
    assert impact["database_exists"] is True
    assert impact["summary"] == {
        "safe_candidate_count": 1,
        "database_exists": True,
        "affected_track_count": 1,
        "affected_row_count": 2,
    }
    assert impact["safe_candidate_track_ids"] == [2]
    assert impact["affected_track_count"] == 1
    assert impact["affected_row_count"] == 2
    assert {row["table_name"] for row in impact["affected_rows"]} == {"classifier_labels", "classifier_predictions"}
    assert {
        (
            row["catalog_uuid"],
            row["track_uuid"],
            row["content_generation"],
        )
        for row in impact["affected_rows"]
    } == {duplicate_identity}
    assert all(row["action"] == "DELETE ON APPLY" for row in impact["affected_rows"])
    with zipfile.ZipFile(result.xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        rhythm_lab_xml = archive.read("xl/worksheets/sheet5.xml").decode("utf-8")
    assert "Rhythm Lab" in workbook_xml
    assert "classifier_labels" in rhythm_lab_xml
    assert "classifier_predictions" in rhythm_lab_xml
    assert "delete_label" in rhythm_lab_xml
    assert "delete_prediction" in rhythm_lab_xml
    assert "keep_label" not in rhythm_lab_xml
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "rhythm_lab_summary=safe_candidates=1 database_exists=true affected_tracks=1 affected_rows=2" in log_text


def test_report_only_cli_prints_rhythm_lab_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(dedup, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.execute(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid,
                content_generation, selected_path, label
            ) VALUES (
                'break_energy', ?, ?, ?, ?, 'delete_label'
            )
            """,
            (*duplicate_identity, str(duplicate_path)),
        )

    exit_code = dedup.main(["--db", str(db_path), "--root", str(audio_dir), "--out-dir", str(out_dir)])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "Report-only run complete. groups=1 safe_candidates=1" in stdout
    assert "Rhythm Lab: safe_candidates=1 database_exists=true affected_tracks=1 affected_rows=1" in stdout


def test_cli_does_not_accept_rhythm_lab_db_argument() -> None:
    dedup = _load_dedup_module()

    with pytest.raises(SystemExit):
        dedup.parse_args(["--root", "M:/Volumes/Abstracted", "--rhythm-lab-db", "lab.sqlite"])


def test_apply_duplicate_deletions_removes_only_safe_temp_files_and_database_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(dedup, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    _create_library_db(db_path)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    database = LibraryDatabase(db_path)
    duplicate_identity = database.get_track_identity(2)
    assert duplicate_identity is not None
    with database.connect_artifacts() as connection:
        connection.execute(
            """
            INSERT INTO sonara_timeline (
                track_id, track_uuid, content_generation,
                contract_hash, payload_json, analyzed_at
            ) VALUES (?, ?, ?, 'sha256:test-timeline', '{}', ?)
            """,
            (
                duplicate_identity.track_id,
                duplicate_identity.track_uuid,
                duplicate_identity.content_generation,
                "2026-07-24T00:00:00.000000Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO sonara_fingerprints(
                track_id, track_uuid, content_generation,
                contract_hash, fingerprint_version, word_count,
                byte_order, fingerprint_blob, analyzed_at
            ) VALUES(
                ?, ?, ?, 'sha256:test-fingerprint', '1', 1,
                'little', ?, ?
            )
            """,
            (
                duplicate_identity.track_id,
                duplicate_identity.track_uuid,
                duplicate_identity.content_generation,
                np.asarray([1], dtype="<u4").tobytes(),
                "2026-07-24T00:00:00.000000Z",
            ),
        )
        connection.commit()
    result = dedup.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
    )

    apply_result = dedup.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=result.payload)

    assert keeper_path.exists()
    assert not duplicate_path.exists()
    assert apply_result.deleted_track_ids == (2,)
    connection = sqlite3.connect(db_path)
    artifacts = database.connect_artifacts()
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(1,)]
        assert [
            int(row[0])
            for row in artifacts.execute(
                "SELECT track_id FROM mert_embeddings ORDER BY track_id"
            )
        ] == [1]
        assert [
            int(row[0])
            for row in artifacts.execute(
                "SELECT track_id FROM maest_embeddings ORDER BY track_id"
            )
        ] == [1]
        assert list(
            artifacts.execute("SELECT track_id FROM sonara_timeline")
        ) == []
        assert list(
            artifacts.execute("SELECT track_id FROM sonara_fingerprints")
        ) == []
    finally:
        artifacts.close()
        connection.close()


def test_apply_log_lists_deleted_files(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    log_path = tmp_path / "audio_dedup_report.log"
    deleted_path = tmp_path / "Abstracted" / "duplicate.mp3"
    payload = {
        "generated_at": "2026-05-29T06:00:00",
        "database_path": str(tmp_path / "library.sqlite"),
        "root": str(tmp_path / "Abstracted"),
        "preset": "safe",
        "min_score": 0.965,
        "min_similarity": 0.985,
        "database_track_count": 2,
        "track_count": 2,
        "scoped_track_count": 2,
        "group_count": 1,
        "rhythm_lab": {
            "summary": {
                "safe_candidate_count": 1,
                "database_exists": False,
                "affected_track_count": 0,
                "affected_row_count": 0,
            },
            "database_path": str(tmp_path / "rhythm_lab.sqlite"),
            "database_exists": False,
            "affected_track_count": 0,
            "affected_row_count": 0,
        },
    }
    apply_result = dedup.ApplyResult(
        deleted_track_ids=(2,),
        deleted_paths=(str(deleted_path),),
        skipped=(),
        failed=(),
        rhythm_lab_deleted_rows=0,
    )

    dedup.write_text_log(log_path, payload, apply_result=apply_result)

    log_text = log_path.read_text(encoding="utf-8")
    assert "deleted_files:" in log_text
    assert f"deleted_file={deleted_path}" in log_text


def test_apply_duplicate_deletions_removes_deleted_tracks_from_default_rhythm_lab_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(dedup, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    keeper_identity = _identity_tuple(db_path, 1)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid,
                content_generation, selected_path, label
            ) VALUES ('break_energy', ?, ?, ?, ?, 'broken')
            """,
            [
                (*keeper_identity, str(keeper_path)),
                (*duplicate_identity, str(duplicate_path)),
            ],
        )
        connection.executemany(
            """
            INSERT INTO classifier_predictions(
                classifier_key, catalog_uuid, track_uuid,
                content_generation, selected_path, feature_set,
                model_artifact, label, confidence, probabilities_json
            )
            VALUES(
                'break_energy', ?, ?, ?, ?, 'combined',
                'model.joblib', 'broken', 0.9, '{}'
            )
            """,
            [
                (*keeper_identity, str(keeper_path)),
                (*duplicate_identity, str(duplicate_path)),
            ],
        )
        connection.execute(
            "INSERT INTO classifier_training_checkpoints(classifier_key, counts_json) VALUES ('break_energy', '{}')"
        )
    result = dedup.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
    )

    apply_result = dedup.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=result.payload)

    assert apply_result.rhythm_lab_deleted_rows == 2
    with sqlite3.connect(rhythm_lab_db) as connection:
        assert connection.execute(
            "SELECT track_uuid FROM classifier_labels"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute(
            "SELECT track_uuid FROM classifier_predictions"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute("SELECT classifier_key FROM classifier_training_checkpoints").fetchall() == [("break_energy",)]

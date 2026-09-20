from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path
import zipfile

import numpy as np
import pytest

from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile

TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup import cli as cli_module  # noqa: E402

from audio_dedup import config as config_module  # noqa: E402

from audio_dedup import core as core_module  # noqa: E402

from audio_dedup import deletion as deletion_module  # noqa: E402

from audio_dedup import keeper as keeper_module  # noqa: E402

from audio_dedup import models as models_module  # noqa: E402

from audio_dedup import report_files as report_files_module  # noqa: E402

from audio_dedup import report_payload as report_payload_module  # noqa: E402

from audio_dedup import report_selection as report_selection_module  # noqa: E402

from audio_dedup import scoring as scoring_module  # noqa: E402

from audio_dedup import track_loading as track_loading_module  # noqa: E402



@pytest.fixture(autouse=True)
def _isolate_external_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    monkeypatch.setattr(core_module, "ffmpeg_available", lambda: False)


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
                selected_path TEXT NOT NULL,
                label TEXT NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid
                )
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
                probabilities_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(
                    classifier_key, catalog_uuid, track_uuid
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
) -> tuple[int, np.ndarray]:
    specification = current_embedding_spec(family)
    supplied = np.asarray(values, dtype="<f4")
    if supplied.ndim != 1 or supplied.size > specification.dimension:
        raise ValueError(
            f"{family} fixture must contain at most {specification.dimension} values"
        )
    vector = np.zeros(specification.dimension, dtype="<f4")
    vector[: supplied.size] = supplied
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError(f"{family} fixture must have a finite positive norm")
    return specification.dimension, np.ascontiguousarray(vector / norm, dtype="<f4")


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
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sonara_features(
                    track_id, detected_bpm, onset_density_per_second,
                    energy_score, danceability_score, valence_score,
                    acousticness_score, spectral_centroid_hz,
                    integrated_loudness_lufs, dynamic_range_db,
                    mfcc_mean_blob, chroma_mean_blob,
                    spectral_contrast_mean_blob, analysis_schema_version,
                    analyzed_at
                ) VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    zeroblob(52), zeroblob(48), zeroblob(28),
                    6,
                    '2026-07-24T00:00:00.000000Z'
                )
                """,
                (
                    identity.track_id,
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
        dimension, vector = _current_embedding_fixture(key, values)
        with database.connect() as connection:
            if key == "mert_v2":
                # MERT-v2 stores all 24 layers; the tool reads layer 24.
                connection.executemany(
                    """
                    INSERT INTO mert_v2_embeddings(
                        track_id, layer, track_uuid, dim, normalization,
                        embedding_blob, analyzed_at
                    ) VALUES(
                        ?, ?, ?, ?, ?, ?,
                        '2026-07-24T00:00:00.000000Z'
                    )
                    """,
                    [
                        (
                            identity.track_id,
                            layer,
                            identity.track_uuid,
                            dimension,
                            "l2",
                            vector.tobytes(),
                        )
                        for layer in range(1, 25)
                    ],
                )
                connection.commit()
                continue
            connection.execute(
                f"""
                INSERT INTO {key}_embeddings(
                    track_id, track_uuid, dim, normalization,
                    embedding_blob, analyzed_at
                ) VALUES(
                    ?, ?, ?, ?, ?,
                    '2026-07-24T00:00:00.000000Z'
                )
                """,
                (
                    identity.track_id,
                    identity.track_uuid,
                    dimension,
                    "l2",
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
    )


def test_root_filter_selects_only_tracks_inside_root(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/A/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstractedness/A/two.flac")
    _insert_track(db_path, track_id=3, path="N:/Volumes/Abstracted/A/three.flac")

    tracks = track_loading_module.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])

    assert [track.track_id for track in tracks] == [1]


def test_path_contains_additionally_filters_inside_root(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/Keep/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/Other/two.flac")

    tracks = track_loading_module.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=["keep"])

    assert [track.track_id for track in tracks] == [1]


def test_load_tracks_limits_embeddings_to_selected_sources_and_reports_progress(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    vectors = {
        "mert_v2": [1.0, 0.0, 0.0],
        "maest": [0.0, 1.0, 0.0],
        "muq": [0.0, 0.0, 1.0],
        "clap": [0.5, 0.5, 0.0],
    }
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors=vectors,
    )
    progress: list[tuple[int, int, str]] = []

    tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
        sources=("mert_v2", "maest"),
        progress_callback=lambda processed, total, message: progress.append(
            (processed, total, message)
        ),
    )

    assert track_loading_module.EMBEDDING_LOAD_CHUNK_SIZE == 200
    assert set(tracks[0].embeddings) == {"mert_v2", "maest"}
    assert (0, 1, "Loading MERT_V2 embeddings") in progress
    assert (1, 1, "Loading MERT_V2 embeddings") in progress
    assert (0, 1, "Loading MAEST embeddings") in progress
    assert (1, 1, "Loading MAEST embeddings") in progress
    assert all("MUQ" not in message and "CLAP" not in message for _, _, message in progress)


def test_load_tracks_rejects_non_unit_l2_embedding(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    vectors = {
        "mert_v2": [1.0, 0.0, 0.0],
        "maest": [0.0, 1.0, 0.0],
    }
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors=vectors,
    )

    mert_v2_specification = current_embedding_spec("mert_v2")
    malformed = np.zeros(mert_v2_specification.dimension, dtype="<f4")
    malformed[0] = 2.0
    database = LibraryDatabase(db_path)
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE mert_v2_embeddings
            SET embedding_blob = ?
            WHERE track_id = 1
            """,
            (malformed.tobytes(),),
        )
        connection.commit()

    tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )

    assert len(tracks) == 1
    assert "mert_v2" not in tracks[0].embeddings
    _maest_contract, expected_maest = _current_embedding_fixture(
        "maest",
        vectors["maest"],
    )
    np.testing.assert_array_equal(
        tracks[0].embeddings["maest"],
        expected_maest,
    )


def test_load_tracks_uses_only_structurally_valid_current_muq_vectors(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors={"muq": [1.0, 0.0, 0.0]},
    )

    tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )

    assert set(tracks[0].embeddings) == {"muq"}
    _contract, expected_muq = _current_embedding_fixture(
        "muq",
        [1.0, 0.0, 0.0],
    )
    np.testing.assert_array_equal(
        tracks[0].embeddings["muq"],
        expected_muq,
    )

    database = LibraryDatabase(db_path)
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE muq_embeddings
            SET normalization = 'none'
            WHERE track_id = 1
            """,
        )
        connection.commit()

    invalid_tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )

    assert "muq" not in invalid_tracks[0].embeddings


@pytest.mark.parametrize(
    ("sources", "weights", "match"),
    [
        ([], None, "at least one"),
        (["mert_v2", "mert_v2"], None, "unique"),
        (["unknown"], None, "Unsupported"),
        (["mert_v2", "muq"], {"mert_v2": 1.0}, "exactly"),
        (["mert_v2"], {"mert_v2": -0.1}, "finite and nonnegative"),
        (["mert_v2"], {"mert_v2": float("nan")}, "finite and nonnegative"),
        (["mert_v2"], {"mert_v2": float("inf")}, "finite and nonnegative"),
        (
            ["mert_v2", "muq"],
            {"mert_v2": 0.0, "muq": 0.0},
            "positive",
        ),
    ],
)
def test_source_config_rejects_invalid_sources_and_weights(
    sources: list[str],
    weights: dict[str, float] | None,
    match: str,
) -> None:

    with pytest.raises(ValueError, match=match):
        config_module.resolve_source_config(
            sources=sources,
            weights=weights,
        )


def test_cli_accepts_repeatable_sources_and_weights() -> None:

    args = cli_module.parse_args(
        [
            "--root",
            "D:/Music",
            "--source",
            "mert_v2",
            "--source",
            "muq",
            "--weight",
            "mert_v2=0.8",
            "--weight",
            "muq=0.2",
        ]
    )
    source_config = config_module.resolve_source_config(
        sources=args.sources,
        weights=config_module.parse_weight_arguments(args.weights),
    )

    assert source_config.sources == ("mert_v2", "muq")
    assert source_config.weights == {"mert_v2": 0.8, "muq": 0.2}


@pytest.mark.parametrize(
    ("sources", "weights", "expected_blockers"),
    [
        (
            ["muq"],
            {"muq": 1.0},
            {"MERT_V2 source disabled", "MAEST source disabled"},
        ),
        (
            None,
            None,
            {"missing MERT_V2 embedding", "missing MAEST embedding"},
        ),
    ],
)
def test_high_muq_only_report_candidate_is_never_safe_to_delete(
    tmp_path: Path,
    sources: list[str] | None,
    weights: dict[str, float] | None,
    expected_blockers: set[str],
) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    vectors = {"muq": [1.0, 0.0, 0.0]}
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        vectors=vectors,
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.mp3",
        size=8_000_000,
        vectors=vectors,
    )
    tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )
    config = config_module.resolve_preset("safe", min_score=None)
    source_config = config_module.resolve_source_config(
        sources=sources,
        weights=weights,
    )

    groups = scoring_module.find_duplicate_groups(
        tracks,
        config,
        limit_groups=None,
        source_config=source_config,
    )
    payload = report_payload_module.build_report(
        groups,
        tracks,
        config,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
        source_config=source_config,
    )

    assert len(groups) == 1
    evidence = payload["groups"][0]["pairwise_evidence"][0]
    assert evidence["muq_similarity"] == pytest.approx(1.0)
    candidate = payload["groups"][0]["candidate_deletes"][0]
    assert candidate["decision"] == "review"
    assert candidate["safe_to_delete"] == "false"
    assert expected_blockers <= set(candidate["blocked_reasons"])
    assert report_selection_module.safe_delete_candidates(payload) == []


@pytest.mark.parametrize(
    (
        "sources",
        "weights",
        "expected_weight_blockers",
        "expect_corroboration_blocker",
    ),
    [
        (
            ["mert_v2", "maest", "muq"],
            {"mert_v2": 0.0, "maest": 0.0, "muq": 1.0},
            {
                "MERT_V2 weight is not positive",
                "MAEST weight is not positive",
            },
            False,
        ),
        (
            ["mert_v2", "maest", "muq"],
            {"mert_v2": 0.001, "maest": 0.001, "muq": 0.998},
            set(),
            True,
        ),
    ],
)
def test_weighting_requires_substantive_corroboration(
    tmp_path: Path,
    sources: list[str],
    weights: dict[str, float],
    expected_weight_blockers: set[str],
    expect_corroboration_blocker: bool,
) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        vectors={
            "mert_v2": [1.0, 0.0],
            "maest": [1.0, 0.0],
            "muq": [1.0, 0.0],
            "clap": [1.0, 0.0],
        },
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.mp3",
        size=8_000_000,
        vectors={
            "mert_v2": [-1.0, 0.0],
            "maest": [-1.0, 0.0],
            "muq": [1.0, 0.0],
            "clap": [1.0, 0.0],
        },
    )
    tracks = track_loading_module.load_tracks(
        db_path,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
    )
    config = config_module.resolve_preset("safe", min_score=None)
    source_config = config_module.resolve_source_config(
        sources=sources,
        weights=weights,
    )

    groups = scoring_module.find_duplicate_groups(
        tracks,
        config,
        limit_groups=None,
        source_config=source_config,
    )
    payload = report_payload_module.build_report(
        groups,
        tracks,
        config,
        root=Path("M:/Volumes/Abstracted"),
        path_contains=[],
        source_config=source_config,
    )

    assert len(groups) == 1
    evidence = payload["groups"][0]["pairwise_evidence"][0]
    assert evidence["score"] >= config.min_score
    assert evidence["content_similarity"] >= config.min_similarity
    assert evidence["mert_v2_similarity"] == pytest.approx(-1.0)
    assert evidence["maest_similarity"] == pytest.approx(-1.0)
    candidate = payload["groups"][0]["candidate_deletes"][0]
    assert candidate["decision"] == "review"
    assert candidate["safe_to_delete"] == "false"
    blockers = set(candidate["blocked_reasons"])
    assert expected_weight_blockers <= blockers
    has_corroboration_blocker = any(
        blocker.startswith(
            "MERT_V2+MAEST corroboration below delete safety threshold"
        )
        for blocker in blockers
    )
    assert has_corroboration_blocker is expect_corroboration_blocker
    assert report_selection_module.safe_delete_candidates(payload) == []


def test_min_score_overrides_preset_threshold() -> None:

    config = config_module.resolve_preset("safe", min_score=0.91)

    assert config.name == "safe"
    assert config.min_score == 0.91
    assert config.min_similarity == 0.985
    assert config.direct_keeper_score == 0.98


def test_report_only_main_does_not_delete_files_or_mutate_database(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    first_path = audio_dir / "first.flac"
    second_path = audio_dir / "second.mp3"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _create_library_db(db_path)
    vectors = {"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(first_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(second_path), size=8_000_000, mtime=200, vectors=vectors)

    exit_code = cli_module.main(["--db", str(db_path), "--root", str(audio_dir), "--out-dir", str(out_dir), "--embedding"])

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


def test_keeper_selection_prefers_lossless_then_bitrate_proxy() -> None:
    low_bitrate_flac = models_module.TrackRecord(
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
    high_bitrate_flac = models_module.TrackRecord(
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
    mp3 = models_module.TrackRecord(
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

    assert keeper_module.choose_keeper([low_bitrate_flac, high_bitrate_flac, mp3]).track_id == 2


def test_ambiguous_chain_group_is_report_only(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors={"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        vectors={"mert_v2": [0.96, 0.28, 0.0], "maest": [0.96, 0.28, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=3,
        path="M:/Volumes/Abstracted/three.flac",
        vectors={"mert_v2": [0.84, 0.5425864, 0.0], "maest": [0.84, 0.5425864, 0.0]},
    )

    config = config_module.resolve_preset("safe", min_score=0.925, min_similarity=0.8)
    tracks = track_loading_module.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = scoring_module.find_duplicate_groups(tracks, config, limit_groups=None)
    payload = report_payload_module.build_report(groups, tracks, config, root=Path("M:/Volumes/Abstracted"), path_contains=[])

    group = payload["groups"][0]
    assert {track["track_id"] for track in group["candidate_deletes"]} == {2, 3}
    assert all(track["safe_to_delete"] == "false" for track in group["candidate_deletes"])
    assert "ambiguous chain" in " ".join(group["blocked_reasons"])


def test_safe_preset_requires_content_similarity_not_only_overall_score(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    sonara = {"bpm": 128.0, "danceability": 0.8, "energy": 0.7, "valence": 0.5}
    near_but_not_duplicate = {"mert_v2": [0.96, 0.28, 0.0], "maest": [0.96, 0.28, 0.0]}
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        sonara=sonara,
        vectors={"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        sonara=sonara,
        vectors=near_but_not_duplicate,
    )

    tracks = track_loading_module.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = scoring_module.find_duplicate_groups(tracks, config_module.resolve_preset("safe", min_score=None), limit_groups=None)

    assert groups == []


def test_sonara_similarity_reads_stored_feature_payload_values() -> None:
    config = config_module.resolve_preset("safe", min_score=None)
    sonara = {
        "bpm": {"value": 128.0, "type": "float"},
        "energy": {"value": 0.7, "type": "float"},
        "onset_density": {"value": 0.4, "type": "float"},
    }
    left = models_module.TrackRecord(
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
    right = models_module.TrackRecord(
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

    evidence = scoring_module.score_pair(left, right, config)

    assert evidence.sonara_similarity == 1.0


def test_json_and_xlsx_reports_include_candidate_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    _create_library_db(db_path)
    vectors = {
        "mert_v2": [1.0, 0.0, 0.0],
        "maest": [1.0, 0.0, 0.0],
        "muq": [1.0, 0.0, 0.0],
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

    result = core_module.run_report(db_path=db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[], preset_name="safe", min_score=None, limit_groups=None, out_dir=out_dir, mode=config_module.MODE_EMBEDDING)

    json_payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert json_payload["database_path"] == str(db_path.resolve())
    assert json_payload["database_track_count"] == 3
    assert json_payload["scoped_track_count"] == 2
    assert json_payload["track_count"] == 2
    assert json_payload["sources"] == [
        "mert_v2",
        "maest",
        "muq",
        "clap",
    ]
    assert json_payload["weights"] == {
        "mert_v2": 0.43,
        "maest": 0.32,
        "muq": 0.12,
        "clap": 0.04,
    }
    assert json_payload["min_similarity"] == 0.985
    assert "content_similarity" in json_payload["groups"][0]["pairwise_evidence"][0]
    assert "mert_v2_similarity" in json_payload["groups"][0]["pairwise_evidence"][0]
    assert json_payload["groups"][0]["pairwise_evidence"][0]["muq_similarity"] == pytest.approx(1.0)
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
    assert "mert_v2_similarity" in candidates_xml
    assert "muq_similarity" in candidates_xml
    assert "content_similarity_vs_keeper" in candidates_xml
    assert "Audio Dedup Report" in summary_xml
    assert str(db_path.resolve()) in summary_xml
    assert "Total tracks in database" in summary_xml
    assert "Tracks inside selected root" in summary_xml
    assert "muq=0.12" in summary_xml
    assert "muq_similarity" in result.log_path.read_text(encoding="utf-8")
    assert not list(out_dir.glob("audio_dedup_report_*.png"))


def test_report_includes_rhythm_lab_impact_for_safe_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    keeper_identity = _identity_tuple(db_path, 1)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid, selected_path, label
            ) VALUES ('break_energy', ?, ?, ?, ?)
            """,
            [
                (*keeper_identity, str(keeper_path), "keep_label"),
                (*duplicate_identity, str(duplicate_path), "delete_label"),
            ],
        )
        connection.execute(
            """
                INSERT INTO classifier_predictions(
                    classifier_key, catalog_uuid, track_uuid, selected_path,
                    feature_set, model_artifact, label, confidence, probabilities_json
                )
                VALUES (
                    'break_energy', ?, ?, ?,
                    'combined', 'model.joblib', 'delete_prediction', 0.9, '{}'
            )
            """,
            (*duplicate_identity, str(duplicate_path)),
        )

    result = core_module.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
        mode=config_module.MODE_EMBEDDING,
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


def test_apply_duplicate_deletions_removes_only_safe_temp_files_and_database_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    _create_library_db(db_path)
    vectors = {"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    result = core_module.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
        mode=config_module.MODE_EMBEDDING,
    )

    apply_result = deletion_module.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=result.payload)

    assert keeper_path.exists()
    assert not duplicate_path.exists()
    assert apply_result.deleted_track_ids == (2,)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(1,)]
        assert [
            int(row[0])
            for row in connection.execute(
                "SELECT DISTINCT track_id FROM mert_v2_embeddings ORDER BY track_id"
            )
        ] == [1]
        assert [
            int(row[0])
            for row in connection.execute(
                "SELECT track_id FROM maest_embeddings ORDER BY track_id"
            )
        ] == [1]
    finally:
        connection.close()


def test_apply_log_lists_deleted_files(tmp_path: Path) -> None:
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
    apply_result = models_module.ApplyResult(
        deleted_track_ids=(2,),
        deleted_paths=(str(deleted_path),),
        skipped=(),
        failed=(),
        rhythm_lab_deleted_rows=0,
    )

    report_files_module.write_text_log(log_path, payload, apply_result=apply_result)

    log_text = log_path.read_text(encoding="utf-8")
    assert "deleted_files:" in log_text
    assert f"deleted_file={deleted_path}" in log_text


def _two_copy_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "library.sqlite"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", tmp_path / "missing_rhythm_lab.sqlite")
    _create_library_db(db_path)
    vectors = {"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    result = core_module.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=tmp_path / "reports",
        mode=config_module.MODE_EMBEDDING,
    )
    return db_path, audio_dir, keeper_path, duplicate_path, result


def test_apply_duplicate_deletions_deletes_the_reviewer_selection_including_the_keeper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )
    keeper_track_id = int(result.payload["groups"][0]["suggested_keeper"]["track_id"])
    assert keeper_track_id == 1

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        root=audio_dir,
        payload=result.payload,
        selected_track_ids=[keeper_track_id],
    )

    assert apply_result.deleted_track_ids == (keeper_track_id,)
    assert not keeper_path.exists()
    assert duplicate_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(2,)]
    finally:
        connection.close()


def test_apply_duplicate_deletions_refuses_a_selection_that_empties_the_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        root=audio_dir,
        payload=result.payload,
        selected_track_ids=[1, 2],
    )

    assert apply_result.deleted_track_ids == ()
    assert keeper_path.exists()
    assert duplicate_path.exists()
    assert all("group would lose every copy" in reason for reason in apply_result.skipped)


def test_apply_duplicate_deletions_never_deletes_permanently_when_the_recycle_bin_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, audio_dir, keeper_path, duplicate_path, result = _two_copy_report(
        tmp_path,
        monkeypatch,
    )
    module = types.ModuleType("send2trash")

    def refuse(_path: str) -> None:
        raise OSError("recycle bin unavailable")

    module.send2trash = refuse
    monkeypatch.setitem(sys.modules, "send2trash", module)

    apply_result = deletion_module.apply_duplicate_deletions(
        db_path=db_path,
        root=audio_dir,
        payload=result.payload,
        selected_track_ids=[2],
        deletion_mode=config_module.DELETION_MODE_TRASH,
    )

    assert apply_result.deleted_track_ids == ()
    assert duplicate_path.exists()
    assert keeper_path.exists()
    assert any("recycle bin unavailable" in reason for reason in apply_result.failed)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        ).fetchall() == [(1,), (2,)]
    finally:
        connection.close()


def test_apply_duplicate_deletions_removes_deleted_tracks_from_default_rhythm_lab_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    monkeypatch.setattr(config_module, "DEFAULT_RHYTHM_LAB_DB", rhythm_lab_db)
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert_v2": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    keeper_identity = _identity_tuple(db_path, 1)
    duplicate_identity = _identity_tuple(db_path, 2)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(
                classifier_key, catalog_uuid, track_uuid, selected_path, label
            ) VALUES ('break_energy', ?, ?, ?, 'broken')
            """,
            [
                (*keeper_identity, str(keeper_path)),
                (*duplicate_identity, str(duplicate_path)),
            ],
        )
        connection.executemany(
            """
                INSERT INTO classifier_predictions(
                    classifier_key, catalog_uuid, track_uuid, selected_path,
                    feature_set, model_artifact, label, confidence, probabilities_json
                )
                VALUES(
                    'break_energy', ?, ?, ?,
                    'combined', 'model.joblib', 'broken', 0.9, '{}'
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
    result = core_module.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
        mode=config_module.MODE_EMBEDDING,
    )

    apply_result = deletion_module.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=result.payload)

    assert apply_result.rhythm_lab_deleted_rows == 2
    with sqlite3.connect(rhythm_lab_db) as connection:
        assert connection.execute(
            "SELECT track_uuid FROM classifier_labels"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute(
            "SELECT track_uuid FROM classifier_predictions"
        ).fetchall() == [(keeper_identity[1],)]
        assert connection.execute("SELECT classifier_key FROM classifier_training_checkpoints").fetchall() == [("break_energy",)]

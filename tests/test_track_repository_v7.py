from __future__ import annotations

import json
import re
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    register_contract,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_search_fts import (
    fts_match_query,
    rebuild_track_search_fts,
)
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-23T12:34:56.123456Z"
_LATER = "2026-07-23T12:35:56.654321Z"
_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
_MAEST_ANALYSIS_CONTRACT = ContractIdentity(
    analysis_family="maest",
    output_kind="analysis",
    model_name="mtg-upf/discogs-maest-30s-pw-129e",
    model_version="1.0",
    checkpoint_id="sha256:" + "4" * 64,
    preprocessing="shared-mono-sr16000-window30s",
    parameters={
        "analysis_offset_seconds": 30.0,
        "analysis_window_ratios": [0.25, 0.5, 0.75],
        "input_seconds": 30.0,
        "sample_rate_hz": 16_000,
        "top_k": 3,
    },
)


def _scanned_file(
    path: Path,
    *,
    size: int | None = None,
    modified_ns: int | None = None,
) -> ScannedFile:
    stat = path.stat()
    return ScannedFile(
        file_path=str(path),
        file_size_bytes=stat.st_size if size is None else size,
        file_modified_ns=(stat.st_mtime_ns if modified_ns is None else modified_ns),
        audio_format="Wave",
        audio_codec="PCM",
        sample_rate_hz=44_100,
        channel_count=2,
        bit_rate_bps=1_411_200,
        audio_duration_seconds=1.0,
    )


def _add_track(
    database: LibraryDatabase,
    path: Path,
    *,
    title: str,
    timestamp: str = _NOW,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(title.encode("utf-8"))
    return database.upsert_scanned_track(
        file=_scanned_file(path),
        tags=FileTags(
            title=title,
            artist="Repository Artist",
            album="Repository Album",
            tag_bpm=128.0,
            tag_key="8A",
            genres=("Techno",),
        ),
        scanned_at=timestamp,
    )


def _fts_ids(
    database: LibraryDatabase,
    query: str,
) -> list[int]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT track_id
            FROM track_search_fts
            WHERE track_search_fts MATCH ?
            ORDER BY track_id
            """,
            (fts_match_query(query),),
        ).fetchall()
    return [int(row[0]) for row in rows]


def _fts_content_contains(
    database: LibraryDatabase,
    text: str,
) -> bool:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                file_path,
                title,
                artist,
                album,
                comment,
                label,
                catalog_number,
                country,
                isrc,
                year,
                track_number,
                disc_number,
                file_genres,
                maest_genres
            FROM track_search_fts
            """
        ).fetchall()
    needle = text.casefold()
    return any(
        needle in str(value).casefold() for row in rows for value in row if value
    )


def _set_maest_genres(
    database: LibraryDatabase,
    *,
    track_id: int,
    generation: int,
    genres: object,
) -> None:
    with database.connect() as connection:
        contract_hash = register_contract(
            connection,
            _MAEST_ANALYSIS_CONTRACT,
            created_at=_NOW,
        )
        connection.execute(
            """
            INSERT INTO maest_scores(
                track_id,
                content_generation,
                contract_hash,
                genres_json,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                content_generation = excluded.content_generation,
                contract_hash = excluded.contract_hash,
                genres_json = excluded.genres_json,
                analyzed_at = excluded.analyzed_at
            """,
            (
                track_id,
                generation,
                contract_hash,
                json.dumps(genres),
                _NOW,
            ),
        )
        connection.commit()


def _insert_core_state(
    database: LibraryDatabase,
    *,
    track_id: int,
    other_track_id: int,
) -> None:
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO contracts(
                contract_hash,
                analysis_family,
                output_kind,
                model_name,
                release_hash,
                canonical_payload_json,
                created_at
            ) VALUES ('sonara-core', 'sonara', 'core', 'sonara', 'release-a', '{}', ?)
            """,
            (_NOW,),
        )
        connection.execute(
            """
            INSERT INTO contracts(
                contract_hash,
                analysis_family,
                output_kind,
                model_name,
                canonical_payload_json,
                created_at
            ) VALUES ('maest-analysis', 'maest', 'analysis', 'maest', '{}', ?)
            """,
            (_NOW,),
        )
        connection.execute(
            """
            INSERT INTO sonara(
                track_id,
                content_generation,
                contract_hash,
                mfcc_mean_blob,
                chroma_mean_blob,
                spectral_contrast_mean_blob,
                analyzed_at
            ) VALUES (?, 1, 'sonara-core', ?, ?, ?, ?)
            """,
            (
                track_id,
                b"\x00" * 52,
                b"\x00" * 48,
                b"\x00" * 28,
                _NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO maest_scores(
                track_id,
                content_generation,
                contract_hash,
                syncopated_rhythm,
                genres_json,
                analyzed_at
            ) VALUES (?, 1, 'maest-analysis', 1, '[]', ?)
            """,
            (track_id, _NOW),
        )
        connection.execute(
            """
            INSERT INTO classifier_scores(
                track_id,
                classifier_key,
                content_generation,
                model_id,
                feature_set,
                feature_manifest_hash,
                required_outputs_hash,
                uses_sonara,
                sonara_release_hash,
                positive_label,
                predicted_class,
                score_bucket,
                score,
                confidence,
                probabilities_json,
                analyzed_at
            ) VALUES (
                ?, 'voice', 1, 'model-a', 'sonara',
                'manifest-a', 'required-a', 1, 'release-a', 'voice', 'voice',
                'high', 0.9, 0.8, '{"voice":0.9}', ?
            )
            """,
            (track_id, _NOW),
        )
        connection.execute(
            "INSERT INTO likes(track_id, liked_at) VALUES (?, ?)",
            (track_id, _NOW),
        )
        connection.execute(
            """
            INSERT INTO pair_feedback(
                seed_track_id,
                candidate_track_id,
                rating,
                reason_tags_json,
                notes,
                source,
                created_at,
                updated_at
            ) VALUES (?, ?, 3, '[]', NULL, 'manual', ?, ?)
            """,
            (track_id, other_track_id, _NOW, _NOW),
        )
        connection.execute(
            """
            INSERT INTO transition_feedback(
                outgoing_track_id,
                incoming_track_id,
                rating,
                risk_tags_json,
                notes,
                source,
                created_at
            ) VALUES (?, ?, 3, '[]', NULL, 'manual', ?)
            """,
            (track_id, other_track_id, _NOW),
        )
        connection.commit()


def _insert_artifact(
    database: LibraryDatabase,
    *,
    table: str,
    track_id: int,
    track_uuid: str,
    generation: int,
) -> None:
    with database.connect_artifacts() as connection:
        if table == "sonara_timeline":
            connection.execute(
                """
                INSERT INTO sonara_timeline(
                    track_id,
                    track_uuid,
                    content_generation,
                    contract_hash,
                    payload_json,
                    analyzed_at
                ) VALUES (?, ?, ?, 'artifact-contract', '{}', ?)
                """,
                (track_id, track_uuid, generation, _NOW),
            )
        elif table == "sonara_fingerprints":
            connection.execute(
                """
                INSERT INTO sonara_fingerprints(
                    track_id,
                    track_uuid,
                    content_generation,
                    contract_hash,
                    fingerprint_version,
                    word_count,
                    byte_order,
                    fingerprint_blob,
                    analyzed_at
                ) VALUES (
                    ?, ?, ?, 'artifact-contract', '1', 1,
                    'little', ?, ?
                )
                """,
                (
                    track_id,
                    track_uuid,
                    generation,
                    struct.pack("<I", 1),
                    _NOW,
                ),
            )
        else:
            connection.execute(
                f"""
                INSERT INTO {table}(
                    track_id,
                    track_uuid,
                    content_generation,
                    contract_hash,
                    dim,
                    normalization,
                    embedding_blob,
                    analyzed_at
                ) VALUES (?, ?, ?, 'artifact-contract', 1, 'none', ?, ?)
                """,
                (
                    track_id,
                    track_uuid,
                    generation,
                    struct.pack("<f", 1.0),
                    _NOW,
                ),
            )
        connection.commit()


def test_new_track_creates_uuid_generation_typed_tags_and_live_fts(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    path = tmp_path / "Music" / "New Track.wav"
    path.parent.mkdir()

    mutation = _add_track(database, path, title="Typed Midnight")

    assert mutation.action == "added"
    assert mutation.identity.content_generation == 1
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        mutation.identity.track_uuid,
    )
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT
                t.file_path,
                t.content_generation,
                t.last_scanned_at,
                t.created_at,
                t.updated_at,
                ft.title,
                ft.artist,
                ft.genres_json,
                ft.tags_read_at
            FROM tracks AS t
            JOIN file_tags AS ft ON ft.track_id = t.track_id
            WHERE t.track_id = ?
            """,
            (mutation.identity.track_id,),
        ).fetchone()
    assert row is not None
    assert row["file_path"] == canonical_file_path(path)
    assert int(row["content_generation"]) == 1
    assert row["title"] == "Typed Midnight"
    assert row["artist"] == "Repository Artist"
    assert json.loads(row["genres_json"]) == ["Techno"]
    for timestamp in (
        row["last_scanned_at"],
        row["created_at"],
        row["updated_at"],
        row["tags_read_at"],
    ):
        assert _TIMESTAMP_PATTERN.fullmatch(str(timestamp))
    assert _fts_ids(database, "midnight") == [mutation.identity.track_id]


def test_external_file_change_invalidates_derived_rows_but_preserves_human_data(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first = _add_track(
        database,
        tmp_path / "first.wav",
        title="Original Title",
    )
    second = _add_track(
        database,
        tmp_path / "second.wav",
        title="Second Track",
    )
    _insert_core_state(
        database,
        track_id=first.identity.track_id,
        other_track_id=second.identity.track_id,
    )
    _insert_artifact(
        database,
        table="maest_embeddings",
        track_id=first.identity.track_id,
        track_uuid=first.identity.track_uuid,
        generation=1,
    )

    original = tmp_path / "first.wav"
    old_stat = original.stat()
    changed = database.upsert_scanned_track(
        file=_scanned_file(
            original,
            size=old_stat.st_size + 10,
            modified_ns=old_stat.st_mtime_ns + 1,
        ),
        tags=FileTags(title="Changed Title"),
        scanned_at=_LATER,
    )

    assert changed.action == "updated"
    assert changed.identity.track_uuid == first.identity.track_uuid
    assert changed.identity.content_generation == 2
    with database.connect() as connection:
        for table in ("sonara", "maest_scores", "classifier_scores"):
            assert (
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE track_id = ?",
                    (first.identity.track_id,),
                ).fetchone()[0]
                == 0
            )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM likes WHERE track_id = ?",
                (first.identity.track_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM pair_feedback").fetchone()[0] == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM transition_feedback").fetchone()[0]
            == 1
        )
    with database.connect_artifacts() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0]
            == 0
        )
    assert _fts_ids(database, "changed") == [first.identity.track_id]
    assert _fts_ids(database, "original") == []

    _insert_artifact(
        database,
        table="maest_embeddings",
        track_id=first.identity.track_id,
        track_uuid=first.identity.track_uuid,
        generation=99,
    )
    _insert_artifact(
        database,
        table="mert_embeddings",
        track_id=first.identity.track_id,
        track_uuid=first.identity.track_uuid,
        generation=2,
    )
    unchanged = database.upsert_scanned_track(
        file=_scanned_file(
            original,
            size=old_stat.st_size + 10,
            modified_ns=old_stat.st_mtime_ns + 1,
        ),
        tags=FileTags(),
        scanned_at="2026-07-23T12:36:56.000000Z",
    )
    assert unchanged.action == "unchanged"
    with database.connect_artifacts() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0]
            == 0
        )
        current = connection.execute(
            """
            SELECT track_uuid, content_generation
            FROM mert_embeddings
            WHERE track_id = ?
            """,
            (first.identity.track_id,),
        ).fetchone()
    assert tuple(current) == (first.identity.track_uuid, 2)


def test_refresh_and_self_tag_write_do_not_change_generation_or_analysis(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    path = tmp_path / "tags.wav"
    mutation = _add_track(database, path, title="Before Refresh")
    identity = mutation.identity
    _insert_artifact(
        database,
        table="clap_embeddings",
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        generation=identity.content_generation,
    )

    refresh_expected = database.get_track_file_state(path)
    assert refresh_expected is not None
    refreshed = database.refresh_file_tags(
        refresh_expected,
        FileTags(title="After Refresh", genres=("House",)),
        tags_read_at=_LATER,
    )
    assert refreshed == identity

    expected = database.get_track_file_state(path)
    assert expected is not None
    callback_order: list[str] = []

    def write_source(source_path: Path) -> None:
        callback_order.append("write")
        with source_path.open("ab") as stream:
            stream.write(b"genre")

    def read_source_tags(_source_path: Path) -> FileTags:
        callback_order.append("read")
        return FileTags(
            title="After Self Write",
            genres=("Deep House",),
        )

    def validate_readback(tags: FileTags) -> None:
        callback_order.append("validate")
        assert tags.genres == ("Deep House",)

    self_written = database.apply_self_tag_write(
        expected,
        write_source=write_source,
        read_source_tags=read_source_tags,
        validate_readback=validate_readback,
        tags_read_at="2026-07-23T12:36:56.000000Z",
    )
    assert self_written == identity
    assert callback_order == ["write", "read", "validate"]
    final_stat = path.stat()
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT
                t.content_generation,
                t.file_size_bytes,
                t.file_modified_ns,
                ft.title,
                ft.genres_json
            FROM tracks AS t
            JOIN file_tags AS ft ON ft.track_id = t.track_id
            WHERE t.track_id = ?
            """,
            (identity.track_id,),
        ).fetchone()
    assert int(row["content_generation"]) == 1
    assert int(row["file_size_bytes"]) == final_stat.st_size
    assert int(row["file_modified_ns"]) == final_stat.st_mtime_ns
    assert row["title"] == "After Self Write"
    assert json.loads(row["genres_json"]) == ["Deep House"]
    with database.connect_artifacts() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM clap_embeddings WHERE track_id = ?",
                (identity.track_id,),
            ).fetchone()[0]
            == 1
        )
    assert _fts_ids(database, "self") == [identity.track_id]
    assert _fts_ids(database, "before") == []


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("catalog_uuid", "wrong-catalog"),
        ("track_uuid", "wrong-track"),
        ("content_generation", 2),
        ("file_size_bytes", 999_999),
        ("file_modified_ns", 999_999),
    ],
)
def test_self_tag_write_cas_rejects_stale_candidate_before_source_write(
    tmp_path: Path,
    field_name: str,
    replacement: str | int,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    path = tmp_path / "cas.wav"
    _add_track(database, path, title="CAS")
    current = database.get_track_file_state(path)
    assert current is not None
    stale = replace(current, **{field_name: replacement})
    writes: list[Path] = []

    with pytest.raises(RuntimeError):
        database.apply_self_tag_write(
            stale,
            write_source=lambda source_path: writes.append(source_path),
            read_source_tags=lambda _source_path: FileTags(title="CAS"),
            validate_readback=lambda _tags: None,
        )

    assert writes == []
    assert path.read_bytes() == b"CAS"


def test_clear_library_is_database_only_and_preserves_bundle_identity(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first_path = tmp_path / "first.wav"
    second_path = tmp_path / "second.wav"
    first = _add_track(database, first_path, title="First")
    second = _add_track(database, second_path, title="Second")
    original_audio = {
        first_path: first_path.read_bytes(),
        second_path: second_path.read_bytes(),
    }
    _insert_core_state(
        database,
        track_id=first.identity.track_id,
        other_track_id=second.identity.track_id,
    )
    for table in (
        "maest_embeddings",
        "mert_embeddings",
        "muq_embeddings",
        "clap_embeddings",
        "sonara_similarity_embeddings",
    ):
        _insert_artifact(
            database,
            table=table,
            track_id=first.identity.track_id,
            track_uuid=first.identity.track_uuid,
            generation=first.identity.content_generation,
        )
    with database.connect_artifacts() as connection:
        connection.execute(
            """
            INSERT INTO sonara_timeline(
                track_id,
                track_uuid,
                content_generation,
                contract_hash,
                payload_json,
                analyzed_at
            ) VALUES (?, ?, ?, 'timeline-contract', '{}', ?)
            """,
            (
                first.identity.track_id,
                first.identity.track_uuid,
                first.identity.content_generation,
                _NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO sonara_fingerprints(
                track_id,
                track_uuid,
                content_generation,
                contract_hash,
                fingerprint_version,
                word_count,
                byte_order,
                fingerprint_blob,
                analyzed_at
            ) VALUES (?, ?, ?, 'fingerprint-contract', '1', 0, 'little', ?, ?)
            """,
            (
                first.identity.track_id,
                first.identity.track_uuid,
                first.identity.content_generation,
                b"",
                _NOW,
            ),
        )
        connection.commit()
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO library_settings(setting_key, setting_value, updated_at)
            VALUES ('test.active', 'preserve-me', ?)
            """,
            (_NOW,),
        )
        connection.commit()
        contract_count = int(
            connection.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        )
    assert not database.evaluation_path.exists()

    result = database.clear_library()

    assert result == {
        "tracks_deleted": 2,
        "embeddings_deleted": 5,
        "artifacts_deleted": 7,
        "evaluation_rows_deleted": 0,
    }
    assert not database.evaluation_path.exists()
    for path, payload in original_audio.items():
        assert path.read_bytes() == payload
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT catalog_uuid FROM library_catalog").fetchone()[0]
            == database.catalog_uuid
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
            == contract_count
        )
        assert (
            connection.execute(
                """
            SELECT setting_value
            FROM library_settings
            WHERE setting_key = 'test.active'
            """
            ).fetchone()[0]
            == "preserve-me"
        )
    with database.connect_artifacts() as connection:
        for table in (
            "maest_embeddings",
            "mert_embeddings",
            "muq_embeddings",
            "clap_embeddings",
            "sonara_similarity_embeddings",
            "sonara_timeline",
            "sonara_fingerprints",
        ):
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )
        assert (
            connection.execute("SELECT catalog_uuid FROM storage_metadata").fetchone()[
                0
            ]
            == database.catalog_uuid
        )


def test_clear_library_clears_existing_optional_evaluation_payloads(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    evaluation = database.connect_evaluation(create=True)
    assert evaluation is not None
    with evaluation:
        session_id = evaluation.execute(
            """
            INSERT INTO search_sessions(mode, request_json, created_at)
            VALUES ('similarity', '{}', ?)
            """,
            (_NOW,),
        ).lastrowid
        evaluation.execute(
            """
            INSERT INTO search_session_seeds(
                session_id,
                position,
                track_id,
                track_uuid,
                content_generation
            ) VALUES (?, 0, 1, 'track', 1)
            """,
            (session_id,),
        )
        evaluation.execute(
            """
            INSERT INTO search_result_events(
                session_id,
                rank,
                track_id,
                track_uuid,
                content_generation,
                total_score,
                score_breakdown_json,
                created_at
            ) VALUES (?, 0, 1, 'track', 1, 0.5, '{}', ?)
            """,
            (session_id, _NOW),
        )
        evaluation.execute(
            """
            INSERT INTO calibration_runs(
                profile_name,
                search_mode,
                config_json,
                metrics_json,
                created_at
            ) VALUES ('default', 'similarity', '{}', '{}', ?)
            """,
            (_NOW,),
        )
        evaluation.execute(
            """
            INSERT INTO evaluation_settings(
                setting_key,
                value_json,
                updated_at
            ) VALUES ('test', '{}', ?)
            """,
            (_NOW,),
        )
    evaluation.close()

    result = database.clear_library()

    assert result["evaluation_rows_deleted"] == 5
    evaluation = database.connect_evaluation(create=False)
    assert evaluation is not None
    with evaluation:
        for table in (
            "search_session_seeds",
            "search_result_events",
            "search_sessions",
            "calibration_runs",
            "evaluation_settings",
        ):
            assert (
                evaluation.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )
        assert (
            evaluation.execute("SELECT catalog_uuid FROM storage_metadata").fetchone()[
                0
            ]
            == database.catalog_uuid
        )
    evaluation.close()


def test_remove_deleted_track_requires_exact_identity_and_source_absence(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    path = tmp_path / "remove.wav"
    mutation = _add_track(database, path, title="Remove")
    identity = mutation.identity
    _insert_artifact(
        database,
        table="clap_embeddings",
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        generation=identity.content_generation,
    )

    with pytest.raises(RuntimeError, match="still exists"):
        database.remove_deleted_track(
            expected=identity,
            file_path=path,
        )
    assert database.get_track_identity(identity.track_id) == identity

    path.unlink()
    with pytest.raises(RuntimeError, match="identity"):
        database.remove_deleted_track(
            expected=replace(identity, track_uuid="stale-track"),
            file_path=path,
        )

    result = database.remove_deleted_track(
        expected=identity,
        file_path=path,
    )

    assert result.removed
    assert result.core_rows_deleted == 1
    assert result.artifact_rows_deleted == 1
    assert database.get_track_identity(identity.track_id) is None
    with database.connect_artifacts() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM clap_embeddings").fetchone()[0]
            == 0
        )

    retry = database.remove_deleted_track(
        expected=identity,
        file_path=path,
    )
    assert retry.already_absent
    assert retry.core_rows_deleted == 0
    assert retry.artifact_rows_deleted == 0


def test_remove_deleted_track_purges_stale_artifacts_and_preserves_other_track(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    removed = _add_track(
        database,
        tmp_path / "remove-stale.wav",
        title="Remove stale",
    ).identity
    other = _add_track(
        database,
        tmp_path / "preserve.wav",
        title="Preserve",
    ).identity
    artifact_tables = (
        "maest_embeddings",
        "mert_embeddings",
        "muq_embeddings",
        "clap_embeddings",
        "sonara_similarity_embeddings",
        "sonara_timeline",
        "sonara_fingerprints",
    )
    for index, table in enumerate(artifact_tables):
        if index % 2 == 0:
            stale_track_id = removed.track_id
            stale_track_uuid = f"stale-{removed.track_uuid}"
        else:
            stale_track_id = 10_000 + index
            stale_track_uuid = removed.track_uuid
        _insert_artifact(
            database,
            table=table,
            track_id=stale_track_id,
            track_uuid=stale_track_uuid,
            generation=removed.content_generation + 10,
        )
        _insert_artifact(
            database,
            table=table,
            track_id=other.track_id,
            track_uuid=other.track_uuid,
            generation=other.content_generation,
        )

    removed_path = tmp_path / "remove-stale.wav"
    removed_path.unlink()
    result = database.remove_deleted_track(
        expected=removed,
        file_path=removed_path,
    )

    assert result.removed
    assert result.artifact_rows_deleted == len(artifact_tables)
    assert database.get_track_identity(removed.track_id) is None
    assert database.get_track_identity(other.track_id) == other
    with database.connect_artifacts() as connection:
        for table in artifact_tables:
            rows = connection.execute(
                f"""
                SELECT track_id, track_uuid, content_generation
                FROM {table}
                ORDER BY track_id
                """
            ).fetchall()
            assert [tuple(row) for row in rows] == [
                (
                    other.track_id,
                    other.track_uuid,
                    other.content_generation,
                )
            ]


def test_remove_deleted_track_purges_crossed_live_artifact_identities(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    removed = _add_track(
        database,
        tmp_path / "remove-crossed.wav",
        title="Remove crossed",
    ).identity
    crossed = _add_track(
        database,
        tmp_path / "crossed-live.wav",
        title="Crossed live",
    ).identity
    preserved = _add_track(
        database,
        tmp_path / "preserved-live.wav",
        title="Preserved live",
    ).identity
    artifact_tables = (
        "maest_embeddings",
        "mert_embeddings",
        "muq_embeddings",
        "clap_embeddings",
        "sonara_similarity_embeddings",
        "sonara_timeline",
        "sonara_fingerprints",
    )
    for index, table in enumerate(artifact_tables):
        if index % 2 == 0:
            stale_track_id = removed.track_id
            stale_track_uuid = crossed.track_uuid
        else:
            stale_track_id = crossed.track_id
            stale_track_uuid = removed.track_uuid
        _insert_artifact(
            database,
            table=table,
            track_id=stale_track_id,
            track_uuid=stale_track_uuid,
            generation=removed.content_generation,
        )
        _insert_artifact(
            database,
            table=table,
            track_id=preserved.track_id,
            track_uuid=preserved.track_uuid,
            generation=preserved.content_generation,
        )

    removed_path = tmp_path / "remove-crossed.wav"
    removed_path.unlink()
    result = database.remove_deleted_track(
        expected=removed,
        file_path=removed_path,
    )

    assert result.removed
    assert result.artifact_rows_deleted == len(artifact_tables)
    assert database.get_track_identity(removed.track_id) is None
    assert database.get_track_identity(crossed.track_id) == crossed
    assert database.get_track_identity(preserved.track_id) == preserved
    with database.connect_artifacts() as connection:
        for table in artifact_tables:
            rows = connection.execute(
                f"""
                SELECT track_id, track_uuid, content_generation
                FROM {table}
                ORDER BY track_id
                """
            ).fetchall()
            assert [tuple(row) for row in rows] == [
                (
                    preserved.track_id,
                    preserved.track_uuid,
                    preserved.content_generation,
                )
            ]


def test_summary_selection_and_liked_mutation_use_current_identity(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first = _add_track(database, tmp_path / "first.wav", title="First")
    second = _add_track(database, tmp_path / "second.wav", title="Second")

    summaries = database.get_track_summaries(
        (
            second.identity.track_id,
            first.identity.track_id,
            second.identity.track_id,
        )
    )
    assert [summary.title for summary in summaries] == [
        "Second",
        "First",
        "Second",
    ]
    with pytest.raises(KeyError):
        database.get_track_summaries((999_999,))

    liked = database.set_track_liked(
        expected=first.identity,
        liked=True,
    )
    assert liked.liked
    with pytest.raises(RuntimeError, match="different catalog"):
        database.set_track_liked(
            expected=replace(
                first.identity,
                catalog_uuid="wrong-catalog",
            ),
            liked=False,
        )
    with pytest.raises(RuntimeError, match="content generation changed"):
        database.set_track_liked(
            expected=replace(
                first.identity,
                content_generation=2,
            ),
            liked=False,
        )
    assert database.get_track_summaries((first.identity.track_id,))[0].liked


def test_fts_rebuild_indexes_only_human_text_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first = _add_track(
        database,
        tmp_path / "techno" / "midnight-drive.wav",
        title="Midnight Drive",
    )
    second = _add_track(
        database,
        tmp_path / "house" / "sunrise-groove.wav",
        title="Sunrise Groove",
    )
    third = _add_track(
        database,
        tmp_path / "untagged" / "mystery-track-xyzzy.wav",
        title="Temporary Title",
    )
    first_state = database.get_track_file_state(
        tmp_path / "techno" / "midnight-drive.wav"
    )
    second_state = database.get_track_file_state(
        tmp_path / "house" / "sunrise-groove.wav"
    )
    assert first_state is not None
    assert second_state is not None
    database.refresh_file_tags(
        first_state,
        FileTags(
            title="Midnight Drive",
            artist="Artist Alpha",
            album="Dark Frequencies",
            comment="Recorded live",
            year=2026,
            label="Subterranean Records",
            catalog_number="SUB-042",
            country="DE",
            isrc="DEABC2600001",
            track_number="1",
            disc_number="1",
            genres=("Techno", "Industrial"),
        ),
        tags_read_at=_LATER,
    )
    database.refresh_file_tags(
        second_state,
        FileTags(
            title="Sunrise Groove",
            artist="Artist Beta",
            genres=("House", "Deep House"),
        ),
        tags_read_at=_LATER,
    )
    _set_maest_genres(
        database,
        track_id=first.identity.track_id,
        generation=first.identity.content_generation,
        genres=[
            {"genre_name": "Techno", "score": 0.91},
            {"genre_name": "Industrial Techno", "score": 0.72},
        ],
    )
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM file_tags WHERE track_id = ?",
            (third.identity.track_id,),
        )
        first_count = rebuild_track_search_fts(connection)
        second_count = rebuild_track_search_fts(connection)
        columns = {
            item[0]
            for item in connection.execute(
                "SELECT * FROM track_search_fts LIMIT 0"
            ).description
        }

    assert first_count == second_count == 3
    assert _fts_ids(database, "midnight") == [first.identity.track_id]
    assert _fts_ids(database, "alpha") == [first.identity.track_id]
    assert _fts_ids(database, "subterranean") == [first.identity.track_id]
    assert _fts_ids(database, "industrial") == [first.identity.track_id]
    assert _fts_ids(database, "2026") == [first.identity.track_id]
    assert _fts_ids(database, "house") == [second.identity.track_id]
    assert _fts_ids(database, "xyzzy") == [third.identity.track_id]
    assert not _fts_content_contains(
        database,
        _MAEST_ANALYSIS_CONTRACT.contract_hash,
    )
    assert not _fts_content_contains(database, "0.91")
    assert not _fts_content_contains(database, "0.72")
    assert columns == {
        "track_id",
        "file_path",
        "title",
        "artist",
        "album",
        "comment",
        "label",
        "catalog_number",
        "country",
        "isrc",
        "year",
        "track_number",
        "disc_number",
        "file_genres",
        "maest_genres",
    }


def test_fts_rebuild_replaces_changed_maest_genres_and_accepts_strings(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    mutation = _add_track(
        database,
        tmp_path / "evolving.wav",
        title="Evolving Sound",
    )
    _set_maest_genres(
        database,
        track_id=mutation.identity.track_id,
        generation=mutation.identity.content_generation,
        genres=[{"genre_name": "Footwork", "score": 0.85}],
    )
    with database.connect() as connection:
        rebuild_track_search_fts(connection)
    assert _fts_ids(database, "footwork") == [mutation.identity.track_id]
    assert _fts_ids(database, "drone") == []

    _set_maest_genres(
        database,
        track_id=mutation.identity.track_id,
        generation=mutation.identity.content_generation,
        genres=["Drone", "Jungle"],
    )
    with database.connect() as connection:
        rebuild_track_search_fts(connection)

    assert _fts_ids(database, "drone") == [mutation.identity.track_id]
    assert _fts_ids(database, "jungle") == [mutation.identity.track_id]
    assert _fts_ids(database, "footwork") == []


@pytest.mark.parametrize(
    ("file", "tags", "timestamp"),
    [
        (
            ScannedFile("invalid.wav", 1, 1, audio_duration_seconds=float("nan")),
            FileTags(),
            _NOW,
        ),
        (
            ScannedFile("invalid.wav", 1, 1),
            FileTags(tag_bpm=float("inf")),
            _NOW,
        ),
        (
            ScannedFile("invalid.wav", True, 1),
            FileTags(),
            _NOW,
        ),
        (
            ScannedFile("invalid.wav", 1, 1),
            FileTags(),
            "2026-07-23T12:34:56Z",
        ),
    ],
)
def test_invalid_numeric_facts_and_timestamps_are_rejected_before_sqlite(
    tmp_path: Path,
    file: ScannedFile,
    tags: FileTags,
    timestamp: str,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with pytest.raises(ValueError):
        database.upsert_scanned_track(
            file=file,
            tags=tags,
            scanned_at=timestamp,
        )
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0

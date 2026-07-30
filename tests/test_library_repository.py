from __future__ import annotations

import csv
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    ClassifierSpecification,
    current_embedding_spec,
)
from dj_track_similarity.db_connection import (
    connect_artifacts_database,
    connect_database,
    ensure_database_schema,
)
from dj_track_similarity.db_library_queries import LibraryQueryRepository
from dj_track_similarity.db_storage import storage_database_paths
from dj_track_similarity.exporter import export_tracks
from dj_track_similarity.track_models import TrackIdentity


_NOW = "2026-07-24T00:00:00.000000Z"


@dataclass(frozen=True)
class _TrackSeed:
    track_id: int
    track_uuid: str


class _Repository(LibraryQueryRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.artifacts_path = storage_database_paths(self.path).artifacts
        self.catalog_uuid = ensure_database_schema(self.path)
        self._write_lock = threading.RLock()
        self.core_connect_count = 0
        self.artifacts_connect_count = 0
        self.core_statements: list[str] = []
        self.artifact_statements: list[str] = []

    def connect(self) -> sqlite3.Connection:
        self.core_connect_count += 1
        connection = connect_database(
            self.path,
            expected_catalog_uuid=self.catalog_uuid,
        )
        connection.set_trace_callback(self.core_statements.append)
        return connection

    def connect_artifacts(self) -> sqlite3.Connection:
        self.artifacts_connect_count += 1
        connection = connect_artifacts_database(
            self.artifacts_path,
            expected_catalog_uuid=self.catalog_uuid,
        )
        connection.set_trace_callback(self.artifact_statements.append)
        return connection

    def reset_connection_counts(self) -> None:
        self.core_connect_count = 0
        self.artifacts_connect_count = 0

    def reset_sql_trace(self) -> None:
        self.core_statements.clear()
        self.artifact_statements.clear()


@pytest.fixture()
def repository(tmp_path: Path) -> _Repository:
    return _Repository(tmp_path)


@contextmanager
def _core(repository: _Repository) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(repository.path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


@contextmanager
def _artifacts(repository: _Repository) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(repository.artifacts_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _insert_track(
    repository: _Repository,
    *,
    title: str,
    artist: str,
    album: str = "Fixture Album",
    genres: tuple[str, ...] = ("House",),
    maest_fts_genres: str = "",
    missing: bool = False,
) -> _TrackSeed:
    track_uuid = str(uuid.uuid4())
    file_path = f"C:/Music/{artist} - {title}.flac"
    with _core(repository) as core:
        cursor = core.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                audio_format, audio_codec, sample_rate_hz, channel_count,
                bit_rate_bps, audio_duration_seconds, content_generation,
                last_scanned_at, missing_since, created_at, updated_at
            ) VALUES (
                ?, ?, 12345, 987654321, 'flac', 'flac', 44100, 2,
                1411200, 300.0, 1, ?, ?, ?, ?
            )
            """,
            (
                track_uuid,
                file_path,
                _NOW,
                _NOW if missing else None,
                _NOW,
                _NOW,
            ),
        )
        track_id = int(cursor.lastrowid)
        core.execute(
            """
            INSERT INTO file_tags (
                track_id, title, artist, album, tag_bpm, tag_key,
                comment, year, label, country, track_number,
                genres_json, tags_read_at
            ) VALUES (
                ?, ?, ?, ?, 128.0, '8A', 'fixture comment', 2026,
                'Fixture Label', 'UA', '1', ?, ?
            )
            """,
            (
                track_id,
                title,
                artist,
                album,
                json.dumps(genres),
                _NOW,
            ),
        )
        core.execute(
            """
            INSERT INTO track_search_fts (
                track_id, file_path, title, artist, album, comment, label,
                country, year, track_number, file_genres, maest_genres
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                file_path,
                title,
                artist,
                album,
                "fixture comment",
                "Fixture Label",
                "UA",
                "2026",
                "1",
                " ".join(genres),
                maest_fts_genres,
            ),
        )
    return _TrackSeed(track_id=track_id, track_uuid=track_uuid)


def _register_active(
    repository: _Repository,
    *outputs: AnalysisOutput,
) -> None:
    del repository, outputs


def _insert_embedding(
    repository: _Repository,
    *,
    track: _TrackSeed,
    output: AnalysisOutput,
    track_uuid: str | None = None,
    generation: int = 1,
) -> None:
    table = {
        "maest": "maest_embeddings",
        "mert": "mert_embeddings",
        "sonara": "sonara_similarity_embeddings",
    }[output.analysis_family]
    vector = np.zeros(
        current_embedding_spec(output.analysis_family).dimension,
        dtype="<f4",
    )
    vector[0] = 1.0
    with _artifacts(repository) as artifacts:
        artifacts.execute(
            f"""
            INSERT INTO {table} (
                track_id, track_uuid, content_generation,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track.track_id,
                track_uuid or track.track_uuid,
                generation,
                vector.size,
                current_embedding_spec(output.analysis_family).normalization,
                vector.tobytes(order="C"),
                _NOW,
            ),
        )


def _insert_sonara_core(
    repository: _Repository,
    *,
    track: _TrackSeed,
) -> None:
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO sonara (
                track_id, content_generation,
                detected_bpm, detected_key_name, detected_key_camelot,
                energy_score, aggression_score, aggression_confidence,
                aggression_forcefulness, aggression_harshness,
                aggression_tension, aggression_rhythm,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (
                ?, 1, 126.0, 'A minor', '8A', 0.77,
                0.505047082901001, 0.9123457074165344,
                0.6432198286056519, 0.4789124131202698,
                0.731246829032898, 0.8567891120910645,
                ?, ?, ?, ?
            )
            """,
            (
                track.track_id,
                bytes(13 * 4),
                bytes(12 * 4),
                bytes(7 * 4),
                _NOW,
            ),
        )


def _insert_classifier(
    repository: _Repository,
    *,
    track: _TrackSeed,
    classifier_key: str,
    score: float,
) -> None:
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO classifier_scores (
                track_id, track_uuid, classifier_key, content_generation,
                feature_set, feature_names_json, positive_label, predicted_class,
                score_bucket, score, confidence, probabilities_json,
                analyzed_at
            ) VALUES (
                ?, ?, ?, 1, 'mert', '["mert.embedding"]',
                'positive', 'positive', 'high', ?, 0.91, ?, ?
            )
            """,
            (
                track.track_id,
                track.track_uuid,
                classifier_key,
                score,
                json.dumps({"negative": 1.0 - score, "positive": score}),
                _NOW,
            ),
        )


def _classifier_specification(classifier_key: str) -> ClassifierSpecification:
    return ClassifierSpecification(
        classifier_key=classifier_key,
        feature_set="mert",
        feature_names=("mert.embedding",),
        required_outputs=(AnalysisOutput("mert", "embedding"),),
        label_order=("negative", "positive"),
        positive_label="positive",
    )


def _query_plan(path: Path, statement: str) -> tuple[str, ...]:
    with sqlite3.connect(path) as connection:
        return tuple(
            str(row[3])
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN {statement}",
            )
        )


def test_page_and_filters_use_one_validated_bundle_and_human_fts_only(
    repository: _Repository,
) -> None:
    alpha = _insert_track(
        repository,
        title="Alpha",
        artist="Artist A",
        maest_fts_genres="SecretMachineGenre",
    )
    _insert_track(repository, title="Beta", artist="Artist B")
    _insert_track(
        repository,
        title="Missing",
        artist="Artist C",
        missing=True,
    )

    repository.reset_connection_counts()
    page = repository.paginate_track_summaries(limit=1)

    assert page.total == 2
    assert page.limit == 1
    assert [track.track_id for track in page.items] == [alpha.track_id]
    assert page.items[0].catalog_uuid == repository.catalog_uuid
    assert page.items[0].track_uuid == alpha.track_uuid
    assert page.items[0].content_generation == 1
    assert repository.core_connect_count == 1
    assert repository.artifacts_connect_count == 1
    assert (
        repository.paginate_track_summaries(
            query="Alpha",
            search_mode="fts",
        ).total
        == 1
    )
    assert (
        repository.paginate_track_summaries(
            query="SecretMachineGenre",
            search_mode="fts",
        ).total
        == 0
    )
    assert len(repository.list_track_summaries()) == 2
    assert len(repository.list_track_summaries(include_missing=True)) == 3


def test_artifact_readiness_requires_current_uuid_and_generation(
    repository: _Repository,
) -> None:
    current = _insert_track(repository, title="Current", artist="Artist A")
    wrong_uuid = _insert_track(
        repository,
        title="Wrong UUID",
        artist="Artist B",
    )
    output = AnalysisOutput("mert", "embedding")
    _register_active(repository, output)
    _insert_embedding(repository, track=current, output=output)
    _insert_embedding(
        repository,
        track=wrong_uuid,
        output=output,
        track_uuid=str(uuid.uuid4()),
    )

    summaries = {track.track_id: track for track in repository.list_track_summaries()}
    assert summaries[current.track_id].analysis_coverage.mert
    assert not summaries[wrong_uuid.track_id].analysis_coverage.mert

    with _core(repository) as core:
        core.execute(
            """
            UPDATE tracks
            SET content_generation = 2, updated_at = ?
            WHERE track_id = ?
            """,
            (_NOW, current.track_id),
        )
    current_summary = next(
        track
        for track in repository.list_track_summaries()
        if track.track_id == current.track_id
    )
    assert current_summary.catalog_uuid == repository.catalog_uuid
    assert current_summary.track_uuid == current.track_uuid
    assert current_summary.content_generation == 2
    assert not current_summary.analysis_coverage.mert

@pytest.mark.parametrize("malformed_kind", ("zero_l2", "wrong_dim"))
def test_library_coverage_rejects_malformed_embedding_payload(
    repository: _Repository,
    malformed_kind: str,
) -> None:
    track = _insert_track(
        repository,
        title="Malformed",
        artist="Artifact",
    )
    output = AnalysisOutput("mert", "embedding")
    _register_active(repository, output)
    _insert_embedding(repository, track=track, output=output)
    dimension = current_embedding_spec("mert").dimension
    malformed_dim = dimension if malformed_kind == "zero_l2" else dimension - 1
    with _artifacts(repository) as artifacts:
        artifacts.execute(
            """
            UPDATE mert_embeddings
            SET dim = ?, embedding_blob = ?
            WHERE track_id = ?
            """,
            (
                malformed_dim,
                bytes(malformed_dim * 4),
                track.track_id,
            ),
        )

    summary = repository.get_track_summaries((track.track_id,))[0]
    assert not summary.analysis_coverage.mert
    assert repository.get_track_detail(track.track_id).embeddings == ()
    assert repository.library_summary().mert == 0


def test_sonara_rows_are_current_and_validate_artifact_shapes(
    repository: _Repository,
) -> None:
    track = _insert_track(repository, title="SONARA", artist="Artist A")
    _register_active(
        repository,
        AnalysisOutput("sonara", "core"),
        AnalysisOutput("sonara", "timeline"),
        AnalysisOutput("sonara", "fingerprint"),
    )
    _insert_sonara_core(
        repository,
        track=track,
    )
    timeline_payload = {
        "beats": [0, 22, 43],
        "onset_frames": [0, 11, 22, 33, 43],
        "chord_sequence": ["Am", "C", "G"],
        "chord_events": [
            {
                "label": "Am",
                "start_sec": 0.0,
                "end_sec": 1.0,
            }
        ],
        "tempo_curve": [128.0, 128.0],
        "downbeats": [0, 43],
        "energy_curve": [0.2, 0.5, 0.8],
        "segments": [
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "energy": 0.5,
            }
        ],
        "loudness_curve": [-12.0, -10.0, -11.0],
    }
    with _artifacts(repository) as artifacts:
        artifacts.execute(
            """
            INSERT INTO sonara_timeline (
                track_id, track_uuid, content_generation,
                payload_json, analyzed_at
            ) VALUES (?, ?, 1, ?, ?)
            """,
            (
                track.track_id,
                track.track_uuid,
                json.dumps(timeline_payload, separators=(",", ":")),
                _NOW,
            ),
        )
        artifacts.execute(
            """
            INSERT INTO sonara_fingerprints (
                track_id, track_uuid, content_generation,
                fingerprint_version, word_count, byte_order,
                fingerprint_blob, analyzed_at
            ) VALUES (?, ?, 1, '1', 2, 'little', ?, ?)
            """,
            (
                track.track_id,
                track.track_uuid,
                bytes(8),
                _NOW,
            ),
        )

    detail = repository.get_track_detail(track.track_id)

    assert detail.analysis_coverage.sonara_core
    assert detail.analysis_coverage.timeline
    assert detail.analysis_coverage.fingerprint
    assert detail.sonara_core is not None
    assert detail.sonara_core.detected_bpm == 126.0
    assert detail.sonara_core.aggression_score == 0.505047082901001
    assert detail.sonara_core.aggression_confidence == 0.9123457074165344
    assert detail.sonara_core.aggression_forcefulness == 0.6432198286056519
    assert detail.sonara_core.aggression_harshness == 0.4789124131202698
    assert detail.sonara_core.aggression_tension == 0.731246829032898
    assert detail.sonara_core.aggression_rhythm == 0.8567891120910645
    assert detail.optional_outputs.timeline_fields == tuple(timeline_payload)
    assert detail.optional_outputs.audio_fingerprint_available
    assert repository.load_sonara_timeline(track.track_id) == timeline_payload

    with _artifacts(repository) as artifacts:
        artifacts.execute(
            """
            UPDATE sonara_fingerprints
            SET fingerprint_version = ''
            WHERE track_id = ?
            """,
            (track.track_id,),
        )

    malformed = repository.get_track_detail(track.track_id)
    assert not malformed.analysis_coverage.fingerprint
    assert not malformed.optional_outputs.audio_fingerprint_available


def test_maest_analysis_and_embedding_have_independent_readiness(
    repository: _Repository,
) -> None:
    analysis_only = _insert_track(
        repository,
        title="Analysis",
        artist="Artist A",
    )
    embedding_only = _insert_track(
        repository,
        title="Embedding",
        artist="Artist B",
    )
    analysis_output = AnalysisOutput("maest", "analysis")
    embedding_output = AnalysisOutput("maest", "embedding")
    _register_active(
        repository,
        analysis_output,
        embedding_output,
    )
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO maest_scores (
                track_id, content_generation,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, 1, 1, ?, ?)
            """,
            (
                analysis_only.track_id,
                '[{"label":"Techno","score":0.9}]',
                _NOW,
            ),
        )
    _insert_embedding(
        repository,
        track=embedding_only,
        output=embedding_output,
    )

    summaries = {track.track_id: track for track in repository.list_track_summaries()}
    assert summaries[analysis_only.track_id].analysis_coverage.maest_analysis
    assert not summaries[analysis_only.track_id].analysis_coverage.maest_embedding
    assert not summaries[embedding_only.track_id].analysis_coverage.maest_analysis
    assert summaries[embedding_only.track_id].analysis_coverage.maest_embedding
    assert "maest" not in summaries[analysis_only.track_id].analysis_coverage.as_dict()
    assert repository.library_summary().as_dict() == {
        "tracks": 2,
        "sonara": 0,
        "maest_analysis": 1,
        "maest_embedding": 1,
        "mert": 0,
        "muq": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
    }


def test_likes_and_exports_preserve_requested_order(
    repository: _Repository,
    tmp_path: Path,
) -> None:
    first = _insert_track(repository, title="First", artist="Artist A")
    second = _insert_track(repository, title="Second", artist="Artist B")
    missing = _insert_track(
        repository,
        title="Missing",
        artist="Artist C",
        missing=True,
    )

    second_identity = TrackIdentity(
        catalog_uuid=repository.catalog_uuid,
        track_id=second.track_id,
        track_uuid=second.track_uuid,
        content_generation=1,
    )
    liked = repository.set_track_liked(
        expected=second_identity,
        liked=True,
    )
    assert liked.liked
    assert repository.list_liked_track_ids() == (second.track_id,)
    with pytest.raises(RuntimeError, match="content generation changed"):
        repository.set_track_liked(
            expected=TrackIdentity(
                catalog_uuid=repository.catalog_uuid,
                track_id=second.track_id,
                track_uuid=second.track_uuid,
                content_generation=2,
            ),
            liked=False,
        )
    assert repository.list_liked_track_ids() == (second.track_id,)

    rows = repository.export_track_rows(
        (second.track_id, first.track_id, second.track_id)
    )
    assert [row.track_id for row in rows] == [
        second.track_id,
        first.track_id,
        second.track_id,
    ]
    with pytest.raises(KeyError, match=str(missing.track_id)):
        repository.export_track_rows((first.track_id, missing.track_id))

    m3u_path = export_tracks("ordered set", rows, tmp_path, "m3u")
    m3u_lines = m3u_path.read_text(encoding="utf-8").splitlines()
    assert m3u_lines[2::2] == [
        rows[0].file_path,
        rows[1].file_path,
        rows[2].file_path,
    ]
    csv_path = export_tracks("ordered set", rows, tmp_path, "csv")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert [row["title"] for row in exported] == [
        "Second",
        "First",
        "Second",
    ]


def test_summary_and_classifier_filters_use_current_rows(
    repository: _Repository,
) -> None:
    first = _insert_track(repository, title="First", artist="Artist A")
    _insert_track(repository, title="Second", artist="Artist B")
    maest = AnalysisOutput("maest", "analysis")
    mert = AnalysisOutput("mert", "embedding")
    _register_active(repository, maest, mert)
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO maest_scores (
                track_id, content_generation,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, 1, 1, ?, ?)
            """,
            (
                first.track_id,
                '[{"label":"Techno","score":0.9}]',
                _NOW,
            ),
        )
    _insert_embedding(repository, track=first, output=mert)
    _insert_classifier(
        repository,
        track=first,
        classifier_key="voice_presence",
        score=0.82,
    )

    filtered = repository.filter_track_summaries(
        classifier_min_scores={"voice_presence": 0.8},
        classifier_specifications=(_classifier_specification("voice_presence"),),
    )
    assert [track.track_id for track in filtered] == [first.track_id]
    assert (
        repository.filter_track_summaries(
            syncopated_only=True,
        )[0].track_id
        == first.track_id
    )
    tag_candidates = repository.list_genre_tag_candidates()
    assert len(tag_candidates) == 1
    assert tag_candidates[0].track_id == first.track_id
    assert tag_candidates[0].content_generation == 1
    assert tag_candidates[0].expected_file_size_bytes == 12345
    assert tag_candidates[0].expected_file_modified_ns == 987654321
    assert tag_candidates[0].genres == ("Techno",)

    summary = repository.library_summary(
        classifier_keys=("voice_presence",),
        classifier_specifications=(_classifier_specification("voice_presence"),),
    )
    assert summary.as_dict() == {
        "tracks": 2,
        "sonara": 0,
        "maest_analysis": 1,
        "maest_embedding": 0,
        "mert": 1,
        "muq": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 1,
    }


def test_page_artifact_hydration_is_bounded_and_uses_requested_rowids(
    repository: _Repository,
) -> None:
    tracks = tuple(
        _insert_track(
            repository,
            title=f"Track {index:02d}",
            artist="Artifact Artist",
        )
        for index in range(6)
    )
    output = AnalysisOutput("mert", "embedding")
    _register_active(repository, output)
    for track in tracks:
        _insert_embedding(repository, track=track, output=output)

    repository.reset_sql_trace()
    page = repository.paginate_track_summaries(limit=3)

    assert page.total == len(tracks)
    assert len(page.items) == 3
    assert all(track.analysis_coverage.mert for track in page.items)
    hydration_statements = [
        statement
        for statement in repository.artifact_statements
        if "CROSS JOIN mert_embeddings stored" in statement
    ]
    assert len(hydration_statements) == 1
    plan = _query_plan(repository.artifacts_path, hydration_statements[0])
    assert any("SCAN requested VIRTUAL TABLE" in detail for detail in plan)
    assert any(
        "SEARCH stored USING INTEGER PRIMARY KEY (rowid=?)" in detail
        for detail in plan
    )
    assert not any(
        "idx_mert_embeddings_generation" in detail
        for detail in plan
    )

    repository.reset_sql_trace()
    assert repository.library_summary().mert == len(tracks)
    full_summary_statement = next(
        statement
        for statement in repository.artifact_statements
        if "FROM mert_embeddings" in statement
    )
    assert "CROSS JOIN mert_embeddings" not in full_summary_statement
    assert _query_plan(repository.artifacts_path, full_summary_statement)

    repository.reset_sql_trace()
    repository.paginate_track_summaries(limit=1)
    one_row_selects = sum(
        statement.lstrip().upper().startswith("SELECT")
        for statement in repository.core_statements
    ) + sum(
        statement.lstrip().upper().startswith("SELECT")
        for statement in repository.artifact_statements
    )
    repository.reset_sql_trace()
    repository.paginate_track_summaries(limit=6)
    six_row_selects = sum(
        statement.lstrip().upper().startswith("SELECT")
        for statement in repository.core_statements
    ) + sum(
        statement.lstrip().upper().startswith("SELECT")
        for statement in repository.artifact_statements
    )
    assert one_row_selects == six_row_selects


def test_classifier_filter_uses_lookup_index_and_preserves_multi_filter_order(
    repository: _Repository,
) -> None:
    high_voice = _insert_track(
        repository,
        title="High voice",
        artist="Classifier Artist",
    )
    high_both = _insert_track(
        repository,
        title="High both",
        artist="Classifier Artist",
    )
    second_both = _insert_track(
        repository,
        title="Second both",
        artist="Classifier Artist",
    )
    stale = _insert_track(
        repository,
        title="Stale",
        artist="Classifier Artist",
    )
    _register_active(repository, AnalysisOutput("mert", "embedding"))
    for track, voice, arousal in (
        (high_voice, 0.99, 0.70),
        (high_both, 0.86, 0.95),
        (second_both, 0.81, 0.90),
        (stale, 1.00, 1.00),
    ):
        _insert_classifier(
            repository,
            track=track,
            classifier_key="voice_presence",
            score=voice,
        )
        _insert_classifier(
            repository,
            track=track,
            classifier_key="arousal",
            score=arousal,
        )
    with _core(repository) as core:
        core.execute(
            """
            UPDATE tracks
            SET content_generation = 2, updated_at = ?
            WHERE track_id = ?
            """,
            (_NOW, stale.track_id),
        )

    specifications = (
        _classifier_specification("voice_presence"),
        _classifier_specification("arousal"),
    )
    repository.reset_sql_trace()
    single = repository.filter_track_summaries(
        classifier_min_scores={"voice_presence": 0.8},
        classifier_specifications=specifications,
    )
    assert [track.track_id for track in single] == [
        high_voice.track_id,
        high_both.track_id,
        second_both.track_id,
    ]

    driving_statements = [
        statement
        for statement in repository.core_statements
        if "INDEXED BY idx_classifier_scores_lookup" in statement
    ]
    assert len(driving_statements) == 2
    for statement in driving_statements:
        plan = _query_plan(repository.path, statement)
        assert any(
            "SEARCH primary_cs USING INDEX idx_classifier_scores_lookup"
            in detail
            for detail in plan
        )
        assert any(
            "SEARCH t USING INTEGER PRIMARY KEY (rowid=?)" in detail
            for detail in plan
        )
    result_statement = next(
        statement
        for statement in driving_statements
        if "ORDER BY" in statement
    )
    assert "primary_cs.score DESC" in result_statement
    assert "SELECT cs.score" not in result_statement

    multi = repository.filter_track_summaries(
        classifier_min_scores={
            "voice_presence": 0.8,
            "arousal": 0.8,
        },
        classifier_specifications=specifications,
    )
    assert [track.track_id for track in multi] == [
        high_both.track_id,
        second_both.track_id,
    ]

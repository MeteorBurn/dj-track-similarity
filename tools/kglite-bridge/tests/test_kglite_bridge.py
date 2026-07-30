from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest


TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from kglite_bridge import (  # noqa: E402
    BridgeError,
    BuildOptions,
    build_projection,
    write_kglite_graph,
)
from dj_track_similarity.analysis_models import current_embedding_spec  # noqa: E402
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema  # noqa: E402
from dj_track_similarity.db_ddl import create_core_schema  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _insert_track(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    track_uuid: str,
    path: Path,
    generation: int,
    title: str,
    artist: str,
    genres_json: str,
    liked: bool = False,
) -> None:
    connection.execute(
        """
        INSERT INTO tracks (
            track_id, track_uuid, file_path, file_size_bytes,
            file_modified_ns, audio_format, audio_codec, sample_rate_hz,
            channel_count, bit_rate_bps, audio_duration_seconds,
            content_generation, last_scanned_at, missing_since,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'wav', 'pcm_s16le', 44100, 2, 1411200,
                  30.0, ?, ?, NULL, ?, ?)
        """,
        (
            track_id,
            track_uuid,
            str(path),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            generation,
            "2026-01-01T00:00:00.000000Z",
            "2026-01-01T00:00:00.000000Z",
            "2026-01-01T00:00:00.000000Z",
        ),
    )
    connection.execute(
        """
        INSERT INTO file_tags (
            track_id, title, artist, album, tag_bpm, tag_key,
            comment, year, label, catalog_number, country, isrc,
            track_number, disc_number, genres_json, tags_read_at
        ) VALUES (?, ?, ?, 'Fixture Album', 128.0, '8A',
                  NULL, 2026, NULL, NULL, NULL, NULL,
                  NULL, NULL, ?, ?)
        """,
        (
            track_id,
            title,
            artist,
            genres_json,
            "2026-01-01T00:00:00.000000Z",
        ),
    )
    if liked:
        connection.execute(
            "INSERT INTO likes(track_id, liked_at) VALUES (?, ?)",
            (track_id, "2026-01-01T00:00:00.000000Z"),
        )


def _fixture_bundle(
    tmp_path: Path,
) -> tuple[Path, Path, tuple[Path, ...], int]:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = tmp_path / "library.artifacts.sqlite"
    audio_paths: list[Path] = []
    for index in range(1, 6):
        audio_path = tmp_path / f"track-{index}.wav"
        audio_path.write_bytes(f"dummy-audio-{index}".encode("ascii"))
        audio_paths.append(audio_path)

    catalog_uuid = "11111111-2222-3333-4444-555555555555"
    dimension = current_embedding_spec("mert").dimension
    with sqlite3.connect(core_path) as core:
        create_core_schema(core)
        core.execute(
            """
            INSERT INTO library_catalog(
                singleton_id, catalog_uuid, created_at, updated_at
            ) VALUES (1, ?, ?, ?)
            """,
            (
                catalog_uuid,
                "2026-01-01T00:00:00.000000Z",
                "2026-01-01T00:00:00.000000Z",
            ),
        )
        fixtures = [
            (1, "track-uuid-1", 1, "One", "Artist A", '["House", "Techno"]', True),
            (2, "track-uuid-2", 1, "Two", "Artist A", '["House"]', False),
            (3, "track-uuid-3", 1, "Three", "Artist B", '["Ambient"]', False),
            (4, "track-uuid-4", 2, "Stale", "Artist B", '["Ambient"]', False),
            (5, "track-uuid-5", 1, "Inactive", "Artist B", '["Ambient"]', False),
        ]
        for index, track_uuid, generation, title, artist, genres, liked in fixtures:
            _insert_track(
                core,
                track_id=index,
                track_uuid=track_uuid,
                path=audio_paths[index - 1],
                generation=generation,
                title=title,
                artist=artist,
                genres_json=genres,
                liked=liked,
            )
        core.commit()

    create_artifacts_sidecar_schema(str(artifacts_path), catalog_uuid)
    vectors = {}
    for track_id, leading in {
        1: (1.0, 0.0),
        2: (0.8, 0.6),
        3: (-1.0, 0.0),
        4: (0.0, 1.0),
        5: (0.0, -1.0),
    }.items():
        vector = np.zeros(dimension, dtype="<f4")
        vector[:2] = leading
        vectors[track_id] = vector
    with sqlite3.connect(artifacts_path) as artifacts:
        for track_id, vector in vectors.items():
            generation = 1
            artifacts.execute(
                """
                INSERT INTO mert_embeddings(
                    track_id, track_uuid, content_generation,
                    dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    f"track-uuid-{track_id}",
                    generation,
                    dimension,
                    "none" if track_id == 5 else "l2",
                    vector.tobytes(),
                    "2026-01-01T00:00:00.000000Z",
                ),
            )
        artifacts.commit()
    return core_path, artifacts_path, tuple(audio_paths), dimension


def test_projection_is_current_only_deterministic_and_read_only(tmp_path: Path) -> None:
    core_path, artifacts_path, audio_paths, _dimension = _fixture_bundle(tmp_path)
    before = {path: _sha256(path) for path in (core_path, artifacts_path, *audio_paths)}
    options = BuildOptions(
        core_path=core_path,
        artifacts_path=artifacts_path,
        sources=("mert",),
        top_k=1,
        min_score=-1.0,
        integrity_check=True,
    )

    first = build_projection(options)
    second = build_projection(options)

    assert first.report.projection_digest == second.report.projection_digest
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.report.selected_sources == ("mert",)
    assert first.report.nodes_by_type["Track"] == 5
    assert first.report.edges_by_type["SIMILAR_MERT"] == 3
    source = first.report.source_reports[0]
    assert source.total_rows == 5
    assert source.valid_vectors == 3
    assert source.stale_rows == 1
    assert source.invalid_rows == 1
    assert all(
        "embedding" not in key for node in first.nodes for key in node.properties
    )
    assert {
        edge.properties["rank"]
        for edge in first.edges
        if edge.relationship == "SIMILAR_MERT"
    } == {1}
    assert before == {
        path: _sha256(path) for path in (core_path, artifacts_path, *audio_paths)
    }


@pytest.mark.skipif(
    importlib.util.find_spec("kglite") is None,
    reason="optional kglite module is not installed",
)
def test_writes_reloadable_kgl_without_mutating_inputs(tmp_path: Path) -> None:
    import kglite

    core_path, artifacts_path, audio_paths, _dimension = _fixture_bundle(tmp_path)
    before = {path: _sha256(path) for path in (core_path, artifacts_path, *audio_paths)}
    projection = build_projection(
        BuildOptions(
            core_path=core_path,
            artifacts_path=artifacts_path,
            sources=("mert",),
            top_k=1,
            min_score=-1.0,
        )
    )
    output = tmp_path / "library.kgl"
    second_output = tmp_path / "library-second.kgl"

    written = write_kglite_graph(
        projection,
        output,
        core_path=core_path,
        artifacts_path=artifacts_path,
    )
    write_kglite_graph(
        projection,
        second_output,
        core_path=core_path,
        artifacts_path=artifacts_path,
    )

    assert written == output.resolve()
    second_graph = kglite.load(str(second_output))
    try:
        second_projection_row = second_graph.cypher(
            "MATCH (p:Projection) RETURN p.projection_digest AS digest"
        ).to_list()
    finally:
        close = getattr(second_graph, "close", None)
        if callable(close):
            close()
    assert second_projection_row == [{"digest": projection.report.projection_digest}]
    graph = kglite.load(str(output))
    try:
        routes = graph.cypher(
            """
            MATCH (a:Track)-[r:SIMILAR_MERT]->(b:Track)
            RETURN a.track_uuid AS seed, b.track_uuid AS candidate,
                   r.rank AS rank
            ORDER BY seed
            """
        ).to_list()
        projection_row = graph.cypher(
            "MATCH (p:Projection) RETURN p.projection_digest AS digest"
        ).to_list()
    finally:
        close = getattr(graph, "close", None)
        if callable(close):
            close()
    assert len(routes) == 3
    assert all(row["rank"] == 1 for row in routes)
    assert projection_row == [{"digest": projection.report.projection_digest}]
    assert before == {
        path: _sha256(path) for path in (core_path, artifacts_path, *audio_paths)
    }


def test_refuses_output_that_is_an_input(tmp_path: Path) -> None:
    core_path, artifacts_path, _audio_paths, _dimension = _fixture_bundle(tmp_path)
    projection = build_projection(
        BuildOptions(
            core_path=core_path,
            artifacts_path=artifacts_path,
            sources=("mert",),
            top_k=1,
            min_score=-1.0,
        )
    )

    unsafe_core = tmp_path / "core-input.kgl"
    unsafe_core.write_bytes(core_path.read_bytes())
    with pytest.raises(BridgeError, match="must not replace Core"):
        write_kglite_graph(
            projection,
            unsafe_core,
            core_path=unsafe_core,
            artifacts_path=artifacts_path,
        )


def test_catalog_binding_mismatch_fails_closed(tmp_path: Path) -> None:
    core_path, artifacts_path, _audio_paths, _dimension = _fixture_bundle(tmp_path)
    replacement = tmp_path / "other.artifacts.sqlite"
    create_artifacts_sidecar_schema(
        str(replacement), "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )

    with pytest.raises(BridgeError, match="catalog_uuid binding mismatch"):
        build_projection(
            BuildOptions(
                core_path=core_path,
                artifacts_path=replacement,
                sources=("mert",),
            )
        )

    assert artifacts_path.exists()


def test_structurally_invalid_sonara_vector_is_not_projected(
    tmp_path: Path,
) -> None:
    core_path, artifacts_path, _audio_paths, _dimension = _fixture_bundle(tmp_path)
    vector = np.asarray([1.0, 0.0], dtype="<f4")
    with sqlite3.connect(artifacts_path) as artifacts:
        artifacts.execute(
            """
            INSERT INTO sonara_similarity_embeddings(
                track_id, track_uuid, content_generation, dim,
                normalization, embedding_blob, analyzed_at
            ) VALUES(1, 'track-uuid-1', 1, 2, 'l2', ?, ?)
            """,
            (vector.tobytes(), "2026-01-01T00:00:00.000000Z"),
        )
        artifacts.commit()

    projection = build_projection(
        BuildOptions(
            core_path=core_path,
            artifacts_path=artifacts_path,
            sources=("sonara",),
        )
    )

    report = projection.report.source_reports[0]
    assert report.family == "sonara"
    assert report.invalid_rows == 1
    assert report.valid_vectors == 0
    assert "SIMILAR_SONARA" not in projection.report.edges_by_type

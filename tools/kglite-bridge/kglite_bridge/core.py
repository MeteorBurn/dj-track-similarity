"""Deterministic read-only projection of a DJ library into KGLite.

SQLite remains authoritative. This module pins query-only snapshots of Core
and Artifacts, validates every exported embedding against current identity,
and builds a disposable metadata/similarity graph. It never opens audio files
and never stores raw embeddings in KGLite.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterator, Mapping, Sequence
import unicodedata

import numpy as np

from dj_track_similarity.analysis_models import current_embedding_spec


SUPPORTED_SOURCES = ("maest", "mert", "muq", "clap")
SOURCE_TABLES: Mapping[str, str] = {
    "maest": "maest_embeddings",
    "mert": "mert_embeddings",
    "muq": "muq_embeddings",
    "clap": "clap_embeddings",
}
SOURCE_RELATIONSHIPS: Mapping[str, str] = {
    source: f"SIMILAR_{source.upper()}" for source in SUPPORTED_SOURCES
}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
class BridgeError(RuntimeError):
    """The requested projection is unsafe or inconsistent."""


@dataclass(frozen=True)
class BuildOptions:
    """Validated projection controls."""

    core_path: Path
    artifacts_path: Path | None = None
    sources: tuple[str, ...] | None = None
    top_k: int = 10
    min_score: float = 0.0
    include_paths: bool = True
    integrity_check: bool = False
    similarity_block_size: int = 512

    def normalized(self) -> "BuildOptions":
        core_path = Path(self.core_path).expanduser().resolve()
        artifacts_path = (
            Path(self.artifacts_path).expanduser().resolve()
            if self.artifacts_path is not None
            else core_path.with_name(f"{core_path.stem}.artifacts{core_path.suffix}")
        )
        if isinstance(self.top_k, bool) or not 1 <= int(self.top_k) <= 100:
            raise BridgeError("top_k must be an integer between 1 and 100")
        min_score = float(self.min_score)
        if not math.isfinite(min_score) or not -1.0 <= min_score <= 1.0:
            raise BridgeError("min_score must be finite and between -1 and 1")
        if (
            isinstance(self.similarity_block_size, bool)
            or not 1 <= int(self.similarity_block_size) <= 8192
        ):
            raise BridgeError("similarity_block_size must be between 1 and 8192")
        sources = None
        if self.sources is not None:
            requested: list[str] = []
            for source in self.sources:
                normalized = str(source).strip().lower()
                if normalized not in SUPPORTED_SOURCES:
                    raise BridgeError(f"unsupported embedding source: {source!r}")
                if normalized not in requested:
                    requested.append(normalized)
            sources = tuple(
                source for source in SUPPORTED_SOURCES if source in requested
            )
        return BuildOptions(
            core_path=core_path,
            artifacts_path=artifacts_path,
            sources=sources,
            top_k=int(self.top_k),
            min_score=min_score,
            include_paths=bool(self.include_paths),
            integrity_check=bool(self.integrity_check),
            similarity_block_size=int(self.similarity_block_size),
        )


@dataclass(frozen=True)
class GraphNode:
    node_type: str
    node_id: str
    properties: Mapping[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    relationship: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingSource:
    family: str
    dimension: int
    normalization: str


@dataclass(frozen=True)
class SourceReport:
    family: str
    total_rows: int
    invalid_rows: int
    stale_rows: int
    valid_vectors: int
    similarity_edges: int


@dataclass(frozen=True)
class ProjectionReport:
    projection_digest: str
    catalog_uuid: str
    selected_sources: tuple[str, ...]
    node_count: int
    edge_count: int
    nodes_by_type: Mapping[str, int]
    edges_by_type: Mapping[str, int]
    source_reports: tuple[SourceReport, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_sources"] = list(self.selected_sources)
        return payload


@dataclass(frozen=True)
class Projection:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    report: ProjectionReport


@dataclass(frozen=True)
class _Track:
    track_id: int
    track_uuid: str
    file_path: str
    file_size_bytes: int
    audio_format: str | None
    duration_seconds: float | None
    content_generation: int
    title: str
    artist: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    year: int | None
    genres: tuple[str, ...]
    liked: bool


@contextmanager
def _read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
    if not path.is_file():
        raise BridgeError(f"SQLite input does not exist: {path}")
    uri = f"{path.as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise BridgeError(
            f"cannot open SQLite input read-only: {path}: {error}"
        ) from error
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        yield connection
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def _require_tables(
    connection: sqlite3.Connection, names: Sequence[str], label: str
) -> None:
    present = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    missing = sorted(set(names) - present)
    if missing:
        raise BridgeError(f"{label} is missing required tables: {', '.join(missing)}")


def _check_integrity(connection: sqlite3.Connection, label: str) -> None:
    rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
    if rows != ["ok"]:
        raise BridgeError(f"{label} quick_check failed: {rows}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalize_label(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _value_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(_normalize_label(value).encode("utf-8")).hexdigest()
    return f"{prefix}:sha256:{digest}"


def _track_node_id(catalog_uuid: str, track_uuid: str) -> str:
    return f"track:{catalog_uuid}:{track_uuid}"


def _read_embedding_sources(
    artifacts: sqlite3.Connection,
    requested_sources: tuple[str, ...] | None,
) -> tuple[EmbeddingSource, ...]:
    available = tuple(
        source
        for source in SUPPORTED_SOURCES
        if artifacts.execute(
            f"SELECT 1 FROM {SOURCE_TABLES[source]} LIMIT 1"
        ).fetchone()
        is not None
    )
    selected = available if requested_sources is None else requested_sources
    sources: list[EmbeddingSource] = []
    for source in selected:
        specification = current_embedding_spec(source)
        sources.append(
            EmbeddingSource(
                family=source,
                dimension=specification.dimension,
                normalization=specification.normalization,
            )
        )
    return tuple(sources)


def _read_tracks(core: sqlite3.Connection) -> tuple[_Track, ...]:
    rows = core.execute(
        """
        SELECT
            t.track_id, t.track_uuid, t.file_path, t.file_size_bytes,
            t.audio_format, t.audio_duration_seconds, t.content_generation,
            ft.title, ft.artist, ft.album, ft.tag_bpm, ft.tag_key, ft.year,
            ft.genres_json,
            CASE WHEN l.track_id IS NULL THEN 0 ELSE 1 END AS liked
        FROM tracks AS t
        LEFT JOIN file_tags AS ft ON ft.track_id = t.track_id
        LEFT JOIN likes AS l ON l.track_id = t.track_id
        WHERE t.missing_since IS NULL
        ORDER BY t.track_uuid
        """
    ).fetchall()
    tracks: list[_Track] = []
    for row in rows:
        try:
            raw_genres = json.loads(str(row["genres_json"] or "[]"))
        except json.JSONDecodeError as error:
            raise BridgeError(
                f"track {row['track_uuid']} has invalid genres_json"
            ) from error
        if not isinstance(raw_genres, list):
            raise BridgeError(f"track {row['track_uuid']} genres_json is not an array")
        genres_by_key: dict[str, str] = {}
        for raw_genre in raw_genres:
            if not isinstance(raw_genre, str):
                raise BridgeError(f"track {row['track_uuid']} has a non-string genre")
            genre = raw_genre.strip()
            if genre:
                genres_by_key.setdefault(_normalize_label(genre), genre)
        path = str(row["file_path"])
        stored_title = None if row["title"] is None else str(row["title"]).strip()
        tracks.append(
            _Track(
                track_id=int(row["track_id"]),
                track_uuid=str(row["track_uuid"]),
                file_path=path,
                file_size_bytes=int(row["file_size_bytes"]),
                audio_format=None
                if row["audio_format"] is None
                else str(row["audio_format"]),
                duration_seconds=(
                    None
                    if row["audio_duration_seconds"] is None
                    else float(row["audio_duration_seconds"])
                ),
                content_generation=int(row["content_generation"]),
                title=stored_title or Path(path).stem,
                artist=None
                if row["artist"] is None
                else str(row["artist"]).strip() or None,
                album=None
                if row["album"] is None
                else str(row["album"]).strip() or None,
                tag_bpm=None if row["tag_bpm"] is None else float(row["tag_bpm"]),
                tag_key=None if row["tag_key"] is None else str(row["tag_key"]),
                year=None if row["year"] is None else int(row["year"]),
                genres=tuple(genres_by_key[key] for key in sorted(genres_by_key)),
                liked=bool(row["liked"]),
            )
        )
    return tuple(tracks)


def _read_vectors(
    core_tracks: Mapping[int, _Track],
    artifacts: sqlite3.Connection,
    source: EmbeddingSource,
) -> tuple[tuple[str, ...], np.ndarray, SourceReport]:
    table = SOURCE_TABLES[source.family]
    rows = artifacts.execute(
        f"""
        SELECT track_id, track_uuid, content_generation, dim,
               normalization, embedding_blob
        FROM {table}
        ORDER BY track_uuid, track_id
        """
    ).fetchall()
    invalid_rows = 0
    stale_rows = 0
    vectors: list[tuple[str, np.ndarray]] = []
    for row in rows:
        track = core_tracks.get(int(row["track_id"]))
        if (
            track is None
            or str(row["track_uuid"]) != track.track_uuid
            or int(row["content_generation"]) != track.content_generation
        ):
            stale_rows += 1
            continue
        if (
            int(row["dim"]) != source.dimension
            or str(row["normalization"]) != source.normalization
        ):
            invalid_rows += 1
            continue
        blob = row["embedding_blob"]
        if not isinstance(blob, bytes) or len(blob) != source.dimension * 4:
            invalid_rows += 1
            continue
        vector = np.frombuffer(blob, dtype="<f4").copy()
        if vector.shape != (source.dimension,) or not bool(np.all(np.isfinite(vector))):
            invalid_rows += 1
            continue
        norm = float(np.linalg.norm(vector))
        if not math.isfinite(norm) or norm <= 0.0:
            invalid_rows += 1
            continue
        if source.normalization == "l2" and not bool(
            np.isclose(norm, 1.0, rtol=1e-4, atol=1e-5)
        ):
            invalid_rows += 1
            continue
        vectors.append((track.track_uuid, vector))
    vectors.sort(key=lambda item: item[0])
    track_uuids = tuple(item[0] for item in vectors)
    matrix = (
        np.stack([item[1] for item in vectors]).astype(np.float32, copy=False)
        if vectors
        else np.empty((0, source.dimension), dtype=np.float32)
    )
    report = SourceReport(
        family=source.family,
        total_rows=len(rows),
        invalid_rows=invalid_rows,
        stale_rows=stale_rows,
        valid_vectors=len(vectors),
        similarity_edges=0,
    )
    return track_uuids, matrix, report


def _similarity_edges(
    *,
    catalog_uuid: str,
    source: EmbeddingSource,
    track_uuids: tuple[str, ...],
    matrix: np.ndarray,
    tracks_by_uuid: Mapping[str, _Track],
    top_k: int,
    min_score: float,
    block_size: int,
) -> list[GraphEdge]:
    count = len(track_uuids)
    if count < 2:
        return []
    norms = np.linalg.norm(matrix, axis=1)
    normalized = matrix / norms[:, None]
    edges: list[GraphEdge] = []
    relationship = SOURCE_RELATIONSHIPS[source.family]
    for start in range(0, count, block_size):
        stop = min(start + block_size, count)
        scores_block = normalized[start:stop] @ normalized.T
        scores_block = np.round(np.clip(scores_block, -1.0, 1.0), decimals=8)
        for offset, scores in enumerate(scores_block):
            seed_index = start + offset
            scores[seed_index] = -np.inf
            eligible = np.flatnonzero(scores >= min_score)
            if eligible.size == 0:
                continue
            limit = min(top_k, int(eligible.size))
            if eligible.size > limit:
                local = scores[eligible]
                partition = np.argpartition(-local, limit - 1)[:limit]
                threshold = float(np.min(local[partition]))
                eligible = eligible[local >= threshold]
            ordered = sorted(
                (int(index) for index in eligible),
                key=lambda index: (-float(scores[index]), track_uuids[index]),
            )[:limit]
            seed_uuid = track_uuids[seed_index]
            seed_track = tracks_by_uuid[seed_uuid]
            for rank, target_index in enumerate(ordered, start=1):
                target_uuid = track_uuids[target_index]
                target_track = tracks_by_uuid[target_uuid]
                edges.append(
                    GraphEdge(
                        relationship=relationship,
                        source_type="Track",
                        source_id=_track_node_id(catalog_uuid, seed_uuid),
                        target_type="Track",
                        target_id=_track_node_id(catalog_uuid, target_uuid),
                        properties={
                            "source_family": source.family,
                            "score": float(scores[target_index]),
                            "rank": rank,
                            "seed_content_generation": seed_track.content_generation,
                            "target_content_generation": target_track.content_generation,
                        },
                    )
                )
    return edges


def _base_graph(
    *,
    catalog_uuid: str,
    tracks: tuple[_Track, ...],
    include_paths: bool,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    catalog_id = f"catalog:{catalog_uuid}"
    nodes: list[GraphNode] = [
        GraphNode(
            node_type="Catalog",
            node_id=catalog_id,
            properties={
                "title": "DJ library",
                "catalog_uuid": catalog_uuid,
            },
        )
    ]
    edges: list[GraphEdge] = []
    artists: dict[str, GraphNode] = {}
    genres: dict[str, GraphNode] = {}
    liked_tracks = [track for track in tracks if track.liked]
    liked_collection_id = f"collection:{catalog_uuid}:liked"
    if liked_tracks:
        nodes.append(
            GraphNode(
                node_type="Collection",
                node_id=liked_collection_id,
                properties={
                    "title": "Liked",
                    "collection_key": "liked",
                    "collection_kind": "core_likes",
                    "catalog_uuid": catalog_uuid,
                },
            )
        )
        edges.append(
            GraphEdge(
                relationship="HAS_COLLECTION",
                source_type="Catalog",
                source_id=catalog_id,
                target_type="Collection",
                target_id=liked_collection_id,
            )
        )

    for track in tracks:
        track_id = _track_node_id(catalog_uuid, track.track_uuid)
        properties: dict[str, Any] = {
            "title": track.title,
            "track_uuid": track.track_uuid,
            "track_id": track.track_id,
            "catalog_uuid": catalog_uuid,
            "content_generation": track.content_generation,
            "file_size_bytes": track.file_size_bytes,
            "audio_format": track.audio_format,
            "duration_seconds": track.duration_seconds,
            "artist": track.artist,
            "album": track.album,
            "tag_bpm": track.tag_bpm,
            "tag_key": track.tag_key,
            "year": track.year,
            "liked": track.liked,
        }
        if include_paths:
            properties["file_path"] = track.file_path
        nodes.append(GraphNode("Track", track_id, properties))
        edges.append(
            GraphEdge(
                relationship="CONTAINS_TRACK",
                source_type="Catalog",
                source_id=catalog_id,
                target_type="Track",
                target_id=track_id,
            )
        )
        if track.artist:
            artist_id = _value_id("artist", track.artist)
            artists.setdefault(
                artist_id,
                GraphNode(
                    "Artist",
                    artist_id,
                    {
                        "title": track.artist,
                        "normalized_name": _normalize_label(track.artist),
                    },
                ),
            )
            edges.append(GraphEdge("BY_ARTIST", "Track", track_id, "Artist", artist_id))
        for genre in track.genres:
            genre_id = _value_id("genre", genre)
            genres.setdefault(
                genre_id,
                GraphNode(
                    "Genre",
                    genre_id,
                    {"title": genre, "normalized_name": _normalize_label(genre)},
                ),
            )
            edges.append(GraphEdge("HAS_GENRE", "Track", track_id, "Genre", genre_id))
        if track.liked:
            edges.append(
                GraphEdge(
                    "IN_COLLECTION",
                    "Track",
                    track_id,
                    "Collection",
                    liked_collection_id,
                )
            )
    nodes.extend(artists.values())
    nodes.extend(genres.values())

    return nodes, edges


def _projection_digest(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
    *,
    options: BuildOptions,
    catalog_uuid: str,
) -> str:
    digest = hashlib.sha256()
    header = {
        "format": "djts-kglite-projection-v1",
        "catalog_uuid": catalog_uuid,
        "top_k": options.top_k,
        "min_score": options.min_score,
        "include_paths": options.include_paths,
    }
    digest.update((_canonical_json(header) + "\n").encode("utf-8"))
    for node in sorted(nodes, key=lambda item: (item.node_type, item.node_id)):
        digest.update(
            (
                _canonical_json(
                    ["node", node.node_type, node.node_id, dict(node.properties)]
                )
                + "\n"
            ).encode("utf-8")
        )
    for edge in sorted(
        edges,
        key=lambda item: (
            item.relationship,
            item.source_type,
            item.source_id,
            item.target_type,
            item.target_id,
            _canonical_json(dict(item.properties)),
        ),
    ):
        digest.update(
            (
                _canonical_json(
                    [
                        "edge",
                        edge.relationship,
                        edge.source_type,
                        edge.source_id,
                        edge.target_type,
                        edge.target_id,
                        dict(edge.properties),
                    ]
                )
                + "\n"
            ).encode("utf-8")
        )
    return f"sha256:{digest.hexdigest()}"


def build_projection(options: BuildOptions) -> Projection:
    """Build an in-memory projection without writing either input or output."""

    normalized = options.normalized()
    assert normalized.artifacts_path is not None
    if _same_path(normalized.core_path, normalized.artifacts_path):
        raise BridgeError("Core and Artifacts inputs must be distinct files")

    with ExitStack() as stack:
        core = stack.enter_context(_read_only_connection(normalized.core_path))
        artifacts = stack.enter_context(
            _read_only_connection(normalized.artifacts_path)
        )
        _require_tables(
            core,
            (
                "library_catalog",
                "tracks",
                "file_tags",
                "likes",
            ),
            "Core",
        )
        _require_tables(
            artifacts,
            ("storage_metadata", *SOURCE_TABLES.values()),
            "Artifacts",
        )
        if normalized.integrity_check:
            _check_integrity(core, "Core")
            _check_integrity(artifacts, "Artifacts")

        catalog_rows = core.execute(
            "SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1"
        ).fetchall()
        metadata_rows = artifacts.execute(
            """
            SELECT catalog_uuid
            FROM storage_metadata
            WHERE singleton_id = 1
            """
        ).fetchall()
        if len(catalog_rows) != 1 or len(metadata_rows) != 1:
            raise BridgeError("Core/Artifacts singleton metadata is incomplete")
        catalog_uuid = str(catalog_rows[0]["catalog_uuid"])
        artifact_catalog_uuid = str(metadata_rows[0]["catalog_uuid"])
        if not catalog_uuid or artifact_catalog_uuid != catalog_uuid:
            raise BridgeError("Core/Artifacts catalog_uuid binding mismatch")
        sources = _read_embedding_sources(artifacts, normalized.sources)
        tracks = _read_tracks(core)
        tracks_by_id = {track.track_id: track for track in tracks}
        tracks_by_uuid = {track.track_uuid: track for track in tracks}
        nodes, edges = _base_graph(
            catalog_uuid=catalog_uuid,
            tracks=tracks,
            include_paths=normalized.include_paths,
        )
        source_reports: list[SourceReport] = []
        for source in sources:
            track_uuids, matrix, source_report = _read_vectors(
                tracks_by_id, artifacts, source
            )
            similarity_edges = _similarity_edges(
                catalog_uuid=catalog_uuid,
                source=source,
                track_uuids=track_uuids,
                matrix=matrix,
                tracks_by_uuid=tracks_by_uuid,
                top_k=normalized.top_k,
                min_score=normalized.min_score,
                block_size=normalized.similarity_block_size,
            )
            edges.extend(similarity_edges)
            source_reports.append(
                SourceReport(
                    **{
                        **asdict(source_report),
                        "similarity_edges": len(similarity_edges),
                    }
                )
            )

    digest = _projection_digest(
        nodes, edges, options=normalized, catalog_uuid=catalog_uuid
    )
    projection_id = f"projection:{digest}"
    nodes.append(
        GraphNode(
            "Projection",
            projection_id,
            {
                "title": "DJ library KGLite projection",
                "projection_digest": digest,
                "projection_format": "djts-kglite-projection-v1",
                "catalog_uuid": catalog_uuid,
                "top_k": normalized.top_k,
                "min_score": normalized.min_score,
                "include_paths": normalized.include_paths,
                "sources": ",".join(source.family for source in sources),
            },
        )
    )
    edges.append(
        GraphEdge(
            "PROJECTED_AS",
            "Catalog",
            f"catalog:{catalog_uuid}",
            "Projection",
            projection_id,
        )
    )
    nodes.sort(key=lambda item: (item.node_type, item.node_id))
    edges.sort(
        key=lambda item: (
            item.relationship,
            item.source_type,
            item.source_id,
            item.target_type,
            item.target_id,
            _canonical_json(dict(item.properties)),
        )
    )
    node_counts = Counter(node.node_type for node in nodes)
    edge_counts = Counter(edge.relationship for edge in edges)
    report = ProjectionReport(
        projection_digest=digest,
        catalog_uuid=catalog_uuid,
        selected_sources=tuple(source.family for source in sources),
        node_count=len(nodes),
        edge_count=len(edges),
        nodes_by_type=dict(sorted(node_counts.items())),
        edges_by_type=dict(sorted(edge_counts.items())),
        source_reports=tuple(source_reports),
    )
    return Projection(tuple(nodes), tuple(edges), report)


def _same_path(first: Path, second: Path) -> bool:
    first_text = os.path.normcase(os.path.abspath(first))
    second_text = os.path.normcase(os.path.abspath(second))
    return first_text == second_text


def _require_identifier(value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise BridgeError(f"unsafe graph identifier: {value!r}")
    return value


def _batched(values: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _write_nodes(graph: Any, nodes: Sequence[GraphNode], batch_size: int) -> None:
    grouped: dict[str, list[GraphNode]] = defaultdict(list)
    for node in nodes:
        grouped[node.node_type].append(node)
    for node_type in sorted(grouped):
        safe_type = _require_identifier(node_type)
        group = grouped[node_type]
        property_names = sorted(
            {
                name
                for node in group
                for name, value in node.properties.items()
                if value is not None
            }
        )
        for name in property_names:
            _require_identifier(name)
        assignments = ["id: r.id", *(f"{name}: r.{name}" for name in property_names)]
        query = f"UNWIND $rows AS r CREATE (n:{safe_type} {{{', '.join(assignments)}}})"
        rows = [
            {
                "id": node.node_id,
                **{name: node.properties.get(name) for name in property_names},
            }
            for node in group
        ]
        for batch in _batched(rows, batch_size):
            graph.cypher(query, params={"rows": list(batch)})


def _write_edges(graph: Any, edges: Sequence[GraphEdge], batch_size: int) -> None:
    grouped: dict[tuple[str, str, str], list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        grouped[(edge.relationship, edge.source_type, edge.target_type)].append(edge)
    for relationship, source_type, target_type in sorted(grouped):
        safe_relationship = _require_identifier(relationship)
        safe_source = _require_identifier(source_type)
        safe_target = _require_identifier(target_type)
        group = grouped[(relationship, source_type, target_type)]
        property_names = sorted(
            {
                name
                for edge in group
                for name, value in edge.properties.items()
                if value is not None
            }
        )
        for name in property_names:
            _require_identifier(name)
        properties = (
            " {" + ", ".join(f"{name}: r.{name}" for name in property_names) + "}"
            if property_names
            else ""
        )
        query = (
            "UNWIND $rows AS r "
            f"MATCH (a:{safe_source} {{id: r.source_id}}), "
            f"(b:{safe_target} {{id: r.target_id}}) "
            f"CREATE (a)-[:{safe_relationship}{properties}]->(b)"
        )
        rows = [
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                **{name: edge.properties.get(name) for name in property_names},
            }
            for edge in group
        ]
        for batch in _batched(rows, batch_size):
            graph.cypher(query, params={"rows": list(batch)})


def _single_count(result: Any, key: str) -> int:
    rows = result.to_list()
    if len(rows) != 1 or key not in rows[0]:
        raise BridgeError(f"KGLite verification did not return {key}")
    return int(rows[0][key])


def write_kglite_graph(
    projection: Projection,
    output_path: Path,
    *,
    core_path: Path,
    artifacts_path: Path,
    overwrite: bool = False,
    batch_size: int = 500,
) -> Path:
    """Write and reload-verify a disposable `.kgl` graph."""

    output = Path(output_path).expanduser().resolve()
    core = Path(core_path).expanduser().resolve()
    artifacts = Path(artifacts_path).expanduser().resolve()
    if output.suffix.lower() != ".kgl":
        raise BridgeError("output path must use the .kgl extension")
    if _same_path(output, core) or _same_path(output, artifacts):
        raise BridgeError("output path must not replace Core or Artifacts SQLite")
    if output.exists() and not overwrite:
        raise BridgeError(f"output already exists; pass --overwrite: {output}")
    if isinstance(batch_size, bool) or not 1 <= int(batch_size) <= 10_000:
        raise BridgeError("batch_size must be between 1 and 10000")
    try:
        import kglite
    except ImportError as error:
        raise BridgeError(
            "the optional kglite Python module is required to write a .kgl graph"
        ) from error

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{output.stem}.",
        suffix=".staging.kgl",
        dir=output.parent,
    )
    os.close(descriptor)
    staging = Path(staging_name)
    staging.unlink()
    graph = kglite.KnowledgeGraph()
    try:
        _write_nodes(graph, projection.nodes, int(batch_size))
        _write_edges(graph, projection.edges, int(batch_size))
        graph.save(str(staging))
    except Exception as error:
        staging.unlink(missing_ok=True)
        raise BridgeError(f"KGLite graph build failed: {error}") from error
    finally:
        close = getattr(graph, "close", None)
        if callable(close):
            close()

    try:
        verified = kglite.load(str(staging))
        node_count = _single_count(
            verified.cypher("MATCH (n) RETURN count(n) AS node_count"),
            "node_count",
        )
        edge_count = _single_count(
            verified.cypher("MATCH ()-[r]->() RETURN count(r) AS edge_count"),
            "edge_count",
        )
    except Exception as error:
        staging.unlink(missing_ok=True)
        raise BridgeError(
            f"saved KGLite graph failed reload verification: {error}"
        ) from error
    finally:
        if "verified" in locals():
            close = getattr(verified, "close", None)
            if callable(close):
                close()
    if node_count != projection.report.node_count:
        staging.unlink(missing_ok=True)
        raise BridgeError(
            f"saved KGLite node count mismatch: {node_count} != "
            f"{projection.report.node_count}"
        )
    if edge_count != projection.report.edge_count:
        staging.unlink(missing_ok=True)
        raise BridgeError(
            f"saved KGLite edge count mismatch: {edge_count} != "
            f"{projection.report.edge_count}"
        )
    if output.exists() and not overwrite:
        staging.unlink(missing_ok=True)
        raise BridgeError(f"output already exists; pass --overwrite: {output}")
    os.replace(staging, output)
    return output

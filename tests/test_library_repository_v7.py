from __future__ import annotations

import csv
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    register_contract,
)
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    AnalysisOutput,
    classifier_required_outputs_hash,
)
from dj_track_similarity.db_connection import (
    connect_artifacts_database,
    connect_database,
    ensure_database_schema,
)
from dj_track_similarity.db_library_queries import LibraryQueryRepository
from dj_track_similarity.db_schema import (
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
)
from dj_track_similarity.db_storage import storage_database_paths
from dj_track_similarity.exporter import export_tracks
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    sonara_runtime_contracts,
)
from dj_track_similarity.track_models import TrackIdentity


_NOW = "2026-07-24T00:00:00.000000Z"


class _FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "5" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness"
    __sonara_vocalness_model_build_id__ = "sha256:" + "6" * 64


_SONARA_CONTRACTS = sonara_runtime_contracts(_FakeSonara)
_SONARA_RELEASE = _SONARA_CONTRACTS.release_hash


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

    def connect(self) -> sqlite3.Connection:
        self.core_connect_count += 1
        return connect_database(
            self.path,
            expected_catalog_uuid=self.catalog_uuid,
        )

    def connect_artifacts(self) -> sqlite3.Connection:
        self.artifacts_connect_count += 1
        return connect_artifacts_database(
            self.artifacts_path,
            expected_catalog_uuid=self.catalog_uuid,
        )

    def reset_connection_counts(self) -> None:
        self.core_connect_count = 0
        self.artifacts_connect_count = 0


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
                comment, year, label, catalog_number, country, isrc,
                track_number, disc_number, genres_json, tags_read_at
            ) VALUES (
                ?, ?, ?, ?, 128.0, '8A', 'fixture comment', 2026,
                'Fixture Label', 'CAT-1', 'UA', 'UA-TEST-1',
                '1', '1', ?, ?
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
                catalog_number, country, isrc, year, track_number,
                disc_number, file_genres, maest_genres
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                file_path,
                title,
                artist,
                album,
                "fixture comment",
                "Fixture Label",
                "CAT-1",
                "UA",
                "UA-TEST-1",
                "2026",
                "1",
                "1",
                " ".join(genres),
                maest_fts_genres,
            ),
        )
    return _TrackSeed(track_id=track_id, track_uuid=track_uuid)


def _active_setting_key(contract: ContractIdentity) -> str:
    return (
        f"{ACTIVE_CONTRACT_SETTING_PREFIX}."
        f"{contract.analysis_family}.{contract.output_kind}"
    )


def _register_active(
    repository: _Repository,
    *contracts: ContractIdentity,
    active_release: str | None = None,
) -> None:
    with _core(repository) as core:
        for contract in contracts:
            register_contract(core, contract, created_at=_NOW)
            core.execute(
                """
                INSERT INTO library_settings(
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (
                    _active_setting_key(contract),
                    contract.contract_hash,
                    _NOW,
                ),
            )
        if active_release is not None:
            core.execute(
                """
                INSERT INTO library_settings(
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    active_release,
                    _NOW,
                ),
            )


def _mert_contract(*, model_version: str = "revision-1") -> ContractIdentity:
    current = current_embedding_analysis_output("mert").contract
    if model_version == "revision-1":
        return current
    revision = {"revision-2": "b" * 40}.get(model_version, model_version)
    return replace(current, model_version=revision)


def _maest_contract() -> ContractIdentity:
    return MaestModelRunner(
        device="cpu",
        top_k=5,
        inference_batch_size=1,
    ).active_outputs[0].contract


def _maest_embedding_contract() -> ContractIdentity:
    return current_embedding_analysis_output("maest").contract


def _sonara_contract(output_kind: str) -> ContractIdentity:
    return {
        "core": _SONARA_CONTRACTS.core,
        "timeline": _SONARA_CONTRACTS.timeline,
        "embedding": _SONARA_CONTRACTS.embedding,
        "fingerprint": _SONARA_CONTRACTS.fingerprint,
    }[output_kind]


def _insert_embedding(
    repository: _Repository,
    *,
    track: _TrackSeed,
    contract: ContractIdentity,
    track_uuid: str | None = None,
    generation: int = 1,
) -> None:
    table = {
        "maest": "maest_embeddings",
        "mert": "mert_embeddings",
        "sonara": "sonara_similarity_embeddings",
    }[contract.analysis_family]
    assert contract.dim is not None
    vector = np.zeros(contract.dim, dtype="<f4")
    vector[0] = 1.0
    with _artifacts(repository) as artifacts:
        artifacts.execute(
            f"""
            INSERT INTO {table} (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track.track_id,
                track_uuid or track.track_uuid,
                generation,
                contract.contract_hash,
                contract.dim,
                contract.normalization,
                vector.tobytes(order="C"),
                _NOW,
            ),
        )


def _insert_sonara_core(
    repository: _Repository,
    *,
    track: _TrackSeed,
    contract: ContractIdentity,
) -> None:
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO sonara (
                track_id, content_generation, contract_hash,
                detected_bpm, detected_key_name, detected_key_camelot,
                energy_score, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (?, 1, ?, 126.0, 'A minor', '8A', 0.77, ?, ?, ?, ?)
            """,
            (
                track.track_id,
                contract.contract_hash,
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
    uses_sonara: bool = False,
    sonara_release_hash: str | None = None,
) -> None:
    required_outputs_hash = (
        "sha256:" + "0" * 64
        if uses_sonara
        else classifier_required_outputs_hash((AnalysisOutput(_mert_contract()),))
    )
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO classifier_scores (
                track_id, classifier_key, content_generation, model_id,
                feature_set, feature_manifest_hash, required_outputs_hash,
                uses_sonara,
                sonara_release_hash, positive_label, predicted_class,
                score_bucket, score, confidence, probabilities_json,
                analyzed_at
            ) VALUES (
                ?, ?, 1, 'fixture-model', 'mert', 'sha256:fixture',
                ?, ?, ?, 'positive', 'positive', 'high', ?, 0.91, ?, ?
            )
            """,
            (
                track.track_id,
                classifier_key,
                required_outputs_hash,
                int(uses_sonara),
                sonara_release_hash,
                score,
                json.dumps({"negative": 1.0 - score, "positive": score}),
                _NOW,
            ),
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


def test_artifact_readiness_requires_active_contract_uuid_and_generation(
    repository: _Repository,
) -> None:
    current = _insert_track(repository, title="Current", artist="Artist A")
    wrong_uuid = _insert_track(
        repository,
        title="Wrong UUID",
        artist="Artist B",
    )
    contract = _mert_contract()
    _register_active(repository, contract)
    _insert_embedding(repository, track=current, contract=contract)
    _insert_embedding(
        repository,
        track=wrong_uuid,
        contract=contract,
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

    replacement = _mert_contract(model_version="revision-2")
    _register_active(repository, replacement)
    assert not any(
        track.analysis_coverage.mert for track in repository.list_track_summaries()
    )


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
    contract = _mert_contract()
    _register_active(repository, contract)
    _insert_embedding(repository, track=track, contract=contract)
    assert contract.dim is not None
    malformed_dim = contract.dim if malformed_kind == "zero_l2" else contract.dim - 1
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


def test_sonara_rows_are_current_only_with_active_release(
    repository: _Repository,
) -> None:
    track = _insert_track(repository, title="SONARA", artist="Artist A")
    core_contract = _sonara_contract("core")
    timeline_contract = _sonara_contract("timeline")
    fingerprint_contract = _sonara_contract("fingerprint")
    _register_active(
        repository,
        core_contract,
        timeline_contract,
        fingerprint_contract,
    )
    _insert_sonara_core(
        repository,
        track=track,
        contract=core_contract,
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
                track_id, track_uuid, content_generation, contract_hash,
                payload_json, analyzed_at
            ) VALUES (?, ?, 1, ?, ?, ?)
            """,
            (
                track.track_id,
                track.track_uuid,
                timeline_contract.contract_hash,
                json.dumps(timeline_payload, separators=(",", ":")),
                _NOW,
            ),
        )
        artifacts.execute(
            """
            INSERT INTO sonara_fingerprints (
                track_id, track_uuid, content_generation, contract_hash,
                fingerprint_version, word_count, byte_order,
                fingerprint_blob, analyzed_at
            ) VALUES (?, ?, 1, ?, '1', 2, 'little', ?, ?)
            """,
            (
                track.track_id,
                track.track_uuid,
                fingerprint_contract.contract_hash,
                bytes(8),
                _NOW,
            ),
        )

    unavailable = repository.get_track_detail(track.track_id)
    assert not unavailable.analysis_coverage.sonara_core
    assert unavailable.sonara_core is None
    assert repository.load_sonara_timeline(track.track_id) is None

    _register_active(repository, active_release=_SONARA_RELEASE)
    detail = repository.get_track_detail(track.track_id)

    assert detail.analysis_coverage.sonara_core
    assert detail.analysis_coverage.timeline
    assert detail.analysis_coverage.fingerprint
    assert detail.sonara_core is not None
    assert detail.sonara_core.detected_bpm == 126.0
    assert detail.optional_outputs.timeline_fields == tuple(timeline_payload)
    assert detail.optional_outputs.audio_fingerprint_available
    assert repository.load_sonara_timeline(track.track_id) == timeline_payload

    with _artifacts(repository) as artifacts:
        artifacts.execute(
            """
            UPDATE sonara_fingerprints
            SET fingerprint_version = '999'
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
    analysis_contract = _maest_contract()
    embedding_contract = _maest_embedding_contract()
    _register_active(
        repository,
        analysis_contract,
        embedding_contract,
    )
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO maest_scores (
                track_id, content_generation, contract_hash,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, 1, ?, 1, ?, ?)
            """,
            (
                analysis_only.track_id,
                analysis_contract.contract_hash,
                '[{"label":"Techno","score":0.9}]',
                _NOW,
            ),
        )
    _insert_embedding(
        repository,
        track=embedding_only,
        contract=embedding_contract,
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


def test_summary_and_classifier_filters_ignore_stale_sonara_scores(
    repository: _Repository,
) -> None:
    first = _insert_track(repository, title="First", artist="Artist A")
    second = _insert_track(repository, title="Second", artist="Artist B")
    maest = _maest_contract()
    mert = _mert_contract()
    _register_active(repository, maest, mert)
    with _core(repository) as core:
        core.execute(
            """
            INSERT INTO maest_scores (
                track_id, content_generation, contract_hash,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, 1, ?, 1, ?, ?)
            """,
            (
                first.track_id,
                maest.contract_hash,
                '[{"label":"Techno","score":0.9}]',
                _NOW,
            ),
        )
    _insert_embedding(repository, track=first, contract=mert)
    _insert_classifier(
        repository,
        track=first,
        classifier_key="voice_presence",
        score=0.82,
    )
    _insert_classifier(
        repository,
        track=second,
        classifier_key="voice_presence",
        score=0.95,
        uses_sonara=True,
        sonara_release_hash=_SONARA_RELEASE,
    )

    filtered = repository.filter_track_summaries(
        classifier_min_scores={"voice_presence": 0.8},
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

    summary = repository.library_summary(classifier_keys=("voice_presence",))
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


def test_classifier_readers_hide_score_after_ml_contract_change(
    repository: _Repository,
) -> None:
    track = _insert_track(repository, title="First", artist="Artist A")
    old_mert = _mert_contract()
    _register_active(repository, old_mert)
    _insert_classifier(
        repository,
        track=track,
        classifier_key="voice_presence",
        score=0.82,
    )
    assert [
        item.track_id
        for item in repository.filter_track_summaries(
            classifier_min_scores={"voice_presence": 0.8},
        )
    ] == [track.track_id]

    _register_active(
        repository,
        _mert_contract(model_version="revision-2"),
    )

    assert (
        repository.filter_track_summaries(
            classifier_min_scores={"voice_presence": 0.8},
        )
        == ()
    )
    assert (
        repository.library_summary(classifier_keys=("voice_presence",)).classifiers == 0
    )

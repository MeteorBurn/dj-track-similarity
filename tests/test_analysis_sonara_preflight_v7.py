from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.analysis_jobs as analysis_jobs_module
import dj_track_similarity.api as api
from dj_track_similarity.analysis_job_state import AnalysisJobStatus
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_pipeline import (
    AnalysisPipelineManager,
    AnalysisPipelineStatus,
    PipelineStageStatus,
)
from dj_track_similarity.analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    AnalysisOutput,
    active_contract_setting_key,
)
from dj_track_similarity.analysis_contracts import utc_timestamp
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    prepare_sonara_release,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    sonara_runtime_contracts,
)


class _PreviousSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "1" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = "sha256:" + "2" * 64


class _CurrentSonara(_PreviousSonara):
    __sonara_build_id__ = "sha256:" + "3" * 64
    __sonara_vocalness_model_build_id__ = "sha256:" + "4" * 64


def _outputs(sonara_module: object) -> tuple[AnalysisOutput, ...]:
    return tuple(
        AnalysisOutput(identity)
        for identity in sonara_runtime_contracts(sonara_module).identities
    )


def _use_current_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AnalysisOutput, ...]:
    current = _outputs(_CurrentSonara)
    monkeypatch.setattr(
        analysis_jobs_module,
        "analysis_outputs_for_sonara_runtime",
        lambda: current,
    )
    return current


def _prepare_release(
    database: LibraryDatabase,
    tmp_path: Path,
    sonara_module: object,
) -> None:
    backup_dir = tmp_path / "sonara-backups"
    backup_dir.mkdir(exist_ok=True)
    prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=sonara_module,
    )


def test_preflight_rejects_non_current_four_output_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    previous = _outputs(_PreviousSonara)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _prepare_release(db, tmp_path, _PreviousSonara)
    manager = AnalysisJobManager(db)

    with pytest.raises(
        RuntimeError,
        match="SONARA_RELEASE_PREPARATION_REQUIRED",
    ) as captured:
        manager.validate_sonara_preflight()

    assert "loaded runtime" in str(captured.value)
    assert current[0].contract_hash != previous[0].contract_hash


def test_release_status_reports_missing_exact_outputs_on_fresh_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db = LibraryDatabase(tmp_path / "library.sqlite")

    status = AnalysisJobManager(db).sonara_release_status()

    assert status.catalog_uuid == db.catalog_uuid
    assert status.state == "preparation_required"
    assert status.ready is False
    assert "the core output is not active" in status.detail
    assert status.expected_release_hash == current[0].contract.release_hash
    assert status.active_release_hash is None
    assert [output.output_kind for output in status.outputs] == [
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    ]
    assert [output.state for output in status.outputs] == ["missing"] * 4
    assert [output.expected_contract_hash for output in status.outputs] == [
        output.contract_hash for output in current
    ]
    assert all(output.active_contract_hash is None for output in status.outputs)


def test_preflight_activates_current_outputs_once_when_no_sonara_state_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    manager = AnalysisJobManager(db)

    before = manager.sonara_release_status()
    assert before.ready is False
    with db.connect() as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM library_settings
            WHERE setting_key = ?
               OR setting_key LIKE ?
            """,
            (
                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
            ),
        ).fetchone()[0] == 0

    manager.validate_sonara_preflight()
    with db.connect() as connection:
        settings = dict(
            connection.execute(
                """
                SELECT setting_key, setting_value
                FROM library_settings
                WHERE setting_key = ?
                   OR setting_key LIKE ?
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
                ),
            )
        )
        contracts = connection.execute(
            """
            SELECT contract_hash
            FROM contracts
            WHERE analysis_family = 'sonara'
            ORDER BY output_kind
            """
        ).fetchall()
        first_updated_at = dict(
            connection.execute(
                """
                SELECT setting_key, updated_at
                FROM library_settings
                WHERE setting_key = ?
                   OR setting_key LIKE ?
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
                ),
            )
        )

    assert settings == {
        SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY: current[0].contract.release_hash,
        **{
            active_contract_setting_key(output): output.contract_hash
            for output in current
        },
    }
    assert {str(row[0]) for row in contracts} == {
        output.contract_hash for output in current
    }
    assert not list(tmp_path.glob("*.pre-sonara-*"))

    manager.validate_sonara_preflight()
    with db.connect() as connection:
        second_updated_at = dict(
            connection.execute(
                """
                SELECT setting_key, updated_at
                FROM library_settings
                WHERE setting_key = ?
                   OR setting_key LIKE ?
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
                ),
            )
        )
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM contracts
            WHERE analysis_family = 'sonara'
            """
        ).fetchone()[0] == 4
    assert second_updated_at == first_updated_at


def test_reset_current_outputs_remains_ready_for_reanalysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    manager = AnalysisJobManager(db)
    manager.validate_sonara_preflight()

    reset = db.reset_analysis_outputs(current)

    assert reset.core_rows_deleted == 0
    assert reset.artifact_rows_deleted == 0
    assert reset.classifier_rows_deleted == 0
    manager.validate_sonara_preflight()
    assert manager.sonara_release_status().ready is True


@pytest.mark.parametrize(
    "delete_all_active_settings",
    (False, True),
    ids=("one-missing-setting", "all-settings-missing"),
)
def test_reset_endpoint_rejects_partial_sonara_state_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delete_all_active_settings: bool,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    AnalysisJobManager(db).validate_sonara_preflight()

    with db.connect() as connection:
        timestamp = utc_timestamp()
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks (
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "partial-reset-track",
                    str(tmp_path / "partial-reset-track.wav"),
                    1024,
                    123456789,
                    1,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sonara (
                track_id, content_generation, contract_hash,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                1,
                current[0].contract_hash,
                bytes(13 * 4),
                bytes(12 * 4),
                bytes(7 * 4),
                timestamp,
            ),
        )
        if delete_all_active_settings:
            connection.execute(
                """
                DELETE FROM library_settings
                WHERE setting_key = ?
                   OR setting_key LIKE ?
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
                ),
            )
        else:
            connection.execute(
                "DELETE FROM library_settings WHERE setting_key = ?",
                (active_contract_setting_key(current[-1]),),
            )
        settings_before = connection.execute(
            """
            SELECT setting_key, setting_value
            FROM library_settings
            WHERE setting_key = ?
               OR setting_key LIKE ?
            ORDER BY setting_key
            """,
            (
                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
            ),
        ).fetchall()
        rows_before = connection.execute(
            "SELECT COUNT(*) FROM sonara"
        ).fetchone()[0]

    response = TestClient(api.create_app(db_path)).post(
        "/api/analysis/reset",
        json={"analysis_family": "sonara"},
    )

    assert response.status_code == 409
    assert (
        "complete active Core, Timeline, Embedding, and Fingerprint"
        in response.json()["detail"]
    )
    with db.connect() as connection:
        assert connection.execute(
            """
            SELECT setting_key, setting_value
            FROM library_settings
            WHERE setting_key = ?
               OR setting_key LIKE ?
            ORDER BY setting_key
            """,
            (
                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
            ),
        ).fetchall() == settings_before
        assert connection.execute(
            "SELECT COUNT(*) FROM sonara"
        ).fetchone()[0] == rows_before


def test_reset_old_outputs_allows_current_runtime_reanalysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    previous = _outputs(_PreviousSonara)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _prepare_release(db, tmp_path, _PreviousSonara)

    with db.connect() as connection:
        timestamp = utc_timestamp()
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks (
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-track",
                    str(tmp_path / "old-track.wav"),
                    1024,
                    123456789,
                    1,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sonara (
                track_id, content_generation, contract_hash,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                1,
                previous[0].contract_hash,
                bytes(13 * 4),
                bytes(12 * 4),
                bytes(7 * 4),
                utc_timestamp(),
            ),
        )
        connection.execute(
            """
            INSERT INTO classifier_scores (
                track_id, classifier_key, content_generation, model_id,
                feature_set, feature_manifest_hash, required_outputs_hash,
                uses_sonara, sonara_release_hash, positive_label,
                predicted_class, score_bucket, score, confidence,
                probabilities_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "old-sonara-classifier",
                1,
                "old-model",
                "old-feature-set",
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                1,
                previous[0].contract.release_hash,
                "yes",
                "yes",
                "high",
                1.0,
                1.0,
                '{"yes":1.0}',
                utc_timestamp(),
            ),
        )
    with db.connect_artifacts() as connection:
        connection.execute(
            """
            INSERT INTO sonara_timeline (
                track_id, track_uuid, content_generation, contract_hash,
                payload_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "old-track",
                1,
                previous[1].contract_hash,
                "{}",
                utc_timestamp(),
            ),
        )
        connection.execute(
            """
            INSERT INTO sonara_similarity_embeddings (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "old-track",
                1,
                previous[2].contract_hash,
                1,
                "l2",
                bytes(4),
                utc_timestamp(),
            ),
        )
        connection.execute(
            """
            INSERT INTO sonara_fingerprints (
                track_id, track_uuid, content_generation, contract_hash,
                fingerprint_version, word_count, byte_order,
                fingerprint_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "old-track",
                1,
                previous[3].contract_hash,
                "old",
                0,
                "little",
                b"",
                utc_timestamp(),
            ),
        )

    reset = db.reset_analysis_outputs(previous)

    assert reset.core_rows_deleted == 1
    assert reset.artifact_rows_deleted == 3
    assert reset.classifier_rows_deleted == 1
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sonara").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM classifier_scores WHERE uses_sonara = 1"
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM library_settings
            WHERE setting_key = ?
               OR setting_key LIKE ?
            """,
            (
                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",
            ),
        ).fetchone()[0] == 0
    with db.connect_artifacts() as connection:
        for table in (
            "sonara_timeline",
            "sonara_similarity_embeddings",
            "sonara_fingerprints",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0] == 0

    manager = AnalysisJobManager(db)
    manager.validate_sonara_preflight()

    status = manager.sonara_release_status()
    assert status.ready is True
    assert status.active_release_hash == current[0].contract.release_hash
    assert [output.active_contract_hash for output in status.outputs] == [
        output.contract_hash for output in current
    ]
    with db.connect() as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM contracts
            WHERE analysis_family = 'sonara'
            """
        ).fetchone()[0] == 8


@pytest.mark.parametrize(
    "existing_state",
    [
        "setting",
        "core_row",
        "classifier_row",
        "timeline_row",
        "embedding_row",
        "fingerprint_row",
    ],
)
def test_preflight_does_not_activate_over_existing_sonara_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    existing_state: str,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db = LibraryDatabase(tmp_path / "library.sqlite")

    if existing_state == "setting":
        with db.connect() as connection:
            connection.execute(
                """
                INSERT INTO library_settings (
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, ?)
                """,
                (
                    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
                    "sha256:" + "f" * 64,
                    utc_timestamp(),
                ),
            )
    elif existing_state == "core_row":
        with db.connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO sonara (
                    track_id, content_generation, contract_hash,
                    mfcc_mean_blob, chroma_mean_blob,
                    spectral_contrast_mean_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    1,
                    current[0].contract_hash,
                    bytes(13 * 4),
                    bytes(12 * 4),
                    bytes(7 * 4),
                    utc_timestamp(),
                ),
            )
    elif existing_state == "classifier_row":
        with db.connect() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO classifier_scores (
                    track_id, classifier_key, content_generation, model_id,
                    feature_set, feature_manifest_hash, required_outputs_hash,
                    uses_sonara, sonara_release_hash, positive_label,
                    predicted_class, score_bucket, score, confidence,
                    probabilities_json, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "existing-classifier",
                    1,
                    "existing-model",
                    "existing-feature-set",
                    "sha256:" + "a" * 64,
                    "sha256:" + "b" * 64,
                    1,
                    current[0].contract.release_hash,
                    "yes",
                    "yes",
                    "high",
                    1.0,
                    1.0,
                    '{"yes":1.0}',
                    utc_timestamp(),
                ),
            )
    elif existing_state == "timeline_row":
        with db.connect_artifacts() as connection:
            connection.execute(
                """
                INSERT INTO sonara_timeline (
                    track_id, track_uuid, content_generation, contract_hash,
                    payload_json, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "existing-track",
                    1,
                    current[1].contract_hash,
                    "{}",
                    utc_timestamp(),
                ),
            )
    elif existing_state == "embedding_row":
        with db.connect_artifacts() as connection:
            connection.execute(
                """
                INSERT INTO sonara_similarity_embeddings (
                    track_id, track_uuid, content_generation, contract_hash,
                    dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "existing-track",
                    1,
                    current[2].contract_hash,
                    1,
                    "l2",
                    bytes(4),
                    utc_timestamp(),
                ),
            )
    else:
        with db.connect_artifacts() as connection:
            connection.execute(
                """
                INSERT INTO sonara_fingerprints (
                    track_id, track_uuid, content_generation, contract_hash,
                    fingerprint_version, word_count, byte_order,
                    fingerprint_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "existing-track",
                    1,
                    current[3].contract_hash,
                    "existing",
                    0,
                    "little",
                    b"",
                    utc_timestamp(),
                ),
            )

    with pytest.raises(
        RuntimeError,
        match="SONARA_RELEASE_PREPARATION_REQUIRED",
    ):
        AnalysisJobManager(db).validate_sonara_preflight()

    with db.connect() as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM library_settings
            WHERE setting_key LIKE ?
            """,
            (f"{ACTIVE_CONTRACT_SETTING_PREFIX}.sonara.%",),
        ).fetchone()[0] == 0


def test_preflight_checks_active_release_setting_separately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_current_runtime(monkeypatch)
    previous = _outputs(_PreviousSonara)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _prepare_release(db, tmp_path, _CurrentSonara)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE library_settings
            SET setting_value = ?
            WHERE setting_key = ?
            """,
            (
                previous[0].contract.release_hash,
                SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
            ),
        )

    with pytest.raises(
        RuntimeError,
        match="active SONARA release settings are inconsistent",
    ):
        AnalysisJobManager(db).validate_sonara_preflight()


def test_prepared_exact_release_passes_candidate_readiness_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _prepare_release(db, tmp_path, _CurrentSonara)
    calls: list[tuple[tuple[AnalysisOutput, ...], int | None]] = []
    original = db.list_analysis_candidates

    def list_candidates(
        outputs: tuple[AnalysisOutput, ...],
        *,
        limit: int | None = None,
    ):
        calls.append((tuple(outputs), limit))
        return original(outputs, limit=limit)

    monkeypatch.setattr(db, "list_analysis_candidates", list_candidates)

    AnalysisJobManager(db).validate_sonara_preflight()

    assert calls == [(current, 0)]


def test_release_status_endpoint_reports_exact_prepared_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _use_current_runtime(monkeypatch)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _prepare_release(db, tmp_path, _CurrentSonara)
    client = TestClient(api.create_app(db_path))

    response = client.get("/api/analysis/sonara/releases/status")

    assert response.status_code == 200
    assert response.json() == {
        "catalog_uuid": db.catalog_uuid,
        "state": "ready",
        "ready": True,
        "detail": "The loaded runtime's exact SONARA release is active.",
        "expected_release_hash": current[0].contract.release_hash,
        "active_release_hash": current[0].contract.release_hash,
        "outputs": [
            {
                "output_kind": output.contract.output_kind,
                "state": "current",
                "expected_contract_hash": output.contract_hash,
                "active_contract_hash": output.contract_hash,
            }
            for output in current
        ],
    }


def test_api_preflight_fails_before_queue_and_allows_prepared_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_current_runtime(monkeypatch)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _prepare_release(db, tmp_path, _PreviousSonara)
    start_calls: list[dict[str, object]] = []

    def fake_start(
        _manager: AnalysisJobManager,
        **kwargs: object,
    ) -> AnalysisJobStatus:
        start_calls.append(dict(kwargs))
        return AnalysisJobStatus(
            job_id="queued-after-preflight",
            state="queued",
            models=["sonara"],
            sonara_outputs=list(kwargs.get("sonara_outputs", ())),
        )

    monkeypatch.setattr(AnalysisJobManager, "start", fake_start)
    client = TestClient(api.create_app(db_path))

    blocked = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )

    assert blocked.status_code == 409
    assert "SONARA_RELEASE_PREPARATION_REQUIRED" in blocked.json()["detail"]
    assert "Reset incompatible SONARA analysis data" in blocked.json()["detail"]
    assert start_calls == []

    _prepare_release(db, tmp_path, _CurrentSonara)
    allowed = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )

    assert allowed.status_code == 200
    assert allowed.json()["job_id"] == "queued-after-preflight"
    assert len(start_calls) == 1
    assert start_calls[0]["models"] == ["sonara"]


def test_pipeline_preflight_activates_before_queue_when_no_sonara_state_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_current_runtime(monkeypatch)
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    start_calls: list[dict[str, object]] = []

    def fake_start(
        _manager: AnalysisPipelineManager,
        **kwargs: object,
    ) -> AnalysisPipelineStatus:
        start_calls.append(dict(kwargs))
        return AnalysisPipelineStatus(
            job_id="queued-after-activation",
            state="queued",
            order=["sonara"],
            stages={"sonara": PipelineStageStatus(name="sonara")},
        )

    monkeypatch.setattr(AnalysisPipelineManager, "start", fake_start)
    client = TestClient(api.create_app(db_path))

    allowed = client.post(
        "/api/analysis/pipelines",
        json={
            "stages": ["sonara"],
            "limit": 0,
            "sonara": {"outputs": ["core"], "batch_size": 8},
        },
    )

    assert allowed.status_code == 200
    assert allowed.json()["job_id"] == "queued-after-activation"
    assert len(start_calls) == 1

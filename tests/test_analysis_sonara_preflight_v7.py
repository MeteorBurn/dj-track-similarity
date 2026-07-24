from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.analysis_jobs as analysis_jobs_module
import dj_track_similarity.api as api
from dj_track_similarity.analysis_job_state import AnalysisJobStatus
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_models import (
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    AnalysisOutput,
)
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
    assert (
        "Back up the selected Core and Artifacts databases" in blocked.json()["detail"]
    )
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

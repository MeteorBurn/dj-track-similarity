from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api.application as api
from dj_track_similarity.analysis.jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)


_OUTPUTS = (
    AnalysisOutput("sonara", "core"),
    AnalysisOutput("sonara", "timeline"),
    AnalysisOutput("sonara", "embedding"),
    AnalysisOutput("sonara", "fingerprint"),
)


def _candidate(
    track_id: int,
    missing_outputs: tuple[AnalysisOutput, ...],
) -> AnalysisCandidate:
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid="catalog-test",
            track_id=track_id,
            track_uuid=f"track-{track_id}",
        ),
        file_path=f"C:/music/{track_id}.wav",
        file_size_bytes=100,
        file_modified_ns=1_000,
        missing_outputs=missing_outputs,
    )


@dataclass
class _CoverageRepository:
    catalog_uuid: str = "catalog-test"

    def list_track_paths(self):
        return [SimpleNamespace(track_id=track_id) for track_id in (1, 2, 3)]

    def list_analysis_candidates(
        self,
        outputs,
        *,
        limit=None,
        require_current_sonara=False,
    ):
        assert tuple(outputs) == _OUTPUTS
        assert limit is None
        assert not require_current_sonara
        return [
            _candidate(2, _OUTPUTS),
        ]


def test_sonara_status_reports_current_data_coverage_without_release_identity() -> None:
    status = AnalysisJobManager(_CoverageRepository()).sonara_status()

    assert status.catalog_uuid == "catalog-test"
    assert status.total_tracks == 3
    assert [
        (
            output.output_kind,
            output.present_count,
            output.missing_count,
        )
        for output in status.outputs
    ] == [
        ("core", 2, 1),
        ("timeline", 2, 1),
        ("embedding", 2, 1),
        ("fingerprint", 2, 1),
    ]


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None)
    return TestClient(api.create_app(tmp_path / "library.sqlite"))


def test_sonara_status_endpoint_is_neutral_and_release_routes_are_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)
    # A missing track is neither a candidate nor part of the total: counting it
    # would report its absent SONARA data as present.
    stamp = "2026-09-15T00:00:00Z"
    with closing(LibraryDatabase(tmp_path / "library.sqlite").connect()) as connection, connection:
        for index, missing_since in ((1, None), (2, stamp)):
            connection.execute(
                "INSERT INTO tracks(track_uuid, file_path, file_size_bytes, file_modified_ns, "
                "last_scanned_at, missing_since, created_at, updated_at) VALUES (?, ?, 1, 1, ?, ?, ?, ?)",
                (f"00000000-0000-0000-0000-00000000000{index}", str(tmp_path / f"{index}.wav"), stamp, missing_since, stamp, stamp),
            )

    response = client.get("/api/analysis/sonara/status")

    assert response.status_code == 200
    assert response.json() == {
        "catalog_uuid": response.json()["catalog_uuid"],
        "total_tracks": 1,
        "outputs": [
            {
                "output_kind": kind,
                "present_count": 0,
                "missing_count": 1,
            }
            for kind in ("core", "timeline", "embedding", "fingerprint")
        ],
    }
    assert client.get("/api/analysis/sonara/releases/status").status_code == 404
    assert (
        client.post("/api/analysis/sonara/releases/prepare", json={}).status_code
        in {404, 405}
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api.application as api
from dj_track_similarity.analysis.jobs import AnalysisJobManager
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)


_OUTPUTS = (
    AnalysisOutput("sonara", "core"),
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

    def library_summary(self):
        return SimpleNamespace(tracks=3)

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

    response = client.get("/api/analysis/sonara/status")

    assert response.status_code == 200
    assert response.json() == {
        "catalog_uuid": response.json()["catalog_uuid"],
        "total_tracks": 0,
        "outputs": [
            {
                "output_kind": "core",
                "present_count": 0,
                "missing_count": 0,
            },
            {
                "output_kind": "embedding",
                "present_count": 0,
                "missing_count": 0,
            },
            {
                "output_kind": "fingerprint",
                "present_count": 0,
                "missing_count": 0,
            },
        ],
    }
    assert client.get("/api/analysis/sonara/releases/status").status_code == 404
    assert (
        client.post("/api/analysis/sonara/releases/prepare", json={}).status_code
        in {404, 405}
    )

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

import dj_track_similarity.api as api
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"

RISK_BREAKDOWN_KEYS = {
    "bpm",
    "tonal",
    "energy_jump",
    "density_jump",
    "texture_clash",
    "mood_clash",
    "vocal_conflict",
    "grid_instability",
    "structure_transition",
    "source_disagreement",
    "confidence_missingness",
}


def test_hybrid_search_endpoint_returns_unified_diagnostics(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 1.0},
            "per_source": 3,
            "limit": 2,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["weights_used"] == {"mert": 0.0, "maest": 1.0}
    assert payload["sources"] == ["mert", "maest"]
    assert payload["results"][0]["track"]["track_id"] == track_ids["maest_top"]
    assert payload["results"][0]["rank"] == 1
    assert payload["results"][0]["score"] == 1.0
    assert payload["results"][0]["adjusted_score"] == payload["results"][0]["score"]
    assert payload["results"][0]["transition_risk_weight"] == 0.0
    assert payload["results"][0]["transition_risk_penalty"] == 0.0
    assert payload["results"][0]["transition_risk"] is not None
    assert payload["results"][0]["transition_diagnostics"]["supporting_seed_count"] == 1
    assert "maest" in payload["results"][0]["score_breakdown"]
    assert payload["results"][0]["total_score"] == payload["results"][0]["adjusted_score"]
    assert payload["results"][0]["calibrated_score"] is None
    assert set(payload["results"][0]["match_character"]) == {"groove", "density", "texture", "mood", "tonal", "vocalness", "energy_flow", "novelty"}
    assert set(payload["results"][0]["risk_breakdown"]) == RISK_BREAKDOWN_KEYS
    assert payload["results"][0]["source_support"]["maest"]["available"] is True
    assert payload["results"][0]["classifier_support"] == {}
    assert payload["results"][0]["explanation"]
    assert payload["results"][0]["feedback"] is None
    assert payload["session_id"] is None
    assert "diagnostic ranking output" in " ".join(payload["limitations"])
    assert db.count_evaluation_rows()["search_sessions"] == 0


def test_hybrid_search_records_session_events_and_hydrates_feedback(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db, track_ids = _hybrid_library(db_path, tmp_path)
    db.upsert_track_pair_feedback(
        track_ids["seed"],
        track_ids["maest_top"],
        2,
        reason_tags=("good_groove", "good_density"),
        source="hybrid_ui",
    )

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 1.0},
            "per_source": 3,
            "limit": 2,
            "record_session": True,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["session_id"], int)
    assert payload["results"][0]["track"]["track_id"] == track_ids["maest_top"]
    assert payload["results"][0]["feedback"]["source"] == "hybrid_ui"
    assert payload["results"][0]["feedback"]["rating"] == 2
    assert payload["results"][0]["feedback"]["reason_tags"] == ["good_groove", "good_density"]
    counts = LibraryDatabase(db_path).count_evaluation_rows()
    assert counts["search_sessions"] == 1
    assert counts["search_result_events"] == len(payload["results"])
    session = LibraryDatabase(db_path).list_search_sessions_with_events()[0]
    assert session["mode"] == "hybrid_search_preview"
    assert session["seed_track_ids"] == [track_ids["seed"]]
    assert session["request"]["feedback_source"] == "hybrid_ui"
    assert session["request"]["record_session"] is True
    first_event_breakdown = session["events"][0]["score_breakdown"]
    assert first_event_breakdown["score_kind"] == "weighted_rrf"
    assert first_event_breakdown["total_score"] == payload["results"][0]["total_score"]
    assert first_event_breakdown["calibrated_score"] is None
    assert first_event_breakdown["adjusted_score"] == payload["results"][0]["adjusted_score"]
    assert first_event_breakdown["raw_rrf_score"] == payload["results"][0]["raw_rrf_score"]
    assert first_event_breakdown["transition_risk_weight"] == 0.0
    assert first_event_breakdown["sources"]["maest"]["rank"] == 1
    assert first_event_breakdown["source_support"]["maest"]["available"] is True
    assert first_event_breakdown["risk_breakdown"] == payload["results"][0]["risk_breakdown"]
    assert first_event_breakdown["explanation"] == payload["results"][0]["explanation"]
    assert "score" in first_event_breakdown["sources"]["maest"]
    assert "confidence" not in first_event_breakdown


def test_hybrid_search_endpoint_rejects_invalid_weights(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 0.0},
        },
    )

    assert response.status_code == 400
    assert "positive" in response.json()["detail"]


def test_hybrid_search_endpoint_rejects_invalid_transition_risk_weight(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [track_ids["seed"]], "transition_risk_weight": 1.01},
    )

    assert response.status_code == 422


def test_hybrid_search_endpoint_rejects_duplicate_seed_ids(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [track_ids["seed"], track_ids["seed"]], "sources": ["mert"]},
    )

    assert response.status_code == 422
    assert "seed_track_ids must be unique" in response.text


def test_hybrid_search_endpoint_rejects_unknown_contract_fields(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [track_ids["seed"]], "calibrated_probability": True},
    )

    assert response.status_code == 422


def test_hybrid_search_endpoint_accepts_clap_as_neutral_missing_source(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest", "clap"],
            "per_source": 3,
            "limit": 2,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["mert", "maest", "clap"]
    assert payload["results"]
    assert any(
        "source=clap" in warning and "no current candidates" in warning
        for warning in payload["warnings"]
    )
    assert payload["results"][0]["transition_diagnostics"]["components"]["source_disagreement_risk"] == 0.0


def test_hybrid_search_endpoint_does_not_touch_audio_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    audio_path = tmp_path / "not-created.wav"
    db = LibraryDatabase(db_path)
    output = current_embedding_analysis_output("mert")
    db.register_analysis_outputs((output,))
    seed_id = _track(db, tmp_path, "not-created", create_file=False)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [seed_id], "sources": ["mert"], "per_source": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert not audio_path.exists()
    assert LibraryDatabase(db_path).count_evaluation_rows()["search_sessions"] == 0


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _hybrid_library(db_path: Path, tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(db_path)
    outputs = _embedding_outputs()
    db.register_analysis_outputs(tuple(outputs.values()))
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "mert_top": _track(db, tmp_path, "mert_top"),
        "maest_top": _track(db, tmp_path, "maest_top"),
        "shared": _track(db, tmp_path, "shared"),
    }
    _save_embeddings(
        db,
        outputs,
        track_ids["seed"],
        mert=[1.0, 0.0],
        maest=[0.0, 1.0],
    )
    _save_embeddings(
        db,
        outputs,
        track_ids["mert_top"],
        mert=[0.99, 0.01],
        maest=[1.0, 0.0],
    )
    _save_embeddings(
        db,
        outputs,
        track_ids["maest_top"],
        mert=[0.0, 1.0],
        maest=[0.01, 0.99],
    )
    _save_embeddings(
        db,
        outputs,
        track_ids["shared"],
        mert=[0.8, 0.2],
        maest=[0.2, 0.8],
    )
    return db, track_ids


def _track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    *,
    create_file: bool = True,
) -> int:
    path = tmp_path / f"{stem}.wav"
    if create_file:
        path.write_bytes(stem.encode("utf-8"))
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=path.stat().st_size if create_file else 0,
            file_modified_ns=path.stat().st_mtime_ns if create_file else 1,
            audio_format="wav",
        ),
        tags=FileTags(
            artist=f"Artist {stem}",
            title=stem.replace("_", " ").title(),
            tag_bpm=124.0,
            tag_key="8A",
        ),
        scanned_at=_NOW,
    ).identity
    return identity.track_id


def _embedding_outputs() -> dict[str, AnalysisOutput]:
    maest_outputs = {
        output.contract.output_kind: output
        for output in MaestModelRunner(
            device="cpu",
            top_k=3,
            inference_batch_size=1,
        ).active_outputs
    }
    return {
        "mert": current_embedding_analysis_output("mert"),
        "maest_analysis": maest_outputs["analysis"],
        "maest": maest_outputs["embedding"],
        "clap": current_embedding_analysis_output("clap"),
    }


def _save_embeddings(
    db: LibraryDatabase,
    outputs: dict[str, AnalysisOutput],
    track_id: int,
    *,
    mert: list[float],
    maest: list[float],
) -> None:
    identity = db.get_track_identities((track_id,))[track_id]
    target = AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )
    writes: list[EmbeddingWrite] = []
    for family, values in (("mert", mert), ("maest", maest)):
        output = outputs[family]
        vector = np.zeros(output.contract.dim, dtype=np.float32)
        vector[: len(values)] = values
        vector /= np.linalg.norm(vector)
        embedding = EmbeddingOutput(
            contract=output.contract,
            vector=vector,
            analyzed_at=_NOW,
        )
        if family == "maest":
            result = db.save_maest_results(
                (
                    MaestWrite(
                        target=target,
                        analysis_contract=outputs["maest_analysis"].contract,
                        genres=(
                            MaestGenreScore(
                                label="Electronic---Test",
                                score=1.0,
                            ),
                        ),
                        syncopated_rhythm=None,
                        analyzed_at=_NOW,
                        embedding=embedding,
                    ),
                )
            )[0]
            assert result.ok, result.error
        else:
            writes.append(EmbeddingWrite(target=target, output=embedding))
    results = db.save_embedding_results(tuple(writes))
    assert all(result.ok for result in results)

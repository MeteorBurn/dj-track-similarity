from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

import dj_track_similarity.api as api
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    SonaraWrite,
)
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import SonaraRowV7
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    prepare_sonara_release,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    SonaraContractSet,
    sonara_runtime_contracts,
)
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"


class _FakeSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "5" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness"
    __sonara_vocalness_model_build_id__ = "sha256:" + "6" * 64


def test_reference_compare_returns_separate_model_groups(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "library.sqlite"
    db, tracks = _reference_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare",
        json={"seed_track_id": tracks["seed"].track_id, "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_id"] == tracks["seed"].track_id
    assert [group["model"] for group in payload["groups"]] == [
        "clap",
        "mert",
        "muq",
        "maest",
        "sonara",
    ]
    groups = {group["model"]: group for group in payload["groups"]}
    for model in ("clap", "mert", "muq", "maest", "sonara"):
        assert groups[model]["available"] is True
        assert (
            groups[model]["results"][0]["track"]["track_id"]
            == tracks[f"{model}_top"].track_id
        )
    assert not db.evaluation_path.exists()


def test_reference_compare_marks_missing_model_without_error(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    mert = _embedding_outputs()["mert"]
    db.register_analysis_outputs((mert,))
    seed = _track(db, tmp_path, "seed")
    candidate = _track(db, tmp_path, "candidate")
    _embedding(db, seed, mert, [1.0, 0.0])
    _embedding(db, candidate, mert, [0.9, 0.1])

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare",
        json={
            "seed_track_id": seed.track_id,
            "models": ["mert", "clap", "sonara"],
            "limit": 3,
        },
    )

    assert response.status_code == 200
    groups = {group["model"]: group for group in response.json()["groups"]}
    assert groups["mert"]["available"] is True
    assert groups["mert"]["results"][0]["track"]["track_id"] == candidate.track_id
    assert groups["clap"]["available"] is False
    assert groups["clap"]["results"] == []
    assert groups["sonara"]["available"] is False
    assert "active SONARA Core contract" in groups["sonara"]["reason"]


def test_reference_compare_verdict_persists_pair_feedback(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed = _track(db, tmp_path, "seed")
    candidate = _track(db, tmp_path, "candidate")

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare/verdict",
        json={
            "seed_track_id": seed.track_id,
            "candidate_track_id": candidate.track_id,
            "model": "muq",
            "verdict": "palette",
            "notes": "same pressure and texture",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_id"] == seed.track_id
    assert payload["candidate_track_id"] == candidate.track_id
    assert payload["model"] == "muq"
    assert payload["verdict"] == "palette"
    assert payload["source"] == "reference_compare:muq"
    feedback = LibraryDatabase(db_path).get_pair_feedback_map()[
        (seed.track_id, candidate.track_id, "reference_compare:muq")
    ]
    assert feedback["rating"] == 2
    assert feedback["reason_tags"] == ["palette"]
    assert feedback["notes"] == "same pressure and texture"


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _reference_library(
    db_path: Path, tmp_path: Path
) -> tuple[LibraryDatabase, dict[str, AnalysisTarget]]:
    db = LibraryDatabase(db_path)
    outputs = _embedding_outputs()
    maest_analysis = _maest_analysis_output()
    contracts = _sonara_contracts()
    backup_dir = tmp_path / "sonara-backups"
    backup_dir.mkdir()
    prepare_sonara_release(
        db,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=_FakeSonara,
    )
    db.register_analysis_outputs(
        (
            *outputs.values(),
            maest_analysis,
        )
    )
    tracks = {
        name: _track(db, tmp_path, name)
        for name in (
            "seed",
            "clap_top",
            "mert_top",
            "muq_top",
            "maest_top",
            "sonara_top",
        )
    }
    for model, vector in (
        ("clap", [1.0, 0.0]),
        ("mert", [0.0, 1.0]),
        ("muq", [0.0, 0.0, 1.0]),
        ("maest", [0.7, 0.7]),
    ):
        _embedding(
            db,
            tracks["seed"],
            outputs[model],
            vector,
            maest_analysis=maest_analysis if model == "maest" else None,
        )
        top = tracks[f"{model}_top"]
        _embedding(
            db,
            top,
            outputs[model],
            [*vector[:-1], vector[-1] * 0.98, 0.02],
            maest_analysis=maest_analysis if model == "maest" else None,
        )
    _save_sonara(db, tracks["seed"], contracts, energy=0.8, danceability=0.8)
    _save_sonara(db, tracks["sonara_top"], contracts, energy=0.79, danceability=0.79)
    return db, tracks


def _track(db: LibraryDatabase, root: Path, name: str) -> AnalysisTarget:
    path = root / f"{name}.wav"
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title=name, artist="Reference fixture"),
        scanned_at=_NOW,
    ).identity
    return AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )


def _embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
    values: list[float],
    *,
    maest_analysis: AnalysisOutput | None = None,
) -> None:
    vector = np.zeros(output.contract.dim, dtype=np.float32)
    vector[: len(values)] = values
    vector /= np.linalg.norm(vector)
    embedding = EmbeddingOutput(
        contract=output.contract,
        vector=vector,
        analyzed_at=_NOW,
    )
    if output.contract.analysis_family == "maest":
        assert maest_analysis is not None
        result = db.save_maest_results(
            (
                MaestWrite(
                    target=target,
                    analysis_contract=maest_analysis.contract,
                    genres=(MaestGenreScore(label="Techno", score=0.9),),
                    syncopated_rhythm=None,
                    analyzed_at=_NOW,
                    embedding=embedding,
                ),
            )
        )[0]
    else:
        result = db.save_embedding_results(
            (EmbeddingWrite(target=target, output=embedding),)
        )[0]
    assert result.ok, result.error


def _embedding_outputs() -> dict[str, AnalysisOutput]:
    return {
        family: current_embedding_analysis_output(family)
        for family in ("mert", "clap", "muq", "maest")
    }


def _maest_analysis_output() -> AnalysisOutput:
    return MaestModelRunner(
        device="cpu",
        top_k=5,
        inference_batch_size=1,
    ).active_outputs[0]


def _sonara_contracts() -> SonaraContractSet:
    return sonara_runtime_contracts(_FakeSonara)


def _save_sonara(
    db: LibraryDatabase,
    target: AnalysisTarget,
    contracts: SonaraContractSet,
    *,
    energy: float,
    danceability: float,
) -> None:
    values = {field.name: None for field in fields(SonaraRowV7)}
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "contract_hash": contracts.core.contract_hash,
            "energy_score": energy,
            "danceability_score": danceability,
            "valence_score": energy,
            "acousticness_score": 1.0 - energy,
            "mfcc_mean_blob": np.full(13, energy, dtype="<f4").tobytes(),
            "chroma_mean_blob": np.full(12, energy, dtype="<f4").tobytes(),
            "spectral_contrast_mean_blob": np.full(
                7, 1.0 - energy, dtype="<f4"
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    result = db.save_sonara_results(
        (
            SonaraWrite(
                target=target, core_contract=contracts.core, core=SonaraRowV7(**values)
            ),
        )
    )[0]
    assert result.ok, result.error

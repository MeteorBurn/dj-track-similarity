from __future__ import annotations

from contextlib import closing
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api.application as api
from dj_track_similarity.analysis_models import (
    EMBEDDING_LAYERS,
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    current_embedding_spec,
)
from dj_track_similarity.analysis.model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.api.application import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.ddl import SonaraRow
from sonara_test_support import complete_sonara_write, save_sonara_writes
from embedding_test_support import same_vector_layers
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"


def test_sonara_search_endpoint_uses_stored_sonara_features(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    seed = _add_sonara_track(
        db,
        tmp_path,
        "seed.wav",
        {"energy": 0.8, "danceability": 0.8, "valence": 0.25, "acousticness": 0.1},
    )
    close = _add_sonara_track(
        db,
        tmp_path,
        "close.wav",
        {"energy": 0.78, "danceability": 0.79, "valence": 0.27, "acousticness": 0.12},
    )
    far = _add_sonara_track(
        db,
        tmp_path,
        "far.wav",
        {"energy": 0.15, "danceability": 0.2, "valence": 0.8, "acousticness": 0.65},
    )

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={
            "seed_track_ids": [seed.track_id],
            "mixer_weights": {
                "timbre": 0.0,
                "rhythm": 0.0,
                "dynamics": 1.0,
                "harmonic": 0.0,
                "tempo": 0.0,
            },
            "limit": 5,
            "min_similarity": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        close.track_id,
        far.track_id,
    ]
    assert payload[0]["score"] > payload[1]["score"]


def test_generic_search_endpoint_returns_muq_result_shape(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    with TestClient(create_app(db_path)) as client:
        for family, seed_count in (("muq", 1), ("mert_v2", 6)):
            output = current_embedding_analysis_output(family)
            seeds = [
                _add_embedding_track(db, tmp_path, output, f"{family}-seed-{index}.wav", [1.0, 0.0])
                for index in range(seed_count)
            ]
            candidate = _add_embedding_track(db, tmp_path, output, f"{family}-candidate.wav", [0.9, 0.1])
            response = client.post(
                "/api/search",
                json={
                    "analysis_family": family,
                    "seed_track_ids": [seed.track_id for seed in seeds],
                    "limit": 20,
                    "min_similarity": 0.0,
                    "epsilon": 0.0,
                    "noise": 0.0,
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert len(payload) == 1
            assert payload[0]["track"]["track_id"] == candidate.track_id
            assert payload[0]["score"] == pytest.approx(0.9 / np.hypot(0.9, 0.1))
            assert payload[0]["score_breakdown"] is None
            seed_ids = [seed.track_id for seed in seeds]
            layer_count = EMBEDDING_LAYERS[family].count
            layer_request = {"analysis_family": family, "seed_track_ids": seed_ids, "layer": 12}
            for invalid_layer in (0, layer_count + 1, True, "12"):
                assert client.post(
                    "/api/search", json={**layer_request, "layer": invalid_layer}
                ).status_code == 422
            _keep_only_default_layer(db, family)
            assert client.post("/api/search", json=layer_request).status_code == 400
            for target in (*seeds, candidate):
                final = db.load_analysis_vectors(output, targets=(target,))[0].vector
                layer = np.zeros_like(final)
                layer[1 if target == candidate else 0] = 1.0
                saved = db.save_embedding_results((EmbeddingWrite(target=target, output=EmbeddingOutput(
                    family=family, vector=final, analyzed_at=_NOW,
                    layer_vectors=tuple(layer if number == 12 else final for number in range(1, layer_count + 1)),
                )),))
                assert saved[0].ok
            selected_layer = client.post("/api/search", json=layer_request)
            assert selected_layer.status_code == 200
            assert len(selected_layer.json()) == 1
            assert selected_layer.json()[0]["track"]["track_id"] == candidate.track_id
            assert selected_layer.json()[0]["score"] == pytest.approx(0.0)
        # A family that stores one vector per track has no layer to select.
        assert client.post(
            "/api/search", json={"analysis_family": "clap", "seed_track_ids": [1], "layer": 1}
        ).status_code == 422


def test_cluster_map_places_the_current_search_and_explains_it(
    monkeypatch, tmp_path: Path
) -> None:
    from dataclasses import replace

    import dj_track_similarity.api.routes_search as routes_search
    from dj_track_similarity.analysis_models import SonaraFeatureRow
    from dj_track_similarity.search.cluster_map import build_cluster_map

    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    dimension = current_embedding_spec("maest").dimension
    # Each coordinate varies independently in the fixed library background.
    # Candidate composition must never determine its own validation scale.
    scalars = {
        "tempo_variability": (0.03, 0.01),
        "onset_density_per_second": (4.0, 1.0),
        "dynamic_range_db": (10.0, 2.0),
        "loudness_range_lu": (5.0, 1.0),
        "energy_curve_stddev": (0.1, 0.02),
        "zero_crossing_rate": (0.1, 0.02),
        "spectral_centroid_hz": (2000.0, 300.0),
        "spectral_bandwidth_hz": (2500.0, 300.0),
        "spectral_rolloff_hz": (6000.0, 500.0),
        "spectral_flatness": (0.1, 0.02),
        "dissonance_score": (0.1, 0.02),
        "chord_changes_per_second": (1.0, 0.2),
    }
    vectors = {
        "chroma_mean_blob": 12,
        "mfcc_mean_blob": 13,
        "spectral_contrast_mean_blob": 7,
    }

    def profile(offsets: np.ndarray) -> dict[str, object]:
        values = {
            name: mean + scale * offset
            for (name, (mean, scale)), offset in zip(scalars.items(), offsets, strict=False)
        }
        cursor = len(scalars)
        for name, length in vectors.items():
            values[name] = np.asarray(
                1.0 + 0.1 * offsets[cursor:cursor + length], dtype="<f4"
            )
            cursor += length
        return values

    width = len(scalars) + sum(vectors.values())
    matching = profile(np.zeros(width))
    shifted = profile(np.full(width, 8.0))
    rng = np.random.default_rng(81)
    background = [profile(row) for row in rng.uniform(-1.0, 1.0, (256, width))]
    profiles: dict[int, dict[str, object]] = {}

    def add(name: str, direction: dict[int, float], values: dict[str, object]) -> AnalysisTarget:
        target = _add_sonara_track(
            db, tmp_path, name,
            {
                **{key: value for key, value in values.items() if key in scalars},
                "energy_curve_hop_seconds": 0.5, "energy_curve_sample_count": 600,
                "energy_curve_mean": 0.5, "energy_curve_min": 0.0, "energy_curve_max": 1.0,
            },
        )
        profiles[target.track_id] = values
        vector = np.zeros(dimension, dtype=np.float32)
        vector[0] = 1.0
        for axis, value in direction.items():
            vector[axis] = value
        vector /= np.linalg.norm(vector)
        result = db.save_maest_results((MaestWrite(
            target=target,
            genres=(MaestGenreScore(label="Electronic---House", score=0.9),),
            syncopated_rhythm=None, analyzed_at=_NOW,
            embedding=EmbeddingOutput(
                family="maest", vector=vector, analyzed_at=_NOW,
                layer_vectors=same_vector_layers("maest", vector),
            ),
        ),))[0]
        assert result.ok, result.error
        return target

    seeds = [add("seed-a.wav", {20: 0.2}, matching), add("seed-b.wav", {20: -0.2}, matching)]
    ordinary = [add(f"match-{i}.wav", {1: 0.1, 30 + i: 0.01}, matching) for i in range(17)]
    model_direction = add("different-model-direction.wav", {2: 0.1, 50: 0.01}, matching)
    excluded_only = add("excluded-features.wav", {1: 0.1, 51: 0.01}, {
        **matching, "detected_bpm": 85.0, "energy_score": 0.0,
        "mood_sad_score": 1.0, "vocal_probability": 1.0,
    })
    anomaly = add("sonara-deviation.wav", {1: 0.1, 52: 0.01}, shifted)
    sonara_output = db.active_analysis_output("sonara", "core")
    rows = tuple(
        replace(row, values={**row.values, **profiles[row.target.track_id]})
        for row in db.load_sonara_feature_rows(sonara_output)
    )
    calibration_rows = tuple(
        SonaraFeatureRow(
            AnalysisTarget(db.catalog_uuid, 1000 + i, f"background-{i}"),
            sonara_output, values,
        )
        for i, values in enumerate(background)
    )
    monkeypatch.setattr(LibraryDatabase, "load_sonara_feature_rows", lambda *args, **kwargs: rows + calibration_rows)
    captured = {}

    def record_map(tracks, library_sonara):
        captured["tracks"] = tracks
        captured["library"] = library_sonara
        return build_cluster_map(tracks, library_sonara)

    monkeypatch.setattr(routes_search, "build_cluster_map", record_map)
    request = {
        "analysis_family": "maest", "layer": 5,
        "seed_track_ids": [seed.track_id for seed in seeds], "limit": 20, "noise": 0,
    }
    with TestClient(create_app(db_path)) as client:
        search = client.post("/api/search", json=request)
        response = client.post("/api/search/cluster-map", json=request)

    assert search.status_code == 200
    assert response.status_code == 200, response.text
    payload = response.json()
    candidates = [point for point in payload["points"] if not point["seed"]]
    assert [point["track"]["track_id"] for point in candidates] == [
        item["track"]["track_id"] for item in search.json()
    ]
    for point, result in zip(candidates, search.json(), strict=True):
        assert point["similarity"] == pytest.approx(result["score"], abs=1e-5)
        assert point["track"]["track_uuid"] == result["track"]["track_uuid"]
    assert {point["track"]["track_id"] for point in payload["points"] if point["seed"]} == {
        seed.track_id for seed in seeds
    }
    assert payload["catalog_uuid"] == db.catalog_uuid
    assert payload["layer"] == 5
    points = {point["track"]["track_id"]: point for point in candidates}
    assert {track_id for track_id, point in points.items() if point["sonara"]["requires_listening"]} == {
        anomaly.track_id
    }
    for target in [*ordinary, model_direction, excluded_only]:
        validation = points[target.track_id]["sonara"]
        assert validation["available"]
        assert validation["distance"] == pytest.approx(0.0)
        assert not any(item["departure"] for item in validation["deviations"])
    deviation = points[anomaly.track_id]["sonara"]
    assert deviation["distance"] > points[ordinary[0].track_id]["sonara"]["distance"]
    assert all(item["available"] and item["departure"] for item in deviation["deviations"])
    assert not payload["summary"]["coherent_drift"]

    # An internally identical cohort far from the references must retain drift;
    # changing its composition never refits the library scale or the references.
    displaced_tracks = [
        item if item.seed else replace(item, sonara=shifted)
        for item in captured["tracks"]
    ]
    displaced = build_cluster_map(displaced_tracks, captured["library"])
    assert displaced.summary.coherent_drift
    assert all(item.coherent_drift for item in displaced.summary.descriptors)
    for point in displaced.points:
        if not point.seed:
            assert point.sonara.requires_listening
            assert point.sonara.distance == pytest.approx(deviation["distance"])

    # Opposing vector departures are individual deviations, not a coherent
    # shift in one direction. Magnitudes alone would falsely mark this cohort.
    opposing = []
    for index, item in enumerate(captured["tracks"]):
        vector_shift = profile(np.full(width, 8.0 if index % 2 else -8.0))
        values = {**matching, **{key: vector_shift[key] for key in vectors}}
        opposing.append(item if item.seed else replace(item, sonara=values))
    split = build_cluster_map(opposing, captured["library"])
    assert not split.summary.coherent_drift
    assert all(point.sonara.requires_listening for point in split.points if not point.seed)

    # Distinct references are alternatives: matching a real reference must
    # not become an anomaly merely because it differs from their mean.
    alternatives = [
        captured["tracks"][0],
        replace(captured["tracks"][1], sonara=shifted),
        replace(captured["tracks"][len(seeds)], sonara=shifted),
    ]
    alternative = build_cluster_map(alternatives, captured["library"]).points[2].sonara
    assert alternative.distance == pytest.approx(0.0)
    assert alternative.nearest_reference_id == seeds[1].track_id
    assert alternative.requires_listening is False

    # Missing measured evidence is unavailable, never an imputed safe match.
    single = [captured["tracks"][0], captured["tracks"][len(seeds)]]
    single[1] = replace(single[1], sonara={**matching, "tempo_variability": None})
    incomplete = build_cluster_map(single, captured["library"])
    validation = incomplete.points[1].sonara
    assert not validation.available
    assert validation.distance is None
    assert validation.percentile is None
    assert validation.requires_listening is None
    assert any(not item.available for item in validation.deviations)


def test_sonara_search_endpoint_accepts_mixer_and_modifiers(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    seed = _add_sonara_track(
        db,
        tmp_path,
        "seed.wav",
        {
            "mfcc_mean": [0.2, 0.4],
            "spectral_centroid_mean": 1600,
            "valence": 0.4,
            "energy": 0.5,
        },
    )
    brighter = _add_sonara_track(
        db,
        tmp_path,
        "brighter.wav",
        {
            "mfcc_mean": [0.22, 0.41],
            "spectral_centroid_mean": 1620,
            "valence": 0.7,
            "energy": 0.5,
        },
    )
    darker = _add_sonara_track(
        db,
        tmp_path,
        "darker.wav",
        {
            "mfcc_mean": [0.21, 0.39],
            "spectral_centroid_mean": 1580,
            "valence": 0.2,
            "energy": 0.5,
        },
    )

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={
            "seed_track_ids": [seed.track_id],
            "limit": 5,
            "min_similarity": 0.0,
            "mixer_weights": {
                "timbre": 1.0,
                "rhythm": 0.0,
                "dynamics": 0.0,
                "harmonic": 0.0,
                "tempo": 0.0,
            },
            "modifiers": {"valence": 1.0, "aggression": 0.0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        brighter.track_id,
        darker.track_id,
    ]
    assert "timbre" in payload[0]["score_breakdown"]
    assert "modifier_valence" in payload[0]["score_breakdown"]


def test_random_sonara_track_uses_an_unselected_current_sonara_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    targets = [
        _add_sonara_track(db, tmp_path, "one.wav", {"energy": 0.2}),
        _add_sonara_track(db, tmp_path, "two.wav", {"energy": 0.5}),
        _add_sonara_track(db, tmp_path, "three.wav", {"energy": 0.8}),
    ]

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara/random-track",
        json={"exclude_track_ids": [targets[0].track_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] in {target.track_id for target in targets[1:]}
    assert payload["analysis_coverage"]["sonara_core"] is True


def test_random_sonara_track_requires_an_available_sonara_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)

    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/sonara/random-track",
        json={},
    )

    assert response.status_code == 409
    assert "SONARA Core" in response.json()["detail"]


def test_random_embedding_track_uses_an_unselected_embedded_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = current_embedding_analysis_output("mert_v2")
    db.register_analysis_outputs((output,))
    targets = [
        _add_embedding_track(db, tmp_path, output, "one.wav", [1.0, 0.0]),
        _add_embedding_track(db, tmp_path, output, "two.wav", [0.9, 0.1]),
        _add_embedding_track(db, tmp_path, output, "three.wav", [0.0, 1.0]),
    ]
    _track(db, tmp_path, "without-embedding.wav")

    response = TestClient(create_app(db_path)).post(
        "/api/search/random-track",
        json={"analysis_family": "mert_v2", "exclude_track_ids": [targets[0].track_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] in {target.track_id for target in targets[1:]}
    assert payload["analysis_coverage"]["mert_v2"] is True
    client = TestClient(create_app(db_path))
    _keep_only_default_layer(db, "mert_v2")
    assert client.post("/api/search/random-track", json={"analysis_family": "mert_v2", "layer": 12}).status_code == 409
    assert client.post("/api/search/random-track", json={"analysis_family": "mulan", "layer": 12}).status_code == 422
    target = targets[1]
    vector = db.load_analysis_vectors(output, targets=(target,))[0].vector
    saved = db.save_embedding_results((EmbeddingWrite(target=target, output=EmbeddingOutput(
        family="mert_v2", vector=vector, analyzed_at=_NOW, layer_vectors=tuple(vector for _ in range(24)),
    )),))
    assert saved[0].ok
    layer_pick = client.post("/api/search/random-track", json={"analysis_family": "mert_v2", "layer": 12})
    assert layer_pick.status_code == 200
    assert layer_pick.json()["track_id"] == target.track_id
    assert client.post("/api/search/random-track", json={"analysis_family": "mert_v2", "layer": 12,
                                                       "exclude_track_ids": [target.track_id]}).status_code == 409


def test_random_embedding_track_requires_an_available_embedded_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = _muq_output()
    db.register_analysis_outputs((output,))
    only = _add_embedding_track(db, tmp_path, output, "only.wav", [1.0, 0.0])

    response = TestClient(create_app(db_path)).post(
        "/api/search/random-track",
        json={"analysis_family": "muq", "exclude_track_ids": [only.track_id]},
    )

    assert response.status_code == 409
    assert "muq" in response.json()["detail"]


def test_sonara_search_enforces_the_shared_seed_contract(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    too_many = client.post(
        "/api/search/sonara", json={"seed_track_ids": [1, 2, 3, 4, 5, 6]}
    )
    duplicates = client.post(
        "/api/search/sonara", json={"seed_track_ids": [1, 1]}
    )
    non_positive = client.post(
        "/api/search/sonara", json={"seed_track_ids": [0]}
    )

    assert too_many.status_code == 422
    assert duplicates.status_code == 422
    assert non_positive.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 501},
        {"min_similarity": -0.1},
        {"min_similarity": 1.1},
        {"epsilon": -0.1},
        {"noise": -0.1},
        {"noise": 1.1},
    ],
)
def test_generic_search_endpoint_rejects_invalid_numeric_fields(
    monkeypatch, tmp_path: Path, payload: dict[str, float]
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/search", json={"seed_track_ids": [1], **payload})

    assert response.status_code == 422


def _sonara_library(db_path: Path) -> LibraryDatabase:
    return LibraryDatabase(db_path)


def _add_sonara_track(
    db: LibraryDatabase,
    root: Path,
    name: str,
    features: dict[str, float | list[float]],
) -> AnalysisTarget:
    target = _track(db, root, name)
    values = {field.name: None for field in fields(SonaraRow)}
    energy = _float(features.get("energy"))
    values.update(
        {
            "track_id": target.track_id,
            "energy_score": energy,
            "danceability_score": _float(features.get("danceability")),
            "valence_score": _float(features.get("valence")),
            "acousticness_score": _float(features.get("acousticness")),
            "spectral_centroid_hz": _float(features.get("spectral_centroid_mean")),
            "mfcc_mean_blob": _blob(features.get("mfcc_mean"), 13),
            "chroma_mean_blob": _blob(None, 12),
            "spectral_contrast_mean_blob": _blob(None, 7),
            "analysis_schema_version": 6,
            "analyzed_at": _NOW,
        }
    )
    # Keys named like a SonaraRow column are stored as given.
    values.update(
        {
            name: value if isinstance(value, int) else _float(value)
            for name, value in features.items()
            if name in values
        }
    )
    result = save_sonara_writes(
        db,
        (
            complete_sonara_write(target, SonaraRow(**values)),
        )
    )[0]
    assert result.ok, result.error
    return target


def _add_embedding_track(
    db: LibraryDatabase,
    root: Path,
    output: AnalysisOutput,
    name: str,
    embedding: list[float],
) -> AnalysisTarget:
    target = _track(db, root, name)
    vector = np.zeros(
        current_embedding_spec(output.analysis_family).dimension,
        dtype=np.float32,
    )
    vector[: len(embedding)] = embedding
    vector /= np.linalg.norm(vector)
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=vector,
                    analyzed_at=_NOW,
                    layer_vectors=same_vector_layers(output.analysis_family, vector),
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target


def _keep_only_default_layer(db: LibraryDatabase, family: str) -> None:
    """Leave each track only its default layer, as a migrated library holds it."""

    with closing(db.connect()) as connection, connection:
        connection.execute(
            f"DELETE FROM {family}_embeddings WHERE layer != ?",
            (EMBEDDING_LAYERS[family].default,),
        )


def _track(db: LibraryDatabase, root: Path, name: str) -> AnalysisTarget:
    path = root / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title=name),
        scanned_at=_NOW,
    ).identity
    return AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
    )


def _muq_output() -> AnalysisOutput:
    return current_embedding_analysis_output("muq")


def _float(value: float | list[float] | None) -> float | None:
    return float(value) if isinstance(value, (float, int)) else None


def _blob(value: float | list[float] | None, dim: int) -> bytes:
    values = list(value) if isinstance(value, list) else []
    values.extend([0.0] * (dim - len(values)))
    return np.asarray(values[:dim], dtype="<f4").tobytes()

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


def test_cluster_map_explains_the_current_search_by_sonara_alone(
    monkeypatch, tmp_path: Path
) -> None:
    from dataclasses import replace

    import dj_track_similarity.api.routes_search as routes_search
    from dj_track_similarity.analysis_models import SonaraFeatureRow
    from dj_track_similarity.search.cluster_map import build_cluster_map
    from dj_track_similarity.search.sonara_descriptors import DESCRIPTOR_KEYS, FACET_KEYS, describe

    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    dimension = current_embedding_spec("maest").dimension
    # Each measured column varies independently in the fixed library background;
    # the candidates never set their own scale.
    scalars = {
        "detected_bpm": (124.0, 3.0),
        "onset_density_per_second": (4.0, 1.0),
        "tempo_variability": (0.03, 0.01),
        "beat_grid_stability": (0.8, 0.05),
        "integrated_loudness_lufs": (-9.0, 1.0),
        "loudness_range_lu": (5.0, 1.0),
        "dynamic_range_db": (10.0, 2.0),
        "energy_curve_stddev": (0.1, 0.02),
        "spectral_centroid_hz": (2000.0, 300.0),
        "spectral_bandwidth_hz": (2500.0, 300.0),
        "spectral_rolloff_hz": (6000.0, 500.0),
        "spectral_flatness": (0.1, 0.02),
        "zero_crossing_rate": (0.1, 0.02),
        "dissonance_score": (0.1, 0.02),
        "chord_changes_per_second": (1.0, 0.2),
    }
    spectral = ("spectral_centroid_hz", "spectral_bandwidth_hz", "spectral_rolloff_hz",
                "spectral_flatness", "zero_crossing_rate")
    vectors = {"mfcc_mean_blob": 13, "chroma_mean_blob": 12, "spectral_contrast_mean_blob": 7}
    width = len(scalars) + sum(vectors.values())

    def profile(offsets: np.ndarray) -> dict[str, object]:
        values: dict[str, object] = {
            name: mean + scale * offset
            for (name, (mean, scale)), offset in zip(scalars.items(), offsets, strict=False)
        }
        cursor = len(scalars)
        for name, length in vectors.items():
            values[name] = tuple(1.0 + 0.1 * offsets[cursor:cursor + length])
            cursor += length
        values["analyzed_duration_seconds"] = 300.0
        return values

    def shifted(values: dict[str, object], sign: float = 1.0) -> dict[str, object]:
        return {**values, **{name: scalars[name][0] + sign * 8 * scalars[name][1] for name in spectral}}

    matching = profile(np.zeros(width))
    rng = np.random.default_rng(81)
    background = [profile(row) for row in rng.uniform(-1.0, 1.0, (256, width))]
    # One stored Timeline for everyone: its descriptors can never separate tracks.
    beats = list(range(0, 12_000, 20))
    timeline = {
        "beats": beats, "onsets": [b + offset for b in beats for offset in (0, 10)],
        "energy_curve": [0.5 + 0.2 * np.sin(i / 20) for i in range(600)], "energy_curve_hop_seconds": 0.5,
        "loudness_curve": [-9.0] * 300, "tempo_curve": [124.0] * len(beats),
        "segments": [{"start_sec": 0.0, "end_sec": 300.0, "energy": 0.5}],
        "chord_events": [{"label": "Am", "start_sec": 0.0, "end_sec": 200.0}, {"label": "C", "start_sec": 200.0, "end_sec": 300.0}],
    }
    profiles: dict[int, dict[str, object]] = {}

    def add(name: str, direction: dict[int, float], values: dict[str, object]) -> AnalysisTarget:
        target = _add_sonara_track(db, tmp_path, name, {})
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
    heuristics_only = add("excluded-heuristics.wav", {1: 0.1, 51: 0.01}, {
        **matching, "energy_score": 0.0, "danceability_score": 1.0, "mood_sad_score": 1.0,
        "aggression_score": 1.0, "vocal_probability": 1.0,
    })
    anomaly = add("brighter.wav", {1: 0.1, 52: 0.01}, shifted(matching))
    sonara_output = db.active_analysis_output("sonara", "core")
    stored = {row.target: row for row in db.load_sonara_feature_rows(sonara_output)}
    rows = {
        target: replace(row, values={**row.values, **profiles[target.track_id]})
        for target, row in stored.items()
    }
    rows |= {
        (target := AnalysisTarget(db.catalog_uuid, 1000 + i, f"background-{i}")): SonaraFeatureRow(target, sonara_output, values)
        for i, values in enumerate(background)
    }
    monkeypatch.setattr(LibraryDatabase, "load_sonara_feature_rows",
                        lambda self, output, *, targets=None: tuple(rows.values()) if targets is None
                        else tuple(rows[target] for target in targets if target in rows))
    monkeypatch.setattr(LibraryDatabase, "load_sonara_timelines",
                        lambda self, targets: {target: timeline for target in targets})
    captured = {}

    def record_map(background_scales, tracks, *, shown, **pool):
        captured.update(background=background_scales, tracks=tracks, shown=shown)
        return build_cluster_map(background_scales, tracks, shown=shown, **pool)

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
    # The map shows exactly the search: identities, order and model scores.
    assert [point["track"]["track_id"] for point in candidates] == [item["track"]["track_id"] for item in search.json()]
    for rank, (point, result) in enumerate(zip(candidates, search.json(), strict=True), start=1):
        assert point["rank"] == rank
        assert point["similarity"] == pytest.approx(result["score"], abs=1e-5)
        assert point["track"]["track_uuid"] == result["track"]["track_uuid"]
    assert {point["track"]["track_id"] for point in payload["points"] if point["seed"]} == {s.track_id for s in seeds}
    assert payload["catalog_uuid"] == db.catalog_uuid and payload["layer"] == 5
    assert payload["background_count"] == len(rows)
    # The pool is every track the model could have returned, references aside.
    assert payload["summary"]["pool_size"] == payload["summary"]["pool_count"] == len(ordinary) + 3

    points = {point["track"]["track_id"]: point["evidence"] for point in candidates}
    spectrum = FACET_KEYS.index("spectrum")
    # A different model direction or different heuristic labels are not SONARA
    # distance: only measured physics moves a point.
    for target in [*ordinary, model_direction, heuristics_only]:
        assert points[target.track_id]["distance"] == pytest.approx(0.0, abs=1e-9)
    evidence = points[anomaly.track_id]
    assert evidence["distance"] > 0.5
    # The explanation is the exact split of the same distance.
    assert sum(evidence["contribution"]) == pytest.approx(1.0)
    assert evidence["facet_share"][spectrum] == pytest.approx(1.0)
    assert evidence["facet_percentile"][spectrum] > 99
    assert not payload["summary"]["shifts"]

    # Scales and the centre never refit on the returned tracks: a cohort shifted
    # together keeps each track's distance and shows a coherent shift.
    displaced = [item if item.seed else replace(item, core=shifted(dict(item.core))) for item in captured["tracks"]]
    moved = build_cluster_map(captured["background"], displaced, shown=captured["shown"])
    for point in moved.points:
        if not point.seed:
            assert point.evidence.distance == pytest.approx(evidence["distance"])
    shift_keys = {DESCRIPTOR_KEYS[item.descriptor] for item in moved.summary.shifts}
    assert shift_keys == {"centroid", "bandwidth", "rolloff", "flatness", "zcr"}
    assert all(item.median > 0 for item in moved.summary.shifts)

    # Opposite departures are individual deviations, not a shift of the output.
    opposing = [
        item if item.seed else replace(item, core=shifted(dict(item.core), 1.0 if index % 2 else -1.0))
        for index, item in enumerate(captured["tracks"])
    ]
    assert not build_cluster_map(captured["background"], opposing, shown=captured["shown"]).summary.shifts

    # A missing measurement stays unknown instead of becoming a safe match.
    first = next(item for item in captured["tracks"] if item.track.track_id in {t.track_id for t in ordinary})
    single = [*(item for item in captured["tracks"] if item.seed),
              replace(first, rank=1, core={**first.core, "spectral_centroid_hz": None, "detected_bpm": None})]
    unknown = next(point for point in build_cluster_map(captured["background"], single, shown=1).points if not point.seed)
    assert unknown.evidence.delta[DESCRIPTOR_KEYS.index("centroid")] is None
    assert unknown.evidence.facet_distance[FACET_KEYS.index("tempo")] is None
    assert unknown.evidence.facet_distance[spectrum] == pytest.approx(0.0)

    # The model's own pool is the fair null for its picks: against a pool that
    # already sits on the references, a candidate the library calls close is far.
    nudged = [
        item if item.seed else replace(item, core={
            **item.core, **{name: scalars[name][0] + scalars[name][1] for name in spectral}
        })
        for item in captured["tracks"]
    ]
    on_references = np.vstack([describe(matching, timeline)[0]] * 50)
    judged = build_cluster_map(captured["background"], nudged, shown=captured["shown"], pool=on_references, pool_size=50)
    near = next(point for point in judged.points if not point.seed)
    assert near.evidence.percentile < 50
    assert near.evidence.pool_percentile == pytest.approx(100.0)
    assert judged.summary.pool_preservation[spectrum].median == pytest.approx(100.0)


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

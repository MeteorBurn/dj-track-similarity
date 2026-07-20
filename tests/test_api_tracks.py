from pathlib import Path
import json
import subprocess
import wave

from fastapi.testclient import TestClient

import numpy as np

import dj_track_similarity.api as api_module
import dj_track_similarity.database as database_module
import dj_track_similarity.media_preview as media_preview_module
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature
from dj_track_similarity.sonara_features import sonara_analysis_signatures_for_outputs


def test_tracks_endpoint_returns_paginated_slim_items_and_total(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _add_track(db, tmp_path, "alpha.wav", "Artist A", "Alpha", {"comment": "large metadata"})
    _add_track(db, tmp_path, "beta.wav", "Artist B", "Beta", {"comment": "large metadata"})
    _add_track(db, tmp_path, "gamma.wav", "Artist C", "Gamma", {"comment": "large metadata"})

    response = TestClient(create_app(db_path)).get("/api/tracks?limit=2&offset=1&include_metadata=false")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["title"] for item in payload["items"]] == ["Beta", "Gamma"]
    assert all(item["metadata"] is None for item in payload["items"])


def test_tracks_endpoints_return_empty_contract_for_new_database(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _ = LibraryDatabase(db_path)
    client = TestClient(create_app(db_path))

    page_response = client.get("/api/tracks", params={"limit": 50, "offset": 0, "include_metadata": "false"})
    filtered_response = client.post("/api/tracks/filtered", json={"query": "missing", "liked": True})

    assert page_response.status_code == 200
    assert page_response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
    assert filtered_response.status_code == 200
    assert filtered_response.json() == {"items": [], "total": 0}


def test_track_sonara_timeline_endpoint_returns_lazy_sidecar_data(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    with_curves_id = _add_track(db, tmp_path, "curves.wav", "Artist", "Curves", {})
    without_curves_id = _add_track(db, tmp_path, "plain.wav", "Artist", "Plain", {})
    stale_curves_id = _add_track(db, tmp_path, "stale-curves.wav", "Artist", "Stale Curves", {})
    curves = {
        "energy_curve": {"type": "list", "value": [0.1, 0.4, 0.8], "length": 3},
        "loudness_curve": {"type": "list", "value": [-18.0, -12.0], "length": 2},
        "downbeats": {"type": "list", "value": [0, 4, 8], "length": 3},
    }
    signature = sonara_analysis_signatures_for_outputs(["timeline"])["timeline"]
    db.save_sonara_timeline(
        with_curves_id,
        curves,
        provenance={"package_version": "0.2.9"},
        analysis_signature=signature,
    )
    db.save_sonara_timeline(
        stale_curves_id,
        curves,
        provenance={"package_version": "0.2.9"},
        analysis_signature=signature,
    )
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE timeline.sonara_timeline
            SET analysis_signature_json = json_set(analysis_signature_json, '$.schema_version', 2)
            WHERE track_id = ?
            """,
            (stale_curves_id,),
        )
    client = TestClient(create_app(db_path))

    stored = client.get(f"/api/tracks/{with_curves_id}/sonara-timeline")
    empty = client.get(f"/api/tracks/{without_curves_id}/sonara-timeline")
    stale = client.get(f"/api/tracks/{stale_curves_id}/sonara-timeline")
    missing = client.get("/api/tracks/999999/sonara-timeline")

    assert stored.status_code == 200
    assert stored.json()["energy_curve"]["value"] == [0.1, 0.4, 0.8]
    assert stored.json()["loudness_curve"]["value"] == [-18.0, -12.0]
    assert stored.json()["downbeats"]["value"] == [0, 4, 8]
    assert empty.status_code == 200
    assert empty.json() == {}
    assert stale.status_code == 200
    assert stale.json() == {}
    assert db.load_sonara_timeline(stale_curves_id) is None
    assert missing.status_code == 404


def test_tracks_endpoint_does_not_parse_metadata_for_slim_items(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "analyzed.wav", "Artist", "Analyzed", {"comment": "large metadata"})
    db.save_sonara_features(
        track_id,
        {"energy": 0.7},
        energy=0.7,
        model_name="sonara-test",
        analysis_signature=expected_sonara_analysis_signature([]),
    )
    db.save_genres(track_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    db.save_embedding(track_id, np.asarray([0.0, 1.0], dtype=np.float32), model_name="maest-test", embedding_key="maest")
    db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), model_name="mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0, 1.0], dtype=np.float32), model_name="muq-test", embedding_key="muq")

    def fail_if_metadata_parsed(_metadata_json: object) -> dict[str, object]:
        raise AssertionError("slim track rows must not parse metadata_json")

    monkeypatch.setattr(database_module, "metadata_from_json", fail_if_metadata_parsed)

    response = TestClient(create_app(db_path)).get("/api/tracks?limit=1&include_metadata=false")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["metadata"] is None
    assert item["analyses"] == ["sonara", "maest", "mert", "muq"]


def test_tracks_endpoint_filters_by_query_and_syncopated_preset(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(db, tmp_path, "house.wav", "DJ One", "Deep House", {})
    breaks_id = _add_track(db, tmp_path, "breaks.wav", "DJ Two", "Broken Rhythm", {})
    db.save_genres(house_id, [{"label": "House", "score": 0.8}], model_name="maest")
    db.save_genres(breaks_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest")
    client = TestClient(create_app(db_path))

    query_payload = client.get("/api/tracks?q=two").json()
    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert query_payload["total"] == 1
    assert query_payload["items"][0]["id"] == breaks_id
    assert preset_payload["total"] == 1
    assert preset_payload["items"][0]["id"] == breaks_id


def test_tracks_endpoint_keeps_like_default_and_supports_explicit_fts_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    substring_id = _add_track(db, tmp_path, "substring.wav", "DJ One", "AlphaBeta", {})
    token_id = _add_track(db, tmp_path, "token.wav", "DJ Two", "Deep House", {})
    client = TestClient(create_app(db_path))

    like_payload = client.get("/api/tracks", params={"q": "phaB"}).json()
    fts_substring_payload = client.get("/api/tracks", params={"q": "phaB", "search_mode": "fts"}).json()
    fts_token_payload = client.get("/api/tracks", params={"q": "deep house", "search_mode": "fts"}).json()
    invalid_payload = client.get("/api/tracks", params={"q": "deep", "search_mode": "legacy"})

    assert [item["id"] for item in like_payload["items"]] == [substring_id]
    assert fts_substring_payload["total"] == 0
    assert [item["id"] for item in fts_token_payload["items"]] == [token_id]
    assert invalid_payload.status_code == 422


def test_tracks_endpoint_toggles_and_filters_liked_tracks(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first_id = _add_track(db, tmp_path, "first.wav", "DJ One", "First", {})
    second_id = _add_track(db, tmp_path, "second.wav", "DJ Two", "Second", {})
    client = TestClient(create_app(db_path))

    liked = client.post(f"/api/tracks/{second_id}/liked", json={"liked": True})
    liked_page = client.get("/api/tracks", params={"liked": "true"})
    all_page = client.get("/api/tracks")
    unliked = client.post(f"/api/tracks/{second_id}/liked", json={"liked": False})
    empty_liked_page = client.get("/api/tracks", params={"liked": "true"})

    assert liked.status_code == 200
    assert liked.json()["liked"] is True
    assert liked_page.status_code == 200
    assert liked_page.json()["total"] == 1
    assert [item["id"] for item in liked_page.json()["items"]] == [second_id]
    assert liked_page.json()["items"][0]["liked"] is True
    assert [item["liked"] for item in all_page.json()["items"]] == [False, True]
    assert first_id != second_id
    assert unliked.status_code == 200
    assert unliked.json()["liked"] is False
    assert empty_liked_page.json()["items"] == []


def test_tracks_endpoint_orders_liked_tracks_by_like_time(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    older_id = _add_track(db, tmp_path, "older.wav", "ZZZ Artist", "Older Like", {})
    newer_id = _add_track(db, tmp_path, "newer.wav", "AAA Artist", "Newer Like", {})
    db.set_track_liked(older_id, True)
    db.set_track_liked(newer_id, True)
    with db.connect() as connection:
        connection.execute("UPDATE track_likes SET liked_at = ? WHERE track_id = ?", ("2026-01-01 00:00:00", older_id))
        connection.execute("UPDATE track_likes SET liked_at = ? WHERE track_id = ?", ("2026-01-01 00:00:01", newer_id))
    client = TestClient(create_app(db_path))

    liked_page = client.get("/api/tracks", params={"liked": "true"})
    filtered_page = client.post("/api/tracks/filtered", json={"liked": True})

    assert liked_page.status_code == 200
    assert [item["id"] for item in liked_page.json()["items"]] == [older_id, newer_id]
    assert filtered_page.status_code == 200
    assert [item["id"] for item in filtered_page.json()["items"]] == [older_id, newer_id]


def test_tracks_endpoint_filters_by_classifier_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    low_id = _add_track(db, tmp_path, "low.wav", "DJ One", "Low Energy", {})
    high_id = _add_track(db, tmp_path, "high.wav", "DJ Two", "High Energy", {})
    db.save_classifier_score(
        low_id,
        classifier="break_energy",
        score=0.71,
        label="medium",
        confidence=0.71,
        probabilities={"break_energy": 0.71, "straight_energy": 0.29},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="break_energy",
        score=0.93,
        label="high",
        confidence=0.93,
        probabilities={"break_energy": 0.93, "straight_energy": 0.07},
        feature_set="combined",
        model_id="model.joblib",
    )
    client = TestClient(create_app(db_path))

    response = client.get("/api/tracks", params={"classifier_min_scores": '{"break_energy": 0.9}'})
    filtered = client.post("/api/tracks/filtered", json={"classifier_min_scores": {"break_energy": 0.9}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == high_id
    assert payload["items"][0]["classifier_scores"]["break_energy"]["score"] == 0.93
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [high_id]


def test_tracks_endpoint_filters_by_generic_classifier_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    low_id = _add_track(db, tmp_path, "low-live.wav", "DJ One", "Low Live", {})
    high_id = _add_track(db, tmp_path, "high-live.wav", "DJ Two", "High Live", {})
    db.save_classifier_score(
        low_id,
        classifier="live_instrumentation",
        score=0.41,
        label="low",
        confidence=0.59,
        probabilities={"live_instrument": 0.41, "no_instrument": 0.59},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="live_instrumentation",
        score=0.88,
        label="high",
        confidence=0.88,
        probabilities={"live_instrument": 0.88, "no_instrument": 0.12},
        feature_set="combined",
        model_id="model.joblib",
    )
    client = TestClient(create_app(db_path))

    response = client.get("/api/tracks", params={"classifier_min_scores": '{"live_instrumentation": 0.8}'})
    filtered = client.post(
        "/api/tracks/filtered",
        json={"classifier_min_scores": {"live_instrumentation": 0.8}},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [high_id]
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [high_id]


def test_classifier_analyze_endpoint_uses_classifier_key(monkeypatch, tmp_path: Path) -> None:
    from dj_track_similarity.classifier_jobs import ClassifierJobManager, ClassifierJobStatus

    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    seen: dict[str, object] = {}

    def fake_start(self, *, classifier: str, limit: int | None = None, model_path=None):
        seen["classifier"] = classifier
        seen["limit"] = limit
        return ClassifierJobStatus(
            job_id="job-1",
            state="queued",
            adapter_name=classifier,
            embedding_key=classifier,
            total=0,
        )

    monkeypatch.setattr(ClassifierJobManager, "start", fake_start)
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [{"classifier_key": "live_instrumentation", "is_scoring_compatible": True}],
    )
    client = TestClient(create_app(db_path))

    response = client.post("/api/classifiers/live_instrumentation/analyze", json={"limit": 7})

    assert response.status_code == 200
    assert response.json()["adapter_name"] == "live_instrumentation"
    assert seen == {"classifier": "live_instrumentation", "limit": 7}


def test_classifier_job_endpoints_scope_lookup_to_classifier_key(monkeypatch, tmp_path: Path) -> None:
    from dj_track_similarity.classifier_jobs import ClassifierJobManager, ClassifierJobStatus

    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    calls: list[tuple[str, str | None, str | None]] = []

    def status(job_id: str = "job-1") -> ClassifierJobStatus:
        return ClassifierJobStatus(
            job_id=job_id,
            state="queued",
            adapter_name="live_instrumentation",
            embedding_key="live_instrumentation",
            total=0,
        )

    def fake_latest(self, *, classifier: str | None = None):
        calls.append(("latest", classifier, None))
        return status()

    def fake_get(self, job_id: str, *, classifier: str | None = None):
        calls.append(("get", classifier, job_id))
        return status(job_id)

    def fake_cancel(self, job_id: str, *, classifier: str | None = None):
        calls.append(("cancel", classifier, job_id))
        return status(job_id)

    monkeypatch.setattr(ClassifierJobManager, "latest", fake_latest)
    monkeypatch.setattr(ClassifierJobManager, "get", fake_get)
    monkeypatch.setattr(ClassifierJobManager, "cancel", fake_cancel)
    client = TestClient(create_app(db_path))

    latest = client.get("/api/classifiers/live_instrumentation/analyze/jobs/latest")
    fetched = client.get("/api/classifiers/live_instrumentation/analyze/jobs/job-2")
    cancelled = client.post("/api/classifiers/live_instrumentation/analyze/jobs/job-3/cancel")

    assert latest.status_code == 200
    assert fetched.status_code == 200
    assert cancelled.status_code == 200
    assert calls == [
        ("latest", "live_instrumentation", None),
        ("get", "live_instrumentation", "job-2"),
        ("cancel", "live_instrumentation", "job-3"),
    ]


def test_classifier_job_endpoint_returns_404_for_unknown_scoped_job(monkeypatch, tmp_path: Path) -> None:
    from dj_track_similarity.classifier_jobs import ClassifierJobManager

    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)

    def fake_get(self, job_id: str, *, classifier: str | None = None):
        raise KeyError(f"{classifier}:{job_id}")

    monkeypatch.setattr(ClassifierJobManager, "get", fake_get)
    client = TestClient(create_app(db_path))

    response = client.get("/api/classifiers/live_instrumentation/analyze/jobs/missing-job")

    assert response.status_code == 404
    assert "missing-job" in response.json()["detail"]


def test_classifier_reset_endpoint_deletes_requested_scores_only(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "track.wav", "DJ One", "Track", {})
    for classifier in ["break_energy", "live_instrumentation", "other_classifier"]:
        db.save_classifier_score(
            track_id,
            classifier=classifier,
            score=0.9,
            label="high",
            confidence=0.9,
            probabilities={"positive": 0.9, "negative": 0.1},
            feature_set="combined",
            model_id="model.joblib",
        )
    client = TestClient(create_app(db_path))

    response = client.post(
        "/api/classifiers/reset",
        json={"classifiers": ["break_energy", "live_instrumentation"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "classifiers": ["break_energy", "live_instrumentation"],
        "scores_deleted": 2,
    }
    assert db.classifier_score(track_id, "break_energy") is None
    assert db.classifier_score(track_id, "live_instrumentation") is None
    assert db.classifier_score(track_id, "other_classifier") is not None


def test_classifiers_endpoint_lists_promoted_model_metadata(tmp_path: Path, monkeypatch) -> None:
    import dj_track_similarity.api as api_module

    root = tmp_path / "models" / "classifiers" / "live-instrumentation"
    root.mkdir(parents=True)
    (root / "model.joblib").write_bytes(b"model")
    (root / "model.json").write_text(
        json.dumps(
            {
                "classifier_key": "live_instrumentation",
                "profile_name": "Live Instrumentation",
                "artifact_prefix": "live-instrumentation",
                "positive_label": "live_instrument",
                "label_order": ["live_instrument", "no_instrument"],
            }
        ),
        encoding="utf-8",
    )
    from dj_track_similarity.classifier_scoring import promoted_classifiers

    monkeypatch.setattr(api_module, "promoted_classifiers", lambda: promoted_classifiers(root.parent))
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    client = TestClient(create_app(db_path))

    response = client.get("/api/classifiers")

    assert response.status_code == 200
    assert response.json()[0]["classifier_key"] == "live_instrumentation"


def test_filtered_tracks_endpoint_returns_all_matching_tracks_without_pagination(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(db, tmp_path, "house.wav", "DJ One", "Deep House", {})
    breaks_id = _add_track(db, tmp_path, "breaks.wav", "DJ Two", "Broken Rhythm", {})
    garage_id = _add_track(db, tmp_path, "garage.wav", "DJ Three", "Broken Garage", {})
    db.save_genres(house_id, [{"label": "House", "score": 0.8}], model_name="maest")
    db.save_genres(breaks_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest")
    db.save_genres(garage_id, [{"label": "UK Garage", "score": 0.9}], model_name="maest")
    client = TestClient(create_app(db_path))

    response = client.post("/api/tracks/filtered", json={"query": "broken", "preset": "syncopated"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [garage_id, breaks_id]
    assert all(item["metadata"] is None for item in payload["items"])


def test_syncopated_preset_ignores_non_genre_metadata_text(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(
        db,
        tmp_path,
        "house.wav",
        "DJ One",
        "Deep House",
        {"sonara_features": {"acousticness": {"description": "Acoustic versus electronic character estimate."}}},
    )
    db.save_genres(house_id, [{"label": "Tech House", "score": 0.8}], model_name="maest")
    client = TestClient(create_app(db_path))

    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert preset_payload["total"] == 0
    assert preset_payload["items"] == []


def test_syncopated_preset_uses_stored_maest_syncopated_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    legacy_breaks_id = _add_track(
        db,
        tmp_path,
        "legacy-breaks.wav",
        "DJ One",
        "Legacy Breaks",
        {"maest_genres": [{"label": "Breakbeat", "score": 0.9}], "maest_model": "legacy-maest"},
    )
    flagged_house_id = _add_track(
        db,
        tmp_path,
        "flagged-house.wav",
        "DJ Two",
        "Flagged House",
        {"maest_genres": [{"label": "House", "score": 0.8}], "maest_model": "maest", "maest_syncopated_rhythm": True},
    )
    client = TestClient(create_app(db_path))

    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert preset_payload["total"] == 1
    assert preset_payload["items"][0]["id"] == flagged_house_id
    assert legacy_breaks_id != flagged_house_id


def test_track_detail_endpoint_returns_full_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "alpha.wav", "Artist", "Alpha", {"comment": "stored comment"})

    response = TestClient(create_app(db_path)).get(f"/api/tracks/{track_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == track_id
    assert payload["metadata"]["comment"] == "stored comment"


def test_library_summary_counts_tracks_and_analysis_families(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    sonara_id = _add_track(db, tmp_path, "sonara.wav", "Artist", "Sonara", {})
    maest_id = _add_track(db, tmp_path, "maest.wav", "Artist", "Maest", {})
    maest_genres_only_id = _add_track(db, tmp_path, "maest-genres-only.wav", "Artist", "Maest Genres Only", {})
    mert_id = _add_track(db, tmp_path, "mert.wav", "Artist", "Mert", {})
    db.save_sonara_features(
        sonara_id,
        {"energy": 0.7},
        energy=0.7,
        model_name="sonara-test",
        analysis_signature=expected_sonara_analysis_signature([]),
    )
    db.save_genres(maest_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    db.save_embedding(maest_id, np.asarray([0.0, 1.0], dtype=np.float32), model_name="maest-test", embedding_key="maest")
    db.save_genres(maest_genres_only_id, [{"label": "House", "score": 0.8}], model_name="maest-test")
    db.save_embedding(mert_id, np.asarray([1.0, 0.0], dtype=np.float32), model_name="mert-test", embedding_key="mert")
    db.save_embedding(mert_id, np.asarray([1.0, 1.0], dtype=np.float32), model_name="muq-test", embedding_key="muq")
    db.set_track_liked(mert_id, True)

    response = TestClient(create_app(db_path)).get("/api/library/summary")

    assert response.status_code == 200
    assert response.json() == {"tracks": 4, "sonara": 1, "maest": 1, "mert": 1, "muq": 1, "clap": 0, "liked": 1, "classifiers": 0}


def test_library_summary_and_track_status_ignore_unsigned_sonara(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "legacy.wav", "Artist", "Legacy", {})
    db.save_sonara_features(track_id, {"bpm": 128.0}, bpm=128.0, model_name="sonara-legacy")
    client = TestClient(create_app(db_path))

    summary = client.get("/api/library/summary").json()
    track = client.get("/api/tracks?include_metadata=false").json()["items"][0]

    assert summary["sonara"] == 0
    assert track["analyses"] is None


def test_library_summary_counts_tracks_with_complete_promoted_classifier_scores(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    complete_id = _add_track(db, tmp_path, "complete.wav", "Artist", "Complete", {})
    partial_id = _add_track(db, tmp_path, "partial.wav", "Artist", "Partial", {})
    unrelated_id = _add_track(db, tmp_path, "unrelated.wav", "Artist", "Unrelated", {})
    for track_id, classifier in [
        (complete_id, "break_energy"),
        (complete_id, "live_instrumentation"),
        (partial_id, "break_energy"),
        (unrelated_id, "unused_classifier"),
    ]:
        db.save_classifier_score(
            track_id,
            classifier=classifier,
            score=0.92,
            label="positive",
            confidence=0.92,
            probabilities={"positive": 0.92, "negative": 0.08},
            feature_set="combined",
            model_id=f"{classifier}-test",
        )
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [
            {"classifier_key": "break_energy"},
            {"classifier_key": "live_instrumentation"},
        ],
    )

    response = TestClient(create_app(db_path)).get("/api/library/summary")

    assert response.status_code == 200
    assert response.json()["classifiers"] == 1


def test_media_endpoint_transcodes_aiff_preview_to_browser_playable_wav(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "preview.aiff", "Artist", "Preview", {})
    source_path = tmp_path / "preview.aiff"
    source_bytes = source_path.read_bytes()
    calls: list[list[str]] = []

    def fail_streaming_process(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("AIFF preview should not use streaming ffmpeg stdout")

    def fake_run(command: list[str], *, stderr: int, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "Popen", fail_streaming_process)
    monkeypatch.setattr(media_preview_module.subprocess, "run", fake_run)

    response = TestClient(create_app(db_path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-length"] == str(len(b"RIFFbrowser-compatible-wav"))
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert source_path.read_bytes() == source_bytes
    assert Path(calls[0][-1]) != source_path
    assert not Path(calls[0][-1]).exists()
    assert calls == [[
        "ffmpeg-test",
        "-i",
        str(tmp_path / "preview.aiff"),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "wav",
        "-c:a",
        "pcm_s16le",
        "-y",
        calls[0][-1],
    ]]


def test_media_endpoint_reports_missing_audio_file_without_traceback(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    missing_path = tmp_path / "missing.wav"
    track_id = db.upsert_track(path=missing_path, size=1, mtime=1, metadata={"title": "Missing"})

    response = TestClient(create_app(db_path), raise_server_exceptions=False).get(f"/media/{track_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Audio file is missing"}
    assert "Traceback" not in response.text


def test_media_endpoint_transcodes_flac_preview_to_browser_playable_wav(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "preview.flac", "Artist", "Preview", {})
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, stderr: int, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fake_run)

    response = TestClient(create_app(db_path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-length"] == str(len(b"RIFFbrowser-compatible-wav"))
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert calls == [[
        "ffmpeg-test",
        "-i",
        str(tmp_path / "preview.flac"),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "wav",
        "-c:a",
        "pcm_s16le",
        "-y",
        calls[0][-1],
    ]]


def test_media_endpoint_transcodes_dsf_preview_to_browser_playable_wav(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "preview.dsf", "Artist", "Preview", {})
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, stderr: int, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fake_run)

    response = TestClient(create_app(db_path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-length"] == str(len(b"RIFFbrowser-compatible-wav"))
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert calls == [[
        "ffmpeg-test",
        "-i",
        str(tmp_path / "preview.dsf"),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "wav",
        "-c:a",
        "pcm_s16le",
        "-y",
        calls[0][-1],
    ]]


def test_media_endpoint_transcodes_24_bit_wav_preview_to_browser_playable_wav(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    path = tmp_path / "preview-24.wav"
    _write_wav(path, sample_width=3)
    track_id = db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={"title": "Preview 24"})
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, stderr: int, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fake_run)

    response = TestClient(create_app(db_path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["content-length"] == str(len(b"RIFFbrowser-compatible-wav"))
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert calls == [[
        "ffmpeg-test",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "wav",
        "-c:a",
        "pcm_s16le",
        "-y",
        calls[0][-1],
    ]]


def test_media_endpoint_reports_preview_transcode_failure_without_traceback(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "broken.aiff", "Artist", "Broken", {})

    def fail_run(command: list[str], *, stderr: int, check: bool) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(3199971767, command, stderr=b"Invalid data found when processing input")

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fail_run)

    response = TestClient(create_app(db_path), raise_server_exceptions=False).get(f"/media/{track_id}")

    assert response.status_code == 422
    assert "Audio preview failed" in response.json()["detail"]
    assert "Invalid data found when processing input" in response.json()["detail"]
    assert "Traceback" not in response.text


def _add_track(
    db: LibraryDatabase,
    tmp_path: Path,
    filename: str,
    artist: str,
    title: str,
    metadata: dict[str, object],
) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(
        path=path,
        size=path.stat().st_size,
        mtime=1,
        metadata={"artist": artist, "title": title, **metadata},
    )


def _write_wav(path: Path, *, sample_width: int) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(sample_width)
        audio.setframerate(44100)
        audio.writeframes(b"\x00" * sample_width * 2 * 128)

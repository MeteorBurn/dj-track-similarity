from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from api_test_support import create_api_client
from dj_track_similarity.api import routes_prompt_decisions


def test_prompt_decisions_round_trip_through_the_app_wide_json_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # The folder does not exist yet: the first save creates it.
    decisions_path = tmp_path / "database" / "prompt_decisions.json"
    monkeypatch.setattr(routes_prompt_decisions, "PROMPT_DECISIONS_PATH", decisions_path)
    client = create_api_client(monkeypatch, tmp_path / "library.sqlite")

    empty = client.get("/api/search/text/decisions")
    saved = client.put("/api/search/text/decisions/rhythm/breakbeat", json={"model": "mulan"})
    listed = client.get("/api/search/text/decisions")
    bad_model = client.put("/api/search/text/decisions/rhythm/breakbeat", json={"model": "maest"})
    bad_field = client.put(
        "/api/search/text/decisions/rhythm/breakbeat",
        json={"model": "clap", "note": "free text"},
    )
    bad_key = client.put("/api/search/text/decisions/Rhythm Break", json={"model": "clap"})
    stored = json.loads(decisions_path.read_text(encoding="utf-8"))

    assert empty.status_code == 200
    assert empty.json() == {"decisions": {}}
    assert saved.status_code == 200
    entry = saved.json()
    assert set(entry) == {"model", "updated_at"}
    assert entry["model"] == "mulan"
    assert datetime.fromisoformat(entry["updated_at"]).utcoffset() == timedelta(0)
    assert listed.json() == {"decisions": {"rhythm/breakbeat": entry}}
    # The rejected requests left the saved decision untouched.
    assert stored == {"decisions": {"rhythm/breakbeat": entry}}
    assert [bad_model.status_code, bad_field.status_code, bad_key.status_code] == [422, 422, 422]

    removed = client.delete("/api/search/text/decisions/rhythm/breakbeat")
    removed_again = client.delete("/api/search/text/decisions/rhythm/breakbeat")

    assert [removed.status_code, removed_again.status_code] == [204, 204]
    assert json.loads(decisions_path.read_text(encoding="utf-8")) == {"decisions": {}}

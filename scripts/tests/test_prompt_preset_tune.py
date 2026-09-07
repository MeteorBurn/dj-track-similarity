from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    EmbeddingFamilySpec,
)
from dj_track_similarity.search import engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prompt_preset_tune as tuner


def test_dev_selection_is_frozen_before_test_and_manifest_is_deterministic(monkeypatch):
    monkeypatch.setattr(
        engine, "current_embedding_spec", lambda _family: EmbeddingFamilySpec(2, "l2")
    )
    output = AnalysisOutput("clap", "embedding")
    rows, judgements = [], []
    for index in range(24):
        uuid = f"track-{index:03}"
        vector = np.array([1.0, 0.0] if index % 2 else [0.0, 1.0], dtype=np.float32)
        rows.append(
            AnalysisVectorRow(
                AnalysisTarget("catalog", index + 1, uuid), output, vector
            )
        )
        judgements.append(
            {
                "intent_key": "axis/intent",
                "track_uuid": uuid,
                "judgement_scope": "label",
                "verdict": 1 if index % 2 else -1,
                "group_id": uuid,
                "split": "dev" if index < 12 else "test",
                "manifest_id": "explicit-v1",
            }
        )
    identity = {"model": "synthetic-2d"}
    dataset = {
        "catalog_uuid": "catalog",
        "manifest_id": "explicit-v1",
        "output_identities": {"clap": identity},
        "judgements": judgements,
    }
    snapshot = {"catalog_uuid": "catalog", "rows": rows, "excluded_count": 2}
    presets = {
        "axis/intent": {
            "positive": {"shared": ["axis-x"]},
            "negative": {"shared": ["axis-y"]},
            "negativeWeight": 0.73,
            "productionBanks": {
                "clap": {
                    "positive_queries": ["axis-x"],
                    "negative_queries": ["axis-y"],
                    "negative_weight": 0.73,
                }
            },
        }
    }

    def embed(texts):
        return [
            np.array([1, 0] if text == "axis-x" else [0, 1], dtype=np.float32)
            for text in texts
        ]

    def run(data):
        return tuner.evaluate_family(
            snapshot=snapshot,
            family="clap",
            identity=identity,
            dataset=data,
            presets=presets,
            embed_texts=embed,
            candidates=[
                {
                    "name": "opposite-ranking",
                    "intent_key": "axis/intent",
                    "positive_queries": ["axis-y"],
                    "negative_queries": [],
                }
            ],
        )

    result = run(dataset)
    changed = deepcopy(dataset)
    for item in changed["judgements"]:
        if item["split"] == "test":
            item["verdict"] *= -1
    other = run(changed)
    selected = result["intents"][0]
    assert selected["production_baseline"]["negative_weight"] == 0.73
    candidate = next(
        item for item in selected["grid"] if item["variant"] == "opposite-ranking"
    )
    assert (
        selected["selected_dev_candidate"]["dev"]["judged_pool_average_precision"]
        > candidate["dev"]["judged_pool_average_precision"]
    )
    assert (
        selected["selected_dev_candidate"]["dev"]["judged_pool_average_precision"]
        > other["intents"][0]["selected_dev_candidate"]["test"][
            "judged_pool_average_precision"
        ]
    )
    assert (
        selected["selected_dev_candidate"]["bank_hash"]
        == other["intents"][0]["selected_dev_candidate"]["bank_hash"]
    )
    assert (
        selected["selected_dev_candidate"]["dev"]
        == other["intents"][0]["selected_dev_candidate"]["dev"]
    )
    assert (
        selected["selected_dev_candidate"]["test"]
        != other["intents"][0]["selected_dev_candidate"]["test"]
    )
    assert selected["test_evaluations_per_selected_candidate"] == 1
    assert result["manifest"] == run(dataset)["manifest"]
    assert result["manifest"]["eligible_track_uuids"] == sorted(
        row.target.track_uuid for row in rows
    )
    assert not result["promoted"]
    presets["axis/intent"]["productionBanks"]["clap"] = {
        "positive_queries": ["axis-x"],
        "negative_queries": [],
        "negative_weight": 0.0,
    }
    zero_baseline = run(dataset)["intents"][0]["production_baseline"]
    assert zero_baseline["negative_queries"] == []
    assert zero_baseline["negative_weight"] == 0.0
    leaking = deepcopy(dataset)
    leaking["judgements"][-1]["group_id"] = leaking["judgements"][0]["group_id"]
    with pytest.raises(ValueError, match="leak"):
        run(leaking)
    excluded = deepcopy(dataset)
    excluded["judgements"][0]["judgement_scope"] = "query"
    excluded["judgements"][1]["intent_key"] = "unknown"
    excluded["judgements"][2]["track_uuid"] = "stale"
    excluded["judgements"][3]["verdict"] = 0
    reasons = run(excluded)["excluded"]
    assert (
        reasons["not_explicit_label_judgement"]
        == reasons["unknown_intent_key"]
        == reasons["ineligible_or_missing_embedding"]
        == reasons["unjudged"]
        == 1
    )


def test_cli_without_independent_labels_does_not_touch_library_or_load_models(
    tmp_path, monkeypatch, capsys
):
    import json

    library = tmp_path / "named.sqlite"
    library.write_bytes(b"untouched user state")
    before = library.read_bytes()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("No model or library query is needed without qrels")

    monkeypatch.setattr(tuner, "load_presets", forbidden)
    assert tuner.main(["--db", str(library)]) == 0
    assert (
        json.loads(capsys.readouterr().out)["status"] == "insufficient_eligible_labels"
    )
    assert library.read_bytes() == before
    missing = tmp_path / "does-not-exist.sqlite"
    with pytest.raises(FileNotFoundError):
        tuner.main(["--db", str(missing)])
    assert not missing.exists()

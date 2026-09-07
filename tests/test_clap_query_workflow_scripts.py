from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAP_SKILL = ROOT / ".djts" / "skills" / "clap-query-workflow" / "SKILL.md"
CURATOR_SKILL = ROOT / ".djts" / "skills" / "prompt-bank-curator" / "SKILL.md"
SCORE_PROMPT_BANK = ROOT / ".djts" / "skills" / "clap-query-workflow" / "scripts" / "score_prompt_bank.py"
PROJECT_SEARCH = ROOT / ".djts" / "skills" / "clap-query-workflow" / "scripts" / "project_text_search.py"


def load_score_prompt_bank_module():
    spec = importlib.util.spec_from_file_location("score_prompt_bank_for_test", SCORE_PROMPT_BANK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checkpoint_loading_forces_weights_only(tmp_path: Path) -> None:
    module = load_score_prompt_bank_module()
    calls = []

    class FakeTorch:
        def __init__(self) -> None:
            self.load = self.original_load

        def original_load(self, *args, **kwargs):
            calls.append((args, kwargs.copy()))
            return {"state_dict": {}}

    fake_torch = FakeTorch()

    class FakeModel:
        def load_ckpt(self, checkpoint_path: str, verbose: bool = False) -> None:
            fake_torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    original_load = fake_torch.load
    module.load_checkpoint_weights_only(FakeModel(), fake_torch, tmp_path / "model.pt")

    assert calls
    assert calls[0][1]["weights_only"] is True
    assert fake_torch.load is original_load


def test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(tmp_path: Path) -> None:
    module = load_score_prompt_bank_module()

    class FakeTorch:
        def __init__(self) -> None:
            self.load = self.original_load

        def original_load(self, *args, **kwargs):
            if "weights_only" in kwargs:
                raise TypeError("load() got an unexpected keyword argument 'weights_only'")
            return {"state_dict": {}}

    fake_torch = FakeTorch()

    class FakeModel:
        def load_ckpt(self, checkpoint_path: str, verbose: bool = False) -> None:
            fake_torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    original_load = fake_torch.load
    with pytest.raises(SystemExit, match="Safe checkpoint loading requires"):
        module.load_checkpoint_weights_only(FakeModel(), fake_torch, tmp_path / "model.pt")

    assert fake_torch.load is original_load


@pytest.mark.parametrize("family", ["clap", "mulan"])
def test_project_search_script_targets_both_text_models(monkeypatch, capsys, family):
    import json
    import sys
    spec = importlib.util.spec_from_file_location("project_search_test", PROJECT_SEARCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    results = [{"track": {"track_id": 1, "title": "Synthetic"}, "score": 0.5}]
    def post(url, payload, timeout):
        calls.append((url, payload))
        return {"results": results, "execution": {"run_id": "issued"}}
    monkeypatch.setattr(module, "post_json", post)
    monkeypatch.setattr(sys, "argv", [str(PROJECT_SEARCH), "--model", family, "--query", "test query", "--negative-weight", "0.75", "--no-db-check", "--json"])
    assert module.main() == 0
    assert calls[0][0].endswith("/api/search/text")
    assert calls[0][1]["analysis_family"] == family
    assert calls[0][1]["negative_weight"] == 0.75
    assert json.loads(capsys.readouterr().out) == results

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAP_SKILL = ROOT / ".agents" / "skills" / "clap-query-workflow" / "SKILL.md"
SCORE_PROMPT_BANK = ROOT / ".agents" / "skills" / "clap-query-workflow" / "scripts" / "score_prompt_bank.py"


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


def test_clap_text_score_language_remains_ranking_signal_not_probability() -> None:
    skill_text = CLAP_SKILL.read_text(encoding="utf-8")
    readme_text = README.read_text(encoding="utf-8")

    assert "CLAP text-search scores are text-to-audio cosine or contrast scores, not probabilities" in skill_text
    assert "Current scoring: normalized positive text embeddings are mean-pooled" in skill_text
    assert "hard negatives are subtracted with `alpha = 0.35`" in skill_text
    assert "CLAP text-search scores are not the same scale as seed-based audio-to-audio scores" in readme_text
    assert "Treat them as prompt evidence, not as a universal similarity value" in readme_text

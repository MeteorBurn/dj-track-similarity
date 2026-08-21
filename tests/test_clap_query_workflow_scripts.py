from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAP_SKILL = ROOT / ".agents" / "skills" / "clap-query-workflow" / "SKILL.md"
CURATOR_SKILL = ROOT / ".agents" / "skills" / "prompt-bank-curator" / "SKILL.md"
SCORE_PROMPT_BANK = ROOT / ".agents" / "skills" / "clap-query-workflow" / "scripts" / "score_prompt_bank.py"
PROJECT_SEARCH = ROOT / ".agents" / "skills" / "clap-query-workflow" / "scripts" / "project_text_search.py"


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


def test_text_score_language_remains_ranking_signal_not_probability() -> None:
    skill_text = CLAP_SKILL.read_text(encoding="utf-8")
    readme_text = README.read_text(encoding="utf-8")

    assert "Text-search scores are text-to-audio cosine or contrast scores, not probabilities" in skill_text
    assert "Current scoring: normalized positive text embeddings are mean-pooled" in skill_text
    assert "hard negatives are subtracted with the preset's `negative_weight`" in skill_text
    assert "CLAP text-search scores are not the same scale as seed-based audio-to-audio scores" in readme_text
    assert "Treat them as prompt evidence, not as a universal similarity value" in readme_text


def collapsed(text: str) -> str:
    """Compare wording, not line wrapping."""

    return " ".join(text.split())


def test_text_search_skills_declare_their_model_layer_boundary() -> None:
    skills = (
        CLAP_SKILL.read_text(encoding="utf-8"),
        CURATOR_SKILL.read_text(encoding="utf-8"),
    )

    for text in skills:
        prose = collapsed(text)
        assert "## Layer Boundary" in prose
        assert "CLAP and MuQ-MuLan" in prose
        assert "SONARA, MERT, MAEST" in prose
        assert "never change how they are produced" in prose


def test_project_search_script_targets_both_text_models() -> None:
    source = PROJECT_SEARCH.read_text(encoding="utf-8")

    assert '"--model"' in source
    assert 'TEXT_MODELS = ("clap", "mulan")' in source
    assert "choices=TEXT_MODELS" in source
    assert '"analysis_family": args.model' in source
    assert '"--negative-weight"' in source
    assert '"negative_weight"' in source
    assert '"--preset"' not in source

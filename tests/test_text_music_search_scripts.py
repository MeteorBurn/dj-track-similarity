from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".djts"
    / "skills"
    / "text-music-search"
    / "scripts"
)


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        f"{name}_for_test", SCRIPTS / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(module, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [module.__file__, *map(str, args)])
    return module.main()


def envelope(family="clap", catalog="synthetic-catalog"):
    return {
        "results": [{"track": {"track_id": 1, "title": "Synthetic"}, "score": 0.5}],
        "execution": {
            "run_id": "synthetic-run",
            "query_key": "synthetic-query",
            "query_context": {"analysis_family": family, "catalog_uuid": catalog},
            "feedback": {
                "requested": True,
                "applied": False,
                "reason": "insufficient_history",
            },
            "feedback_capability": "ready",
        },
    }


def valid_bank():
    return {
        "labels": {
            "pulse": {"prompts": ["steady pulse"], "hard_negatives": ["ambient drone"]}
        },
        "global_hard_negatives": ["spoken narration"],
    }


def test_checkpoint_loading_forces_weights_only_and_restores_binding(tmp_path):
    module = load_script("score_prompt_bank")
    for failure in (
        None,
        TypeError("unsupported 'weights_only'"),
        RuntimeError("bad checkpoint"),
    ):
        calls = []

        def original_load(*args, **kwargs):
            calls.append(kwargs)
            if failure is not None:
                raise failure
            return {"state_dict": {}}

        torch = SimpleNamespace(load=original_load)
        model = SimpleNamespace(
            load_ckpt=lambda path, verbose: torch.load(path, weights_only=False)
        )
        if failure is None:
            module.load_checkpoint_weights_only(model, torch, tmp_path / "model.pt")
        else:
            expected = SystemExit if isinstance(failure, TypeError) else RuntimeError
            with pytest.raises(expected):
                module.load_checkpoint_weights_only(model, torch, tmp_path / "model.pt")
        assert calls == [{"weights_only": True}]
        assert torch.load is original_load


def test_project_search_preserves_manual_banks_and_execution_for_both_models(
    monkeypatch, capsys, tmp_path
):
    module = load_script("project_text_search")
    positive_file = tmp_path / "positive.txt"
    positive_file.write_text("file positive\n", encoding="utf-8")
    negative_file = tmp_path / "negative.txt"
    negative_file.write_text("file negative\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "get_json",
        lambda *a, **kw: pytest.fail("explicit bypass must skip GET"),
    )
    for family in ("clap", "mulan"):
        response = envelope(family)
        calls = []

        def post(url, payload, timeout):
            calls.append((url, payload))
            return response

        monkeypatch.setattr(module, "post_json", post)
        args = [
            "--model",
            family,
            "--query",
            "first\nsecond",
            "--positive",
            "third\nfourth",
            "--positive-file",
            positive_file,
            "--negative",
            "negative one\nnegative two",
            "--negative-file",
            negative_file,
            "--negative-weight",
            "0.75",
            "--no-db-check",
        ]
        assert invoke(module, monkeypatch, *args, "--json") == 0
        assert json.loads(capsys.readouterr().out) == response
        url, payload = calls[-1]
        assert url.endswith("/api/search/text")
        assert payload["analysis_family"] == family
        assert payload["positive_queries"] == [
            "first",
            "second",
            "third",
            "fourth",
            "file positive",
        ]
        assert payload["negative_queries"] == [
            "negative one",
            "negative two",
            "file negative",
        ]
        assert payload["negative_weight"] == 0.75
        assert invoke(module, monkeypatch, *args, "--no-negatives") == 0
        output = capsys.readouterr().out
        for value in (
            "synthetic-run",
            "synthetic-query",
            family,
            "insufficient_history",
        ):
            assert value in output
        assert calls[-1][1]["negative_queries"] == []


def test_project_search_requires_expected_database_and_rejects_catalog_switch(
    monkeypatch, capsys, tmp_path
):
    module = load_script("project_text_search")
    for name in module.DB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    gets, posts = [], []
    current = {
        "selected": True,
        "path": str(tmp_path / "expected.sqlite"),
        "catalog_uuid": "synthetic-catalog",
    }
    response = envelope()

    def get(url, timeout):
        gets.append(url)
        return current

    def post(url, payload, timeout):
        posts.append(url)
        return response

    monkeypatch.setattr(module, "get_json", get)
    monkeypatch.setattr(module, "post_json", post)
    base = ["--query", "pulse", "--model", "clap", "--json"]
    for extra in (
        [],
        ["--expected-db", tmp_path / "missing.sqlite"],
        ["--expected-db", tmp_path],
    ):
        with pytest.raises(SystemExit):
            invoke(module, monkeypatch, *base, *extra)
        assert gets == posts == []
    expected = tmp_path / "expected.sqlite"
    expected.write_bytes(b"synthetic database path fixture")
    good = current.copy()
    for invalid in (
        None,
        {},
        {**good, "selected": False},
        {**good, "path": str(tmp_path / "other.sqlite")},
        {**good, "catalog_uuid": ""},
    ):
        current = invalid
        with pytest.raises(SystemExit):
            invoke(module, monkeypatch, *base, "--expected-db", expected)
        assert posts == []
    current = good
    assert invoke(module, monkeypatch, *base, "--expected-db", expected) == 0
    assert json.loads(capsys.readouterr().out) == response
    for name in module.DB_ENV_VARS:
        monkeypatch.setenv(name, str(expected))
        assert invoke(module, monkeypatch, *base) == 0
        capsys.readouterr()
        monkeypatch.delenv(name)
    response = envelope(catalog="replaced-catalog")
    with pytest.raises(SystemExit):
        invoke(module, monkeypatch, *base, "--expected-db", expected)
    assert capsys.readouterr().out == ""


def test_validator_accepts_format_and_rejects_invalid_banks_without_model_loading(
    monkeypatch, capsys, tmp_path
):
    module = load_script("validate_prompt_bank")
    bank_file = tmp_path / "bank.json"
    malformed = [
        None,
        [],
        {},
        {"labels": {}},
        {"labels": {"x": []}},
        {"labels": {"x": {"prompts": []}}},
        {"labels": {"x": {"prompts": [1]}}},
        {"labels": {"x": {"prompts": [" "]}}},
    ]
    for negatives in (None, 0, "", {}, [""], [1]):
        bank = valid_bank()
        bank["global_hard_negatives"] = negatives
        malformed.append(bank)
        bank = valid_bank()
        bank["labels"]["pulse"]["hard_negatives"] = negatives
        malformed.append(bank)
    for bank in malformed:
        bank_file.write_text(json.dumps(bank), encoding="utf-8")
        assert invoke(module, monkeypatch, bank_file) == 1, bank
        capsys.readouterr()
    bank = valid_bank()
    bank["labels"]["pulse"]["prompts"].append("pulse " * 100)
    bank_file.write_text(json.dumps(bank), encoding="utf-8")
    for model in (None, "clap", "mulan"):
        extra = [] if model is None else ["--model", model]
        assert invoke(module, monkeypatch, bank_file, *extra) == 0
        capsys.readouterr()


def test_scorer_preflight_blocks_invalid_inputs_and_output_aliases_before_dependencies(
    monkeypatch, tmp_path
):
    module = load_script("score_prompt_bank")
    monkeypatch.setattr(
        module,
        "require_dependencies",
        lambda: pytest.fail("invalid inputs loaded dependencies"),
    )
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps(valid_bank()), encoding="utf-8")
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    base = ["--prompt-bank", bank, "--ckpt", checkpoint, "--audio", audio]
    for option in ("--window-seconds", "--hop-seconds", "--alpha"):
        invalid = ["-1", "nan", "inf"] + (
            [] if option == "--alpha" else ["0", "0.000000001"]
        )
        for value in invalid:
            with pytest.raises(SystemExit):
                invoke(module, monkeypatch, *base, option, value)
    for option in ("--prompt-bank", "--ckpt", "--audio"):
        for value in (tmp_path / "missing", tmp_path):
            with pytest.raises(SystemExit):
                invoke(module, monkeypatch, *base, option, value)
    for invalid in (
        [],
        {"labels": {}},
        {"labels": {"x": {"prompts": ["x"]}}, "global_hard_negatives": [0]},
    ):
        bank.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(SystemExit):
            invoke(module, monkeypatch, *base)
    bank.write_text(json.dumps(valid_bank()), encoding="utf-8")
    originals = {path: path.read_bytes() for path in (bank, checkpoint, audio)}
    for index, path in enumerate(originals):
        alias = tmp_path / f"alias-{index}"
        os.link(path, alias)
        symlink = tmp_path / f"symlink-{index}"
        symlink.symlink_to(path)
        for out in (path, alias, symlink):
            with pytest.raises(SystemExit):
                invoke(module, monkeypatch, *base, "--out", out)
    assert {path: path.read_bytes() for path in originals} == originals


def test_scorer_synthetic_cli_preserves_windows_negative_max_and_output(
    monkeypatch, capsys, tmp_path
):
    module = load_script("score_prompt_bank")
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps(valid_bank()), encoding="utf-8")
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"synthetic checkpoint")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    out = tmp_path / "scores.json"
    windows_seen = []
    torch = SimpleNamespace(
        load=lambda *a, **kw: {}, cuda=SimpleNamespace(is_available=lambda: False)
    )

    class Model:
        def __init__(self, **kwargs):
            pass

        def load_ckpt(self, path, verbose):
            torch.load(path)

        def get_text_embedding(self, prompts, use_tensor):
            vectors = {
                "steady pulse": [1, 0],
                "ambient drone": [0, 1],
                "spoken narration": [-1, 0],
            }
            return np.array([vectors[prompt] for prompt in prompts])

        def get_audio_embedding_from_data(self, windows, use_tensor):
            windows_seen.append(windows.copy())
            return np.array([[1, 0], [0, 1], [1, 0]])

    samples = np.arange(11, dtype=np.float32)
    librosa = SimpleNamespace(load=lambda *a, **kw: (samples, kw["sr"]))
    monkeypatch.setattr(
        module,
        "require_dependencies",
        lambda: (np, librosa, SimpleNamespace(CLAP_Module=Model), torch),
    )
    args = [
        "--prompt-bank",
        bank,
        "--ckpt",
        checkpoint,
        "--audio",
        audio,
        "--alpha",
        "0.5",
        "--window-seconds",
        str(6 / 48000),
        "--hop-seconds",
        str(3 / 48000),
    ]
    assert invoke(module, monkeypatch, *args, "--out", out) == 0
    capsys.readouterr()
    report = json.loads(out.read_text(encoding="utf-8"))
    np.testing.assert_array_equal(
        windows_seen[0], np.array([samples[:6], samples[3:9], samples[5:11]])
    )
    result = report["results"][0]
    assert result["num_windows"] == 3
    assert result["labels"]["pulse"]["negative"]["mean"] == pytest.approx(1 / 3)
    assert result["labels"]["pulse"]["final"]["mean"] == pytest.approx(0.5)
    assert result["ranking"][0]["final_top20_mean"] == pytest.approx(1)
    assert report["checkpoint"] == str(checkpoint) and report["prompt_bank"] == str(
        bank
    )
    assert report["alpha"] == 0.5
    assert invoke(module, monkeypatch, *args) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert invoke(module, monkeypatch, *args, "--alpha", "0") == 0
    positive_only = json.loads(capsys.readouterr().out)["results"][0]["labels"]["pulse"]
    assert "negative" not in positive_only
    assert positive_only["final"]["mean"] == pytest.approx(2 / 3)

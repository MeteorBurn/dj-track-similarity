#!/usr/bin/env python3
"""Validate a text-music prompt bank JSON file without loading a model.

Run this script with the project's root .venv interpreter and an existing bank.
Structure and non-empty strings are requirements. Prompt length, balance and
optional CLAP / MuQ-MuLan style advice are heuristics, not tokenizer validation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

NEGATION_RE = re.compile(r"\b(no|not|without|never|non-)\b", re.IGNORECASE)
TOKENISH_RE = re.compile(r"[\w'-]+|[^\w\s]")
MODEL_ADVICE = {
    "clap": "CLAP: use affirmative, concise descriptions of audible track attributes.",
    "mulan": "MuQ-MuLan: mix short music labels, focused keywords and natural music descriptions.",
}


def tokenish_count(text: str) -> int:
    return len(TOKENISH_RE.findall(text))


def warn(message: str) -> None:
    print(f"WARN: {message}")


def fail(message: str) -> None:
    print(f"ERROR: {message}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: failed to read JSON from {path}: {exc}") from exc


def validate_prompt_list(
    values: Any, context: str, *, required: bool, advisory: bool
) -> int:
    """Validate every positive or negative line with the same string contract."""

    if not isinstance(values, list) or (required and not values):
        fail(f"{context} must be {'a non-empty list' if required else 'a list'}")
        return 1
    errors = 0
    seen: set[str] = set()
    for index, prompt in enumerate(values, start=1):
        if not isinstance(prompt, str) or not prompt.strip():
            fail(f"{context} #{index} must be a non-empty string")
            errors += 1
            continue
        if not advisory:
            continue
        normalized = prompt.strip().casefold()
        if normalized in seen:
            warn(f"{context} has duplicate-like prompt: {prompt!r}")
        seen.add(normalized)
        count = tokenish_count(prompt)
        if count > 50:
            warn(
                f"{context} #{index} is long ({count} approximate units). "
                "This is not a tokenizer count; check the selected model's tokenizer before truncating."
            )
        if NEGATION_RE.search(prompt):
            warn(
                f"{context} #{index} uses negation; describe the audible target "
                "or the competing class affirmatively."
            )
    return errors


def validate_bank(bank: Any, model: str | None = None, *, advisory: bool = True) -> int:
    """Return the number of format errors; optional style advice never rejects a bank."""

    if not isinstance(bank, dict):
        fail("bank JSON root must be an object")
        return 1

    labels = bank.get("labels")
    if not isinstance(labels, dict) or not labels:
        fail("bank must contain a non-empty object at key 'labels'")
        return 1

    errors = 0
    prompt_counts: list[int] = []
    if advisory and model is not None:
        if model not in MODEL_ADVICE:
            raise ValueError(f"Unsupported text model: {model}")
        warn(MODEL_ADVICE[model] + " Keep each label on one semantic axis and evaluate on the intended library.")

    for label, spec in labels.items():
        if not isinstance(label, str) or not label.strip():
            fail("label names must be non-empty strings")
            errors += 1
        if not isinstance(spec, dict):
            fail(f"label {label!r} must map to an object")
            errors += 1
            continue

        prompts = spec.get("prompts")
        errors += validate_prompt_list(prompts, f"label {label!r} prompts", required=True, advisory=advisory)
        if isinstance(prompts, list) and prompts:
            prompt_counts.append(len(prompts))
            if advisory and model is not None and len(prompts) != 6:
                warn(
                    f"label {label!r} has {len(prompts)} prompts. Project presets use six per model "
                    "(two short labels, two keyword lists, two descriptions); experiments may use other counts."
                )
        errors += validate_prompt_list(
            spec.get("hard_negatives", []), f"label {label!r} hard_negatives", required=False, advisory=advisory
        )

    if advisory and len(set(prompt_counts)) > 1:
        warn(f"label prompt counts differ: {prompt_counts}. Comparable classes should usually be balanced.")

    errors += validate_prompt_list(
        bank.get("global_hard_negatives", []), "global_hard_negatives", required=False, advisory=advisory
    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a text-music prompt bank without loading models.")
    parser.add_argument("prompt_bank", type=Path, help="Existing UTF-8 JSON with labels/prompts and optional hard negatives.")
    parser.add_argument("--model", choices=tuple(MODEL_ADVICE), default=None, help="Add advisory CLAP or MuQ-MuLan prompt-style guidance.")
    args = parser.parse_args()

    bank = load_json(args.prompt_bank)
    errors = validate_bank(bank, model=args.model)

    if errors:
        print(f"\nValidation failed with {errors} error(s).")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

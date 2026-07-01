#!/usr/bin/env python3
"""Validate a CLAP prompt bank JSON file.

Usage:
    python scripts/validate_prompt_bank.py assets/prompt_bank.starter.json

The validator intentionally avoids model dependencies. It checks structure,
rough prompt length, label balance, and common CLAP prompt anti-patterns.
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


def tokenish_count(text: str) -> int:
    return len(TOKENISH_RE.findall(text))


def warn(message: str) -> None:
    print(f"WARN: {message}")


def fail(message: str) -> None:
    print(f"ERROR: {message}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"ERROR: failed to read JSON: {exc}") from exc


def validate_bank(bank: dict[str, Any]) -> int:
    errors = 0

    labels = bank.get("labels")
    if not isinstance(labels, dict) or not labels:
        fail("bank must contain a non-empty object at key 'labels'")
        return 1

    prompt_counts: list[int] = []

    for label, spec in labels.items():
        if not isinstance(spec, dict):
            fail(f"label {label!r} must map to an object")
            errors += 1
            continue

        prompts = spec.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            fail(f"label {label!r} must contain non-empty list 'prompts'")
            errors += 1
            continue

        prompt_counts.append(len(prompts))

        seen: set[str] = set()
        for i, prompt in enumerate(prompts):
            if not isinstance(prompt, str) or not prompt.strip():
                fail(f"label {label!r} prompt #{i + 1} must be a non-empty string")
                errors += 1
                continue

            normalized = prompt.strip().lower()
            if normalized in seen:
                warn(f"label {label!r} has duplicate-like prompt: {prompt!r}")
            seen.add(normalized)

            n = tokenish_count(prompt)
            if n > 77:
                fail(f"label {label!r} prompt #{i + 1} exceeds 77 token-ish units ({n}): {prompt!r}")
                errors += 1
            elif n > 50:
                warn(f"label {label!r} prompt #{i + 1} is long ({n} token-ish units): {prompt!r}")

            if NEGATION_RE.search(prompt):
                warn(
                    f"label {label!r} prompt #{i + 1} uses negation; prefer positive wording plus hard negatives: {prompt!r}"
                )

        hard_negatives = spec.get("hard_negatives", [])
        if hard_negatives is not None and not isinstance(hard_negatives, list):
            fail(f"label {label!r} hard_negatives must be a list when present")
            errors += 1
        elif isinstance(hard_negatives, list):
            for j, neg in enumerate(hard_negatives):
                if not isinstance(neg, str) or not neg.strip():
                    fail(f"label {label!r} hard_negative #{j + 1} must be a non-empty string")
                    errors += 1

    if prompt_counts and len(set(prompt_counts)) > 1:
        warn(f"label prompt counts differ: {prompt_counts}. Comparable classes should usually be balanced.")

    global_hard_negatives = bank.get("global_hard_negatives", [])
    if global_hard_negatives and not isinstance(global_hard_negatives, list):
        fail("global_hard_negatives must be a list when present")
        errors += 1

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt_bank", type=Path)
    args = parser.parse_args()

    bank = load_json(args.prompt_bank)
    errors = validate_bank(bank)

    if errors:
        print(f"\nValidation failed with {errors} error(s).")
        return 1

    print("Validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

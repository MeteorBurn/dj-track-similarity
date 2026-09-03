#!/usr/bin/env python3
"""Score audio files against a CLAP prompt bank.

This script is designed for LAION-CLAP music workflows. It uses deterministic
10-second windows instead of relying on file-level random truncation for long
tracks when enable_fusion=False.

Example:
    python scripts/score_prompt_bank.py \
        --prompt-bank assets/prompt_bank.starter.json \
        --ckpt <path-to-laion-clap-music-checkpoint.pt> \
        --audio track1.wav track2.mp3 \
        --alpha 0.35 \
        --out scores.json

Dependencies:
    pip install laion-clap librosa torch numpy
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

np: Any = None


def require_dependencies():
    try:
        import numpy as _np  # type: ignore
        import librosa  # type: ignore
        import laion_clap  # type: ignore
        import torch  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "Missing dependency. Install with: pip install laion-clap librosa torch numpy\n"
            f"Original import error: {exc}"
        ) from exc
    return _np, librosa, laion_clap, torch


def load_checkpoint_weights_only(model: Any, torch: Any, ckpt_path: Path) -> None:
    """Load a LAION-CLAP checkpoint without allowing arbitrary pickle objects."""
    original_torch_load = torch.load

    def torch_load_weights_only(*args: Any, **kwargs: Any) -> Any:
        kwargs["weights_only"] = True
        return original_torch_load(*args, **kwargs)

    torch.load = torch_load_weights_only
    try:
        model.load_ckpt(str(ckpt_path), verbose=False)
    except TypeError as exc:
        if "weights_only" in str(exc):
            raise SystemExit(
                "Safe checkpoint loading requires a PyTorch version whose torch.load supports weights_only=True."
            ) from exc
        raise
    finally:
        torch.load = original_torch_load


def l2norm(x: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    denom = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.maximum(denom, eps)


def load_prompt_bank(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def embed_prompt_ensemble(model: Any, prompts: list[str]) -> np.ndarray:
    emb = model.get_text_embedding(prompts, use_tensor=False)
    emb = l2norm(np.asarray(emb, dtype=np.float32), axis=-1)
    vec = l2norm(emb.mean(axis=0, keepdims=True), axis=-1)[0]
    return vec.astype(np.float32)


def build_label_bank(model: Any, bank: dict[str, Any]) -> tuple[list[str], np.ndarray]:
    labels = []
    vectors = []
    for label, spec in bank["labels"].items():
        labels.append(label)
        vectors.append(embed_prompt_ensemble(model, spec["prompts"]))
    return labels, np.stack(vectors, axis=0)


def embed_negative_prompts(model: Any, prompts: list[str]) -> np.ndarray | None:
    deduped = list(dict.fromkeys(prompt.strip() for prompt in prompts if isinstance(prompt, str) and prompt.strip()))
    if not deduped:
        return None
    emb = model.get_text_embedding(deduped, use_tensor=False)
    return l2norm(np.asarray(emb, dtype=np.float32), axis=-1)


def build_negative_banks(model: Any, bank: dict[str, Any], labels: list[str]) -> dict[str, np.ndarray]:
    global_negatives: list[str] = []
    for neg in bank.get("global_hard_negatives", []) or []:
        if isinstance(neg, str) and neg.strip():
            global_negatives.append(neg.strip())

    result: dict[str, np.ndarray] = {}
    label_specs = bank.get("labels", {})
    for label in labels:
        negatives = list(global_negatives)
        spec = label_specs.get(label, {})
        for neg in spec.get("hard_negatives", []) or []:
            if isinstance(neg, str) and neg.strip():
                negatives.append(neg.strip())
        embedded = embed_negative_prompts(model, negatives)
        if embedded is not None:
            result[label] = embedded
    return result


def load_audio_windows(
    librosa: Any,
    path: Path,
    sample_rate: int = 48_000,
    window_seconds: float = 10.0,
    hop_seconds: float = 5.0,
) -> np.ndarray:
    audio, _ = librosa.load(str(path), sr=sample_rate, mono=True)
    if audio.size == 0:
        raise ValueError(f"empty audio: {path}")

    window = int(round(sample_rate * window_seconds))
    hop = int(round(sample_rate * hop_seconds))
    if window <= 0 or hop <= 0:
        raise ValueError("window and hop must be positive")

    if audio.size <= window:
        padded = np.zeros(window, dtype=np.float32)
        padded[: audio.size] = audio.astype(np.float32)
        return padded.reshape(1, -1)

    starts = list(range(0, max(audio.size - window + 1, 1), hop))
    if starts[-1] + window < audio.size:
        starts.append(audio.size - window)

    windows = np.stack([audio[s : s + window] for s in starts], axis=0).astype(np.float32)
    return windows


def top_fraction_mean(values: np.ndarray, fraction: float = 0.2) -> float:
    if values.size == 0:
        return float("nan")
    k = max(1, int(math.ceil(values.size * fraction)))
    return float(np.sort(values)[-k:].mean())


def summarize_scores(scores: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(np.mean(scores)),
        "median": float(np.median(scores)),
        "top20_mean": top_fraction_mean(scores, 0.2),
        "max": float(np.max(scores)),
        "std": float(np.std(scores)),
    }


def score_audio(
    model: Any,
    librosa: Any,
    audio_path: Path,
    labels: list[str],
    label_vectors: np.ndarray,
    negative_vectors_by_label: dict[str, np.ndarray],
    alpha: float,
    window_seconds: float,
    hop_seconds: float,
) -> dict[str, Any]:
    windows = load_audio_windows(librosa, audio_path, window_seconds=window_seconds, hop_seconds=hop_seconds)
    audio_emb = model.get_audio_embedding_from_data(windows, use_tensor=False)
    audio_emb = l2norm(np.asarray(audio_emb, dtype=np.float32), axis=-1)

    positive = audio_emb @ label_vectors.T

    final = positive.copy()
    negative_by_label: dict[str, np.ndarray] = {}
    if alpha > 0:
        for idx, label in enumerate(labels):
            negative_vectors = negative_vectors_by_label.get(label)
            if negative_vectors is None:
                continue
            negative_scores = (audio_emb @ negative_vectors.T).max(axis=1)
            negative_by_label[label] = negative_scores
            final[:, idx] = positive[:, idx] - alpha * negative_scores

    per_label = {}
    for idx, label in enumerate(labels):
        per_label[label] = {
            "positive": summarize_scores(positive[:, idx]),
            "final": summarize_scores(final[:, idx]),
        }
        if label in negative_by_label:
            per_label[label]["negative"] = summarize_scores(negative_by_label[label])

    ranking = sorted(
        [
            {
                "label": label,
                "final_top20_mean": per_label[label]["final"]["top20_mean"],
                "final_median": per_label[label]["final"]["median"],
                "positive_top20_mean": per_label[label]["positive"]["top20_mean"],
            }
            for label in labels
        ],
        key=lambda item: item["final_top20_mean"],
        reverse=True,
    )

    return {
        "audio": str(audio_path),
        "num_windows": int(windows.shape[0]),
        "window_seconds": window_seconds,
        "hop_seconds": hop_seconds,
        "ranking": ranking,
        "labels": per_label,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-bank", type=Path, required=True)
    parser.add_argument("--ckpt", type=Path, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--audio", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--alpha", type=float, default=0.35, help="Hard-negative margin weight")
    parser.add_argument("--amodel", default="HTSAT-base")
    parser.add_argument("--device", default=None)
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--hop-seconds", type=float, default=5.0)
    args = parser.parse_args()

    global np
    np, librosa, laion_clap, torch = require_dependencies()

    device = args.device
    if device is None:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

    bank = load_prompt_bank(args.prompt_bank)

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel=args.amodel, device=device)
    load_checkpoint_weights_only(model, torch, args.ckpt)

    labels, label_vectors = build_label_bank(model, bank)
    label_vectors = l2norm(label_vectors, axis=-1)
    negative_vectors_by_label = build_negative_banks(model, bank, labels)

    results = []
    for audio_path in args.audio:
        results.append(
            score_audio(
                model=model,
                librosa=librosa,
                audio_path=audio_path,
                labels=labels,
                label_vectors=label_vectors,
                negative_vectors_by_label=negative_vectors_by_label,
                alpha=args.alpha,
                window_seconds=args.window_seconds,
                hop_seconds=args.hop_seconds,
            )
        )

    output = {
        "prompt_bank": str(args.prompt_bank),
        "checkpoint": str(args.ckpt),
        "amodel": args.amodel,
        "enable_fusion": False,
        "alpha": args.alpha,
        "results": results,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())

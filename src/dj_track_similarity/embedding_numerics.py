from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _normalize_rows(matrix: np.ndarray) -> list[np.ndarray]:
    vectors = []
    for row in matrix:
        vector = np.asarray(row, dtype=np.float32).reshape(-1)
        if not np.isfinite(vector).all():
            raise ValueError("Model produced a non-finite vector")
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("Model produced a zero vector")
        vectors.append(vector / norm)
    return vectors

def _array_output_to_numpy(output) -> np.ndarray:
    if hasattr(output, "detach"):
        output = output.detach().cpu().numpy()
    return np.asarray(output, dtype=np.float32)

def _normalized_embedding_rows(
    output,
    *,
    expected_rows: int,
    expected_dim: int,
    model_label: str,
) -> list[np.ndarray]:
    matrix = _array_output_to_numpy(output)
    if matrix.shape != (expected_rows, expected_dim):
        raise ValueError(
            f"{model_label} output shape {matrix.shape} does not match "
            f"({expected_rows}, {expected_dim})"
        )
    return _normalize_rows(matrix)

def _average_l2_window_embeddings(
    pooled_windows: Sequence[np.ndarray],
    track_windows: Sequence[Sequence[int]],
) -> list[np.ndarray]:
    vectors: list[np.ndarray] = []
    for indices in track_windows:
        vector = np.mean(
            np.vstack([pooled_windows[index] for index in indices]),
            axis=0,
        ).astype(np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("Model produced a zero vector")
        vectors.append(vector / norm)
    return vectors

from __future__ import annotations

import numpy as np

from dj_track_similarity.analysis_models import EMBEDDING_LAYERS


def same_vector_layers(family: str, vector: np.ndarray) -> tuple[np.ndarray, ...] | None:
    """Every stored layer of a layered family as *vector*, else ``None``.

    A layered ``EmbeddingOutput`` must carry all of its layers; a fixture that
    needs only one vector per track repeats it on each of them.
    """

    layers = EMBEDDING_LAYERS.get(family)
    return None if layers is None else (vector,) * layers.count

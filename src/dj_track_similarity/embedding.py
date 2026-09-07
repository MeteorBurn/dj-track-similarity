from __future__ import annotations

from .embedding_clap import ClapEmbeddingAdapter
from .embedding_maest import MaestEmbeddingAdapter
from .embedding_mert import MertEmbeddingAdapter
from .embedding_mulan import MuqMulanEmbeddingAdapter
from .embedding_muq import MuqEmbeddingAdapter


def adapter_factories():
    return {
        "maest": MaestEmbeddingAdapter,
        "mert": MertEmbeddingAdapter,
        "muq": MuqEmbeddingAdapter,
        "mulan": MuqMulanEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
    }

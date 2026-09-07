from __future__ import annotations

from .clap import ClapEmbeddingAdapter
from .maest import MaestEmbeddingAdapter
from .mert import MertEmbeddingAdapter
from .mulan import MuqMulanEmbeddingAdapter
from .muq import MuqEmbeddingAdapter


def adapter_factories():
    return {
        "maest": MaestEmbeddingAdapter,
        "mert": MertEmbeddingAdapter,
        "muq": MuqEmbeddingAdapter,
        "mulan": MuqMulanEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
    }

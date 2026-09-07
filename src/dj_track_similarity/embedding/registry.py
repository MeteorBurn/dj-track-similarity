from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict, overload

if TYPE_CHECKING:
    from .clap import ClapEmbeddingAdapter
    from .maest import MaestEmbeddingAdapter
    from .mert import MertEmbeddingAdapter
    from .mulan import MuqMulanEmbeddingAdapter
    from .muq import MuqEmbeddingAdapter


class AdapterFactories(TypedDict):
    maest: type[MaestEmbeddingAdapter]
    mert: type[MertEmbeddingAdapter]
    muq: type[MuqEmbeddingAdapter]
    mulan: type[MuqMulanEmbeddingAdapter]
    clap: type[ClapEmbeddingAdapter]


def adapter_factories() -> AdapterFactories:
    from .clap import ClapEmbeddingAdapter
    from .maest import MaestEmbeddingAdapter
    from .mert import MertEmbeddingAdapter
    from .mulan import MuqMulanEmbeddingAdapter
    from .muq import MuqEmbeddingAdapter

    return {
        "maest": MaestEmbeddingAdapter,
        "mert": MertEmbeddingAdapter,
        "muq": MuqEmbeddingAdapter,
        "mulan": MuqMulanEmbeddingAdapter,
        "clap": ClapEmbeddingAdapter,
    }


@overload
def create_embedding_adapter(
    family: Literal["maest"],
    *,
    device: str,
    inference_batch_size: int,
    top_k: int,
) -> MaestEmbeddingAdapter: ...


@overload
def create_embedding_adapter(
    family: Literal["mert", "muq"],
    *,
    device: str,
    inference_batch_size: int | None = None,
    top_k: None = None,
) -> MertEmbeddingAdapter | MuqEmbeddingAdapter: ...


@overload
def create_embedding_adapter(
    family: Literal["mulan", "clap"],
    *,
    device: str,
    inference_batch_size: int | None = None,
    top_k: None = None,
) -> MuqMulanEmbeddingAdapter | ClapEmbeddingAdapter: ...


def create_embedding_adapter(
    family: str,
    *,
    device: str,
    inference_batch_size: int | None = None,
    top_k: int | None = None,
) -> (
    MaestEmbeddingAdapter
    | MertEmbeddingAdapter
    | MuqEmbeddingAdapter
    | MuqMulanEmbeddingAdapter
    | ClapEmbeddingAdapter
):
    """Construct a lazy adapter without changing family-specific defaults."""

    factories = adapter_factories()
    if family == "maest":
        if top_k is None or inference_batch_size is None:
            raise TypeError("MAEST construction requires top_k and inference_batch_size")
        return factories["maest"](
            device=device,
            inference_batch_size=inference_batch_size,
            top_k=top_k,
        )
    if family == "mert" or family == "muq" or family == "mulan" or family == "clap":
        if top_k is not None:
            raise TypeError("top_k is only supported for MAEST")
        factory = factories[family]
        if inference_batch_size is None:
            return factory(device=device)
        return factory(device=device, inference_batch_size=inference_batch_size)
    raise ValueError(f"Unsupported embedding model: {family}")

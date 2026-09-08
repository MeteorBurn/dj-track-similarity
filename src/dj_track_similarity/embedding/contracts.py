from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from ..audio.loader import DecodedAudio
    from .maest import MaestAnalysisResult


class EmbeddingIdentity(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    @property
    def checkpoint_id(self) -> str: ...

    @property
    def preprocessing(self) -> str: ...


class EmbeddingRuntime(EmbeddingIdentity, Protocol):
    @property
    def device(self) -> str | None: ...

    def preflight(self) -> None: ...

    def runtime_parameters(self) -> dict[str, object]: ...


class DecodedAudioEmbeddingAdapter(EmbeddingRuntime, Protocol):
    def embed_decoded_batch(
        self,
        decoded_items: list[DecodedAudio],
    ) -> list[NDArray[np.float32]]: ...


class TextEmbeddingAdapter(EmbeddingIdentity, Protocol):
    @property
    def embedding_key(self) -> str: ...

    def embed_text(self, text: str) -> NDArray[np.float32]: ...

    def embed_texts(self, texts: Sequence[str]) -> list[NDArray[np.float32]]: ...


class MaestAnalysisAdapter(EmbeddingRuntime, Protocol):
    def analyze_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        include_mel_spectrogram: bool = False,
    ) -> list[MaestAnalysisResult]: ...

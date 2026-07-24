from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TypeVar, cast

import numpy as np
import numpy.typing as npt

from .analysis_contracts import utc_timestamp
from .analysis_job_batch import AnalysisBatchItem
from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisWriteResult,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    SonaraWrite,
    clap_embedding_output,
    maest_analysis_output,
    maest_embedding_output,
    mert_embedding_output,
    muq_embedding_output,
)
from .audio_loader import DecodedAudio
from .embedding import (
    ClapEmbeddingAdapter,
    MertEmbeddingAdapter,
    MuqEmbeddingAdapter,
)
from .genres import MaestGenreAdapter
from .sonara_contract import normalize_sonara_outputs
from .sonara_features import (
    SonaraBatchMetrics,
    analysis_outputs_for_sonara_runtime,
    analyze_and_store_sonara_batch,
)


_CHECKPOINT_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_SYNCOPATED_RHYTHM_LABELS = frozenset(
    label.casefold()
    for label in (
        "Breakbeat",
        "Breakcore",
        "Breaks",
        "Progressive Breaks",
        "Broken Beat",
        "Drum n Bass",
        "Jungle",
        "Halftime",
        "Juke",
        "UK Garage",
        "Speed Garage",
        "Bassline",
        "Electro",
    )
)


class AnalysisWriteRepository(Protocol):
    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]: ...

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
    ) -> list[AnalysisCandidate]: ...

    def save_sonara_results(
        self,
        writes: Sequence[SonaraWrite],
    ) -> tuple[AnalysisWriteResult, ...]: ...

    def save_maest_results(
        self,
        writes: Sequence[MaestWrite],
    ) -> tuple[AnalysisWriteResult, ...]: ...

    def save_embedding_results(
        self,
        writes: Sequence[EmbeddingWrite],
    ) -> tuple[AnalysisWriteResult, ...]: ...


class AnalysisModelRunner(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def device(self) -> str | None: ...

    @property
    def active_outputs(self) -> tuple[AnalysisOutput, ...]: ...

    @property
    def candidate_outputs(self) -> tuple[AnalysisOutput, ...]: ...

    def preflight(self) -> None: ...

    def analyze_batch(
        self,
        repository: AnalysisWriteRepository,
        items: Sequence[AnalysisBatchItem],
    ) -> Sequence[Exception | None]: ...


RunnerFactory = Callable[
    [str, str, int, int, tuple[str, ...]],
    AnalysisModelRunner,
]


class SonaraModelRunner:
    model = "sonara"
    device = "cpu"

    def __init__(
        self,
        *,
        outputs: tuple[str, ...] = ("core",),
        sonara_module: Any | None = None,
    ) -> None:
        self.outputs = normalize_sonara_outputs(outputs)
        self._sonara_module = sonara_module
        self._active_outputs = analysis_outputs_for_sonara_runtime(sonara_module)
        selected = set(self.outputs)
        self._candidate_outputs = tuple(
            output
            for output in self._active_outputs
            if output.contract.output_kind in selected
        )
        if not self._candidate_outputs:
            raise RuntimeError("SONARA runner has no requested outputs")
        self.progress: Callable[[int, int], None] | None = None
        self.last_metrics: SonaraBatchMetrics | None = None

    @property
    def model_name(self) -> str:
        return self._active_outputs[0].contract.model_name

    @property
    def active_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    @property
    def candidate_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._candidate_outputs

    def preflight(self) -> None:
        """SONARA runtime identity is preflighted by release preparation."""

    def analyze_batch(
        self,
        repository: AnalysisWriteRepository,
        items: Sequence[AnalysisBatchItem],
    ) -> Sequence[Exception | None]:
        self.last_metrics = None
        results = analyze_and_store_sonara_batch(
            repository,
            [item.candidate for item in items],
            sonara_module=self._sonara_module,
            outputs=self.outputs,
            progress=self.progress,
            metrics=self._capture_metrics,
        )
        return [result.error for result in results]

    def _capture_metrics(self, metrics: SonaraBatchMetrics) -> None:
        self.last_metrics = metrics


class MaestModelRunner:
    model = "maest"

    def __init__(
        self,
        *,
        device: str,
        top_k: int,
        inference_batch_size: int,
        adapter: MaestGenreAdapter | None = None,
    ) -> None:
        self.adapter = adapter or MaestGenreAdapter(
            device=device,
            top_k=top_k,
            inference_batch_size=inference_batch_size,
        )
        facts, extras = _contract_parameters(
            self.adapter,
            reserved=(
                "sample_rate_hz",
                "input_seconds",
                "analysis_offset_seconds",
                "analysis_window_ratios",
                "top_k",
                "pooling",
            ),
        )
        identity = _adapter_identity(self.adapter)
        analysis = maest_analysis_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_offset_seconds=cast(
                float,
                facts["analysis_offset_seconds"],
            ),
            analysis_window_ratios=cast(
                Sequence[float],
                facts["analysis_window_ratios"],
            ),
            top_k=cast(int, facts["top_k"]),
            parameters=extras,
        )
        embedding = maest_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_offset_seconds=cast(
                float,
                facts["analysis_offset_seconds"],
            ),
            analysis_window_ratios=cast(
                Sequence[float],
                facts["analysis_window_ratios"],
            ),
            pooling=cast(str, facts["pooling"]),
            parameters=extras,
        )
        self._active_outputs = (analysis, embedding)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    @property
    def active_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    @property
    def candidate_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    def preflight(self) -> None:
        self.adapter.preflight()

    def analyze_batch(
        self,
        repository: AnalysisWriteRepository,
        items: Sequence[AnalysisBatchItem],
    ) -> Sequence[Exception | None]:
        decoded_items = _decoded_items(items)
        genres_by_track = self.adapter.predict_decoded_batch(decoded_items)
        if len(genres_by_track) != len(items):
            raise ValueError("MAEST batch result count does not match track count")

        prepared: list[MaestWrite | Exception] = []
        analysis_contract = self._active_outputs[0].contract
        embedding_contract = self._active_outputs[1].contract
        for item, decoded, genres in zip(items, decoded_items, genres_by_track):
            try:
                analyzed_at = utc_timestamp()
                genre_scores = _maest_genres(genres)
                vector = _embedding_for_path(self.adapter, decoded.path)
                if vector is None:
                    raise ValueError("MAEST did not return the required embedding")
                prepared.append(
                    MaestWrite(
                        target=item.candidate.target,
                        analysis_contract=analysis_contract,
                        genres=genre_scores,
                        syncopated_rhythm=_has_syncopated_rhythm(genre_scores),
                        analyzed_at=analyzed_at,
                        embedding=EmbeddingOutput(
                            contract=embedding_contract,
                            vector=_l2_normalize(vector, model="MAEST"),
                            analyzed_at=analyzed_at,
                        ),
                    )
                )
            except Exception as error:
                prepared.append(error)

        writes = tuple(item for item in prepared if isinstance(item, MaestWrite))
        write_results = repository.save_maest_results(writes)
        return _merge_write_results(prepared, writes, write_results)


class EmbeddingModelRunner:
    def __init__(
        self,
        model: str,
        *,
        device: str,
        inference_batch_size: int,
        adapter: (
            MertEmbeddingAdapter | MuqEmbeddingAdapter | ClapEmbeddingAdapter | None
        ) = None,
    ) -> None:
        self.model = model
        adapter_classes = {
            "mert": MertEmbeddingAdapter,
            "muq": MuqEmbeddingAdapter,
            "clap": ClapEmbeddingAdapter,
        }
        try:
            adapter_class = adapter_classes[model]
        except KeyError as error:
            raise ValueError(f"Unsupported embedding model: {model}") from error
        self.adapter = adapter or adapter_class(
            device=device,
            inference_batch_size=inference_batch_size,
        )
        self._active_outputs = (embedding_analysis_output(model, self.adapter),)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    @property
    def active_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    @property
    def candidate_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    def preflight(self) -> None:
        self.adapter.preflight()

    def analyze_batch(
        self,
        repository: AnalysisWriteRepository,
        items: Sequence[AnalysisBatchItem],
    ) -> Sequence[Exception | None]:
        vectors = self.adapter.embed_decoded_batch(_decoded_items(items))
        if len(vectors) != len(items):
            raise ValueError(
                f"{self.model.upper()} batch result count does not match track count"
            )

        prepared: list[EmbeddingWrite | Exception] = []
        contract = self._active_outputs[0].contract
        for item, vector in zip(items, vectors):
            try:
                prepared.append(
                    EmbeddingWrite(
                        target=item.candidate.target,
                        output=EmbeddingOutput(
                            contract=contract,
                            vector=vector,
                            analyzed_at=utc_timestamp(),
                        ),
                    )
                )
            except Exception as error:
                prepared.append(error)

        writes = tuple(item for item in prepared if isinstance(item, EmbeddingWrite))
        write_results = repository.save_embedding_results(writes)
        return _merge_write_results(prepared, writes, write_results)


def default_model_runners(
    model: str,
    device: str,
    inference_batch_size: int,
    top_k: int,
    sonara_outputs: tuple[str, ...] = ("core",),
) -> AnalysisModelRunner:
    if model == "sonara":
        return SonaraModelRunner(outputs=sonara_outputs)
    if model == "maest":
        return MaestModelRunner(
            device=device,
            top_k=top_k,
            inference_batch_size=inference_batch_size,
        )
    if model in {"mert", "muq", "clap"}:
        return EmbeddingModelRunner(
            model,
            device=device,
            inference_batch_size=inference_batch_size,
        )
    raise ValueError(f"No analysis runner configured for: {model}")


_default_model_runners: RunnerFactory = default_model_runners


def _adapter_identity(adapter: object) -> dict[str, str]:
    identity = {
        "model_name": _required_adapter_text(adapter, "model_name"),
        "model_version": _required_adapter_text(adapter, "model_version"),
        "checkpoint_id": _required_adapter_text(adapter, "checkpoint_id"),
        "preprocessing": _required_adapter_text(adapter, "preprocessing"),
    }
    if _CHECKPOINT_DIGEST_PATTERN.fullmatch(identity["checkpoint_id"]) is None:
        raise ValueError(
            f"{identity['model_name']} checkpoint_id must be a lowercase sha256 digest"
        )
    return identity


def _required_adapter_text(adapter: object, name: str) -> str:
    value = getattr(adapter, name, None)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{type(adapter).__name__} does not expose immutable {name}")
    return value.strip()


def _contract_parameters(
    adapter: object,
    *,
    reserved: Sequence[str],
) -> tuple[dict[str, object], dict[str, object]]:
    factory = getattr(adapter, "contract_parameters", None)
    if not callable(factory):
        raise RuntimeError(
            f"{type(adapter).__name__} does not expose contract_parameters()"
        )
    raw = factory()
    if not isinstance(raw, Mapping):
        raise TypeError("adapter contract_parameters() must return a mapping")
    extras = dict(raw)
    missing = sorted(name for name in reserved if name not in extras)
    if missing:
        raise ValueError(
            f"adapter contract parameters are incomplete; missing={missing}"
        )
    facts = {name: extras.pop(name) for name in reserved}
    return facts, extras


def embedding_analysis_output(
    model: str,
    adapter: object,
) -> AnalysisOutput:
    """Build the strict active embedding output for one production adapter."""

    identity = _adapter_identity(adapter)
    if model == "maest":
        facts, extras = _contract_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "input_seconds",
                "analysis_offset_seconds",
                "analysis_window_ratios",
                "top_k",
                "pooling",
            ),
        )
        return maest_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_offset_seconds=cast(
                float,
                facts["analysis_offset_seconds"],
            ),
            analysis_window_ratios=cast(
                Sequence[float],
                facts["analysis_window_ratios"],
            ),
            pooling=cast(str, facts["pooling"]),
            parameters=extras,
        )
    if model == "mert":
        facts, extras = _contract_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "window_seconds",
                "max_windows",
                "hidden_layers",
                "pooling",
            ),
        )
        return mert_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            window_seconds=cast(float, facts["window_seconds"]),
            max_windows=cast(int, facts["max_windows"]),
            hidden_layers=cast(Sequence[int], facts["hidden_layers"]),
            pooling=cast(str, facts["pooling"]),
            parameters=extras,
        )
    if model == "muq":
        facts, extras = _contract_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "window_seconds",
                "max_windows",
                "pooling",
                "dtype",
            ),
        )
        return muq_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            window_seconds=cast(float, facts["window_seconds"]),
            max_windows=cast(int, facts["max_windows"]),
            pooling=cast(str, facts["pooling"]),
            dtype=cast(str, facts["dtype"]),
            parameters=extras,
        )
    if model == "clap":
        facts, extras = _contract_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "window_seconds",
                "max_windows",
                "pooling",
                "amodel",
                "enable_fusion",
            ),
        )
        return clap_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            window_seconds=cast(float, facts["window_seconds"]),
            max_windows=cast(int, facts["max_windows"]),
            pooling=cast(str, facts["pooling"]),
            amodel=cast(str, facts["amodel"]),
            enable_fusion=cast(bool, facts["enable_fusion"]),
            parameters=extras,
        )
    raise ValueError(f"Unsupported embedding model: {model}")


def current_embedding_analysis_output(
    model: str,
    *,
    device: str = "auto",
) -> AnalysisOutput:
    """Build current adapter identity without loading model weights."""

    clean_model = str(model).strip().lower()
    if clean_model == "maest":
        adapter: object = MaestGenreAdapter(device=device)
    elif clean_model == "mert":
        adapter = MertEmbeddingAdapter(device=device)
    elif clean_model == "muq":
        adapter = MuqEmbeddingAdapter(device=device)
    elif clean_model == "clap":
        adapter = ClapEmbeddingAdapter(device=device)
    else:
        raise ValueError(f"Unsupported embedding model: {model}")
    return embedding_analysis_output(clean_model, adapter)


def _decoded_items(items: Sequence[AnalysisBatchItem]) -> list[DecodedAudio]:
    decoded: list[DecodedAudio] = []
    for item in items:
        if not isinstance(item.decoded, DecodedAudio):
            raise TypeError(
                "ML analysis requires a DecodedAudio value for every candidate"
            )
        decoded.append(item.decoded)
    return decoded


def _maest_genres(
    values: Sequence[Mapping[str, object]],
) -> tuple[MaestGenreScore, ...]:
    genres: list[MaestGenreScore] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise TypeError("MAEST genre rows must be mappings")
        genres.append(
            MaestGenreScore(
                label=str(value.get("label") or ""),
                score=float(value.get("score")),
            )
        )
    return tuple(genres)


def _has_syncopated_rhythm(genres: Sequence[MaestGenreScore]) -> bool:
    return any(genre.label.casefold() in _SYNCOPATED_RHYTHM_LABELS for genre in genres)


def _embedding_for_path(
    adapter: MaestGenreAdapter,
    path: str,
) -> npt.NDArray[np.float32] | None:
    vector = adapter.embedding_for_path(path)
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float32)


def _l2_normalize(
    vector: npt.ArrayLike,
    *,
    model: str,
) -> npt.NDArray[np.float32]:
    values = np.asarray(vector, dtype=np.float32)
    if values.ndim != 1 or not bool(np.all(np.isfinite(values))):
        raise ValueError(f"{model} produced an invalid embedding")
    norm = float(np.linalg.norm(values))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError(f"{model} produced a zero embedding")
    return np.asarray(values / norm, dtype=np.float32)


_Write = TypeVar("_Write", SonaraWrite, MaestWrite, EmbeddingWrite)


def _merge_write_results(
    prepared: Sequence[_Write | Exception],
    writes: Sequence[_Write],
    results: Sequence[AnalysisWriteResult],
) -> list[Exception | None]:
    if len(results) != len(writes):
        raise RuntimeError(
            "analysis repository result count does not match prepared write count"
        )
    validated: list[Exception | None] = []
    for write, result in zip(writes, results):
        if not isinstance(result, AnalysisWriteResult):
            raise TypeError(
                "analysis repository must return AnalysisWriteResult values"
            )
        if result.target != write.target:
            raise RuntimeError(
                "analysis repository returned a result for the wrong target"
            )
        if result.error is None:
            expected_hashes = {output.contract_hash for output in _write_outputs(write)}
            written_hashes = {output.contract_hash for output in result.written_outputs}
            if written_hashes != expected_hashes:
                raise RuntimeError(
                    "analysis repository did not confirm every requested output"
                )
            validated.append(None)
        else:
            validated.append(RuntimeError(result.error))

    result_iterator = iter(validated)
    merged: list[Exception | None] = []
    for item in prepared:
        if isinstance(item, Exception):
            merged.append(item)
        else:
            merged.append(next(result_iterator))
    return merged


def _write_outputs(
    write: SonaraWrite | MaestWrite | EmbeddingWrite,
) -> tuple[AnalysisOutput, ...]:
    if isinstance(write, EmbeddingWrite):
        return (AnalysisOutput(write.output.contract),)
    return write.outputs

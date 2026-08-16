from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TypeVar, cast

import numpy as np
import numpy.typing as npt

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
    mulan_embedding_output,
)
from .analysis_job_batch import DecodeFailure
from .audio_loader import (
    DecodedAudio,
    load_decoded_audio_with_ffmpeg,
)
from .embedding import (
    ClapEmbeddingAdapter,
    MaestEmbeddingAdapter,
    MertEmbeddingAdapter,
    MuqEmbeddingAdapter,
    MuqMulanEmbeddingAdapter,
)
from .maest_analysis_validation import has_maest_syncopated_rhythm
from .timestamps import utc_timestamp
from .sonara_features import (
    SonaraBatchMetrics,
    analysis_outputs_for_sonara_runtime,
    analyze_and_store_sonara_batch,
)
from .sonara_staging import (
    SonaraStagingConfig,
    StagedSonaraResult,
    analyze_and_store_staged_sonara,
    analyze_staged_sonara_group,
    sonara_process_executor,
)
from .sonara_storage import prepare_sonara_write


_CHECKPOINT_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
class AnalysisWriteRepository(Protocol):
    def current_sonara_track_count(self) -> int: ...

    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]: ...

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
        require_current_sonara: bool = False,
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


RunnerFactory = Callable[[str, str, int, int], AnalysisModelRunner]


class SonaraModelRunner:
    model = "sonara"
    device = "cpu"

    def __init__(
        self,
        *,
        sonara_module: Any | None = None,
        staging_config: SonaraStagingConfig | None = None,
    ) -> None:
        self._sonara_module = sonara_module
        self._active_outputs = analysis_outputs_for_sonara_runtime()
        self._candidate_outputs = self._active_outputs
        self.progress: Callable[[int, int], None] | None = None
        self.last_metrics: SonaraBatchMetrics | None = None
        self.last_ffmpeg_fallback_track_ids: frozenset[int] = frozenset()
        self.staging_config = staging_config
        self.cancelled: Callable[[], bool] | None = None
        self.track_result: Callable[[StagedSonaraResult], None] | None = None
        self.incremental_results_emitted = False

    @property
    def model_name(self) -> str:
        return "sonara"

    @property
    def active_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._active_outputs

    @property
    def candidate_outputs(self) -> tuple[AnalysisOutput, ...]:
        return self._candidate_outputs

    def preflight(self) -> None:
        """SONARA requires no model preflight beyond normal batch execution."""

    def analyze_batch(
        self,
        repository: AnalysisWriteRepository,
        items: Sequence[AnalysisBatchItem],
    ) -> Sequence[Exception | None]:
        self.last_metrics = None
        self.last_ffmpeg_fallback_track_ids = frozenset()
        self.incremental_results_emitted = False
        candidates = [item.candidate for item in items]
        if self.staging_config is None:
            results = analyze_and_store_sonara_batch(
                repository,
                candidates,
                sonara_module=self._sonara_module,
                progress=self.progress,
                metrics=self._capture_metrics,
            )
        else:
            self.incremental_results_emitted = True
            staged_results = analyze_and_store_staged_sonara(
                repository,
                candidates,
                config=self.staging_config,
                analyze_group=analyze_staged_sonara_group,
                prepare_write=lambda candidate, analysis: prepare_sonara_write(
                    candidate,
                    analysis,
                    analyzed_at=utc_timestamp(),
                ),
                store_write=_store_staged_sonara_write,
                cancelled=self.cancelled,
                executor_factory=lambda: sonara_process_executor(self.staging_config),
                result_callback=self.track_result,
            )
            results = staged_results
            self.last_metrics = SonaraBatchMetrics(
                track_count=len(candidates),
                source_bytes=sum(candidate.file_size_bytes for candidate in candidates),
                analyze_seconds=sum(result.analyze_seconds for result in staged_results),
                prepare_seconds=0.0,
                store_seconds=sum(result.store_seconds for result in staged_results),
                copy_seconds=sum(result.copy_seconds for result in staged_results),
                staged_track_count=len(staged_results),
                ffmpeg_fallback_count=sum(
                    result.used_ffmpeg_fallback for result in staged_results
                ),
            )
        self.last_ffmpeg_fallback_track_ids = frozenset(
            result.target.track_id
            for result in results
            if result.used_ffmpeg_fallback
        )
        return [result.error for result in results]

    def _capture_metrics(self, metrics: SonaraBatchMetrics) -> None:
        self.last_metrics = metrics


def _store_staged_sonara_write(
    repository: AnalysisWriteRepository,
    write: SonaraWrite,
) -> None:
    results = tuple(repository.save_sonara_results((write,)))
    if len(results) != 1:
        raise RuntimeError("SONARA staged storage did not return one result")
    result = results[0]
    if result.target != write.target:
        raise RuntimeError("SONARA staged storage returned the wrong target")
    if result.error is not None:
        raise RuntimeError(f"SONARA storage failure: {result.error}")


class MaestModelRunner:
    model = "maest"

    def __init__(
        self,
        *,
        device: str,
        top_k: int,
        inference_batch_size: int,
        adapter: MaestEmbeddingAdapter | None = None,
    ) -> None:
        self.adapter = adapter or MaestEmbeddingAdapter(
            device=device,
            top_k=top_k,
            inference_batch_size=inference_batch_size,
        )
        facts, extras = _runtime_parameters(
            self.adapter,
            reserved=(
                "sample_rate_hz",
                "input_seconds",
                "analysis_window_positions",
                "top_k",
                "pooling",
            ),
        )
        identity = _adapter_identity(self.adapter)
        analysis = maest_analysis_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_window_positions=cast(
                Sequence[float],
                facts["analysis_window_positions"],
            ),
            top_k=cast(int, facts["top_k"]),
            parameters=extras,
        )
        embedding = maest_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_window_positions=cast(
                Sequence[float],
                facts["analysis_window_positions"],
            ),
            pooling=cast(str, facts["pooling"]),
            parameters=extras,
        )
        self._active_outputs = (analysis, embedding)
        self.last_ffmpeg_fallback_track_ids: frozenset[int] = frozenset()

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
        self.last_ffmpeg_fallback_track_ids = frozenset()
        results_by_track = self._maest_results(items)

        prepared: list[MaestWrite | Exception] = []
        for item, result in zip(items, results_by_track):
            try:
                if isinstance(result, Exception):
                    raise result
                analyzed_at = utc_timestamp()
                genre_scores = _maest_genres(result.genres)
                prepared.append(
                    MaestWrite(
                        target=item.candidate.target,
                        genres=genre_scores,
                        syncopated_rhythm=_has_syncopated_rhythm(genre_scores),
                        analyzed_at=analyzed_at,
                        embedding=EmbeddingOutput(
                            family="maest",
                            vector=_l2_normalize(result.embedding, model="MAEST"),
                            analyzed_at=analyzed_at,
                        ),
                    )
                )
            except Exception as error:
                prepared.append(error)

        writes = tuple(item for item in prepared if isinstance(item, MaestWrite))
        write_results = repository.save_maest_results(writes)
        return _merge_write_results(prepared, writes, write_results)

    def _maest_results(
        self,
        items: Sequence[AnalysisBatchItem],
    ) -> list[MaestAnalysisResult | Exception]:
        results: list[MaestAnalysisResult | Exception | None] = [None] * len(items)
        direct_indexes = [
            index
            for index, item in enumerate(items)
            if isinstance(item.decoded, DecodedAudio)
        ]
        if direct_indexes:
            direct_items = [items[index] for index in direct_indexes]
            direct_results = self.adapter.analyze_decoded_batch(
                _decoded_items(direct_items),
                window_contexts=[
                    item.candidate.maest_window_context for item in direct_items
                ],
            )
            if len(direct_results) != len(direct_items):
                raise ValueError("MAEST batch result count does not match track count")
            for index, result in zip(direct_indexes, direct_results):
                results[index] = result

        ffmpeg_track_ids: set[int] = set()
        for index, item in enumerate(items):
            if not isinstance(item.decoded, DecodeFailure):
                continue
            try:
                decoded = load_decoded_audio_with_ffmpeg(item.candidate.file_path)
                ffmpeg_results = self.adapter.analyze_decoded_batch(
                    [decoded],
                    window_contexts=[item.candidate.maest_window_context],
                )
                if len(ffmpeg_results) != 1:
                    raise ValueError("MAEST FFmpeg fallback did not return one result")
                results[index] = ffmpeg_results[0]
                ffmpeg_track_ids.add(item.candidate.target.track_id)
            except Exception as ffmpeg_error:
                results[index] = RuntimeError(
                    f"full TorchCodec decode failed: {item.decoded.error}; "
                    f"FFmpeg fallback failed: {ffmpeg_error}"
                )

        self.last_ffmpeg_fallback_track_ids = frozenset(ffmpeg_track_ids)
        if any(result is None for result in results):
            raise RuntimeError("MAEST runner did not produce one result per item")
        return [result for result in results if result is not None]


class EmbeddingModelRunner:
    def __init__(
        self,
        model: str,
        *,
        device: str,
        inference_batch_size: int,
        adapter: (
            MertEmbeddingAdapter
            | MuqEmbeddingAdapter
            | MuqMulanEmbeddingAdapter
            | ClapEmbeddingAdapter
            | None
        ) = None,
    ) -> None:
        self.model = model
        adapter_classes = {
            "mert": MertEmbeddingAdapter,
            "muq": MuqEmbeddingAdapter,
            "mulan": MuqMulanEmbeddingAdapter,
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
        self.last_ffmpeg_fallback_track_ids: frozenset[int] = frozenset()

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
        self.last_ffmpeg_fallback_track_ids = frozenset()
        vectors = self._embedding_vectors(items)
        prepared: list[EmbeddingWrite | Exception] = []
        for item, vector in zip(items, vectors):
            try:
                if isinstance(vector, Exception):
                    raise vector
                prepared.append(
                    EmbeddingWrite(
                        target=item.candidate.target,
                        output=EmbeddingOutput(
                            family=self.model,
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

    def _embedding_vectors(
        self,
        items: Sequence[AnalysisBatchItem],
    ) -> list[np.ndarray | Exception]:
        results: list[np.ndarray | Exception | None] = [None] * len(items)
        direct_indexes = [
            index
            for index, item in enumerate(items)
            if isinstance(item.decoded, DecodedAudio)
        ]
        if direct_indexes:
            direct_items = [items[index] for index in direct_indexes]
            vectors = self.adapter.embed_decoded_batch(_decoded_items(direct_items))
            if len(vectors) != len(direct_items):
                raise ValueError(
                    f"{self.model.upper()} batch result count does not match track count"
                )
            for index, vector in zip(direct_indexes, vectors):
                results[index] = vector

        ffmpeg_track_ids: set[int] = set()
        for index, item in enumerate(items):
            if not isinstance(item.decoded, DecodeFailure):
                continue
            try:
                decoded = load_decoded_audio_with_ffmpeg(item.candidate.file_path)
                ffmpeg_vectors = self.adapter.embed_decoded_batch([decoded])
                if len(ffmpeg_vectors) != 1:
                    raise ValueError(
                        f"{self.model.upper()} FFmpeg fallback did not return one vector"
                    )
                results[index] = ffmpeg_vectors[0]
                ffmpeg_track_ids.add(item.candidate.target.track_id)
            except Exception as ffmpeg_error:
                results[index] = RuntimeError(
                    f"full TorchCodec decode failed: {item.decoded.error}; "
                    f"FFmpeg fallback failed: {ffmpeg_error}"
                )

        self.last_ffmpeg_fallback_track_ids = frozenset(ffmpeg_track_ids)
        if any(result is None for result in results):
            raise RuntimeError("Embedding runner did not produce one result per item")
        return [result for result in results if result is not None]


def default_model_runners(
    model: str,
    device: str,
    inference_batch_size: int,
    top_k: int,
) -> AnalysisModelRunner:
    if model == "sonara":
        return SonaraModelRunner()
    if model == "maest":
        return MaestModelRunner(
            device=device,
            top_k=top_k,
            inference_batch_size=inference_batch_size,
        )
    if model in {"mert", "muq", "mulan", "clap"}:
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


def _runtime_parameters(
    adapter: object,
    *,
    reserved: Sequence[str],
) -> tuple[dict[str, object], dict[str, object]]:
    factory = getattr(adapter, "runtime_parameters", None)
    if not callable(factory):
        raise RuntimeError(
            f"{type(adapter).__name__} does not expose runtime_parameters()"
        )
    raw = factory()
    if not isinstance(raw, Mapping):
        raise TypeError("adapter runtime_parameters() must return a mapping")
    extras = dict(raw)
    missing = sorted(name for name in reserved if name not in extras)
    if missing:
        raise ValueError(
            f"adapter runtime parameters are incomplete; missing={missing}"
        )
    facts = {name: extras.pop(name) for name in reserved}
    return facts, extras


def embedding_analysis_output(
    model: str,
    adapter: object,
) -> AnalysisOutput:
    """Build the current embedding output for one production adapter."""

    identity = _adapter_identity(adapter)
    if model == "maest":
        facts, extras = _runtime_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "input_seconds",
                "analysis_window_positions",
                "top_k",
                "pooling",
            ),
        )
        return maest_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            input_seconds=cast(float, facts["input_seconds"]),
            analysis_window_positions=cast(
                Sequence[float],
                facts["analysis_window_positions"],
            ),
            pooling=cast(str, facts["pooling"]),
            parameters=extras,
        )
    if model == "mert":
        facts, extras = _runtime_parameters(
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
        facts, extras = _runtime_parameters(
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
    if model == "mulan":
        facts, extras = _runtime_parameters(
            adapter,
            reserved=(
                "sample_rate_hz",
                "window_seconds",
                "max_windows",
                "pooling",
                "dtype",
            ),
        )
        return mulan_embedding_output(
            **identity,
            sample_rate_hz=cast(int, facts["sample_rate_hz"]),
            window_seconds=cast(float, facts["window_seconds"]),
            max_windows=cast(int, facts["max_windows"]),
            pooling=cast(str, facts["pooling"]),
            dtype=cast(str, facts["dtype"]),
            parameters=extras,
        )
    if model == "clap":
        facts, extras = _runtime_parameters(
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
        adapter: object = MaestEmbeddingAdapter(device=device)
    elif clean_model == "mert":
        adapter = MertEmbeddingAdapter(device=device)
    elif clean_model == "muq":
        adapter = MuqEmbeddingAdapter(device=device)
    elif clean_model == "mulan":
        adapter = MuqMulanEmbeddingAdapter(device=device)
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
    return has_maest_syncopated_rhythm(genre.label for genre in genres)


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
            expected_outputs = {output.key for output in _write_outputs(write)}
            written_outputs = {output.key for output in result.written_outputs}
            if written_outputs != expected_outputs:
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
        return (AnalysisOutput(write.output.family, "embedding"),)
    return write.outputs

"""Single-track MAEST export shared by HTTP and CLI, without analysis-row writes."""
from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import numpy as np

from ..analysis_models import AnalysisTarget
from ..audio.loader import load_decoded_audio, load_decoded_audio_with_ffmpeg
from ..embedding.contracts import MaestAnalysisAdapter
from ..track_models import TrackFileState


class MaestExportRepository(Protocol):
    def require_maest_export_source(self, target: AnalysisTarget | int) -> TrackFileState: ...


@dataclass(frozen=True)
class MaestMelExport:
    filename: str
    content: bytes


def build_maest_mel_export(
    repository: MaestExportRepository,
    target: AnalysisTarget | int,
    adapter: MaestAnalysisAdapter,
) -> MaestMelExport:
    source = repository.require_maest_export_source(target)
    decode_error = None
    try:
        decoded = load_decoded_audio(source.file_path)
        decoder = "torchcodec"
    except Exception as error:
        decode_error = f"{type(error).__name__}: {error}"
        try:
            decoded = load_decoded_audio_with_ffmpeg(source.file_path)
        except Exception as fallback_error:
            raise RuntimeError(
                f"TorchCodec decode failed: {decode_error}; "
                f"PyAV/FFmpeg recovery failed: {fallback_error}"
            ) from fallback_error
        decoder = "pyav-ffmpeg"
    results = adapter.analyze_decoded_batch([decoded], include_mel_spectrogram=True)
    if len(results) != 1 or results[0].mel_spectrogram is None:
        raise RuntimeError("MAEST did not return one result with a mel spectrogram")
    result = results[0]
    mel = result.mel_spectrogram
    assert mel is not None
    metadata = {
        "format": "dj-track-similarity-maest-mel",
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "track": asdict(source),
        "model": {
            "name": adapter.model_name,
            "version": adapter.model_version,
            "checkpoint_id": adapter.checkpoint_id,
            "preprocessing": adapter.preprocessing,
            "runtime_parameters": adapter.runtime_parameters(),
        },
        "decoder": decoder,
        "decode_error": decode_error,
        "source_sample_rate_hz": decoded.sample_rate,
        "duration_seconds": decoded.audio.numel() / decoded.sample_rate,
        "mel": mel.metadata,
        "genres": result.genres,
        "embedding_normalization": "l2",
    }
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        mel=np.asarray(mel.values, dtype="<f4"),
        embedding=np.asarray(result.embedding, dtype="<f4"),
        metadata_json=np.asarray(json.dumps(metadata, ensure_ascii=False, allow_nan=False)),
    )
    return MaestMelExport(f"maest-{source.track_id}-mel.npz", buffer.getvalue())


def write_maest_mel_export(export: MaestMelExport, output: Path) -> None:
    """Create a new artifact, refusing to overwrite audio or any existing file."""
    if output.suffix.lower() != ".npz":
        raise ValueError("MAEST mel output must have the .npz extension")
    with output.open("xb") as stream:
        try:
            stream.write(export.content)
        except BaseException:
            stream.close()
            output.unlink(missing_ok=True)
            raise

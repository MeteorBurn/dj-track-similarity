from __future__ import annotations

import base64
import struct

import numpy as np

from dj_track_similarity.analysis.sonara_runtime import (
    DEFAULT_SONARA_BPM_MAX,
    DEFAULT_SONARA_BPM_MIN,
)
from dj_track_similarity.analysis_models import (
    SONARA_EMBEDDING_DIM,
    AnalysisTarget,
    AnalysisWriteResult,
    EmbeddingOutput,
    FingerprintOutput,
    SonaraWrite,
    TimelineOutput,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.ddl import SonaraRow


def save_sonara_writes(
    database: LibraryDatabase,
    writes: tuple[SonaraWrite, ...],
) -> tuple[AnalysisWriteResult, ...]:
    """Store SONARA fixtures as a job does: under the library's claimed BPM range."""

    bpm_range = database.claim_sonara_analysis_range(
        DEFAULT_SONARA_BPM_MIN,
        DEFAULT_SONARA_BPM_MAX,
    )
    return database.save_sonara_results(writes, bpm_range=bpm_range)


def complete_sonara_write(target: AnalysisTarget, core: SonaraRow) -> SonaraWrite:
    """Wrap a hand-built Core row in the other outputs every SONARA write carries.

    The fingerprint encodes the track id, so two tracks never share one.
    """

    analyzed_at = core.analyzed_at
    return SonaraWrite(
        target=target,
        core=core,
        timeline=TimelineOutput(
            payload={
                "beats": [],
                "onsets": [],
                "chord_events": [],
                "downbeats": [],
                "energy_curve": [0.5],
                "energy_curve_hop_seconds": 0.5,
                "loudness_curve": [-10.0],
                "segments": [{"start_sec": 0.0, "end_sec": 1.0, "energy": 0.5}],
                "tempo_curve": [],
            },
            sample_rate_hz=22_050,
            hop_length=512,
            analyzed_at=analyzed_at,
        ),
        embedding=EmbeddingOutput(
            family="sonara",
            vector=np.full(SONARA_EMBEDDING_DIM, 0.5, dtype="<f4"),
            analyzed_at=analyzed_at,
        ),
        fingerprint=FingerprintOutput(
            value=base64.b64encode(struct.pack("<I", target.track_id)).decode("ascii"),
            version=1,
            analyzed_at=analyzed_at,
        ),
    )

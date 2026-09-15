from __future__ import annotations

import base64
import struct

import numpy as np

from dj_track_similarity.analysis_models import (
    SONARA_EMBEDDING_DIM,
    AnalysisTarget,
    EmbeddingOutput,
    FingerprintOutput,
    SonaraWrite,
    TimelineOutput,
)
from dj_track_similarity.db.ddl import SonaraRow


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

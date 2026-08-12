"""Source collection that preserves per-provider failures."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .models import SourceResult, TrackInput


class MetadataSource(Protocol):
    name: str

    def fetch(self, track: TrackInput) -> SourceResult: ...


def collect_source_results(track: TrackInput, sources: Iterable[MetadataSource]) -> tuple[SourceResult, ...]:
    """Fetch every source and turn source-local faults into reportable results."""

    results: list[SourceResult] = []
    for source in sources:
        try:
            results.append(source.fetch(track))
        except Exception as error:
            results.append(SourceResult(name=source.name, status="error", error=str(error)))
    return tuple(results)

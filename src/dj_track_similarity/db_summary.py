"""Library summary repository export.

The implementation lives with the rest of the v7 read model so every summary
uses the same active-contract and cross-file identity rules.
"""

from __future__ import annotations

from .db_library_queries import LibraryQueryRepository


class SummaryRepository(LibraryQueryRepository):
    """Composition name used by :class:`LibraryDatabase`."""

__all__ = ["SummaryRepository"]

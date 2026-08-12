"""Library summary repository export."""

from __future__ import annotations

from .db_library_queries import LibraryQueryRepository


class SummaryRepository(LibraryQueryRepository):
    """Composition name used by :class:`LibraryDatabase`."""


__all__ = ["SummaryRepository"]

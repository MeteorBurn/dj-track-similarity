"""Library summary repository export.

The implementation lives with the rest of the read model so every summary
uses the same structural and cross-file identity rules.
"""

from __future__ import annotations

from contextlib import closing

from .db_library_queries import (
    ANALYSIS_COUNT_SETTING_PREFIX,
    _ANALYSIS_COUNT_FIELDS,
    LibraryQueryRepository,
)
from .db_tracks import utc_now_text


_LEGACY_ANALYSIS_COUNTS_SETTING_KEY = "analysis.counts"


class SummaryRepository(LibraryQueryRepository):
    """Composition name used by :class:`LibraryDatabase`."""

    def refresh_analysis_counts(self) -> None:
        """Persist the current successful analysis coverage in Core settings."""

        summary = self.library_summary()
        counts = {
            field: (
                summary.maest_analysis
                if field == "maest"
                else getattr(summary, field)
            )
            for field in _ANALYSIS_COUNT_FIELDS
        }
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    timestamp = utc_now_text()
                    connection.executemany(
                        """
                        INSERT INTO library_settings(
                            setting_key,
                            setting_value,
                            updated_at
                        )
                        VALUES (?, ?, ?)
                        ON CONFLICT(setting_key) DO UPDATE SET
                            setting_value = excluded.setting_value,
                            updated_at = excluded.updated_at
                        """,
                        (
                            (
                                f"{ANALYSIS_COUNT_SETTING_PREFIX}{field}",
                                str(value),
                                timestamp,
                            )
                            for field, value in counts.items()
                        ),
                    )
                    connection.execute(
                        "DELETE FROM library_settings WHERE setting_key = ?",
                        (_LEGACY_ANALYSIS_COUNTS_SETTING_KEY,),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise


__all__ = ["SummaryRepository"]

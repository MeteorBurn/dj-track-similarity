from __future__ import annotations

from typing import Iterable

class SummaryRepository:
    def library_summary(self, classifier_keys: Iterable[str] | None = None) -> dict[str, int]:
        cleaned_classifier_keys = sorted({key.strip() for key in (classifier_keys or []) if key.strip()})
        with self.connect() as connection:
            tracks = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
            sonara = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_present_sonara_flag
                    WHERE has_sonara_analysis = 1
                      AND sonara_analysis_is_current(metadata_json) = 1
                    """
                ).fetchone()[0]
            )
            maest = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_present_maest_embedding_flag
                    WHERE has_maest_embedding = 1
                    """
                ).fetchone()[0]
            )
            mert = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_present_mert_embedding_flag
                    WHERE has_mert_embedding = 1
                    """
                ).fetchone()[0]
            )
            muq = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_present_muq_embedding_flag
                    WHERE has_muq_embedding = 1
                    """
                ).fetchone()[0]
            )
            clap = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_present_clap_embedding_flag
                    WHERE has_clap_embedding = 1
                    """
                ).fetchone()[0]
            )
            liked = int(connection.execute("SELECT COUNT(*) FROM track_likes").fetchone()[0])
            classifiers = 0
            if cleaned_classifier_keys:
                placeholders = ", ".join("?" for _ in cleaned_classifier_keys)
                classifiers = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT t.id
                            FROM tracks t
                            JOIN track_classifier_scores s ON s.track_id = t.id
                            WHERE s.classifier IN ({placeholders})
                            GROUP BY t.id
                            HAVING COUNT(DISTINCT s.classifier) = ?
                        )
                        """,
                        (*cleaned_classifier_keys, len(cleaned_classifier_keys)),
                    ).fetchone()[0]
                )
        return {
            "tracks": tracks,
            "sonara": sonara,
            "maest": maest,
            "mert": mert,
            "muq": muq,
            "clap": clap,
            "liked": liked,
            "classifiers": classifiers,
        }

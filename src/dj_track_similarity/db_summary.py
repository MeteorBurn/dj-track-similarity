from __future__ import annotations

from typing import Iterable

from .db_repository_utils import MAEST_EMBEDDING_KEY


class SummaryRepository:
    def library_summary(self, classifier_keys: Iterable[str] | None = None) -> dict[str, int]:
        cleaned_classifier_keys = sorted({key.strip() for key in (classifier_keys or []) if key.strip()})
        with self.connect() as connection:
            tracks = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
            sonara = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_sonara_present
                    WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL
                    """
                ).fetchone()[0]
            )
            maest = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?",
                    (MAEST_EMBEDDING_KEY,),
                ).fetchone()[0]
            )
            mert = int(
                connection.execute("SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?", ("mert",)).fetchone()[0]
            )
            clap = int(
                connection.execute("SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?", ("clap",)).fetchone()[0]
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
            "clap": clap,
            "liked": liked,
            "classifiers": classifiers,
        }

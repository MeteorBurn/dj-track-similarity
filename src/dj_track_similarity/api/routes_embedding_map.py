from __future__ import annotations

import numpy as np
from fastapi import FastAPI, HTTPException

from .schemas import EmbeddingMapRequest, EmbeddingMapResponse
from .state import AppDatabaseState, DatabaseBusy
from ..analysis_models import current_embedding_spec
from ..search.embedding_explorer import explore_embeddings


def register_embedding_map_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.post("/api/library/embedding-map", response_model=EmbeddingMapResponse)
    def embedding_map(request: EmbeddingMapRequest) -> dict[str, object]:
        database, generation = state.capture_db()
        if request.catalog_uuid != database.catalog_uuid:
            raise HTTPException(status_code=409, detail="The selected library has changed")
        try:
            output = database.active_analysis_output(request.analysis_family, "embedding")
            if output is None:
                raise HTTPException(status_code=409, detail="MERT-v2 embeddings are unavailable")
            rows = database.load_analysis_vectors(output)
            track_ids = [row.target.track_id for row in rows]
            matrix = (
                np.stack([row.vector for row in rows])
                if rows
                else np.empty((0, current_embedding_spec(request.analysis_family).dimension), dtype=np.float32)
            )
            result = explore_embeddings(track_ids, matrix, n_clusters=request.cluster_count)
            with state.captured_db(database, generation):
                current_rows = database.load_analysis_vectors(output)
                if (
                    tuple(row.target for row in current_rows) != tuple(row.target for row in rows)
                    or any(not np.array_equal(before.vector, after.vector) for before, after in zip(rows, current_rows))
                ):
                    raise HTTPException(status_code=409, detail="Embeddings changed while building the map")
                tracks = database.get_track_summaries(track_ids)
                for row, track in zip(rows, tracks, strict=True):
                    if (track.catalog_uuid, track.track_uuid) != (row.target.catalog_uuid, row.target.track_uuid):
                        raise HTTPException(status_code=409, detail="A map track is no longer current")
                return {
                    "catalog_uuid": database.catalog_uuid,
                    "analysis_family": request.analysis_family,
                    "eligible_count": len(rows),
                    "requested_cluster_count": request.cluster_count,
                    "cluster_count": len(result.representative_track_ids),
                    "projection": {
                        "method": "pca",
                        "explained_variance_ratio": result.explained_variance_ratio,
                    },
                    "clusters": [
                        {
                            "id": cluster_id,
                            "count": int(np.count_nonzero(result.cluster_ids == cluster_id)),
                            "representative_track_id": representative,
                        }
                        for cluster_id, representative in enumerate(result.representative_track_ids)
                    ],
                    "points": [
                        {"track": track, "x": float(point[0]), "y": float(point[1]), "cluster": int(cluster)}
                        for track, point, cluster in zip(tracks, result.coordinates, result.cluster_ids, strict=True)
                    ],
                }
        except DatabaseBusy as error:
            raise HTTPException(status_code=409, detail="The selected library changed or is busy") from error
        except (KeyError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

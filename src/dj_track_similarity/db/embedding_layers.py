"""Per-layer embedding checks; startup never changes existing schemas."""

from __future__ import annotations

import re
import sqlite3

from ..analysis_models import EMBEDDING_LAYERS
from .ddl import LAYERED_EMBEDDINGS_DDL

_MIGRATION_SCRIPT = "scripts/migrate_layered_embeddings.py"


def validate_embedding_layer(family: str, layer: int | None) -> int | None:
    """Resolve the stored layer to read or write for *family*.

    ``None`` selects the default layer of a layered family and stays ``None``
    for a family that stores one vector per track.
    """

    layers = EMBEDDING_LAYERS.get(family)
    if layers is None:
        if layer is not None:
            raise ValueError(f"Layer selection is not supported for {family}")
        return None
    if layer is None:
        return layers.default
    if type(layer) is not int or not 1 <= layer <= layers.count:
        raise ValueError(f"{family} layer must be an integer from 1 to {layers.count}")
    return layer


def _compact_sql(sql: str) -> str:
    return re.sub(r"\s+", "", sql).rstrip(";").lower()


def embedding_layers_capability(connection: sqlite3.Connection, family: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = ?",
        (f"{family}_embeddings",),
    ).fetchone()
    if row is None:
        return "absent"
    expected = _compact_sql(LAYERED_EMBEDDINGS_DDL[family])
    return "ready" if _compact_sql(str(row[0])) == expected else "incompatible"


def require_embedding_layers(connection: sqlite3.Connection, family: str) -> None:
    state = embedding_layers_capability(connection, family)
    if state != "ready":
        raise RuntimeError(
            f"{family} layer schema is {state}; migrate this database with "
            f"{_MIGRATION_SCRIPT} or use a database created with all-layer storage"
        )

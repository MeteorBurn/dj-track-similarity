"""MERT-v2 layer capability checks; startup never changes existing schemas."""

from __future__ import annotations

import re
import sqlite3

from .ddl import MERT_V2_EMBEDDINGS_DDL


def validate_mert_v2_layer(family: str, layer: int) -> int:
    if type(layer) is not int or not 1 <= layer <= 24:
        raise ValueError("MERT-v2 layer must be an integer from 1 to 24")
    if family != "mert_v2" and layer != 24:
        raise ValueError("Layer selection is only supported for MERT-v2")
    return layer


def mert_v2_layers_capability(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type = 'table' "
        "AND name = 'mert_v2_embeddings'"
    ).fetchone()
    if row is None:
        return "absent"
    actual = re.sub(r"\s+", "", str(row[0])).rstrip(";").lower()
    expected = re.sub(r"\s+", "", MERT_V2_EMBEDDINGS_DDL).rstrip(";").lower()
    return "ready" if actual == expected else "incompatible"


def require_mert_v2_layers(connection: sqlite3.Connection) -> None:
    state = mert_v2_layers_capability(connection)
    if state != "ready":
        raise RuntimeError(
            f"MERT-v2 layer schema is {state}; use a database created with all-layer storage"
        )

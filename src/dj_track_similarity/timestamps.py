"""The UTC timestamp formats this project writes.

Two formats are in use and they are not interchangeable: rows and payloads
that record when something happened keep microseconds, while the evaluation
layer stamps whole seconds. Both used to be private functions named
_utc_timestamp in five modules, so one name produced two different strings
depending on which file you happened to be reading.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Microsecond precision, as stored in library and sidecar rows."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_timestamp_seconds() -> str:
    """Whole seconds, as written by the evaluation layer."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

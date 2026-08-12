"""Small dependency-free JSON client for official provider endpoints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> Mapping[str, object]:
    query = urlencode(params)
    request = Request(f"{url}?{query}" if query else url, headers=dict(headers))
    with urlopen(request, timeout=20) as response:  # noqa: S310 - only provider-owned URLs are passed by adapters.
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("provider returned a non-object JSON response")
    return parsed

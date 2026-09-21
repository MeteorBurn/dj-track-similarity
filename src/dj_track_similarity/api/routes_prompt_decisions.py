"""App-wide PROMPT A/B decisions: which text model hears each label better.

One JSON file in the repository's local ``database/`` folder serves every
library, so switching the library keeps the decisions.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Response
from fastapi import Path as PathParameter

from .schemas import (
    PROMPT_PRESET_KEY_PATTERN,
    PromptDecisionRequest,
    PromptDecisionResponse,
    PromptDecisionsResponse,
)


LOGGER = logging.getLogger(__name__)

PROMPT_DECISIONS_PATH = Path(__file__).resolve().parents[3] / "database" / "prompt_decisions.json"

_WRITE_LOCK = threading.Lock()

PresetKey = Annotated[str, PathParameter(pattern=PROMPT_PRESET_KEY_PATTERN)]


def _read_decisions() -> PromptDecisionsResponse:
    path = PROMPT_DECISIONS_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PromptDecisionsResponse()
    try:
        return PromptDecisionsResponse.model_validate_json(text)
    except ValueError as error:
        # Never rewrite a file we cannot read: it holds the owner's decisions.
        LOGGER.error("Prompt decisions file is corrupt path=%s error=%s", path, error)
        raise HTTPException(
            status_code=500,
            detail=f"Prompt decisions file is corrupt and was left untouched: {path}",
        ) from error


def _write_decisions(decisions: PromptDecisionsResponse) -> None:
    path = PROMPT_DECISIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with staged.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(decisions.model_dump(), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def register_prompt_decision_routes(app: FastAPI) -> None:
    @app.get("/api/search/text/decisions", response_model=PromptDecisionsResponse)
    def prompt_decisions():
        return _read_decisions()

    # A preset key contains "/", so it takes the rest of the path.
    @app.put(
        "/api/search/text/decisions/{preset_key:path}",
        response_model=PromptDecisionResponse,
    )
    def save_prompt_decision(preset_key: PresetKey, request: PromptDecisionRequest):
        entry = PromptDecisionResponse(
            model=request.model,
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with _WRITE_LOCK:
            decisions = _read_decisions()
            decisions.decisions[preset_key] = entry
            _write_decisions(decisions)
        return entry

    @app.delete("/api/search/text/decisions/{preset_key:path}", status_code=204)
    def delete_prompt_decision(preset_key: PresetKey):
        with _WRITE_LOCK:
            decisions = _read_decisions()
            if decisions.decisions.pop(preset_key, None) is not None:
                _write_decisions(decisions)
        return Response(status_code=204)

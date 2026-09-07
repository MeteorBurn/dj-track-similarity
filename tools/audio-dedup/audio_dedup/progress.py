from __future__ import annotations

from . import models as models_module


def _report_progress(callback: models_module.ProgressCallback | None, processed: int, total: int, message: str) -> None:
    if callback is not None:
        callback(max(0, int(processed)), max(0, int(total)), message)


def _raise_if_cancelled(should_cancel: models_module.CancelCheck | None) -> None:
    if should_cancel is not None and should_cancel():
        raise models_module.AudioDedupCancelled("Audio dedup job cancelled")

from __future__ import annotations

import threading
import time

import typer


def _run_cli_job_with_progress(manager: object, job_id: str, *, label: str, poll_interval: float = 0.5):
    typer.echo(f"Starting {label} analysis")
    result = None
    errors: list[BaseException] = []

    def run() -> None:
        nonlocal result
        try:
            result = manager.run_job(job_id)  # type: ignore[attr-defined]
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    previous_width = 0
    while thread.is_alive():
        previous_width = _write_cli_progress(manager.get(job_id), previous_width)  # type: ignore[attr-defined]
        thread.join(poll_interval)
    thread.join()
    if errors:
        raise errors[0]
    status = result or manager.get(job_id)  # type: ignore[attr-defined]
    _write_cli_progress(status, previous_width)
    typer.echo()
    return status


def _write_cli_progress(status: object, previous_width: int = 0) -> int:
    line = _format_cli_progress(status)
    padding = " " * max(0, previous_width - len(line))
    typer.echo(f"\r{line}{padding}", nl=False)
    return len(line)


def _format_cli_progress(status: object) -> str:
    total = int(getattr(status, "total", 0) or 0)
    processed = int(getattr(status, "processed", 0) or 0)
    analyzed = int(getattr(status, "analyzed", 0) or 0)
    failed = int(getattr(status, "failed", 0) or 0)
    progress = (processed / total) if total else (1.0 if getattr(status, "state", "") == "completed" else 0.0)
    progress = min(1.0, max(0.0, progress))
    bar_width = 24
    filled = int(round(progress * bar_width))
    bar = "#" * filled + "-" * (bar_width - filled)
    speed = _status_tracks_per_second(status, processed)
    eta = _format_eta_seconds(_eta_seconds(total, processed, speed))
    total_text = str(total) if total else "?"
    return (
        f"[{bar}] {progress * 100:5.1f}% "
        f"processed={processed}/{total_text} analyzed={analyzed} failed={failed} "
        f"{speed:.2f} tracks/s eta={eta}"
    )


def _status_tracks_per_second(status: object, processed: int) -> float:
    avg_seconds = getattr(status, "avg_seconds_per_track", None)
    if avg_seconds:
        return 1.0 / float(avg_seconds)
    started_at = getattr(status, "started_at", None)
    if started_at and processed:
        elapsed = max(0.001, time.time() - float(started_at))
        return processed / elapsed
    return 0.0


def _eta_seconds(total: int, processed: int, speed: float) -> float | None:
    if total <= 0 or processed >= total:
        return 0.0
    if speed <= 0:
        return None
    return max(0.0, (total - processed) / speed)


def _format_eta_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    remaining = int(round(seconds))
    hours, remainder = divmod(remaining, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"

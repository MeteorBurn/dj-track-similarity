from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from . import models as models_module
from . import report_payload as report_payload_module
from . import xlsx_report as xlsx_report_module


def write_report_bundle(
    *,
    out_dir: Path,
    run_result: models_module.RepairRunResult,
    sources: list[str],
    folders: list[Path],
    dbs: list[Path],
    logs: list[Path],
    explicit_paths: list[Path],
    reason_filters: list[str],
) -> models_module.ReportResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    generated_at = now.isoformat(timespec="seconds")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    json_path = _unique_report_path(out_dir / f"audio_doctor_report_{stamp}.json")
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    payload = report_payload_module.build_report_payload(
        run_result,
        generated_at=generated_at,
        sources=sources,
        folders=folders,
        dbs=dbs,
        logs=logs,
        explicit_paths=explicit_paths,
        reason_filters=reason_filters,
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    xlsx_report_module.write_xlsx_report(xlsx_path, payload)
    write_text_log(log_path, payload)
    return models_module.ReportResult(json_path=json_path, xlsx_path=xlsx_path, log_path=log_path, payload=payload)


def write_text_log(path: Path, payload: dict[str, object]) -> None:
    status_counts = payload.get("status_counts", {})
    reason_counts = payload.get("reason_counts", {})
    state = payload.get("state", {})
    assert isinstance(status_counts, dict)
    assert isinstance(reason_counts, dict)
    assert isinstance(state, dict)
    lines = [
        f"audio_doctor {payload['mode']} run",
        f"generated_at={payload['generated_at']}",
        f"total_collected={payload['total_collected']}",
        f"processed_count={payload['processed_count']}",
        f"state_result_count={payload.get('state_result_count', 0)}",
        f"result_count={payload['result_count']}",
        f"missing_db_files={payload['missing_db_files']}",
        f"state_enabled={state.get('enabled', False)}",
        f"state_file={state.get('path') or ''}",
        f"skipped_from_state={state.get('skipped_from_state', 0)}",
        f"skipped_by_reason={state.get('skipped_by_reason', 0)}",
        f"state_included_in_report={state.get('included_in_report', 0)}",
    ]
    lines.extend(f"status_count_{status}={count}" for status, count in status_counts.items())
    lines.extend(f"reason_count_{reason}={count}" for reason, count in reason_counts.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unique_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique report path for {path}")

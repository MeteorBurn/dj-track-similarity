from __future__ import annotations

import json
from pathlib import Path

from . import models as models_module
from . import xlsx_report as xlsx_report_module


def write_text_log(path: Path, payload: dict[str, object], *, apply_result: models_module.ApplyResult | None = None) -> None:
    lines = [
        "audio_dedup apply run" if apply_result is not None else "audio_dedup report-only run",
        f"generated_at={payload['generated_at']}",
        f"database={payload.get('database_path') or ''}",
        f"search_mode={payload.get('search_mode', '')}",
        f"database_track_count={payload.get('database_track_count', payload['track_count'])}",
        f"scoped_track_count={payload.get('scoped_track_count', payload['track_count'])}",
        f"group_count={payload['group_count']}",
        "suspected_transcodes="
        + str(
            payload.get("spectral_analysis", {}).get("suspected_transcode_count", 0)
            if isinstance(payload.get("spectral_analysis"), dict)
            else 0
        ),
    ]
    if apply_result is None:
        lines.append("no files deleted; no databases mutated")
    else:
        lines.extend(
            [
                f"deleted_track_count={len(apply_result.deleted_track_ids)}",
                f"skipped_count={len(apply_result.skipped)}",
                f"failed_count={len(apply_result.failed)}",
                f"rhythm_lab_deleted_rows={apply_result.rhythm_lab_deleted_rows}",
            ]
        )
        if apply_result.deleted_paths:
            lines.append("deleted_files:")
            lines.extend(f"deleted_file={path}" for path in apply_result.deleted_paths)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report_files(result: models_module.ReportResult, *, apply_result: models_module.ApplyResult | None = None) -> None:
    result.json_path.write_text(
        json.dumps(result.payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    xlsx_report_module.write_xlsx_report(result.xlsx_path, result.payload)
    write_text_log(result.log_path, result.payload, apply_result=apply_result)


def apply_result_payload(result: models_module.ApplyResult) -> dict[str, object]:
    return {
        "deleted_track_ids": list(result.deleted_track_ids),
        "deleted_paths": list(result.deleted_paths),
        "skipped": list(result.skipped),
        "failed": list(result.failed),
        "rhythm_lab_deleted_rows": result.rhythm_lab_deleted_rows,
    }


def _unique_report_dir(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique report directory for {path}")

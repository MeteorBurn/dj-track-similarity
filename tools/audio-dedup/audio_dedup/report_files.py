from __future__ import annotations

import json
from pathlib import Path

from . import config as config_module
from . import models as models_module
from . import rhythm_lab as rhythm_lab_module
from . import xlsx_report as xlsx_report_module


def write_text_log(path: Path, payload: dict[str, object], *, apply_result: models_module.ApplyResult | None = None) -> None:
    rhythm_lab = payload.get("rhythm_lab", {})
    lines = [
        "audio_dedup apply run" if apply_result is not None else "audio_dedup report-only run",
        f"generated_at={payload['generated_at']}",
        f"database={payload.get('database_path') or ''}",
        f"root={payload['root']}",
        f"search_mode={payload.get('search_mode', '')}",
        f"preset={payload['preset']}",
        "sources=" + ",".join(
            str(item)
            for item in payload.get(
                "sources",
                list(config_module.SUPPORTED_EMBEDDINGS),
            )
        ),
        "weights=" + ",".join(
            f"{key}={value}"
            for key, value in dict(
                payload.get("weights", config_module.DEFAULT_SOURCE_WEIGHTS)
            ).items()
        ),
        f"min_score={payload['min_score']}",
        f"min_similarity={payload['min_similarity']}",
        "min_similarity_semantics=audio-to-audio content gate over enabled MERT/MAEST/MuQ/CLAP embeddings; not CLAP text-search score",
        "muq_similarity_semantics=audio-to-audio cosine over structurally valid current-generation stored MuQ embeddings",
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
    if isinstance(rhythm_lab, dict):
        lines.extend(
            [
                f"rhythm_lab_summary={rhythm_lab_module.rhythm_lab_summary_text(rhythm_lab)}",
                f"rhythm_lab_database={rhythm_lab.get('database_path', '')}",
                f"rhythm_lab_database_exists={rhythm_lab.get('database_exists', False)}",
                f"rhythm_lab_affected_track_count={rhythm_lab.get('affected_track_count', 0)}",
                f"rhythm_lab_affected_row_count={rhythm_lab.get('affected_row_count', 0)}",
            ]
        )
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


def _unique_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique report path for {path}")

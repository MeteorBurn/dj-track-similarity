from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import file_repair as file_repair_module
from . import models as models_module
from . import result_formatting as result_formatting_module
from . import run_state as run_state_module


def run_paths(
    paths: list[Path],
    *,
    all_paths: list[Path],
    skipped_from_state: int,
    reporter: result_formatting_module.RunReporter,
    use_color: bool,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    state: dict[str, object] | None,
    state_path: Path | None,
    state_mode: bool,
    summary_only: bool,
    workers: int,
    skipped_by_reason: int,
    missing_db_files: int,
    skipped_state_results: list[models_module.StateRepairResult],
    progress_callback: Callable[[int, int, Path, models_module.FileRepairResult], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> models_module.RepairRunResult:
    if state_mode:
        reporter.line(f"Total tracks: {len(all_paths)}")
        if missing_db_files:
            reporter.line(f"Missing DB files: {missing_db_files}")
        if state_path is not None:
            reporter.line(f"State file: {state_path}")
        reporter.line(f"Already checked from state: {skipped_from_state}")
        if skipped_by_reason:
            reporter.line(f"Skipped by reason filter: {skipped_by_reason}")
        reporter.line(f"Pending tracks: {len(paths)}")
    else:
        reporter.line(f"Total tracks: {len(paths)}")

    results: list[models_module.FileRepairResult] = []
    total = len(paths)
    indexed_results = process_paths(
        paths,
        apply_changes=apply_changes,
        backup_dir=backup_dir,
        no_backup=no_backup,
        keep_id3=keep_id3,
        workers=workers,
        should_cancel=should_cancel,
    )
    for index, path, result in indexed_results:
        if should_cancel is not None and should_cancel():
            raise models_module.AudioDoctorCancelled("Audio Doctor job cancelled")
        results.append(result)
        if state is not None and state_path is not None:
            run_state_module.update_state_entry(state, path, result, apply_changes=apply_changes)
            run_state_module.save_state(state_path, state)
        if progress_callback is not None:
            progress_callback(index, total, path, result)
        if not summary_only:
            reporter.line(
                result_formatting_module.format_result(result, dry_run=not apply_changes, index=index, total=total, color=use_color),
                log_text=result_formatting_module.format_result(result, dry_run=not apply_changes, index=index, total=total, color=False),
            )

    failed = sum(1 for result in results if result.status == "failed")
    changed = sum(1 for result in results if result.status == "repaired")
    repairable = sum(1 for result in results if result.status == "repairable")
    notice = sum(1 for result in results if result.status == "notice")
    suspicious = sum(1 for result in results if result.status == "suspicious")
    tag_error = sum(1 for result in results if result.status == "tag-error")
    ok = sum(1 for result in results if result.status == "ok")
    problem_counts = result_formatting_module.summarize_problem_types(results)
    summary = (
        "Summary: "
        f"total={len(results)} repaired={changed} repairable={repairable} "
        f"notice={notice} ok={ok} suspicious={suspicious} "
        f"tag-error={tag_error} failed={failed}"
    )
    if state_mode:
        summary += f" skipped-state={skipped_from_state}"
        if skipped_by_reason:
            summary += f" skipped-reason={skipped_by_reason}"
    reporter.line(summary)
    if problem_counts:
        reporter.line("Problem summary:")
        for problem, count in problem_counts:
            reporter.line(f"{problem}: {count}")
    return models_module.RepairRunResult(
        exit_code=1 if failed else 0,
        results=results,
        skipped_state_results=skipped_state_results,
        total_collected=len(all_paths),
        skipped_from_state=skipped_from_state,
        skipped_by_reason=skipped_by_reason,
        missing_db_files=missing_db_files,
        state_path=state_path,
        state_mode=state_mode,
        apply_changes=apply_changes,
        keep_id3=keep_id3,
        backup_dir=backup_dir,
        no_backup=no_backup,
        workers=workers,
    )


def process_paths(
    paths: list[Path],
    *,
    apply_changes: bool,
    backup_dir: Path | None,
    no_backup: bool,
    keep_id3: str,
    workers: int,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[tuple[int, Path, models_module.FileRepairResult]]:
    worker_count = max(1, workers)
    if apply_changes or worker_count == 1 or len(paths) <= 1:
        for index, path in enumerate(paths, start=1):
            if should_cancel is not None and should_cancel():
                raise models_module.AudioDoctorCancelled("Audio Doctor job cancelled")
            yield (
                index,
                path,
                file_repair_module.repair_file(
                    path,
                    apply_changes=apply_changes,
                    backup_dir=backup_dir,
                    no_backup=no_backup,
                    keep_id3=keep_id3,
                ),
            )
        return

    def check_one(item: tuple[int, Path]) -> tuple[int, Path, models_module.FileRepairResult]:
        index, path = item
        if should_cancel is not None and should_cancel():
            raise models_module.AudioDoctorCancelled("Audio Doctor job cancelled")
        return (
            index,
            path,
            file_repair_module.repair_file(
                path,
                apply_changes=False,
                backup_dir=backup_dir,
                no_backup=no_backup,
                keep_id3=keep_id3,
            ),
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        yield from executor.map(check_one, enumerate(paths, start=1))

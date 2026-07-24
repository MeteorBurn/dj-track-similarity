# Audio Doctor Notes

Standalone metadata / container repair helper. Independent safety domain — see root `AGENTS.md` for the write-path invariant and repo-wide rules.

## Boundaries

- Not a Python package: no `pyproject.toml`, no `setup.py`, no per-tool test config. Script tree.
- CLI entry: `tools/audio-doctor/audio_doctor_cli.py` → `audio_doctor.core.main()`.
- Package: `tools/audio-doctor/audio_doctor/` with `core.py`, `cli.py`, `inputs.py`, `inspection.py`, `models.py`, `repair.py`, `reports.py`, `state.py`.
- API integration lives in `src/dj_track_similarity/api_routes_audio_doctor.py` and `audio_doctor_jobs.py`; the job manager enforces the confirmation phrase and prior dry-run state.

## Dry-Run Contract (NEVER weaken)

- Default mode is dry-run. It reads files only; it writes reports + state under `tools/audio-doctor/data/reports/` and `tools/audio-doctor/data/state/`.
- `--apply` is blocked unless a prior dry-run recorded state for the exact target files.
- `--apply` only rewrites cases previously classified `REPAIRABLE`. It refuses unknown or non-repairable findings.
- Apply mode default: backups on. Every repair creates a full-file backup under `tools/audio-doctor/data/backups/`, verifies the repaired file, and restores the backup on verification failure.
- UI/API apply also requires the exact literal string `APPLY REPAIR` (`audio_doctor_jobs.py::APPLY_CONFIRMATION`). Do not weaken this to a boolean or a substring match.
- No-backup mode exists (`--no-backup`) but is opt-in and must not become the default.

## What This Tool Must Not Do

- Never mutate audio outside `--apply`, and never touch files not previously classified as repairable.
- Resolve every apply target and backup path before writing; keep all report/state identity checks bound to the same file observed during dry-run.
- Never modify library SQLite rows — Audio Doctor only reads `tracks.file_path` when `--db` is passed; repair operates on the filesystem, not on stored metadata.
- Never delete files. Repair may rewrite; deletion is Audio Dedup's territory.
- Never chain into Audio Dedup or classifier scoring.

## Local Files

- Reports, state, and backups all live under `tools/audio-doctor/data/`, gitignored except `.gitkeep`.
- Do not commit dry-run state, reports, or backup trees.

## Testing

- `python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=` (root pytest does not collect this).
- For API/job-manager changes also run `python -m pytest tests\test_api_audio_doctor.py --override-ini addopts=`.
- Tests use synthetic minimal WAV/AIFF containers built in the test file; no real audio library.

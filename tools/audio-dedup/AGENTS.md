# Audio Dedup Notes

Standalone duplicate-audio report and cleanup helper. Independent safety domain — see root `AGENTS.md`.

## Boundaries

- Not a Python package: no `pyproject.toml`, no per-tool test config. Script tree.
- CLI entry: `tools/audio-dedup/audio_dedup_cli.py` → `audio_dedup.core.main()`.
- Package: `tools/audio-dedup/audio_dedup/` (just `core.py` + `__init__.py`).
- API-side job manager: `src/dj_track_similarity/audio_dedup_jobs.py`.

## Report-First Contract (NEVER weaken)

- Default is report-only. It reads stored MERT/MAEST/CLAP/SONARA analysis + file metadata; it writes JSON, XLSX, and log files under `tools/audio-dedup/data/reports/`. No filesystem or DB mutations.
- `--apply` requires the exact literal `APPLY DELETE` (`audio_dedup_jobs.py:21`, `core.py:1346+`). Do not weaken to a boolean or a substring match.
- Apply mode only deletes files that:
  1. Were classified as safe duplicate candidates in the current run, AND
  2. Live inside the `--root` passed on this invocation.
- After a successful file delete, remove the corresponding SQLite row(s). Never delete DB rows for files you did not actually delete.
- Do not run apply mode as part of routine verification, testing, or dry-run rerun.

## What This Tool Must Not Do

- Never repair, retag, or transcode files. That is Audio Doctor's territory.
- Never touch files outside `--root`, even if they appear in the same duplicate cluster.
- Never delete without the exact `APPLY DELETE` string plus a fresh report identifying the target.
- Never invalidate or delete SONARA / MERT / MAEST / MuQ / CLAP data for surviving tracks.

## Local Files

- Reports live under `tools/audio-dedup/data/reports/`, gitignored except `.gitkeep`.

## Testing

- `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=` (root pytest does not collect this).
- Tests build synthetic SQLite sidecars + tiny audio in the test file; no real library.

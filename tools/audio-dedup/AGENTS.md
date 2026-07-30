# Audio Dedup Notes

Standalone duplicate-audio report and cleanup helper. Independent safety domain — see root `AGENTS.md`.

## Boundaries

- Not a Python package: no `pyproject.toml`, no per-tool test config. Script tree.
- CLI entry: `tools/audio-dedup/audio_dedup_cli.py` → `audio_dedup.core.main()`.
- Package: `tools/audio-dedup/audio_dedup/` (just `core.py` + `__init__.py`).
- API integration: `src/dj_track_similarity/api_routes_audio_dedup.py` + `audio_dedup_jobs.py`.

## Report-First Contract (NEVER weaken)

- Default is report-only. It reads stored MERT/MAEST/MuQ/CLAP/SONARA analysis + file metadata; it writes JSON, XLSX, and log files under `tools/audio-dedup/data/reports/`. No filesystem or DB mutations.
- `--apply` requires the exact literal `APPLY DELETE` (`audio_dedup_jobs.py::APPLY_CONFIRMATION`, `core.py::confirm_apply`). Do not weaken to a boolean or a substring match.
- Apply mode only deletes files that:
  1. Were classified as safe duplicate candidates in the current run, AND
  2. Live inside the `--root` passed on this invocation.
- After a successful file delete, remove the corresponding SQLite row(s). Never delete DB rows for files you did not actually delete.
- Do not run apply mode as part of routine verification, testing, or dry-run rerun.

## Embedding Sources

- `SUPPORTED_EMBEDDINGS = ("mert", "maest", "muq", "clap")`.
- Raw defaults are MERT `0.43`, MAEST `0.32`, MuQ `0.12`, and CLAP `0.04`. These are evidence weights, not calibrated probabilities.
- `sources` must be unique and non-empty. Custom `weights` must contain exactly the enabled sources, be finite/nonnegative, and include at least one positive value.
- Load valid available embeddings. Missing evidence stays missing; never
  substitute another family or a CLAP text-search score.
- Effective scoring normalizes over evidence available for the pair. Reports/status must preserve selected `sources`, effective `weights`, per-family similarities (including `muq_similarity`), and `blocked_reasons`.
- The exact legacy delete-safety profile is MERT/MAEST/CLAP with raw defaults `0.43/0.32/0.04`. Every non-legacy source/weight profile additionally requires positive MERT and MAEST weights plus independent MERT+MAEST corroboration at the threshold. MuQ or CLAP alone can never authorize deletion.

## What This Tool Must Not Do

- Never repair, retag, or transcode files. That is Audio Doctor's territory.
- Never touch files outside `--root`, even if they appear in the same duplicate cluster.
- Never delete without the exact `APPLY DELETE` string plus a fresh report identifying the target.
- Never invalidate or delete SONARA / MERT / MAEST / MuQ / CLAP data for surviving tracks.
- UI/CLI source controls may broaden report-only exploration, but backend delete-safety remains authoritative and must fail closed.

## Local Files

- Reports live under `tools/audio-dedup/data/reports/`, gitignored except `.gitkeep`.

## Testing

- `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=` (root pytest does not collect this).
- For API/job-manager changes also run `python -m pytest tests\test_api_audio_dedup.py tests\test_audio_dedup_runtime.py --override-ini addopts=`.
- Tests build synthetic SQLite sidecars + tiny audio in the test file; no real library.

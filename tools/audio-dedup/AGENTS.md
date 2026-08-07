# Audio Dedup Notes

Standalone duplicate-audio report and cleanup helper. Independent safety domain — see root `AGENTS.md`.

## Active Development

- The root evolution policy applies. Source families, weights, thresholds,
  report fields, CLI/API shapes, and package layout are current implementation,
  not permanent contracts.
- Change scoring and schemas through shared definitions and update reports,
  status, UI, tests, and docs together. Do not create compatibility branches or
  duplicated hard-coded profiles unless persisted/external data requires them.
- The deletion baseline applies unless the user explicitly requests a new risk
  model. Any redesign must keep target scope and user intent explicit, fail
  closed on insufficient evidence, and reconcile database rows only with
  filesystem actions that actually succeeded.

## Current Boundaries

- Not a Python package: no `pyproject.toml`, no per-tool test config. Script tree.
- CLI entry: `tools/audio-dedup/audio_dedup_cli.py` → `audio_dedup.core.main()`.
- Package: `tools/audio-dedup/audio_dedup/` (just `core.py` + `__init__.py`).
- API integration: `src/dj_track_similarity/api_routes_audio_dedup.py` + `audio_dedup_jobs.py`.

## Current Report-First Safety Baseline

- Default is report-only. It reads stored MERT/MAEST/MuQ/CLAP/SONARA analysis + file metadata; it writes JSON, XLSX, and log files under `tools/audio-dedup/data/reports/`. No filesystem or DB mutations.
- `--apply` currently uses the exact confirmation owned by
  `audio_dedup_jobs.py::APPLY_CONFIRMATION` and `core.py::confirm_apply`. Avoid
  additional literal copies. A requested confirmation redesign must remain
  explicit and update every entry point together.
- Apply mode only deletes files that:
  1. Were classified as safe duplicate candidates in the current run, AND
  2. Live inside the `--root` passed on this invocation.
- After a successful file delete, remove the corresponding SQLite row(s). Never delete DB rows for files you did not actually delete.
- Do not run apply mode as part of routine verification, testing, or dry-run rerun.

## Current Embedding Sources

- `SUPPORTED_EMBEDDINGS` and the default evidence weights live in the tool's
  executable source. Treat both as an extensible current profile, not a frozen
  list; these weights are not calibrated probabilities.
- `sources` must be unique and non-empty. Custom `weights` must contain exactly the enabled sources, be finite/nonnegative, and include at least one positive value.
- Load valid available embeddings. Missing evidence stays missing; never
  substitute another family or a CLAP text-search score.
- Effective scoring normalizes over evidence available for the pair. Reports/status must preserve selected `sources`, effective `weights`, per-family similarities (including `muq_similarity`), and `blocked_reasons`.
- The active delete-safety profile and its independent corroboration rules are
  authoritative in executable source and focused tests. They may evolve only
  as a deliberate safety-policy change; report-only source flexibility must not
  accidentally broaden deletion eligibility.

## Current Responsibility Boundary

Unless a task explicitly redesigns Audio Dedup's responsibility:

- Never repair, retag, or transcode files. That is Audio Doctor's territory.
- Never touch files outside `--root`, even if they appear in the same duplicate cluster.
- Never delete without the active explicit confirmation from its owning source
  plus a fresh report identifying the target.
- Never invalidate or delete SONARA / MERT / MAEST / MuQ / CLAP data for surviving tracks.
- UI/CLI source controls may broaden report-only exploration, but backend delete-safety remains authoritative and must fail closed.

## Local Files

- Reports live under `tools/audio-dedup/data/reports/`, gitignored except `.gitkeep`.

## Testing

- `python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=` (root pytest does not collect this).
- For API/job-manager changes also run `python -m pytest tests\test_api_audio_dedup.py tests\test_audio_dedup_runtime.py --override-ini addopts=`.
- Tests build synthetic SQLite sidecars + tiny audio in the test file; no real library.

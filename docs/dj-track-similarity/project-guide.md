# dj-track-similarity Documentation

This is the documentation index for `dj-track-similarity`. Start here when you
are not sure which page you need. The short project introduction remains in the
[repository README](https://github.com/MeteorBurn/dj-track-similarity/blob/main/README.md);
the pages below hold the operational user and developer reference.

For a first local run, start with [Installation](install.md), read the
[Overview](overview.md), then use [CLI Reference](cli.md) to scan a folder and
start the server. If you already have a library database, use
[Analysis Families](analysis.md) to choose which analysis pass to run next, then
use [Search and Tag Writing](search-and-tags.md) for day-to-day DJ workflow
guidance.

## Main Project

- [Installation](install.md): requirements, dependency groups, the verified
  Windows CUDA stack, FFmpeg setup, and how to verify the install.
- [Overview](overview.md): project purpose, core features, safety model, and
  supported audio files.
- [Architecture and Runtime](architecture.md): backend/frontend map,
  dependencies, CUDA/FFmpeg notes, and logging. Use this when setup, GPU,
  audio-decoding, or server startup behavior is unclear.
- [Database and Stored Data](database.md): SQLite schema, metadata, embeddings,
  and classifier-score storage. Use this when checking what the app saves and
  what remains read-only.
- [Analysis Models](models.md): what each model (Sonara, MAEST, MERT, CLAP) is,
  what it produces, how the app uses it, and which install extras it needs.
- [Analysis Families](analysis.md): Sonara, MAEST, MERT, CLAP, and promoted
  classifier scoring. Use this before spending time on analysis jobs so you can
  pick the useful feature family first.
- [Search and Tag Writing](search-and-tags.md): SONARA/MERT/CLAP/CLASS
  workflows and standard genre writes. Use this for finding compatible tracks,
  filtering by classifier scores, and deciding when genre writing is safe.
- [CLI Reference](cli.md): `dj-sim` commands, options, output, and examples.
- [Web API Reference](api.md): FastAPI endpoints used by the frontend.
- [Development and Verification](development.md): setup commands and focused
  verification guidance.

## Rhythm Lab

- [Rhythm Lab](rhythm-lab.md): classifier profiles, labeling UI, training,
  prediction, promotion, deletion, and main-app integration.

## Maintenance Scripts

Only stable user-facing maintenance helpers are documented here:

- [Audio Metadata Repair Script](scripts/repair-audio-metadata.md):
  dry-run-first metadata/container diagnostics and repair.
- [Audio Dedup Report and Cleanup Script](scripts/audio-dedup.md): report-only
  duplicate-audio analysis by default, plus an explicit confirmed `--apply`
  cleanup pass.
- [Database Optimization Script](scripts/optimize-database.md):
  schema-validated SQLite backup, vacuum, analyze, and integrity check.

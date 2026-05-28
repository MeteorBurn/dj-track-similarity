# dj-track-similarity Documentation

This is the documentation index for `dj-track-similarity`. The short project
introduction remains in [README.md](../../README.md); the pages below hold the
operational user and developer reference.

## Main Project

- [Overview](overview.md): project purpose, core features, safety model, and
  supported audio files.
- [Architecture and Runtime](architecture.md): backend/frontend map,
  dependencies, CUDA/FFmpeg notes, and logging.
- [Database and Stored Data](database.md): SQLite schema, metadata, embeddings,
  and classifier-score storage.
- [Analysis Families](analysis.md): Sonara, MAEST, MERT, CLAP, and promoted
  classifier scoring.
- [Search and Tag Writing](search-and-tags.md): SONARA/MERT/CLAP/CLASS
  workflows and standard genre writes.
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
- [Audio Dedup Report Script](scripts/audio-dedup.md): report-only
  duplicate-audio candidate analysis.
- [Database Optimization Script](scripts/optimize-database.md):
  schema-validated SQLite backup, vacuum, analyze, and integrity check.

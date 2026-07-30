# SONARA integration

> Audience: Maintainers working with stored SONARA results.
> Goal: Describe the current decode, output, storage, and update boundaries.
> Type: reference

## Current path

The current project uses SONARA in `playlist` mode with a `70..180` BPM range.
The SONARA job passes ordered path chunks directly to `sonara.analyze_batch()`, and SONARA's
Symphonia path owns file decoding. The production SONARA job does not call the project's FFmpeg
loader or its signal-analysis helpers. ML, preview, and other non-SONARA functions retain their
FFmpeg dependency.

The application requests and stores only the scalar and compact fixed-vector Core result in the Core
`sonara` table. Timeline, SONARA similarity embedding, and fingerprint are not requested, converted,
stored, read, or exposed.

The Artifacts database still creates `sonara_timeline`, `sonara_similarity_embeddings`, and
`sonara_fingerprints` as empty placeholders. Their current columns are not a SONARA schema,
dimension, version, or compatibility contract.

The Full-only `time_signature` metrogram is excluded from current Core storage. It is not a ranking
or classifier input, and Beatgrid uses SONARA's normal fallback when a meter estimate is unavailable.

## Structural storage boundary

A selected catalog consists of a Core database plus a mandatory Artifacts database bound by the
same `catalog_uuid`. Evaluation is an optional third database created only by evaluation workflows.
Missing, structurally incompatible, or cross-catalog sidecars fail closed.

Normal track reads expose Core coverage and compact summaries. There is no Timeline route or
optional SONARA output metadata.

## Updating SONARA or stored fields

The project does not require a versioned schema or release contract before adopting a new SONARA
release. Adapt the source and database structure to the fields that the project should use, then run
focused compatibility checks.

Normal startup never changes an incompatible database layout. Preview the dedicated migration:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --dry-run
```

If the plan is correct, rerun without `--dry-run`. Apply requires the exact confirmation
`MIGRATE DATABASE`. Before either database is replaced, the command creates and validates a
self-contained Core and Artifacts backup pair. It then rebuilds the required tables and finishes with
integrity, foreign-key, and orphan checks. A failure restores the verified pair when possible and
records recovery information when manual recovery is required.

Migration changes structure only. It reports analysis families that may need reanalysis, but it does
not start analysis. Reset or reanalyze the affected families only when you choose to rebuild them.
Rhythm Lab profiles and labels remain separate from this Core/Artifacts migration.

## Scoring boundary

Search, SET, Hybrid, and classifiers use stored SONARA Core values. MERT, MuQ, MAEST, and CLAP
remain separate analysis sources. Every result is a ranking or diagnostic signal, not an automatic
DJ decision.

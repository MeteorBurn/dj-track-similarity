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

The application requests and stores only the scalar and compact fixed-vector SONARA result in the
library `sonara_features` table. Timeline, SONARA similarity embedding, and fingerprint are not
requested, converted, stored, read, or exposed.

The Full-only `time_signature` metrogram is excluded from current SONARA storage. It is not a ranking
or classifier input, and Beatgrid uses SONARA's normal fallback when a meter estimate is unavailable.

## Storage boundary

A selected catalog uses one library database with `catalog_uuid`. Evaluation is an optional sidecar
created only by Evaluation workflows. Normal track reads expose SONARA coverage and compact summaries. There is no Timeline route or
optional SONARA output metadata.

## Updating SONARA or stored fields

The project does not require a versioned schema or release contract before adopting a new SONARA
release. Adapt the source and database structure to the fields that the project should use, then run
focused compatibility checks.

Normal startup never changes an incompatible legacy layout. The explicit `dj-sim migrate-database`
command is the one-time conversion path after all SQLite users stop. It does not start analysis.
Reset or reanalyze only the outputs you choose to rebuild. Rhythm Lab profiles and labels remain
separate.

## Scoring boundary

Search, Evaluation diagnostics, Audio Dedup, and classifiers use stored SONARA values. MERT, MuQ, MAEST, and CLAP
remain separate analysis sources. Every result is a ranking or diagnostic signal, not an automatic
DJ decision.

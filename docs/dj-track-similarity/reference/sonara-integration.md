# SONARA integration

> Audience: Maintainers working with stored SONARA results.
> Goal: Describe the current decode, output, storage, and update boundaries.
> Type: reference

## Current tested path

The current project environment uses SONARA `0.3.5` in `playlist` mode with a `70..180` BPM range.
The SONARA job passes ordered path chunks directly to `sonara.analyze_batch()`, and SONARA's
Symphonia path owns file decoding. The production SONARA job does not call the project's FFmpeg
loader or its signal-analysis helpers. ML, preview, and other non-SONARA functions retain their
FFmpeg dependency.

These values describe the tested checkout. They are not a permanent compatibility policy. A SONARA
update may add or change fields in this project after the affected ingestion, storage, and retrieval
paths have been adapted and checked.

SONARA `0.3.5` includes an opt-in `aggression` feature. This project currently does not request or
store those outputs. The existing `mood_aggressive_score` comes from SONARA's separately requested
`mood` feature.

## Output kinds

| Output kind | Contents | Storage |
| --- | --- | --- |
| `core` | Scalar and compact fixed-vector features | Core `sonara` |
| `timeline` | Beats, onsets, chord events, tempo, energy, loudness, downbeats, and structure sequences | Artifacts `sonara_timeline` |
| `embedding` | SONARA similarity vector | Artifacts `sonara_similarity_embeddings` |
| `fingerprint` | SONARA audio fingerprint | Artifacts `sonara_fingerprints` |

`core` is always included. Selecting several output kinds performs one SONARA call, then persistence
splits the returned object across the Core and Artifacts tables without repeating decode or native
analysis.

The Full-only `time_signature` metrogram is excluded from current Core storage. It is not a ranking
or classifier input, and Beatgrid uses SONARA's normal fallback when a meter estimate is unavailable.

## Structural storage boundary

A selected catalog consists of a Core database plus a mandatory Artifacts database bound by the
same `catalog_uuid`. Evaluation is an optional third database created only by evaluation workflows.
Missing, structurally incompatible, or cross-catalog sidecars fail closed.

Normal track reads expose analysis coverage and compact summaries. The explicit timeline route loads
the stored `timeline` row, while the metadata dialog shows timeline fields and the presence of the
embedding and fingerprint outputs.

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

Search, SET, Hybrid, and classifiers use the stored SONARA values they request. Timeline,
embedding, and fingerprint outputs remain separate evidence. MERT, MuQ, MAEST, and CLAP remain
separate analysis sources. Every result is a ranking or diagnostic signal, not an automatic DJ
decision.

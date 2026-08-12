# FAQ

> Audience: Users who want short answers about the current runtime.
> Goal: Separate safe local workflows from migration assumptions.
> Type: help

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data only.

## Which actions can write audio files?

Only MAEST genre-tag apply, Audio Doctor apply, and Audio Dedup apply. Audio Dedup apply can delete
files; each is confirmation-gated and separate from normal scan, search, and analysis.

## Can the app migrate an incompatible database?

Normal startup refuses an incompatible legacy split database and never rewrites it. After stopping
the server and database tools, use `dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`. It creates a timestamped backup, builds and verifies the replacement,
and does not run analysis or reanalysis.

## What follows a SONARA change?

Adapt the project to the SONARA fields you want. Reanalyze only the affected outputs when you
choose. Retrain,
promote, and rescore a SONARA-dependent classifier only when its feature recipe changed.

## Why are classifier artifacts blocked?

Runtime scoring requires an artifact whose ordered feature recipe and inputs match the current
stored data. Affected artifacts must be retrained and promoted; incompatible scores are not silently
reused.

## Can I use the browser UI with a compatible database?

Yes. Build the current frontend bundle and serve it with the current backend. Database selection,
library paging and chunked loads, analysis, search, Current Set, CLASS, LAB, Rhythm Lab launch,
metadata, preview, and exact-identity writes use the current typed responses.

## Can I share reports or databases?

Review them first: they can contain local paths, tags, scores, and listening decisions.

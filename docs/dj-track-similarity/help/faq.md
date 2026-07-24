# FAQ

> Audience: Users who want short answers about the current v7 runtime.
> Goal: Separate safe local workflows from legacy assumptions.
> Type: help

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data only.

## Which actions can write audio files?

Only MAEST genre-tag apply, Audio Doctor apply, and Audio Dedup apply. Audio Dedup apply can delete
files; each is confirmation-gated and separate from normal scan, search, and analysis.

## Can v7 migrate my old database?

No. The Python runtime is greenfield schema v7. It does not migrate v5/v6 files, adapt old SONARA
results, or recreate Timeline/Representations sidecars. A library is Core plus mandatory
`*.artifacts.sqlite`, bound by `catalog_uuid`; `*.evaluation.sqlite` is optional evaluation state.

## What follows a SONARA change?

Run `prepare-sonara-release` with a verified backup location, then reanalyze SONARA. The operation
uses the exact `core`, `timeline`, `embedding`, and `fingerprint` contracts, writes a durable receipt
for crash resume, and is ordered rather than distributed-atomic. Retrain, promote, and rescore every
SONARA-dependent classifier afterward. The project feature revision is `6`.

## Why are classifier artifacts blocked?

Runtime scoring requires classifier manifest version `2`. Checked-in version `1` or unversioned
artifacts must be retrained and promoted. Their scores are not silently reused.

## Can I use the browser UI with v7?

No. The frontend v7 port is deferred. Use CLI or API contracts for v7 library work.

## Can I share reports or databases?

Review them first: they can contain local paths, tags, scores, and listening decisions.

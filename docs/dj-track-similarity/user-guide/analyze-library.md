# Analyze a library with v7

> Audience: Users running local analysis from the current Python runtime.
> Goal: Choose safe v7 analysis commands and understand their storage boundary.
> Type: guide

The current runtime uses greenfield schema v7. Analysis reads source audio
and writes local SQLite state. It does not modify source audio files. Scan first, then select the
analysis family that answers your listening question.

## Current UI status

The frontend v7 port is deferred. The existing browser analysis controls are not v7-compatible, so
do not use this page as a guide to current checkboxes, limits, or reset buttons. Use the CLI or API
while the frontend is being ported.

## Prepare SONARA before the first run

Every fresh v7 bundle must activate the loaded immutable four-output SONARA release before the first
SONARA analysis:

```powershell
mkdir .\backups
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backups --confirm "PREPARE SONARA RELEASE"
```

The backup directory must exist and be writable. Preparation derives the exact `core`, `timeline`,
`embedding`, and `fingerprint` contracts from the loaded runtime. It also verifies Core and
Artifacts backups before writing a durable resumable receipt.

## Run a family

After preparation, SONARA runs alone. Select all four outputs for the complete active release:

```powershell
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
```

ML families can run together:

```powershell
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Omit `--limit` to consider the whole library. A positive limit selects only candidates missing the
requested current outputs. Use `--device auto`, `--device cpu`, or `--device cuda` for MAEST, MERT,
MuQ, and CLAP. SONARA uses its native CPU path.

## SONARA outputs and storage

The only SONARA output names are `core`, `timeline`, `embedding`, and `fingerprint`. Core is always
included. Core feature rows live in Core; Timeline payloads, the SONARA embedding, and the
fingerprint live in the mandatory `*.artifacts.sqlite` companion. MAEST, MERT, MuQ, and CLAP
embeddings also live in Artifacts. Core and Artifacts must share one `catalog_uuid`.

`*.evaluation.sqlite` is optional evaluation state. The runtime does not migrate v5/v6 databases,
adapt old SONARA results, or recreate the removed Timeline/Representations sidecars.

## Prepare again when the SONARA release changes

The project SONARA feature revision is `6`. A changed SONARA release, decoder, output feature
profile, or feature revision requires the same preparation before new SONARA work. The process is
ordered and crash-resumable, not a distributed atomic transaction. After preparation, reanalyze
SONARA and retrain, promote, and rescore every classifier that uses SONARA.

## Pipeline and classifiers

The backend pipeline order is always SONARA, then ML, then CLASSIFIERS. Per-file failures are kept
in job status. A fatal initialization failure or cancellation stops later stages.

Classifier scoring is database-only and does not decode source audio. It requires a compatible
manifest version `2`; checked-in version `1` or unversioned artifacts are blocked until retrained
and promoted. Scores stay scoped to their `classifier_key`.

## Reset and interpretation

Resets affect SQLite data only. Do not use a reset as a substitute for the ordered SONARA release
preparation flow. Model outputs are ranking evidence for listening-led shortlists, not objective
truth or automatic DJ decisions.

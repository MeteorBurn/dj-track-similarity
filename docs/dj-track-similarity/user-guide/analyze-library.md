# Analyze a library with v7

> Audience: Users running local analysis from the current Python runtime.
> Goal: Choose safe v7 analysis commands and understand their storage boundary.
> Type: guide

The current runtime uses greenfield schema v7. Analysis reads source audio
and writes local SQLite state. It does not modify source audio files. Scan first, then select the
analysis family that answers your listening question.

## Browser controls

The browser can start the v7 jobs directly. **Analyze limit** defaults to `0` for the whole eligible
library. The initial batch values are Track `8`,
Inference `16`, and SONARA `8`; **Device** defaults to `auto`.

The panel keeps **SONARA**, **ML**, and **CLASSIFIERS** as separate stages. **FULL** runs them in the
fixed order. SONARA is selected at startup. Its mandatory `core` output is selected and locked;
`timeline`, `embedding`, and `fingerprint` are optional. The ML selection contains MAEST, MERT, MuQ,
and CLAP, not SONARA or CLASSIFIERS. Progress, per-file failures, blockers, cancellation, and reset
results come from the typed v7 job responses.

## First SONARA run

In a catalog with no SONARA state, the first SONARA **Analyze** derives and registers the exact
runtime contracts for all four outputs automatically. There is no separate UI release card or
backup dialog. Registration still covers the complete release when the job requests only `core` or
another subset.

The advanced `prepare-sonara-release` CLI/API workflow remains available for a catalog with
conflicting or inconsistent release state. It verifies Core and Artifacts backups and records a
resumable receipt. It is not a mandatory fresh-catalog or browser step.

## Run a family

SONARA can run alone. Select all four outputs when you need every optional output:

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

## Reanalyze after the SONARA release changes

The project SONARA feature revision is `6`. A changed SONARA release, decoder, output feature
profile, or feature revision requires a full SONARA reanalysis. In the browser, use **Reset
SONARA**, then **Analyze**. Reset removes the stored SONARA outputs and dependent classifier scores,
so the next analysis registers the exact runtime contracts and rebuilds the requested outputs.
Retrain, promote, and rescore every classifier that uses SONARA.

## Pipeline and classifiers

The backend pipeline order is always SONARA, then ML, then CLASSIFIERS. Per-file failures are kept
in job status. A fatal initialization failure or cancellation stops later stages.

Classifier scoring is database-only and does not decode source audio. It requires a compatible
manifest version `2`; checked-in version `1` or unversioned artifacts are blocked until retrained
and promoted. Scores stay scoped to their `classifier_key`.

## Reset and interpretation

Resets affect SQLite data only. Normal reruns skip current results and analyze missing requested
outputs; use **Reset SONARA**, then **Analyze**, only for an intentional full reanalysis. Model
outputs are ranking evidence for listening-led shortlists, not objective truth or automatic DJ
decisions.

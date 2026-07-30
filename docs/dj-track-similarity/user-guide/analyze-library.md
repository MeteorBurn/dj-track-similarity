# Analyze a library

> Audience: Users running local analysis from the current Python runtime.
> Goal: Choose safe analysis commands and understand their storage boundary.
> Type: guide

Analysis reads source audio and writes local SQLite state. It does not modify source audio files.
Scan first, then select the analysis family that answers your listening question.

## Browser controls

The browser can start the jobs directly. **Analyze limit** defaults to `0` for the whole eligible
library. The initial batch values are Track `8`,
Inference `16`, and SONARA `8`; **Device** defaults to `auto`.

The panel keeps **SONARA**, **ML**, and **CLASSIFIERS** as separate stages. **FULL** runs them in the
fixed order. SONARA is selected at startup and always runs Core only; there are no output
checkboxes. The ML selection contains MAEST, MERT, MuQ, and CLAP, not SONARA or CLASSIFIERS. Progress,
per-file failures, blockers, cancellation, and reset results come from the typed job responses.

## Run a family

SONARA Core can run alone:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

ML families can run together:

```powershell
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Omit `--limit` to consider the whole library. A positive limit selects only candidates missing the
requested current outputs. Use `--device auto`, `--device cpu`, or `--device cuda` for MAEST, MERT,
MuQ, and CLAP. SONARA uses its native CPU path.

## SONARA storage

SONARA writes Core feature rows to Core. Timeline, SONARA embedding, and fingerprint collection are
disabled. Their empty tables remain in the mandatory `*.artifacts.sqlite` companion as layout
placeholders only. MAEST, MERT, MuQ, and CLAP embeddings also live in Artifacts. Core and Artifacts
must share one `catalog_uuid`.

`*.evaluation.sqlite` is optional evaluation state. Normal startup refuses an incompatible
Core/Artifacts layout rather than adapting it automatically.

## Reanalyze after a SONARA change

Adopting a new SONARA release does not require a versioned project contract. Adapt the fields and
storage that the project should use. If database structure changes, inspect
`dj-sim migrate-database --db <path> --dry-run`, then apply only after reviewing the backup-first
plan. Reanalysis is a separate choice: use **Reset SONARA**, then **Analyze**, only for outputs you
intend to rebuild. Retrain and promote a classifier only when its ordered feature recipe changed.

## Pipeline and classifiers

The backend pipeline order is always SONARA, then ML, then CLASSIFIERS. Per-file failures are kept
in job status. A fatal initialization failure or cancellation stops later stages.

Classifier scoring is database-only and does not decode source audio. It requires ordered feature
names and inputs that match current stored data. An incompatible artifact is blocked until that
profile is retrained and promoted. Scores stay scoped to their `classifier_key`.

## Reset and interpretation

Resets affect SQLite data only. Normal reruns skip current results and analyze missing requested
outputs; use **Reset SONARA**, then **Analyze**, only for an intentional full reanalysis. Model
outputs are ranking evidence for listening-led shortlists, not objective truth or automatic DJ
decisions.

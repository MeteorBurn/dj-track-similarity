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
fixed order. SONARA is selected at startup and always runs Core plus its dedicated embedding as one
fixed output set. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ,
MuQ-MuLan, and CLAP, not SONARA or CLASSIFIERS. The browser still starts with SONARA selected;
when the CLI or API ML model list is omitted, its normal ordered default is MAEST, MERT, MuQ,
MuQ-MuLan, then CLAP. Progress, per-file failures, blockers, cancellation, and reset
results come from the typed job responses.

## Run a family

SONARA can run alone and writes its fixed Core-plus-embedding output set:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

ML families can run together:

```powershell
dj-sim analyze --models maest,mert,muq,mulan,clap --db .\data\library.sqlite
```

Omit `--limit` to consider the whole library. A positive limit selects only candidates missing the
requested current outputs. Use `--device auto`, `--device cpu`, or `--device cuda` for MAEST, MERT,
MuQ, MuQ-MuLan, and CLAP. SONARA uses its native CPU path.

## SONARA storage

SONARA writes Core feature rows to `sonara_features` and unnormalized 48-dimensional `float32`
embeddings to the dedicated `sonara_embeddings` table. A successful SONARA pass stores both rows
together. Timeline and fingerprint collection remain disabled. The SONARA embedding is persisted
data only; it is not a current similarity, search, or classifier input. MAEST, MERT, MuQ,
MuQ-MuLan, and CLAP embeddings live in their own dedicated tables in the same library database.
MuQ-MuLan analysis reads mono 24 kHz `float32` audio in 10-second windows and writes its own
L2-normalized 512-dimensional rows to `mulan_embeddings`. It never converts existing MuQ rows.
For an existing library that predates this table, first run the backup-first
`dj-sim migrate-mulan-embeddings` command described in the
[database reference](../reference/database.md).

`*.evaluation.sqlite` is optional evaluation state. Normal startup refuses a legacy split layout
rather than adapting it automatically.

## Reanalyze after a SONARA change

Adopting a new SONARA release does not require a versioned project contract. Adapt the fields and
storage that the project should use. Reanalysis is a separate choice: use **Reset SONARA**, then
**Analyze**, only for outputs you intend to rebuild. Retrain and promote a classifier only when its
ordered feature recipe changed.

## Pipeline and classifiers

The backend pipeline order is SONARA, then ML. Per-file failures are kept in job status. A fatal
initialization failure or cancellation stops later stages.

Classifier scoring is database-only and does not decode source audio. Start it for one promoted
profile from the **CLASS** tab. It requires ordered feature names and inputs that match current
stored data. An incompatible artifact is blocked until that profile is retrained and promoted.
Scores stay scoped to their `classifier_key`.

## Reset and interpretation

Resets affect SQLite data only. A normal SONARA rerun selects a track when either its current Core
row or embedding row is missing and stores both rows together. Tracks with both rows remain skipped.
Use **Reset SONARA**, then **Analyze**, only for an intentional full reanalysis. Model outputs are
ranking evidence for listening-led shortlists, not objective truth or automatic DJ decisions.

# Reanalyze SONARA with split storage

> Audience: Users opening a schema v5 library with the current application.
> Goal: Move to Core, Timeline, and Representations storage and rebuild analysis cleanly.
> Type: workflow

## 1. Back up the catalog

Stop the server and copy the main database plus any existing adjacent side databases. After analysis
begins, copy all three files together because they form one catalog.

## 2. Open the main database

Open the existing schema v5 `.sqlite` file with the current app. Migration to schema v6 runs once
and creates:

```text
library.sqlite
library.timeline.sqlite
library.representations.sqlite
```

The migration deliberately clears old SONARA data and invalidates SONARA-dependent classifier
scores. Existing MAEST/MERT/MuQ/CLAP embeddings, MAEST metadata, their analysis flags,
embedding-only classifier scores, tracks, file tags, likes, feedback, and evaluation records remain.
Databases older than schema v5 are not adapted; scan the audio library into a fresh current database
instead.

## 3. Reset the old SONARA contract explicitly

If any Core, Timeline, or Representations rows use an earlier project contract, the native preflight
blocks the job. After the backup, use the existing SONARA reset, which removes all three SONARA
stores and SONARA-dependent classifier scores without modifying audio, labels, feedback, or ML-only
embeddings. Old and new SONARA data are not adapted or mixed.

## 4. Analyze SONARA

Use the UI checkboxes or CLI. Core only is the default:

```powershell
dj-sim analyze --models sonara --db C:\db\library.sqlite
```

For all current SONARA data:

```powershell
dj-sim analyze --models sonara --sonara-outputs core,timeline,representations --db C:\db\library.sqlite
```

You can add optional outputs later:

```powershell
dj-sim analyze --models sonara --sonara-outputs timeline,representations --db C:\db\library.sqlite
```

The default native batch size is `64`. Use `--sonara-batch-size 1..128` when needed. Complete the
full Core pass before retraining SONARA-dependent classifiers. Timeline and Representations require
their own full pass only when explicitly selected.

## 5. Analyze missing ML models separately

```powershell
dj-sim analyze --models maest,mert,muq,clap --db C:\db\library.sqlite
```

SONARA cannot be combined with those models or with classifiers in the same job.
The migration does not require these models to be rerun when their existing embeddings are present.

## 6. Retrain, promote, and score classifiers separately

Retrain and promote every SONARA-dependent classifier only after required Core and ML coverage is
complete. Then run:

```powershell
dj-sim analyze-classifiers --db C:\db\library.sqlite
```

The job scores only tracks with each manifest's complete current input set. Tracks that become ready
later are picked up by a repeated classifier job.

## 7. Verify in metadata

Open a track's metadata dialog:

- Core should list calculated values and SONARA `0.2.9`/schema `4` provenance.
- Timeline should say data is present and list its stored field names.
- Representations should say data is present and list the SONARA `embedding` and `fingerprint`.

Verify classifier readiness and blockers in the CLASSIFIERS block, then confirm expected score
coverage. Use a 100-file native pilot after backup/reset. Do not continue to the full Core run until
the pilot completes without failures under native signatures and SQLite returns a successful
integrity check.

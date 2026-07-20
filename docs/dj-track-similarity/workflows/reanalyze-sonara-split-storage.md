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

## 3. Analyze SONARA

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

## 4. Analyze missing ML models separately

```powershell
dj-sim analyze --models maest,mert,muq,clap --db C:\db\library.sqlite
```

SONARA cannot be combined with those models or with classifiers in the same job.
The migration does not require these models to be rerun when their existing embeddings are present.

## 5. Verify in metadata

Open a track's metadata dialog:

- Core should list calculated values and SONARA `0.2.9`/schema `4` provenance.
- Timeline should say data is present and list its stored field names.
- Representations should say data is present and list the SONARA `embedding` and `fingerprint`.

Retrain and promote SONARA-dependent classifiers only after the required Core and ML coverage is
complete.

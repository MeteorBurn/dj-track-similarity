# Run your first analysis

> Audience: Users who have scanned tracks and want model-backed search.
> Goal: Choose analysis families safely and understand what each unlocks.
> Type: tutorial

Scanning tells the app what files you own. Analysis gives it several limited ways to compare how
those files sound. The useful result is not a new audio file: it is local evidence that unlocks
shortlists, filters, and ordered previews.

Analysis jobs read audio or stored analysis values and write SQLite results. They do not rewrite
source audio files.

## Choose by the result you want

| You want to | Run | What you get |
| --- | --- | --- |
| Start from a track and find a broad audio neighborhood | MERT | Ranked seed-search candidates |
| Steer by rhythm, texture, dynamics, harmony, or tempo | SONARA | Explainable feature search and transition evidence |
| Describe a desired sound in words | CLAP | Text-search candidates |
| Generate SET or compare several model views | SONARA, MAEST, MERT, CLAP | Feature-complete candidates for SET and Hybrid |
| Compare another model's neighbors in LAB | MuQ | A separate MuQ result column in Reference Compare |
| Reuse your own labeled concept | CLASSIFIERS | Stored scores for CLASS filters and optional SET or Hybrid controls |

For a first experiment, analyze 25 familiar tracks. Try the resulting searches before choosing
which families deserve a full-library run.

## What each family stores and unlocks

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | signed `core`, `timeline`, `embedding`, and `fingerprint` outputs | feature search, confidence-aware tempo, Camelot resolution, SET ordering, transition diagnostics, classifier inputs |
| MAEST | Core genre/syncopation rows and an Artifacts embedding | genre display, genre tag apply, SET and Hybrid MAEST source |
| MERT | Artifacts embedding | seed search, SET, Hybrid, Audio Dedup evidence |
| MuQ | Artifacts embedding | LAB Reference Compare evidence; no MERT/SONARA search, SET, or Hybrid integration |
| CLAP | Artifacts audio embedding | text search, SET, Hybrid, Audio Dedup evidence |
| CLASSIFIERS | Core `classifier_scores` rows | CLASS filters, SET bias, Hybrid diagnostics |

Classifier scoring is a separate stage. Each promoted manifest defines its exact SONARA and
MAEST/MERT/CLAP requirements. Incomplete tracks are counted as not ready rather than failed.

## CLI analysis

Install optional analysis dependencies first. A fresh v7 bundle must activate the loaded SONARA
release before its first SONARA job. Create a writable backup directory and prepare the immutable
four-output release. Then run:

```powershell
mkdir .\backups
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backups --confirm "PREPARE SONARA RELEASE"
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
dj-sim analyze-classifiers --db .\data\library.sqlite
dj-sim analyze-pipeline --stages sonara,ml,classifiers --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
```

Preparation derives and activates the exact `core`, `timeline`, `embedding`, and `fingerprint`
contracts. It verifies Core and Artifacts backups and records a resumable receipt before analysis
can write under that release.

Useful options:

```powershell
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --device auto --top-k 3 --track-batch-size 8 --inference-batch-size 16 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, and `clap` as a comma-separated list.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track.
- `--track-batch-size` is `1..64` decoded tracks per job batch. The default is `8`.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, and CLAP. The default is `16`.
- `--sonara-batch-size` is `1..16` paths per native SONARA batch. The default is `8`.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. The app gives MuQ only 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full libraries. MuQ stores embeddings for LAB Reference Compare, but it does not feed SET or Hybrid.

In the CLI, omit `--limit` for the whole library.

## Frontend status

The Python backend and CLI use the v7 analysis contract. The checked-in React frontend has not
yet been ported to the new database, track-identity, reset, and output payloads. Do not treat the
current model controls or an existing `frontend/dist` bundle as compatible with this workflow.

Use the CLI or v7 API for current execution. SONARA receives paths in native batches and decodes them
through its Symphonia path inside `sonara.analyze_batch()`. It does not call the project's FFmpeg
loader and has no `analyze_signal` or per-file decode fallback. ML models continue to share the
project's FFmpeg decode.

The SONARA batch value controls concurrent full-file native reads, not ML inference. Keep the
default for a library on one HDD unless a measured pilot supports a larger value.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA materializes `core`,
`timeline`, `embedding`, and `fingerprint` independently from the same immutable four-contract
release, so adding another active output later does not replace `core`. Other complete families are
skipped. Use reset only when you intentionally want to delete stored results.

An unprepared SONARA release fails closed. The preparation above is mandatory even for the first
SONARA run on a fresh v7 bundle. Follow
[Prepare and rebuild a SONARA release](../workflows/reanalyze-sonara-split-storage.md) for the full
backup, activation, rebuild, and classifier sequence.

## Reset boundaries

- Reset SONARA removes active Core and Artifacts outputs plus dependent classifier scores. Labels and feedback remain intact.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.

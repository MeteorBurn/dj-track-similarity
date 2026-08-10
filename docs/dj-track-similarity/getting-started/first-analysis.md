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
| Compare several model views or inspect duplicates | SONARA, MAEST, MERT, MuQ, CLAP | Feature-complete candidates for LAB, Audio Dedup, and classifiers |
| Compare another model's neighbors in LAB | MuQ | A separate MuQ result column in Reference Compare |
| Reuse your own labeled concept | CLASSIFIERS | Stored scores for CLASS filters |

For a first experiment, analyze 25 familiar tracks. Try the resulting searches before choosing
which families deserve a full-library run.

## What each family stores and unlocks

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | Core feature rows | feature search, confidence-aware tempo, Camelot resolution, Evaluation transition diagnostics, Audio Dedup, classifier inputs |
| MAEST | Core genre/syncopation rows and an Artifacts embedding | genre display, genre tag apply, LAB Reference Compare, Audio Dedup, classifier input |
| MERT | Artifacts embedding | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| MuQ | Artifacts embedding | seed search, LAB Reference Compare, Audio Dedup, classifier input |
| CLAP | Artifacts audio embedding | seed and text search, LAB Reference Compare, Audio Dedup, classifier input |
| CLASSIFIERS | Core `classifier_scores` rows | CLASS filters |

Classifier scoring is a separate stage. Each promoted manifest defines its exact SONARA and
MAEST/MERT/MuQ/CLAP requirements. Incomplete tracks are counted as not ready rather than failed.

## CLI analysis

Install optional analysis dependencies first. Then run:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
dj-sim analyze-classifiers --db .\data\library.sqlite
dj-sim analyze-pipeline --stages sonara,ml,classifiers --db .\data\library.sqlite
```

Useful options:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --device auto --top-k 3 --track-batch-size 8 --inference-batch-size 16 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, and `clap` as a comma-separated list.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track.
- `--track-batch-size` is `1..64` decoded tracks per job batch. The default is `8`.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, and CLAP. The default is `16`.
- `--sonara-batch-size` is `1..16` paths per native SONARA batch. The default is `8`.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. The app gives MuQ only 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full libraries. Its embedding can feed seed search and LAB Reference Compare. Audio Dedup and compatible classifier manifests can also use it. Audio Dedup can disable MuQ by omitting `muq` from an explicit source list.

In the CLI, omit `--limit` for the whole library.

## Analyze in the browser

Use the browser model checkboxes to start the same jobs. **Analyze limit** starts at `0` for the
whole eligible library. Track/Inference/
SONARA batch values, Device, progress, blockers, cancellation, and SQLite-only resets are carried
through the typed requests and responses. **CLASSIFIERS** stays a separate stage; **FULL** runs
SONARA, ML, and CLASSIFIERS in order.

SONARA is selected at startup and always runs Core only. There are no output checkboxes. The ML
selection contains MAEST, MERT, MuQ, and CLAP, not SONARA or CLASSIFIERS.

SONARA receives paths in native batches and decodes them through its Symphonia path inside
`sonara.analyze_batch()`. It does not call the project's FFmpeg loader and has no `analyze_signal`
or per-file decode fallback. ML models continue to share the project's FFmpeg decode.

The SONARA batch value controls concurrent full-file native reads, not ML inference. Keep the
default for a library on one HDD unless a measured pilot supports a larger value.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA skips tracks whose current
Core row is already present. Other complete families are skipped. Use reset only when you
intentionally want to delete stored results.

After adopting a SONARA change, adapt storage explicitly if needed and decide which outputs to
reset or reanalyze. Follow [Migrate and reanalyze SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

## Reset boundaries

- Reset SONARA removes active Core and Artifacts outputs plus dependent classifier scores. Labels and feedback remain intact.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.

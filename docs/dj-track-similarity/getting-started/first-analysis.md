# Run your first analysis

> Audience: Users who have scanned tracks and want model-backed search.
> Goal: Choose analysis families safely and understand what each unlocks.
> Type: tutorial

Analysis jobs decode audio and write SQLite results. They do not rewrite source audio files.

## Analysis families

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | metadata fields and `has_sonara_analysis` | feature search, SET ordering, BPM/key/energy fallback, classifier inputs |
| MAEST | genre labels, syncopated rhythm data, MAEST embedding | genre display, genre tag apply, SET and Hybrid MAEST source |
| MERT | MERT embedding | seed search, SET, Hybrid, Audio Dedup evidence |
| MuQ | MuQ embedding | stored coverage for future workflows; no search or SET integration yet |
| CLAP | CLAP audio embedding | text search, SET, Hybrid, Audio Dedup evidence |
| CLASSIFIERS | `track_classifier_scores` rows | CLASS filters, SET bias, Hybrid diagnostics |

Classifier scoring needs existing or same-job SONARA, MAEST, and MERT data.

## CLI analysis

Install optional analysis dependencies first. Then run:

```powershell
dj-sim analyze --models sonara,maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
```

Useful options:

```powershell
dj-sim analyze --models sonara,maest,mert,muq,clap --device auto --top-k 3 --track-batch-size 4 --inference-batch-size 24 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, and `clap` as a comma-separated list.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track.
- `--track-batch-size` is `1..64` decoded tracks per job batch.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, and CLAP.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. The app gives MuQ only 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full libraries. MuQ currently stores embeddings only.

In the CLI, omit `--limit` for the whole library.

## UI analysis

In **1. Database and analysis**:

1. Select the model checkboxes.
2. Choose `AUTO`, `CPU`, or `CUDA`.
3. Set **Analyze limit**. `0` means the whole library.
4. Adjust **Track batch size** and **Inference batch size** only when memory or throughput needs it.
5. Click **Analyze**.

The UI creates a job and polls progress. It also shows the current model/path and keeps a process log. The stop button requests cancellation.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. If a track already has a selected family, that family is skipped for that track. Use the per-family reset buttons only when you want to delete stored results and rerun.

## Reset boundaries

- Reset SONARA removes SONARA metadata and flags and restores working BPM/key/energy/duration from remaining tags when possible.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.

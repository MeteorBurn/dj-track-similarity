# Run your first analysis

> Audience: Users who have scanned tracks and want model-backed search.
> Goal: Choose analysis families safely and understand what each unlocks.
> Type: tutorial

Analysis jobs decode audio and write SQLite results. They do not rewrite source audio files.

## Analysis families

| Family | Writes | Unlocks |
| --- | --- | --- |
| SONARA | signed metadata, provenance, curves, and `has_sonara_analysis` | feature search, confidence-aware tempo, Camelot resolution, SET ordering, transition diagnostics, classifier inputs |
| MAEST | genre labels, syncopated rhythm data, MAEST embedding | genre display, genre tag apply, SET and Hybrid MAEST source |
| MERT | MERT embedding | seed search, SET, Hybrid, Audio Dedup evidence |
| MuQ | MuQ embedding | LAB Reference Compare evidence; no MERT/SONARA search, SET, or Hybrid integration |
| CLAP | CLAP audio embedding | text search, SET, Hybrid, Audio Dedup evidence |
| CLASSIFIERS | `track_classifier_scores` rows | CLASS filters, SET bias, Hybrid diagnostics |

Classifier scoring needs existing or same-job SONARA, MAEST, and MERT data.

## CLI analysis

Install optional analysis dependencies first. Then run:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
```

Useful options:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --device auto --top-k 3 --track-batch-size 4 --inference-batch-size 24 --db .\data\library.sqlite
```

- `--models` accepts `sonara`, `maest`, `mert`, `muq`, and `clap` as a comma-separated list.
- `--device` accepts `auto`, `cpu`, or `cuda`.
- `--top-k` stores `1..10` MAEST genre labels per track.
- `--track-batch-size` is `1..64` decoded tracks per job batch.
- `--inference-batch-size` is `1..128` model samples per forward pass for MAEST, MERT, MuQ, and CLAP.
- `--diagnostics` writes decoder fallback and batch timing details to the file log.

MuQ requires the optional `ml` dependencies and downloads the official `OpenMuQ/MuQ-large-msd-iter` weights. The app gives MuQ only 24 kHz `float32` audio. CPU and CUDA are supported, with CUDA recommended for full libraries. MuQ stores embeddings for LAB Reference Compare, but it does not feed SET or Hybrid.

In the CLI, omit `--limit` for the whole library.

## UI analysis

In **1. Database and analysis**:

1. Select the model checkboxes.
2. Choose `AUTO`, `CPU`, or `CUDA`.
3. Set **Analyze limit**. `0` means the whole library.
4. Adjust **Track batch size** and **Inference batch size** only when memory or throughput needs it.
5. Click **Analyze**.

The UI creates a job and polls progress. It also shows the current model/path and keeps a process log. The stop button requests cancellation.

When SONARA is selected, UI, CLI, and API defaults request all eight supported extra families. An
explicit API empty list or CLI `--sonara-minimal` requests plain playlist mode. The full profile archives complete beat, onset,
chord, tempo, energy, loudness, downbeat, embedding, and fingerprint data outside the hot metadata row.

## Already analyzed tracks

Analysis jobs target missing results for the selected families. SONARA also targets a row when its deterministic signature does not match the requested current profile, so an upgrade or profile change is reanalyzed without a manual reset. Other complete families are skipped. Use the per-family reset buttons only when you intentionally want to delete stored results and rerun.

For an existing analyzed database, use the ordered
[SONARA v0.2.4 migration workflow](../workflows/migrate-sonara-v0-2-4.md) before rebuilding dependent
classifiers.

## Reset boundaries

- Reset SONARA removes SONARA metadata, provenance, signature, curves, flags, and dependent classifier scores, then restores working BPM/key/energy/duration from remaining tags when possible. Labels and feedback remain intact.
- Reset MAEST removes MAEST metadata and MAEST embeddings.
- Reset MERT, MuQ, or CLAP deletes embeddings for that key.
- Reset CLASSIFIERS deletes selected classifier scores only.

All reset operations are SQLite-only.

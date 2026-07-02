# Run your first analysis

> Audience: Users who have scanned tracks and want useful search results.
> Goal: Run the current unified analysis job and understand limit behavior.
> Type: tutorial

Run analysis after scanning so the app can compare tracks by measured audio features and model embeddings. Start with a small batch. Confirm the results are useful before scaling up to the whole library.

## Unified command

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

`--limit 25` means the command processes a small number of tracks missing the requested analysis results. That keeps the first run fast enough to confirm decoding, model loading, and GPU/CPU behavior.

## What each model unlocks

- `sonara` stores measured audio features used by the SONARA tab, Smart Set transition routing, energy cues, and analyzed BPM/key fallback values.
- `maest` stores genre labels and MAEST embeddings. Genre tag apply uses the stored labels; Smart Set selection may use MAEST embeddings, not MAEST genre labels.
- `mert` stores MERT embeddings for seed-based similarity search and hybrid comparison.
- `clap` stores CLAP audio embeddings for CLAP text search and Smart Set routing signals.

## Options

Use `--models`, `--device auto|cpu|cuda`, `--top-k`, `--track-batch-size`, `--inference-batch-size`, and `--diagnostics`. `auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU. Use `--diagnostics` when you need decoder fallback and batch timing details.

For the whole library in the CLI, omit `--limit`. Do not pass `--limit 0` to mean all tracks in the CLI.

## UI limit

In the UI, `Analyze limit = 0` means whole library because the UI sends `null` or no limit to `/api/analysis/jobs`. Positive limits count tracks missing the selected analysis family.

Use a positive UI limit for the same reason as the CLI first batch: it confirms dependencies and expected runtime before committing to a long analysis job.

# Analyze the library from the UI

> Audience: Users running analysis jobs in the browser.
> Goal: Explain model selection, job progress, and reset behavior.
> Type: guide

Use the analysis area after scanning tracks. Analysis reads audio and writes SQLite results. It does not modify source audio files.

## Pick models

The UI lists these choices:

- **SONARA**: audio features and working BPM/key/energy/duration data.
- **MAEST**: genre label output plus syncopated-rhythm metadata and the MAEST embedding.
- **MERT**: audio embedding for seed similarity.
- **MuQ**: 24 kHz `float32` audio embedding stored for future workflows.
- **CLAP**: audio embedding for text search and audio-to-audio comparison.
- **CLASSIFIERS**: promoted classifier scores, if compatible profiles are available.

One job can include multiple families. Tracks that already have a selected result are skipped for that family.

## Limit behavior

`Analyze limit = 0` in the UI means the whole library. Positive limits count tracks missing selected results.

The CLI differs: omit `--limit` for the whole library.

## Device

- `AUTO` selects CUDA when PyTorch sees a GPU, otherwise CPU.
- `CPU` forces CPU.
- `CUDA` requests CUDA and should fail clearly if CUDA is unavailable.

SONARA runs as a CPU runner. MAEST, MERT, MuQ, and CLAP use the selected device through their adapters. MuQ uses official `OpenMuQ/MuQ-large-msd-iter` weights and is fed only 24 kHz `float32` audio. It currently stores embeddings only, with no search or SET integration.

## Batch controls

- **Track batch size**: `1..64`, decoded tracks held and processed together.
- **Inference batch size**: `1..128`, MAEST/MERT/MuQ/CLAP model samples per forward pass.

Lower these if memory is tight. Increase only after a small test batch works.

## Progress and logs

The UI polls the current job and shows:

- state: queued, running, completed, cancelled, or failed,
- total, processed, analyzed, failed, and skipped counts,
- current model and path,
- per-model progress,
- event log and errors.

The square stop button requests cancellation. It does not kill Python mid-write. The job checks the cancellation flag between work units.

## Reset buttons

Reset is SQLite-only:

- SONARA reset removes SONARA metadata and flags.
- MAEST reset removes MAEST metadata and MAEST embeddings.
- MERT, MuQ, and CLAP reset delete embeddings for that key.
- CLASSIFIERS reset deletes selected `track_classifier_scores` rows.

Use reset when you intentionally want a fresh run. Do not reset just because search results feel surprising.

# Analyze the library from the UI

> Audience: UI users running model jobs.
> Goal: Choose analysis families, safe limits, and device settings.
> Type: how-to

## Pick models

Run SONARA, MAEST, MERT, CLAP, or a subset. CLASSIFIERS can run when promoted classifier models are available.

## Limit behavior

UI `Analyze limit = 0` means whole library. Positive values count missing results for the selected model family. CLI whole-library analysis omits `--limit`.

## Advanced controls

Device is `auto`, `cpu`, or `cuda`. Track batch size controls decoded tracks held together. Inference batch size controls model forward-pass batching. Top K controls stored MAEST labels.

## Write boundary

Analysis writes SQLite metadata, features, and embeddings. It does not write audio tags.

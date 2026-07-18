# Known limits

> Audience: Users deciding whether behavior is expected.
> Goal: List current boundaries without pretending they are bugs.
> Type: help

## Local-first means local setup matters

The app depends on your local Python environment, FFmpeg, optional ML packages, GPU runtime, filesystem paths, and browser access to the backend.

## Model analysis can be heavy

MAEST, MERT, MuQ, and CLAP require optional ML dependencies. Large libraries can take time and memory. MuQ runs on 24 kHz `float32` audio and is currently stored for future workflows only. Use a small `--limit` first, then adjust device and batch sizes.

## Scores are not probabilities

Search and SET scores are ranking signals. CLAP text scores, MERT seed scores, SET scores, Hybrid scores, and Audio Dedup thresholds should not be treated as one scale.

## SET needs full coverage

Smart Set Builder requires SONARA plus MERT, MAEST, and CLAP embeddings. A partly analyzed library can browse and search in other tabs, but SET eligible counts will be low.

## SONARA current coverage is broader than one profile

The library summary counts any signed SONARA profile that matches the current version, schema, mode,
sample rate, BPM range, and project revision. It does not prove that every row has the exact full
profile. Check analysis jobs and sample signatures when validating a migration. The project full
profile means all supported adapter audio families; it does not request SONARA tags or its genre
model. See the [SONARA v0.2.4 project contract](../reference/sonara-v0-2-4-contract.md).

## Browser preview depends on files still existing

The database stores paths. If files move or disappear, preview fails until you rescan or relocate stored paths.

## Native dialogs depend on local GUI support

Database and folder picker routes use local GUI support. If unavailable, type paths manually or use CLI commands.

## Docs are built separately

The backend serves `/docs/` only when `docs/dj-track-similarity/site/` exists. Run `npm run check` from the docs folder to build it.

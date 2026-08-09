# Known limits

> Audience: Users deciding whether behavior is expected.
> Goal: List current boundaries without pretending they are bugs.
> Type: help

## Local-first means local setup matters

The app depends on your local Python environment, FFmpeg, optional ML packages, GPU runtime, filesystem paths, and browser access to the backend.

## Model analysis can be heavy

MAEST, MERT, MuQ, and CLAP require optional ML dependencies. Large libraries can take time and memory. MuQ runs on 24 kHz `float32` audio; its stored embedding can participate in seed search, LAB Reference Compare, SET, Hybrid, Audio Dedup, and classifier feature sets. Use a small `--limit` first, then adjust device and batch sizes.

## Scores are not probabilities

Search and SET scores are ranking signals. CLAP text scores, MERT seed scores, SET scores, Hybrid scores, and Audio Dedup thresholds should not be treated as one scale.

## SET needs full coverage

Smart Set Builder always requires SONARA plus every enabled embedding source. The default sources are MERT, MAEST, MuQ, and CLAP. An explicit API source list can omit MuQ or another embedding. A partly analyzed library can browse and search elsewhere, but SET eligible counts will be low for the selected source set.

## Browser preview depends on files still existing

The database stores paths. If files move or disappear, preview fails until you rescan or relocate stored paths.

## Native dialogs depend on local GUI support

Database and folder picker routes use local GUI support. If unavailable, type paths manually or use CLI commands.

## Docs are built separately

The backend serves `/docs/` only when `docs/dj-track-similarity/site/` exists. Run `npm run check` from the docs folder to build it.

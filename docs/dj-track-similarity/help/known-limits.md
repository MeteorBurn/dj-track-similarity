# Known limits

> Audience: Users deciding whether behavior is expected.
> Goal: List current boundaries without pretending they are bugs.
> Type: help

## Local-first means local setup matters

The app depends on your local Python environment, FFmpeg, optional ML packages, GPU runtime, filesystem paths, and browser access to the backend.

## Model analysis can be heavy

MAEST, MERT, MuQ, and CLAP require optional ML dependencies. Large libraries can take time and memory. MuQ runs on 24 kHz `float32` audio. Its stored embedding can participate in seed search and LAB Reference Compare. Audio Dedup and classifier feature sets can use it too. Use a small `--limit` first, then adjust device and batch sizes.

## Scores are not probabilities

Search scores are ranking signals. CLAP text scores, MERT seed scores, LAB model scores, and Audio Dedup thresholds should not be treated as one scale.

## Browser preview depends on files still existing

The database stores paths. If files move or disappear, preview fails until you rescan or relocate stored paths.

## Native dialogs depend on local GUI support

Database and folder picker routes use local GUI support. If unavailable, type paths manually or use CLI commands.

## Docs are built separately

The backend serves `/docs/` only when `docs/dj-track-similarity/site/` exists. Run `npm run check` from the docs folder to build it.

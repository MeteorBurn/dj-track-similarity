# Known limits

> Audience: Users deciding whether behavior is expected.
> Goal: List current boundaries without pretending they are bugs.
> Type: help

## Local-first means local setup matters

The app depends on your local Python environment, a system-available shared FFmpeg runtime, optional
ML packages, GPU runtime, filesystem paths, and browser access to the backend. The repository does
not version or vendor the required FFmpeg `8.1.1` full shared runtime. An `ffmpeg.exe` installed for
another program does not replace the shared libraries required by TorchCodec. Run `dj-sim doctor`
to inspect the selected runtime and PyAV installation.

## Model analysis can be heavy

MAEST, MERT, MuQ, MuQ-MuLan, and CLAP require optional ML dependencies. Large libraries can take time and memory. MuQ and MuQ-MuLan run on mono 24 kHz `float32` audio. MuQ-MuLan uses 10-second windows and writes separate normalized 512D embeddings. Use a small `--limit` first, then adjust device and batch sizes.

## Scores are not probabilities

Search scores are ranking signals. CLAP and MuQ-MuLan text scores, seed scores, LAB model scores, and Audio Dedup thresholds should not be treated as one scale.

## Browser preview depends on files still existing

The database stores paths. If files move or disappear, preview fails until you rescan or relocate stored paths.

## Native dialogs depend on local GUI support

Database and folder picker routes use local GUI support. If unavailable, type paths manually or use CLI commands.

## Docs are built separately

The backend serves `/docs/` only when `docs/dj-track-similarity/site/` exists. Run `npm run check` from the docs folder to build it.

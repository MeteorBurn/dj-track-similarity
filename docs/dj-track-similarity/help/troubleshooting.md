# Troubleshooting by symptom

> Audience: Users fixing local setup or analysis issues.
> Goal: Give checks tied to current storage and analysis behavior.
> Type: help

## Server says the shared FFmpeg runtime is missing

First check project-root `libs/ffmpeg`, which has highest priority and must contain
`avcodec-*.dll` (or the platform-equivalent `.so`/`.dylib` library). This directory is gitignored.
Otherwise, install or provide a shared FFmpeg build and set
`DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` to its library directory, or put that directory on `PATH`.
`ffmpeg.exe` alone is insufficient because the main application loads the shared libraries directly
through TorchCodec.

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR = 'C:\path\to\ffmpeg\bin'
dj-sim serve --host 127.0.0.1 --port 8765
```

## The selected library will not open

A library needs one `.sqlite` file with a valid `library` identity row. If the message reports an
incompatible legacy layout, do not edit the old files by hand. Stop the server and every database
tool, then run `dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`.
It keeps the original files in a timestamped backup directory and does not start analysis.

## A model adapter cannot load its dependencies

Run `python -m pip check` in the same activated environment that runs `dj-sim`, then compare the
installed stack with `pyproject.toml` and `uv.lock`. Update the related packages together so the
adapter still has its required APIs, checkpoints, and output shapes.

```powershell
python -m pip check
```

Restart `dj-sim serve` and any running Rhythm Lab process after changing the environment.

## Timeline, SONARA embedding, or fingerprint data is unavailable

Timeline collection remains disabled. A complete SONARA analysis stores its embedding in
`sonara_embeddings` and its versioned native-base64 acoustic fingerprint in `sonara_fingerprints`.
Neither raw value is exposed through track responses, and neither is a current UI, similarity,
search, classifier, or Audio Dedup input. Run normal SONARA analysis again when any of its Core,
embedding, or fingerprint rows is missing.

## A classifier is incompatible

Rebuild and promote an artifact whose ordered feature names and required inputs match the current
data. Classifier scoring is database-only and remains scoped by `classifier_key`.

## CUDA was requested but analysis fails

Run `dj-sim doctor`, then try `--device cpu` to separate device setup from the analysis workflow.

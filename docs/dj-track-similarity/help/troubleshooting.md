# Troubleshooting by symptom

> Audience: Users fixing local setup or analysis issues.
> Goal: Give checks tied to current storage and analysis behavior.
> Type: help

## Server says FFmpeg is missing

Set `DJ_TRACK_SIMILARITY_FFMPEG` to an FFmpeg executable or put FFmpeg on `PATH`, then restart
`dj-sim serve`.

## The selected library will not open

A library needs its Core `.sqlite` and mandatory `*.artifacts.sqlite` companion with the same
`catalog_uuid`. If the message reports an incompatible structure, do not edit either file by hand.
Run `dj-sim migrate-database --db <path> --dry-run` and review the plan.

## A model adapter cannot load its dependencies

Run `python -m pip check` in the same activated environment that runs `dj-sim`, then compare the
installed stack with `pyproject.toml` and `uv.lock`. Update the related packages together so the
adapter still has its required APIs, checkpoints, and output shapes.

```powershell
python -m pip check
```

Restart `dj-sim serve` and any running Rhythm Lab process after changing the environment.

## Timeline, SONARA embedding, or fingerprint data is unavailable

This is expected: their collection and public read surfaces are disabled. SONARA analysis stores
Core only. The reserved Artifacts tables are empty layout placeholders, not active output formats.

## A classifier is incompatible

Rebuild and promote an artifact whose ordered feature names and required inputs match the current
data. Classifier scoring is database-only and remains scoped by `classifier_key`.

## CUDA was requested but analysis fails

Run `dj-sim doctor`, then try `--device cpu` to separate device setup from the analysis workflow.

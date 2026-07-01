# Troubleshooting by symptom

> Audience: Users fixing common local setup and workflow problems.
> Goal: Map symptoms to likely causes and safe next steps.
> Type: how-to

## ffmpeg is missing

Install or expose an FFmpeg binary on `PATH`, or set `DJ_TRACK_SIMILARITY_FFMPEG`. Restart the server after changing the environment.

## Analyze finds zero tracks

Check that the database was scanned and that the selected models need missing results. UI `Analyze limit = 0` means whole library; CLI whole-library analysis omits `--limit`.

## CLAP text search is empty

Run CLAP analysis first. Text search needs stored CLAP audio embeddings.

## SET eligible count is low

Run missing MERT, MAEST, CLAP, and SONARA analysis families.

# Troubleshooting by symptom

> Audience: Users fixing local v7 setup or analysis issues.
> Goal: Give checks tied to current storage and release behavior.
> Type: help

## Server says FFmpeg is missing

Set `DJ_TRACK_SIMILARITY_FFMPEG` to an FFmpeg executable or put FFmpeg on `PATH`, then restart
`dj-sim serve`.

## The selected library will not open

A v7 library needs its Core `.sqlite` and mandatory `*.artifacts.sqlite` companion with the same
`catalog_uuid`. Do not substitute old `*.timeline.sqlite` or `*.representations.sqlite` files. v5/v6
databases are not migrated by this runtime.

## SONARA is blocked after an update

Use `prepare-sonara-release` with a backup directory and the exact confirmation. It prepares the
four outputs `core`, `timeline`, `embedding`, and `fingerprint`, records progress for crash resume,
and is not a distributed atomic transaction. Reanalyze SONARA, then retrain/promote/rescore affected
v2 classifier artifacts.

## Timeline, embedding, or fingerprint data is unavailable

Those outputs live in mandatory Artifacts and must be requested explicitly after release
preparation. Core is always included. The frontend v7 port is deferred, so do not infer availability
from current browser dialogs.

## A classifier is incompatible

Manifest v1 and unversioned artifacts are blocked. Rebuild and promote a manifest v2 artifact that
matches the current inputs. Classifier scoring is database-only and remains scoped by `classifier_key`.

## CUDA was requested but analysis fails

Run `dj-sim doctor`, then try `--device cpu` to separate device setup from the analysis workflow.

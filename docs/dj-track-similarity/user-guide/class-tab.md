# Use the CLASS tab

> Audience: Users with promoted Rhythm Lab classifier profiles.
> Goal: Filter, rescore, and use classifier scores without confusing them with analysis families.
> Type: guide

The CLASS tab reads promoted local profiles from `models/classifiers/*/model.json`. A profile is useful in the main UI only when the manifest is valid and compatible with scoring.

## What a promoted classifier is

A promoted classifier consists of:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

The manifest describes the classifier key, labels, model id, calibration status, required inputs, and optional Hybrid signal metadata. Version `2` also requires the exact SONARA analysis signature for any SONARA-dependent feature set.

## Filtering

Each promoted classifier appears with a slider from `0.00` to `1.00`. The library browser can filter tracks by minimum stored score for that classifier.

Missing classifier scores do not pass a positive minimum filter. In SET and Hybrid modifiers, missing scores stay neutral.

## Rescoring

The play button on a classifier row resets and rescans that one classifier key. The UI calls the reset path first, then starts `/api/classifiers/{classifier_key}/analyze`.

Classifier scoring is database-only. It reads exactly the SONARA and MAEST/MERT/CLAP inputs declared
by the promoted manifest and writes `track_classifier_scores`. It never decodes audio and never runs
inside a SONARA or ML job.

Scoring is blocked when the promoted artifact, manifest, and track do not share the same current SONARA signature. Retrain and promote legacy SONARA profiles after reanalysis. Labels and feedback remain available.

## CLASSIFIERS analysis stage

The left panel has an independent **CLASSIFIERS** block. Its manual action scores the selected
compatible profiles. The pipeline action runs it after selected SONARA and ML stages. The UI shows
manifest-specific ready/not-ready counts and blockers. Missing inputs exclude a track before the job
total is formed and do not create a partial score. Empty aggregate selection means all compatible
promoted classifiers.

## SET and Hybrid

SET classifier preferences are signed. Negative values avoid the classifier concept, while positive values prefer it. Flow can stay flat or move upward/downward through the set.

Hybrid preview can use classifier preference and risk metadata when a promoted manifest exposes a compatible signal. The Hybrid details panel shows whether classifier support was available, fresh, stale, missing, or neutral.

## When no profiles appear

Promote a profile from Rhythm Lab or place `model.json` plus `model.joblib` under `models/classifiers/<profile>/`. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md).

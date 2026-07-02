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

The manifest describes the classifier key, labels, model id, calibration status, required inputs, and optional Hybrid signal metadata.

## Filtering

Each promoted classifier appears with a slider from `0.00` to `1.00`. The library browser can filter tracks by minimum stored score for that classifier.

Missing classifier scores do not pass a positive minimum filter. In SET and Hybrid modifiers, missing scores stay neutral.

## Rescoring

The play button on a classifier row resets and rescans that one classifier key. The UI calls the reset path first, then starts `/api/classifiers/{classifier_key}/analyze`.

Classifier scoring is database-only. It reads existing SONARA, MAEST, and MERT inputs and writes `track_classifier_scores`. It does not decode audio unless the same analysis job also needs missing model data.

## CLASSIFIERS in analysis jobs

The left panel has a **CLASSIFIERS** checkbox. When selected, the analysis job can score all promoted classifiers that have missing rows. If required SONARA, MAEST, or MERT inputs are missing, select those models in the same job or analyze them first.

## SET and Hybrid

SET classifier preferences are signed. Negative values avoid the classifier concept, while positive values prefer it. Flow can stay flat or move upward/downward through the set.

Hybrid preview can use classifier preference and risk metadata when a promoted manifest exposes a compatible signal. The Hybrid details panel shows whether classifier support was available, fresh, stale, missing, or neutral.

## When no profiles appear

Promote a profile from Rhythm Lab or place `model.json` plus `model.joblib` under `models/classifiers/<profile>/`. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md).

# Use the CLASS tab

> Audience: Users with promoted Rhythm Lab classifier profiles.
> Goal: Filter, rescore, and use classifier scores without confusing them with analysis families.
> Type: guide

Use a classifier when you keep making the same personal judgment and ordinary tags do not capture
it. Examples include a profile you define for vocal-forward versus mostly instrumental tracks, or
for a specific kind of live instrumentation. Rhythm Lab learns from your labeled examples; the
main app then stores a reusable score for the rest of the compatible library.

This score does not discover an objective fact about music. It reflects a local boundary learned
from one profile and its labels. Use it to reduce review work, then listen to borderline and
important tracks.

For a one-off sound idea, use seed or text search instead. A classifier is most useful when the same
question will return across many sessions.

## What you get in the main app

1. You create and label a profile in Rhythm Lab.
2. Training produces candidate artifacts that you review and promote.
3. The main app scores compatible tracks for that promoted profile.
4. The CLASS tab can filter by the stored score.
5. SET can prefer, avoid, raise, or lower the concept through a preview.

The CLASS tab reads promoted local profiles. A profile appears only when its manifest is valid and
compatible with current scoring inputs.

## How a promoted classifier is stored

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

The left panel includes a standalone **CLASSIFIERS** checkbox. Selecting it clears SONARA and ML
selections; **FULL** is the explicit way to combine all stages in one ordered pipeline. The single
**Analyze** action scores compatible profiles. The UI shows
manifest-specific ready/not-ready counts and blockers. Missing inputs exclude a track before the job
total is formed and do not create a partial score. Empty aggregate selection means all compatible
promoted classifiers.

## SET and Hybrid

SET classifier preferences are signed. Negative values avoid the classifier concept, while positive values prefer it. Flow can stay flat or move upward/downward through the set.

Hybrid preview can use classifier preference and risk metadata when a promoted manifest exposes a compatible signal. The Hybrid details panel shows whether classifier support was available, fresh, stale, missing, or neutral.

## When no profiles appear

Promote a profile from Rhythm Lab or place `model.json` plus `model.joblib` under `models/classifiers/<profile>/`. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md).

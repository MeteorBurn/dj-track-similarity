# Classifier scores and the CLASS tab

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

The backend reads promoted local profiles only when their manifest is valid and compatible with
current scoring inputs. The browser lists those profiles in **CLASS**, shows each profile's blocker
when scoring is unavailable, serializes the minimum-score filters into the library query, and
keeps per-profile rescore actions scoped to the selected `classifier_key`. Standalone Rhythm Lab
also exposes training recipes over every supported feature source and source-readiness
explanations.

## How a promoted classifier is stored

A promoted classifier uses one pointer to an immutable model and manifest
generation:

```text
models/classifiers/<artifact-prefix>/current.json
models/classifiers/<artifact-prefix>/generations/<generation-id>/model.joblib
models/classifiers/<artifact-prefix>/generations/<generation-id>/model.json
```

Promotion verifies and syncs both generation files before atomically switching
`current.json`. Discovery rejects an incomplete generation or any pointer,
manifest, or model hash mismatch.

The manifest describes the classifier key, labels, model id, calibration status, ordered feature
names, and required inputs. A SONARA-dependent feature set names
the SONARA values it uses, while `muq:<index>` and `mulan:<index>` features require the expected
vector dimension.
Artifacts with an incomplete or changed feature recipe remain visible with a blocker until that
profile is retrained and promoted.

## Filtering

Each promoted classifier appears with a slider from `0.00` to `1.00`. The library browser can filter tracks by minimum stored score for that classifier.

Missing classifier scores do not pass a positive minimum filter.

## Rescoring

The play button on a classifier row resets and rescans that one classifier key. The UI calls the reset path first, then starts `/api/classifiers/{classifier_key}/analyze`.

Classifier scoring is database-only. It reads exactly the SONARA and
MAEST/MERT/MuQ/MuQ-MuLan/CLAP inputs declared by the promoted manifest and writes rows in
`classifier_scores`. It never decodes audio and never runs inside a SONARA or ML job.

Scoring is blocked when the promoted artifact's ordered feature recipe does not match the stored
inputs for a track. Retrain and promote affected SONARA profiles after a chosen reanalysis. Labels
and feedback remain available.

## CLASSIFIERS analysis stage

The left panel includes a standalone **CLASSIFIERS** checkbox. Selecting it clears SONARA and ML
selections; **FULL** is the explicit way to combine all stages in one ordered pipeline. The single
**Analyze** action scores compatible profiles. The UI shows
manifest-specific ready/not-ready counts and blockers. Missing inputs exclude a track before the job
total is formed and do not create a partial score. Empty aggregate selection means all compatible
promoted classifiers.

## When no profiles appear

Promote a profile from Rhythm Lab or place `model.json` plus `model.joblib` under `models/classifiers/<profile>/`. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md).

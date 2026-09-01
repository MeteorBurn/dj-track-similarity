# Classifier scores and the CLASS tab

Use a classifier when you keep making the same personal judgment and ordinary tags do not capture
it. Examples include a profile you define for vocal-forward versus mostly instrumental tracks, or
for a specific kind of live instrumentation. Rhythm Lab learns from your labeled examples, and the
main app then stores a reusable score for the rest of the compatible library.

This score does not discover an objective fact about music. It reflects a local boundary learned
from one profile and its labels. Use it to reduce review work, then listen to borderline and
important tracks.

For a one-off sound idea, use seed or text search instead. A classifier is most useful when the same
question will return across many sessions.

The `CLASS` tab is the fifth of the five tabs in panel 3, search and listening. Most of its text is
English on screen. The full label mapping is in [UI language](../help/ui-language.md).

## What you get in the main app

1. You create and label a profile in Rhythm Lab.
2. Training produces candidate artifacts that you review and promote.
3. The main app scores compatible tracks for that promoted profile.
4. The `CLASS` tab filters the library by the stored score.

The `CLASS` tab is not a search surface. It has no `Limit` and no seed. Its sliders add minimum-score
conditions to the library query in panel 2, library and listening, so the filtered result appears in
the track list rather than in a result column.

## How a promoted classifier is stored

Promotion writes a flat pair of files under one directory per profile:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Publication is atomic. The pair is written and fsynced under a staging directory, both hashes are
fenced, the staged classifier is exercised through the production scorer on a zero vector, then
`model.json` is flipped to `publication_status: "publishing"`, `model.joblib` is replaced, and
`model.json` is replaced with the `ready` manifest.

The manifest describes the classifier key, labels, model id, calibration status, ordered feature
names, and required inputs. Feature names follow the grammar `<sonara|mert|maest|clap|muq|mulan>:<key>`.
A SONARA-dependent feature set names the SONARA values it uses, while `muq:<index>` and
`mulan:<index>` features require the expected vector dimension, so a manifest becomes invalid if a
family's dimension changes.

Three independent SHA-256 checks guard the artifact: discovery verifies `model.joblib` against the
manifest hash, the requirements loader re-verifies the file without loading it, and the scorer
hashes the exact bytes it hands to `joblib.load`. A mismatch downgrades the profile to `invalid`
rather than scoring with it.

Artifacts with an incomplete or changed feature recipe remain visible with a blocker until that
profile is retrained and promoted.

## Reading the tab

A summary line at the top reads `available {n} · blocked {n}`.

A blocked profile shows its name, a status badge, and the reason, one of the joined manifest errors,
`Classifier profile is no longer available.`, `Classifier manifest status is <status>.`, or
`Classifier manifest is not compatible with scoring.`

An available profile shows its name, its description from `model.json`, and a row of manifest facts:

| Fact | What it shows |
| --- | --- |
| `Status` | the discovery status |
| `Type` | binary or multiclass |
| `Models` | the feature set, uppercased and joined with `+` |
| `Calibrated` | whether the promoted artifact carries a calibration report |
| `Features` | the feature count |
| `Labels` | the label order |
| `Validation` | holdout F1 as a percentage |
| `Promoted` | the promotion date |

## Filtering

Each promoted classifier carries a slider from `0.00` to `1.00` in steps of `0.01`, starting at `0`,
with the scored-track count beside it as `{n} tracks`. Moving it adds a minimum-score condition to
the library query.

The slider is disabled while the profile has no scores, with the tooltip
`<name> has no current calculated scores. Run classifier scoring first.`

Missing classifier scores do not pass a positive minimum filter.

## Rescoring

The play button on a classifier row is titled
`Reset and rescore all <name> classifier results`. It calls `POST /api/classifiers/reset` with
`{"classifier_key": "<key>"}` first, then starts `POST /api/classifiers/{classifier_key}/analyze`.

That reset is required, and it is the reason the button does both. Classifier scoring is
incremental. Its candidate query excludes every track that already has a row for that classifier
key, so a rescore over an already-scored library finds zero work until the key is reset.

The trash button beside it, titled **Delete the calculated data for `<name>`**, runs the reset
alone. Its confirmation states that only that classifier's calculated scores are deleted, and that
audio files and other classifiers' results remain.

Classifier scoring is database-only. It reads exactly the SONARA and MAEST/MERT/MuQ/MuQ-MuLan/CLAP
inputs declared by the promoted manifest and writes rows in `classifier_scores`, scoped by
`classifier_key`. It never decodes audio and never runs inside a SONARA or ML job. Batches are 200
tracks at a time.

The CLI equivalent is:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

## Not ready is not a failure

A track missing any input the manifest requires is dropped by the candidate query before the job
total is computed, so it is neither counted nor failed. A failure means a scoring exception or a
write error, recorded per track in the job status and shown as `failed {n}` in the tab.

The response shape carries `not_ready`, `skipped`, `already_scored`, and `deleted_stale` counters.
All four are currently hard-coded to `0` and carry no computed value.

Scoring is blocked when the promoted artifact's ordered feature recipe does not match the stored
inputs for a track. Retrain and promote affected SONARA profiles after a chosen reanalysis. Labels
and feedback remain available.

## Where classifier scoring runs

There is no classifier checkbox in panel 1, database and analysis. Analysis stages there come from
the SONARA row and the five ML rows only. Classifier jobs are started from this tab or the CLI, and
they share the same single job queue as SONARA and ML, so only one runs at a time.

## When no profiles appear

The empty state reads
`No promoted classifier profiles found. Promote profiles from Rhythm Lab or place model.json + model.joblib under models/classifiers/<profile>/.`

Promote a profile from Rhythm Lab or place `model.json` plus `model.joblib` under
`models/classifiers/<profile>/`. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md) and
[Train a personal classifier](../workflows/train-personal-classifier.md).

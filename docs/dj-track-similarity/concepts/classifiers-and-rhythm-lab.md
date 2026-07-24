# Classifiers and Rhythm Lab

> Audience: Users building personal classifier scores.
> Goal: Explain labels, training, promotion, and how scores appear in the main app.
> Type: concept

Most analysis models arrive with their own general audio representation. A personal classifier asks
a different question: "can the app reuse a distinction that I make repeatedly?"

One possible profile separates vocal-forward tracks from mostly instrumental tracks. Another could
focus on whether live instrumentation is present. The definition and examples come from your
library. New databases begin without profiles, and the resulting score reflects your labels.

## Why train one

A classifier is useful when a concept:

- matters repeatedly across your library,
- is not captured reliably by existing tags,
- is specific enough that you can label consistent examples,
- should become a filter or a gentle preference rather than a one-time search.

If you only need a list for one session, seed search or CLAP text search is usually less work.

## From examples to a useful control

```text
label examples -> train -> review predictions -> promote -> score library -> filter or steer
```

Promotion does not make the model silently choose music for you. It makes one reviewed profile
available as a score in the main app. Missing and borderline cases still need listening.

Rhythm Lab is the companion tool for local labels, training, prediction review, and promotion.
Promoted classifiers become optional signals in the main UI.

## Profiles

Rhythm Lab supports two profile types:

- **binary**: one positive label and one negative label, plus optional review labels,
- **multiclass**: class labels where one track has one current class label for the active profile.

Labels, predictions, queues, and training checkpoints live in the Rhythm Lab labels database under `tools/rhythm-lab/data/` by default.

Rhythm Lab does not create a built-in starter profile. Existing profiles, including older Break Energy profiles, remain normal profile rows in the labels database, but new labels databases start empty until you create a profile.

## Training inputs

Training uses the feature families declared by the selected profile artifact. Combined training
requires current SONARA Core features plus MERT and MAEST embeddings; a feature set that includes
CLAP also requires stored CLAP audio embeddings. Missing required values make a track ineligible;
they are not zero-imputed.

SONARA inputs must share one current analysis signature. Training skips stale or mixed profiles. A row missing a requested opt-in field is also skipped rather than zero-imputed.

Classifier calibration is optional and data-gated. If there are not enough labels for calibration, training can still produce an uncalibrated artifact with diagnostics.

Calibration is not part of the normal Training UI flow. It is an explicit API or
CLI operation for binary profiles where you want calibrated positive-label
probabilities. The gate currently requires at least 100 training labels, 20
positive labels, and 20 negative labels. Normal UI promotion uses uncalibrated
artifacts; promoting a calibrated artifact should use an explicit CLI
calibration requirement.

## Promotion

Promotion copies the selected artifact into the main app model directory:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

The main app discovers promoted profiles from those manifests. Manifest version `2` records the
exact training inputs, including the SONARA contract when needed. Checked-in version `1` or
unversioned artifacts are blocked from scoring: retrain and promote a v2 artifact instead.

## Scoring

Promoted classifier scoring is database-only. Each manifest identifies the exact current SONARA and
MERT/MAEST/CLAP inputs it needs. The aggregate job writes `classifier_scores` for every
selected compatible classifier-track pair without reading audio.

Readiness is computed before the job total. Missing manifest inputs make a track not ready, not
failed. Existing scores are candidates again when their stored `model_id` differs from the current
promoted manifest. Incompatible promoted artifacts remain visible with a retrain/promote blocker and
are never executed.

Adding or promoting one classifier does not delete scores for other classifier keys. After retraining the same classifier key, reset that classifier's old scores before rescoring. Reanalyzing a track with SONARA invalidates that track's SONARA-dependent scores. A full SONARA reset invalidates all such scores but preserves labels and feedback.

The current project SONARA feature revision is `6`. A changed SONARA contract or revision requires
the ordered `prepare-sonara-release` workflow, then reanalysis, retraining, promotion, and
rescoring for affected profiles. Preparation makes verified Core + Artifacts backups and records a
durable receipt so an interrupted operation can resume. It is ordered and crash-resumable, not a
distributed atomic transaction. Labels, feedback, and embedding-only artifacts remain available;
stale promoted artifacts are visible but cannot score until replaced.

## Current UI status

The backend exposes promoted classifier scores, but the frontend v7 port is deferred. Do not treat
the current CLASS-tab controls or browser workflows as v7-compatible. Missing scores remain neutral
where a backend workflow consumes them. Malformed manifests block scoring with a clear status.

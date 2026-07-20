# Classifiers and Rhythm Lab

> Audience: Users building personal classifier scores.
> Goal: Explain labels, training, promotion, and how scores appear in the main app.
> Type: concept

Rhythm Lab is the companion tool for local labels, training, prediction review, and promotion. Promoted classifiers become optional signals in the main UI.

## Profiles

Rhythm Lab supports two profile types:

- **binary**: one positive label and one negative label, plus optional review labels,
- **multiclass**: class labels where one track has one current class label for the active profile.

Labels, predictions, queues, and training checkpoints live in the Rhythm Lab labels database under `tools/rhythm-lab/data/` by default.

Rhythm Lab does not create a built-in starter profile. Existing profiles, including older Break Energy profiles, remain normal profile rows in the labels database, but new labels databases start empty until you create a profile.

## Training inputs

Training can benchmark SONARA, MERT, MAEST, CLAP, combined, and SONARA 2.0 feature-source variants. Combined training requires existing SONARA features plus MERT and MAEST embeddings. Variants that include CLAP require stored CLAP audio embeddings. The `sonara2` and `sonara2vocal` variants still require stored SONARA features at scoring time.

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

The main app discovers promoted profiles from those manifests. Manifest version `2` records the exact SONARA training signature whenever the feature set depends on SONARA. Older SONARA artifacts must be retrained and promoted again.

## Scoring

Promoted classifier scoring is database-only. It reads existing SONARA, MERT, and MAEST inputs and writes `track_classifier_scores` for one `classifier_key` at a time.

Adding or promoting one classifier does not delete scores for other classifier keys. After retraining the same classifier key, reset that classifier's old scores before rescoring. Reanalyzing a track with SONARA invalidates that track's SONARA-dependent scores. A full SONARA reset invalidates all such scores but preserves labels and feedback.

The project SONARA feature-revision guard also invalidates SONARA-dependent main-library scores when
the main database opens and Rhythm Lab predictions when the labels database opens. Embedding-only derived rows,
labels, and feedback are preserved. Stale promoted artifacts remain visible for recovery but cannot
score until the profile is retrained and promoted with the current signed manifest.

For the SONARA `0.2.9`/schema-v6 transition, follow the ordered
[split-storage workflow](../workflows/reanalyze-sonara-split-storage.md) before retraining or rescoring.

## Main UI use

Promoted scores can appear in:

- the CLASS tab as filter sliders,
- the library metadata dialog,
- SET classifier preference and flow controls,
- Hybrid preview preference/risk diagnostics.

Missing scores stay neutral in SET and Hybrid. Malformed manifests block scoring with a clear status.

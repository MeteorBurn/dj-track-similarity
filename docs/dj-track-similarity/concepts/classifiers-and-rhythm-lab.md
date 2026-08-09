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
CLAP also requires stored CLAP audio embeddings. The legacy `combined` alias remains exactly
`sonara+mert+maest`.

MuQ is a normal embedding feature source. The `muq` set emits ordered `muq:<index>` features from
the dimension expected by the current feature recipe. It can be combined with other sources, for
example as `sonara+muq`, `mert+muq`, or `sonara+mert+maest+clap+muq`. Missing required values make
a track ineligible. Required values are not zero-imputed.

SONARA inputs must provide the ordered feature recipe selected for training. A row missing a
requested opt-in field is skipped rather than zero-imputed.

## Promotion

Promotion publishes the selected artifact through the main app's immutable-generation layout. Each
promoted artifact records its exact ordered feature names and required inputs, including MuQ vector
dimensions for `muq:<index>` features. An incomplete or changed recipe is blocked from scoring until
that profile is retrained and promoted.

## Scoring

Promoted classifier scoring is database-only. Each manifest identifies the exact current SONARA and
MERT/MAEST/CLAP/MuQ inputs it needs. The aggregate job writes `classifier_scores` for every
selected compatible classifier-track pair without reading audio.

Readiness is computed before the job total. Missing manifest inputs make a track not ready, not
failed. Existing scores are candidates again when their stored `model_id` differs from the current
promoted manifest. Incompatible promoted artifacts remain visible with a retrain/promote blocker and
are never executed.

Adding or promoting one classifier does not delete scores for other classifier keys. After retraining the same classifier key, reset that classifier's old scores before rescoring. Reanalyzing a track with SONARA invalidates that track's SONARA-dependent scores. A full SONARA reset invalidates all such scores but preserves labels and feedback.

When a SONARA update changes stored structure, use the explicit backup-first database migration.
Reanalysis, retraining, promotion, and rescoring remain separate choices for affected profiles.
Labels, feedback, and unrelated artifacts remain available.

## Current UI status

The static Rhythm Lab UI shows current/missing/stale state for every source and provides a
**Training recipe** selector for MuQ and arbitrary supported source combinations. Use
`benchmark-ablation` with explicit `--feature-set` values when you need a repeatable CLI matrix.

The main frontend lists promoted profiles in CLASS, serializes minimum-score filters, and exposes
per-profile reset plus rescore. Missing scores remain neutral where SET or Hybrid consumes them.
Malformed manifests stay visible but block scoring with a clear status.

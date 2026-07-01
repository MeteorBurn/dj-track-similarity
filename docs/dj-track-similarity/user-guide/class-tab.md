# Use the CLASS tab

> Audience: Users with promoted Rhythm Lab classifiers.
> Goal: Score personal classifiers and use their results safely.
> Type: how-to

## Discovery

The tab discovers promoted classifier profiles from `models/classifiers/*/model.json`.

## Scoring

Promoted scoring reads existing SONARA features plus MERT and MAEST embeddings, then writes `track_classifier_scores` scoped by classifier key. It does not decode or modify audio.

## Retraining

After retraining and promoting the same classifier key, reset only that classifier's stored scores before rescoring. Other classifier keys should remain untouched.

## SET

Classifier sliders are optional modifiers. Missing scores remain neutral.

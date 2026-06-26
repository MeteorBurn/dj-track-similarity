# CLASS tab and promoted classifiers

Audience: Rhythm Lab users  
Goal: use promoted classifier scores in the main UI  
Type: how-to

The `CLASS` tab discovers promoted local classifier profiles from
`models/classifiers/*/model.json`. A promoted classifier writes scores into the
project database, then those scores become filters or modifiers in UI workflows.

## What the score means

For binary classifier profiles, the user-facing score is the promoted model's
positive-label probability stored in `track_classifier_scores.score`.

Missing scores are neutral in SET. They do not count as a negative judgment.

## Score a promoted classifier

Use the classifier scoring control for one promoted profile. The app should
score only missing rows for that classifier key unless you intentionally reset
that classifier's rows.

After retraining and promoting a new model for the same key, reset only that
classifier's stored scores and rescore it.

## Keep scopes separate

Classifier scoring:

- reads existing SONARA, MERT, and MAEST-derived inputs;
- writes only SQLite `track_classifier_scores`;
- does not decode audio for normal scoring;
- does not clear scores for unrelated classifier keys.

Use [Train a personal classifier](../workflows/train-personal-classifier.md)
for the labeling/training/promotion workflow.

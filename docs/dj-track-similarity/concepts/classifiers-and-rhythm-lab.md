# Classifiers and Rhythm Lab

> Audience: Users deciding whether to train personal models.
> Goal: Explain profiles, labels, training, promotion, and main-app scoring.
> Type: explanation

## Profiles

Binary profiles use exactly one positive and one negative training label plus optional review labels. Multiclass profiles use class labels, one current class per active profile.

## Storage

Lab labels, predictions, and checkpoints stay under `tools/rhythm-lab/data/`. Promoted runtime models live under `models/classifiers/`. Main-app scoring writes `track_classifier_scores` scoped by classifier key.

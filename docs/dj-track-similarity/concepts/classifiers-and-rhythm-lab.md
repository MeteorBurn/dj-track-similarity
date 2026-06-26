# Classifiers and Rhythm Lab

Audience: Rhythm Lab users and developers  
Goal: explain labels, training artifacts, promotion, and scoring  
Type: explanation

Rhythm Lab is the labeling and training side of the classifier workflow. The
main app consumes promoted classifier models and stores scores.

## Two databases

The main library database stores tracks, metadata, analysis inputs, likes, and
promoted classifier scores.

The lab database stores classifier labels, predictions, training checkpoints,
and active-learning queues. Lab state lives under `tools/rhythm-lab/data/` by
default.

## Profile types

- `binary`: one positive label, one negative label, optional review labels.
- `multiclass`: user-defined class labels; one current class per track for the
  active profile.

## Training inputs

Training benchmarks SONARA, MERT, MAEST, and combined feature sets. Combined
training requires SONARA features plus MERT and MAEST embeddings.

## Promotion

Promotion copies the selected combined artifact into
`models/classifiers/<artifact-prefix>/` for the main app. Runtime scoring reads
the promoted manifest and writes scores scoped by classifier key.

## Calibration

Calibration is opt-in. `--calibrate` attempts calibrated training when there
are enough labels. `promote --require-calibration` should be used only when
calibrated production behavior is intentionally required.

# Classifiers and Rhythm Lab

Аудитория: Rhythm Lab users и developers  
Цель: объяснить labels, training artifacts, promotion и scoring  
Тип: explanation

Rhythm Lab - labeling and training side classifier workflow. Main app потребляет
promoted classifier models и хранит scores.

## Two databases

Main library database хранит tracks, metadata, analysis inputs, likes и
promoted classifier scores.

Lab database хранит classifier labels, predictions, training checkpoints и
active-learning queues. Lab state по умолчанию живет в `tools/rhythm-lab/data/`.

## Profile types

- `binary`: один positive label, один negative label, optional review labels.
- `multiclass`: user-defined class labels; один current class per track для
  active profile.

## Training inputs

Training benchmarks SONARA, MERT, MAEST and combined feature sets. Combined
training требует SONARA features plus MERT and MAEST embeddings.

## Promotion

Promotion copies selected combined artifact into
`models/classifiers/<artifact-prefix>/` for main app. Runtime scoring reads
promoted manifest and writes scores scoped by classifier key.

## Calibration

Calibration opt-in. `--calibrate` attempts calibrated training when labels are
enough. `promote --require-calibration` используйте только когда calibrated
production behavior intentionally required.

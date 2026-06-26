# CLASS tab

Аудитория: пользователи promoted classifiers  
Цель: использовать personal classifier scores в main UI  
Тип: how-to

`CLASS` tab показывает controls для promoted local classifier profiles. Profiles
обнаруживаются из `models/classifiers/*/model.json`.

## Requirements

1. Разметьте и обучите profile в Rhythm Lab.
2. Promote combined artifact в main app.
3. Score main library для этого classifier key.

## Как читать scores

User-facing score - это probability positive label для promoted model. Per-label
probabilities остаются в stored JSON.

Missing scores нейтральны для SET modifiers.

## Scoring boundary

Classifier scoring должен быть scoped by `classifier_key`. Scoring одного
profile не должен удалять или recompute scores других profiles.

Если profile retrained/promoted с тем же key, старые scores для этого key могут
быть stale. Сбросьте только этот classifier key перед rescoring.

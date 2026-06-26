# Analyze library

Аудитория: пользователи UI  
Цель: безопасно запускать analysis jobs  
Тип: how-to

Analysis jobs пишут только SQLite metadata, features, embeddings или classifier
scores. Они не переписывают source audio.

## Выбор family

| Family | Что дает |
| --- | --- |
| SONARA | feature-oriented search and SET requirement |
| MERT | seed audio similarity |
| CLAP | text search embeddings |
| MAEST | genre analysis and embeddings |
| Classifier | promoted profile scores |

## Limit

`Analyze limit = 0` означает whole library для missing results выбранной
family. Положительное значение обрабатывает только это число missing results.

## Device

`auto` выбирает CUDA при доступности, иначе CPU. Если явно выбрать CUDA без
доступного GPU, job должен упасть с понятной ошибкой.

## Когда анализировать все

Сначала проверьте маленький limit. Whole-library jobs могут быть долгими,
особенно для ML families.

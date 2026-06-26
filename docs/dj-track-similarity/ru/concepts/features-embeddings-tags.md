# Features, embeddings, and tags

Аудитория: пользователи, сравнивающие analysis families  
Цель: четко разделить data types проекта  
Тип: explanation

App хранит несколько видов информации. В UI они могут выглядеть похожими, но не
являются взаимозаменяемыми.

## File tags

Tags приходят из audio file metadata: title, artist, album, BPM, key и другие
human-facing fields. Scan and RefreshTags читают практический whitelist в
SQLite.

Для Smart Set Builder tag BPM preferred when present. SONARA BPM - fallback.

## SONARA features

SONARA пишет feature values, model metadata и derived working fields вроде BPM,
key, duration, energy в SQLite. Это analyzed values, а не file tags, записанные
обратно в audio.

## Embeddings

MERT, CLAP и MAEST хранят vector embeddings в SQLite. Search и SET могут
использовать эти vectors как similarity signals.

MAEST также производит genre analysis, но SET selection не должен опираться на
MAEST genre labels. MAEST embeddings - другой signal.

## Classifier scores

Promoted classifier profiles пишут scores в `track_classifier_scores`. Score
принадлежит одному classifier key. Missing classifier scores нейтральны для
SET.

## Reports and exports

Reports, playlists и helper-tool output - local files. Это не то же самое, что
library state, и обычно может быть regenerated.

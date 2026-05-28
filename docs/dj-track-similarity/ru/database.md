# База данных и сохраняемые данные

Эта страница документирует текущую SQLite-схему и metadata/analysis payloads,
которые сохраняются в SQLite. Используйте ее, чтобы понять, что приложение
сохраняет, что удаляет reset или почему отдельный режим поиска сначала требует
конкретный analysis pass.

## Спецификация SQLite

Текущая schema version: `2`.

База данных - локальное состояние пользователя. Обычные workflows scan,
analysis, search, reset, clear и relocation изменяют только SQLite records; они
не перезаписывают аудиофайлы. Явное исключение - отдельный workflow записи
MAEST genre tags, описанный в [Поиск и запись тегов](search-and-tags.md).

### `tracks`

Хранит одну строку на индексированный аудиофайл:

- `id`: стабильный локальный track ID.
- `path`: уникальный сохраненный audio path.
- `size`: размер файла на момент scan.
- `mtime`: время изменения файла на момент scan.
- `artist`, `title`, `album`: выбранные file metadata.
- `bpm`, `musical_key`, `energy`, `duration`: рабочие поля для UI и analysis
  flows.
- `metadata_json`: JSON object для Mutagen fields и model-derived metadata.
- `created_at`, `updated_at`: локальные timestamps строки.

`metadata_json` должен быть валидным JSON. Схема содержит triggers, которые
отклоняют invalid JSON при insert или update.

Используйте эту таблицу, чтобы ответить на вопросы "какие треки есть в
библиотеке?" и "какие metadata или analysis summaries UI показывает для row?".
`path` - ссылка обратно на локальный аудиофайл; relocation обновляет только
сохраненный путь, когда те же файлы переехали в новый root.

### `embeddings`

Хранит model vectors по track и embedding space:

- `track_id`: ссылается на `tracks.id`.
- `embedding_key`: сейчас `mert`, `clap` или `maest`.
- `model_name`: идентификатор model или checkpoint.
- `dim`: dimension вектора.
- `vector`: binary float32 vector payload.
- `updated_at`: локальный timestamp строки.

Primary key - `(track_id, embedding_key)`, поэтому один трек может иметь MERT,
CLAP и MAEST vectors без смешивания этих spaces.

Используйте эту таблицу, чтобы проверить, хватает ли данных workflow на основе
embeddings: MERT search требует `mert`, CLAP text search требует `clap`, а
promoted combined classifiers требуют `mert` плюс `maest` вместе с Sonara
features.

### `library_settings`

Хранит локальные database-level settings, например выбранный music root.

Используйте эту таблицу для app-level preferences, привязанных к одной базе, а
не к одному track.

### `track_classifier_scores`

Хранит derived classifier outputs по track и classifier key:

- `track_id`: ссылается на `tracks.id`.
- `classifier`: classifier key, например `live_instrumentation`.
- `score`: основной user-facing score для filtering.
- `label`: coarse label вроде `high`, `medium` или `low`.
- `confidence`: максимальная class probability.
- `probabilities_json`: classifier probabilities по training labels профиля.
- `feature_set`: feature family, использованная classifier artifact, сейчас
  `combined`.
- `model_id`: promoted model path, использованный для scoring.
- `analyzed_at`: локальный scoring timestamp.

Primary key - `(track_id, classifier)`, поэтому повторный запуск classifier
обновляет score для этого track вместо добавления исторических rows.

Используйте эту таблицу, когда CLASS filter ведет себя неожиданно. Missing rows
обычно означают, что promoted classifier еще не оценил track или track не имел
нужных Sonara, MERT или MAEST inputs во время scoring.

## Metadata и analysis data

Приложение намеренно разделяет file tags и computed values.

Mutagen scanning читает фиксированный whitelist:

- `artist`
- `title`
- `album`
- `genre`
- `year`
- `country`
- `label`
- `catalog_number`
- `track_number`
- `disc_number`
- `bpm`
- `key`
- `comment`
- `isrc`
- `duration`
- `audio_format`
- `audio_codec`
- `date`

Values нормализуются в JSON-safe values перед сохранением. Mutagen-specific
objects, например ID3 timestamps, конвертируются в strings.

`RefreshTags` заменяет только этот subset Mutagen metadata. Он сохраняет stored
paths и model analysis data.

Analysis outputs живут рядом с file tags, а не заменяют их. Поэтому track может
показывать одновременно file metadata вроде `genre` или `bpm` и computed values
вроде Sonara BPM, MAEST genres, embeddings или classifier scores.


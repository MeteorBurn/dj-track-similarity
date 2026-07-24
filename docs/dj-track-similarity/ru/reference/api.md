# Справочник API

> Для кого: Пользователи и сопровождающие, автоматизирующие локальное приложение FastAPI.
> Задача: Кратко описать семейства конечных точек и основные правила передаваемых данных.
> Тип: Справочник

API намеренно локальный и не требует аутентификации. Осторожно выбирайте адрес сервера. Используйте
`127.0.0.1`, если не хотите сознательно открыть доступ в локальной сети.

Ниже описан активный контракт бэкенда v7. Клиент React всё ещё использует удалённые структуры до
v7 и пока не перенесён, поэтому совместимость интерфейса здесь не обещается.

## База данных

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/database/current` | текущий выбор SQLite |
| `POST` | `/api/database/switch` | переключение на путь |
| `POST` | `/api/database/dialog` | системный диалог выбора базы |
| `POST` | `/api/database/clear` | удаление строк библиотеки SQLite |

`/api/database/clear` не удаляет аудиофайлы.

Состояние базы возвращает `path`, `artifacts_path`, `evaluation_path`, `catalog_uuid` и `selected`.
Для нового пути создаются Core v7 и обязательная база Artifacts. Evaluation остаётся необязательной.
Комплект не v7 или неполный комплект отклоняется, а не мигрирует.

## Библиотека и медиа

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/library/scan` | запуск сканирования |
| `POST` | `/api/library/tags/refresh` | запуск обновления тегов |
| `POST` | `/api/library/relocate` | предварительная проверка или применение переноса путей |
| `GET` | `/api/library/summary` | количество треков, результатов анализа, отметок и классификаторов |
| `GET` | `/api/tracks` | лёгкие строки треков с пагинацией |
| `POST` | `/api/tracks/filtered` | полный отфильтрованный список для действий с сетом |
| `GET` | `/api/tracks/{track_id}` | полная строка метаданных |
| `GET` | `/api/tracks/{track_id}/sonara-timeline` | явное чтение Timeline |
| `POST` | `/api/tracks/{track_id}/liked` | переключение локальной отметки |
| `GET` | `/media/{track_id}` | поток аудио для прослушивания |

Диапазоны запроса списка: `limit=1..500`, `offset>=0`, `search_mode=like|fts`,
`preset=all|syncopated`.

Конечная точка временных данных возвращает полные сохранённые `beats`, `onset_frames`, `chord_sequence`,
`chord_events`, `tempo_curve`, `energy_curve`, `segments`, `loudness_curve` и `downbeats`. Если
актуальной строки нет, возвращается `{}`, а для неизвестного трека — `404`. Обычный ответ v7
`TrackSummaryV7` содержит составную идентичность (`catalog_uuid`, `track_id`, `track_uuid`,
`content_generation`), `file_path`, компактные теги, `analysis_coverage` и сводки классификаторов.
Подробный ответ содержит `optional_outputs.timeline_fields`, `sonara_embedding_available` и
`audio_fingerprint_available`.

Каждое поле — сериализованный объект, а не исходный массив верхнего уровня:

```json
{
  "energy_curve": {
    "value": [0.31, 0.44, 0.72],
    "type": "list",
    "length": 3
  }
}
```

## Анализ и классификаторы

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | запуск анализа |
| `GET` | `/api/analysis/jobs/latest` | последняя задача |
| `GET` | `/api/analysis/jobs/{job_id}` | состояние задачи |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | запрос отмены |
| `POST` | `/api/analysis/reset` | сброс одного семейства |
| `POST` | `/api/analysis/sonara/releases/prepare` | резервное копирование и активация четырёх результатов загруженного релиза SONARA |
| `GET` | `/api/classifiers` | опубликованные профили |
| `POST` | `/api/classifiers/analyze` | расчёт оценок выбранных классификаторов; пустой список означает все совместимые |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | расчёт оценок одного классификатора |
| `POST` | `/api/classifiers/reset` | удаление выбранных оценок |
| `POST` | `/api/analysis/pipelines` | очередь выбранных этапов в фиксированном порядке |
| `GET` | `/api/analysis/pipelines/latest` | состояние последнего родительского конвейера |
| `GET` | `/api/analysis/pipelines/{job_id}` | состояние родителя и этапов |
| `POST` | `/api/analysis/pipelines/{job_id}/cancel` | отмена текущего и ожидающих этапов |

Тело анализа содержит `models` и `limit`. Для ML добавляются `device`, `top_k`,
`track_batch_size` и `inference_batch_size`; для SONARA — `sonara_outputs` и
`sonara_batch_size`. `classifier_keys` не принимается.

Допустимые результаты SONARA: `core`, `timeline`, `embedding`, `fingerprint`. При отсутствии поля
используется `["core"]`; нормализация всегда включает `core`. SONARA выполняется отдельно, а
планировщик сравнивает контракт каждого результата. В нативный `analyze_batch` передаются пути;
ML-модели используют общее декодирование FFmpeg. Неподготовленный релиз возвращает `409` с
`SONARA_RELEASE_PREPARATION_REQUIRED`.

Тело подготовки:

```json
{
  "backup_dir": "C:\\backups\\dj-track-similarity",
  "confirm": "PREPARE SONARA RELEASE"
}
```

Передать результаты или хеш релиза нельзя. Операция проверяет копии Core и Artifacts и использует
упорядоченный процесс с квитанцией, который можно продолжить после прерывания.

Совокупное тело запроса классификаторов: `{ "classifier_keys": [], "limit": null }`. Готовность зависит от
манифеста; общее количество учитывает готовые пары классификатор–трек, а неготовые пары исключаются и
не считаются ошибками. Конвейер выбирает `sonara`, `ml` и/или `classifiers`, общий лимит и вложенные настройки.
Порядок всегда SONARA, ML, CLASSIFIERS. Ручные и конвейерные этапы используют одну последовательную
очередь приложения.

`GET /api/library/summary` сообщает покрытие SONARA, анализа и эмбеддинга MAEST, MERT, MuQ, CLAP,
отметок и совместимых классификаторов. `analysis_coverage` трека разделяет `sonara_core`,
`timeline`, `sonara_embedding` и `fingerprint`.

Сброс принимает `{ "analysis_family": "sonara" }` или `maest`, `mert`, `muq`, `clap`. Ответ содержит
`core_rows_deleted`, `artifact_rows_deleted` и `classifier_rows_deleted`. Для SONARA удаляются
только зависимые оценки; метки, обратная связь и независимые эмбеддинги сохраняются.

## Поиск и SET

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/search` | поиск по референсным трекам для `maest`, `mert`, `muq` или `clap` |
| `POST` | `/api/search/sonara` | поиск SONARA по референсным трекам |
| `POST` | `/api/search/text` | текстовый поиск CLAP |
| `POST` | `/api/search/hybrid` | взвешенный предварительный результат Hybrid |
| `POST` | `/api/set-builder/generate` | предварительный результат Smart Set Builder |
| `POST` | `/api/reference/compare` | группы Reference Compare для одного референсного трека |
| `POST` | `/api/reference/compare/verdict` | сохранение одного вердикта прослушивания |

Важные диапазоны:

- списки референсных треков для Hybrid и его обратной связи — `1..5` уникальных ID;
- лимиты поиска обычно `1..500`;
- Hybrid `per_source` — `1..100`;
- Hybrid `limit` — `1..100`;
- SET `limit` — `1..500`;
- SET `auto_seed_count` — `1..5`;
- SET `bpm_start` и `bpm_target` — `20..300`, если заданы.

Reference Compare принимает один `seed_track_id`, необязательные `models` из `clap`, `mert`, `muq`,
`maest`, `sonara` и `limit=1..100`. Вердикты: `mood`, `palette`, `instruments`, `groove`, `genre`,
`transition`, `miss`. Они сохраняются как локальная обратная связь под
`reference_compare:<model>`.

## Теги и экспорт

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/export` | запись M3U или CSV |
| `POST` | `/api/tags/genres/apply` | синхронная запись жанра MAEST |
| `POST` | `/api/tags/genres/jobs` | запуск задачи жанровых тегов |
| `GET` | `/api/tags/genres/jobs/latest` | последняя задача жанров |
| `GET` | `/api/tags/genres/jobs/{job_id}` | состояние задачи жанров |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | отмена задачи жанров |
| `POST` | `/api/dialog/folder` | системный диалог папки |

API жанров отклоняет запись отдельного трека. Текущее поведение записывает все доступные
сохранённые жанры MAEST.

## Вспомогательные инструменты

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/audio-doctor/jobs` | запуск Audio Doctor |
| `GET` | `/api/audio-doctor/jobs/latest` | последняя задача Audio Doctor |
| `GET` | `/api/audio-doctor/jobs/{job_id}` | состояние |
| `POST` | `/api/audio-doctor/jobs/{job_id}/cancel` | отмена |
| `GET` | `/api/audio-doctor/jobs/{job_id}/report/xlsx` | скачивание XLSX |
| `POST` | `/api/audio-dedup/jobs` | запуск Audio Dedup |
| `GET` | `/api/audio-dedup/jobs/latest` | последняя задача Audio Dedup |
| `GET` | `/api/audio-dedup/jobs/{job_id}` | состояние |
| `POST` | `/api/audio-dedup/jobs/{job_id}/cancel` | отмена |
| `GET` | `/api/audio-dedup/jobs/{job_id}/report/xlsx` | скачивание XLSX |

Применение Audio Doctor требует `APPLY REPAIR`, Audio Dedup — `APPLY DELETE`.

## Rhythm Lab и сервер

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/rhythm-lab/status` | состояние |
| `POST` | `/api/rhythm-lab/launch` | запуск или повторное использование Rhythm Lab |
| `POST` | `/api/rhythm-lab/stop` | остановка управляемого Rhythm Lab |
| `POST` | `/api/rhythm-lab/collections` | сохранение текущего сета как коллекции |
| `POST` | `/api/server/shutdown` | запрос остановки сервера |

Для остановки требуется заголовок `X-DJ-Track-Similarity-Action: shutdown-server`.

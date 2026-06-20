# Справочник Web API

Эта страница документирует эндпоинты FastAPI, которые использует фронтенд.
Большинству пользователей не нужно вызывать эти эндпоинты напрямую; обращайтесь к
этой странице при отладке веб-интерфейса, интеграции локального скрипта или
проверке того, какое серверное действие выполняет та или иная кнопка UI.

## Справочник Web API

Фронтенд использует эти эндпоинты через `frontend/src/api.ts`.

API ориентирован на локальную работу. Эндпоинты сканирования, анализа, поиска,
предпросмотра, экспорта, сброса, очистки и переноса работают с выбранной базой
данных SQLite и локальными путями файловой системы. Запись в аудиофайлы
происходит только через явные эндпоинты записи MAEST-жанров в теги.

### Соглашения

Эти общие соглашения действуют для всего API:

| Соглашение | Описание |
| --- | --- |
| `400` `DatabaseNotSelected` | Эндпоинт, которому нужна база данных, был вызван до того, как база была выбрана. Сначала выберите её через `/api/database/switch`. |
| `409` `DatabaseBusy` | Попытка переключения базы данных во время задания в состоянии `queued` или `running`. Дождитесь завершения задания или отмените его, затем повторите. |
| `404` | Неизвестный идентификатор трека, задания или медиа. |
| Поле `state` задания | Одно из значений `queued`, `running`, `completed`, `cancelled` или `failed`. |
| Эндпоинты заданий `latest` | Возвращают `null`, если задание этого семейства ещё ни разу не запускалось. |

Длительная работа (сканирование, обновление тегов, multi-model audio analysis,
оценка классификаторами, задания записи жанровых тегов) запускается через
`POST`, который возвращает начальный объект статуса задания.
Затем фронтенд опрашивает соответствующий эндпоинт `jobs/latest` или
`jobs/{job_id}` и может запросить кооперативную отмену.

### База данных

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/database/current` | Вернуть состояние выбранной базы данных. |
| `POST` | `/api/database/switch` | Переключиться на путь базы данных. |
| `POST` | `/api/database/dialog` | Открыть локальный диалог выбора базы данных. |
| `POST` | `/api/database/clear` | Очистить локальные треки SQLite, embeddings и зависимые оценки классификаторов. |

Используйте эти эндпоинты при выборе активной базы данных библиотеки. `clear` —
это операция над базой данных, а не удаление аудиофайлов, но она удаляет индекс
библиотеки и строки анализа из выбранного файла SQLite.

### Библиотека

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/library/scan` | Запустить задание сканирования корневой папки. |
| `POST` | `/api/library/tags/refresh` | Запустить задание обновления Mutagen-тегов. |
| `POST` | `/api/library/relocate` | Просмотреть план или применить перенос сохранённых путей. |
| `GET` | `/api/library/summary` | Вернуть счётчики треков, семейств анализа, понравившихся треков и полного покрытия оценками продвинутых классификаторов. |
| `GET` | `/api/tracks` | Вернуть постраничную страницу треков с поиском. |
| `GET` | `/api/tracks/{track_id}` | Вернуть полные данные одного трека. |
| `POST` | `/api/tracks/{track_id}/liked` | Сохранить или снять локальный флаг «нравится» для одного трека. |
| `POST` | `/api/tracks/filtered` | Вернуть отфильтрованные строки треков для рабочих процессов выбора. |

`/api/tracks` и `/api/tracks/filtered` принимают `preset=syncopated` для
фильтрации по сохранённому флагу синкопированного ритма MAEST. Они принимают
`liked=true`, чтобы показывать только понравившиеся треки, а карты порогов
классификаторов фильтруют треки по сохранённым оценкам классификаторов.

Параметр поиска `q` по умолчанию сохраняет substring `LIKE` поведение. Передайте
`search_mode=fts`, чтобы использовать явный token-based FTS5 index. FTS не ищет
произвольные подстроки внутри token. Он обычно быстрее для count/narrow token
matches, но paged response всё равно сортируется в library order, поэтому
latency первой страницы может меняться для очень частых terms.

Используйте `/api/tracks` для постраничного просмотра, а `/api/tracks/{track_id}`
— только когда диалогу с полными метаданными нужен один трек. Это сохраняет
отзывчивость для больших библиотек.

`/api/library/summary` включает счётчик `classifiers`. Он учитывает трек только
если у трека есть сохранённые строки `track_classifier_scores` для каждого
продвинутого классификатора, обнаруженного из
`models/classifiers/*/model.json`.

`/api/library/relocate` — это эндпоинт с предпросмотром в первую очередь: по
умолчанию он возвращает план переноса и обновляет сохранённые значения
`tracks.path` только при `apply=true`. У него нет кнопки в текущем
веб-интерфейсе и нет метода в `frontend/src/api.ts`; управляйте переносом через
CLI-команду `dj-sim relocate-library` или прямым вызовом API. Применение
отклоняется при наличии конфликтов или отсутствии целевых файлов.

### Задания

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/library/scan/jobs/latest` | Вернуть последнее задание сканирования или обновления тегов. |
| `GET` | `/api/library/scan/jobs/{job_id}` | Вернуть одно задание сканирования. |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | Запросить отмену сканирования. |
| `GET` | `/api/analysis/jobs/latest` | Вернуть последнее multi-model audio analysis задание. |
| `GET` | `/api/analysis/jobs/{job_id}` | Вернуть одно multi-model audio analysis задание. |
| `POST` | `/api/analysis/jobs/{job_id}/cancel` | Запросить отмену multi-model analysis. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | Вернуть последнее задание классификатора. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | Вернуть одно задание классификатора. |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | Запросить отмену классификатора. |
| `GET` | `/api/tags/genres/jobs/latest` | Вернуть последнее задание записи жанровых тегов. |
| `GET` | `/api/tags/genres/jobs/{job_id}` | Вернуть одно задание записи жанровых тегов. |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | Запросить отмену записи жанровых тегов. |

Эндпоинты заданий позволяют фронтенду опрашивать длительную работу и запрашивать
отмену. Отмена является кооперативной: задание может завершить текущий трек или
пакет, прежде чем остановиться.

### Анализ и поиск

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/analysis/jobs` | Запустить одно selected-model audio-analysis задание для SONARA, MAEST, MERT и/или CLAP. |
| `GET` | `/api/classifiers` | Список продвинутых классификаторов из `models/classifiers/*/model.json`. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Запустить оценку классификатором. |
| `POST` | `/api/classifiers/reset` | Удалить сохранённые оценки для указанных ключей классификаторов. |
| `POST` | `/api/analysis/reset` | Сбросить одно семейство анализа. |
| `POST` | `/api/search` | Поиск в пространстве embedding MERT. |
| `POST` | `/api/search/sonara` | Поиск по признакам Sonara. |
| `POST` | `/api/search/text` | Поиск по аудиовекторам CLAP из текста. |
| `POST` | `/api/set-builder/generate` | Сгенерировать упорядоченный preview Smart Set Builder из manual seeds или auto anchors. |

Используйте `/api/analysis/jobs` перед эндпоинтами поиска, если библиотека ещё
не обработана. Request body принимает `models`, `limit`, `device`, `top_k`,
`track_batch_size` и `inference_batch_size`. `models` по умолчанию включает все
четыре аудиомодели (`sonara`, `maest`, `mert`, `clap`) и должен быть непустым
subset. `limit: null` означает все eligible tracks; положительные limits
считают tracks, у которых отсутствует хотя бы одна выбранная модель.

`track_batch_size` управляет тем, сколько декодированных треков задание держит
и обрабатывает вместе. `inference_batch_size` управляет forward-pass batches
MAEST/MERT/CLAP. Значения по умолчанию: `track_batch_size=4` и
`inference_batch_size=24`. Старое единое поле request `batch_size` больше не
принимается.

Analysis job пропускает результаты выбранных моделей, которые уже существуют.
Top-level status использует `total`, `processed`, `analyzed`, `failed` и
`skipped` как track-level counters. `model_progress` хранит per-model counters.
Status responses отдают `track_batch_size` и `inference_batch_size`; legacy
response field `batch_size` больше не выводится.
`current_model` показывает, какая выбранная модель выполняется сейчас. Пустые
результаты поиска часто означают, что у кандидатов отсутствуют нужные признаки
Sonara, embeddings MERT или embeddings CLAP.

`GET /api/classifiers` не требует базы данных; он обнаруживает продвинутые
профили на диске. UI может запускать promoted classifier scoring из того же
analysis control block, что и аудиомодели, через `CLASSIFIERS`; внутри это всё
ещё вызывает `/api/classifiers/{classifier_key}/analyze` для каждого
обнаруженного профиля после завершения выбранного audio-analysis job. Треки без
нужных SONARA, MERT и MAEST inputs пропускаются classifier scoring.
`/api/classifiers/reset` принимает список ключей классификаторов и удаляет их
строки `track_classifier_scores` (пустой список ничего не удаляет).

Default result limit для `/api/search`, `/api/search/sonara` и
`/api/search/text` равен `10`, если request не передаёт `limit`.

`POST /api/set-builder/generate` — read-only endpoint для preview сета. Он не
запускает audio analysis, не считает classifiers, не сохраняет sessions, не
пишет теги и не меняет аудиофайлы. Он использует только сохранённые MERT,
MAEST и CLAP audio embeddings, сохранённые SONARA playlist features и
необязательные сохранённые promoted-classifier scores. MAEST genre labels не
участвуют в выборе кандидатов.

Поля запроса:

- `seed_mode`: `manual` или `auto`. Manual mode требует `1-5`
  `seed_track_ids`; auto mode выбирает `1-5` связанных anchors из
  feature-complete tracks.
- `seed_track_ids`: ID manual seed-треков. В auto mode игнорируется.
- `auto_seed_count`: сколько связанных anchors выбрать в auto mode, `1-5`.
- `mode`: `similar_crate`, `weird_adjacent`, `balanced_set` или `discovery`.
- `limit`: длина preview, по умолчанию `24`.
- `diversity`: `0.0-1.0`, используется при упорядочивании.
- `energy_curve`: `warmup`, `balanced`, `peak` или `wave`.
- `bpm_mode`: `general`, `low_to_high` или `high_to_low`. `general`
  оставляет прежнее мягкое BPM/key transition поведение без отдельной
  траектории темпа.
- `bpm_change`: `slow`, `medium` или `fast`; используется только когда
  `bpm_mode` не `general`.
- `bpm_start`, `bpm_target`: необязательные значения `20-300` BPM для
  траектории темпа. Если поле пустое, builder выводит значение из первого
  seed/anchor и доступного BPM-диапазона библиотеки.
- `classifier_targets`, `classifier_avoid`: карты от promoted
  `classifier_key` к threshold `0.0-1.0`.
- `classifier_curves`: карты от promoted `classifier_key` к `{start, end}`
  целевым значениям intensity.
- `random_seed`: необязательное целое число для воспроизведения одной
  randomized generation. Не передавайте его, если нужен свежий случайный
  auto/ordering pass.

Ответ включает `seed_track_ids`, счётчики покрытия признаков и ordered `items`.
Каждый item содержит `track`, `reason`, `score`, `score_breakdown`,
`sonara_groups`, `classifier_scores` и transition metadata. Seeds или auto
anchors входят в возвращённую последовательность с `reason=seed_anchor`.

Треки без обязательных MERT, MAEST, CLAP или SONARA inputs исключаются из
генерации кандидатов. Отсутствующие classifier scores допустимы: они дают
нейтральный вклад классификатора и более низкую classifier confidence в
объяснении score. BPM/key ordering мягкий: сначала используются file tags, при
их отсутствии — SONARA fallback. Если выбран явный BPM mode, фактический BPM
трека дополнительно участвует в low-to-high или high-to-low tempo curve;
отсутствующий BPM остаётся нейтральным, а не исключает трек. Ordered preview
также соблюдает строгий artist guard: один известный исполнитель может
появиться в одном preview максимум один раз. Manual seeds входят в ответ как
`seed_anchor`, но повтор известного исполнителя среди manual seeds отклоняется.
Auto anchors и остальные позиции семплируются из mode-scored pools, поэтому
повторные вызовы без `random_seed` могут возвращать разные, но связанные сеты.

Область сброса по семействам:

| Сброс | Что удаляет |
| --- | --- |
| `/api/analysis/reset` `sonara` | Ключи метаданных `sonara_*`; пересчитывает сохранённые BPM/тональность/энергию/длительность из оставшихся метаданных. |
| `/api/analysis/reset` `maest` | Ключи метаданных `maest_*` плюс embeddings `maest`. |
| `/api/analysis/reset` `mert` / `clap` | Embeddings соответствующего ключа. |
| `/api/classifiers/reset` | Строки `track_classifier_scores` для перечисленных ключей классификаторов. |

### Экспорт, теги, диалоги, медиа

| Метод | Путь | Назначение |
| --- | --- | --- |
| `POST` | `/api/export` | Экспортировать выбранные треки как M3U или CSV. |
| `POST` | `/api/tags/genres/apply` | Синхронно записать MAEST-жанры во все треки, у которых есть MAEST-жанры. |
| `POST` | `/api/tags/genres/jobs` | Запустить отменяемое фоновое задание записи MAEST-жанров в теги. |
| `POST` | `/api/dialog/folder` | Открыть диалог выбора папки. |
| `GET` | `/media/{track_id}` | Отдать воспроизводимое в браузере аудио для одного трека. |

Оба эндпоинта записи жанровых тегов применяются ко всем трекам, у которых есть
сохранённые MAEST-жанры. Они не принимают подмножество треков: тело запроса с
`track_ids` отклоняется с HTTP `400`. Это явный путь записи в аудиофайл, и он
перезаписывает только стандартное поле жанра.

Плеер предпросмотра во фронтенде использует `/media/{track_id}` и запускает
воспроизведение после нажатия кнопки предпросмотра. Ответы AIFF/AIF
транскодируются во временные файлы WAV для совместимости с браузером и поддержки
перемотки без перезаписи исходного аудио. Если подготовка preview не удалась,
например FFmpeg отклонил поврежденный файл, endpoint возвращает HTTP `422` с
текстом ошибки FFmpeg вместо внутреннего traceback.

Используйте `/api/export` для файлов плейлистов и отчётов. Предпочитайте
`/api/tags/genres/jobs` для записи жанров, чтобы были доступны прогресс и отмена;
синхронный `/api/tags/genres/apply` возвращает по одной строке результата на
трек, но блокируется до завершения всего пакета.

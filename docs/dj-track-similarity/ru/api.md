# Справочник Web API

Эта страница документирует FastAPI endpoints, используемые frontend. Большинству
пользователей не нужно вызывать эти endpoints напрямую; используйте страницу
для debugging web UI, интеграции local script или проверки, какое backend action
использует UI button.

## Справочник Web API

Frontend вызывает эти endpoints через `frontend/src/api.ts`.

API local-first. Endpoints для scan, analyze, search, preview, export, reset,
clear или relocate работают с выбранной SQLite database и local filesystem
paths. Запись в аудиофайлы происходит только через явные MAEST genre tag
endpoints.

### Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | Вернуть состояние выбранной database. |
| `POST` | `/api/database/switch` | Переключиться на database path. |
| `POST` | `/api/database/dialog` | Открыть локальный dialog выбора database. |
| `POST` | `/api/database/clear` | Очистить local SQLite tracks, embeddings и dependent classifier scores. |

Используйте эти endpoints при выборе active library database. `clear` - database
operation, а не удаление аудиофайлов, но он удаляет library index и analysis
rows из выбранного SQLite file.

### Library

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | Запустить scan job для root folder. |
| `POST` | `/api/library/tags/refresh` | Запустить Mutagen tag refresh job. |
| `POST` | `/api/library/relocate` | Preview или apply stored path relocation. |
| `GET` | `/api/library/summary` | Вернуть counters для tracks и analysis families. |
| `GET` | `/api/tracks` | Вернуть paginated/searchable track page. |
| `GET` | `/api/tracks/{track_id}` | Вернуть один full track payload. |
| `POST` | `/api/tracks/filtered` | Вернуть filtered track rows для selection workflows. |

`/api/tracks` и `/api/tracks/filtered` принимают `preset=syncopated`, чтобы
фильтровать по stored MAEST syncopated-rhythm flag. Они также принимают
classifier threshold maps для filtering tracks по stored classifier scores.

Используйте `/api/tracks` для paged browsing, а `/api/tracks/{track_id}` только
когда full metadata dialog нужен один track. Это сохраняет responsiveness для
больших libraries.

### Jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/library/scan/jobs/latest` | Вернуть latest scan или tag-refresh job. |
| `GET` | `/api/library/scan/jobs/{job_id}` | Вернуть одну scan job. |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | Запросить scan cancellation. |
| `GET` | `/api/analyze/jobs/latest` | Вернуть latest MERT/CLAP analysis job. |
| `GET` | `/api/analyze/jobs/{job_id}` | Вернуть одну MERT/CLAP analysis job. |
| `POST` | `/api/analyze/jobs/{job_id}/cancel` | Запросить MERT/CLAP cancellation. |
| `GET` | `/api/sonara/analyze/jobs/latest` | Вернуть latest Sonara job. |
| `GET` | `/api/sonara/analyze/jobs/{job_id}` | Вернуть одну Sonara job. |
| `POST` | `/api/sonara/analyze/jobs/{job_id}/cancel` | Запросить Sonara cancellation. |
| `GET` | `/api/genres/analyze/jobs/latest` | Вернуть latest MAEST job. |
| `GET` | `/api/genres/analyze/jobs/{job_id}` | Вернуть одну MAEST job. |
| `POST` | `/api/genres/analyze/jobs/{job_id}/cancel` | Запросить MAEST cancellation. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | Вернуть latest classifier job. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | Вернуть одну classifier job. |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | Запросить classifier cancellation. |
| `GET` | `/api/tags/genres/jobs/latest` | Вернуть latest genre tag write job. |
| `GET` | `/api/tags/genres/jobs/{job_id}` | Вернуть одну genre tag write job. |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | Запросить genre tag write cancellation. |

Job endpoints позволяют frontend poll long-running work и запрашивать
cancellation. Cancellation cooperative: job может закончить текущий track или
batch перед остановкой.

### Analysis and search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analyze` | Запустить MERT или CLAP embedding analysis. |
| `POST` | `/api/sonara/analyze` | Запустить Sonara feature analysis. |
| `POST` | `/api/genres/analyze` | Запустить MAEST genre analysis. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Запустить classifier scoring. |
| `POST` | `/api/analysis/reset` | Reset одного analysis family. |
| `POST` | `/api/search` | Search in MERT embedding space. |
| `POST` | `/api/search/sonara` | Search with Sonara features. |
| `POST` | `/api/search/text` | Search CLAP audio vectors from text. |

Используйте analysis endpoints перед search endpoints, если library еще не
processed. Empty search results часто означают, что у candidate tracks нет
нужных Sonara features, MERT embeddings или CLAP embeddings.

### Export, tags, dialogs, media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/export` | Export selected tracks as M3U or CSV. |
| `POST` | `/api/tags/genres/apply` | Apply MAEST genres immediately. |
| `POST` | `/api/tags/genres/jobs` | Start cancellable MAEST genre tag write job. |
| `POST` | `/api/dialog/folder` | Open a folder chooser dialog. |
| `GET` | `/media/{track_id}` | Serve browser-playable audio for one track. |

Frontend preview player использует `/media/{track_id}` и запускает playback
после click по preview button. AIFF/AIF responses транскодируются во временные
WAV files для browser compatibility и scrubbing support без перезаписи source
audio.

Используйте `/api/export` для playlist/report files. Используйте
`/api/tags/genres/jobs` для больших genre writes, чтобы были progress и
cancellation; оставляйте `/api/tags/genres/apply` для немедленных малых writes.


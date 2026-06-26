# API reference

Аудитория: developers и frontend integrators  
Цель: показать current endpoint groups и main payload models  
Тип: reference

FastAPI app создается через `dj_track_similarity.api:create_app`. Она mounts
built docs at `/docs`, если существует `docs/dj-track-similarity/site`, и
frontend bundle at `/`, если существует `frontend/dist`.

## Database and library

| Endpoint | Purpose |
| --- | --- |
| `GET /api/database/current` | current selected database |
| `POST /api/database/switch` | switch database path |
| `POST /api/database/dialog` | open native database dialog |
| `POST /api/library/scan` | start scan job |
| `POST /api/library/tags/refresh` | refresh stored tag metadata |
| `POST /api/library/relocate` | preview/apply stored path relocation |
| `POST /api/database/clear` | clear selected database state |
| `GET /api/tracks` | paginated/searchable lightweight track rows |
| `GET /api/tracks/{track_id}` | full track details |
| `POST /api/tracks/{track_id}/liked` | toggle liked state |
| `GET /api/library/summary` | library counters |
| `GET /media/{track_id}` | local media preview |

## Analysis and classifiers

| Endpoint | Purpose |
| --- | --- |
| `POST /api/analysis/jobs` | start analysis job |
| `GET /api/analysis/jobs/latest` | latest analysis job |
| `GET /api/analysis/jobs/{job_id}` | job status |
| `POST /api/analysis/jobs/{job_id}/cancel` | cancel job |
| `POST /api/analysis/reset` | reset selected analysis state |
| `GET /api/classifiers` | promoted classifiers |
| `POST /api/classifiers/{classifier_key}/analyze` | score one classifier |
| `POST /api/classifiers/reset` | reset classifier scores |
| `GET /api/classifiers/{classifier_key}/calibration-report` | report |
| `GET /api/classifiers/{classifier_key}/label-suggestions` | suggestions |

## Search and SET

| Endpoint | Purpose |
| --- | --- |
| `POST /api/search` | MERT seed search |
| `POST /api/search/sonara` | SONARA feature search |
| `POST /api/search/text` | CLAP text search |
| `POST /api/search/hybrid` | weighted hybrid search |
| `POST /api/set-builder/generate` | Smart Set Builder preview |

## Export, tags, tools

| Endpoint | Purpose |
| --- | --- |
| `POST /api/export` | export selected/current set |
| `POST /api/tags/genres/apply` | explicit standard genre write |
| `POST /api/tags/genres/jobs` | genre tag write job |
| `POST /api/audio-dedup/jobs` | duplicate report/apply job |
| `GET /api/audio-dedup/jobs/{job_id}/report/xlsx` | XLSX report |
| `GET /api/rhythm-lab/status` | lab process status |
| `POST /api/rhythm-lab/launch` | launch lab |
| `POST /api/rhythm-lab/stop` | stop lab |
| `POST /api/dialog/folder` | native folder dialog |

## Important request models

`AnalysisJobRequest` includes `limit`, `models`, `classifier_keys`, `device`,
`top_k`, `track_batch_size` and `inference_batch_size`.

`SetBuilderGenerateRequest` includes seed mode, auto anchor count, set mode,
limit, diversity, energy curve, BPM mode/change/start/target and classifier
preferences/flows.

`AudioDedupJobRequest` includes root/path filters, preset, thresholds, group
limit, output directory, apply flag and confirmation text.

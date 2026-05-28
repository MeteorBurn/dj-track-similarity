# Web API Reference

This page documents the FastAPI endpoints used by the frontend.

## Web API Reference

The frontend uses these endpoints through `frontend/src/api.ts`.

### Database

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/database/current` | Return selected database state. |
| `POST` | `/api/database/switch` | Switch to a database path. |
| `POST` | `/api/database/dialog` | Open a local database chooser dialog. |
| `POST` | `/api/database/clear` | Clear local SQLite tracks, embeddings, and dependent classifier scores. |

### Library

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/library/scan` | Start a scan job for a root folder. |
| `POST` | `/api/library/tags/refresh` | Start a Mutagen tag refresh job. |
| `POST` | `/api/library/relocate` | Preview or apply stored path relocation. |
| `GET` | `/api/library/summary` | Return counters for tracks and analysis families. |
| `GET` | `/api/tracks` | Return a paginated/searchable track page. |
| `GET` | `/api/tracks/{track_id}` | Return one full track payload. |
| `POST` | `/api/tracks/filtered` | Return filtered track rows for selection workflows. |

`/api/tracks` and `/api/tracks/filtered` accept `preset=syncopated` to filter on
the stored MAEST syncopated-rhythm flag. They also accept classifier threshold
maps to filter tracks by stored classifier scores.

### Jobs

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/library/scan/jobs/latest` | Return latest scan or tag-refresh job. |
| `GET` | `/api/library/scan/jobs/{job_id}` | Return one scan job. |
| `POST` | `/api/library/scan/jobs/{job_id}/cancel` | Request scan cancellation. |
| `GET` | `/api/analyze/jobs/latest` | Return latest MERT/CLAP analysis job. |
| `GET` | `/api/analyze/jobs/{job_id}` | Return one MERT/CLAP analysis job. |
| `POST` | `/api/analyze/jobs/{job_id}/cancel` | Request MERT/CLAP cancellation. |
| `GET` | `/api/sonara/analyze/jobs/latest` | Return latest Sonara job. |
| `GET` | `/api/sonara/analyze/jobs/{job_id}` | Return one Sonara job. |
| `POST` | `/api/sonara/analyze/jobs/{job_id}/cancel` | Request Sonara cancellation. |
| `GET` | `/api/genres/analyze/jobs/latest` | Return latest MAEST job. |
| `GET` | `/api/genres/analyze/jobs/{job_id}` | Return one MAEST job. |
| `POST` | `/api/genres/analyze/jobs/{job_id}/cancel` | Request MAEST cancellation. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/latest` | Return latest classifier job. |
| `GET` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}` | Return one classifier job. |
| `POST` | `/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel` | Request classifier cancellation. |
| `GET` | `/api/tags/genres/jobs/latest` | Return latest genre tag write job. |
| `GET` | `/api/tags/genres/jobs/{job_id}` | Return one genre tag write job. |
| `POST` | `/api/tags/genres/jobs/{job_id}/cancel` | Request genre tag write cancellation. |

### Analysis and Search

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/analyze` | Start MERT or CLAP embedding analysis. |
| `POST` | `/api/sonara/analyze` | Start Sonara feature analysis. |
| `POST` | `/api/genres/analyze` | Start MAEST genre analysis. |
| `POST` | `/api/classifiers/{classifier_key}/analyze` | Start classifier scoring. |
| `POST` | `/api/analysis/reset` | Reset one analysis family. |
| `POST` | `/api/search` | Search in MERT embedding space. |
| `POST` | `/api/search/sonara` | Search with Sonara features. |
| `POST` | `/api/search/text` | Search CLAP audio vectors from text. |

### Export, Tags, Dialogs, Media

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/export` | Export selected tracks as M3U or CSV. |
| `POST` | `/api/tags/genres/apply` | Apply MAEST genres immediately. |
| `POST` | `/api/tags/genres/jobs` | Start cancellable MAEST genre tag write job. |
| `POST` | `/api/dialog/folder` | Open a folder chooser dialog. |
| `GET` | `/media/{track_id}` | Serve browser-playable audio for one track. |

The frontend preview player uses `/media/{track_id}` and starts playback after a
preview button click. AIFF/AIF responses are transcoded to temporary WAV files
for browser compatibility and scrubbing support without rewriting source audio.

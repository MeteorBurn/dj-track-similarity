# Configuration reference

Аудитория: power users и developers  
Цель: перечислить runtime paths, ports and environment variables  
Тип: reference

## Common ports

| Component | Default |
| --- | --- |
| Main FastAPI server | `127.0.0.1:8765` |
| Frontend Vite dev server | `127.0.0.1:5173` |
| Rhythm Lab | `127.0.0.1:8777` |

Перед запуском local UI/server process проверьте, не занят ли intended port.

## FFmpeg

Server и robust audio decoding требуют FFmpeg. Добавьте `ffmpeg` в `PATH` или
задайте:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

Matching `ffprobe` resolved near FFmpeg when available.

## Logging environment variables

| Variable | Purpose |
| --- | --- |
| `DJ_TRACK_SIMILARITY_LOG` | log file path |
| `DJ_TRACK_SIMILARITY_LOG_LEVEL` | default log level |
| `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS` | enable track event logs |
| `DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS` | enable analysis diagnostics |

## Documentation build

Docs VitePress root is `docs/dj-track-similarity`.

```powershell
cd docs\dj-track-similarity
npm run build
```

Generated site is `docs/dj-track-similarity/site` and served by main backend at
`/docs/`.

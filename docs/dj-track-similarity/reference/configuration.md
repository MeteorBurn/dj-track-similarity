# Configuration reference

Audience: power users and developers  
Goal: list runtime paths, ports, and environment variables  
Type: reference

## Common ports

| Component | Default |
| --- | --- |
| Main FastAPI server | `127.0.0.1:8765` |
| Frontend Vite dev server | `127.0.0.1:5173` |
| Rhythm Lab | `127.0.0.1:8777` |

Before starting a local UI/server process, check whether the intended port is
already in use.

## FFmpeg

The server and robust audio decoding require FFmpeg. Either put `ffmpeg` on
`PATH` or set:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

The matching `ffprobe` is resolved near FFmpeg when available.

## Logging environment variables

| Variable | Purpose |
| --- | --- |
| `DJ_TRACK_SIMILARITY_LOG` | log file path |
| `DJ_TRACK_SIMILARITY_LOG_LEVEL` | default log level |
| `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS` | enable track event logs |
| `DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS` | enable analysis diagnostics |

## Documentation build

The docs VitePress root is `docs/dj-track-similarity`.

```powershell
cd docs\dj-track-similarity
npm run build
```

The generated site is `docs/dj-track-similarity/site` and is served by the main
backend at `/docs/`.

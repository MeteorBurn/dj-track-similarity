# Troubleshooting

Аудитория: users and power users  
Цель: diagnose common local setup and workflow failures  
Тип: how-to

## `ffmpeg is required`

Install FFmpeg and put it on `PATH`, or set:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

Then restart shell/server.

## `dj-sim` is not found

Activate project environment and install package:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
dj-sim --help
```

All following commands assume active environment.

## UI opens but shows no tracks

Check that selected database contains scanned tracks:

```powershell
dj-sim scan <music-library> --db .\data\library.sqlite
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Also verify UI connected to expected database in database selector/status area.

## Search returns no results

Check required analysis:

- SONARA search needs SONARA features.
- MERT seed search needs MERT embeddings.
- CLAP text search needs CLAP embeddings.
- SET needs SONARA plus MERT, MAEST and CLAP audio embeddings.
- CLASS needs promoted classifier scores for selected classifier.

## CUDA requested but unavailable

Use `--device auto` or `--device cpu`, or install matching CUDA PyTorch stack.
Explicit `cuda` expected to fail when PyTorch cannot see GPU.

## Port already in use

Default main server port is `8765`, Vite is `5173`, Rhythm Lab is `8777`. Stop
existing process or choose another port.

## Audio dedup or repair looks risky

Stay in report/dry-run mode. Do not use `--apply` until selected paths, reports,
backups and confirmation boundary are clear.

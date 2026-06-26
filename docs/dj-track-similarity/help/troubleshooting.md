# Troubleshooting

Audience: users and power users  
Goal: diagnose common local setup and workflow failures  
Type: how-to

## `ffmpeg is required`

Install FFmpeg and put it on `PATH`, or set:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

Then restart the shell/server.

## `dj-sim` is not found

Activate the project environment and install the package:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
dj-sim --help
```

All following commands assume the environment is active.

## The UI opens but shows no tracks

Check that the selected database contains scanned tracks:

```powershell
dj-sim scan <music-library> --db .\data\library.sqlite
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Also verify the UI is connected to the expected database in the database
selector/status area.

## Search returns no results

Check the required analysis:

- SONARA search needs SONARA features.
- MERT seed search needs MERT embeddings.
- CLAP text search needs CLAP embeddings.
- SET needs SONARA plus MERT, MAEST, and CLAP audio embeddings.
- CLASS needs promoted classifier scores for the selected classifier.

## CUDA was requested but is unavailable

Use `--device auto` or `--device cpu`, or install a matching CUDA PyTorch stack.
Explicit `cuda` is expected to fail when PyTorch cannot see a GPU.

## Port is already in use

The default main server port is `8765`, Vite is `5173`, and Rhythm Lab is
`8777`. Stop the existing process or choose another port.

## Audio dedup or repair looks risky

Stay in report/dry-run mode. Do not use `--apply` until the selected paths,
reports, backups, and confirmation boundary are clear.

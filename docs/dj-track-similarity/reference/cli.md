# CLI reference

Audience: power users and developers  
Goal: list current command groups and common flags  
Type: reference

Activate the project environment once before running project commands:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

## Root command

```powershell
dj-sim --help
```

Current root commands include:

- `scan`
- `relocate-library`
- `analyze`
- `analyze-classifier`
- `doctor`
- `text-search`
- `serve`

Current subcommand groups include:

- `eval`
- `classifier`
- `index`

## Scan

```powershell
dj-sim scan <music-root> --db .\data\library.sqlite
```

`scan` reads supported audio metadata and writes/updates SQLite rows.

## Relocate library paths

```powershell
dj-sim relocate-library <old-root> <new-root> --db .\data\library.sqlite
dj-sim relocate-library <old-root> <new-root> --apply --db .\data\library.sqlite
```

Without `--apply`, relocation previews path changes. With `--apply`, it updates
stored SQLite paths only. It does not move, copy, delete, or retag audio.

## Analyze

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

Important options:

- `--models` selects analysis families and defaults to
  `sonara,maest,mert,clap`.
- `--device` defaults to `auto`.
- `--limit 0` means whole library for the selected missing work.
- `--top-k`, `--track-batch-size`, and `--inference-batch-size` tune batch
  behavior.
- `--diagnostics` enables analysis diagnostics for the run.

## Classifier scoring

```powershell
dj-sim analyze-classifier live_instrumentation --limit 25 --db .\data\library.sqlite
```

Classifier scores are scoped by classifier key.

## Text search

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" `
  --limit 5 `
  --db .\data\library.sqlite
```

Text search needs CLAP embeddings.

## Serve

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Useful options:

- `--log-level`
- `--log-track-events`

The server requires FFmpeg on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`.

## ANN sidecar indexes

```powershell
dj-sim index --help
```

The `index` group includes `build`, `verify`, `benchmark`, and `clear` for
optional persistent ANN sidecar indexes.

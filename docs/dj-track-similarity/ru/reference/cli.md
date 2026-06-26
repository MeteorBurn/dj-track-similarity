# CLI reference

Аудитория: power users и developers  
Цель: перечислить current command groups и common flags  
Тип: reference

Перед project commands активируйте environment один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

## Root command

```powershell
dj-sim --help
```

Current root commands:

- `scan`
- `relocate-library`
- `analyze`
- `analyze-classifier`
- `doctor`
- `text-search`
- `serve`

Current subcommand groups:

- `eval`
- `classifier`
- `index`

## Scan

```powershell
dj-sim scan <music-root> --db .\data\library.sqlite
```

`scan` читает supported audio metadata и writes/updates SQLite rows.

## Relocate library paths

```powershell
dj-sim relocate-library <old-root> <new-root> --db .\data\library.sqlite
dj-sim relocate-library <old-root> <new-root> --apply --db .\data\library.sqlite
```

Без `--apply` relocation previews path changes. С `--apply` обновляет только
stored SQLite paths. Оно не move, copy, delete или retag audio.

## Analyze

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

Important options:

- `--models` выбирает analysis families и defaults to `sonara,maest,mert,clap`.
- `--device` defaults to `auto`.
- `--limit 0` means whole library for selected missing work.
- `--top-k`, `--track-batch-size`, `--inference-batch-size` tune batch
  behavior.
- `--diagnostics` enables analysis diagnostics for the run.

## Classifier scoring

```powershell
dj-sim analyze-classifier live_instrumentation --limit 25 --db .\data\library.sqlite
```

Classifier scores scoped by classifier key.

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

Server requires FFmpeg on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`.

## ANN sidecar indexes

```powershell
dj-sim index --help
```

`index` group includes `build`, `verify`, `benchmark` and `clear` for optional
persistent ANN sidecar indexes.

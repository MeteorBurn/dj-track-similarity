# Архитектура и среда выполнения

Эта страница описывает backend, frontend, runtime dependencies и поведение
логирования.

## Архитектура

Backend package находится в `src/dj_track_similarity/`.

- `cli.py` предоставляет Typer CLI `dj-sim`.
- `api.py` создает FastAPI app и REST endpoints.
- `database.py` отвечает за доступ к SQLite и все database mutations.
- `db_schema.py` определяет текущую SQLite-схему и validation.
- `scanner.py` сканирует папки и читает Mutagen metadata.
- `scan_jobs.py`, `analysis_jobs.py`, `sonara_jobs.py`, `genre_jobs.py`,
  `classifier_jobs.py` и `tags.py` управляют cancellable jobs и status objects.
- `audio_loader.py` предоставляет общий native-first audio loading.
- `sonara_features.py` извлекает сфокусированный набор Sonara playlist features.
- `sonara_similarity.py` и `sonara_similarity_scoring.py` ранжируют похожесть
  Sonara features.
- `embedding.py` содержит MERT и CLAP embedding adapters.
- `genres.py` содержит MAEST genre adapter.
- `classifier_scoring.py` загружает promoted classifier artifacts и оценивает
  feature-complete tracks.
- `search.py` выполняет similarity search в embedding space.
- `exporter.py` пишет M3U и CSV outputs.
- `runtime.py` выбирает `auto`, `cpu` или `cuda` для PyTorch tasks.
- `dependencies.py` проверяет runtime dependencies, например `ffmpeg`.
- `logging_config.py` настраивает rotating file logs.

Frontend находится в `frontend/src/`.

- `api.ts` зеркалит FastAPI contract.
- `App.tsx` координирует app state и workflows.
- `LibraryPanel.tsx` содержит scan, refresh, analysis, reset и clear controls.
- `TrackPanel.tsx`, `TrackRows.tsx` и `TrackMetadataDialog.tsx` показывают rows
  библиотеки и details треков.
- `SearchPlaylistPanel.tsx` содержит tabs SONARA, MERT, CLAP и CLASS, а также
  export controls.

## Runtime dependencies

Основные runtime dependencies объявлены в `pyproject.toml`:

- `numpy>=1.26,<2.0`
- `mutagen`
- `pydantic`
- `typer`
- `fastapi`
- `uvicorn`
- `joblib`

Optional groups:

- `sonara`: устанавливает поддержку Sonara.
- `ml`: устанавливает синхронизированный стек PyTorch/Torchaudio/Torchvision/
  TorchCodec, Transformers, Hugging Face Hub, LAION-CLAP и MAEST.
- `rhythm-lab`: устанавливает scikit-learn для локального обучения
  классификаторов и benchmarking в Rhythm Lab.
- `dev`: устанавливает pytest и Ruff.

`ffmpeg` требуется для надежного запуска сервера и декодирования аудио. Он
может находиться через `PATH` или задаваться переменной:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

Проверенный Windows CUDA stack:

- PyTorch `2.11.0`
- Torchaudio `2.11.0`
- Torchvision `0.26.0`
- TorchCodec `0.13.0`
- NumPy `>=1.26,<2.0`
- PyTorch wheel index `https://download.pytorch.org/whl/cu130`

Установите matching CUDA wheels из официального PyTorch wheel index перед
установкой остальных ML dependencies:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Используйте `.[sonara,ml,rhythm-lab,dev]`, если та же среда будет обучать
Rhythm Lab classifier profiles.

На Windows TorchCodec-backed Torchaudio decoding требует shared build FFmpeg с
DLL в `PATH`, а не только статический `ffmpeg.exe`. Portable tools setup должен
использовать GyanD `ffmpeg 8.1.1-full_build-shared` или совместимую структуру
`full_build-shared`, например:

```text
C:\Utils\tools\ffmpeg\bin\ffmpeg.exe
C:\Utils\tools\ffmpeg\bin\avcodec-*.dll
C:\Utils\tools\ffmpeg\bin\avformat-*.dll
```

## Логирование

Runtime file logging по умолчанию пишет в:

```text
dj-track-similarity.log
```

Лог ротируется ежедневно в полночь и хранит один rotated day. INFO-level
startup, completion, warning и error summaries пишутся по умолчанию. Успешные
per-track job events агрегируются и не пишутся в file log, если detailed
logging не включен.

Environment variables:

- `DJ_TRACK_SIMILARITY_LOG`: путь file log.
- `DJ_TRACK_SIMILARITY_LOG_LEVEL`: `debug`, `info`, `warning`, `error` или
  `critical`.
- `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS`: установите `1`, `true`, `yes` или
  `on`, чтобы писать успешные per-track job events.

Сервер также поддерживает `--log-level` и `--log-track-events`.

CLI analysis commands во время работы печатают live one-line progress display.
Строка перерисовывается на месте и включает progress bar, percentage,
`processed/total`, `analyzed`, `failed`, примерный `tracks/s` и estimated
remaining time. Это console-only progress для CLI process, который запустил
job; он не подключается к jobs, стартовавшим из web UI/server process.

CLI analysis commands могут писать diagnostic timing lines в file log, если
передан `--diagnostics` или установлено
`DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS=1`. Они включают batch-level
`prepare_seconds`, `decode_seconds`, `inference_seconds`, `save_seconds`,
`total_seconds`, `tracks_per_second`, track count и window count для MERT/CLAP
и MAEST. Sonara diagnostics логирует per-track `total_seconds` и
`tracks_per_second`, потому что внутренние decode и feature extraction
выполняются внутри Sonara. Audio loading также логирует decoder fallback
details по path: failed decoders вроде `torchaudio`, `wave` или `ffmpeg`, их
error text и fallback decoder, который в итоге сработал. Это diagnostic logging
выключено по умолчанию.


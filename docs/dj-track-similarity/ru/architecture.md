# Архитектура и среда выполнения

Эта страница описывает backend, frontend, зависимости среды выполнения и
поведение логирования.

## Архитектура

Пакет backend находится в `src/dj_track_similarity/`.

- `cli.py` предоставляет Typer CLI `dj-sim`.
- `api.py` создаёт приложение FastAPI; группы маршрутов живут в модулях
  `api_routes_*`.
- `database.py` — публичный фасад `LibraryDatabase`. Внутренние части базы
  разделены на `db_tracks.py` для CRUD треков, paging, likes и relocation,
  `db_analysis.py` для embeddings, analysis writes, resets и выбора кандидатов
  analyzer, а также `db_summary.py` для summary counters.
- `db_schema.py` определяет текущую схему SQLite и её проверку.
- `scanner.py` сканирует папки и читает метаданные Mutagen.
- `scan_jobs.py`, `analysis_jobs.py`, `classifier_jobs.py` и `tags.py`
  управляют отменяемыми заданиями и объектами статуса. Внутренности
  multi-model analysis дополнительно разделены: `analysis_job_state.py`
  отвечает за progress/status accounting, `analysis_job_batch.py` — за
  per-batch decode preparation, а `analysis_model_runners.py` — за runner
  adapters Sonara, MAEST, MERT и CLAP.
- `audio_loader.py` предоставляет общую загрузку аудио по принципу
  native-first.
- `sonara_features.py` извлекает сфокусированный набор признаков плейлиста
  Sonara.
- `sonara_similarity.py` и `sonara_similarity_scoring.py` ранжируют похожесть
  признаков Sonara.
- `embedding.py` содержит адаптеры embedding для MERT и CLAP.
- `genres.py` содержит жанровый адаптер MAEST.
- `classifier_scoring.py` загружает продвинутые артефакты классификаторов и
  оценивает треки с полным набором признаков.
- `tags.py` записывает метки MAEST в стандартное поле жанра и выполняет
  отменяемое задание записи жанровых тегов; `wave_tags.py` предоставляет
  защищённый путь записи жанра для WAV/ID3.
- `search.py` выполняет поиск похожести в пространстве embedding.
- `exporter.py` пишет выходные файлы M3U и CSV.
- `runtime.py` выбирает `auto`, `cpu` или `cuda` для задач PyTorch.
- `dependencies.py` проверяет зависимости среды выполнения, например `ffmpeg`.
- `logging_config.py` настраивает ротируемые файловые логи.

Frontend находится в `frontend/src/`.

- `api.ts` зеркалит контракт FastAPI.
- `App.tsx` координирует состояние приложения и рабочие процессы.
- `LibraryPanel.tsx` содержит элементы управления сканированием, обновлением,
  анализом, сбросом и очисткой.
- `TrackPanel.tsx`, `TrackRows.tsx` и `TrackMetadataDialog.tsx` показывают
  строки библиотеки, элементы управления понравившимися треками и подробности
  трека.
- `SearchPlaylistPanel.tsx` содержит вкладки SONARA, MERT, CLAP и CLASS, а
  также элементы управления экспортом.

## Зависимости среды выполнения

Основные зависимости среды выполнения объявлены в `pyproject.toml`:

- `numpy>=1.26,<2.0`
- `mutagen`
- `pydantic`
- `typer`
- `fastapi`
- `uvicorn`
- `joblib`

Дополнительные группы зависимостей:

- `sonara`: устанавливает поддержку Sonara.
- `ml`: устанавливает синхронизированный стек
  PyTorch/Torchaudio/Torchvision/TorchCodec, Transformers, Hugging Face Hub,
  LAION-CLAP и поддержку MAEST.
- `rhythm-lab`: устанавливает scikit-learn для локального обучения и
  бенчмаркинга классификаторов в Rhythm Lab.
- `dev`: устанавливает pytest и Ruff.

`ffmpeg` требуется для надёжного запуска сервера и декодирования аудио. Он
может находиться через `PATH` или задаваться переменной:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

Проверенный стек Windows CUDA:

- PyTorch `2.11.0`
- Torchaudio `2.11.0`
- Torchvision `0.26.0`
- TorchCodec `0.13.0`
- NumPy `>=1.26,<2.0`
- Индекс wheel-пакетов PyTorch `https://download.pytorch.org/whl/cu130`

Установите соответствующие CUDA-wheel из официального индекса wheel-пакетов
PyTorch перед установкой остальных ML-зависимостей:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Используйте `.[sonara,ml,rhythm-lab,dev]`, если та же среда будет также обучать
профили классификаторов Rhythm Lab.

На Windows декодирование Torchaudio через TorchCodec требует shared-сборки
FFmpeg с DLL, доступными в `PATH`, а не только статического `ffmpeg.exe`.
Настройка портативных инструментов должна использовать GyanD
`ffmpeg 8.1.1-full_build-shared` или совместимую раскладку `full_build-shared`,
например:

```text
C:\Utils\tools\ffmpeg\bin\ffmpeg.exe
C:\Utils\tools\ffmpeg\bin\avcodec-*.dll
C:\Utils\tools\ffmpeg\bin\avformat-*.dll
```

## Логирование

Файловое логирование среды выполнения по умолчанию пишет в:

```text
dj-track-similarity.log
```

Лог ротируется ежедневно в полночь и хранит один ротированный день. По
умолчанию записываются сводки уровня INFO: запуск, завершение, предупреждения и
ошибки. Успешные события заданий по отдельным трекам агрегируются и не пишутся в
файловый лог, если не включено подробное логирование.

Переменные окружения:

- `DJ_TRACK_SIMILARITY_LOG`: путь к файловому логу.
- `DJ_TRACK_SIMILARITY_LOG_LEVEL`: `debug`, `info`, `warning`, `error` или
  `critical`.
- `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS`: установите в `1`, `true`, `yes` или
  `on`, чтобы записывать успешные события заданий по отдельным трекам.

Сервер также поддерживает `--log-level` и `--log-track-events`.

Команды анализа CLI во время работы печатают живой однострочный индикатор
прогресса. Строка перерисовывается на месте и включает индикатор прогресса,
процент выполнения, `processed/total`, `analyzed`, `failed`, приблизительный
`tracks/s` и оценку оставшегося времени. Это прогресс только для консоли того
процесса CLI, который запустил задание; он не подключается к заданиям,
запущенным из web UI или процесса сервера.

Команды анализа CLI могут также записывать строки диагностического тайминга в
файловый лог, если в команде передан `--diagnostics` или установлено
`DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS=1`. Они включают на уровне пакета
`prepare_seconds`, `decode_seconds`, `inference_seconds`, `save_seconds`,
`total_seconds`, `tracks_per_second`, число треков и число окон для MERT/CLAP и
MAEST. Диагностика Sonara логирует `total_seconds` и `tracks_per_second` по
отдельным трекам, поскольку её внутреннее декодирование и извлечение признаков
выполняются внутри Sonara. Загрузка аудио также логирует подробности
переключения декодеров по пути: неудавшиеся декодеры вроде `torchaudio`, `wave`
или `ffmpeg`, текст их ошибок и резервный декодер, который в итоге сработал,
если такой нашёлся. Это диагностическое логирование по умолчанию выключено.

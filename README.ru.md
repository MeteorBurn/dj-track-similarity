# dj-track-similarity

[English version](README.md)

Локальный инструмент для анализа DJ-библиотеки и поиска треков, которые могут
хорошо работать рядом друг с другом в сете.

`dj-track-similarity` - это personal, local-first проект для DJ и коллекционеров
музыки. Он сканирует папку с аудиофайлами в SQLite, запускает опциональный
аудиоанализ и дает браузерный UI для инспекции треков, поиска по звучанию,
сборки временных идей для сетов и экспорта плейлистов.

Это не отполированный коммерческий продукт и не формальный research benchmark.
Это enthusiast-проект вокруг реальной локальной библиотеки, где практические
workflow важнее широких обещаний.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## Для кого это

Проект может быть полезен, если ты:

- хранишь локальные музыкальные файлы и хочешь searchable analysis database;
- готовишь DJ-сеты и хочешь больше сигналов, чем BPM, key и genre tags;
- хочешь seed-track search, text-to-audio search или объяснимые audio features;
- хочешь обучать маленькие персональные классификаторы, например vocal
  presence или live instrumentation;
- нормально относишься к локальному Python-приложению и хочешь держать свою
  музыкальную библиотеку на своей машине.

Репозиторий не содержит demo music library. Первый полезный результат появляется
после сканирования твоей собственной папки с аудио.

## Чем помогает

- Просматривать большую локальную библиотеку без загрузки всех metadata fields
  сразу.
- Сравнивать file tags, Sonara features, MAEST labels, embeddings и classifier
  scores, не смешивая их источники.
- Искать соседние треки от выбранных seed tracks через SONARA или MERT.
- Искать по текстовым prompt'ам вроде `dark hypnotic techno, rolling bass, no vocals`
  после CLAP-анализа.
- Генерировать ordered Smart Set Builder previews из ручных seed tracks или
  automatic anchors.
- Обучать Rhythm Lab classifiers для персональных понятий и промоутить их в
  основной app как reusable CLASS filters.
- Экспортировать временные сеты как M3U или CSV.

## Быстрый старт

Команды ниже рассчитаны на PowerShell в Windows. Это основной проверенный
локальный environment для проекта.

Требования:

- Python `>=3.10`
- FFmpeg в `PATH` или переменная `DJ_TRACK_SIMILARITY_FFMPEG`, указывающая на
  `ffmpeg.exe`
- локальные audio files для сканирования

Создай environment и установи базовый development package:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Ожидаемый результат:

```text
Команда dj-sim доступна в активном environment.
```

Создай локальную базу и просканируй папку с музыкой:

```powershell
New-Item -ItemType Directory -Force .\data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Ожидаемый результат:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

Запусти локальный web UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Открой:

```text
http://127.0.0.1:8765/
```

Ожидаемый результат:

```text
В браузере видны просканированные треки. Можно просматривать библиотеку,
инспектировать metadata, слушать preview, выбирать seed tracks и запускать
analysis jobs из UI.
```

Также есть Windows helper:

```powershell
scripts\run_server.cmd
```

Для доступа с другого устройства в той же LAN:

```powershell
run_server_lan.cmd
```

## Добавить аудиоанализ

Базовой установки достаточно для scan, browse, server и работы с уже сохраненными
данными. Установи optional dependencies, когда нужны model-backed features:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Для обучения classifier profiles в Rhythm Lab добавь lab extra:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Если нужен объяснимый поиск, начни с небольшого Sonara-pass:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Ожидаемый результат:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> ...
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> models=sonara ...
```

После этого обнови web UI и используй SONARA tab или feature controls.

Полная установка MAEST, MERT и CLAP, включая проверенный Windows CUDA stack,
описана в [Installation](docs/dj-track-similarity/ru/install.md).

## Основные workflow

### Просмотреть и разобрать локальную библиотеку

Просканируй папку, запусти server и используй Library + metadata dialog в UI.
File tags, model-derived values и classifier scores показываются как отдельные
источники, чтобы расхождения были видны.

### Найти похожие или совместимые треки

Запусти ту analysis family, которая подходит под задачу:

- SONARA - объяснимые rhythm, energy, loudness, tonal и spectral features.
- MERT - audio similarity от seed tracks.
- CLAP - text-to-audio search.
- MAEST - generated genre labels, syncopated-rhythm filter и classifier inputs.

После этого SET tab может построить ordered preview из manual seeds или
automatic anchors.

### Обучить персональные классификаторы

Используй Rhythm Lab, когда generic similarity уже недостаточно. Он запускается
отдельно от основного приложения, хранит labels в `tools/rhythm-lab/data/` и
promote'ит runtime models сюда:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Типичный запуск:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Открой:

```text
http://127.0.0.1:8777/
```

Ожидаемый результат:

```text
Открывается Rhythm Lab для profile-based labeling, train-refresh, prediction
review и promotion в основное приложение.
```

Перед training или promote classifiers прочитай
[Rhythm Lab](docs/dj-track-similarity/ru/rhythm-lab.md).

### Искать по тексту

После того как CLAP audio embeddings уже существуют:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Ожидаемый результат:

```text
<score>    <track_id>    <path>
```

### Экспортировать временный сет

В web UI добавь треки в current set и экспортируй M3U или CSV. Export пишет
только playlist/report files и не переписывает audio files.

## Варианты установки

Dependency groups заданы в `pyproject.toml`:

| Extra | Когда использовать |
| --- | --- |
| `dev` | Tests, linting и обычная локальная разработка. |
| `sonara` | Sonara playlist feature extraction. |
| `ml` | MAEST, MERT, CLAP, PyTorch, TorchCodec и связанные ML packages. |
| `rhythm-lab` | Локальная разметка и обучение classifiers через scikit-learn. |
| `ann` | Опциональные generated ANN sidecar indexes для экспериментов с embedding search. |

Полезные install-команды:

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[sonara,ml,dev]"
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Проверь environment:

```powershell
dj-sim --help
dj-sim doctor
```

Ожидаемый результат:

```text
dj-sim doctor показывает Python, PyTorch, CUDA visibility и device, который
выберет auto.
```

## Конфигурация

Большинство команд принимает `--db <path>`. Если база не указана, используется
`dj-track-similarity.sqlite` в корне репозитория или приложение попросит выбрать
database в UI.

FFmpeg нужен для server startup и надежного audio decoding. Добавь FFmpeg в
`PATH` или задай:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

В Windows TorchCodec-backed Torchaudio decoding требует shared FFmpeg build с
DLL в `PATH`, а не только standalone static `ffmpeg.exe`. Проверенный setup
описан в [Installation](docs/dj-track-similarity/ru/install.md).

## Безопасность и ограничения

Обычные app workflows работают через database-first подход и read-only для audio
files:

- scan, RefreshTags, analysis, search, preview, reset, relocation preview и
  export не изменяют audio files;
- classifier scoring пишет только SQLite `track_classifier_scores`;
- library relocation обновляет только stored SQLite paths;
- database clear удаляет только local SQLite rows;
- browser AIFF/AIF preview может транскодировать во временный WAV stream, но не
  переписывает source file.

Явные исключения:

- genre-save workflow может записать сохраненные MAEST labels в standard audio
  genre tags;
- standalone audio repair helper отделен от приложения, dry-run-first, и может
  переписывать только repairable files при запуске с `--apply`.

Практические ограничения:

- model analysis может быть медленным на CPU;
- CLAP, MERT и MAEST требуют optional ML dependencies;
- полезные classifier models требуют достаточной и последовательной локальной
  разметки;
- score thresholds могут требовать локальной калибровки, потому что каждая
  music library отличается;
- проект публичный, но локальные databases, logs, reports и trained models могут
  содержать приватную информацию о библиотеке, поэтому их не стоит случайно
  коммитить.

## Troubleshooting

### `dj-sim` не найден

Активируй virtual environment и переустанови package:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Server падает из-за FFmpeg

Установи FFmpeg, добавь его `bin` folder в `PATH` или задай
`DJ_TRACK_SIMILARITY_FFMPEG`. Для Windows ML decoding используй shared FFmpeg
build с DLL в `PATH`.

### Text search ничего полезного не возвращает

CLAP text search требует CLAP audio embeddings:

```powershell
dj-sim analyze --models clap --db .\data\library.sqlite
```

### Promoted classifier был переобучен

После promote новой classifier model нужно пересчитать scores этого classifier.
В main UI строка classifier делает это сама: сбрасывает только scores этого
classifier и затем считает их заново.

## Документация

Начни отсюда:

- [Project guide](docs/dj-track-similarity/ru/project-guide.md)
- [Installation](docs/dj-track-similarity/ru/install.md)
- [Overview](docs/dj-track-similarity/ru/overview.md)
- [Analysis families](docs/dj-track-similarity/ru/analysis.md)
- [Search and tags](docs/dj-track-similarity/ru/search-and-tags.md)
- [Rhythm Lab](docs/dj-track-similarity/ru/rhythm-lab.md)
- [CLI reference](docs/dj-track-similarity/ru/cli.md)
- [Web API](docs/dj-track-similarity/ru/api.md)
- [Development](docs/dj-track-similarity/ru/development.md)

## Разработка

Запустить backend tests:

```powershell
pytest
```

Собрать frontend bundle, который отдает backend:

```powershell
cd frontend
npm run build
```

Собрать docs site после правок Markdown в `docs/dj-track-similarity/`:

```powershell
cd docs\dj-track-similarity
npm run build
```

В репозитории сейчас нет отдельного `CONTRIBUTING.md` или license file.
Используй development guide и focused tests как source of truth для локальных
изменений.

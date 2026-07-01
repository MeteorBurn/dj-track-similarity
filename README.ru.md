# dj-track-similarity

[English version](README.md)

Локальная рабочая среда для DJ-библиотеки: сканирование аудиофайлов, анализ музыки, поиск связанных треков и подготовка идей для сетов без загрузки вашей коллекции во внешние сервисы.

`dj-track-similarity` рассчитан на работу с реальной локальной музыкальной библиотекой. Проект хранит теги, признаки и эмбеддинги в SQLite, дает браузерный интерфейс для повседневной работы и показывает разные источники данных отдельно, чтобы было понятно, почему тот или иной трек попал в выдачу.

Это практический персональный проект, а не коммерческий рекомендательный сервис и не академический benchmark. Его задача проще: быстрее довести вас от большой папки с музыкой до списка кандидатов, которые стоит послушать рядом друг с другом.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## Возможности

- Сканировать локальную папку с музыкой в SQLite-библиотеку.
- Просматривать треки с пагинацией, тегами, покрытием анализа и аудиопревью.
- Запускать SONARA, MAEST, MERT и CLAP-анализ для более глубокого поиска.
- Искать похожие треки от выбранных seed-треков через MERT или SONARA.
- Искать по текстовым описаниям через CLAP после расчета CLAP audio embeddings.
- Строить Smart Set Builder previews из выбранных seed-треков или автоматических anchors.
- Обучать и подключать персональные Rhythm Lab classifiers, например для вокала, live instrumentation или энергетики.
- Экспортировать временные сеты в M3U или CSV.
- Использовать Audio Doctor и Audio Dedup как report-first инструменты обслуживания библиотеки.

## Как проект смотрит на музыку

Приложение не смешивает разные источники сигналов:

- **File tags** читаются из аудиофайлов через Mutagen.
- **SONARA features** описывают измеримые свойства: energy, rhythm, loudness, tonal и spectral signals.
- **MERT, MAEST и CLAP embeddings** используются как векторные пространства для similarity search.
- **MAEST labels** помогают с жанровой навигацией и tag workflows.
- **Classifier scores** приходят из ваших promoted Rhythm Lab models.

Все эти score являются подсказками для сортировки, а не объективной истиной. Хороший сценарий: использовать приложение для короткого списка кандидатов, затем слушать и принимать решение самостоятельно.

## Быстрый старт

Основная проверенная среда разработки и запуска - Windows, PowerShell и Python `>=3.10`.

Вам нужны:

- Python `>=3.10`
- FFmpeg в `PATH` или переменная `DJ_TRACK_SIMILARITY_FFMPEG`, указывающая на `ffmpeg.exe`
- папка с локальными аудиофайлами

Создайте окружение и установите базовый пакет:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Создайте локальную базу и просканируйте папку:

```powershell
mkdir data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Запустите web UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Откройте:

```text
http://127.0.0.1:8765/
```

В браузере должны появиться просканированные треки. После этого можно просматривать библиотеку, открывать metadata dialog, слушать preview, выбирать seed-треки и запускать analysis jobs.

В корне репозитория также есть Windows launcher:

```powershell
run_server.cmd local --db C:\db\abstracted.sqlite
run_server.cmd lan --db C:\db\abstracted.sqlite
```

## Добавить анализ

Базовой установки достаточно для сканирования, просмотра библиотеки, запуска UI и работы с уже сохраненными данными. Установите дополнительные зависимости, когда нужен model-backed search:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Для первого прохода лучше ограничить объем:

```powershell
dj-sim analyze --models sonara,mert,clap --limit 25 --db .\data\library.sqlite
```

В UI значение `Analyze limit = 0` означает всю библиотеку. Положительные значения считают только треки, у которых нет выбранного семейства анализа.

Полная установка Windows ML stack, CUDA и FFmpeg описана в [Install](docs/dj-track-similarity/ru/getting-started/install.md).

## Режимы поиска

Основная поисковая поверхность разделена на вкладки:

- **SET** строит read-only preview сета из ручных seed-треков или automatic anchors.
- **SONARA** ищет по объяснимым audio features и поддерживает mixer/modifier controls.
- **MERT** ищет от выбранных seed-треков в MERT embedding space.
- **CLAP** ищет по текстовому prompt against stored CLAP audio embeddings.
- **CLASS** фильтрует или оценивает треки через promoted local classifier profiles.

CLAP text scores обычно ниже, чем seed-based audio-to-audio scores. Полезные CLAP text результаты могут находиться примерно в диапазоне `0.35-0.55`; их нельзя напрямую сравнивать с MERT seed-search scores или порогами Audio Dedup. Если заполнено поле CLAP `Avoid`, итоговый score является contrast evidence: positive prompt match минус negative prompt match.

## Персональные классификаторы

Rhythm Lab - отдельный workflow для разметки и локальных classifiers. Он запускается отдельно, читает основную библиотеку для контекста и хранит labels в `tools/rhythm-lab/data/`.

Запуск:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Откройте:

```text
http://127.0.0.1:8777/
```

Promoted runtime models хранятся здесь:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Перед обучением или promotion classifiers прочитайте [Classifiers and Rhythm Lab](docs/dj-track-similarity/ru/concepts/classifiers-and-rhythm-lab.md).

## Инструменты обслуживания

В репозитории есть помощники для обслуживания локальной библиотеки:

- **Audio Doctor** работает по dry-run-first модели и ремонтирует только файлы, которые были помечены как repairable.
- **Audio Dedup** по умолчанию пишет JSON/XLSX/log reports и удаляет файлы только после точного подтверждения `APPLY DELETE`.
- **Database optimization** должен создавать SQLite backup перед maintenance work.

Audio Dedup использует audio-to-audio MERT, MAEST, CLAP, SONARA и duration evidence. Его `Min similarity` gate не находится в той же шкале, что CLAP text search.

## Модель безопасности

Обычные workflows не изменяют аудиофайлы:

- scan
- Refresh Tags
- analysis
- search
- preview
- reset
- relocation preview
- export
- classifier scoring

Явные write paths ограничены:

- MAEST genre tag apply может записывать standard genre tags в аудиофайлы.
- Audio Doctor `--apply` может ремонтировать файлы после dry-run.
- Audio Dedup apply mode может удалить подтвержденные duplicate candidates.
- Relocation apply обновляет только пути в SQLite; файлы не перемещаются.

Локальные базы, logs, reports и trained models могут раскрывать приватную информацию о вашей библиотеке. Не добавляйте их в Git случайно.

## Документация

Начните отсюда:

- [Project guide](docs/dj-track-similarity/ru/project-guide.md)
- [Quickstart](docs/dj-track-similarity/ru/getting-started/quickstart.md)
- [Install](docs/dj-track-similarity/ru/getting-started/install.md)
- [First library](docs/dj-track-similarity/ru/getting-started/first-library.md)
- [First analysis](docs/dj-track-similarity/ru/getting-started/first-analysis.md)
- [Search by text with CLAP](docs/dj-track-similarity/ru/user-guide/text-search.md)
- [Similarity scores](docs/dj-track-similarity/ru/concepts/similarity-scores.md)
- [Audio Dedup](docs/dj-track-similarity/ru/tools-and-scripts/audio-dedup.md)
- [CLI reference](docs/dj-track-similarity/ru/reference/cli.md)
- [API reference](docs/dj-track-similarity/ru/reference/api.md)
- [Development](docs/dj-track-similarity/ru/developer/development.md)

## Разработка

Запустите backend tests:

```powershell
python -m pytest
```

Соберите frontend bundle, который отдает backend:

```powershell
cd frontend
npm run build
```

Соберите docs site:

```powershell
cd docs\dj-track-similarity
npm run build
```

Docs build output записывается в `docs/dj-track-similarity/site/` и не отслеживается в Git.

В репозитории сейчас нет отдельного `CONTRIBUTING.md` или license file.

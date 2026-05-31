# Справочник CLI

Эта страница описывает интерфейс командной строки `dj-sim`. Используйте CLI для
повторяемых локальных рабочих процессов, пакетного анализа, быстрой диагностики
и операций, которые удобнее просматривать в терминале, чем в веб-интерфейсе.

## Справочник CLI

Сначала установите проект, чтобы команда `dj-sim` стала доступна:

```powershell
python -m pip install -e ".[dev]"
```

Каждая команда, работающая с базой данных, объявляет собственную опцию `--db`;
глобальной опции `--db` нет. Используйте `--db`, чтобы указать конкретную базу
данных SQLite. Если `--db` опущена, такие команды по умолчанию используют:

```text
dj-track-similarity.sqlite
```

в текущем рабочем каталоге. Команда `doctor` не обращается ни к какой базе
данных и поэтому не принимает `--db`.

## Выбор команды

| Цель | Команда |
| --- | --- |
| Добавить или обновить треки из папки | `dj-sim scan` |
| Запустить локальный сервер веб-интерфейса/API | `dj-sim serve` |
| Построить анализ SONARA, MAEST, MERT и/или CLAP | `dj-sim analyze` |
| Оценить продвинутый классификатор Rhythm Lab | `dj-sim analyze-classifier` |
| Искать по текстовому запросу CLAP | `dj-sim text-search` |
| Обновить сохранённые пути после перемещения библиотеки | `dj-sim relocate-library` |
| Проверить настройку Python, PyTorch и CUDA | `dj-sim doctor` |

### `dj-sim`

```powershell
dj-sim [OPTIONS] COMMAND [ARGS]...
```

Опции уровня приложения (встроенные в Typer, не общий `--db`):

| Опция | Описание |
| --- | --- |
| `--install-completion` | Установить автодополнение для текущей оболочки. |
| `--show-completion` | Вывести код автодополнения оболочки. |
| `--help` | Показать справку. |

> Примечание: `--db` не является опцией уровня приложения. Она повторяется в
> каждой команде, которая читает или пишет базу данных. Команда `analyze`
> отображает живой индикатор прогресса; команды `scan`, `relocate-library`,
> `analyze-classifier`, `text-search`, `doctor` и `serve` выводят только
> обычный текст.

Команды:

```text
scan
relocate-library
analyze
analyze-classifier
doctor
text-search
serve
```

### `dj-sim scan`

Сканирует музыкальную папку и добавляет или обновляет строки треков в SQLite.

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
```

Использование:

```text
dj-sim scan [OPTIONS] MUSIC_ROOT
```

Аргументы:

| Аргумент | Тип | Обязателен | Описание |
| --- | --- | --- | --- |
| `MUSIC_ROOT` | path | да | Папка, рекурсивно сканируемая на наличие поддерживаемых аудиофайлов. |

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Путь к базе данных SQLite. |
| `--help` | flag | off | Показать справку. |

Вывод:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

`scan` читает метаданные аудио и пишет только в SQLite. Он не изменяет
аудиофайлы.

Используйте эту команду первой для новой базы данных и запускайте её повторно
после добавления файлов в музыкальную папку. Существующий анализ сохраняется для
неизменившихся треков.

### `dj-sim serve`

Запускает локальный сервер FastAPI и отдаёт frontend.

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Использование:

```text
dj-sim serve [OPTIONS]
```

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--host` | text | `127.0.0.1` | Адрес привязки локального сервера. |
| `--port` | integer | `8765` | HTTP-порт. |
| `--db` | path | none | Необязательный путь к базе данных SQLite. Без него выберите/создайте базу данных в интерфейсе. |
| `--log-level` | text | `info` | Уровень логирования в файл: `debug`, `info`, `warning`, `error` или `critical`. |
| `--log-track-events` | flag | off | Записывать успешные события по трекам в файловый лог. |
| `--help` | flag | off | Показать справку. |

Затем откройте:

```text
http://127.0.0.1:8765/
```

Также есть вспомогательный скрипт для Windows:

```powershell
scripts\run_server.cmd
```

Используйте `serve`, когда нужен браузерный рабочий процесс: постраничный
просмотр, предпрослушивание воспроизведения, элементы управления анализом,
вкладки поиска, фильтры классификаторов, экспорт и просмотр метаданных.

### `dj-sim analyze`

Анализирует отсутствующие результаты SONARA, MAEST, MERT и/или CLAP в одном
задании. По умолчанию выбраны все четыре аудиомодели.

```powershell
dj-sim analyze --models sonara,maest,mert,clap --device auto --track-batch-size 6 --inference-batch-size 24 --limit 25 --db .\data\library.sqlite
```

Использование:

```text
dj-sim analyze [OPTIONS]
```

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Путь к базе данных SQLite. |
| `--limit` | integer | none | Максимальное число треков-кандидатов для анализа. |
| `--models` | comma-separated text | `sonara,maest,mert,clap` | Выбранные модели: `sonara`, `maest`, `mert`, `clap`. |
| `--device` | text | `auto` | Устройство MAEST/MERT/CLAP: `auto`, `cpu` или `cuda`. |
| `--top-k` | integer `1..10` | `3` | Число жанровых меток MAEST, сохраняемых для трека. |
| `--track-batch-size` | integer `1..64` | `6` | Число декодированных треков, удерживаемых и обрабатываемых вместе. |
| `--inference-batch-size` | integer `1..128` | `24` | Размер батча инференса MAEST/MERT/CLAP. |
| `--diagnostics` | flag | off | Записывать диагностику резервного декодера и таймингов пакетов в файловый лог. |
| `--help` | flag | off | Показать справку. |

Примеры:

```powershell
dj-sim analyze --db .\data\library.sqlite
dj-sim analyze --models maest,mert --device cpu --track-batch-size 2 --inference-batch-size 4 --db .\data\library.sqlite
dj-sim analyze --models clap --device cuda --track-batch-size 6 --inference-batch-size 24 --db .\data\library.sqlite
```

Вывод:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> models=<models> device=<device> top_k=<n> track_batch_size=<n> inference_batch_size=<n>
```

`processed`, `analyzed` и `failed` — это счётчики на уровне треков. Подробные
счётчики по моделям доступны в статусе web/API `model_progress`.

`auto` выбирает CUDA, когда PyTorch видит GPU, иначе CPU. Явный `cuda`
завершается ошибкой, если CUDA недоступна.

Трек попадает в задание, если у него отсутствует хотя бы одна выбранная модель.
Уже существующие результаты выбранных моделей пропускаются. Трек декодируется
один раз на in-memory batch, затем недостающие выбранные модели запускаются в
порядке SONARA, MAEST, MERT, CLAP.

Используйте `--models sonara` для вкладки поиска SONARA и видимых групп
признаков. Используйте `--models maest` перед просмотром сгенерированных жанров,
пресетом `syncopated` или combined-классификаторами. Используйте `--models mert`
для seed-track similarity и `--models clap` перед текстовым поиском CLAP.
MAEST анализ записывает в SQLite жанровые метаданные и embedding, но сам по себе
не записывает жанровые теги в аудиофайлы.

### `dj-sim analyze-classifier`

Оценивает треки с помощью продвинутого профиля классификатора.

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Использование:

```text
dj-sim analyze-classifier CLASSIFIER [OPTIONS]
```

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `CLASSIFIER` | text | обязателен | Ключ классификатора, например `live_instrumentation`. |
| `--db` | path | `dj-track-similarity.sqlite` | Путь к базе данных SQLite. |
| `--model` | path | `models/classifiers/<artifact-prefix>/model.joblib` | Необязательный путь к артефакту классификатора. |
| `--limit` | integer | none | Максимальное число треков с полным набором признаков для оценки. |
| `--help` | flag | off | Показать справку. |

Вывод:

```text
classifier=live_instrumentation scored=<n> skipped=<n> model=<path>
```

Команда читает существующие данные SONARA, MERT и MAEST. Треки, у которых
отсутствует какой-либо обязательный вход, пропускаются. Оценки записываются
(upsert) в `track_classifier_scores`. В отличие от `dj-sim analyze`, оценка
классификатора выполняется синхронно и печатает одну итоговую строку вместо
живого индикатора прогресса.

Используйте эту команду после продвижения модели из Rhythm Lab. Если
пропускается много треков, сначала выполните для них анализ Sonara, MERT и MAEST.

### `dj-sim text-search`

Выполняет текстовый поиск CLAP (text-to-audio).

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Использование:

```text
dj-sim text-search [OPTIONS] QUERY
```

Аргументы:

| Аргумент | Тип | Обязателен | Описание |
| --- | --- | --- | --- |
| `QUERY` | text | да | Текстовое описание, преобразуемое CLAP в embedding. |

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | Путь к базе данных SQLite. |
| `--limit` | integer `1..500` | `50` | Максимальное число результатов. |
| `--min-similarity` | float | none | Необязательный минимальный порог оценки. |
| `--device` | text | `auto` | Устройство CLAP: `auto`, `cpu` или `cuda`. |
| `--help` | flag | off | Показать справку. |

Строки вывода:

```text
<score>    <track_id>    <path>
```

Аудио-embedding'и CLAP должны существовать, прежде чем текстовый поиск сможет
возвращать полезные результаты.

Используйте эту команду для исследовательских поисков, когда текстовое описание
быстрее, чем выбор seed-треков. Конкретные запросы с настроением, ритмом,
инструментовкой и наличием вокала обычно полезнее, чем один широкий жанр.

### `dj-sim relocate-library`

Предпросмотр или применение переноса сохранённых путей после перемещения той же
музыкальной папки.

```powershell
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
```

Применить после проверки сухого прогона (dry-run):

```powershell
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
```

Использование:

```text
dj-sim relocate-library [OPTIONS] OLD_ROOT NEW_ROOT
```

Аргументы:

| Аргумент | Тип | Обязателен | Описание |
| --- | --- | --- | --- |
| `OLD_ROOT` | path | да | Существующий сохранённый корневой префикс в SQLite. |
| `NEW_ROOT` | path | да | Новый корень, где теперь находятся те же файлы. |

Опции:

| Опция | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--apply` | flag | off | Обновить сохранённые пути после успешных проверок предпросмотра. |
| `--db` | path | `dj-track-similarity.sqlite` | Путь к базе данных SQLite. |
| `--help` | flag | off | Показать справку. |

Вывод:

```text
dry_run=<true|false> tracks_matched=<n> tracks_updated=<n> missing_files=<n> conflicts=<n>
```

Конфликты и отсутствующие целевые файлы печатаются по каждому треку. Режим
применения отклоняет отсутствующие файлы и конфликты вместо частичного обновления
путей.

Используйте эту команду только тогда, когда те же аудиофайлы переместились в
новый корневой каталог и вы хотите сохранить существующие идентификаторы треков,
анализ и оценки классификаторов. Всегда проверяйте вывод сухого прогона (dry-run)
перед добавлением `--apply`.

### `dj-sim doctor`

Выводит диагностику среды выполнения Python, PyTorch и CUDA.

```powershell
dj-sim doctor
```

Использование:

```text
dj-sim doctor [OPTIONS]
```

`doctor` — это диагностика окружения только для чтения. Она не открывает базу
данных и не принимает `--db`.

Вывод может включать:

```text
python=<path>
torch=<version>
torch_cuda_build=<version-or-none>
cuda_available=<true|false>
cuda_device_count=<n>
cuda_device_name=<name-or-none>
nvidia_smi_cuda=<version-or-none>
device_auto=<cuda|cpu>
suggested_torch_index=<url>
install=torch torchaudio --index-url <url>
```

Используйте эту команду, когда поведение `auto`, `cpu` или `cuda` неясно.

Запускайте её перед длительным анализом на GPU, если вы изменили пакеты Python,
CUDA-колёса, драйверы или настройку FFmpeg/TorchCodec.

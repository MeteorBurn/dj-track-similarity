# Справочник CLI

Эта страница документирует command line interface `dj-sim`. Используйте CLI для
повторяемых локальных workflows, batch analysis, быстрых diagnostics и операций,
которые проще проверить в terminal, чем в web UI.

## Справочник CLI

Сначала установите проект, чтобы `dj-sim` был доступен:

```powershell
python -m pip install -e ".[dev]"
```

Используйте `--db` в командах, которые должны работать с конкретной SQLite
database. Без `--db` CLI commands используют:

```text
dj-track-similarity.sqlite
```

в текущей working directory.

## Выбор команды

| Цель | Команда |
| --- | --- |
| Добавить или обновить tracks из folder | `dj-sim scan` |
| Запустить local web UI/API server | `dj-sim serve` |
| Построить MERT или CLAP embeddings | `dj-sim analyze` |
| Построить explainable Sonara features | `dj-sim analyze-sonara` |
| Предсказать MAEST genres и MAEST embeddings | `dj-sim analyze-genres` |
| Оценить promoted Rhythm Lab classifier | `dj-sim analyze-classifier` |
| Искать по CLAP text prompt | `dj-sim text-search` |
| Обновить stored paths после перемещения library | `dj-sim relocate-library` |
| Проверить Python, PyTorch и CUDA setup | `dj-sim doctor` |

### `dj-sim`

```powershell
dj-sim [OPTIONS] COMMAND [ARGS]...
```

Global options:

| Option | Meaning |
| --- | --- |
| `--install-completion` | Установить shell completion для текущего shell. |
| `--show-completion` | Напечатать shell completion code. |
| `--help` | Показать help. |

Commands:

```text
scan
relocate-library
analyze
analyze-genres
analyze-sonara
analyze-classifier
doctor
text-search
serve
```

### `dj-sim scan`

Сканирует music folder и добавляет или обновляет SQLite track rows.

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
```

Usage:

```text
dj-sim scan [OPTIONS] MUSIC_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `MUSIC_ROOT` | path | yes | Folder, recursively scanned for supported audio files. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Показать help. |

Output:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

`scan` читает audio metadata и пишет только SQLite. Он не изменяет аудиофайлы.

Используйте его первым для новой database и повторяйте после добавления files в
music folder. Existing analysis сохраняется для unchanged tracks.

### `dj-sim serve`

Запускает local FastAPI server и отдает frontend.

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Usage:

```text
dj-sim serve [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | text | `127.0.0.1` | Bind address for the local server. |
| `--port` | integer | `8765` | HTTP port. |
| `--db` | path | none | Optional SQLite database path. Без него database выбирается/создается в UI. |
| `--log-level` | text | `info` | File log level: `debug`, `info`, `warning`, `error` или `critical`. |
| `--log-track-events` | flag | off | Писать successful per-track events в file log. |
| `--help` | flag | off | Показать help. |

Затем откройте:

```text
http://127.0.0.1:8765/
```

Также есть Windows helper:

```powershell
scripts\run_server.cmd
```

Используйте `serve`, когда нужен browser workflow: paged browsing, playback
preview, analysis controls, search tabs, classifier filters, exports и metadata
review.

### `dj-sim analyze`

Строит missing MERT или CLAP embeddings.

```powershell
dj-sim analyze --adapter mert --device auto --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of missing embeddings to analyze. |
| `--adapter` | text | `mert` | Embedding adapter: `mert` или `clap`. |
| `--device` | text | `auto` | Embedding device: `auto`, `cpu` или `cuda`. |
| `--batch-size` | integer `1..64` | `4` | Embedding inference batch size. |
| `--diagnostics` | flag | off | Писать decoder fallback и batch timing diagnostics в file log. |
| `--help` | flag | off | Показать help. |

Examples:

```powershell
dj-sim analyze --adapter mert --device cpu --batch-size 2 --db .\data\library.sqlite
dj-sim analyze --adapter clap --device cuda --batch-size 8 --db .\data\library.sqlite
```

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=<key> device=<device> batch_size=<n>
```

`auto` выбирает CUDA, когда PyTorch видит GPU, иначе CPU. Явный `cuda` fails,
если CUDA unavailable.

Используйте `--adapter mert` для seed-track similarity. Используйте
`--adapter clap`, когда нужен CLAP text search. Если нужен только explainable
feature search, запускайте `analyze-sonara`.

### `dj-sim analyze-sonara`

Извлекает missing Sonara playlist features.

```powershell
dj-sim analyze-sonara --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-sonara [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing Sonara features to analyze. |
| `--batch-size` | integer `1..64` | `1` | Parallel Sonara track workers. |
| `--diagnostics` | flag | off | Писать analysis timing diagnostics в file log. |
| `--help` | flag | off | Показать help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> batch_size=<n>
```

Sonara `batch-size` означает parallel track workers.

Используйте это для SONARA search tab, visible feature groups или library-level
fields вроде analyzed BPM, key, energy, danceability и loudness.

### `dj-sim analyze-genres`

Извлекает missing MAEST genre labels.

```powershell
dj-sim analyze-genres --device auto --top-k 3 --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-genres [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing MAEST genres to analyze. |
| `--device` | text | `auto` | MAEST device: `auto`, `cpu` или `cuda`. |
| `--top-k` | integer `1..10` | `3` | Number of MAEST genre labels to store per track. |
| `--batch-size` | integer `1..64` | `4` | MAEST inference batch size. |
| `--diagnostics` | flag | off | Писать decoder fallback и batch timing diagnostics в file log. |
| `--help` | flag | off | Показать help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=maest device=<device> top_k=<n> batch_size=<n>
```

MAEST analysis пишет SQLite genre metadata и MAEST embedding vector.

Используйте это перед review generated genres, preset `syncopated` или
training/scoring combined classifier profiles. Сам по себе анализ не пишет
genre tags в аудиофайлы.

### `dj-sim analyze-classifier`

Оценивает tracks через promoted classifier profile.

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-classifier CLASSIFIER [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `CLASSIFIER` | text | required | Classifier key, например `live_instrumentation`. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--model` | path | `models/classifiers/<artifact-prefix>/model.joblib` | Optional classifier artifact path. |
| `--limit` | integer | none | Maximum number of feature-complete tracks to score. |
| `--help` | flag | off | Показать help. |

Output:

```text
classifier=live_instrumentation scored=<n> skipped=<n> model=<path>
```

Команда читает existing SONARA, MERT и MAEST data. Tracks без любого required
input пропускаются. Scores upserted в `track_classifier_scores`.

Используйте после promotion model из Rhythm Lab. Если many tracks skipped,
сначала запустите Sonara, MERT и MAEST analysis для этих tracks.

### `dj-sim text-search`

Запускает CLAP text-to-audio search.

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim text-search [OPTIONS] QUERY
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `QUERY` | text | yes | Text description embedded by CLAP. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer `1..500` | `50` | Maximum result count. |
| `--min-similarity` | float | none | Optional minimum score threshold. |
| `--device` | text | `auto` | CLAP device: `auto`, `cpu` или `cuda`. |
| `--help` | flag | off | Показать help. |

Output rows:

```text
<score>    <track_id>    <path>
```

CLAP audio embeddings должны существовать, чтобы text search возвращал полезные
results.

Используйте это для exploratory searches, где text description быстрее выбора
seed tracks. Concrete prompts с mood, rhythm, instrumentation и vocal presence
обычно полезнее одного broad genre.

### `dj-sim relocate-library`

Preview или apply stored path relocation после перемещения той же music folder.

```powershell
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
```

Apply после проверки dry run:

```powershell
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
```

Usage:

```text
dj-sim relocate-library [OPTIONS] OLD_ROOT NEW_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `OLD_ROOT` | path | yes | Existing stored root prefix in SQLite. |
| `NEW_ROOT` | path | yes | New root where the same files now exist. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--apply` | flag | off | Update stored paths after preview checks pass. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Показать help. |

Output:

```text
dry_run=<true|false> tracks_matched=<n> tracks_updated=<n> missing_files=<n> conflicts=<n>
```

Conflicts и missing target files печатаются per track. Apply mode rejects
missing files and conflicts вместо частичного обновления paths.

Используйте это только когда те же аудиофайлы переехали в новый root folder и
нужно сохранить existing track IDs, analysis и classifier scores. Всегда
проверяйте dry-run output перед добавлением `--apply`.

### `dj-sim doctor`

Печатает Python, PyTorch и CUDA runtime diagnostics.

```powershell
dj-sim doctor
```

Usage:

```text
dj-sim doctor [OPTIONS]
```

Output can include:

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

Используйте это, когда поведение `auto`, `cpu` или `cuda` неясно.

Запускайте перед long GPU analysis, если меняли Python packages, CUDA wheels,
drivers или FFmpeg/TorchCodec setup.


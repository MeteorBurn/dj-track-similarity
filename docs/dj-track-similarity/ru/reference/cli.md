# Справочник CLI

> Для кого: Для тех, кому нужны точные имена команд.
> Задача: Перечислить текущий интерфейс CLI и безопасные примеры.
> Тип: Справочник

Установленный консольный скрипт называется `dj-sim`. Предполагается, что окружение Python уже
активировано.

## Основные команды

Просканировать папку:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

Проанализировать выбранные семейства:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Запустить интерфейс:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Выполнить текстовый поиск CLAP:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass" --limit 20 --db .\data\library.sqlite
```

Предварительно проверить перенос путей:

```powershell
dj-sim relocate-library D:\Music E:\Music --db .\data\library.sqlite
```

Применить перенос:

```powershell
dj-sim relocate-library D:\Music E:\Music --apply --db .\data\library.sqlite
```

Применение меняет только сохранённые пути SQLite и отклоняет отсутствующие цели и конфликты.

Рассчитать один опубликованный классификатор:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Рассчитать выбранные или все совместимые классификаторы:

```powershell
dj-sim analyze-classifiers --classifiers live_instrumentation,voice_presence --db .\data\library.sqlite
dj-sim analyze-classifiers --db .\data\library.sqlite
```

Запустить конвейер с фиксированным порядком:

```powershell
dj-sim analyze-pipeline --stages sonara,ml,classifiers --db .\data\library.sqlite
```

Проверить среду:

```powershell
dj-sim doctor
```

## Параметры анализа

`dj-sim analyze` поддерживает:

| Параметр | Значения |
| --- | --- |
| `--models` | разделённые запятыми `sonara`, `maest`, `mert`, `muq`, `clap` |
| `--limit` | необязательное целое; не указывайте для всей библиотеки |
| `--device` | `auto`, `cpu`, `cuda` |
| `--top-k` | `1..10` меток MAEST |
| `--track-batch-size` | `1..64` декодированных треков в партии, по умолчанию `8` |
| `--inference-batch-size` | `1..128` примеров за проход модели, по умолчанию `16` |
| `--diagnostics` | диагностика декодирования и времени партий в файловом журнале |
| `--sonara-outputs` | разделённые запятыми `core`, `timeline`, `representations`; по умолчанию `core` |
| `--sonara-batch-size` | `1..16` одновременных нативных путей, по умолчанию `8` |

Обычный анализ SONARA записывает только Core. Для трёх хранилищ используйте
`--sonara-outputs core,timeline,representations`; при расширении существующего анализа можно выбрать
только отсутствующий результат. Core находится в основной выбранной базе, Timeline — в соседней
`*.timeline.sqlite`, а эмбеддинг и отпечаток — в `*.representations.sqlite`. Эти два значения
относятся к SONARA; поисковые эмбеддинги MAEST/MERT/MuQ/CLAP остаются в Core. Диалог метаданных
читает значения Core и только списки имён полей дополнительных баз.

Точный профиль запроса каждого результата и нативный путь декодирования и выполнения входят в
сигнатуру SONARA. Строки старого контракта блокируют первую нативную задачу до резервного
копирования и явного сброса SONARA. После этого частичное актуальное покрытие можно продолжать по
сигнатуре результата.

`analyze-classifiers` создаёт отдельную задачу только для базы. Без `--classifiers` выбираются все
совместимые опубликованные артефакты. `analyze-pipeline` принимает те же настройки этапов и всегда
выполняет SONARA, ML, CLASSIFIERS; `--ml-models` не может содержать SONARA.

Для базы схемы v5 используйте
[повторный анализ с раздельным хранением](../workflows/reanalyze-sonara-split-storage.md).

## Параметры текстового поиска

`dj-sim text-search` поддерживает:

| Параметр | Значение |
| --- | --- |
| `query` | обязательный текстовый запрос |
| `--limit` | число результатов `1..500` |
| `--min-similarity` | необязательный порог |
| `--device` | `auto`, `cpu` или `cuda` для текстового эмбеддинга CLAP |
| `--use-ann-index` | явно включить постоянный индекс CLAP |
| `--index-dir` | нестандартный каталог индекса |

Если индекс недоступен, команда предупреждает и выполняет точный поиск.

## Команды постоянных индексов

```powershell
dj-sim index build --adapter clap --db .\data\library.sqlite
dj-sim index verify --adapter clap --db .\data\library.sqlite
dj-sim index benchmark --adapter clap --db .\data\library.sqlite
dj-sim index clear --adapter clap --db .\data\library.sqlite
```

Доступные адаптеры: `mert`, `maest`, `clap`.

## Команды оценки

Группа `eval` предназначена для локальной диагностики и отчётов обратной связи:

- `export-candidates`;
- `export-weighted-candidates`;
- `export-seed-sample`;
- `import-pair-feedback`;
- `import-transition-feedback`;
- `report`;
- `run-ablation`;
- `build-score-profile`;
- `run-calibration`;
- `optimize-score-profile`;
- `profile-sources`;
- `apply-score-profile`;
- `sweep-risk-penalty`.

Команды требуют актуальную схему SQLite и работают с локальной базой и файлами отчётов.

## Диагностика классификаторов

```powershell
dj-sim classifier calibration-report --classifier live_instrumentation --db .\data\library.sqlite
```

```powershell
dj-sim classifier suggest-labels --classifier live_instrumentation --limit 25 --db .\data\library.sqlite
```

## Отдельные инструменты

Rhythm Lab:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Предварительная проверка Audio Doctor:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

Отчёт Audio Dedup:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Оптимизация базы:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Кратко о безопасности

- `scan`, `analyze`, `text-search`, `serve`, `doctor`, `index` и отчёты оценки не переписывают аудио.
- `relocate-library --apply` меняет только пути SQLite.
- Audio Doctor `--apply` может переписывать исправимые файлы.
- Audio Dedup `--apply` может удалять файлы.
- Запись жанрового тега MAEST доступна через приложение и API, но не как верхнеуровневая команда `dj-sim`.

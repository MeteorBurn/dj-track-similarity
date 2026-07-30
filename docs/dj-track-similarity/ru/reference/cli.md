# Справочник CLI

> Для кого: Пользователи, которым нужны точные имена команд.
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
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Запустить бэкенд:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Без `--db` команда `serve` запускается без выбранной базы и не создаёт файлы SQLite. После запуска
базу можно открыть или создать через диалог выбора либо `/api/database/switch`. С параметром `--db`
сервер до запуска Uvicorn открывает существующий совместимый комплект или создаёт новую пару Core и
Artifacts по указанному пути.

Исходный код React использует текущие типы API. После изменений frontend или API заново соберите
`frontend/dist`, чтобы backend раздавал комплект из актуального типизированного клиента.

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

Применение меняет только сохранённые пути SQLite и отклоняет отсутствующие целевые файлы и конфликты.

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

## Миграция структуры базы

Обычный запуск проверяет структуру Core и обязательной соседней базы Artifacts. Несовместимый
комплект отклоняется с указанием команды миграции; приложение не меняет его автоматически.

Сначала просмотрите план в режиме только чтения:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --dry-run
```

Применяйте преобразование только после отдельного решения пользователя:

```powershell
dj-sim migrate-database --db .\data\library.sqlite
```

Применение требует точной фразы `MIGRATE DATABASE`. Параметр `--backup-dir` может изменить каталог
резервных копий по умолчанию. До замены любой базы команда проверяет автономные копии Core и
Artifacts, а после преобразования — целостность, внешние ключи и потерянные межбазовые ссылки.
Повторный анализ она не запускает.

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
| `--sonara-outputs` | разделённые запятыми `core`, `timeline`, `embedding`, `fingerprint`; по умолчанию `core` |
| `--sonara-batch-size` | `1..16` путей, одновременно обрабатываемых нативным анализом, по умолчанию `8` |

Обычный анализ SONARA материализует только `core`. Чтобы сохранить все четыре результата,
используйте `--sonara-outputs core,timeline,embedding,fingerprint`. Следующая задача может выбрать
другой отсутствующий результат. `core` хранится в Core, а остальные три результата — в отдельных
таблицах обязательной базы Artifacts. Эмбеддинги MAEST/MERT/MuQ/CLAP также находятся в отдельных
таблицах Artifacts.

`analyze-classifiers` создаёт отдельную задачу, которая работает только с базой. Без `--classifiers` выбираются все
совместимые опубликованные артефакты. `analyze-pipeline` принимает те же настройки этапов и всегда
выполняет этапы SONARA, ML, CLASSIFIERS именно в таком порядке; `--ml-models` не может содержать SONARA.

Для структурных обновлений и необязательного повторного анализа следуйте странице
[«Миграция и повторный анализ хранилища SONARA»](../workflows/reanalyze-sonara-split-storage.md).

## Параметры текстового поиска

`dj-sim text-search` поддерживает:

| Параметр | Значение |
| --- | --- |
| `query` | обязательный текстовый запрос |
| `--limit` | число результатов `1..500` |
| `--min-similarity` | необязательный порог |
| `--device` | `auto`, `cpu` или `cuda` для текстового эмбеддинга CLAP |
| `--use-ann-index` | требовать постоянный индекс CLAP вместо точного поиска |
| `--index-dir` | нестандартный каталог индекса |

Если индекс отсутствует, устарел или не поддерживается, команда завершается ошибкой. Не указывайте
`--use-ann-index`, когда нужен точный поиск без вспомогательного индекса.

## Команды постоянных индексов

```powershell
dj-sim index build --model clap --db .\data\library.sqlite
dj-sim index verify --model clap --db .\data\library.sqlite
dj-sim index benchmark --model clap --db .\data\library.sqlite
dj-sim index clear --model clap --db .\data\library.sqlite
```

Доступные модели: `maest`, `mert`, `muq`, `clap`. Для `build`, `verify` и `benchmark` параметр
`--model` обязателен; в `clear` его можно не указывать только для очистки всех созданных индексов.

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

Команды требуют совместимую структуру SQLite и работают с локальной базой и файлами отчётов.
Команды экспорта кандидатов и профилирования источников принимают повторяемый `--source` со
значениями `mert`, `maest`, `muq`, `sonara`, `clap`. Без параметра используются все пять.
Стандартная выборка только с полным анализом теперь требует актуальное покрытие SONARA, MERT,
MAEST, MuQ и CLAP. Если полный набор не нужен, используйте `--allow-partial-analysis`.

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
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab_v7.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab_v7.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab_v7.sqlite
```

Предварительная проверка Audio Doctor:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

Отчёт Audio Dedup:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Стандартные источники эмбеддингов — `mert`, `maest`, `muq`, `clap`, их исходные веса — `0.43`,
`0.32`, `0.12`, `0.04`. Повторите `--source`, чтобы выбрать подмножество, а при переопределении
весов передайте по одному `--weight FAMILY=VALUE` для каждого включённого источника. Следующий
пример явно отключает MuQ и использует прежний набор:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --source mert --source maest --source clap --weight mert=0.43 --weight maest=0.32 --weight clap=0.04
```

Оптимизация базы:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Кратко о безопасности

- `scan`, `analyze`, `text-search`, `serve`, `doctor`, `index` и команды формирования отчётов оценки не переписывают аудио.
- `relocate-library --apply` меняет только пути SQLite.
- Audio Doctor `--apply` может переписывать исправимые файлы.
- Audio Dedup `--apply` может удалять файлы.
- Запись жанрового тега MAEST доступна через приложение и API, но не как верхнеуровневая команда `dj-sim`.

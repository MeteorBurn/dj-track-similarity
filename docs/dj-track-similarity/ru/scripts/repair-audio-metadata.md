# Скрипт восстановления аудиометаданных

По возможности запускайте этот скрипт через проектное Python-окружение:

```powershell
.\.venv\Scripts\python.exe scripts\audio_repair\repair_audio_metadata.py --help
```

Отдельный вспомогательный инструмент для диагностики и восстановления проблем с
аудиометаданными и контейнерами. Dry-run работает только на чтение и не
копирует и не записывает аудиофайлы. Каждый обычный запуск по умолчанию пишет
repair-специфичный JSON-отчёт, оформленную книгу XLSX и структурированный
текстовый лог в `scripts\audio_repair\reports`.

Используйте этот скрипт, когда сканирование, RefreshTags или запись жанров
сообщают о подозрительных либо нечитаемых метаданных, особенно для краевых
случаев WAV/AIFF/контейнеров. Не используйте его как обычный редактор тегов:
это диагностический и repair-инструмент для файлов, которые сам скрипт
классифицирует как безопасные для восстановления.

Использование:

```text
python scripts\audio_repair\repair_audio_metadata.py [OPTIONS] [paths ...]
```

Входные данные:

- позиционные `paths`: аудиофайлы для проверки или восстановления.
- `--folder FOLDER`: рекурсивно собрать поддерживаемые аудиофайлы из папки.
- `--db DB`: собрать существующие аудиофайлы из `tracks.path` в SQLite-базе
  библиотеки. База открывается только на чтение.
- `--db-root PATH`: использовать только пути базы данных под этим сохранённым
  корнем. Можно указывать несколько раз.
- `--file-root PATH`: заменить совпавший префикс `--db-root` этим реальным
  корнем файловой системы перед проверкой существования каждого файла.
- `--log LOG`: извлечь из лога проекта пути WAV с post-save readback failure.
- `--since TIMESTAMP`: использовать только строки лога с указанной временной
  метки и позже.
- `--until TIMESTAMP`: использовать только строки лога раньше указанной
  временной метки.

Параметры восстановления и безопасности:

- `--apply`: записать восстановленные файлы. По умолчанию используется dry-run.
- `--backup-dir PATH`: каталог резервных копий, используемый только с
  `--apply`.
- `--no-backup`: применить изменения без полных резервных копий файлов;
  используйте только если есть другая резервная копия.
- `--keep-id3 first|last|none`: для WAV-восстановления выбрать, какой читаемый
  ID3 chunk верхнего уровня сохранить. По умолчанию `first`.
- `--reason VALUE`: в folder/db-режиме применять только записи с сохранённой
  причиной. Можно указывать несколько раз.

Управление запуском:

- `--limit N`: обработать только первые собранные пути.
- `--summary-only`: вывести только итоговую сводку.
- `--color auto|always|never`: раскрашивать status labels.
- `--out-dir DIR`: каталог отчётов. По умолчанию
  `scripts\audio_repair\reports`.
- `--file-log PATH`: необязательный лог консольного transcript, который
  перезаписывается при каждом запуске. Он отделён от структурированного лога
  отчёта.
- `--no-file-log`: отключить необязательный консольный transcript log.
- `--no-report`: отключить bundle отчётов JSON/XLSX/log.
- `--state PATH`: явный state-файл для folder/db-режима.
- `--workers N`: параллельные воркеры для dry-run. Apply-режим всегда
  выполняется последовательно.

Структура, создаваемая по умолчанию:

```text
scripts\audio_repair\reports\audio_repair_report_<timestamp>.json
scripts\audio_repair\reports\audio_repair_report_<timestamp>.xlsx
scripts\audio_repair\reports\audio_repair_report_<timestamp>.log
scripts\audio_repair\state\state.<source>.<hash>.json
scripts\audio_repair\backups\<filename>.<timestamp>.<suffix>.bak
```

Bundle отчётов содержит только данные audio-repair. В нём нет группировки
дублей, delete candidates, Rhythm Lab impact или полей `audio_dedup`. JSON
хранит собранные источники, параметры запуска, state skips, число отсутствующих
DB-файлов, `status_counts`, `reason_counts`, `problem_summary` и один элемент
`results` на обработанный файл. Книга XLSX является основным артефактом для
проверки человеком и содержит три листа:

- `Summary`: режим, счётчики источников, число обработанных файлов, state
  skips, счётчики статусов и счётчики причин.
- `Results`: по одной строке на файл с action (`REPAIR AVAILABLE`, `REPAIRED`,
  `REVIEW MANUALLY` и так далее), status, reason, path, size delta, ID3
  counters, primary action, backup path и Mutagen summary.
- `Problems`: сгруппированная problem summary, соответствующая терминальному
  выводу.

Структурированный `.log` повторяет run-level счётчики в key-value формате для
быстрого поиска через grep или shell.

Рекомендуемый workflow:

1. Запустите dry-run на небольшом наборе путей, папке, логе или подмножестве
   базы данных.
2. Просмотрите сгенерированную книгу и status/reason для каждой записи
   `REPAIRABLE`.
3. Запускайте `--apply` только для конкретной причины или набора файлов,
   которые действительно собираетесь исправить.
4. Оставляйте backup включённым, если у вас уже нет внешней резервной копии.

Примеры:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --workers 4
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --apply --reason OVERSIZED_DATA
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes\Abstracted
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes --file-root S:\Music\Volumes
python scripts\audio_repair\repair_audio_metadata.py .\music\track.wav --summary-only
```

Значения статусов:

- `OK`: восстановление не требуется.
- `NOTICE`: косметическая необязательная очистка; файл не перезаписывается.
- `REPAIRABLE`: безопасное восстановление существует, но dry-run только
  сообщает о нём.
- `REPAIRED`: apply-режим записал и проверил восстановление.
- `SUSPICIOUS`: несоответствие формата/контейнера или кодека, требующее более
  внимательной проверки.
- `TAG-ERROR`: ошибка чтения тегов без безопасного repair-пути.
- `BROKEN`: файл не удалось разобрать как ожидаемый контейнер.
- `FAILED`: apply попытался выполнить repair, но запись или проверка не
  удалась.
- `UNSUPPORTED`: расширение вне repairable-набора WAV/AIFF; файл только
  inspected.

Причины:

В folder/db-режиме каждый результат также записывает причину в верхнем
регистре. Используйте её с `--reason`, чтобы повторно запустить apply только
для одного класса исправлений, например:

- `OVERSIZED_DATA`: WAV chunk `data` больше аудиополезной нагрузки перед ID3.
- `DUPLICATE_ID3`: больше одного top-level ID3 chunk в WAV.
- `EMPTY_ID3`: пустой AIFF chunk `ID3 `, блокирующий чтение Mutagen.
- `CONTAINER_NORMALIZATION`: нормализация root-size или padding RIFF/FORM.
- `EXTENSION_MISMATCH`: контейнер/кодек не соответствует расширению файла.

`--reason` допустим только в folder/db-режиме, потому что требует state-файл.
Используйте точный текст причины, показанный в отчёте.

Коды выхода:

- `0`: завершено без результатов `FAILED`.
- `1`: хотя бы один файл завершился статусом `FAILED`.
- `2`: ошибка использования, например `--file-root` без `--db-root`,
  `--reason` вне state-режима, `--backup-dir` вместе с `--no-backup` или
  отсутствие входных путей.

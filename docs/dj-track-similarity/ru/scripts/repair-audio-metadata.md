# Скрипт восстановления аудиометаданных

По возможности запускайте этот скрипт через project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\audio_repair\repair_audio_metadata.py --help
```

Standalone helper для диагностики и восстановления проблем audio metadata /
container. Dry-run работает read-only и не копирует и не пишет аудиофайлы.

Используйте этот скрипт, когда scanning, tag refresh или genre writing сообщает
о подозрительных или нечитаемых metadata, особенно для WAV/AIFF/container edge
cases. Не используйте его как general tag editor; это diagnostic и repair tool
для файлов, которые script классифицирует как safe to repair.

Usage:

```text
python scripts\audio_repair\repair_audio_metadata.py [OPTIONS] [paths ...]
```

Inputs:

- positional `paths`: аудиофайлы для inspect или repair.
- `--folder FOLDER`: рекурсивно собрать supported audio files из folder.
- `--db DB`: собрать existing audio files из `tracks.path` в SQLite library
  database. Database opened read-only.
- `--db-root PATH`: использовать только database paths под этим stored root.
  Можно повторять.
- `--file-root PATH`: заменить matching `--db-root` prefix этим real filesystem
  root перед проверкой существования каждого файла.
- `--log LOG`: извлечь post-save readback-failed WAV paths из project log.
- `--since TIMESTAMP`: использовать только log lines at or after timestamp.
- `--until TIMESTAMP`: использовать только log lines before timestamp.

Repair and safety options:

- `--apply`: записать repaired files. Default - dry-run.
- `--backup-dir PATH`: backup directory, используется только с `--apply`.
- `--no-backup`: apply без full-file backups; используйте только при наличии
  другого backup.
- `--keep-id3 first|last|none`: для WAV repair выбрать readable top-level ID3
  chunk, который оставить. Default - `first`.
- `--reason VALUE`: в folder или database mode применять только entries с
  stored reason. Можно повторять.

Run control:

- `--limit N`: обработать только первые collected paths.
- `--summary-only`: напечатать только final summary.
- `--color auto|always|never`: colorize status labels.
- `--file-log PATH`: file log path, перезаписывается на каждом run.
- `--no-file-log`: отключить file log.
- `--state PATH`: explicit folder/database-mode state file.
- `--workers N`: parallel dry-run workers. Apply mode всегда sequential.

Recommended workflow:

1. Запустите dry run на небольшом path, folder, log или database subset.
2. Проверьте status и reason для каждого `REPAIRABLE` entry.
3. Запускайте `--apply` только для конкретной reason или file set, который
   действительно хотите исправить.
4. Оставляйте backups включенными, если у вас нет внешнего backup.

Examples:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --workers 4
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --apply --reason OVERSIZED_DATA
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes\Abstracted
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes --file-root S:\Music\Volumes
python scripts\audio_repair\repair_audio_metadata.py .\music\track.wav --summary-only
```

Status meanings:

- `OK`: repair не требуется.
- `NOTICE`: необязательная cleanup.
- `SUSPICIOUS`: format/container или codec mismatch.
- `TAG-ERROR`: tag-read failure без safe repair path.
- `REPAIRABLE`: safe repair logic exists.
- `REPAIRED`: apply mode succeeded.


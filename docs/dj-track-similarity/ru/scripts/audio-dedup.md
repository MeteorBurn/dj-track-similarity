# Скрипт отчета о дублях аудио

По возможности запускайте этот скрипт через project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --help
```

Report-only helper для candidate duplicates audio. Он читает существующую
SQLite database `dj-track-similarity`, сравнивает tracks внутри выбранного
stored path root и пишет JSON, CSV и text-log reports. Он никогда не удаляет
аудиофайлы и никогда не изменяет database.

Используйте этот script, когда нужны доказательства возможных duplicate audio
перед ручной очисткой library. Он намеренно conservative: создает reports, а не
delete commands.

Usage:

```text
python scripts\audio_dedup\audio_dedup.py --root ROOT [OPTIONS]
```

Options:

- `--db DB`: project SQLite database. Default - `C:\db\abstracted.sqlite`.
- `--root ROOT`: required stored path root для ограничения candidate tracks.
- `--path-contains TEXT`: дополнительный case-insensitive path filter. Можно
  повторять.
- `--preset safe|balanced|aggressive`: scoring preset. Default - `safe`.
- `--min-score SCORE`: override preset duplicate threshold.
- `--limit-groups N`: записать не больше N duplicate groups.
- `--out-dir DIR`: output report directory. Default -
  `scripts\audio_dedup\reports`.

Examples:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset balanced --path-contains mastered
```

Outputs называются `audio_dedup_report_<timestamp>.json`, `.csv` и `.log`.
Default report directory игнорируется git. Проверяйте каждого candidate вручную;
report включает suggested keepers и candidate-delete evidence, но script
намеренно не выполняет delete action.

Начинайте с preset `safe` для обычного library maintenance. Используйте
`balanced` или `aggressive` только если готовы просматривать больше false
positives.


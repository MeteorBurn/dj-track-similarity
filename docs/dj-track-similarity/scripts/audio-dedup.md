# Audio Dedup Report Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --help
```

Report-only duplicate-audio candidate helper. It reads an existing
`dj-track-similarity` SQLite database, compares tracks inside a selected stored
path root, and writes JSON, CSV, and text-log reports. It never deletes audio
files and never mutates the database.

Use this script when you want evidence for possible duplicate audio before
cleaning a library manually. It is intentionally conservative: it produces
reports, not delete commands.

Usage:

```text
python scripts\audio_dedup\audio_dedup.py --root ROOT [OPTIONS]
```

Options:

- `--db DB`: project SQLite database. Default is `C:\db\abstracted.sqlite`.
- `--root ROOT`: required stored path root used to limit candidate tracks.
- `--path-contains TEXT`: additional case-insensitive path filter. Can be
  repeated.
- `--preset safe|balanced|aggressive`: scoring preset. Default is `safe`.
- `--min-score SCORE`: override the preset duplicate threshold.
- `--limit-groups N`: write at most N duplicate groups.
- `--out-dir DIR`: output report directory. Default is
  `scripts\audio_dedup\reports`.

Examples:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset balanced --path-contains mastered
```

Outputs are named `audio_dedup_report_<timestamp>.json`, `.csv`, and `.log`.
The default report directory is ignored by git. Review every candidate manually;
the report includes suggested keepers and candidate-delete evidence, but the
script intentionally performs no delete action.

Start with the `safe` preset for normal library maintenance. Use `balanced` or
`aggressive` only when you are comfortable reviewing more false positives.

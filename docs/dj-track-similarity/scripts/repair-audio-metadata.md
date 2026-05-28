# Audio Metadata Repair Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\audio_repair\repair_audio_metadata.py --help
```

Standalone diagnostic and repair helper for audio metadata/container issues.
Dry-run is read-only and does not copy or write audio files.

Use this script when scanning, tag refresh, or genre writing reports suspicious
or unreadable metadata, especially for WAV/AIFF/container edge cases. Do not use
it as a general tag editor; it is a diagnostic and repair tool for files the
script classifies as safe to repair.

Usage:

```text
python scripts\audio_repair\repair_audio_metadata.py [OPTIONS] [paths ...]
```

Inputs:

- positional `paths`: audio files to inspect or repair.
- `--folder FOLDER`: recursively collect supported audio files from a folder.
- `--db DB`: collect existing audio files from `tracks.path` in a SQLite
  library database. The database is opened read-only.
- `--db-root PATH`: only use database paths under this stored root. Can be
  repeated.
- `--file-root PATH`: replace the matching `--db-root` prefix with this real
  filesystem root before checking whether each file exists.
- `--log LOG`: extract post-save readback-failed WAV paths from a project log.
- `--since TIMESTAMP`: only use log lines at or after a timestamp.
- `--until TIMESTAMP`: only use log lines before a timestamp.

Repair and safety options:

- `--apply`: write repaired files. Default is dry-run.
- `--backup-dir PATH`: backup directory used only with `--apply`.
- `--no-backup`: apply without full-file backups; use only if another backup
  exists.
- `--keep-id3 first|last|none`: for WAV repair, choose which readable top-level
  ID3 chunk to keep. Default is `first`.
- `--reason VALUE`: in folder or database mode, apply only entries with a
  stored reason. Can be repeated.

Run control:

- `--limit N`: process only the first collected paths.
- `--summary-only`: print only the final summary.
- `--color auto|always|never`: colorize status labels.
- `--file-log PATH`: file log path overwritten on every run.
- `--no-file-log`: disable the file log.
- `--state PATH`: explicit folder/database-mode state file.
- `--workers N`: parallel dry-run workers. Apply mode always runs sequentially.

Recommended workflow:

1. Run a dry run against a small path, folder, log, or database subset.
2. Review the status and reason for every `REPAIRABLE` entry.
3. Run `--apply` only for the specific reason or file set you intend to fix.
4. Keep backups enabled unless you already have an external backup.

Examples:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --workers 4
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --apply --reason OVERSIZED_DATA
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes\Abstracted
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes --file-root S:\Music\Volumes
python scripts\audio_repair\repair_audio_metadata.py .\music\track.wav --summary-only
```

Status meanings:

- `OK`: no repair needed.
- `NOTICE`: non-required cleanup.
- `SUSPICIOUS`: format/container or codec mismatch.
- `TAG-ERROR`: tag-read failure without a safe repair path.
- `REPAIRABLE`: safe repair logic exists.
- `REPAIRED`: apply mode succeeded.

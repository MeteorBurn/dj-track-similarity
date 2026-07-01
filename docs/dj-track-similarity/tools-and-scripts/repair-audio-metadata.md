# Repair audio metadata helper

> Audience: Power users investigating broken metadata or WAV ID3 issues.
> Goal: Use the dry-run-first repair script with clear backup expectations.
> Type: how-to

## Dry-run

```powershell
.\.venv\Scripts\python.exe scripts\audio_repair\repair_audio_metadata.py --folder <music-folder>
```

Dry-run does not write or copy audio.

## Database input

`--db` opens SQLite read-only. `--db-root` plus `--file-root` remaps stored roots before filesystem checks; missing remapped files are skipped.

## Apply backup

`--apply` writes only repairable files. Unless `--no-backup` is used, it creates a full-file backup before writing, deletes it after successful verification, or restores from it on failure and then deletes it. Do not treat backups as a retained archive.

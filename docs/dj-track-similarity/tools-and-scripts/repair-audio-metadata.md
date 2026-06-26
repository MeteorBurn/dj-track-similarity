# Repair audio metadata

Audience: careful power users  
Goal: inspect and optionally repair known metadata/container issues  
Type: how-to/reference

`scripts/audio_repair/repair_audio_metadata.py` is a standalone helper. It is
dry-run-first and separate from the app's normal tag-writing path.

## Dry-run

Activate the project environment once:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

Inspect a folder:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder D:\Music
```

Inspect paths from a project database:

```powershell
python scripts\audio_repair\repair_audio_metadata.py `
  --db .\data\library.sqlite `
  --db-root D:\Music
```

Dry-run is read-only. It does not copy or write audio files.

## Reports and state

The script can write JSON, XLSX, and structured log reports under
`scripts/audio_repair/reports` by default. Folder and DB mode use state files
under `scripts/audio_repair/state` so you can later process selected reasons.

## Apply

```powershell
python scripts\audio_repair\repair_audio_metadata.py `
  --folder D:\Music `
  --reason REPAIRABLE `
  --apply
```

Apply mode is sequential. It rewrites only files the script reports as
repairable. Full-file backups are created by default under
`scripts/audio_repair/backups`.

Use `--no-backup` only when you already have a separate backup.

## Common selectors

- `--log` extracts post-save readback-failed WAV paths from a project log.
- `--since` and `--until` restrict log timestamps.
- `--file-root` remaps paths collected from a `--db-root`.
- `--limit` processes only the first selected paths.
- `--workers` controls parallel dry-run workers; apply always runs
  sequentially.

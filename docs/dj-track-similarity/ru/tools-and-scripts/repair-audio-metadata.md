# Repair audio metadata

Аудитория: осторожные power users  
Цель: inspect и optionally repair known metadata/container issues  
Тип: how-to/reference

`scripts/audio_repair/repair_audio_metadata.py` - standalone helper. Он
dry-run-first и отделен от normal app tag-writing path.

## Dry-run

Активируйте project environment один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

Inspect folder:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder D:\Music
```

Inspect paths from project database:

```powershell
python scripts\audio_repair\repair_audio_metadata.py `
  --db .\data\library.sqlite `
  --db-root D:\Music
```

Dry-run read-only. Он не copy и не write audio files.

## Reports and state

Script может писать JSON, XLSX и structured log reports в
`scripts/audio_repair/reports` by default. Folder and DB mode use state files
under `scripts/audio_repair/state`, чтобы позже process selected reasons.

## Apply

```powershell
python scripts\audio_repair\repair_audio_metadata.py `
  --folder D:\Music `
  --reason REPAIRABLE `
  --apply
```

Apply mode sequential. Он rewrites only files reported as repairable. Full-file
backups создаются by default under `scripts/audio_repair/backups`.

Используйте `--no-backup` только если у вас уже есть separate backup.

## Common selectors

- `--log` extracts post-save readback-failed WAV paths from a project log.
- `--since` and `--until` restrict log timestamps.
- `--file-root` remaps paths collected from a `--db-root`.
- `--limit` processes only the first selected paths.
- `--workers` controls parallel dry-run workers; apply always runs
  sequentially.

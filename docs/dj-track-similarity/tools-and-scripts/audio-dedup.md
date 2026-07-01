# Audio Dedup

> Audience: Users looking for duplicate audio candidates.
> Goal: Generate reports first and apply deletion only with explicit confirmation.
> Type: how-to

## Report mode

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\audio_dedup_cli.py --db <library-db> --root <music-folder>
```

Default mode writes JSON/XLSX/log reports and deletes nothing.

## Apply

`--apply` is destructive. It prompts for exact confirmation `APPLY DELETE`, deletes only safe duplicate candidates inside the selected root, and removes SQLite rows only after files are successfully deleted.

# Audio dedup

Audience: careful power users  
Goal: generate duplicate-audio reports and understand explicit apply mode  
Type: how-to/reference

The duplicate-audio tool reads an existing project SQLite database and compares
tracks inside a selected stored path root. By default it writes reports only.

## Report-only run

Activate the project environment once:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

```powershell
python tools\audio-dedup\audio_dedup_cli.py `
  --db .\data\library.sqlite `
  --root D:\Music `
  --preset safe
```

Useful options:

- `--path-contains` filters stored paths and can be repeated.
- `--preset` is `safe`, `balanced`, or `aggressive`.
- `--min-score` and `--min-similarity` override preset thresholds.
- `--limit-groups` limits the number of duplicate groups written.
- `--out-dir` changes the report directory.

## Apply mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py `
  --db .\data\library.sqlite `
  --root D:\Music `
  --preset safe `
  --apply
```

Apply mode writes reports first, then prompts for confirmation before deleting
safe duplicate candidates and their database rows. Do not run apply mode from
routine tests or broad verification.

## Main UI job

The UI exposes the same safety boundary. Apply mode requires the exact
confirmation text `APPLY DELETE`.

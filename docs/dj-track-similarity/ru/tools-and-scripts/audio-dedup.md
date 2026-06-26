# Audio dedup

Аудитория: осторожные power users  
Цель: создавать duplicate-audio reports и понимать explicit apply mode  
Тип: how-to/reference

Duplicate-audio tool читает existing project SQLite database и сравнивает tracks
внутри selected stored path root. By default он пишет только reports.

## Report-only run

Активируйте project environment один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

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
- `--limit-groups` limits duplicate groups written.
- `--out-dir` changes report directory.

## Apply mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py `
  --db .\data\library.sqlite `
  --root D:\Music `
  --preset safe `
  --apply
```

Apply mode сначала пишет reports, затем prompts for confirmation before
deleting safe duplicate candidates and their database rows. Не запускайте apply
mode из routine tests или broad verification.

## Main UI job

UI exposes same safety boundary. Apply mode требует exact confirmation text
`APPLY DELETE`.

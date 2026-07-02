# Audio Dedup

> Audience: Users looking for duplicate audio candidates.
> Goal: Generate reports first and apply deletion only with explicit confirmation.
> Type: how-to

## Report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db <library-db> --root <music-folder>
```

Default mode writes JSON/XLSX/log reports and deletes nothing.

Audio Dedup `Min similarity` is an audio-to-audio content gate over stored MERT, MAEST, and CLAP audio embeddings. It is not comparable to the lower CLAP text-search score range, so do not lower duplicate-delete thresholds just because CLAP prompt scores look smaller.

## UI and API

The main UI opens Audio Dedup from the top toolbar. The UI supports preset selection, report output, cancellation, and XLSX download. The API endpoints live under `/api/audio-dedup/jobs`.

## Apply

`--apply` is destructive. It prompts for exact confirmation `APPLY DELETE` before removing safe duplicate candidates inside the selected root. SQLite rows are removed only after files are successfully deleted.

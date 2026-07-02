# Audio Doctor

> Audience: Power users investigating broken metadata or WAV/AIFF container issues.
> Goal: Run dry-run-first inspection and apply only verified repairs.
> Type: how-to

## Dry-run

```powershell
python tools\audio-doctor\audio_doctor_cli.py --folder <music-folder>
```

Dry-run does not write or copy audio. It writes JSON, XLSX, and log reports under `tools\audio-doctor\data\reports` by default and stores repeat-run state under `tools\audio-doctor\data\state`.

## Database input

`--db` opens SQLite read-only and reads `tracks.path`. `--db-root` plus `--file-root` remaps stored roots before filesystem checks. Missing remapped files are skipped.

## UI and API

The main UI opens Audio Doctor from the top toolbar. The UI supports selected-database and folder sources, state/reason filters, reports, cancellation, and XLSX download. The API endpoints live under `/api/audio-doctor/jobs`.

## Apply

`--apply` writes only repairable WAV/AIFF cases. Unless `--no-backup` is used, it creates a full-file backup before writing. After verification, the backup is deleted or used for restore on failure. UI/API apply mode requires exact confirmation `APPLY REPAIR` and is intended to run after a dry-run state exists.

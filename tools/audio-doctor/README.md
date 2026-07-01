# Audio Doctor

Dry-run-first metadata and container repair helper for `dj-track-similarity`.

```powershell
.\.venv\Scripts\python.exe tools\audio-doctor\audio_doctor_cli.py --help
```

Dry-run by folder:

```powershell
.\.venv\Scripts\python.exe tools\audio-doctor\audio_doctor_cli.py --folder <music-folder>
```

Dry-run by selected SQLite database, with optional stored-root remapping:

```powershell
.\.venv\Scripts\python.exe tools\audio-doctor\audio_doctor_cli.py --db <library-db> --db-root <stored-root> --file-root <local-root>
```

Apply only after a dry-run has recorded state:

```powershell
.\.venv\Scripts\python.exe tools\audio-doctor\audio_doctor_cli.py --folder <music-folder> --apply --reason OVERSIZED_DATA
```

Apply writes only repairable WAV/AIFF cases, creates full-file backups by
default, verifies the repaired file, and restores the backup on verification
failure. UI/API apply mode additionally requires the exact `APPLY REPAIR`
confirmation.

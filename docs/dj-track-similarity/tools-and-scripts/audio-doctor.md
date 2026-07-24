# Audio Doctor

> Audience: Users diagnosing audio metadata/container problems.
> Goal: Run dry-run checks and use repair mode only after review.
> Type: guide

Audio Doctor inspects audio files for known metadata/container issues and can repair only known safe repairable states. It is dry-run-first.

## UI source modes

Open Audio Doctor from the wrench icon in the top bar.

**Selected DB** reads `tracks.file_path` from the selected SQLite database. Optional **DB roots** restrict stored paths, and **File root** remaps matching DB roots before filesystem checks.

**Folder** recursively scans a filesystem folder.

## UI controls

- **keep-id3**: `first`, `last`, or `none` for WAV repair handling.
- **Workers**: `1..32` for dry-run. Apply always runs sequentially.
- **Limit**: optional first N pending files.
- **Reason**: optional reason filters from prior state/report entries.
- **Output dir**: report bundle directory.
- **State path**: optional state JSON path for repeat dry-run/apply workflows.

Click **Start** for dry-run mode. Review the XLSX report before any repair.

## CLI dry-run

Folder:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --folder D:\Music
```

Selected database:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

With root remapping:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite --db-root D:\OldMusic --file-root E:\Music
```

## Apply mode

Apply mode requires exact confirmation in the UI/API:

```text
APPLY REPAIR
```

The app also requires prior dry-run state. In the standalone CLI, apply creates full-file backups by default unless you explicitly disable backups.

Apply mode repairs only entries reported as repairable. It is not a general tag editor.

## Output

Reports and state live under `tools/audio-doctor/data/` by default. Treat them as private because they include file paths and diagnostics.

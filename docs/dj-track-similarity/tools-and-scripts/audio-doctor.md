# Audio Doctor

> Audience: Users diagnosing audio metadata/container problems.
> Goal: Run dry-run checks and use repair mode only after review.
> Type: guide

Audio Doctor inspects audio files for known metadata/container issues and can repair only known safe repairable states. It is dry-run-first.

## Inputs

Use `--db` to inspect the database's `tracks.file_path` values. `--db-root` limits stored paths, and `--file-root` remaps matching stored roots before filesystem checks. Use `--folder` to scan a filesystem folder recursively.

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

Apply mode requires the exact CLI confirmation:

```text
APPLY REPAIR
```

The app also requires prior dry-run state. In the standalone CLI, apply creates full-file backups by default unless you explicitly disable backups.

Apply mode repairs only entries reported as repairable. It is not a general tag editor.

## Output

Reports and state live under `tools/audio-doctor/data/` by default. Treat them as private because they include file paths and diagnostics.

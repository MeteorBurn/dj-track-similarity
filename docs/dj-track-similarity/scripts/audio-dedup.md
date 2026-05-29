# Audio Dedup Report Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --help
```

Duplicate-audio candidate helper. By default it is report-only: it reads an
existing `dj-track-similarity` SQLite database, compares tracks inside a
selected stored path root, and writes JSON, styled XLSX, and text-log reports.

Use this script when you want evidence for possible duplicate audio before
cleaning a library manually. It is intentionally conservative: it produces
reports first. Destructive cleanup is available only with `--apply` and an
interactive confirmation prompt.

Usage:

```text
python scripts\audio_dedup\audio_dedup.py --root ROOT [OPTIONS]
```

Options:

- `--db DB`: project SQLite database. Default is `C:\db\abstracted.sqlite`.
- `--root ROOT`: required stored path root used to limit candidate tracks.
- `--path-contains TEXT`: additional case-insensitive path filter. Can be
  repeated.
- `--preset safe|balanced|aggressive`: scoring preset. Default is `safe`.
- `--min-score SCORE`: override the preset duplicate threshold.
- `--limit-groups N`: write at most N duplicate groups.
- `--out-dir DIR`: output report directory. Default is
  `scripts\audio_dedup\reports`.
- `--apply`: after reports are written, ask for an exact confirmation phrase
  and delete only candidates marked `DELETE CANDIDATE` / `true_candidate`.
  Tracks are removed from SQLite only after their audio files are successfully
  deleted.

Examples:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset balanced --path-contains mastered
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset safe --apply
```

Outputs are named `audio_dedup_report_<timestamp>.json`, `.xlsx`, and `.log`.
The default report directory is ignored by git.

The workbook is the main human review artifact. It includes:

- `Summary`: database path, selected root, total track count in the database,
  track count inside the selected root/filter scope, and high-level duplicate
  statistics.
- `Groups`: one row per duplicate group, with the suggested `KEEP` track and
  the reasons it outranks the other files.
- `Candidates`: one row per duplicate candidate, with `DELETE CANDIDATE` or
  `REVIEW MANUALLY`, the keeper path, direct score, similarity evidence, and
  review blockers.
- `Pair Evidence`: the detailed pairwise MERT, MAEST, SONARA, CLAP, and
  duration evidence used by the grouping step. Tagged BPM/key values are shown
  only as track metadata and are not used for duplicate scoring; SONARA BPM
  remains part of the SONARA similarity signal when available.

Review every candidate manually; the report includes suggested keepers and
candidate-delete evidence.

Apply mode:

1. The script writes the JSON/XLSX/log reports first.
2. It counts safe delete candidates only.
3. It prints a destructive-action warning and requires typing exactly
   `APPLY DELETE`.
4. It deletes only files still inside the selected `--root`.
5. It removes SQLite rows only for tracks whose files were successfully
   deleted. Related rows in tables with a `track_id` column are removed before
   the `tracks` row.

Do not use `--apply` until you have reviewed the generated workbook. Automated
tests and routine verification should not invoke the script with `--apply`.

Start with the `safe` preset for normal library maintenance. Use `balanced` or
`aggressive` only when you are comfortable reviewing more false positives.

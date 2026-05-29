# Audio Metadata Repair Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\audio_repair\repair_audio_metadata.py --help
```

Standalone diagnostic and repair helper for audio metadata/container issues.
Dry-run is read-only and does not copy or write audio files. Each normal run
writes a repair-specific JSON report, styled XLSX workbook, and structured text
log under `scripts\audio_repair\reports` by default.

Use this script when scanning, tag refresh, or genre writing reports suspicious
or unreadable metadata, especially for WAV/AIFF/container edge cases. Do not use
it as a general tag editor; it is a diagnostic and repair tool for files the
script classifies as safe to repair.

Usage:

```text
python scripts\audio_repair\repair_audio_metadata.py [OPTIONS] [paths ...]
```

Inputs:

- positional `paths`: audio files to inspect or repair.
- `--folder FOLDER`: recursively collect supported audio files from a folder.
- `--db DB`: collect existing audio files from `tracks.path` in a SQLite
  library database. The database is opened read-only.
- `--db-root PATH`: only use database paths under this stored root. Can be
  repeated.
- `--file-root PATH`: replace the matching `--db-root` prefix with this real
  filesystem root before checking whether each file exists.
- `--log LOG`: extract post-save readback-failed WAV paths from a project log.
- `--since TIMESTAMP`: only use log lines at or after a timestamp.
- `--until TIMESTAMP`: only use log lines before a timestamp.

Repair and safety options:

- `--apply`: write repaired files. Default is dry-run.
- `--backup-dir PATH`: backup directory used only with `--apply`.
- `--no-backup`: apply without full-file backups; use only if another backup
  exists.
- `--keep-id3 first|last|none`: for WAV repair, choose which readable top-level
  ID3 chunk to keep. Default is `first`.
- `--reason VALUE`: in folder or database mode, apply only entries with a
  stored reason. Can be repeated.

Run control:

- `--limit N`: process only the first collected paths.
- `--summary-only`: print only the final summary.
- `--color auto|always|never`: colorize status labels.
- `--out-dir DIR`: report output directory. Default is
  `scripts\audio_repair\reports`.
- `--file-log PATH`: optional console transcript log path overwritten on every
  run. This is separate from the structured report log.
- `--no-file-log`: disable the optional console transcript log.
- `--no-report`: disable the JSON/XLSX/log report bundle.
- `--state PATH`: explicit folder/database-mode state file.
- `--workers N`: parallel dry-run workers. Apply mode always runs sequentially.

Default generated structure:

```text
scripts\audio_repair\reports\audio_repair_report_<timestamp>.json
scripts\audio_repair\reports\audio_repair_report_<timestamp>.xlsx
scripts\audio_repair\reports\audio_repair_report_<timestamp>.log
scripts\audio_repair\state\state.<source>.<hash>.json
scripts\audio_repair\backups\<filename>.<timestamp>.<suffix>.bak
```

The report bundle contains only audio-repair data. It does not include duplicate
grouping, delete candidates, Rhythm Lab impact, or any `audio_dedup` fields.
The JSON stores the collected sources, run options, state skips, missing DB-file
count, `status_counts`, `reason_counts`, `problem_summary`, and one `results`
entry per processed file. The XLSX workbook is the main review artifact and has
three sheets:

- `Summary`: mode, source counts, processed counts, state skips, status counts,
  and reason counts.
- `Results`: one row per file with action (`REPAIR AVAILABLE`, `REPAIRED`,
  `REVIEW MANUALLY`, and so on), status, reason, path, size delta, ID3 counts,
  primary action, backup path, and Mutagen summary.
- `Problems`: grouped problem summary matching the terminal output.

The structured `.log` mirrors the run-level counts in key-value form for quick
grep or shell review.

Recommended workflow:

1. Run a dry run against a small path, folder, log, or database subset.
2. Review the generated workbook and the status/reason for every `REPAIRABLE`
   entry.
3. Run `--apply` only for the specific reason or file set you intend to fix.
4. Keep backups enabled unless you already have an external backup.

Examples:

```powershell
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --workers 4
python scripts\audio_repair\repair_audio_metadata.py --folder .\music --apply --reason OVERSIZED_DATA
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes\Abstracted
python scripts\audio_repair\repair_audio_metadata.py --db C:\db\abstracted.sqlite --db-root M:\Volumes --file-root S:\Music\Volumes
python scripts\audio_repair\repair_audio_metadata.py .\music\track.wav --summary-only
```

Status meanings:

- `OK`: no repair needed.
- `NOTICE`: cosmetic, non-required cleanup; not rewritten.
- `REPAIRABLE`: a safe repair exists (dry-run only reports it).
- `REPAIRED`: apply mode wrote a verified repair.
- `SUSPICIOUS`: format/container or codec mismatch worth a closer look.
- `TAG-ERROR`: tag-read failure without a safe repair path.
- `BROKEN`: the file could not be parsed as the expected container.
- `FAILED`: apply attempted a repair but it could not be written or verified.
- `UNSUPPORTED`: extension outside the repairable WAV/AIFF set; inspected only.

Reasons:

In folder or database mode, each result also records an uppercase reason. Use it
with `--reason` to re-run apply against only one class of fix, for example:

- `OVERSIZED_DATA`: a WAV `data` chunk larger than the audio payload before ID3.
- `DUPLICATE_ID3`: more than one top-level ID3 chunk in a WAV.
- `EMPTY_ID3`: an empty AIFF `ID3 ` chunk that blocks Mutagen reads.
- `CONTAINER_NORMALIZATION`: RIFF/FORM root-size or padding normalization.
- `EXTENSION_MISMATCH`: container/codec does not match the file extension.

`--reason` is only valid in folder or database mode (it requires the state
file). Match the exact reason text shown in the report.

Exit codes:

- `0`: completed with no `FAILED` results.
- `1`: at least one file ended in the `FAILED` status.
- `2`: a usage error, such as `--file-root` without `--db-root`, `--reason`
  outside state mode, `--backup-dir` together with `--no-backup`, or no input
  paths found.

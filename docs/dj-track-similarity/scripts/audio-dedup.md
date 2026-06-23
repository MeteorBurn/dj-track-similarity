# Audio Dedup Report and Cleanup Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --help
```

Duplicate-audio helper with two modes. By default it is report-only: it reads an
existing `dj-track-similarity` SQLite database, compares tracks inside a
selected stored path root, and writes JSON, styled XLSX, and text-log reports.
The report also checks the default Rhythm Lab database at
`tools\rhythm-lab\data\rhythm_lab.sqlite` and lists any lab rows that would be
removed for safe delete candidates. The JSON report stores both a compact
`rhythm_lab.summary` object and the detailed affected rows; the text log writes
the same summary as a `rhythm_lab_summary=...` line.
With `--apply` it adds a confirmed cleanup pass that deletes safe duplicate
files and their database rows after the reports are written. If a Rhythm Lab
database exists at the default path, apply mode also removes matching lab rows
for the deleted source track IDs.

Use the default report mode when you want evidence for possible duplicate audio
before cleaning a library. It is intentionally conservative: it always produces
the reports first. The destructive cleanup runs only with `--apply` and an
interactive confirmation prompt, and it deletes only candidates the report
marks as safe.

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
- `--min-similarity SCORE`: override the preset embedding content-similarity
  threshold.
- `--limit-groups N`: write at most N duplicate groups.
- `--out-dir DIR`: output report directory. Default is
  `scripts\audio_dedup\reports`.
- `--apply`: after reports are written, ask for an exact confirmation phrase
  and delete only candidates marked `DELETE CANDIDATE` / `true_candidate`.
  Tracks are removed from SQLite only after their audio files are successfully
  deleted.

## Presets

Each preset sets a default duplicate-score threshold, an embedding
content-similarity threshold, a stricter direct keeper-match threshold for
automatic delete candidates, and how strict the duration match must be.
`--min-score` overrides only the report inclusion score threshold;
`--min-similarity` overrides only the embedding similarity gate. The
safe-delete and duration parameters stay as listed.

| Preset | Min score | Min content similarity | Safe delete score | Duration tolerance | Use when |
| --- | --- | --- | --- | --- | --- |
| `safe` | `0.965` | `0.985` | `0.980` | ~2 s / 1% ratio | Conservative maintenance with the fewest false positives. |
| `balanced` | `0.950` | `0.970` | `0.970` | ~5 s / 2.5% ratio | A wider net that can still mark strong candidates for deletion. |
| `aggressive` | `0.925` | `0.940` | `0.965` | ~15 s / 8% ratio | Broadest matching; expect more manual review, but very strong direct matches can still be delete candidates. |

## Scoring

The pair score blends available signals into a single value in `0..1`,
normalized by the weight of the signals that exist for both tracks:

| Signal | Weight |
| --- | --- |
| MERT embedding similarity | `0.43` |
| MAEST embedding similarity | `0.32` |
| SONARA feature similarity | `0.14` |
| CLAP embedding similarity | `0.04` |
| Duration closeness | `0.05` |

Candidate grouping also requires a separate `content_similarity` value built
from embeddings only: MERT, MAEST, and CLAP with the same relative embedding
weights shown above. This prevents the script from treating tracks as duplicate
audio solely because SONARA texture features and duration look alike. Pairs with
no usable embedding similarity are excluded from duplicate groups.

Each group is labelled with a confidence tier of `high`, `medium`, or `review`
based on its score and any blocking reasons. Tagged BPM/key values are shown as
track metadata only and are never used for duplicate scoring.

Examples:

```powershell
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset balanced --path-contains mastered
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset safe --min-similarity 0.99
.\.venv\Scripts\python.exe scripts\audio_dedup\audio_dedup.py --db .\data\library.sqlite --root D:\Music --preset safe --apply
```

Outputs are named `audio_dedup_report_<timestamp>.json`, `.xlsx`, and `.log`.
The default report directory is ignored by git.

The CLI prints a short terminal summary after each run, including the duplicate
group count, safe delete candidate count in report mode, and Rhythm Lab
database/affected-row counts.

The workbook is the main human review artifact. It includes:

- `Summary`: database path, selected root, preset, score threshold, total track
  count in the database, track count inside the selected root/filter scope,
  duplicate-group and candidate counts, a confidence breakdown
  (`high`/`medium`/`review`), the content-similarity threshold, and
  MERT/MAEST/CLAP embedding coverage counts.
- `Groups`: one row per duplicate group, with the suggested `KEEP` track and
  the reasons it outranks the other files.
- `Candidates`: one row per duplicate candidate, with `DELETE CANDIDATE` or
  `REVIEW MANUALLY`, the keeper path, direct score, embedding-only content
  similarity, similarity evidence, and review blockers.
- `Pair Evidence`: the detailed pairwise MERT, MAEST, SONARA, CLAP, and
  duration evidence used by the grouping step, plus the combined
  `content_similarity` gate value. Tagged BPM/key values are shown only as
  track metadata and are not used for duplicate scoring; SONARA BPM remains
  part of the SONARA similarity signal when available.
- `Rhythm Lab`: rows in the default Rhythm Lab database that would be removed
  by apply mode for candidates marked safe to delete. If the database is
  missing or no safe candidate has lab rows, the sheet contains only headers.

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
6. It opens `tools\rhythm-lab\data\rhythm_lab.sqlite`, when it exists, and
   removes rows whose `source_track_id` matches the successfully deleted track
   IDs. This cleans manual labels and predictions without touching classifier
   profiles or training checkpoints.
7. It rewrites the JSON and log reports with `mode` set to `apply` and an
   `apply_result` block listing deleted track IDs, deleted paths, and any
   skipped or failed deletions, plus the Rhythm Lab row cleanup count. The
   log also writes a `deleted_files:` block with one `deleted_file=...` line
   for each file successfully removed from disk. The existing
   `rhythm_lab.summary` block remains in the JSON as the pre-apply impact
   summary that was shown in the workbook.

If you decline the confirmation, the reports stay on disk and nothing is
deleted. Do not use `--apply` until you have reviewed the generated workbook.
Automated tests and routine verification should not invoke the script with
`--apply`.

Start with the `safe` preset for normal library maintenance. Use `balanced` or
`aggressive` only when you are comfortable reviewing more false positives.

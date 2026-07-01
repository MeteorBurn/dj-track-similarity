# Maintain a library safely

> Audience: Users keeping a changing music folder usable over time.
> Goal: Refresh tags, relocate paths, report duplicates, and optimize SQLite without accidental audio writes.
> Type: how-to

## Routine

- Scan new folders or changed files.
- Refresh Tags when external metadata changed.
- Run missing analysis after adding tracks.
- Use relocation preview before apply.
- Backup important reports before cleanup.

## Risky tools

Audio Dedup is report-only by default and destructive only with apply confirmation. Audio repair is dry-run-first and writes only with `--apply`. Database optimization creates a SQLite backup before maintenance.

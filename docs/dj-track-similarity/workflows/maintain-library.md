# Maintain a library safely

> Audience: Users keeping local music state healthy.
> Goal: Maintain the database bundle without changing source audio.
> Type: workflow

1. Scan after adding files. Scan updates Core tracks and tags without writing audio.
2. Keep Core and mandatory `*.artifacts.sqlite` together. They are bound by `catalog_uuid`.
3. Treat `*.evaluation.sqlite` as optional evaluation state.
4. Use relocation preview before apply. Apply changes stored `tracks.file_path` only; it never moves,
   copies, deletes, or retags audio.
5. Run Audio Doctor and Audio Dedup in report mode before their confirmation-gated apply modes.

When a database structure changes, preview `dj-sim migrate-database --db <path> --dry-run`. Apply
only after reviewing the plan; the exact `MIGRATE DATABASE` confirmation creates verified Core and
Artifacts backups before rebuilding. Reanalysis and classifier retraining remain separate choices.

Use `python scripts\optimize_database.py --db .\data\library.sqlite` only for a local bundle you
control. It validates and backs up Core + Artifacts before maintenance. The browser supports
scan, Refresh Tags, relocation preview, and report-first helper jobs; database optimization remains
an explicit script workflow.

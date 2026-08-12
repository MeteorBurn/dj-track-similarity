# Maintain a library safely

> Audience: Users keeping local music state healthy.
> Goal: Maintain the database bundle without changing source audio.
> Type: workflow

1. Scan after adding files. Scan updates library tracks and tags without writing audio.
2. Keep `library.sqlite` backed up. Include optional `*.evaluation.sqlite` when it exists.
3. Treat `*.evaluation.sqlite` as optional evaluation state.
4. Use relocation preview before apply. Apply changes stored `tracks.file_path` only; it never moves,
   copies, deletes, or retags audio.
5. Run Audio Doctor and Audio Dedup in report mode before their confirmation-gated apply modes.

When a database structure changes, keep a verified backup and update the clean current schema
deliberately. A legacy split database is not changed at startup; convert it only with the explicit
`dj-sim migrate-database` command after stopping its SQLite users. Reanalysis and classifier
retraining remain separate choices.

Use `python scripts\optimize_database.py --db .\data\library.sqlite` only for a local database you
control. It backs up and checks integrity before maintenance. The browser supports scan, Refresh
Tags, relocation preview, and report-first helper jobs; database optimization remains an explicit
script workflow.

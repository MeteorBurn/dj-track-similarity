# Maintain a v7 library safely

> Audience: Users keeping local music state healthy.
> Goal: Maintain the v7 bundle without changing source audio.
> Type: workflow

1. Scan after adding files. Scan updates Core tracks and tags without writing audio.
2. Keep Core and mandatory `*.artifacts.sqlite` together. They are bound by `catalog_uuid`.
3. Treat `*.evaluation.sqlite` as optional evaluation state.
4. Use relocation preview before apply. Apply changes stored `tracks.file_path` only; it never moves,
   copies, deletes, or retags audio.
5. Run Audio Doctor and Audio Dedup in report mode before their confirmation-gated apply modes.

For changed SONARA identity, do not attempt a v5/v6 migration or mix releases. Run the ordered,
crash-resumable `prepare-sonara-release` workflow with backups, then reanalyze and rebuild every
SONARA-dependent classifier. It is not a distributed atomic transaction.

Use `python scripts\optimize_database.py --db .\data\library.sqlite` only for a local bundle you
control. It validates and backs up Core + Artifacts before maintenance. The frontend v7 port is
deferred, so use CLI/API workflows rather than current browser controls.

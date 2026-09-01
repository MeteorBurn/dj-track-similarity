# Maintain a library safely

A routine you can repeat without putting your audio or your database at risk. Control names are
given in English, and [UI language](../help/ui-language.md) carries the on-screen string for each
one.

## In the browser

Panel 1, database and analysis, carries every maintenance action the browser has:

| Action | Control | What it does |
| --- | --- | --- |
| Add new files | **Load tracks into the database** | opens the import dialog and scans a folder |
| Reread tags | **Refresh tags** | rereads Mutagen tags for existing tracks, leaving paths and analysis rows alone |
| Check the database | **Validate the database** | runs a read-only validation job and reports checked, warning, and error counts |
| Review duplicates | **Find and review duplicates** | opens the report-first Audio Dedup reviewer |
| Empty the catalog | **Clear the database** | deletes every SQLite row after a confirmation, leaving audio files on disk |

**Validate the database** opens the file read-only and streams its findings into the log. Only one
validation job runs at a time. Run it after a crash or a manual file move, and before a backup.

Per-family analysis resets live on the model rows in the same panel, and classifier score resets
live in the [CLASS tab](../user-guide/class-tab.md).

## Routine

1. Scan after adding files. Scan updates library tracks and tags without writing audio.
2. Run **Refresh tags** after editing tags outside the app. Scan skips tag decoding when a file's
   size and modification time are unchanged, so a tag-only edit is invisible to it.
3. Run **Validate the database** periodically, or
   `dj-sim validate-database --db .\data\library.sqlite` from the CLI. The CLI form exits with code
   2 when it finds errors, which makes it usable in a script.
4. Keep `library.sqlite` backed up. Include the optional `*.evaluation.sqlite` when it exists.
5. Run Audio Dedup in report mode first, then review copy by copy in the browser dialog. Deletions
   can go to the recycle bin.
6. Run Audio Doctor in its default report mode before considering `--apply`.

## Relocation is a CLI workflow

When the library moves to another drive or folder, `dj-sim relocate-library OLD NEW` previews the
rewrite. Add `--apply` to commit it. It changes stored SQLite paths only and never moves, copies,
deletes, or retags audio. There is no relocation surface in the browser.

## Database changes and migrations

When a database structure changes, keep a verified backup and update the clean current schema
deliberately. A legacy split database is not changed at startup. Convert it only with the explicit
`dj-sim migrate-database` command after stopping its SQLite users:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'
```

It creates a timestamped backup and verifies the staged one-file database. It starts no analysis.
Reanalysis and classifier retraining remain separate choices. See
[Reanalyze SONARA data](./reanalyze-sonara-split-storage.md).

## Database optimization

Optimization stays an explicit script workflow with no browser button:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
python scripts\optimize_database.py --db tools\rhythm-lab\database\rhythm_lab.sqlite
```

Use it only for a local database you control. It backs up the file and checks integrity before
running maintenance. See [Optimize database](../tools-and-scripts/optimize-database.md).

# Optimize a SQLite database

SQLite maintenance that takes a verified backup before it touches anything.

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

`--db` is the only argument, and it is required.

## The run, in order

1. Detects the database kind. A file carrying a valid `library` identity row is a `library`.
   Anything else is a generic `sqlite` file.
2. Builds the file set. A library is maintained together with its adjacent `*.evaluation.sqlite`
   sidecar when that file exists. A generic file is maintained alone.
3. Runs `PRAGMA integrity_check` on every file. A failure here stops the run before any write.
4. Backs up every file to `<name>.bak-<timestamp>` beside the original, through the SQLite backup
   API rather than a file copy. A name collision gets a numeric suffix.
5. Runs the maintenance statements on each file: `PRAGMA journal_mode = WAL`,
   `PRAGMA synchronous = NORMAL`, `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and
   `PRAGMA wal_checkpoint(TRUNCATE)`. The busy timeout is 30 seconds.
6. Runs `PRAGMA integrity_check` again. A failure here raises rather than reporting success.

The script imposes no fixed table, column, or index list, so a future library addition does not make
optimization fail.

## Printed summary

Six summary lines, then two lines per maintained file:

```text
database=<the path you passed>
database_kind=library
integrity_before=ok
integrity_after=ok
size_before=<bytes>
size_after=<bytes>
library.database=<library path>
library.backup=<library backup path>
evaluation.database=<sidecar path>
evaluation.backup=<sidecar backup path>
```

`database_kind` is `library` or `sqlite`. The `integrity_before` and `integrity_after` values are
`ok` only when every file in the set passed. The two size values are the sum across the set, in
bytes, so a library with a sidecar reports the combined total. The per-file lines use the role name
as a prefix: `library`, `evaluation`, or `sqlite` for a generic file.

## Maintaining the Rhythm Lab database

The Rhythm Lab labels database is a generic SQLite file to this script, so it reports
`database_kind=sqlite` and one `sqlite.database` and `sqlite.backup` pair.

```powershell
python scripts\optimize_database.py --db tools\rhythm-lab\database\rhythm_lab.sqlite
```

## Before the run

Stop the main app when practical, because `VACUUM` rewrites the whole file. Keep the optional
Evaluation sidecar with the library backup when it exists, since the two belong together. Neither
the maintenance nor the backup changes source audio files.

The backups stay on disk. Delete them yourself once you are satisfied with the result.

## Related pages

- [Scripts](./scripts.md)
- [Maintain library](../workflows/maintain-library.md)

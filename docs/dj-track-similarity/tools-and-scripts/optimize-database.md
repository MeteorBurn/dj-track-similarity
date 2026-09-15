# Optimize a SQLite database

SQLite maintenance that takes a verified backup before it touches anything.

```powershell
uv run --no-sync dj-sim optimize-database --db .\database\library.sqlite
```

`--db` is required. Add `--dry-run` to inspect the database and report free space
without writing anything.

## The run, in order

1. Detects the database kind. A file carrying a valid `library` identity row is a `library`.
   Anything else is a generic `sqlite` file.
2. Builds the file set. A library is maintained together with its adjacent `*.evaluation.sqlite`
   sidecar when that file exists. A generic file is maintained alone.
3. Runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on every file. A failure here
   stops the run before any write.
4. Checks free space on the database drive for the backup, the `VACUUM` temporary copy, and WAL
   growth. Refuses to start if there is not enough.
5. Backs up every file to `<name>.bak-<timestamp>` beside the original, through the SQLite backup
   API rather than a file copy, then verifies the copy. A name collision gets a numeric suffix.
6. Runs the maintenance statements on each file: merges FTS5 index segments, `VACUUM`, `ANALYZE`,
   and, for a WAL-mode file, `PRAGMA wal_checkpoint(TRUNCATE)`. The run keeps whatever journal mode
   it found; it does not set `journal_mode` or `synchronous`.
7. Runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check` again on each file. A failure here
   raises rather than reporting success, and that file's backup is kept as the rollback point. Once
   a file verifies clean, its backup is removed.

The tool imposes no fixed table, column, or index list, so a future library addition does not make
optimization fail.

## Printed summary

`--dry-run` prints the inspection and stops before any write:

```text
database_kind=<library or sqlite>
size=<bytes>
compacted_estimate=<bytes>
free_bytes=<bytes, or unknown>
required_free_bytes=<bytes>
free_space_ok=<True or False>
```

A real run prints one line per step (backing up, running maintenance, verifying), then a summary:

```text
database_kind=<library or sqlite>
size_before=<bytes>
size_after=<bytes>
integrity_before=ok
integrity_after=ok
library: size <before>-><after> journal=wal backup=removed (verified)
```

The `integrity_before`/`integrity_after` values are `ok` only when every file in the set passed.
The size values are the sum across the set, so a library with a sidecar reports the combined total.
Each per-file line is prefixed with its role (`library`, `evaluation`, or `sqlite` for a generic
file); `backup=` names the kept backup path instead of `removed (verified)` when that file's
post-optimization check failed.

## Before the run

Stop the main app when practical, because `VACUUM` rewrites the whole file. Keep the optional
Evaluation sidecar with the library backup when it exists, since the two belong together. Neither
the maintenance nor the backup changes source audio files.

The backup this run makes is temporary, not a retained copy: it exists only to protect the file
while `VACUUM` rewrites it, and is removed as soon as the file verifies again afterward. It is kept
only when that final check fails, so there is something to restore from.

## Related pages

- [Scripts](./scripts.md)
- [Maintain library](../workflows/maintain-library.md)

# Database Optimization Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\optimize_database.py --help
```

Optimizes a SQLite database that already matches the current schema contract. It
validates the schema, creates a backup, vacuums, analyzes, and verifies
integrity. It does not migrate, repair, or adapt databases from older schemas.

Use this script after large scan, reset, clear, relocation, or analysis churn if
the SQLite file has grown or you want a fresh integrity check. It is not part of
normal daily use and should not be used to fix schema-version problems.

Usage:

```text
python scripts\optimize_database.py --db DB
```

Example:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

This script writes to the database and creates a backup next to it. If the
database schema is not current, the script prints an error and stops before
creating a backup or modifying the database.

There is only one operating mode and no dry-run: every successful run validates
the schema, makes a backup, and optimizes the file in place.

## How It Works

1. Require the `--db` file to exist.
2. Run `PRAGMA integrity_check`; abort if the result is not `ok`.
3. Validate the current schema contract (`user_version = 2`, the expected
   tables `embeddings`, `library_settings`, `track_classifier_scores`,
   `track_likes`, and `tracks`, plus their columns, indexes, triggers, and
   foreign keys). Any mismatch aborts before the backup.
4. Create an online SQLite backup named `<db-name>.bak-<YYYYMMDD-HHMMSS>` next
   to the database (a numeric suffix is added if that name already exists).
5. Set WAL journaling, then run `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and a
   truncating WAL checkpoint.
6. Run `PRAGMA integrity_check` again; abort if the result is not `ok`.

## Output

On success the script prints a short summary to standard output:

```text
database=<resolved database path>
backup=<backup file path>
integrity_before=ok
integrity_after=ok
size_before=<bytes>
size_after=<bytes>
user_version=2
```

The only file the script writes besides the optimized database is the backup
`<db-name>.bak-<timestamp>`. There is no JSON, XLSX, or log report.

> Warning: this script is for current-schema databases only. It refuses to run
> on older or unexpected schemas instead of migrating them, and it does not ask
> for confirmation before optimizing.

Close the running app before optimizing the same database so the backup,
vacuum, and integrity check operate on a quiet file.

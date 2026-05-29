# Database Optimization Script

Run this script with the project Python environment when possible:

```powershell
.\.venv\Scripts\python.exe scripts\optimize_database.py --help
```

Optimizes a supported project SQLite database. The script recognizes the main
library database and the Rhythm Lab label database by their marker tables,
creates a backup, vacuums, analyzes, and verifies integrity. It does not
migrate, repair, or adapt database schemas.

Use this script after large scan, reset, clear, relocation, analysis, labeling,
or prediction churn if the SQLite file has grown or you want a fresh integrity
check. It is not part of normal daily use and should not be used to fix schema
or data problems.

Usage:

```text
python scripts\optimize_database.py --db DB
```

Example:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
python scripts\optimize_database.py --db tools\rhythm-lab\data\rhythm_lab.sqlite
```

This script writes to the database and creates a backup next to it. If the
database is not recognized as either the main library database or Rhythm Lab
database, the script prints an error and stops before creating a backup or
modifying the database.

There is only one operating mode and no dry-run: every successful run validates
basic support markers and integrity, makes a backup, and optimizes the file in
place.

## How It Works

1. Require the `--db` file to exist.
2. Run `PRAGMA integrity_check`; abort if the result is not `ok`.
3. Detect a supported database kind from marker tables:
   - main library: `tracks` and `embeddings`
   - Rhythm Lab: `classifier_profiles`, `classifier_labels`,
     `classifier_predictions`, and `classifier_training_checkpoints`
   Unknown SQLite files abort before the backup.
4. Create an online SQLite backup named `<db-name>.bak-<YYYYMMDD-HHMMSS>` next
   to the database (a numeric suffix is added if that name already exists).
5. Set WAL journaling, then run `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and a
   truncating WAL checkpoint.
6. Run `PRAGMA integrity_check` again; abort if the result is not `ok`.

## Output

On success the script prints a short summary to standard output:

```text
database=<resolved database path>
database_kind=<library|rhythm_lab>
backup=<backup file path>
integrity_before=ok
integrity_after=ok
size_before=<bytes>
size_after=<bytes>
```

The only file the script writes besides the optimized database is the backup
`<db-name>.bak-<timestamp>`. There is no JSON, XLSX, or log report.

> Warning: this script is for recognized project databases only. It refuses to
> run on unrelated SQLite files, does not migrate schemas, and does not ask for
> confirmation before optimizing.

Close the running app or Rhythm Lab before optimizing the same database so the
backup, vacuum, and integrity check operate on a quiet file.

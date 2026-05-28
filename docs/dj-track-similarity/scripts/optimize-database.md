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

Close the running app before optimizing the same database so the backup,
vacuum, and integrity check operate on a quiet file.

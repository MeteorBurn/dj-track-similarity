# Optimize database

Audience: power users and maintainers  
Goal: compact a supported SQLite database with a backup and integrity checks  
Type: how-to/reference

`scripts/optimize_database.py` supports project library databases and Rhythm
Lab databases. It refuses unknown SQLite files.

## Run

Activate the project environment once:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

The script:

1. checks the file exists;
2. runs `PRAGMA integrity_check`;
3. detects a supported database kind;
4. creates a timestamped backup next to the database;
5. runs `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and WAL checkpoint truncate;
6. runs `PRAGMA integrity_check` again;
7. prints the backup path and before/after sizes.

## Safety notes

Do not run this while another app instance is actively writing to the same
database. For real library state, prefer closing the UI/server first or working
on a copy.

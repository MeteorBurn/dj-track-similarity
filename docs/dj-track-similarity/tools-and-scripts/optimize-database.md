# Optimize a SQLite database

> Audience: Users maintaining local SQLite state.
> Goal: Run the maintenance script with backup and integrity checks.
> Type: guide

The optimization script supports the main library database and the Rhythm Lab labels database. It refuses unknown SQLite layouts.

## Command

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Behavior

The script:

1. resolves the database path,
2. checks that the file exists,
3. runs `PRAGMA integrity_check`,
4. detects a supported database kind,
5. creates a SQLite backup beside the database,
6. runs WAL, `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and WAL checkpoint maintenance,
7. runs `PRAGMA integrity_check` again,
8. prints database kind, backup path, integrity results, and size before/after.

Backups are named like:

```text
library.sqlite.bak-YYYYMMDD-HHMMSS
```

## Safety

Run it only on local databases you control. Stop the main app first when possible so another process is not writing during maintenance.

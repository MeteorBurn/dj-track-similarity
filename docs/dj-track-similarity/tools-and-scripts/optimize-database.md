# Optimize a SQLite database

> Audience: Users maintaining local SQLite state.
> Goal: Run the maintenance script with backup and integrity checks.
> Type: guide

The optimization script supports a current three-file library catalog and the standalone Rhythm Lab labels database. It refuses unknown or removed single-file library layouts.

## Command

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Behavior

The script:

1. resolves the database path,
2. checks that the file exists,
3. detects a supported database kind,
4. for a library, verifies the matching catalog ID and schemas of Core, Timeline, and Representations,
5. runs `PRAGMA integrity_check` on every selected file,
6. creates a SQLite backup beside every selected file,
7. runs WAL, `VACUUM`, `ANALYZE`, `PRAGMA optimize`, and WAL checkpoint maintenance on each file,
8. runs `PRAGMA integrity_check` again,
9. prints the database kind, every database/backup path, integrity results, and total size before/after.

Backups are named like:

```text
library.sqlite.bak-YYYYMMDD-HHMMSS
library.timeline.sqlite.bak-YYYYMMDD-HHMMSS
library.representations.sqlite.bak-YYYYMMDD-HHMMSS
```

## Safety

Run it only on local databases you control. Stop the main app first when possible so another process is not writing during maintenance.

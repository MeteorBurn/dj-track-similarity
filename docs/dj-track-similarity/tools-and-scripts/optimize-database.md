# Optimize a SQLite database

> Audience: Users maintaining a large project or Rhythm Lab database.
> Goal: Run optimization with a backup and integrity checks.
> Type: how-to

## Command

```powershell
python scripts\optimize_database.py --db <library-db>
```

## Behavior

The script checks integrity, creates a SQLite backup, runs `VACUUM`, `ANALYZE`, `PRAGMA optimize`, checkpoints WAL, and checks integrity again.

## Safety

Do not run it while another process is actively writing the same database.

# Optimize a SQLite database

> Audience: Users maintaining local SQLite state.
> Goal: Run maintenance with backups and integrity checks.
> Type: guide

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

For a v7 library, the script works with Core and the mandatory adjacent
`*.artifacts.sqlite` database. It validates their schemas and shared `catalog_uuid`, checks integrity,
creates verified backups, and then runs SQLite maintenance on each selected file. It reports the
paths, backup paths, integrity results, and size before/after.

`*.evaluation.sqlite` is optional evaluation state and is included only when present and selected by
the script's current policy. The script does not accept a v5/v6 layout, a `*.timeline.sqlite`, or a
`*.representations.sqlite` substitute.

Stop the main app when practical. Keep Core and Artifacts together for backup and recovery; neither
maintenance nor backup changes source audio files.

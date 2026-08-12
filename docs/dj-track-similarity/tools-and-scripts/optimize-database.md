# Optimize a SQLite database

> Audience: Users maintaining local SQLite state.
> Goal: Run maintenance with backups and integrity checks.
> Type: guide

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

For a library database, the script checks integrity, creates a verified backup, and then runs SQLite
maintenance. When an adjacent `*.evaluation.sqlite` file exists, it backs up and maintains that file
too. It reports paths, backup paths, integrity results, and size before/after. It does not impose a
fixed table or column list, so a future library addition does not make optimization fail.

`*.evaluation.sqlite` is optional evaluation state and is included only when present. The script can
also maintain another SQLite file, such as the Rhythm Lab labels database.

Stop the main app when practical. Keep the optional Evaluation sidecar with the library backup when
it exists. Neither maintenance nor backup changes source audio files.

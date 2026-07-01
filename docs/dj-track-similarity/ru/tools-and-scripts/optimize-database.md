# Optimize Database

> Audience: Пользователи этой страницы.
> Type: how-to

Run `python scripts\optimize_database.py --db <library-db>`. The script checks integrity, creates backup, runs `VACUUM`, `ANALYZE`, `PRAGMA optimize`, checkpoints WAL and checks integrity again.

# Optimize database

Аудитория: power users и maintainers  
Цель: compact supported SQLite database с backup и integrity checks  
Тип: how-to/reference

`scripts/optimize_database.py` supports project library databases и Rhythm Lab
databases. Unknown SQLite files rejected.

## Run

Активируйте project environment один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

Script:

1. checks file exists;
2. runs `PRAGMA integrity_check`;
3. detects supported database kind;
4. creates timestamped backup next to database;
5. runs `VACUUM`, `ANALYZE`, `PRAGMA optimize` and WAL checkpoint truncate;
6. runs `PRAGMA integrity_check` again;
7. prints backup path and before/after sizes.

## Safety notes

Не запускайте это, пока другой app instance активно пишет в ту же database. Для
real library state лучше закрыть UI/server или работать on a copy.

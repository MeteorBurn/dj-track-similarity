# Скрипт оптимизации базы данных

По возможности запускайте этот script через project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\optimize_database.py --help
```

Оптимизирует SQLite database, которая уже соответствует текущему schema
contract. Он validates schema, создает backup, выполняет vacuum, analyze и
integrity verification. Он не мигрирует, не чинит и не адаптирует databases от
старых схем.

Используйте этот script после большого scan, reset, clear, relocation или
analysis churn, если SQLite file вырос или нужен fresh integrity check. Это не
часть normal daily use и не должно использоваться для исправления
schema-version problems.

Usage:

```text
python scripts\optimize_database.py --db DB
```

Example:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

Этот script writes to the database и создает backup рядом с ней. Если database
schema не current, script печатает error и останавливается перед созданием
backup или изменением database.

Закройте running app перед оптимизацией той же database, чтобы backup, vacuum и
integrity check работали по quiet file.


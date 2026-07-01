# Local-first safety model

> Audience: Пользователи и разработчики, которым важны границы записи.
> Goal: Понять, что пишет SQLite, отчёты, теги или удаляет файлы.
> Type: how-to

Основная модель простая: обычные сценарии приложения читают аудио и пишут состояние в SQLite. Только явно названные действия трогают исходные аудиофайлы или удаляют файлы.

## Read-only по умолчанию

Scan, Refresh Tags, analysis, search, preview, reset, clear, relocation preview и export не переписывают исходное аудио. Они обновляют базу, возвращают ответы API или создают M3U/CSV.

## Явные исключения

- Genre apply пишет стандартный genre tag из сохранённых MAEST labels.
- Audio Doctor `--apply` может переписать файлы, помеченные как `REPAIRABLE`, и по умолчанию создаёт full-file backups. Dry-run ничего не пишет.
- Audio Dedup apply/delete может удалить подтверждённые duplicate candidates после точного подтверждения.
- Relocation apply не двигает и не копирует аудио; он обновляет только сохранённые `tracks.path` значения после проверок missing files и conflicts.

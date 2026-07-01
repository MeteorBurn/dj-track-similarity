# Когда приложение может писать в аудиофайлы

> Audience: Пользователи, которые выбирают tag apply, repair или dedup actions.
> Goal: Отделить read-only сценарии от явных записей тегов и удалений.
> Type: how-to

По умолчанию приложение читает аудио и пишет только SQLite или отчёты. Scan, Refresh Tags, analysis, search, previews, export, reset, clear и relocation preview не переписывают исходные аудиофайлы.

## Genre tag apply

`/api/tags/genres/apply` и genre tag jobs — явный путь записи жанров. Они берут сохранённые MAEST genres и перезаписывают только стандартное поле жанра, сохраняя title, artist, album, BPM, key и другие обычные теги.

## Поля тегов

MP3/WAV/AIFF ID3 используют `TCON`; FLAC/Vorbis-style tags используют `GENRE`; MP4/M4A/ALAC используют `©gen`. WAV пишется через Mutagen WAVE/ID3 и проверяется обратным чтением `TCON`.

## Другие явные исключения

Audio repair `--apply` может переписывать только файлы, которые скрипт определил как `REPAIRABLE`; dry-run не пишет аудио. Audio Dedup apply/delete может удалить подтверждённые дубли только после точного подтверждения.

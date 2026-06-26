# Tags and audio writes

Аудитория: осторожные пользователи и power users  
Цель: понять явное исключение для tag writing  
Тип: how-to

Большинство app workflows read-only по отношению к source audio. Genre tag
writing - намеренное исключение: оно может записать stored MAEST genre labels в
standard audio genre tags.

## Что может писать tags

Явный app path:

```text
POST /api/tags/genres/apply
```

или соответствующий UI job.

Он пишет только standard genre field из stored MAEST labels. Title, artist,
album, BPM, key и другие normal tags должны сохраняться.

## Formats

Tag-writing code использует standard fields:

- `TCON` for MP3/WAV/AIFF ID3;
- `GENRE` for FLAC/Vorbis-style tags;
- `©gen` for MP4/M4A/ALAC.

## Batch behavior

Failed writes должны fail только этот track и позволить batch продолжиться. Для
WAV app использует Mutagen WAVE/ID3 handling и read back `TCON`; custom RIFF
repair logic не добавляется в tag-writing path.

## Перед записью tags

Убедитесь, что:

- MAEST labels есть и их стоит записывать;
- у вас есть backups, если файлы важны;
- вы понимаете, что это не search, analysis, preview или export.

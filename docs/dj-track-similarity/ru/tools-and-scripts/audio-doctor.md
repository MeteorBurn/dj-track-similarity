# Audio Doctor

> Audience: Пользователи, которые проверяют broken metadata или WAV/AIFF container issues.
> Type: how-to

Default dry-run не пишет и не копирует аудио:

```powershell
.\.venv\Scripts\python.exe tools\audio-doctor\audio_doctor_cli.py --folder <music-folder>
```

`--db` открывает SQLite read-only и читает `tracks.path`; `--db-root` плюс `--file-root` могут remap stored paths. Reports пишутся в `tools\audio-doctor\data\reports`, state — в `tools\audio-doctor\data\state`.

`--apply` может переписывать только repairable WAV/AIFF cases. UI/API apply требует точное подтверждение `APPLY REPAIR` и должен запускаться после dry-run state.

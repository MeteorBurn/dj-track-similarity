# Разработка и проверка

Эта страница покрывает локальную настройку и ожидания по verification.

## Настройка разработки

Установить development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Установить поддержку Sonara:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Установить ML dependencies:

```powershell
python -m pip install -e ".[ml,dev]"
```

Установить полный локальный lab dependency set, включая Rhythm Lab training:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Запустить backend tests:

```powershell
pytest
```

Собрать frontend:

```powershell
cd frontend
npm run build
```

Собрать статическую HTML-документацию:

```powershell
cd docs\dj-track-similarity
npm install
npm run build
```

HTML документации генерируется в `docs/dj-track-similarity/site/`. После
запуска backend основной UI открывает ее по кнопке документации в top bar на
`/docs/`.

Запустить frontend development server:

```powershell
cd frontend
npm run dev
```

Для Python-команд в этом репозитории предпочитайте project virtual environment,
если он доступен:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Рекомендации по проверке

Используйте focused verification для code changes и script changes.
Documentation-only changes не требуют full test suite, но должны проверяться на
устаревшие local paths и точность команд.

Полезные проверки:

```powershell
dj-sim --help
dj-sim analyze --help
python scripts\audio_repair\repair_audio_metadata.py --help
python scripts\audio_dedup\audio_dedup.py --help
```


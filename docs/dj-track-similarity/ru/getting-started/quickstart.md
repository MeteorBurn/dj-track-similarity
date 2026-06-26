# Quickstart: открыть первую локальную библиотеку

Аудитория: новые пользователи  
Цель: установить приложение, просканировать аудио и открыть browser UI  
Тип: tutorial

Этот tutorial доводит до первого полезного результата: web UI показывает треки
из локальной папки. Сначала используется базовая установка. Model analysis
можно добавить позже.

## Требования

- Python 3.10 или новее.
- FFmpeg в `PATH` или `DJ_TRACK_SIMILARITY_FFMPEG`, указывающий на
  `ffmpeg.exe`.
- Небольшая тестовая папка с аудиофайлами, которую можно безопасно сканировать.

::: warning Safety note
Сначала используйте маленькую папку. Scan читает теги и пишет строки в SQLite.
Он не переписывает аудиофайлы, но база может содержать приватные названия
треков и пути.
:::

## 1. Создать и активировать окружение

Из корня проекта:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Ожидаемый результат:

```text
В prompt видно активное окружение, команда dj-sim доступна.
```

Все следующие команды предполагают, что окружение все еще активно.

## 2. Проверить CLI

```powershell
dj-sim --help
dj-sim doctor
```

Ожидаемый результат:

```text
dj-sim показывает команды scan, analyze, text-search, serve и другие.
doctor сообщает состояние Python, FFmpeg, PyTorch и device.
```

## 3. Просканировать маленькую папку

Замените `<music-library>` на путь к тестовой папке.

```powershell
New-Item -ItemType Directory -Force .\data
dj-sim scan <music-library> --db .\data\library.sqlite
```

Ожидаемый результат:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

Команда создает `.\data\library.sqlite`. База хранит пути файлов, metadata из
тегов и позже состояние анализа.

## 4. Запустить локальный server

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Откройте:

```text
http://127.0.0.1:8765/
```

Ожидаемый результат:

```text
Browser показывает DJ Track Similarity UI и просканированные треки.
```

## 5. Следующий шаг

Для первого explainable search можно запустить маленький SONARA pass:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Перед тяжелыми MAEST, MERT, CLAP или classifier jobs прочитайте
[First analysis](first-analysis.md).

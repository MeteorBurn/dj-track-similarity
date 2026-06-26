# First library

Аудитория: новые пользователи  
Цель: создать первую SQLite library database из локальной папки  
Тип: tutorial

Scan читает supported audio files и их metadata. Он пишет SQLite rows, но не
переписывает source audio.

## 1. Активировать окружение

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

## 2. Создать папку для локальной базы

```powershell
New-Item -ItemType Directory -Force .\data
```

## 3. Просканировать папку

```powershell
dj-sim scan <music-library> --db .\data\library.sqlite
```

Используйте маленькую тестовую папку, пока проверяете setup.

## Что попадает в базу

База хранит path, artist/title/album, BPM/key, duration, energy, metadata JSON
и later analysis flags. Сами аудиофайлы остаются на месте.

## Что делать после scan

Запустите server:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Затем откройте UI и проверьте, что tracks появились в library table.

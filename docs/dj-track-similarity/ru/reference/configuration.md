# Справочник конфигурации

> Для кого: Пользователи, настраивающие пути, порты, сборки и каталоги создаваемых данных.
> Задача: Перечислить практические настройки текущего репозитория.
> Тип: Справочник

## Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `DJ_TRACK_SIMILARITY_FFMPEG` | Полный путь к ffmpeg, если команда `ffmpeg` недоступна через `PATH` |

Если переменная задана, но файл по пути отсутствует, запуск сервера завершается с понятной ошибкой.

## Пути по умолчанию

| Состояние | Путь по умолчанию или обычный путь |
| --- | --- |
| База CLI по умолчанию | `dj-track-similarity.sqlite`, если `--db` не указан |
| Пример базы проекта | `.\data\library.sqlite` |
| Локальная ручная база Windows | `C:\db\abstracted.sqlite` |
| Журналы выполнения | `logs/` |
| Отчёты, состояние и резервные копии Audio Doctor | `tools/audio-doctor/data/` |
| Отчёты Audio Dedup | `tools/audio-dedup/data/reports/` |
| Метки Rhythm Lab | `tools/rhythm-lab/data/rhythm_lab.sqlite` |
| Артефакты Rhythm Lab | `tools/rhythm-lab/artifacts/` |
| Опубликованные классификаторы | `models/classifiers/<artifact-prefix>/` |
| Постоянные индексы ANN | `.dj-track-similarity-indexes/` рядом с выбранной базой по умолчанию |

Создаваемые локальные артефакты исключены из Git, если политика явно не требует обратного.

Активный журнал основного процесса — `logs/dj-track-similarity.log`. Если при запуске его первая
записанная дата старше текущей, журналы проекта архивируются с суффиксом той даты, а приложение
открывает новый активный файл. Сервер, работающий после полуночи, продолжает писать туда же до
перезапуска.

## Порты

| Сервис | По умолчанию |
| --- | ---: |
| Основное приложение и интерфейс | `8765` |
| Сервер разработки Vite | `5173` |
| Rhythm Lab | `8777` |

До запуска ещё одного процесса проверьте, не занят ли фиксированный порт.

## Команды сервера

Только локально:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Локальная сеть:

```powershell
dj-sim serve --host 0.0.0.0 --port 8765 --db .\data\library.sqlite
```

Скрипт Windows:

```powershell
run_server.cmd local --db .\data\library.sqlite
run_server.cmd lan --db .\data\library.sqlite
```

## Команды сборки

Интерфейс:

```powershell
cd frontend
npm install
npm run build
```

Документация:

```powershell
cd docs\dj-track-similarity
npm install --no-package-lock
npm run vale:sync
npm run check
```

Маршрут `/docs/` показывает понятное сообщение «Documentation is not built», если каталог
`docs/dj-track-similarity/site/` отсутствует.

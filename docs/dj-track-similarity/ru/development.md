# Разработка и проверка

Эта страница описывает локальную настройку и ожидания по проверке.

## Настройка разработки

Установите зависимости для разработки:

```powershell
python -m pip install -e ".[dev]"
```

Установите поддержку Sonara:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Установите ML-зависимости:

```powershell
python -m pip install -e ".[ml,dev]"
```

Установите полный локальный набор зависимостей лаборатории, включая обучение
Rhythm Lab:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Запустите тесты backend:

```powershell
pytest
```

Соберите frontend:

```powershell
cd frontend
npm run build
```

Соберите статическую HTML-документацию:

```powershell
cd docs\dj-track-similarity
npm install
npm run build
```

HTML-документация генерируется в `docs/dj-track-similarity/site/`. После запуска
backend основной UI открывает её по кнопке документации в верхней панели по
адресу `/docs/`.

Запустите сервер разработки frontend:

```powershell
cd frontend
npm run dev
```

Для Python-команд в этом репозитории предпочитайте виртуальное окружение проекта,
если оно доступно:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Рекомендации по проверке

Используйте фокусную проверку для изменений кода и изменений скриптов. Изменения
только в документации не требуют полного набора тестов, но их следует проверять
на устаревшие локальные пути и точность команд.

Полезные проверки:

```powershell
dj-sim --help
dj-sim analyze --help
python scripts\audio_repair\repair_audio_metadata.py --help
python scripts\audio_dedup\audio_dedup.py --help
```

# Карта архитектуры

> Для кого: Разработчики, которые ориентируются в репозитории.
> Задача: Увидеть основные компоненты и поток данных до чтения каждого модуля.
> Тип: Объяснение

## Карта

```mermaid
flowchart LR
    CLI[Typer CLI] --> DB[LibraryDatabase]
    API[Бэкенд FastAPI] --> DB
    UI[Интерфейс React] --> API
    Audio[Аудиофайлы] --> Sonara[SONARA / Symphonia]
    Audio --> FFmpeg[FFmpeg: общее декодирование ML]
    Sonara --> Queue[Последовательная очередь анализа]
    FFmpeg --> Queue
    Queue --> DB
    DB --> Classifiers[Этап классификаторов, готовых по манифесту]
    Classifiers --> Queue
    DB --> Search[Поиск и построители SET]
    Lab[Rhythm Lab] --> DB
```

## Карта кода

- `database.py`, `db_schema.py`, `db_storage.py` и `db_analysis*.py` описывают Core и подключённые дополнительные схемы. Эти модули также сохраняют результаты анализа, выполняют запросы с проверкой сигнатур, управляют кэшами, сбросом и очисткой.
- `scanner.py`: поиск поддерживаемого аудио и чтение метаданных Mutagen.
- `analysis_queue.py`: один последовательный обработчик для ручных и конвейерных этапов анализа.
- `analysis_jobs.py` и `sonara_features.py`: отдельные задачи ML, нативный пакетный сбор SONARA и замеры длительности этапов. Пакет SONARA сохраняется одной транзакцией с точкой сохранения для каждого трека.
- `analysis_pipeline.py`: фиксированное управление родительской задачей и дочерними этапами SONARA, ML, CLASSIFIERS.
- `sonara_contract.py`: версия, схема, профиль, сигнатура и совместимость анализа.
- `tempo_resolution.py` и `track_resolution.py`: определение BPM и Camelot/тональности с учётом достоверности.
- `search.py`, `sonara_similarity*.py`, `set_builder.py` и `transition_diagnostics.py`: поиск, порядок SET и риск перехода.
- `classifier_manifest.py`, `classifier_scoring.py` и `classifier_jobs.py`: проверка опубликованных артефактов, готовность по манифесту, общий прогресс и расчёт оценок только по базе.
- `api_routes_*.py`: группы маршрутов FastAPI.
- `frontend/src/`: клиент API и панели интерфейса.

Выбранный `library.sqlite` — база Core. Одна индексированная таблица `embeddings` хранит эмбеддинги
MAEST, MERT, MuQ и CLAP для поиска и ранжирования. Полные временные массивы SONARA находятся в
`library.timeline.sqlite`, а необязательные представления SONARA — эмбеддинг и отпечаток — в
`library.representations.sqlite`. Каждое соединение подключает соответствующую пару и проверяет
общий идентификатор каталога. Часто используемые строки поиска содержат лёгкие поля SONARA и два списка имён;
поиск, SET и классификаторы никогда не загружают Timeline.

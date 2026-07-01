# Persistent ANN indexes

> Audience: Пользователи с большой проанализированной библиотекой, которым нужен более быстрый vector lookup.
> Goal: Собрать, проверить, benchmark и удалить optional sidecar indexes без изменения библиотеки.
> Type: how-to

Persistent ANN indexes — это generated sidecar files, построенные из сохраненных `mert`, `maest` или `clap` audio embeddings. Они необязательны: обычный vector search работает без них, а opt-in search paths возвращаются к exact search, если sidecar отсутствует, устарел или не поддерживается текущей средой.

Используйте их после того, как analysis уже выполнен и exact vector search начинает ощущаться медленным на большой локальной библиотеке. Не собирайте index до появления соответствующих embeddings.

## Что хранится

Команда index пишет generated files в index directory. По умолчанию эта директория находится рядом с выбранной SQLite database:

```text
<database-folder>/.dj-track-similarity-indexes/
```

Путь можно переопределить через `--index-dir <index-folder>`. Sidecar содержит vectors и track IDs, нужные для lookup. Он не копирует audio files и не пишет новые SQLite rows.

Default `.gitignore` исключает `.dj-track-similarity-indexes/`; custom index directories тоже держите вне Git.

## Optional backend

Базовый проект может использовать exact NumPy sidecar. Для HNSW indexes установите optional ANN dependency:

```powershell
python -m pip install -e ".[ann]"
```

`--backend auto` предпочитает `hnswlib`, если он установлен. Если `hnswlib` недоступен, auto mode возвращается к `exact-numpy` и печатает warning.

## Build и verify

Собирайте один adapter за раз:

```powershell
dj-sim index build --adapter clap --db <library-db>
dj-sim index verify --adapter clap --db <library-db>
```

Поддерживаемые adapters:

- `mert`
- `maest`
- `clap`

Полезные build options:

- `--backend auto|hnswlib|exact-numpy`
- `--index-dir <index-folder>`
- `--ef-construction <n>` для HNSW build quality и стоимости сборки
- `--m <n>` для HNSW graph connectivity
- `--ef-search <n>`, сохраняется в manifest для HNSW search

`index build` удаляет старые generated files для того же adapter в выбранной index directory перед записью нового sidecar.

## Benchmark recall

Benchmark сравнивает sidecar с exact vector search на deterministic seed embeddings:

```powershell
dj-sim index benchmark --adapter clap --recall-k 50 --threshold 0.97 --output .\reports\clap-index.json --db <library-db>
```

JSON report удобно использовать при настройке HNSW settings. Failed benchmark означает, что sidecar технически usable, но не прошел выбранный recall threshold.

## Использование в text search

CLAP text search имеет явный opt-in:

```powershell
dj-sim text-search "warm dub techno pads" --use-ann-index --db <library-db>
```

Добавьте `--index-dir <index-folder>`, если sidecar лежит не в default location.

Если sidecar отсутствует, устарел или не поддерживается, команда выводит warning и возвращается к exact search. Results остаются доступными, но поиск может быть медленнее.

## Когда rebuild

Запускайте `dj-sim index verify --adapter <adapter> --db <library-db>`, если results выглядят подозрительно или после maintenance. Rebuild нужен после:

- нового analysis для того же adapter;
- reset или clear embeddings;
- копирования или замены SQLite database;
- переноса sidecar на другую машину;
- намеренного изменения HNSW settings.

## Clear generated files

Удалить sidecar одного adapter:

```powershell
dj-sim index clear --adapter clap --db <library-db>
```

Удалить все owned generated sidecar files из выбранной index directory:

```powershell
dj-sim index clear --db <library-db>
```

`index clear` удаляет только generated index files в выбранной index directory. Он не удаляет audio files и не удаляет SQLite data.

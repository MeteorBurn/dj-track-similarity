# Мост KGLite

> Для кого: Пользователи, исследующие связи библиотеки локальными графовыми запросами.
> Задача: Создать одноразовый граф только для чтения из выбранной библиотеки.
> Тип: Руководство

Мост KGLite переносит выбранные данные SQLite в локальный граф `.kgl`. Core и обязательная
боковая база Artifacts остаются источником истины. Мост открывает оба входа через SQLite
`mode=ro` и `PRAGMA query_only = ON`. Он не открывает аудиофайлы и не сохраняет исходные
векторы эмбеддингов.

KGLite является необязательной зависимостью инструмента и не входит в runtime приложения.

## Содержимое графа

Проекция содержит:

- узлы `Catalog` и `Projection` с привязкой каталога и детерминированным digest проекции;
- узлы `Track`, идентифицированные через `catalog_uuid` вместе с `track_uuid`;
- узлы `Artist` и `Genre` из точных значений тегов;
- одну понравившуюся `Collection` из таблицы Core `likes`, если она не пуста;
- направленные рёбра top-K `SIMILAR_MAEST`, `SIMILAR_MERT`, `SIMILAR_MUQ`,
  `SIMILAR_CLAP` и `SIMILAR_SONARA`.

Каждое ребро сходства сохраняет `source_family`, косинусный `score`, `rank` и оба значения
`content_generation`. Это сигналы ранжирования для
дальнейшего прослушивания, а не вероятности или объективная музыкальная истина.

## Проверка актуальности

Мост прекращает работу при несовместимой структуре Core или Artifacts, отсутствии обязательных
таблиц либо несовпадении `catalog_uuid`.

Эмбеддинг экспортируется только при совпадении следующих данных с текущим состоянием:

- `track_uuid` и `content_generation`;
- текущей размерности, кодировки `float32-le` и нормализации;
- конечных значений вектора и корректной нормализации L2, если она нужна источнику.

Строки устаревших поколений треков и структурно неверные векторы исключаются и учитываются в
отчёте сборки.

## Предварительный запуск

Всегда задавайте базу Core явно. Предварительный запуск проверяет оба входа, рассчитывает
полную проекцию и не записывает файл `.kgl`:

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --dry-run --format json
```

Путь Artifacts по умолчанию имеет вид `<db stem>.artifacts.sqlite`. Используйте
`--artifacts` только для выбранного комплекта с другим явно заданным путём.

## Сборка

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --top-k 10 --min-score 0.0 --format json
```

По умолчанию мост выбирает все активные источники эмбеддингов. Повторите
`--source`, чтобы потребовать определённый набор:

```powershell
python tools\kglite-bridge\kglite_bridge_cli.py `
  --db .\data\library.sqlite `
  --output tools\kglite-bridge\data\library.kgl `
  --source mert --source maest --source muq `
  --top-k 10 --format json
```

Результат сначала записывается в соседний staging-файл, повторно открывается и
проверяется по ожидаемому числу узлов и рёбер, а затем публикуется. Существующий
результат сохраняется, пока явно не задан `--overwrite`. Мост отклоняет выходной
путь, совпадающий с любым входом SQLite.

По умолчанию узлы треков содержат сохранённые пути к аудио. Перед передачей графа
другим используйте `--omit-paths`. Файл `.kgl` всё равно может раскрывать названия
треков, исполнителей, жанры, модели и связи сходства, поэтому считайте его личными
локальными данными.

## Локальная обёртка и запросы

Необязательная машинная обёртка хранит одноразовый граф вне репозитория:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-dry-run `
  --db '<core.sqlite>' --format json

& 'C:\Utils\tools\codingest-djts\djts.ps1' library-build `
  --db '<core.sqlite>' --top-k 10 --format json
```

Перед составлением Cypher опишите схему графа:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-describe `
  --connections --cypher
```

Затем запросите сходство MuQ:

```powershell
& 'C:\Utils\tools\codingest-djts\djts.ps1' library-query `
  'MATCH (a:Track)-[r:SIMILAR_MUQ]->(b:Track) RETURN a.title, b.title, r.score ORDER BY r.score DESC LIMIT 20' `
  --format json
```

Команда `library-mcp` запускает MCP-сервер только для чтения. `library-selftest`
может одновременно проверять тот же граф, потому что read-only серверы KGLite не
удерживают writer lease.

## Проверка

Тесты создают временные базы Core/Artifacts и фиктивные байты аудио. Они проверяют
экспорт только текущих данных, детерминированную идентичность проекции, настоящее
повторное открытие KGLite и количество узлов и рёбер:

```powershell
python -m pytest tools\kglite-bridge\tests\test_kglite_bridge.py --override-ini addopts=
```

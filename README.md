# dj-track-similarity

Локальная утилита для подбора похожих треков под монотонные seamless DJ-сеты.

## Запуск

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

Открой:

```text
http://127.0.0.1:8765/
```

В этом workspace также есть быстрый Windows-скрипт:

```powershell
scripts\run_server.cmd
```

## CLI

```powershell
dj-sim scan "D:\Music"
dj-sim analyze
dj-sim analyze --fake
dj-sim export 1 --format m3u --output-dir "D:\Exports"
dj-sim export 1 --format csv --output-dir "D:\Exports"
dj-sim tag-preview 1 2 3
dj-sim tag-apply 1 2 3
```

`analyze` использует `m-a-p/MERT-v1-95M` через PyTorch/Hugging Face и может скачать веса при первом запуске. `--fake` нужен только для smoke-тестов без ML.

В UI `Analyze limit` по умолчанию ограничивает первый прогон. Поставь `0`, только когда готов анализировать всю библиотеку.

## Safety

- Аудиофайлы не меняются при сканировании, анализе, поиске и экспорте.
- `tag-preview` ничего не пишет.
- `tag-apply` пишет только custom tags `DJ_SIM_*` и не перезаписывает стандартные BPM/key/mood.

## Search knobs

- `Similarity` задает минимальный raw cosine score.
- `Epsilon` оставляет только кандидатов в диапазоне `best_score - epsilon`.
- `Noise` добавляет детерминированную вариативность к ранжированию, но не меняет отображаемый raw score.
- `Lookback` добавляет последние N треков текущего сета в centroid-контекст поиска.

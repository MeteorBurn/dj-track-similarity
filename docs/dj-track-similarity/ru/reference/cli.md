# CLI reference

> Audience: Опытные пользователи, которым нужно быстро вспомнить форму команды.
> Goal: Показать текущие поддерживаемые команды без legacy command names.
> Type: how-to

## Основные команды

```powershell
dj-sim scan <music-folder> --db <library-db>
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db <library-db>
dj-sim analyze-classifier <classifier-key> --limit 25 --db <library-db>
dj-sim text-search "dark rolling techno" --limit 10 --db <library-db>
dj-sim relocate-library <old-root> <new-root> --db <library-db>
dj-sim relocate-library <old-root> <new-root> --apply --db <library-db>
dj-sim doctor
dj-sim serve --host 127.0.0.1 --port 8765 --db <library-db>
```

## Unified analysis options

- `--models`: comma-separated `sonara`, `maest`, `mert`, `clap`.
- `--device`: `auto`, `cpu` или `cuda`.
- `--top-k`: количество MAEST labels на трек, 1-10.
- `--track-batch-size`: сколько decoded tracks держать вместе, 1-64.
- `--inference-batch-size`: batch size для model forward pass, 1-128.
- `--diagnostics`: decoder fallback и batch timing diagnostics.
- Для всей библиотеки в CLI не указывайте `--limit`.

Текущий путь для аудиоанализа — единый `dj-sim analyze --models ...`.

# CLI reference

> Audience: Power users who already know the workflow.
> Goal: Look up current supported command shapes without legacy command names.
> Type: reference

## Core commands

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
- `--device`: `auto`, `cpu`, or `cuda`.
- `--top-k`: MAEST labels per track, 1-10.
- `--track-batch-size`: decoded tracks held together, 1-64.
- `--inference-batch-size`: model forward-pass batch size, 1-128.
- `--diagnostics`: decoder fallback and batch timing diagnostics.
- Omit `--limit` for the whole library in the CLI.

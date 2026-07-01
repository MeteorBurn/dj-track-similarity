# CLI reference

> Audience: Опытные пользователи, которым нужно быстро вспомнить форму команды.
> Goal: Показать текущие поддерживаемые команды без legacy command names.
> Type: reference

`dj-sim` — installed console entry point. Передавайте `--db <library-db>`, если не хотите использовать default `dj-track-similarity.sqlite` в текущей working directory.

## Core workflow commands

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

| Command | Purpose | Writes |
| --- | --- | --- |
| `scan` | Читает tags из music folder в SQLite. | Только SQLite |
| `analyze` | Запускает выбранные SONARA, MAEST, MERT или CLAP analysis families. | Только SQLite |
| `analyze-classifier` | Считает scores для одного promoted local classifier profile. | Только SQLite |
| `text-search` | Embeds CLAP text prompt и ищет по stored CLAP audio embeddings. | Нет |
| `relocate-library` | Preview или apply stored path remapping после перемещения библиотеки. | SQLite only with `--apply` |
| `doctor` | Печатает Python, Torch, CUDA и suggested install diagnostics. | Нет |
| `serve` | Запускает FastAPI/browser UI backend. | Runtime server only |

## Unified analysis options

```powershell
dj-sim analyze --models sonara,maest,mert,clap --device auto --top-k 5 --track-batch-size 4 --inference-batch-size 4 --db <library-db>
```

- `--models`: comma-separated `sonara`, `maest`, `mert`, `clap`.
- `--device`: `auto`, `cpu` или `cuda`.
- `--top-k`: количество MAEST labels на трек, 1-10.
- `--track-batch-size`: сколько decoded tracks держать вместе, 1-64.
- `--inference-batch-size`: batch size для model forward pass, 1-128.
- `--diagnostics`: пишет decoder fallback и batch timing diagnostics в file log.
- Для всей библиотеки в CLI не указывайте `--limit`. В UI `Analyze limit = 0` означает whole library.

## Text search options

```powershell
dj-sim text-search "warm dub techno pads" --limit 25 --min-similarity 0.35 --device auto --db <library-db>
dj-sim text-search "warm dub techno pads" --use-ann-index --index-dir <index-folder> --db <library-db>
```

CLAP text search требует stored CLAP audio embeddings. `--use-ann-index` — explicit opt-in к persistent CLAP sidecar; missing, stale или unsupported sidecars выводят warning и возвращаются к exact search.

## Persistent index commands

```powershell
dj-sim index build --adapter clap --db <library-db>
dj-sim index verify --adapter clap --db <library-db>
dj-sim index benchmark --adapter clap --recall-k 50 --threshold 0.97 --output .\reports\clap-index.json --db <library-db>
dj-sim index clear --adapter clap --db <library-db>
dj-sim index clear --db <library-db>
```

Supported adapters: `mert`, `maest`, `clap`. Common options: `--index-dir <index-folder>` и `--backend auto|hnswlib|exact-numpy`. HNSW tuning options: `--ef-construction`, `--m`, `--ef-search`. См. [Persistent ANN indexes](../tools-and-scripts/persistent-ann-indexes.md).

## Evaluation commands

Evaluation commands требуют current SQLite schema и предназначены для local diagnostics, calibration и manual feedback workflows.

| Command | Typical shape | Output or write |
| --- | --- | --- |
| `eval export-seed-sample` | `dj-sim eval export-seed-sample --count 50 --output <seeds.csv> --db <library-db>` | CSV |
| `eval export-candidates` | `dj-sim eval export-candidates --seed-track-id 123 --source mert --output <candidates.csv> --db <library-db>` | CSV плюс optional recorded sessions |
| `eval export-weighted-candidates` | `dj-sim eval export-weighted-candidates --profile <profile.json> --output <candidates.csv> --db <library-db>` | CSV плюс optional recorded sessions |
| `eval import-pair-feedback` | `dj-sim eval import-pair-feedback --input <pair-feedback.csv> --db <library-db>` | SQLite feedback rows |
| `eval import-transition-feedback` | `dj-sim eval import-transition-feedback --input <transition-feedback.csv> --db <library-db>` | SQLite feedback rows |
| `eval report` | `dj-sim eval report --output <report.json> --db <library-db>` | JSON |
| `eval run-ablation` | `dj-sim eval run-ablation --output <ablation.json> --db <library-db>` | JSON |
| `eval profile-sources` | `dj-sim eval profile-sources --output <sources.json> --profile-output <profile.json> --db <library-db>` | JSON profile diagnostics |
| `eval build-score-profile` | `dj-sim eval build-score-profile --source-profile-report <sources.json> --name <name> --output <profile.json>` | JSON score profile |
| `eval apply-score-profile` | `dj-sim eval apply-score-profile --profile <profile.json> --output <report.json> --db <library-db>` | JSON |
| `eval run-calibration` | `dj-sim eval run-calibration --output <calibration.json> --db <library-db>` | JSON; optional recorded summary через `--record` |
| `eval optimize-score-profile` | `dj-sim eval optimize-score-profile --output <optimizer.json> --db <library-db>` | JSON; optional promotion через `--promote` |
| `eval sweep-risk-penalty` | `dj-sim eval sweep-risk-penalty --profile <profile.json> --output <sweep.json> --db <library-db>` | JSON |

Используйте `--judged-only` на поддерживаемых report commands, когда нужны matched judged-label gates. Repeated options вроде `--k`, `--source`, `--seed-track-id` или `--weight` можно повторять, если это указано в command help.

## Classifier diagnostics

```powershell
dj-sim analyze-classifier live_instrumentation --limit 25 --db <library-db>
dj-sim classifier calibration-report --classifier live_instrumentation --output <report.json> --db <library-db>
dj-sim classifier suggest-labels --classifier live_instrumentation --mode uncertainty --limit 25 --output <suggestions.json> --db <library-db>
```

`analyze-classifier` пишет scores для одного promoted classifier key. `classifier calibration-report` и `classifier suggest-labels` выводят JSON в stdout или в `--output`.

## Safety summary

Main `dj-sim` CLI не переписывает source audio. Обычные write paths — SQLite rows, generated reports или generated ANN sidecar files. Audio repair и duplicate deletion находятся в отдельных Audio Doctor и Audio Dedup tools и документированы как dry-run-first maintenance tools.

# CLI reference

> Audience: Power users who already know the workflow.
> Goal: Look up current supported command shapes without legacy command names.
> Type: reference

`dj-sim` is the installed console entry point. Pass `--db <library-db>` whenever you do not want the default `dj-track-similarity.sqlite` in the current working directory.

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
| `scan` | Read tags from a music folder into SQLite. | SQLite only |
| `analyze` | Run selected SONARA, MAEST, MERT, or CLAP analysis families. | SQLite only |
| `analyze-classifier` | Score one promoted local classifier profile. | SQLite only |
| `text-search` | Embed a CLAP text prompt and search stored CLAP audio embeddings. | No |
| `relocate-library` | Preview or apply stored path remapping after a library move. | SQLite only with `--apply` |
| `doctor` | Print Python, Torch, CUDA, and suggested install diagnostics. | No |
| `serve` | Start the FastAPI/browser UI backend. | Runtime server only |

## Unified analysis options

```powershell
dj-sim analyze --models sonara,maest,mert,clap --device auto --top-k 5 --track-batch-size 4 --inference-batch-size 4 --db <library-db>
```

- `--models`: comma-separated `sonara`, `maest`, `mert`, `clap`.
- `--device`: `auto`, `cpu`, or `cuda`.
- `--top-k`: MAEST labels per track, 1-10.
- `--track-batch-size`: decoded tracks held together, 1-64.
- `--inference-batch-size`: model forward-pass batch size, 1-128.
- `--diagnostics`: write decoder fallback and batch timing diagnostics to the file log.
- Omit `--limit` for the whole library in the CLI. In the UI, `Analyze limit = 0` means whole library.

## Text search options

```powershell
dj-sim text-search "warm dub techno pads" --limit 25 --min-similarity 0.35 --device auto --db <library-db>
dj-sim text-search "warm dub techno pads" --use-ann-index --index-dir <index-folder> --db <library-db>
```

CLAP text search requires stored CLAP audio embeddings. `--use-ann-index` is explicit opt-in to a persistent CLAP sidecar; missing, stale, or unsupported sidecars warn and fall back to exact search.

## Persistent index commands

```powershell
dj-sim index build --adapter clap --db <library-db>
dj-sim index verify --adapter clap --db <library-db>
dj-sim index benchmark --adapter clap --recall-k 50 --threshold 0.97 --output .\reports\clap-index.json --db <library-db>
dj-sim index clear --adapter clap --db <library-db>
dj-sim index clear --db <library-db>
```

Supported adapters are `mert`, `maest`, and `clap`. Common options are `--index-dir <index-folder>` and `--backend auto|hnswlib|exact-numpy`. HNSW tuning options are `--ef-construction`, `--m`, and `--ef-search`. See [Persistent ANN indexes](../tools-and-scripts/persistent-ann-indexes.md).

## Evaluation commands

Evaluation commands require the current SQLite schema and are intended for local diagnostics, calibration, and manual feedback workflows.

| Command | Typical shape | Output or write |
| --- | --- | --- |
| `eval export-seed-sample` | `dj-sim eval export-seed-sample --count 50 --output <seeds.csv> --db <library-db>` | CSV |
| `eval export-candidates` | `dj-sim eval export-candidates --seed-track-id 123 --source mert --output <candidates.csv> --db <library-db>` | CSV plus optional recorded sessions |
| `eval export-weighted-candidates` | `dj-sim eval export-weighted-candidates --profile <profile.json> --output <candidates.csv> --db <library-db>` | CSV plus optional recorded sessions |
| `eval import-pair-feedback` | `dj-sim eval import-pair-feedback --input <pair-feedback.csv> --db <library-db>` | SQLite feedback rows |
| `eval import-transition-feedback` | `dj-sim eval import-transition-feedback --input <transition-feedback.csv> --db <library-db>` | SQLite feedback rows |
| `eval report` | `dj-sim eval report --output <report.json> --db <library-db>` | JSON |
| `eval run-ablation` | `dj-sim eval run-ablation --output <ablation.json> --db <library-db>` | JSON |
| `eval profile-sources` | `dj-sim eval profile-sources --output <sources.json> --profile-output <profile.json> --db <library-db>` | JSON profile diagnostics |
| `eval build-score-profile` | `dj-sim eval build-score-profile --source-profile-report <sources.json> --name <name> --output <profile.json>` | JSON score profile |
| `eval apply-score-profile` | `dj-sim eval apply-score-profile --profile <profile.json> --output <report.json> --db <library-db>` | JSON |
| `eval run-calibration` | `dj-sim eval run-calibration --output <calibration.json> --db <library-db>` | JSON; optional recorded summary with `--record` |
| `eval optimize-score-profile` | `dj-sim eval optimize-score-profile --output <optimizer.json> --db <library-db>` | JSON; optional promotion with `--promote` |
| `eval sweep-risk-penalty` | `dj-sim eval sweep-risk-penalty --profile <profile.json> --output <sweep.json> --db <library-db>` | JSON |

Use `--judged-only` on supported report commands when you want matched judged-label gates. Use repeated options such as `--k`, `--source`, `--seed-track-id`, or `--weight` when the command help says they are repeatable.

## Classifier diagnostics

```powershell
dj-sim analyze-classifier live_instrumentation --limit 25 --db <library-db>
dj-sim classifier calibration-report --classifier live_instrumentation --output <report.json> --db <library-db>
dj-sim classifier suggest-labels --classifier live_instrumentation --mode uncertainty --limit 25 --output <suggestions.json> --db <library-db>
```

`analyze-classifier` writes scores for one promoted classifier key. `classifier calibration-report` and `classifier suggest-labels` emit JSON to stdout or to `--output`.

## Safety summary

The main `dj-sim` CLI does not rewrite source audio. Normal write paths are SQLite rows, generated reports, or generated ANN sidecar files. Audio repair and duplicate deletion workflows live in the separate Audio Doctor and Audio Dedup tools and are documented as dry-run-first maintenance tools.

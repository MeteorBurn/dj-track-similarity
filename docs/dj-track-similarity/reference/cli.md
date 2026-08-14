# CLI reference

> Audience: Users who need exact command names.
> Goal: List the current CLI surface and safe examples.
> Type: reference

The installed console script is `dj-sim`. Commands assume the Python environment is active.

## Core workflow commands

Scan a folder:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

Analyze selected families:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --db .\data\library.sqlite
```

Serve the backend:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Without `--db`, `serve` starts with no selected database and creates no SQLite files. Select or
create a database later through the database picker or `/api/database/switch`. With `--db`, the
server opens an existing compatible bundle or creates a new Core plus Artifacts pair at the
specified path before starting Uvicorn.

The React source uses the current API. Rebuild `frontend/dist` after frontend or API changes so the
backend serves a bundle produced from the current typed client.

Run MuQ-MuLan text search:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass" --model mulan --limit 20 --db .\data\library.sqlite
```

Relocation preview:

```powershell
dj-sim relocate-library D:\Music E:\Music --db .\data\library.sqlite
```

Relocation apply:

```powershell
dj-sim relocate-library D:\Music E:\Music --apply --db .\data\library.sqlite
```

Apply updates stored SQLite paths only. It rejects missing target files and conflicts.

Score one promoted classifier:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Run a fixed-order pipeline:

```powershell
dj-sim analyze-pipeline --stages sonara,ml --db .\data\library.sqlite
```

Runtime diagnostic:

```powershell
dj-sim doctor
```

Validate the selected persisted data without recalculating analysis or changing the database:

```powershell
dj-sim validate-database --db .\data\library.sqlite
dj-sim validate-database --db .\data\library.sqlite --report .\reports\database-validation.json
```

The command walks rows sequentially and reports SQLite integrity, stored track paths, embeddings,
SONARA feature vectors, and classifier scores. File-byte changes are not treated as a failure. A
zero-exit run can still contain warnings, such as a missing file at a stored path; invalid
persisted values return exit code `2`.

## Library maintenance

Normal runtime opens one library database and does not rewrite a legacy split layout. Use a verified
backup and explicit reanalysis for deliberate data changes.

### Migrate a legacy Core/Artifacts pair

Stop `dj-sim serve`, Rhythm Lab, DB Browser, and every other SQLite user first. Then run:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'
```

Use `--backup-root PATH` only to choose the parent directory for the timestamped backup. The command
first copies legacy rows into a staged single-library file. It rebuilds FTS, compares row counts, and
checks SQLite integrity and foreign keys before publishing `library.sqlite`. The original Core and
Artifacts files move into that backup directory. It does not run analysis, reanalysis, or classifier jobs.

## Analysis options

`dj-sim analyze` supports:

| Option | Values |
| --- | --- |
| `--models` | comma-separated `sonara`, `maest`, `mert`, `muq`, `mulan`, `clap`; omitting it selects the ML order `maest,mert,muq,mulan,clap` |
| `--limit` | optional integer; omit for whole library |
| `--device` | `auto`, `cpu`, `cuda` |
| `--top-k` | `1..10` MAEST labels |
| `--track-batch-size` | `1..64` decoded tracks per job batch; default `8` |
| `--inference-batch-size` | `1..128` model samples per forward pass; default `16` |
| `--diagnostics` | file-log decoder and batch timing diagnostics |
| `--sonara-batch-size` | `1..16` concurrent native paths; default `8` |

SONARA analysis always materializes Core plus its unnormalized 48-dimensional `float32` embedding.
Core is stored in `sonara_features`; the embedding is stored in the dedicated `sonara_embeddings`
table. There is no CLI output selector. A normal rerun selects a track when either row is missing
and writes both rows together. Timeline and fingerprint collection remain disabled. The stored
SONARA embedding is not a current similarity, search, or classifier input.

`analyze-classifier <classifier_key>` forms a separate database-only job for the named promoted
artifact. `analyze-pipeline` always executes selected stages as SONARA, then ML; `--ml-models`
cannot contain SONARA.

For structural updates and optional reanalysis, follow
[Migrate and reanalyze SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

## Text search options

`dj-sim text-search` supports:

| Option | Meaning |
| --- | --- |
| `query` | required text prompt |
| `--limit` | result count, `1..500` |
| `--min-similarity` | optional threshold |
| `--model` | `clap` (default) or `mulan` |
| `--device` | `auto`, `cpu`, or `cuda` for the selected text embedding |
| `--use-ann-index` | require the selected family's persistent sidecar lookup instead of exact search |
| `--index-dir` | custom sidecar directory |

If the sidecar is missing, stale, or unsupported, the command fails. Omit `--use-ann-index` when you
want exact search without the sidecar.

## Persistent index commands

```powershell
dj-sim index build --model clap --db .\data\library.sqlite
dj-sim index verify --model clap --db .\data\library.sqlite
dj-sim index benchmark --model clap --db .\data\library.sqlite
dj-sim index clear --model clap --db .\data\library.sqlite
```

Models are `maest`, `mert`, `muq`, `mulan`, or `clap`. The `build`, `verify`, and `benchmark` commands require
`--model`; `clear` omits it only when clearing every generated index.

## Evaluation commands

The `eval` command group is for local diagnostics and feedback reports:

- `export-candidates`
- `export-weighted-candidates`
- `export-seed-sample`
- `import-pair-feedback`
- `import-transition-feedback`
- `report`
- `run-ablation`
- `build-score-profile`
- `run-calibration`
- `optimize-score-profile`
- `profile-sources`
- `apply-score-profile`
- `sweep-risk-penalty`

These commands require the current SQLite schema and operate on local database/report files.
Candidate export and source-profile commands accept repeatable `--source` values from `mert`,
`maest`, `muq`, `mulan`, `sonara`, and `clap`. Omitting the option keeps the established five-source
default and does not add MuQ-MuLan automatically. The default complete-analysis seed sample now requires
current SONARA, MERT, MAEST, MuQ, and CLAP coverage. Use
`--allow-partial-analysis` when that complete gate is not intended.

## Classifier diagnostics

```powershell
dj-sim classifier calibration-report --classifier live_instrumentation --db .\data\library.sqlite
```

```powershell
dj-sim classifier suggest-labels --classifier live_instrumentation --limit 25 --db .\data\library.sqlite
```

## Standalone helper tools

Rhythm Lab:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

Audio Doctor dry-run:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

Audio Dedup report:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

The default embedding sources are `mert`, `maest`, `muq`, and `clap`, with raw weights `0.43`,
`0.32`, `0.12`, and `0.04`. Repeat `--source` to choose a subset and provide one
`--weight FAMILY=VALUE` for every enabled source when overriding weights. This legacy-source
example disables MuQ explicitly:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --source mert --source maest --source clap --weight mert=0.43 --weight maest=0.32 --weight clap=0.04
```

Database optimization:

```powershell
python scripts\optimize_database.py --db .\data\library.sqlite
```

## Safety summary

- `scan`, `analyze`, `text-search`, `serve`, `doctor`, `index`, and evaluation report commands do not rewrite audio files.
- `relocate-library --apply` updates SQLite paths only.
- Audio Doctor `--apply` can rewrite repairable files.
- Audio Dedup `--apply` can delete files.
- MAEST genre tag writing is exposed through the app/API, not as a top-level `dj-sim` command.

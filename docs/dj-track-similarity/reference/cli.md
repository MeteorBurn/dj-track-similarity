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
mkdir .\backup
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backup --confirm "PREPARE SONARA RELEASE"
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Serve the backend:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Without `--db`, `serve` starts with no selected database and creates no SQLite files. Select or
create a database later through the database picker or `/api/database/switch`. With `--db`, the
server opens an existing compatible v7 bundle or creates a new Core plus Artifacts pair at the
specified path before starting Uvicorn.

The checked-in React client has not yet been ported to the v7 API. Do not treat an existing
`frontend/dist` bundle as a verified v7 UI.

Run CLAP text search:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass" --limit 20 --db .\data\library.sqlite
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

Score selected or all compatible promoted classifiers:

```powershell
dj-sim analyze-classifiers --classifiers live_instrumentation,voice_presence --db .\data\library.sqlite
dj-sim analyze-classifiers --db .\data\library.sqlite
```

Run a fixed-order pipeline:

```powershell
dj-sim analyze-pipeline --stages sonara,ml,classifiers --db .\data\library.sqlite
```

Runtime diagnostic:

```powershell
dj-sim doctor
```

## Bundle and release maintenance

The Python runtime accepts only clean schema-v7 bundles. A fresh database path creates Core plus the
mandatory adjacent Artifacts database. It does not upgrade an existing v6 database. The former
`migrate-v7` and `migrate-schema-v7` commands are gone.

Prepare the selected bundle for the loaded SONARA release:

```powershell
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backup --confirm "PREPARE SONARA RELEASE"
```

This command requires an existing writable backup directory and the exact confirmation phrase. It
derives the loaded runtime's four contracts and release hash. It also verifies a Core plus Artifacts
backup pair and records a crash-recoverable receipt. There are no raw identity or output-selection
options.

## Analysis options

`dj-sim analyze` supports:

| Option | Values |
| --- | --- |
| `--models` | comma-separated `sonara`, `maest`, `mert`, `muq`, `clap` |
| `--limit` | optional integer; omit for whole library |
| `--device` | `auto`, `cpu`, `cuda` |
| `--top-k` | `1..10` MAEST labels |
| `--track-batch-size` | `1..64` decoded tracks per job batch; default `8` |
| `--inference-batch-size` | `1..128` model samples per forward pass; default `16` |
| `--diagnostics` | file-log decoder and batch timing diagnostics |
| `--sonara-outputs` | comma-separated `core`, `timeline`, `embedding`, `fingerprint`; default `core` |
| `--sonara-batch-size` | `1..16` concurrent native paths; default `8` |

Plain SONARA analysis materializes `core` only, but the active release always contains four
immutable contracts. Use `--sonara-outputs core,timeline,embedding,fingerprint` to materialize all
four outputs. A later job can select another missing output from the same active release without
changing its identity. `core` is stored in Core. The other three outputs are stored in dedicated
tables in the mandatory Artifacts database. MAEST/MERT/MuQ/CLAP embeddings also live in dedicated
Artifacts tables.

Each output's exact request profile and native decoder/execution path are part of its SONARA analysis
signature. An inactive or unprepared release blocks the native job with a preparation-required
conflict. Run `prepare-sonara-release` before analysis; current partial coverage can then resume by
output signature.

`analyze-classifiers` forms a separate database-only job. An omitted `--classifiers` list means all
scoring-compatible promoted artifacts. `analyze-pipeline` accepts the same stage-specific settings
and always executes selected stages as SONARA, ML, CLASSIFIERS; `--ml-models` cannot contain SONARA.

For the complete release sequence, follow
[Prepare and rebuild a SONARA release](../workflows/reanalyze-sonara-split-storage.md).

## Text search options

`dj-sim text-search` supports:

| Option | Meaning |
| --- | --- |
| `query` | required text prompt |
| `--limit` | result count, `1..500` |
| `--min-similarity` | optional threshold |
| `--device` | `auto`, `cpu`, or `cuda` for CLAP text embedding |
| `--use-ann-index` | opt in to persistent CLAP sidecar lookup |
| `--index-dir` | custom sidecar directory |

If the sidecar is unavailable, the command warns and uses exact search.

## Persistent index commands

```powershell
dj-sim index build --model clap --db .\data\library.sqlite
dj-sim index verify --model clap --db .\data\library.sqlite
dj-sim index benchmark --model clap --db .\data\library.sqlite
dj-sim index clear --model clap --db .\data\library.sqlite
```

Models are `maest`, `mert`, `muq`, or `clap`. The `build`, `verify`, and `benchmark` commands require
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
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Audio Doctor dry-run:

```powershell
python tools\audio-doctor\audio_doctor_cli.py --db .\data\library.sqlite
```

Audio Dedup report:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
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

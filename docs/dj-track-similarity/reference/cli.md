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
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

Serve the UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

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
| `--sonara-outputs` | comma-separated `core`, `timeline`, `representations`; default `core` |
| `--sonara-batch-size` | `1..16` concurrent native paths; default `8` |

Plain SONARA analysis writes Core only. Use
`--sonara-outputs core,timeline,representations` for all three stores, or select only the missing
optional output when extending an existing analysis. Core is stored in the selected main database;
Timeline uses the adjacent `*.timeline.sqlite`; embeddings and fingerprints use
`*.representations.sqlite`. These two representation values are SONARA outputs; the searchable
MAEST/MERT/MuQ/CLAP embeddings remain in Core. The metadata dialog reads Core values and only field-name manifests for
the two side databases.

Each output's exact request profile and native decoder/execution path are part of its SONARA analysis
signature. Old-contract rows block the first native job until the database is backed up and SONARA
is explicitly reset. Current partial native coverage can then resume by output signature.

`analyze-classifiers` forms a separate database-only job. An omitted `--classifiers` list means all
scoring-compatible promoted artifacts. `analyze-pipeline` accepts the same stage-specific settings
and always executes selected stages as SONARA, ML, CLASSIFIERS; `--ml-models` cannot contain SONARA.

For a schema v5 database, follow
[Reanalyze with split SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

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
dj-sim index build --adapter clap --db .\data\library.sqlite
dj-sim index verify --adapter clap --db .\data\library.sqlite
dj-sim index benchmark --adapter clap --db .\data\library.sqlite
dj-sim index clear --adapter clap --db .\data\library.sqlite
```

Adapters are `mert`, `maest`, or `clap`.

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

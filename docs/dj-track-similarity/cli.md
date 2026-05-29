# CLI Reference

This page documents the `dj-sim` command line interface. Use the CLI for
repeatable local workflows, batch analysis, quick diagnostics, and operations
that are easier to review in a terminal than in the web UI.

## CLI Reference

Install the project first so `dj-sim` is available:

```powershell
python -m pip install -e ".[dev]"
```

Each database-aware command declares its own `--db` option; there is no global
`--db`. Use `--db` to target a specific SQLite database. When `--db` is omitted,
those commands default to:

```text
dj-track-similarity.sqlite
```

in the current working directory. The `doctor` command does not touch any
database and therefore accepts no `--db`.

## Choosing a Command

| Goal | Command |
| --- | --- |
| Add or refresh tracks from a folder | `dj-sim scan` |
| Start the local web UI/API server | `dj-sim serve` |
| Build MERT or CLAP embeddings | `dj-sim analyze` |
| Build explainable Sonara features | `dj-sim analyze-sonara` |
| Predict MAEST genres and MAEST embeddings | `dj-sim analyze-genres` |
| Score a promoted Rhythm Lab classifier | `dj-sim analyze-classifier` |
| Search with a CLAP text prompt | `dj-sim text-search` |
| Update stored paths after moving a library | `dj-sim relocate-library` |
| Check Python, PyTorch, and CUDA setup | `dj-sim doctor` |

### `dj-sim`

```powershell
dj-sim [OPTIONS] COMMAND [ARGS]...
```

App-level options (Typer built-ins, not a shared `--db`):

| Option | Meaning |
| --- | --- |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Print shell completion code. |
| `--help` | Show help. |

> Note: `--db` is not an app-level option. It is repeated on each command that
> reads or writes a database. The three job-based analysis commands (`analyze`,
> `analyze-sonara`, `analyze-genres`) render a live progress bar; `scan`,
> `relocate-library`, `analyze-classifier`, `text-search`, `doctor`, and `serve`
> print plain output only.

Commands:

```text
scan
relocate-library
analyze
analyze-genres
analyze-sonara
analyze-classifier
doctor
text-search
serve
```

### `dj-sim scan`

Scan a music folder and add or update SQLite track rows.

```powershell
dj-sim scan <path-to-music> --db .\data\library.sqlite
```

Usage:

```text
dj-sim scan [OPTIONS] MUSIC_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `MUSIC_ROOT` | path | yes | Folder scanned recursively for supported audio files. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

`scan` reads audio metadata and writes SQLite only. It does not modify audio
files.

Use this first for a new database, and rerun it after adding files to the music
folder. Existing analysis is kept for unchanged tracks.

### `dj-sim serve`

Start the local FastAPI server and serve the frontend.

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Usage:

```text
dj-sim serve [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | text | `127.0.0.1` | Bind address for the local server. |
| `--port` | integer | `8765` | HTTP port. |
| `--db` | path | none | Optional SQLite database path. Without it, choose/create a database in the UI. |
| `--log-level` | text | `info` | File log level: `debug`, `info`, `warning`, `error`, or `critical`. |
| `--log-track-events` | flag | off | Write successful per-track events to the file log. |
| `--help` | flag | off | Show help. |

Then open:

```text
http://127.0.0.1:8765/
```

There is also a Windows helper:

```powershell
scripts\run_server.cmd
```

Use `serve` when you want the browser workflow: paged browsing, playback
preview, analysis controls, search tabs, classifier filters, exports, and
metadata review.

### `dj-sim analyze`

Build missing MERT or CLAP embeddings.

```powershell
dj-sim analyze --adapter mert --device auto --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of missing embeddings to analyze. |
| `--adapter` | text | `mert` | Embedding adapter: `mert` or `clap`. |
| `--device` | text | `auto` | Embedding device: `auto`, `cpu`, or `cuda`. |
| `--batch-size` | integer `1..64` | `4` | Embedding inference batch size. |
| `--diagnostics` | flag | off | Write decoder fallback and batch timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Examples:

```powershell
dj-sim analyze --adapter mert --device cpu --batch-size 2 --db .\data\library.sqlite
dj-sim analyze --adapter clap --device cuda --batch-size 8 --db .\data\library.sqlite
```

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=<key> device=<device> batch_size=<n>
```

`auto` chooses CUDA when PyTorch sees a GPU, otherwise CPU. Explicit `cuda`
fails if CUDA is unavailable.

Use `--adapter mert` for seed-track similarity. Use `--adapter clap` when you
want CLAP text search. If you only need explainable feature search, run
`analyze-sonara` instead.

### `dj-sim analyze-sonara`

Extract missing Sonara playlist features.

```powershell
dj-sim analyze-sonara --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-sonara [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing Sonara features to analyze. |
| `--batch-size` | integer `1..64` | `1` | Parallel Sonara track workers. |
| `--diagnostics` | flag | off | Write analysis timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> batch_size=<n>
```

Sonara `batch-size` means parallel track workers.

Use this when you want the SONARA search tab, visible feature groups, or
library-level fields such as analyzed BPM, key, energy, danceability, and
loudness.

### `dj-sim analyze-genres`

Extract missing MAEST genre labels.

```powershell
dj-sim analyze-genres --device auto --top-k 3 --batch-size 4 --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-genres [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer | none | Maximum number of tracks missing MAEST genres to analyze. |
| `--device` | text | `auto` | MAEST device: `auto`, `cpu`, or `cuda`. |
| `--top-k` | integer `1..10` | `3` | Number of MAEST genre labels to store per track. |
| `--batch-size` | integer `1..64` | `4` | MAEST inference batch size. |
| `--diagnostics` | flag | off | Write decoder fallback and batch timing diagnostics to the file log. |
| `--help` | flag | off | Show help. |

Output:

```text
[########################] 100.0% processed=<n>/<n> analyzed=<n> failed=<n> <rate> tracks/s eta=<time>
state=<state> total=<n> processed=<n> analyzed=<n> failed=<n> embedding_key=maest device=<device> top_k=<n> batch_size=<n>
```

MAEST analysis writes SQLite genre metadata and a MAEST embedding vector.

Use this before reviewing generated genres, using the `syncopated` preset, or
training/scoring combined classifier profiles. It does not write genre tags to
audio files by itself.

### `dj-sim analyze-classifier`

Score tracks with a promoted classifier profile.

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Usage:

```text
dj-sim analyze-classifier CLASSIFIER [OPTIONS]
```

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `CLASSIFIER` | text | required | Classifier key, for example `live_instrumentation`. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--model` | path | `models/classifiers/<artifact-prefix>/model.joblib` | Optional classifier artifact path. |
| `--limit` | integer | none | Maximum number of feature-complete tracks to score. |
| `--help` | flag | off | Show help. |

Output:

```text
classifier=live_instrumentation scored=<n> skipped=<n> model=<path>
```

The command reads existing SONARA, MERT, and MAEST data. Tracks missing any
required input are skipped. Scores are upserted into `track_classifier_scores`.
Unlike the three `analyze*` job commands, classifier scoring runs synchronously
and prints a single summary line instead of a live progress bar.

Use this after promoting a model from Rhythm Lab. If many tracks are skipped,
run Sonara, MERT, and MAEST analysis for those tracks first.

### `dj-sim text-search`

Run CLAP text-to-audio search.

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 25 --db .\data\library.sqlite
```

Usage:

```text
dj-sim text-search [OPTIONS] QUERY
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `QUERY` | text | yes | Text description embedded by CLAP. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--limit` | integer `1..500` | `50` | Maximum result count. |
| `--min-similarity` | float | none | Optional minimum score threshold. |
| `--device` | text | `auto` | CLAP device: `auto`, `cpu`, or `cuda`. |
| `--help` | flag | off | Show help. |

Output rows:

```text
<score>    <track_id>    <path>
```

CLAP audio embeddings must exist before text search can return useful results.

Use this for exploratory searches where a text description is faster than
choosing seed tracks. Concrete prompts with mood, rhythm, instrumentation, and
vocal presence tend to be more useful than a single broad genre.

### `dj-sim relocate-library`

Preview or apply stored path relocation after moving the same music folder.

```powershell
dj-sim relocate-library .\music-old .\music-new --db .\data\library.sqlite
```

Apply after reviewing the dry run:

```powershell
dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite
```

Usage:

```text
dj-sim relocate-library [OPTIONS] OLD_ROOT NEW_ROOT
```

Arguments:

| Argument | Type | Required | Meaning |
| --- | --- | --- | --- |
| `OLD_ROOT` | path | yes | Existing stored root prefix in SQLite. |
| `NEW_ROOT` | path | yes | New root where the same files now exist. |

Options:

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--apply` | flag | off | Update stored paths after preview checks pass. |
| `--db` | path | `dj-track-similarity.sqlite` | SQLite database path. |
| `--help` | flag | off | Show help. |

Output:

```text
dry_run=<true|false> tracks_matched=<n> tracks_updated=<n> missing_files=<n> conflicts=<n>
```

Conflicts and missing target files are printed per track. Apply mode rejects
missing files and conflicts instead of partially updating paths.

Use this only when the same audio files moved to a new root folder and you want
to keep existing track IDs, analysis, and classifier scores. Always review the
dry-run output before adding `--apply`.

### `dj-sim doctor`

Print Python, PyTorch, and CUDA runtime diagnostics.

```powershell
dj-sim doctor
```

Usage:

```text
dj-sim doctor [OPTIONS]
```

`doctor` is read-only environment diagnostics. It does not open a database and
accepts no `--db`.

Output can include:

```text
python=<path>
torch=<version>
torch_cuda_build=<version-or-none>
cuda_available=<true|false>
cuda_device_count=<n>
cuda_device_name=<name-or-none>
nvidia_smi_cuda=<version-or-none>
device_auto=<cuda|cpu>
suggested_torch_index=<url>
install=torch torchaudio --index-url <url>
```

Use this when `auto`, `cpu`, or `cuda` behavior is unclear.

Run this before long GPU analysis if you changed Python packages, CUDA wheels,
drivers, or FFmpeg/TorchCodec setup.

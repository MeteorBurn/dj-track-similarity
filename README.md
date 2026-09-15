> [!WARNING]
> **Early development.** This is a personal enthusiast project under active development. Schemas, commands, defaults, and UI structure change often. Expect incomplete features and breaking changes.

# 🎧 DJ Track Similarity

**Build DJ sets as stories from your own local music library.**

<p align="center"><img src="img/dj-track-similarity-banner.png" alt="DJ Track Similarity" width="100%"></p>

`dj-track-similarity` is a local-first workbench for large music folders. It scans them into a SQLite library and runs audio-model analysis on your own machine. Search ranks candidates around seed tracks or text prompts, and the set you assemble by ear exports as M3U or CSV. The server binds to `127.0.0.1` by default, and model assets load only from the local `models/` directory with downloads disabled. Model scores are ranking evidence for listening, not DJ decisions.

## ✨ The core idea

BPM, key, energy, tags, and crates are the usual DJ toolkit. This project keeps that layer and adds two more:

1. **Technical compatibility.** BPM, key, duration, energy, and related metadata from SONARA analysis and file tags. Available today.
2. **Sonic compatibility.** Rhythm, timbre, density, dynamics, and audio similarity from SONARA features and MAEST, MERT, MERT-v2, MuQ, MuQ-MuLan, and CLAP embeddings, plus texture and atmosphere through text prompts. Available today as ranking evidence.
3. **Set dramaturgy.** A set that keeps flowing while the mood changes slowly, through chapters toward a destination. This is the direction. Nothing in the app orders a set automatically, and stored mood values are not a similarity input yet.

The goal is a DJ assistant that builds a playable narrative from reference tracks, start and target moods, a text prompt, an emotional arc, a personal classifier profile, and the previous track in the set. Similarity is one building block of that goal.

Large personal libraries hide music you forgot you own. A typical loop with the current app:

1. Seed a search with an unusual opener, or open the LAB tab to compare how each model ranks the same reference.
2. Preview the candidates, add one to the current set, and seed the next search from it.
3. Repeat, shaping the flow by listening rather than by score.

The author claims no ML or music-information-retrieval expertise. Model outputs are stored separately per model so you can inspect them. The full background and the feature/direction boundary live in the [project idea](docs/dj-track-similarity/concepts/project-idea.md) page.

## ✅ What the project can do today

- Scan a local music folder into one SQLite library (tags read with Mutagen) and browse it in server-side pages.
- Analyze tracks with SONARA, MAEST, MERT, MERT-v2, MuQ, MuQ-MuLan, and CLAP, and search from seed tracks with any of those seven models.
- Search from text prompts with CLAP or MuQ-MuLan once that family's audio embeddings exist (see workflow 4 for A/B comparison and feedback).
- Train personal classifiers in Rhythm Lab (label, train, benchmark, promote) and filter the library by promoted scores in the CLASSIFIER tab.
- Keep a manual current set, export it as M3U or CSV, and remove a confirmed track from the catalog without touching its audio file.
- Run report-first Audio Doctor and Audio Dedup and backup-first database optimization (see [Maintenance tools](#-maintenance-tools)).

## 🚀 Quick start

Development is verified on Windows. Run these PowerShell examples from the repository root. `uv run --no-sync` and the root `.venv` interpreter need no activation.

### What you need

- **`uv`**, the only Python-side prerequisite. `.python-version` pins CPython `3.10.20`, which `uv sync` downloads when the machine lacks it.
- **FFmpeg `8.1.1` as a full shared build.** The version is checked exactly, any other release is refused, and `ffmpeg.exe` without the shared libraries next to it is never enough.
- **Node.js** for the browser UI (the launcher starts Vite, and a clone has no built `frontend/dist`) and for the docs site. Pure CLI use does not need it.
- **A local folder of audio files.** Source files stay in place. See the [Safety model](#-safety-model).

### Step 1 - install the prerequisites

```powershell
winget install --id astral-sh.uv --exact
winget install --id OpenJS.NodeJS.LTS --exact
winget install --id Gyan.FFmpeg.Shared --exact --version 8.1.1
```

Keep `--version 8.1.1`, because the runtime accepts no other release. A hand-extracted `8.1.1` full shared archive also works. Reopen the terminal afterwards so any `PATH` change is visible, and use Step 2 if the runtime still cannot find the `bin` directory.

### Step 2 - make FFmpeg discoverable

The runtime needs the `bin` directory of the shared build. When `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` is set, only that directory is tried. Otherwise the first `PATH` entry holding a complete `8.1.1` build wins. To set it for this and future terminals:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR = "C:\path\to\ffmpeg\bin"
[Environment]::SetEnvironmentVariable(
  "DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR", $env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR, "User")
```

### Step 3 - install the project

The base `uv sync` covers scan, serving, a fresh library database, and set export. The frontend and the docs site are separate npm installs. The third command below is needed only to build or check documentation (that package has no lockfile). Model analysis needs extras, described in [Add model-backed analysis](#-add-model-backed-analysis).

```powershell
uv sync --locked --extra dev
npm --prefix .\frontend ci
npm --prefix .\docs\dj-track-similarity install --no-package-lock
```

### Step 4 - verify

```powershell
uv run --no-sync dj-sim doctor
& .\.venv\Scripts\python.exe -c 'from dj_track_similarity.audio.ffmpeg_runtime import inspect_audio_runtime; print(inspect_audio_runtime())'
```

`doctor` prints the interpreter and Torch status, then the resolved FFmpeg directory, version, and PyAV binding. Without the `ml` extra it reports `torch=missing` (plus an install hint when a CUDA driver is detected) and skips the audio runtime check, so the second command checks the audio runtime on a base install. When the runtime is refused, the output lists every directory that holds FFmpeg libraries and why it was rejected.

### First run

Scan your music folder (replace `D:/Music`) into a new library. Keeping it under `database/` lets the interactive launcher find it:

```powershell
uv run --no-sync dj-sim scan D:/Music --db ./database/library.sqlite
```

Start the backend (`127.0.0.1:8765`) and the live Vite UI with the Windows launcher, keep its window open, and open the `Open UI` address it prints (`http://127.0.0.1:5173/`) in a browser. The window shows the output, and Ctrl+C stops the servers. Run it without arguments to pick a database from `database/` (or type a path to create one) and then choose the mode:

```powershell
.\run_server.cmd local --db .\database\library.sqlite
.\run_server.cmd lan --db .\database\library.sqlite
.\run_server.cmd
```

`local` binds `127.0.0.1`, and `lan` binds `0.0.0.0` and prints a LAN URL. Naming a mode skips the prompts. `--db` opens an existing compatible library or creates a new one at that path. Without it the server creates no SQLite file and waits for the database picker. The top-bar power button stops the backend, a managed Rhythm Lab, and the launcher's Vite child. Launcher prompts and shutdown details are in the [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md).

## 🧠 Add model-backed analysis

Model jobs need optional extras on top of the base install:

```powershell
uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev
```

`sonara`, `ml`, and `rhythm-lab` carry the analysis stacks, `dev` adds the test dependencies, and `audio-online` adds the two packages the [Audio Online](docs/dj-track-similarity/tools-and-scripts/audio-online.md) tool needs. Name every extra you keep in one `uv sync`, because its default exact sync removes the others.

`sonara` and the Torch packages in `ml` resolve through `[tool.uv.sources]`. `sonara` points at a patched SONARA `0.3.6` wheel at a local path that a fresh clone lacks. Build or obtain the matching wheel from the SONARA sources, point the source entry at it, then run `uv lock` before a locked sync. On Windows AMD64 with Python 3.10, `ml` selects `torch`, `torchaudio`, and `torchvision` from the CUDA 13.0 index plus the exact TorchCodec `0.16.0+cu130` wheel. Other supported environments select TorchCodec `0.16.0`.

### Prepare local model assets

The `ml` extra installs packages, not weights. Adapters load pinned assets only from this checkout's `models/` directory and verify their SHA-256 hashes, with automatic downloads and Hub caches disabled. A fresh clone needs these assets before ML analysis or text search can load a model. File names and digests are declared in [analysis_models.py](src/dj_track_similarity/analysis_models.py).

| Family | Required directories under `models/` |
| --- | --- |
| MAEST | `maest/` |
| MERT | `mert/` |
| MERT-v2 | `mert-v2/` |
| MuQ | `muq/` |
| MuQ-MuLan | `mulan/`, `mulan/text/`, `muq/` |
| CLAP | `clap/`, `clap/text/` |

### Run analysis

With the selected dependencies and assets available, run a small first pass:

```powershell
uv run --no-sync dj-sim analyze --models sonara --limit 25 --db ./database/library.sqlite
uv run --no-sync dj-sim analyze --models maest,mert,mert_v2,muq,mulan,clap --limit 25 --db ./database/library.sqlite
uv run --no-sync dj-sim analyze-pipeline --stages sonara,ml --db ./database/library.sqlite
```

Omit `--limit` to analyze the whole library. SONARA runs alone on the CPU while the ML families run together, and the pipeline always runs SONARA before ML. Reruns target only tracks with missing outputs, and per-file failures are kept in the job status without stopping the run. CUDA is recommended for full-library ML runs. The full option table is in the [CLI reference](docs/dj-track-similarity/reference/commands.md#dj-sim-analyze). Useful options:

- `--sonara-batch-size 1..16` (default `8`) for the SONARA job
- `--sonara-bpm-min` / `--sonara-bpm-max` (default `70` / `180`) set the library-wide BPM range on the first SONARA run; choose it here or in the browser SONARA settings dialog, because changing it later needs a SONARA analysis reset
- `--device auto|cpu|cuda` for ML inference
- `--top-k 1..10` for MAEST labels
- `--track-batch-size 1..64` (default `8`) and `--inference-batch-size 1..128` (default `16`) for ML batching

Every job loads its selected models first and reports that as a warm-up phase. A missing or invalid local asset fails the job before any track is decoded. In the browser, SONARA and ML each offer a Direct Mode that reads source files in place and an optional Staged Mode for libraries on slow disks, which copies selected files into a user-selected temporary folder without touching the source and gives the analyzer only the staging paths. Tuning values persist in browser `localStorage`. The staging folder does not, because it receives temporary copies of your audio, so every session asks for it again. See [Model warm-up](docs/dj-track-similarity/reference/analysis-families.md#model-warm-up) and [Direct and Staged Mode](docs/dj-track-similarity/reference/analysis-families.md#direct-and-staged-mode).

## 🎚️ Main workflows

The browser interface is in Russian. Model names, tab labels, and analysis mode names stay English, and [UI language](docs/dj-track-similarity/help/ui-language.md) maps the labels. Search tabs are SIMILARITY, PROMPT, CLASSIFIER, and LAB (Model Listening Lab).

### 1. 🔍 Rediscover your own library

Filters, likes, analysis coverage, text search, and seed search find tracks that match a sound you have in mind, with or without a set in progress. See [Browse library](docs/dj-track-similarity/user-guide/browse-library.md).

### 2. 🎯 Start from a reference track

Pick up to five tracks as seeds. The SIMILARITY tab ranks candidates in one model space per search: SONARA measured Core features with a manual mixer of five sliders and nine directional modifiers, or a MAEST, MERT, MERT-v2, MuQ, MuQ-MuLan, or CLAP embedding space. The LAB tab takes the first seed and shows a short candidate list per available model. Scores are model-specific, and a saved listening verdict reappears when the same candidate returns for that reference and model. See [Search with seeds](docs/dj-track-similarity/user-guide/search-with-seeds.md).

### 3. 🌊 Curate the current set

Preview candidates and add rows to the shared current set. Any result list adds one row at a time. Bulk adds exist for the whole current library page in the browser and for every shown PROMPT candidate. The set panel previews and removes tracks. It also saves the list as a Rhythm Lab collection and exports M3U or CSV. The set is in-memory browser state rather than automatic sequencing, and switching databases clears it together with other catalog-bound state. See [Export playlists](docs/dj-track-similarity/user-guide/export-playlists.md).

### 4. 💬 Search by text

After CLAP or MuQ-MuLan audio embeddings exist, the PROMPT tab searches your library from a prompt bank composed of presets. Each preset carries its own wording per model plus optional negative prompts you can switch off.

A/B runs MuQ-MuLan and CLAP side by side. Approve or reject results to save feedback for that exact query and model. Later PROMPT-tab searches of the same query apply it automatically once at least three usable approvals exist, while the CLI does not use feedback. The results show the executed query and whether feedback applied.

The first search loads the text model, which stays cached until about ten minutes pass without a search. Text-search scores are prompt evidence inside one model's score space and are not comparable to seed-search scores or to the other text model. See [Text search](docs/dj-track-similarity/user-guide/text-search.md). Free-form prompts are available from the CLI:

```powershell
uv run --no-sync dj-sim text-search "dark hypnotic techno, rolling bass, low light, late night tension" --model clap --db ./database/library.sqlite
```

### 5. 🧪 Train personal classifiers

<p align="center"><img src="img/rhythm-lab-banner.png" alt="Rhythm Lab" width="100%"></p>

Rhythm Lab is a separate local app that turns listening decisions into classifier scores. Launch it from the main app. The backend starts or reuses it at `127.0.0.1:8777`, bound to the selected library, with labels in `tools/rhythm-lab/database/rhythm_lab.sqlite`. A new labels database has no built-in profile, so create or select the one you want to train. See [Rhythm Lab](docs/dj-track-similarity/tools-and-scripts/rhythm-lab.md), [Train a personal classifier](docs/dj-track-similarity/workflows/train-personal-classifier.md), and [CLASSIFIER tab](docs/dj-track-similarity/user-guide/class-tab.md). The loop:

1. Label examples in Rhythm Lab.
2. Train and review the profile.
3. Promote one artifact into `models/classifiers/<profile-slug>/` (the profile key with hyphens, such as `live-instrumentation`).
4. Score the library with `dj-sim analyze-classifier`.
5. Filter by the scores in the CLASSIFIER tab.

Scoring is database-only. It reads the stored SONARA, MAEST, MERT, MERT-v2, MuQ, MuQ-MuLan, and CLAP inputs the promoted manifest names, and tracks missing a required input are left out of the job. From PowerShell, with the `rhythm-lab` extra installed, replace `live_instrumentation` with your profile key:

```powershell
& .\.venv\Scripts\python.exe tools/rhythm-lab/rhythm_lab_cli.py train --profile live_instrumentation --source ./database/library.sqlite --labels tools/rhythm-lab/database/rhythm_lab.sqlite
& .\.venv\Scripts\python.exe tools/rhythm-lab/rhythm_lab_cli.py promote --profile live_instrumentation --source ./database/library.sqlite --labels tools/rhythm-lab/database/rhythm_lab.sqlite
uv run --no-sync dj-sim analyze-classifier live_instrumentation --db ./database/library.sqlite
```

## 🧩 How the pieces fit

```text
audio files -> scan tags -> SQLite library -> browse/search/export
      +---- native SONARA -----------^
      +---- TorchCodec (PyAV recovery) -> ML families ---^
      +---- stored inputs -> classifiers -> CLASSIFIER scores
```

The app keeps evidence sources separate and never folds them into one score scale. A file genre tag, a MAEST genre label, a CLAP text score, and a duplicate score answer different questions ([Similarity scores](docs/dj-track-similarity/concepts/similarity-scores.md)).

- **File tags** come from Mutagen during scan and Refresh Tags.
- **SONARA** stores measured Core features (BPM, key, duration, energy, rhythm, dynamics, timbre, tonal signals), a 48-dimensional embedding, and a versioned acoustic fingerprint. The BPM analysis range is a library-wide setting claimed by the first SONARA run. Every later run has to reuse it, and switching requires a SONARA analysis reset. The library rejects an upper bound below twice the lower one. Presets are Rekordbox 70 to 180, VirtualDJ 80 to 240, and Mixed In Key 79 to 192.
- **MAEST** stores genre labels and an audio embedding.
- **MERT**, **MERT-v2**, **MuQ**, **MuQ-MuLan**, and **CLAP** each store their own audio embedding in a separate seed-search space; MERT-v2 stores all 24 transformer layers instead of one vector. CLAP and MuQ-MuLan also serve text-to-track search. MuQ-MuLan does not reuse MuQ embeddings.
- **Rhythm Lab classifiers** score from stored inputs only and save results under a classifier key (see workflow 5).

The ML families share one in-process decode per track: TorchCodec `0.16` over the shared FFmpeg `8.1.1` libraries, with a per-family PyAV `17.1.0` retry that discards malformed packets and keeps the valid audio around them. SONARA decodes natively and uses the same PyAV retry. The retry recovers a readable file. It does not repair a damaged one. Decoding never launches `ffmpeg.exe` (the executable is only run with `-version` to verify the runtime), and the CPU or CUDA device applies to inference only. See [Analysis families](docs/dj-track-similarity/reference/analysis-families.md).

Tempo comparisons weight SONARA BPM by its confidence and beat-grid stability. Unreliable tempo drifts toward a neutral score instead of earning a bonus or a hard rejection. Transition diagnostics also consult SONARA tempo candidates and the file BPM tag at low confidence, while SONARA similarity search uses stored SONARA values only.

Audio Dedup is the SONARA fingerprint's only consumer, and no search, classifier, or dedup workflow reads the SONARA embedding yet. Mood, true peak, and ReplayGain are stored for inspection and Rhythm Lab feature sets, not for similarity scoring. In SIMILARITY search with the SONARA model, the Aggression modifier uses the stored aggression score and shrinks its directional push by SONARA's aggression confidence. See [Features, embeddings, and tags](docs/dj-track-similarity/concepts/features-embeddings-tags.md).

## 🔗 Upstream models and licenses

Optional analysis uses upstream projects and downloaded checkpoints: [SONARA](https://github.com/kkollsga/sonara), [MAEST](https://github.com/openmirlab/maest-infer), [MERT](https://github.com/yizhilll/MERT), [MuQ and MuQ-MuLan](https://github.com/tencent-ailab/muq), and [LAION CLAP](https://github.com/LAION-AI/CLAP). The repository does not vendor model weights. Upstream code and weights carry different licenses, so check their terms for anything beyond local personal use. See [model citations and licenses](docs/dj-track-similarity/reference/model-citations.md).

## 🛠️ Maintenance tools

- **Audio Doctor** inspects audio metadata and container issues and is dry-run by default. `--apply` writes repairs without a further prompt. By default it backs up each file first, verifies the result, and restores the backup on failure; `--no-backup` skips the backup, so no rollback is possible. See [Audio Doctor](docs/dj-track-similarity/tools-and-scripts/audio-doctor.md).
- **Audio Dedup** reports duplicate candidates from stored SONARA fingerprints and MERT, MAEST, MuQ, and CLAP embeddings. The default `--fingerprint` mode leaves every candidate for manual review. Only `--embedding` mode can mark safe delete candidates, and those require MERT and MAEST evidence. Deletion needs the phrase `APPLY DELETE`. The CLI asks you to type it and deletes only safe candidates inside `--root`. The browser review dialog sends it once you confirm, then moves the copies you mark to the recycle bin (the default) or deletes them permanently. See [Audio Dedup](docs/dj-track-similarity/tools-and-scripts/audio-dedup.md).
- **Database validation** (`dj-sim validate-database` or the browser) checks SQLite integrity, track identities, and stored analysis data without changing the library.
- **Database optimization** (`dj-sim optimize-database --db ... [--dry-run]` or the browser) is backup-first: `VACUUM` and `ANALYZE` run against a database that already has a verified backup. A second integrity check follows; if it passes, that backup is removed, and if it fails, the backup stays as the rollback point. The browser offers optimization after a validation with zero errors, scoped to the selected database. See [Optimize database](docs/dj-track-similarity/tools-and-scripts/optimize-database.md).
- **Legacy database migration.** Startup never rewrites a legacy split (core + artifacts) database pair. Stop every database user, then run `uv run --no-sync dj-sim migrate-database --db ./database/library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`. It creates a timestamped backup and verifies the merged file. No analysis starts.

```powershell
& .\.venv\Scripts\python.exe tools/audio-doctor/audio_doctor_cli.py --db ./database/library.sqlite
& .\.venv\Scripts\python.exe tools/audio-dedup/audio_dedup_cli.py --db ./database/library.sqlite --root D:/Music --preset safe
uv run --no-sync dj-sim validate-database --db ./database/library.sqlite
uv run --no-sync dj-sim optimize-database --db ./database/library.sqlite --dry-run
```

## 🛡 Safety model

Normal workflows read source audio and never modify it. Scan, Refresh Tags, analysis, search, browser preview, analysis reset, database clear, confirmed single-track catalog removal, relocation preview, export, and classifier scoring write only SQLite rows, logs, reports, temporary preview files, temporary Staged Mode copies in the staging folder you choose, or exported M3U and CSV files.

Only three workflows touch source audio, and each one is explicit (gates and backups are described under [Maintenance tools](#-maintenance-tools)):

- **MAEST genre tag apply** writes the standard genre field of tracks with stored MAEST genres.
- **Audio Doctor `--apply`** rewrites repairable files in place.
- **Audio Dedup deletion** removes confirmed duplicate copies after an explicit confirmation.

Library relocation apply rewrites stored SQLite paths only. It never moves, copies, deletes, or retags files.

SQLite databases, logs, reports, and promoted classifier artifacts reveal library paths and listening decisions, so `.gitignore` excludes them. [Local-first safety](docs/dj-track-similarity/concepts/local-first-safety.md) holds the full write-path table.

## 📚 Documentation

The docs site starts at the [project guide](docs/dj-track-similarity/project-guide.md).

| Topic | Pages |
| --- | --- |
| Getting started | [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md), [Install](docs/dj-track-similarity/getting-started/install.md), [First library](docs/dj-track-similarity/getting-started/first-library.md), [First analysis](docs/dj-track-similarity/getting-started/first-analysis.md) |
| Everyday use | [Browse library](docs/dj-track-similarity/user-guide/browse-library.md), [Analyze library](docs/dj-track-similarity/user-guide/analyze-library.md), [Search with seeds](docs/dj-track-similarity/user-guide/search-with-seeds.md), [Text search](docs/dj-track-similarity/user-guide/text-search.md), [Export playlists](docs/dj-track-similarity/user-guide/export-playlists.md) |
| Reference and maintenance | [CLI reference](docs/dj-track-similarity/reference/commands.md), [API reference](docs/dj-track-similarity/reference/api.md), [Configuration](docs/dj-track-similarity/reference/configuration.md), [Database](docs/dj-track-similarity/reference/database.md), [SONARA integration](docs/dj-track-similarity/reference/sonara-integration.md), [Tools and scripts](docs/dj-track-similarity/tools-and-scripts/index.md), [Migrate and reanalyze SONARA storage](docs/dj-track-similarity/workflows/reanalyze-sonara-split-storage.md) |

## 🧪 Development checks

[AGENTS.md](AGENTS.md) owns project instructions, the working-branch policy, and verification routing. Check it and the live Git state before starting work. Use the smallest check that covers the change. Root Pytest collects only `tests/`, so name each tool suite explicitly:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_sonara_features.py
& .\.venv\Scripts\python.exe -m pytest tools/audio-doctor/tests
& .\.venv\Scripts\python.exe -m pytest tools/audio-dedup/tests
& .\.venv\Scripts\python.exe -m pytest tools/audio-online/tests
& .\.venv\Scripts\python.exe -m pytest tools/rhythm-lab/tests/test_rhythm_lab.py
```

Frontend runtime or build changes need type checking, the Node tests and, before a commit, the static bundle build. Maintained documentation changes run the docs check. Run `npm --prefix .\docs\dj-track-similarity run vale:sync` once after a fresh checkout or when `.vale.ini` packages change.

```powershell
npm --prefix .\frontend run typecheck
npm --prefix .\frontend test
npm --prefix .\frontend run build
npm --prefix .\docs\dj-track-similarity run check
```

## 🤖 Optional coding-agent setup

The application does not require an agent plugin. For Codex or Claude Code, the shared agents and skills live in [.djts/](.djts/). The one-time setup `.\.djts\scripts\bootstrap.ps1` registers the plugin for the available CLIs and generates the Codex agent launchers. [AGENT LAYER](docs/agent-guides/agent-layer.md#agent-layer) covers regeneration, plugin updates, and verification of the installed copy.

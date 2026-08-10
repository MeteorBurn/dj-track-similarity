> [!WARNING]
> ## 🚧 Early Development
>
> DJ Track Similarity is a personal AI-powered music analysis project currently under active development.
>
> The goal is to build practical tools for music similarity, custom music classifiers, and DJ-oriented music analysis.
>
> Most components are experimental and the architecture still changes often. Expect incomplete features, breaking changes, and frequent refactoring.

# 🎧 DJ Track Similarity

**Build DJ sets as stories from your own local music library.**

<p align="center">
  <img src="img/dj-track-similarity-banner.png" alt="DJ Track Similarity" width="100%">
</p>

`dj-track-similarity` is a local-first DJ library workbench for people with large music folders who want more than tag browsing, BPM matching, or a list of similar tracks.

The project is built around a bigger idea:

> I have a large folder of music. I want to analyze it locally, rediscover tracks I already own, search by vibe, sound, references, or text, and build DJ sets that mix cleanly and move like a story.

A good set is not just a sequence of compatible files. It has an opening, tension, release, turns, chapters, and a destination. This project helps turn a reference track into a short list that can shift mood gradually while staying coherent.

## ✨ The core idea

Most DJ tools start with the basic layer:

- BPM
- key
- energy
- metadata
- playlists
- manual crates

That layer matters, but it is not enough when you want a set to feel like a journey.

This project aims to work on three layers at once:

1. **Technical compatibility**  
   BPM, key, duration, energy, and transition-friendly metadata.

2. **Sonic and emotional compatibility**  
   Rhythm, timbre, density, dynamics, texture, atmosphere, mood, and audio similarity.

3. **Set dramaturgy**  
   A higher-level flow where tracks carry one emotional place through chapters toward a coherent destination.

The most important goal is not simply to answer:

> What sounds similar to this track?

The real goal is closer to:

> What track should come next if this set needs to keep flowing while the mood changes slowly?

Similarity is only a building block. The larger ambition is **dramaturgy**.

## 🧭 Library Problem

Large personal libraries hide a lot of forgotten music. You may own the perfect next track, but it is buried somewhere inside thousands of files.

This project should help you:

- discover tracks inside your own collection that you forgot about;
- find music with a very specific sound or atmosphere;
- start from an unusual opener and build outward;
- search by reference tracks, text prompts, or personal taste;
- prepare DJ sets that feel intentional instead of random;
- move between moods gradually instead of jumping abruptly;
- use model output as suggestions, not as truth.

A typical use case:

1. Pick an unusual reference track as the opening of a set.
2. Ask the system for candidates from your local library, or use LAB Reference Compare to inspect how each model ranks the same reference.
3. Review tracks that are close in sound, compatible for mixing, and useful for the next emotional step.
4. Add one candidate.
5. Continue from the previously selected track, letting the set evolve step by step.
6. Shape the flow through listening and manual choices while treating model scores as suggestions.

The set becomes less like a static playlist and more like a musical path.

## 📝 Author note

This is a personal enthusiast project.

I am not an ML researcher, not a music information retrieval expert, and not someone who claims to fully understand every model or music-analysis method used here. I am an enthusiast building a tool I personally wanted: something local, practical, curious, and useful for digging through a large music collection.

That also defines the attitude of the project:

- model outputs are ranking signals, not objective truth;
- the UI should help shortlist tracks, not replace listening;
- every important signal should stay inspectable and separated;
- the final decision belongs to the DJ.

This is not a commercial recommendation service and it is not a benchmark. It is a local workbench for exploration, set preparation, and learning.

<p align="center">
  <img src="img/rhythm-lab-banner.png" alt="Rhythm Lab" width="100%">
</p>

## ✅ What the project can do today

The current application already supports the practical parts of that vision:

- Create a compatible Core/Artifacts SQLite bundle and scan local audio files with Mutagen metadata.
- Browse large libraries through paginated API responses.
- Read typed metadata, analysis coverage, likes, audio preview, search state, and the current set.
- Run SONARA, MAEST, MERT, MuQ, and CLAP analysis jobs.
- Search from seed tracks with MAEST, MERT, MuQ, CLAP, and SONARA.
- Search from text prompts with CLAP after CLAP audio embeddings exist.
- Launch Rhythm Lab for local classifier labeling, training, benchmark review, and promotion.
- Read promoted Rhythm Lab classifier scores for CLASS filtering.
- Run optional Evaluation API and CLI workflows for feedback, profiles, calibration, and transition diagnostics.
- Export the current set as M3U or CSV.
- Run report-first helper tools for Audio Doctor, Audio Dedup, database optimization, and optional ANN sidecar indexes.
- Preview and explicitly migrate an incompatible Core/Artifacts pair with verified backups when its structure changes.

The Python backend and CLI require a structurally compatible bundle. They create a selected Core
database plus a mandatory adjacent `*.artifacts.sqlite` database; the optional
`*.evaluation.sqlite` database is created only when an evaluation workflow needs it. Normal startup
does not rewrite an incompatible layout. It refuses the database with a clear message so you
can inspect the explicit migration plan first.

The React frontend consumes the current database, track, analysis, search, Current Set, CLASS, LAB,
Rhythm Lab, Audio Dedup, metadata, media, and exact-identity mutation responses. Large-library loading
uses fixed server-side pages of up to `200` tracks with previous, next, and page-number navigation.

## 🚧 The long-term direction

The north star is a DJ assistant that can help generate a playable musical narrative from:

- one or more reference tracks;
- a starting mood and target mood;
- a text prompt or theme;
- a desired emotional arc;
- a personal classifier profile;
- the previous track in the set.

In that direction, a set should be able to feel like chapters in a book:

```text
opening mood -> first turn -> deeper chapter -> tension -> release -> final destination
```

The current project should be understood as a local-first foundation for that idea. Seed search and
CLAP text search are implemented today. LAB Reference Compare and classifier scoring are also
available. The browser keeps a manual current set and exports playlists. Other parts are still a
product direction rather than a finished automatic DJ.

## 🧩 How the pieces fit

```text
audio files -> scan tags -> SQLite library -> browse/search/export
      |                         ^
      +---- SONARA native -------+
      +---- FFmpeg -> ML --------+
      +---- stored inputs -> classifiers -> CLASS scores
```

The app keeps evidence sources separate:

- **File tags** come from Mutagen during scan and Refresh Tags.
- **SONARA** stores Core audio features such as rhythm, dynamics, timbre, tonal signals, BPM, key, duration, and energy. Its standalone CPU/Rust job passes file paths to `sonara.analyze_batch()`, so SONARA/Symphonia owns decoding. There is no FFmpeg or signal-analysis fallback. SONARA BPM analysis uses the project range `70.0..180.0`.
- **MAEST** stores genre labels and an audio embedding.
- **MERT** stores an audio embedding for seed similarity.
- **MuQ** stores a separate audio embedding. It is available to seed search, LAB Reference Compare, Audio Dedup, and Rhythm Lab classifier feature sets.
- **CLAP** stores an audio embedding for text-to-audio search and audio-to-audio comparison.
- **Rhythm Lab classifiers** run as a separate database-only stage and store optional local scores under a classifier key. Each promoted manifest decides which current SONARA and ML inputs are required.

Tempo-aware search and Evaluation transition diagnostics use current signed SONARA tempo
evidence. At low confidence, they also inspect SONARA candidates and the Mutagen BPM tag, while
`grid_stability` can weaken reliability. Unreliable tempo evidence moves toward a neutral score
instead of earning a similarity bonus or becoming an automatic hard rejection.

SONARA mood values are retained for inspection and possible future audio workflows; they are not
current similarity or classifier inputs. True peak and ReplayGain are also stored for
future loudness-management work, not direct SONARA similarity scoring. MAEST/MERT/MuQ/CLAP
embeddings live in dedicated tables in the mandatory Artifacts database.

SONARA analysis stores only the current Core fields. Timeline, SONARA embedding, and fingerprint
collection are disabled. Empty tables for those outputs remain as layout placeholders without
fixing a payload schema, dimension, version, or future contract.

Promoted classifier artifacts must describe the feature names and inputs they actually use. If an
analysis update changes that recipe, retrain and promote the affected profile before scoring it
again.

A file genre tag, a MAEST genre label, a CLAP text score, and an audio-to-audio duplicate score answer different questions. They can all help, but they should not be treated as one universal truth scale.

## 🔗 Upstream models and licenses

Optional analysis uses upstream projects and downloaded checkpoints, including [SONARA](https://github.com/kkollsga/sonara), [MAEST](https://github.com/openmirlab/maest-infer), [MERT](https://github.com/yizhilll/MERT), [MuQ](https://github.com/tencent-ailab/muq), and [LAION CLAP](https://github.com/LAION-AI/CLAP). The repository does not vendor model weights, and upstream code and weights may use different licenses, so check source terms for anything beyond local personal use. See [model citations and licenses](docs/dj-track-similarity/reference/model-citations.md) for details.

## 🎚️ Main workflows

### 1. 🔍 Rediscover your own library

Use the browser, filters, likes, metadata, analysis coverage, CLAP text search, and seed search to find tracks that match a sound you have in mind.

This is useful even when you are not building a set. The project can act like a discovery layer for hidden tracks and unusual textures in your own collection, including songs that match a specific atmosphere.

### 2. 🎯 Start from a reference track

Pick one or more tracks as seeds. The system can rank candidates around the seed using audio-space proximity and SONARA compatibility. LAB keeps model-family results separate for listening-led comparison.

This is useful when you have a track that feels special but you do not know what should come after it.

### 3. 🌊 Curate the current set

Preview search candidates by ear and add useful rows individually to the shared current set. You
can remove entries before export. The same list can be saved as a Rhythm Lab collection; exports
support M3U and CSV. This is browser-local working state, not automatic sequencing.

### 4. 💬 Search by text

After CLAP audio embeddings exist, the CLAP tab can search your library from text prompts such as:

```text
dark hypnotic techno, rolling bass, low light, late night tension
```

CLAP text-search scores are not the same scale as seed-based audio-to-audio scores. Good text results can have lower raw scores. Treat them as prompt evidence, not as a universal similarity value.

### 5. 🧪 Train personal classifiers

Rhythm Lab is a separate local app for turning your own listening decisions into optional classifier
scores. The backend has routes to launch or reuse it at `127.0.0.1:8777` and to save review
collections. The main frontend exposes both actions, and the standalone Lab UI reports
current/missing/stale source state plus MuQ-aware training recipes.

A new Rhythm Lab labels database starts without a built-in classifier profile. Create or select the profile you want to train. Profile-specific CLI commands use an explicit `--profile`.

The normal loop is:

1. Label examples in Rhythm Lab.
2. Train and review benchmark output for the active profile.
3. Promote one trained artifact into `models/classifiers/<profile>/`.
4. Run classifier scoring in the main library database.
5. Use the promoted scores as CLASS filters.

Classifier scoring is database-only. It reads exactly the SONARA and MAEST/MERT/MuQ/CLAP inputs named by each promoted manifest, then writes scores for the selected classifier key. It does not decode or retag source audio. Tracks without the complete manifest input set are reported as not ready and are not runtime failures.

SONARA-dependent classifier artifacts must use the same ordered feature recipe as the stored inputs
they score. Missing requested values are skipped rather than imputed as `0.0`. When that recipe
changes, retrain and promote the affected classifier, then rerun its scoring when you choose. Rhythm
Lab labels and feedback remain available for that retraining loop.

Manual commands are available when you want the CLI workflow:

```powershell
python tools/rhythm-lab/rhythm_lab_cli.py serve --source ./data/library.sqlite --labels tools/rhythm-lab/data/rhythm_lab.sqlite
python tools/rhythm-lab/rhythm_lab_cli.py train --profile live_instrumentation --source ./data/library.sqlite --labels tools/rhythm-lab/data/rhythm_lab.sqlite
python tools/rhythm-lab/rhythm_lab_cli.py promote --profile live_instrumentation --source ./data/library.sqlite --labels tools/rhythm-lab/data/rhythm_lab.sqlite
dj-sim analyze-classifier live_instrumentation --db ./data/library.sqlite
dj-sim analyze-classifiers --db ./data/library.sqlite
```

The default Rhythm Lab state is the single stable database at
`tools/rhythm-lab/data/rhythm_lab.sqlite`. Launching Rhythm Lab from the main app binds that Lab
database to the currently selected Core database.

See [Rhythm Lab](docs/dj-track-similarity/tools-and-scripts/rhythm-lab.md), [Train a personal classifier](docs/dj-track-similarity/workflows/train-personal-classifier.md), and [CLASS tab](docs/dj-track-similarity/user-guide/class-tab.md).

## 🚀 Quick start

Verified local development is Windows-first, but the Python package and web app are ordinary local tools. The command examples assume the environment is active.

You need:

- Python `>=3.10`
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to the ffmpeg executable
- A local folder of audio files
- Node.js only when you build the frontend or docs from source

Install the base package:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create a database and scan a music folder:

```powershell
mkdir data
dj-sim scan D:/Music --db ./data/library.sqlite
```

Start the development app with the interactive Windows launcher:

```powershell
run_server.cmd
```

It first suggests `database\volumes.sqlite` under the repository root. Press Enter to accept that
path or type a replacement. The next prompt selects local or LAN mode. The launcher starts the
backend plus the Vite live UI. Open the printed `5173` UI URL; frontend source changes are visible
without rebuilding `frontend/dist`.

Supplying `--db` opens an existing compatible bundle or creates a new Core plus Artifacts pair at
that path. If you omit `--db`, the server starts without a selected database and does not create any
SQLite file. You can then choose an existing database or create a new one with the database picker.

For non-interactive use, specify the mode and database explicitly:

```powershell
run_server.cmd local --db C:/db/volumes.sqlite
run_server.cmd lan --db C:/db/volumes.sqlite
```

`local` binds to `127.0.0.1`. `lan` binds to `0.0.0.0` and prints a LAN URL. Explicit mode commands
use only the arguments supplied on the command line.

## 🧠 Add model-backed analysis

The base install is enough for scan, backend serving, a fresh database bundle, and set export. Install
optional analysis dependencies when you want the model jobs:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Install the mutually compatible dependency set recorded by `pyproject.toml` and `uv.lock`. Those
files describe the tested environment, not a permanent ban on updates. When dependencies change,
update the manifests and lockfile together and run focused compatibility checks.

Run a small first pass:

```powershell
dj-sim analyze --models sonara --limit 25 --db ./data/library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db ./data/library.sqlite
dj-sim analyze-classifiers --db ./data/library.sqlite
dj-sim analyze-pipeline --stages sonara,ml,classifiers --db ./data/library.sqlite
```

Normal reruns analyze only missing Core rows. If a SONARA update requires a database layout
change, inspect the explicit migration first:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --dry-run
```

Apply it only after reviewing the plan. The command requires the exact confirmation
`MIGRATE DATABASE`, creates and validates Core and Artifacts backups, rebuilds the pair, and finishes
with integrity, foreign-key, and orphan checks. Reanalysis remains a separate user decision.

Useful options from the current CLI and API are:

- `--models sonara` for the standalone CPU/Rust job, or `--models maest,mert,muq,clap` for ML analysis
- `--sonara-batch-size 1..16`; default `8`, independent from ML batching
- `--device auto|cpu|cuda`
- `--top-k 1..10` for MAEST labels
- `--track-batch-size 1..64`; default `8`
- `--inference-batch-size 1..128`; default `16`
- `--diagnostics` to write decoder and batch timing details to the file log

CLI and API pipeline stages share one in-memory queue, so only one SONARA, ML, or CLASSIFIERS stage
runs at a time. The pipeline fixes
the order to SONARA, then ML, then CLASSIFIERS. Per-file failures are retained in job status and do
not stop the next stage. A fatal initialization error or cancellation does.

The SONARA control limits concurrent native file analysis, including full-file reads, rather than
neural-network inference. Each returned batch writes only the Core result through the current
repository with a per-track savepoint. The process log
reports separate native analysis, result preparation, and database storage times plus source MiB/s.
SONARA-only jobs traverse candidates in path order to keep adjacent HDD reads in the same folders.
Queued-stage messages contain only settings used by that stage. SONARA reports its outputs and
native batch, ML reports its models, device, Track batch, and Inference batch, and CLASSIFIERS
reports the selected profile count.

MuQ uses the optional `ml` dependencies and official `OpenMuQ/MuQ-large-msd-iter` weights. The app feeds MuQ only 24 kHz `float32` audio and supports CPU or CUDA. CUDA is recommended for full-library runs. The stored embedding is a normal source for seed search, LAB Reference Compare, Audio Dedup, and compatible classifier manifests. Audio Dedup callers can omit `muq` from an explicit source list.

In the CLI, omit `--limit` to analyze the whole library.

## 🖥️ Frontend status

The React source uses the current backend responses. Its main search tabs are LAB, SONARA, MERT,
MUQ, CLAP, and CLASS. Search results provide individual current-set actions, and the shared Current
Set panel provides preview, removal, Rhythm Lab collection transfer, M3U export, and CSV export.
Database changes clear catalog-bound state; exact-identity writes carry catalog UUID, track UUID,
and content generation.

The UI remains a local, listening-led workbench. Similarity and classifier values are ranking
signals for review, not objective musical truth or automatic performance decisions.

## 🛠️ Maintenance tools

- **Audio Doctor** checks audio metadata/container issues. It is dry-run-first. Apply mode requires exact `APPLY REPAIR` and existing dry-run state. See [Audio Doctor](docs/dj-track-similarity/tools-and-scripts/audio-doctor.md).
- **Audio Dedup** reports duplicate candidates from stored MERT, MAEST, MuQ, and CLAP analysis data. Its source list and weights are configurable; MuQ alone never authorizes deletion. Apply mode still requires exact `APPLY DELETE` and deletes only safe candidates inside the selected root. See [Audio Dedup](docs/dj-track-similarity/tools-and-scripts/audio-dedup.md).
- **Persistent ANN indexes** are optional generated sidecars for repeated vector lookup. Exact search remains available without an ANN flag; explicit ANN use fails when the sidecar is missing, stale, or unsupported. See [Persistent ANN indexes](docs/dj-track-similarity/tools-and-scripts/persistent-ann-indexes.md).
- **Database optimization** supports the main library database and the Rhythm Lab labels database. It backs up the SQLite file, checks integrity, and then runs SQLite maintenance commands. See [Optimize database](docs/dj-track-similarity/tools-and-scripts/optimize-database.md).

Common maintenance commands:

```powershell
python tools/audio-doctor/audio_doctor_cli.py --db ./data/library.sqlite
python tools/audio-dedup/audio_dedup_cli.py --db ./data/library.sqlite --root D:/Music --preset safe
python scripts/optimize_database.py --db ./data/library.sqlite
python scripts/optimize_database.py --db tools/rhythm-lab/data/rhythm_lab.sqlite
```

## 🛡️ Safety model

Default workflows do not modify source audio files:

- scan
- Refresh Tags
- analysis
- search
- audio preview
- analysis reset
- database clear
- relocation preview
- set generation
- export
- classifier scoring

Explicit write paths are narrow:

- MAEST genre tag apply writes the standard genre field in audio files.
- Audio Doctor apply can repair previously reported repairable files.
- Audio Dedup apply can delete confirmed duplicate candidates.
- Library relocation apply updates stored SQLite paths only. It does not move, copy, delete, or retag audio files.

SQLite databases, logs, reports, generated indexes, and promoted classifier artifacts can reveal library information. Keep them out of Git unless you intentionally choose otherwise.

## 📚 Documentation

Start here:

Documentation languages: [English](docs/dj-track-similarity/project-guide.md) ·
[Русский](docs/dj-track-similarity/ru/project-guide.md)

- [Project guide](docs/dj-track-similarity/project-guide.md)
- [Project idea](docs/dj-track-similarity/concepts/project-idea.md)
- [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md)
- [Install](docs/dj-track-similarity/getting-started/install.md)
- [First library](docs/dj-track-similarity/getting-started/first-library.md)
- [First analysis](docs/dj-track-similarity/getting-started/first-analysis.md)
- [Migrate and reanalyze SONARA storage](docs/dj-track-similarity/workflows/reanalyze-sonara-split-storage.md)
- [Browse library](docs/dj-track-similarity/user-guide/browse-library.md)
- [Search with seeds](docs/dj-track-similarity/user-guide/search-with-seeds.md)
- [Text search](docs/dj-track-similarity/user-guide/text-search.md)
- [Local-first safety](docs/dj-track-similarity/concepts/local-first-safety.md)
- [SONARA integration](docs/dj-track-similarity/reference/sonara-integration.md)
- [Tools and scripts](docs/dj-track-similarity/tools-and-scripts/index.md)
- [CLI reference](docs/dj-track-similarity/reference/cli.md)
- [Model citations and licenses](docs/dj-track-similarity/reference/model-citations.md)

## 🧪 Development checks

Run backend tests:

```powershell
python -m pytest
```

Build the frontend bundle served by the backend:

```powershell
cd frontend
npm run build
```

Check and build the docs:

```powershell
cd docs/dj-track-similarity
npm run check
```

Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages change.

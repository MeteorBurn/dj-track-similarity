# 🎧 dj-track-similarity

**Build DJ sets as stories from your own local music library.**

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
2. Ask the system for candidates from your local library.
3. Review tracks that are close in sound, compatible for mixing, and useful for the next emotional step.
4. Add one candidate.
5. Continue from the previously selected track, letting the set evolve step by step.
6. Shape the flow with controls for energy, mood, similarity, diversity, BPM movement, classifiers, and hybrid scoring.

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

## ✅ What the project can do today

The current application already supports the practical parts of that vision:

- Scan local audio files into a SQLite database with Mutagen metadata.
- Browse large libraries through a paginated web UI.
- Show metadata, analysis coverage, likes, audio preview, and search/set state.
- Run SONARA, MAEST, MERT, MuQ, and CLAP analysis jobs.
- Search from seed tracks with MERT and SONARA.
- Search from text prompts with CLAP after CLAP audio embeddings exist.
- Build Smart Set Builder previews from selected seeds or automatic anchors.
- Use Hybrid preview for weighted MERT, MAEST, SONARA, and CLAP candidate checks.
- Launch Rhythm Lab for local classifier labeling, training, benchmark review, and promotion.
- Read promoted Rhythm Lab classifier scores for CLASS filtering, SET biasing, and Hybrid diagnostics.
- Export the current set as M3U or CSV.
- Run report-first helper tools for Audio Doctor, Audio Dedup, database optimization, and optional ANN sidecar indexes.

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

The current project should be understood as a local-first foundation for that idea. Some parts are already implemented as search, SET, Hybrid, CLAP text search, classifier scoring, and playlist export. Other parts are still a product direction rather than a finished automatic DJ.

## 🧩 How the pieces fit

```text
audio files -> scan tags -> SQLite library -> browse/search/export
      |                         ^
      +---- analysis jobs -------+
      |
      +---- Rhythm Lab labels -> promoted classifiers -> CLASS/SET/Hybrid scores
```

The app keeps evidence sources separate:

- **File tags** come from Mutagen during scan and Refresh Tags.
- **SONARA** stores audio features such as rhythm, dynamics, timbre, tonal signals, BPM, key, duration, and energy.
- **MAEST** stores genre labels and an audio embedding.
- **MERT** stores an audio embedding for seed similarity.
- **MuQ** stores a separate audio embedding for future workflows. It is not used by search, SET, Hybrid, or classifiers yet.
- **CLAP** stores an audio embedding for text-to-audio search and audio-to-audio comparison.
- **Rhythm Lab classifiers** store optional local scores under a classifier key.

A file genre tag, a MAEST genre label, a CLAP text score, and an audio-to-audio duplicate score answer different questions. They can all help, but they should not be treated as one universal truth scale.

## 🔗 Upstream models and licenses

Optional analysis uses upstream projects and downloaded checkpoints, including [SONARA](https://github.com/kkollsga/sonara), [MAEST](https://github.com/openmirlab/maest-infer), [MERT](https://github.com/yizhilll/MERT), [MuQ](https://github.com/tencent-ailab/muq), and [LAION CLAP](https://github.com/LAION-AI/CLAP). The repository does not vendor model weights, and upstream code and weights may use different licenses, so check source terms for anything beyond local personal use. See [model citations and licenses](docs/dj-track-similarity/reference/model-citations.md) for details.

## 🎚️ Main workflows

### 1. 🔍 Rediscover your own library

Use the browser, filters, likes, metadata, analysis coverage, CLAP text search, and seed search to find tracks that match a sound you have in mind.

This is useful even when you are not building a set. The project can act like a discovery layer for hidden tracks and unusual textures in your own collection, including songs that match a specific atmosphere.

### 2. 🎯 Start from a reference track

Pick one or more tracks as seeds. The system can rank candidates around the seed using audio-space proximity and SONARA compatibility. Hybrid profiles remain available for diagnostic previews.

This is useful when you have a track that feels special but you do not know what should come after it.

### 3. 🌊 Build a gradual flow

Smart Set Builder can create a read-only ordered preview from manual seeds or automatic anchors.

The goal is to create a flow that can respect:

- similarity;
- diversity;
- energy curve;
- BPM direction;
- broad sonic coherence;
- transition confidence;
- classifier preferences;
- artist pressure;
- user-selected set mode.

### 4. 💬 Search by text

After CLAP audio embeddings exist, the CLAP tab can search your library from text prompts such as:

```text
dark hypnotic techno, rolling bass, low light, late night tension
```

CLAP text-search scores are not the same scale as seed-based audio-to-audio scores. Good text results can have lower raw scores. Treat them as prompt evidence, not as a universal similarity value.

### 5. 🧪 Train personal classifiers

Rhythm Lab is a separate local app for turning your own listening decisions into optional classifier scores. The main UI can launch or reuse Rhythm Lab at `127.0.0.1:8777`, and it can save the current set as a Rhythm Lab review collection.

The normal loop is:

1. Label examples in Rhythm Lab.
2. Train and review benchmark output for the active profile.
3. Promote one trained artifact into `models/classifiers/<profile>/`.
4. Run classifier scoring in the main library database.
5. Use CLASS, SET, or Hybrid preview with the promoted scores.

Classifier scoring is database-only. It reads existing SONARA features plus stored MERT and MAEST embeddings, then writes scores for the selected classifier key. It does not decode or retag source audio.

Manual commands are available when you want the CLI workflow:

```powershell
python tools/rhythm-lab/rhythm_lab_cli.py serve --source ./data/library.sqlite --labels tools/rhythm-lab/data/rhythm_lab.sqlite
python tools/rhythm-lab/rhythm_lab_cli.py train --profile live_instrumentation --source ./data/library.sqlite --labels tools/rhythm-lab/data/rhythm_lab.sqlite
python tools/rhythm-lab/rhythm_lab_cli.py promote --profile live_instrumentation --labels tools/rhythm-lab/data/rhythm_lab.sqlite
dj-sim analyze-classifier live_instrumentation --db ./data/library.sqlite
```

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

Start the web UI:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db ./data/library.sqlite
```

Open:

```text
http://127.0.0.1:8765/
```

There is also a Windows launcher that activates `.venv` and forwards remaining arguments to `dj-sim serve`:

```powershell
run_server.cmd local --db C:/db/abstracted.sqlite
run_server.cmd lan --db C:/db/abstracted.sqlite
```

`local` binds to `127.0.0.1`. `lan` binds to `0.0.0.0` and prints a LAN URL.

## 🧠 Add model-backed analysis

The base install is enough for scan, browse, UI serving, existing SQLite data, and set export. Install optional analysis dependencies when you want the model jobs:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Run a small first pass:

```powershell
dj-sim analyze --models sonara,maest,mert,muq,clap --limit 25 --db ./data/library.sqlite
```

Useful options from the current CLI and API are:

- `--models sonara,maest,mert,muq,clap`
- `--device auto|cpu|cuda`
- `--top-k 1..10` for MAEST labels
- `--track-batch-size 1..64`
- `--inference-batch-size 1..128`
- `--diagnostics` to write decoder and batch timing details to the file log

MuQ uses the optional `ml` dependencies and official `OpenMuQ/MuQ-large-msd-iter` weights. The app feeds MuQ only 24 kHz `float32` audio and supports CPU or CUDA. CUDA is recommended for full-library runs. In this release, MuQ only stores embeddings and analysis status.

In the CLI, omit `--limit` to analyze the whole library. In the UI, `Analyze limit = 0` means the whole library.

## 🖥️ Main UI surfaces

The browser UI is split into three working areas:

1. **Database and analysis**: choose a SQLite database, choose a music folder, scan, refresh tags, run analysis, reset analysis results, write MAEST genres, and clear the database.
2. **Library browser**: use paginated search and row actions for metadata, preview, likes, seeds, and current-set changes.
3. **Search and set preparation**: use SET, SONARA, MERT, CLAP, CLASS, Hybrid preview, playlist export, and Rhythm Lab collection save.

The search panel uses these tabs:

- **SET** builds a read-only ordered set preview. Manual mode uses selected seeds. Auto mode chooses anchors from feature-complete tracks.
- **SONARA** searches from seed tracks with feature mixer and modifier controls.
- **MERT** searches from selected seeds in the MERT embedding space.
- **CLAP** searches from text prompts against stored CLAP audio embeddings.
- **CLASS** filters and rescans promoted local classifier profiles.

## 🛠️ Maintenance tools

- **Audio Doctor** checks audio metadata/container issues. It is dry-run-first. Apply mode requires exact `APPLY REPAIR` and existing dry-run state. See [Audio Doctor](docs/dj-track-similarity/tools-and-scripts/audio-doctor.md).
- **Audio Dedup** reports duplicate candidates from stored analysis data. Apply mode requires exact `APPLY DELETE` and deletes only safe candidates inside the selected root. See [Audio Dedup](docs/dj-track-similarity/tools-and-scripts/audio-dedup.md).
- **Persistent ANN indexes** are optional generated sidecars for repeated vector lookup. Missing or stale indexes fall back to exact search where supported. See [Persistent ANN indexes](docs/dj-track-similarity/tools-and-scripts/persistent-ann-indexes.md).
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

- [Project guide](docs/dj-track-similarity/project-guide.md)
- [Project idea](docs/dj-track-similarity/concepts/project-idea.md)
- [Quickstart](docs/dj-track-similarity/getting-started/quickstart.md)
- [Install](docs/dj-track-similarity/getting-started/install.md)
- [First library](docs/dj-track-similarity/getting-started/first-library.md)
- [First analysis](docs/dj-track-similarity/getting-started/first-analysis.md)
- [Browse library](docs/dj-track-similarity/user-guide/browse-library.md)
- [Search with seeds](docs/dj-track-similarity/user-guide/search-with-seeds.md)
- [Smart Set Builder](docs/dj-track-similarity/user-guide/smart-set-builder.md)
- [Text search](docs/dj-track-similarity/user-guide/text-search.md)
- [Local-first safety](docs/dj-track-similarity/concepts/local-first-safety.md)
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

# Quickstart: scan, analyze, search

You have a music folder and no database yet. By the end of this page you will have a running backend,
25 analyzed tracks, and a first shortlist to listen to.

Keep this first batch small. It proves the setup works before you spend hours analyzing everything,
and it lets you hear what each search surface actually returns.

Run these commands from the repository root. `dj-sim` in them means the project environment:
`run_server.cmd` activates `.venv` itself, and `uv run` reaches it for a single command, as in
`uv run dj-sim scan ...`.

## Before you open the browser

The browser UI mixes Russian and English labels. Every control named on this page is given by its
English name, so use the [UI language glossary](../help/ui-language.md) to match a name to the
string on screen.

## 1. Install the project

```powershell
uv sync --locked --extra dev
```

`uv sync` reads `.python-version`, downloads that CPython build when the machine does not already
have it, and builds `.venv` in the repository root from `uv.lock`.

That covers scanning, serving the backend API, exporting, database operations, and reading SQLite
analysis data you already have. New analysis jobs need the optional extras:

```powershell
uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev
```

The `sonara` extra resolves to a patched local wheel rather than to a package index. On a machine
without that wheel, read [Install](./install.md) before running this.

The `ml` extra resolves through `[tool.uv.sources]` too. On Windows AMD64 with Python 3.10, `uv`
picks the PyTorch packages from the CUDA 13.0 index.

## 2. Create a database and scan

```powershell
mkdir data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Scan walks the folder recursively and reads these audio extensions through Mutagen:

```text
.aac .aif .aiff .alac .ape .flac .m4a .mp3 .ogg .opus .wav .wave .wma .wv
```

You now have a catalog of paths and tags, which is enough to browse in the UI. The app still has no
idea how any of it sounds. Scanning writes SQLite rows and leaves your audio files untouched.

## 3. Analyze a first batch

Install the analysis extras if you skipped them, then run a small batch:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --limit 25 --db .\data\library.sqlite
```

SONARA has to run before the ML families. A job that requests ML models while no track carries a
current SONARA row is refused at creation time, and the browser keeps the ML checkboxes disabled
until at least one SONARA row exists.

A small limit confirms the model stack before you analyze every track. What each family gives you:

- SONARA makes feature-guided search and transition evidence available.
- MERT gives you a direct "find tracks near this track" search.
- MAEST, MuQ, and CLAP add evidence for LAB comparison, Audio Dedup, and classifiers.
- CLAP and MuQ-MuLan enable text search in their own embedding spaces.
- MuQ-MuLan also enables its seed-search view. It stores separate 512D L2-normalized embeddings
  and does not transform MuQ vectors.

Each job loads its models before it reads the first track and reports that as a warm-up phase. On a
new machine that phase also downloads the model weights, so the first run pauses there before the
track counter moves. See [Model warm-up](../reference/analysis-families.md#model-warm-up).

Omit `--limit` in the CLI to take the whole library. In the browser, the shared **Track limit**
stepper at `0` means the same whole-eligible-library thing, applied separately to each stage. It also
caps a scan when the DATABASE stage card is checked instead of SONARA or an ML model.

## 4. Start the app

Start the backend plus the live Vite UI:

```powershell
run_server.cmd
```

The first prompt scans `database\` under the repository root. If it finds one or more `.sqlite`
databases there, it lists them by filename and asks which one to open, defaulting to
`volumes.sqlite` when present or the first one listed otherwise; type a list number to pick one, or
any path to open or create a database elsewhere. If `database\` has none yet, it falls back to
suggesting `database\volumes.sqlite`, and Enter creates that path. The next prompt selects
local-only or LAN mode. Use the printed `5173` UI URL while you develop, so frontend source changes
appear without rebuilding `frontend/dist`.

To skip the prompts, run `run_server.cmd local --db .\database\volumes.sqlite`. Swap `local` for
`lan` only when you want other devices on your local network to reach the server. Explicit mode
commands use only the arguments you pass. The server keeps its terminal busy, so run later CLI jobs
in a second terminal.

To stop that launcher-managed session cleanly, use the power button in the top bar, titled **Stop
every server and close the tab**. It asks the backend to shut down, attempts managed Rhythm Lab
cleanup first, then lets the launcher stop its Vite dev child after the backend exits. The UI also
asks the browser to close the tab. If that is blocked, a fallback page saying that the servers have
stopped confirms that the tab can be closed manually.

Without `--db`, the server starts with no database selected and creates no SQLite files. Pick an
existing compatible library SQLite file in the database picker, or give it a new `.sqlite` path to
create one library database in the current schema.

## 5. Check the backend and browser

In a second PowerShell terminal, read the library summary and the first 25 track rows:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

For a first text shortlist, use the CLI once the chosen family has been analyzed:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, hazy pads" --model mulan --limit 20 --db .\data\library.sqlite
```

Write prompts as positive descriptions of what you want to hear. The text encoders do not model
negation, so `no vocals` searches for vocals. Name the unwanted sound in the `Negative` field of the
`PROMPT` tab instead. See [Text search](../user-guide/text-search.md).

Seed search, SONARA search, Current Set, and export are available in the browser and through the
backend endpoints documented in the [API reference](../reference/api.md).

## Your first pass in the browser

1. In panel 1, database and analysis, confirm the SQLite path in the read-only field at the top. The
   music folder is chosen later, inside the import dialog.
2. In panel 2, library and listening, search or use `Prev`, `Next`, and the page-number field to
   move through fixed pages of up to `200` tracks.
3. Add one to five tracks as seeds from the row actions.
4. In panel 3, search and listening, open the `SIMILARITY` tab and pick `MAEST`, `MERT`, `MuQ`, or
   `MuQ-MuLan` in its `Model` select, or open `SONARA` when you want to steer the search by rhythm,
   sound, dynamics, harmony, or tempo.
5. Preview candidates by ear and add the useful rows to the current set.
6. Review or remove entries in the current set.
7. Export the set as M3U or CSV once it has earned it.

With no seed in mind, press **Add Random Track** in the `SONARA` or `SIMILARITY` tab. It pulls one
eligible track from the library and uses it as the seed.

The loop stays listening-led. Start from an idea, get a shortlist, play it, keep what survives.

## If something fails

- A missing shared FFmpeg runtime blocks server startup and TorchCodec audio decoding. An
  `ffmpeg.exe` file on its own does not satisfy this requirement. See [Troubleshooting](../help/troubleshooting.md).
- Empty search results usually mean the analysis family that search depends on has not run yet. See
  [First analysis](./first-analysis.md).
- Text search needs stored CLAP or MuQ-MuLan audio embeddings for the selected model. Run that
  analysis first.
- Greyed-out ML checkboxes mean the library has no SONARA row yet. Run SONARA first.

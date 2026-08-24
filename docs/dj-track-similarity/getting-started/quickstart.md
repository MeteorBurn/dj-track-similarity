# Quickstart: scan, analyze, search

You have a music folder and no database yet. By the end of this page you will have a running backend,
25 analyzed tracks, and a first shortlist to listen to.

Keep this first batch small. It proves the setup works before you spend hours analyzing everything,
and it lets you hear what each search surface actually returns.

These commands assume the Python environment is active.

## 1. Install the base package

```powershell
python -m pip install -e ".[dev]"
```

That covers scanning, serving the backend API, exporting, database operations, and reading SQLite
analysis data you already have. New analysis jobs need the optional extras:

```powershell
uv sync --locked --extra sonara --extra ml --extra dev
```

Use `uv` for anything involving the `ml` extra, because `pip` ignores `[tool.uv.sources]`. On
Windows AMD64 with Python 3.10, `uv` picks the PyTorch packages from the CUDA 13.0 index.

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

A small limit confirms the model stack before you analyze every track. What each family gives you:

- SONARA makes feature-guided search and transition evidence available.
- MERT gives you a direct "find tracks near this track" search.
- MAEST, MuQ, and CLAP add evidence for LAB comparison, Audio Dedup, and classifiers.
- CLAP and MuQ-MuLan enable text search in their own embedding spaces.
- MuQ-MuLan also enables its seed-search view. It stores separate 512D L2-normalized embeddings
  and does not transform MuQ vectors. Existing Audio Dedup weights remain unchanged.

Omit `--limit` in the CLI to take the whole library. In the browser, **Analyze limit** `0` means the
same whole-eligible-library thing.

## 4. Start the app

Start the backend plus the live Vite UI:

```powershell
run_server.cmd
```

The first prompt suggests `database\volumes.sqlite` under the repository root. Press Enter to accept
it or type another database path. The next prompt selects local-only or LAN mode. Use the printed
`5173` UI URL while you develop, so frontend source changes appear without rebuilding
`frontend/dist`.

To skip the prompts, run `run_server.cmd local --db .\database\volumes.sqlite`. Swap `local` for
`lan` only when you want other devices on your local network to reach the server. Explicit mode
commands use only the arguments you pass. The server keeps its terminal busy, so run later CLI jobs
in a second activated terminal.

Without `--db`, the server starts with no database selected and creates no SQLite files. Pick an
existing compatible library SQLite file in the database picker, or give it a new `.sqlite` path to
create one library database in the current schema.

Open the printed live UI URL. The browser reads the current typed database, track, analysis, search,
set, classifier, Lab, and exact-identity mutation responses.

## 5. Check the backend and browser

In a second PowerShell terminal, read the library summary and the first 25 track rows:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

For a first text shortlist, use the CLI once the chosen family has been analyzed:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --model mulan --limit 20 --db .\data\library.sqlite
```

Seed search, SONARA search, Current Set, and export are available in the browser and through the
backend endpoints documented in the [API reference](../reference/api.md).

## Your first pass in the browser

1. In **Database and analysis**, confirm the SQLite path and music root.
2. In **Library**, search or use **Prev**, **Next**, and the page-number field to move through fixed
   pages of up to `200` tracks.
3. Add one to five tracks as seeds.
4. Open **MERT**, **MUQ**, or **MULAN** for an embedding neighborhood, or **SONARA** when you want to
   steer the search by rhythm, sound, dynamics, harmony, or tempo.
5. Preview candidates by ear and add the useful rows to the current set.
6. Review or remove entries in the current set.
7. Export the set as M3U or CSV once it has earned it.

The loop stays listening-led. Start from an idea, get a shortlist, play it, keep what survives.

## If something fails

- A missing shared FFmpeg runtime blocks server startup and TorchCodec audio decoding. An
  `ffmpeg.exe` file on its own does not satisfy this requirement. See [Troubleshooting](../help/troubleshooting.md).
- Empty search results usually mean the analysis family that search depends on has not run yet. See
  [First analysis](./first-analysis.md).
- Text search needs stored CLAP or MuQ-MuLan audio embeddings for the selected model. Run that
  analysis first.

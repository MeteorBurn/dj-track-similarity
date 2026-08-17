# Quickstart: scan, analyze, search

> Audience: New users who want one working pass before reading details.
> Goal: Create a database, start the backend, and make the first useful search.
> Type: tutorial

The commands below create a local catalog and analyze 25 tracks so the active backend has real
search data. Keep this first batch small while you verify setup and compare search surfaces.

At the end, choose a familiar track and listen to the candidates the app places near it. That first
shortlist is the useful result of the quickstart.

These commands assume the Python environment is active.

## 1. Install the base package

```powershell
python -m pip install -e ".[dev]"
```

The base install supports scanning, backend API serving, exporting, database operations, and
existing SQLite analysis data. For new analysis jobs, install the optional extras later:

```powershell
uv sync --locked --extra sonara --extra ml --extra dev
```

Use `uv` for installs containing the `ml` extra because `pip` does not apply `[tool.uv.sources]`.
On Windows AMD64 with Python 3.10, `uv` selects the PyTorch packages from the CUDA 13.0 index.

## 2. Create a database and scan

```powershell
mkdir data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Scan walks the folder recursively and reads supported audio extensions through Mutagen:

```text
.aac .aif .aiff .alac .ape .flac .m4a .mp3 .ogg .opus .wav .wave .wma .wv
```

The scan creates a local catalog from paths and tags. It gives the UI something to browse, but it
does not yet understand how the tracks sound. The scan writes SQLite rows and does not modify audio
files.

## 3. Analyze a first batch

Install analysis extras first if you have not done so. Then run a small batch:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,mulan,clap --limit 25 --db .\data\library.sqlite
```

A small limit confirms the model stack before you analyze every track. It also lets you hear what
each search approach returns before spending time on full-library analysis.

- SONARA makes feature-guided search and transition evidence available.
- MERT gives you a direct "find tracks near this track" search.
- MAEST, MuQ, and CLAP add evidence for LAB comparison, Audio Dedup, and classifiers.
- CLAP and MuQ-MuLan enable text search in their own embedding spaces.
- MuQ-MuLan also enables its seed-search view. It stores separate 512D L2-normalized embeddings
  and does not transform MuQ vectors. Existing Audio Dedup weights remain unchanged.

In the CLI, omit `--limit` for the whole library. In the browser, **Analyze limit** `0` has the same
whole-eligible-library meaning.

## 4. Start the app

Start the backend plus live Vite UI:

```powershell
run_server.cmd
```

The first prompt suggests `database\volumes.sqlite` under the repository root. Press Enter to accept
it or type another database path. The next prompt selects local-only or LAN mode. The launcher starts
the backend plus the Vite live UI. Use the printed `5173` UI URL during development so frontend
source changes appear without rebuilding `frontend/dist`.

For a non-interactive launch, use `run_server.cmd local --db .\database\volumes.sqlite`. Replace
`local` with `lan` only when you want the server reachable from other devices on the local network.
Explicit mode commands use only the arguments you provide. The server command keeps its terminal
occupied. Run later CLI jobs in a second activated terminal.

Without `--db`, the server starts with no selected database and creates no SQLite files. Use the
database picker to select an existing compatible bundle or choose a new `.sqlite` path. Selecting
a new path creates one library database in the current schema.

Open the printed live UI URL. The browser uses the current typed database, track, analysis, search,
set, classifier, Lab, and exact-identity mutation responses.

## 5. Check the backend and browser

In a second PowerShell terminal, read the library summary and the first 25 track rows:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

For a first text shortlist, use the CLI after analysis for the chosen family:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --model mulan --limit 20 --db .\data\library.sqlite
```

Seed search, SONARA search, Current Set, and export are available in the browser and through the backend
endpoints documented in the [API reference](../reference/api.md).

## First browser flow

1. In **Database and analysis**, confirm the SQLite path and music root.
2. In **Library**, search or use **Prev**, **Next**, and the page-number field to browse fixed
   pages of up to `200` tracks.
3. Add one to five tracks as seeds.
4. Open **MERT**, **MUQ**, or **MULAN** for an embedding neighborhood, or **SONARA** when you want to steer the
   search by rhythm, sound, dynamics, harmony, or tempo.
5. Preview candidates by ear and add useful rows to the current set.
6. Review or remove entries in the current set.
7. Export the set as M3U or CSV when it is useful.

This remains a listening-led loop: start from an idea, get a shortlist, listen, keep the useful
tracks, and export only when the list has earned it.

## If something fails

- A missing shared FFmpeg runtime blocks server startup and TorchCodec audio decoding. An
  `ffmpeg.exe` file alone does not satisfy this requirement. See [Troubleshooting](../help/troubleshooting.md).
- Empty search usually means the needed analysis family has not been run. See [First analysis](./first-analysis.md).
- Text search requires stored CLAP or MuQ-MuLan audio embeddings for the selected model. Run that analysis first.

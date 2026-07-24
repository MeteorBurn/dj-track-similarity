# Quickstart: scan, analyze, search

> Audience: New users who want one working pass before reading details.
> Goal: Create a database, start the v7 backend, and make the first useful search.
> Type: tutorial

::: warning v7 frontend status
The React workflow below documents the deferred frontend. It has not been ported to the schema-v7
API, so these UI steps are not currently validated or available for v7. Use the backend CLI or API
alternative below.
:::

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
python -m pip install -e ".[sonara,ml,dev]"
```

## 2. Create a database and scan

```powershell
mkdir data
dj-sim scan D:\Music --db .\data\library.sqlite
```

Scan walks the folder recursively and reads supported audio extensions through Mutagen:

```text
.aif .aiff .alac .flac .m4a .mp3 .ogg .opus .wav .wave
```

The scan creates a local catalog from paths and tags. It gives the UI something to browse, but it
does not yet understand how the tracks sound. The scan writes SQLite rows and does not modify audio
files.

## 3. Analyze a first batch

Install analysis extras first if you have not done so. Then run a small batch:

```powershell
mkdir .\backups
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backups --confirm "PREPARE SONARA RELEASE"
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
```

Fresh v7 bundles must activate the loaded immutable SONARA release before the first SONARA job.
Preparation derives all four `core`, `timeline`, `embedding`, and `fingerprint` contracts, verifies
the Core and Artifacts backups, and records a resumable receipt.

A small limit confirms the model stack before you analyze every track. It also lets you hear what
each search approach returns before spending time on full-library analysis.

- SONARA makes feature-guided search and transition evidence available.
- MERT gives you a direct "find tracks near this track" search.
- MAEST and CLAP complete the evidence needed by SET.
- CLAP also enables text search.
- MuQ is only used by LAB Reference Compare in this release. You can omit it when you only want seed
  search, SET, Hybrid, or text search.

In the CLI, omit `--limit` for the whole library. The deferred UI uses `Analyze limit = 0` for the
whole library, but that control is not currently available for v7.

## 4. Start the v7 backend API

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

Without `--db`, the server starts with no selected database and creates no SQLite files. Use the
database picker to select an existing compatible v7 bundle or choose a new `.sqlite` path. Selecting
a new path creates the Core database and its mandatory adjacent Artifacts database.

To select the database before the server starts, pass `--db .\data\library.sqlite`. An existing
compatible bundle is opened. A wholly missing bundle is created.

If you use the Windows launcher:

```powershell
run_server.cmd local
```

Use `run_server.cmd lan` only when you want the server reachable from other devices on the local
network. Both launcher modes accept `--db .\data\library.sqlite` when you want to preselect a
database. The server command keeps its terminal occupied. Run later CLI jobs in a second activated
terminal.

Do not treat the page served at `http://127.0.0.1:8765/` as a validated v7 frontend. The active
surface is the backend API.

## 5. Check the current v7 backend

In a second PowerShell terminal, read the library summary and the first 25 track rows:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

For a first text shortlist, use the CLI after CLAP analysis:

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 20 --db .\data\library.sqlite
```

Seed search, SONARA search, SET, and export are available through the current backend endpoints
documented in the [API reference](../reference/api.md).

## Deferred frontend flow

1. In **Database and analysis**, confirm the SQLite path and music root.
2. In **Library**, search or page to a track.
3. Add one to five tracks as seeds.
4. Open **MERT** for a broad audio neighborhood or **SONARA** when you want to steer the search by
   rhythm, sound, dynamics, harmony, or tempo.
5. Open **SET** to generate an ordered preview.
6. Preview candidates by ear before adding them to the current set.
7. Export the set as M3U or CSV when it is useful.

After the React port, this flow is intended to provide the same listening-led loop: start from an
idea, get a shortlist, listen, keep the useful tracks, and export only when the list has earned it.

## If something fails

- Missing FFmpeg blocks server startup and ffmpeg-backed audio decoding. See [Troubleshooting](../help/troubleshooting.md).
- Empty search usually means the needed analysis family has not been run. See [First analysis](./first-analysis.md).
- CLAP text search requires stored CLAP audio embeddings. Run CLAP analysis first.

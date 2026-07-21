# Quickstart: scan, analyze, search

> Audience: New users who want one working pass before reading details.
> Goal: Create a database, open the UI, and make the first useful search.
> Type: tutorial

The commands below create a local catalog and analyze 25 tracks so the browser UI has real search
results. Keep this first batch small while you verify setup and compare search surfaces.

At the end, choose a familiar track and listen to the candidates the app places near it. That first
shortlist is the useful result of the quickstart.

These commands assume the Python environment is active.

## 1. Install the base package

```powershell
python -m pip install -e ".[dev]"
```

The base install supports scanning, browsing, serving the UI, exporting, database operations, and existing SQLite analysis data. For new analysis jobs, install the optional extras later:

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
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
```

A small limit confirms the model stack before you analyze every track. It also lets you hear what
each search approach returns before spending time on full-library analysis.

- SONARA makes feature-guided search and transition evidence available.
- MERT gives you a direct "find tracks near this track" search.
- MAEST and CLAP complete the evidence needed by SET.
- CLAP also enables text search.
- MuQ is only used by LAB Reference Compare in this release. You can omit it when you only want seed
  search, SET, Hybrid, or text search.

In the CLI, omit `--limit` for the whole library. In the UI, `Analyze limit = 0` means the whole
library.

## 4. Start the UI

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open:

```text
http://127.0.0.1:8765/
```

If you use the Windows launcher:

```powershell
run_server.cmd local --db .\data\library.sqlite
```

Use `run_server.cmd lan --db .\data\library.sqlite` only when you want the server reachable from other devices on the local network. The server command keeps its terminal occupied. Run later CLI jobs in a second activated terminal or use the UI analysis controls.

## 5. Try the UI flow

1. In **Database and analysis**, confirm the SQLite path and music root.
2. In **Library**, search or page to a track.
3. Add one to five tracks as seeds.
4. Open **MERT** for a broad audio neighborhood or **SONARA** when you want to steer the search by
   rhythm, sound, dynamics, harmony, or tempo.
5. Open **SET** to generate an ordered preview.
6. Preview candidates by ear before adding them to the current set.
7. Export the set as M3U or CSV when it is useful.

You now have a working loop: start from an idea, get a shortlist, listen, keep the useful tracks,
and export only when the list has earned it.

## If something fails

- Missing FFmpeg blocks server startup and ffmpeg-backed audio decoding. See [Troubleshooting](../help/troubleshooting.md).
- Empty search usually means the needed analysis family has not been run. See [First analysis](./first-analysis.md).
- CLAP text search requires stored CLAP audio embeddings. Run CLAP analysis first.

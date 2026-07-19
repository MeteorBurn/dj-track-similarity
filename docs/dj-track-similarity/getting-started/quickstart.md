# Quickstart: scan, analyze, search

> Audience: New users who want one working pass before reading details.
> Goal: Create a database, open the UI, and make the first useful search.
> Type: tutorial

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

The scan writes SQLite rows. It does not modify audio files.

## 3. Analyze a first batch

Install analysis extras first if you have not done so. Then run a small batch:

```powershell
dj-sim analyze --models sonara,maest,mert,muq,clap --limit 25 --db .\data\library.sqlite
```

A small limit confirms the model stack before you analyze every track. MuQ is only used by LAB Reference Compare in this release, so you can omit `muq` when you only want seed search, SET, Hybrid, or text search. In the CLI, omit `--limit` for the whole library. In the UI, `Analyze limit = 0` means the whole library.

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
4. Open **MERT** for seed embedding search or **SONARA** for feature search.
5. Open **SET** to generate an ordered preview.
6. Preview candidates by ear before adding them to the current set.
7. Export the set as M3U or CSV when it is useful.

## If something fails

- Missing FFmpeg blocks server startup and ffmpeg-backed audio decoding. See [Troubleshooting](../help/troubleshooting.md).
- Empty search usually means the needed analysis family has not been run. See [First analysis](./first-analysis.md).
- CLAP text search requires stored CLAP audio embeddings. Run CLAP analysis first.

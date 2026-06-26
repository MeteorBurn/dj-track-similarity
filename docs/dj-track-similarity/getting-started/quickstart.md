# Quickstart: open your first local library

Audience: new users  
Goal: install the app, scan audio, and open the browser UI  
Type: tutorial

This tutorial gets you to the first useful result: the web UI shows tracks from
a local folder. It uses the base install first. Model analysis can come later.

## Requirements

- Python 3.10 or newer.
- FFmpeg on `PATH`, or `DJ_TRACK_SIMILARITY_FFMPEG` pointing to `ffmpeg.exe`.
- A small test folder of audio files you are comfortable scanning.

::: warning Safety note
Use a small folder first. Scan reads tags and writes SQLite rows. It does not
rewrite audio files, but the database can contain private track names and paths.
:::

## 1. Create and activate the environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Expected result:

```text
The shell prompt shows the environment is active, and dj-sim is available.
```

All following commands assume this environment is still active.

## 2. Check the CLI

```powershell
dj-sim --help
dj-sim doctor
```

Expected result:

```text
dj-sim prints commands such as scan, analyze, text-search, and serve.
doctor reports the local Python, FFmpeg, PyTorch, and device state.
```

## 3. Scan a small folder

Replace `<music-library>` with a test folder path.

```powershell
New-Item -ItemType Directory -Force .\data
dj-sim scan <music-library> --db .\data\library.sqlite
```

Expected result:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

This creates `.\data\library.sqlite`. The database stores file paths, tag
metadata, and later analysis state.

## 4. Start the local server

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open:

```text
http://127.0.0.1:8765/
```

Expected result:

```text
The browser shows the DJ Track Similarity UI and your scanned tracks.
```

## 5. Next step

Run a small SONARA analysis pass if you want an explainable search surface:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Then read [First analysis](first-analysis.md) before starting heavier MAEST,
MERT, CLAP, or classifier jobs.

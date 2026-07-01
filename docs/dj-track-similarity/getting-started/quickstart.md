# Quickstart: scan, analyze, search

> Audience: New users comfortable with a terminal.
> Goal: Create a local library database and run enough analysis to try the UI.
> Type: tutorial

This path creates a SQLite library, checks the audio/ML dependencies, analyzes a small first batch, and opens the browser UI. It is intentionally small: a first batch gives you something to test before you spend time analyzing the whole collection.

## 1. Install and check

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
dj-sim doctor
```

The install command adds the app plus the analysis and Rhythm Lab extras in editable mode. `dj-sim doctor` checks that the command can start and that required runtime tools are visible.

Ready when: `dj-sim doctor` reports a usable environment. If it reports missing FFmpeg, put FFmpeg on `PATH` or set `DJ_TRACK_SIMILARITY_FFMPEG` before serving previews or running audio analysis. If PyTorch, Torchaudio, or TorchCodec imports fail, revisit the install page and keep the PyTorch-family packages synchronized.

## 2. Scan

```powershell
dj-sim scan <music-folder> --db .\data\library.sqlite
```

Scanning reads supported audio files, extracts human-readable tags, and stores paths plus metadata in the SQLite database. It does not analyze audio content yet, and it does not rewrite audio files.

Ready when: the command prints added, updated, unchanged, and skipped counts, and the database file exists at the path you passed with `--db`.

## 3. Analyze a first batch

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

This fills enough SONARA features and MAEST, MERT, and CLAP results to make the search tabs useful. Use `--device auto` unless you specifically need `cpu` or verified `cuda`. Keep `--limit 25` for the first run; omit `--limit` only when you are ready to analyze the whole library from the CLI.

Ready when: the job finishes without errors and later searches show analyzed candidates. If decoding fails for particular files, run with `--diagnostics` to see decoder fallback details.

## 4. Open the UI

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open `http://127.0.0.1:8765/`, browse the library, pick seeds, and try SET, SONARA, MERT, or CLAP search.

Ready when: the page loads, the library counters match the scan, and the analyzed tracks appear in search results. If the server cannot start, check the port and the FFmpeg message first; browser audio preview also depends on FFmpeg being available.

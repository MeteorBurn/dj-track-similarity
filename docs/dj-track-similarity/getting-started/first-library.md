# Create your first library

Audience: new users  
Goal: understand scan and the first database  
Type: tutorial

A library is a SQLite database that points at your local audio files. Scan reads
file metadata with Mutagen and stores rows in SQLite. It does not rewrite the
audio files.

## Pick a safe first folder

Start with a small folder:

- a few tracks you can rescan freely;
- no private paths you plan to publish in screenshots;
- enough variety to make search results visible later.

## Scan

Activate the project environment once, then run:

```powershell
New-Item -ItemType Directory -Force .\data
dj-sim scan <music-library> --db .\data\library.sqlite
```

Expected result:

```text
added=<n> updated=<n> unchanged=<n> skipped=<n>
```

The database stores file path, size, modified time, title, artist, album, BPM,
key, duration, energy, and JSON metadata when available.

## Open it in the UI

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Open `http://127.0.0.1:8765/`.

In the UI, the library panel supports:

- text search by artist, title, genre, and path;
- LIKE and FTS search modes;
- liked-track filtering;
- seed selection;
- preview playback;
- metadata dialog with separated Mutagen tags, SONARA features, MAEST genres,
  and classifier scores.

## What scan does not do

Scan does not:

- analyze audio with SONARA, MAEST, MERT, or CLAP;
- train classifiers;
- write tags into source files;
- move, copy, or delete audio.

Run [First analysis](first-analysis.md) when the library rows are visible.

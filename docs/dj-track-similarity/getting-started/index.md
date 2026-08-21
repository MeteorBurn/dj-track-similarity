# Getting started

You are here to turn a folder of audio files into something you can actually search. The payoff is
not a fully automatic DJ set. It is a searchable map of your own music, plus a shortlist of
candidates you would probably never find by browsing folders alone.

The shortest path runs install, scan, open the UI, analyze a small batch, search, then decide by ear.
Your audio stays where it is. Scan and analysis add information to local SQLite databases without
reorganizing or rewriting the source files.

## What each step gives you

1. **Scan** turns a folder tree into a library you can browse and filter.
2. **Analysis** adds the evidence needed for sound-based search and set previews.
3. **Search** reduces a large library to a listening shortlist.
4. **Current Set or crate building** turns useful candidates into an editable working list.
5. **Export** creates an M3U or CSV file for the next part of your workflow.

## Pages

- [Quickstart](./quickstart.md): the shortest path through scan, serve, and first analysis.
- [Install](./install.md): prerequisites, package extras, FFmpeg, frontend, and docs build notes.
- [First library](./first-library.md): how scanning works and what the database stores.
- [First analysis](./first-analysis.md): choose analysis by the result you want, then configure limits and devices.

## What you need first

- A local folder of audio files.
- A local SQLite path where the app can create or open the library.
- FFmpeg `8.1.1` as a full shared build. Discovery checks
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, then a valid library directory on `PATH`.
  A bare `ffmpeg.exe` is not enough. Run `dj-sim doctor` after setup.
- Optional model dependencies if you want SONARA, MAEST, MERT, MuQ, or CLAP analysis.

## Privacy habit

Treat the SQLite database, logs, reports, generated indexes, and classifier artifacts as private library data. They can include paths, tags, model scores, and listening notes.

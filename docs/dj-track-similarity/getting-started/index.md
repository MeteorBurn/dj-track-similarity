# Getting started

You are here to turn a folder of audio files into something you can actually search. The payoff is
a searchable map of your own music, plus a shortlist of candidates you would probably never find by
browsing folders alone. No automatic DJ set comes out of it.

The shortest path runs install, scan, open the UI, analyze a small batch, search, then decide by ear.
Your audio stays where it is. Scan and analysis add information to a local SQLite database without
reorganizing or rewriting the source files.

## The UI is in Russian

Every panel heading, button title, tooltip, and notice in the browser is Russian. Only technical
tokens stay English: model names, the tab labels `LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, and
`CLASS`, mode names such as `Balanced` and `DJ transition`, and field labels such as `Limit`,
`Mode`, `Device`, and `Analyze limit`.

These pages give the Russian string first and the English meaning in parentheses, so you can find
the control on screen. The full mapping lives in [UI language](../help/ui-language.md).

## What each step gives you

1. **Scan** turns a folder tree into a library you can browse and filter.
2. **Analysis** adds the evidence behind sound-based search and preview.
3. **Search** reduces a large library to a listening shortlist.
4. **Current Set** collects useful candidates into an editable working list.
5. **Export** creates an M3U or CSV file for the next part of your workflow.

## Pages

- [Quickstart](./quickstart.md): the shortest path through install, scan, serve, and first analysis.
- [Install](./install.md): prerequisites, package extras, FFmpeg, frontend, and docs build notes.
- [First library](./first-library.md): how the scan dialog builds a catalog.
- [First analysis](./first-analysis.md): choose analysis by the result you want, then configure limits, modes, devices, and the SONARA BPM range.

## What you need first

- A local folder of audio files.
- A local SQLite path where the app can create or open the library.
- FFmpeg `8.1.1` as a full shared build. Discovery checks
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, then a valid library directory on `PATH`.
  A bare `ffmpeg.exe` is not enough. Run `dj-sim doctor` after setup.
- Optional model dependencies for SONARA, MAEST, MERT, MuQ, MuQ-MuLan, or CLAP analysis.

## Privacy habit

Treat the SQLite database, logs, reports, and promoted classifier artifacts as private library data.
They can include paths, tags, model scores, and listening notes.

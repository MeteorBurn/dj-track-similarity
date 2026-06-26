# Browse the library

Audience: UI users  
Goal: find, preview, and inspect tracks  
Type: how-to

The library panel shows lightweight paginated track rows. Full metadata loads
only when you open a track dialog.

## Select the database

Start the server with a database:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

Or use the database picker in the UI. The top bar shows summary counters for
tracks and analysis coverage.

## Search and filter

The library search field uses text such as artist, title, genre, or path. The
search mode toggle supports:

- `LIKE`: simple broad matching;
- `FTS`: full-text search through the SQLite search index.

You can also show liked tracks only, filter for the MAEST syncopated-rhythm
flag, and reverse the current page order.

## Work with rows

Track rows expose compact actions:

- preview or pause audio;
- open the metadata dialog;
- like or unlike a track;
- mark a track as a seed;
- add or remove a track from the current set.

The metadata dialog keeps sources separate: Mutagen file tags, SONARA features,
classifier scores, and MAEST genre labels are shown as different blocks. This
helps you spot disagreement instead of hiding it.

## Refresh tags

`RefreshTags` rereads file tags for already discovered tracks. It updates
SQLite metadata. It does not rewrite audio, and it does not remove SONARA,
MAEST, MERT, CLAP, or classifier analysis state.

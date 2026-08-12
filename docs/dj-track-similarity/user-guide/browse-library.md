# Browse a large library without rendering everything

> Audience: Users navigating the main web UI after scan.
> Goal: Find tracks, inspect metadata, preview audio, and build seeds or a temporary set.
> Type: guide

## Direct API equivalent

The browser uses the same current endpoints shown here. For scripting, start the backend on `127.0.0.1`
and call them directly:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/library/summary'
Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/tracks?limit=25'
```

Use `GET /api/tracks/{track_id}` for full metadata and `GET /media/{track_id}` for preview audio.
The current response shapes and filter query parameters are in the
[API reference](../reference/api.md).

## Loading behavior

The library panel uses fixed server-side pages of up to `200` tracks. **Prev**, **Next**, and the
page-number field request one `/api/tracks` page at a time. All returned rows render in one
scrollable list. There is no second row-window paginator.

Database changes and newer loads invalidate older responses. Duplicate rows are reconciled by
their stable `catalog_uuid` and `track_uuid` identity.

## Main controls

The library browser supports:

- Text search over artist, title, album, path, genres, and other indexed fields.
- Search mode selection between `like` and `fts`.
- A syncopated rhythm preset when MAEST syncopated rhythm data exists.
- Liked-only filtering.
- Classifier minimum-score filters when promoted classifier scores exist.
- Sort direction toggle.
- **Prev**, **Next**, and page-number navigation for fixed pages of up to `200` tracks.

The API caps each request at `1..500`. The UI keeps rows light and opens full metadata only on
demand.

## Metadata dialog

Open track details when you need the full metadata payload. The dialog separates:

- file tags read through Mutagen,
- SONARA features,
- MAEST genres,
- classifier scores.

The Mutagen section shows primary file facts such as title, length, format, size, and path. It also
shows stored genre, BPM, key, and comment tags when those fields are present. Use the copy button next
to the path when you need the local file location.

Keep those sources separate when judging a track. A MAEST label and a file tag are not the same evidence.

## Preview

The `/media/{track_id}` endpoint streams the local file when the browser can play it. AIFF, FLAC, DSD/DSF, WMA, APE, WV, M4B/M4R, TAK, TTA, and browser-unsafe WAV files are transcoded to a temporary 16-bit WAV for streaming, then the temporary file is deleted. The source audio file is not rewritten.

If the file is missing, preview returns an error instead of hiding the problem.

## Likes

The like button writes a local SQLite row with `catalog_uuid` and `track_uuid`. It does not edit audio tags. Likes can be used for browsing and
filtering.

## Seeds and the current set

From each visible result row you can:

- add or remove a seed track,
- add or remove the track from the current set,
- start or stop preview,
- open metadata,
- toggle liked state.

Seeds feed MERT, MuQ, SONARA, and LAB Reference Compare. The current set is the
temporary playlist shown in the right panel. It is not written to disk until you export it or save
it as a Rhythm Lab collection.

## Add visible tracks

The UI can add all currently filtered tracks to the current set. It reads the full filtered result
from the server in bounded chunks and appends tracks that are not already in the set.

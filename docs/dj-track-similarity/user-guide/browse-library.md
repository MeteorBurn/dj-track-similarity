# Browse the library without loading everything

> Audience: Users navigating the main web UI after scan.
> Goal: Find tracks, inspect metadata, preview audio, and build seeds or a temporary set.
> Type: guide

The library panel reads `/api/tracks` with server-side pagination. It does not load the entire SQLite library into the browser.

## Main controls

The library browser supports:

- Text search over artist, title, album, path, genres, and other indexed fields.
- Search mode selection between `like` and FTS where the UI exposes it.
- A syncopated rhythm preset when MAEST syncopated rhythm data exists.
- Liked-only filtering.
- Classifier minimum-score filters when promoted classifier scores exist.
- Sort direction toggle.
- Previous, next, and page jump controls.

The API caps page size at `1..500`. The UI keeps rows light and opens full metadata only on demand.

## Metadata dialog

Open track details when you need the full metadata payload. The dialog separates:

- file tags read through Mutagen,
- SONARA features,
- MAEST genres,
- classifier scores.

Keep those sources separate when judging a track. A MAEST label and a file tag are not the same evidence.

## Preview

The `/media/{track_id}` endpoint streams the local file when the browser can play it. AIFF, FLAC, DSD/DSF, WMA, APE, WV, M4B/M4R, TAK, TTA, and browser-unsafe WAV files are transcoded to a temporary 16-bit WAV for streaming, then the temporary file is deleted. The source audio file is not rewritten.

If the file is missing, preview returns an error instead of hiding the problem.

## Likes

The like button writes a local SQLite row. It does not edit audio tags. Likes can be used for browsing and filtering.

## Seeds and the current set

From each visible result row you can:

- add or remove a seed track,
- add or remove the track from the current set,
- start or stop preview,
- open metadata,
- toggle liked state.

Seeds feed MERT, SONARA, SET, and Hybrid preview. The current set is the temporary playlist shown in the right panel. It is not written to disk until you export it.

## Add visible tracks

The UI can add all currently filtered tracks to the current set. This reads the filtered result list from the server and appends tracks that are not already in the set.

# Export a playlist preview

> Audience: Users who built a temporary set and want a file outside the app.
> Goal: Export M3U or CSV and understand what is written.
> Type: guide

## Direct API

Call `POST /api/export` with `name`, `track_ids`, `output_dir`, and `format`. The format must be
`m3u` or `csv`; the response returns the created `path`. Direct clients select track IDs explicitly.
The browser does the same when it sends its temporary current set. See the
[API reference](../reference/api.md).

The current set in the UI stays temporary until export, and search results or SET previews change it only when you explicitly add tracks.

## UI flow

**Set and export** is collapsed by default so candidate results keep more vertical space. Adding a
track updates the visible set count without opening the disclosure. Expand it whenever you want to
review the temporary set. The expanded block shows 20 tracks per page with **Prev** and **Next**
navigation, and its current page scrolls inside the block.

1. Add tracks to the current set from library rows, search results, SET preview, or another UI action.
2. Expand **Set and export**.
3. Set the playlist name.
4. Choose or type an output directory.
5. Click the M3U or CSV export button.

The output directory is created if it does not exist.

## File names

The exporter turns the playlist name into a safe file name by keeping letters, numbers, `.`, `_`, and `-`, replacing other runs with `_`, and using `playlist` when the name is empty after cleanup.

## M3U output

M3U files contain:

- `#EXTM3U`,
- one `#EXTINF:-1,Artist - Title` line per track when artist and title exist,
- the stored local path for each track.

## CSV output

CSV files contain these columns:

```text
artist,title,bpm,key,energy,path
```

## Save to Rhythm Lab collection

The UI can also save the current set into a Rhythm Lab collection. Each item carries
`catalog_uuid`, `track_uuid`, and `content_generation`. This writes to the Rhythm Lab labels
database, not to the source audio files.

## Privacy

Exports contain local file paths and may reveal collection structure. Treat exported M3U and CSV files as private unless you intentionally sanitize them.

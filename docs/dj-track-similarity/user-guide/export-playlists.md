# Export a playlist preview

> Audience: Users who built a temporary set and want a file outside the app.
> Goal: Export M3U or CSV and understand what is written.
> Type: guide

The current set in the UI stays temporary until export, and search results or SET previews change it only when you explicitly add tracks.

## UI flow

1. Add tracks to the current set from library rows, search results, SET preview, or another UI action.
2. Set the playlist name.
3. Choose or type an output directory.
4. Click the M3U or CSV export button.

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

The UI can also save the current set into a Rhythm Lab collection. This writes to the Rhythm Lab labels database, not to the source audio files.

## Privacy

Exports contain local file paths and may reveal collection structure. Treat exported M3U and CSV files as private unless you intentionally sanitize them.

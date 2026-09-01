# Export a playlist preview

Once a set is worth keeping, export it as a file your player or your notes can use. This page covers
what M3U and CSV export actually write.

Control names below are given in English. The full mapping to the on-screen strings is in
[UI language](../help/ui-language.md).

## Direct API

Call `POST /api/export` with `name`, `track_ids`, `output_dir`, and `format`. The format must be
`m3u` or `csv`, and the response returns the created `path`. Direct clients select track IDs
explicitly. The browser does the same when it sends its temporary current set. See the
[API reference](../reference/api.md).

The current set in the UI stays temporary until export, and library or search rows change it only
when you explicitly add tracks.

## UI flow

**Set and export** sits at the bottom of panel 3, search and listening, and is collapsed by default,
so candidate results keep more vertical space. Adding a track updates the visible count without
opening the disclosure. Expand it whenever you want to review the temporary set.

1. Add tracks to the current set from library or search rows, with the plus icon titled **Add to the
   set**. Adding every loaded row of a library page at once is a separate button in panel 2.
2. Expand **Set and export**.
3. Set the playlist name. The field starts at `seamless-set` and doubles as the export file name.
4. Choose or type an output directory. The field carries the placeholder `D:/Exports`, and the
   folder icon beside it is titled **Choose the export folder**.
5. Press `M3U` or `CSV`.

A non-empty set shows a note that export saves the current set, while an empty one says the set is
empty and leaves all three export buttons disabled. Leaving the output directory blank is refused
with a message asking for an export folder. The output directory is created if it does not exist.

Above 20 entries the block paginates. `Prev` and `Next` move between pages of 20, with a status
reading the shown range out of the total, and the current page scrolls inside the block.

Each set row carries a preview button, the tag dialog, and a trash icon titled **Remove from the
set**. There is no clear-all button. The set empties one row at a time, or when you switch or clear
the database.

## File names

The exporter turns the playlist name into a safe file name by keeping letters, numbers, `.`, `_`,
and `-`, replacing other runs with `_`, and using `playlist` when the name is empty after cleanup.

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

The third button, `Collection`, saves the current set into a Rhythm Lab collection. It asks for a
name through a native browser prompt titled `Rhythm Lab collection name`, defaulting to the playlist
name or to `Collection <YYYY-MM-DD>`.

Each item carries `catalog_uuid` and `track_uuid`. This writes to the Rhythm Lab labels database,
not to the source audio files. See [Rhythm Lab](../tools-and-scripts/rhythm-lab.md).

## Privacy

Exports contain local file paths and may reveal collection structure. Treat exported M3U and CSV
files as private unless you intentionally sanitize them.

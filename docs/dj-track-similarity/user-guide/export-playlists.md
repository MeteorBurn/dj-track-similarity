# Export a playlist preview

> Audience: Users ready to take a shortlist into another tool.
> Goal: Export selected tracks as M3U or CSV without changing audio files.
> Type: how-to

## UI flow

Add candidates from search or SET preview to the current set, review the order, choose M3U or CSV, then choose an output folder.

## API

The UI calls `/api/export` with a name, track IDs, output directory, and format `m3u` or `csv`.

## Privacy

CSV and M3U exports can include local paths. Do not publish them if they reveal private collection structure.

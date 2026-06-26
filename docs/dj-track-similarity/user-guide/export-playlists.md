# Export playlists

Audience: UI users  
Goal: write a reviewed temporary set to disk  
Type: how-to

Export writes playlist or report files from the current set. It does not
rewrite audio files.

## Build a current set

Add tracks from:

- library rows;
- seed-search results;
- a Smart Set Builder preview.

Review the order before exporting.

## Export formats

The API supports:

- `m3u`;
- `csv`.

Choose an output directory that is safe to write. Avoid committing generated
exports if they contain private library paths.

## What export stores

Export stores a file that points at selected tracks. It does not:

- write tags;
- move audio;
- delete audio;
- change analysis state.

# Browse the library without loading everything

> Audience: UI users with a scanned library.
> Goal: Find tracks, inspect metadata, and preview audio safely.
> Type: how-to

## List behavior

The library is server-side paginated. Search by artist, title, genre, or path; use liked and classifier filters to narrow crates.

## Metadata dialog

The dialog keeps Mutagen tags, SONARA features, MAEST genres, and classifier scores in separate blocks so sources stay clear.

## Preview

Browser preview streams through `/media/{track_id}`. AIFF may be transcoded to WAV for playback, but source files are not rewritten or cached.

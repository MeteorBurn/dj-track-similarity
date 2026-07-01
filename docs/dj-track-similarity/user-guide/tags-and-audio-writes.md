# Know when audio files can be written

> Audience: Users deciding whether to run tag or repair actions.
> Goal: Separate read-only workflows from explicit audio writes and deletes.
> Type: how-to

## Read-only by default

Scan, Refresh Tags, analysis, search, previews, export, reset, clear, and relocation preview read files or write SQLite/reports only.

## Genre tag apply

`/api/tags/genres/apply` and genre tag jobs write stored MAEST genres to the standard genre field while preserving title, artist, album, BPM, key, and other normal tags.

## Tag fields

MP3/WAV/AIFF ID3 use `TCON`; FLAC/Vorbis-style tags use `GENRE`; MP4/M4A/ALAC use `©gen`. WAV uses Mutagen WAVE/ID3 and reads back `TCON`.

## Other explicit exceptions

Audio repair `--apply` can rewrite repairable files. Audio Dedup apply/delete can delete duplicate candidates after exact confirmation.

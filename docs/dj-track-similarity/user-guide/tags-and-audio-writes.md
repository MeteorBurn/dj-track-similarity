# Tags and audio writes

Audience: careful users and power users  
Goal: understand the explicit tag-writing exception  
Type: how-to

Most app workflows are read-only toward source audio. Genre tag writing is the
intentional exception: it can write stored MAEST genre labels into standard
audio genre tags.

## What can write tags

The explicit app path is:

```text
POST /api/tags/genres/apply
```

or the matching UI job.

It writes only the standard genre field from stored MAEST labels. It should
preserve title, artist, album, BPM, key, and other normal tags.

## Formats

The tag-writing code uses standard fields:

- `TCON` for MP3/WAV/AIFF ID3;
- `GENRE` for FLAC/Vorbis-style tags;
- `©gen` for MP4/M4A/ALAC.

## Batch behavior

Failed writes should fail that track and let the batch continue. For WAV, the
app uses Mutagen WAVE/ID3 handling and reads back `TCON`; it does not add custom
RIFF repair logic to the tag-writing path.

## Before writing tags

Make sure:

- MAEST labels are present and worth writing;
- you have backups if the files matter;
- you understand this is not the same workflow as search, analysis, preview, or
  export.

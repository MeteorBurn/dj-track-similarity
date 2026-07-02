# FAQ

> Audience: Users who want short answers.
> Goal: Answer common questions with current behavior.
> Type: help

## Does analysis change audio files?

No. SONARA, MAEST, MERT, CLAP, and classifier scoring write SQLite data. They do not rewrite source audio.

## Which actions can write audio files?

MAEST genre tag apply, Audio Doctor apply, and Audio Dedup apply. Audio Dedup apply can delete files. Each is explicit and separate from normal search and analysis.

## Does relocation move my music?

No. Relocation apply updates stored SQLite paths only after preview checks pass.

## How do I analyze the whole library?

From CLI, omit `--limit`:

```powershell
dj-sim analyze --models sonara,maest,mert,clap --db .\data\library.sqlite
```

In the UI, set `Analyze limit` to `0`.

## Why are CLAP text scores lower than MERT scores?

CLAP text search is text-to-audio evidence. MERT seed search is audio-to-audio embedding similarity. They use different scales.

## Can I use the app without model dependencies?

Yes, for scan, browse, serve, export, database selection, and existing SQLite data. Install optional analysis extras when you want new SONARA, MAEST, MERT, or CLAP results.

## Can I share reports or databases?

Only after review. They can include local file paths, tags, model scores, and notes about your library.

# FAQ

> Audience: Users who want short answers.
> Goal: Answer common questions with current behavior.
> Type: help

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data. They do not rewrite source audio.

## Which actions can write audio files?

MAEST genre tag apply, Audio Doctor apply, and Audio Dedup apply. Audio Dedup apply can delete files. Each is explicit and separate from normal search and analysis.

## Does relocation move my music?

No. Relocation apply updates stored SQLite paths only after preview checks pass.

## How do I analyze the whole library?

From CLI, omit `--limit`:

```powershell
dj-sim analyze --models sonara,maest,mert,muq,clap --db .\data\library.sqlite
```

In the UI, set `Analyze limit` to `0`.

## Do I reset SONARA when upgrading to v0.2.4?

No. Run the default SONARA analysis again. Unsigned, legacy, and mismatched rows are queued by their
signature. Reset only when you intentionally want to purge existing SONARA data first. See the
[migration workflow](../workflows/migrate-sonara-v0-2-4.md).

## Why did my SONARA classifier scores disappear?

A project feature-revision change invalidates SONARA-dependent main-library scores and Rhythm Lab
predictions. Labels and feedback are preserved. Reanalyze SONARA, retrain the profile, promote a
manifest version `2` artifact, and rescore.

## Why are CLAP text scores lower than MERT scores?

CLAP text search is text-to-audio evidence. MERT seed search is audio-to-audio embedding similarity. They use different scales.

## Can I use the app without model dependencies?

Yes, for scan, browse, serve, export, database selection, and existing SQLite data. Install optional analysis extras when you want new SONARA, MAEST, MERT, MuQ, or CLAP results.

## Can I share reports or databases?

Only after review. They can include local file paths, tags, model scores, and notes about your library.

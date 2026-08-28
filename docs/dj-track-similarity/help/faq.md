# FAQ

Short answers about how the current runtime behaves, with the safe local workflows kept separate
from migration assumptions.

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data only.

## Which actions can write audio files?

Three of them. MAEST genre-tag apply, Audio Doctor apply, and Audio Dedup deletion. All three stay
separate from normal scan, search, and analysis.

Their gates differ, so be precise about which one you are using:

- **MAEST genre apply** writes the genre field for tracks with stored MAEST genres, when you start
  it.
- **Audio Doctor apply** is dry-run first, backs up each file, verifies the result, and restores the
  backup on failure. It takes no confirmation phrase, so `--apply` writes immediately.
- **Audio Dedup deletion** requires the phrase `APPLY DELETE` in the request. From the CLI you type
  it. In the browser the client supplies it and you answer a `Да` / `Нет` dialog.

[Local-first safety](../concepts/local-first-safety.md) is the full list.

## Why is the interface in Russian?

The browser UI is written in Russian while this documentation is in English.
[UI language](./ui-language.md) maps every control from one to the other. Model names, tab labels,
mode names, and numeric field labels such as `Limit` stay English on screen.

## What does deleting a track remove?

The catalog row, its FTS entry, and every catalog table that references it by `track_id`, which
covers tags, likes, embeddings, fingerprints, classifier scores, and feedback. The optional
Evaluation database is a separate file with no foreign key back to the catalog, so its
`search_session_seeds` and `search_result_events` rows for that track are deleted in a second step.
Audio Dedup deletion also clears matching Rhythm Lab label rows. Source audio is removed only by
Audio Dedup deletion, never by `DELETE /api/tracks/{track_id}`.

## Can the app migrate an incompatible database?

Normal startup refuses an incompatible legacy split database and never rewrites it. Stop the server
and your database tools, then run `dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`.
It creates a timestamped backup, then builds and verifies the replacement. It does not run analysis
or reanalysis.

## What follows a SONARA change?

Adapt the project to the SONARA fields you want. Reanalyze only the affected outputs, and only when
you choose to. Retrain, promote, and rescore a SONARA-dependent classifier only when its feature
recipe changed.

## Why are classifier artifacts blocked?

Runtime scoring needs an artifact whose ordered feature recipe and inputs match your current stored
data. Affected artifacts have to be retrained and promoted. Incompatible scores are never silently
reused.

## Can I use the browser UI with a compatible database?

Yes. Build the current frontend bundle and serve it with the current backend. Database selection,
library paging, analysis, search, Current Set, CLASS, LAB, Rhythm Lab launch, metadata, preview, and
exact-identity writes all use the current typed responses.

Library loading is one fixed page of up to 200 tracks per request, with previous, next, and
page-number navigation. There is no second row-window paginator and no incremental chunk loading
inside a page. Sort direction and shuffle reorder the loaded page in the browser rather than
requesting a new one.

## Can the app build a set for me?

No. The current set is a list you build by hand, one track at a time, and export in the order you
put them. Automatic sequencing from anchors, a mood arc, or a story prompt is a direction rather
than a feature. See [Project idea](../concepts/project-idea.md) for the boundary.

## Can I share reports or databases?

Review them first. They can contain local paths, tags, scores, and your listening decisions.

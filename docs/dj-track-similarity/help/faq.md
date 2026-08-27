# FAQ

Short answers about how the current runtime behaves, with the safe local workflows kept separate
from migration assumptions.

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data only.

## Which actions can write audio files?

Only MAEST genre-tag apply, Audio Doctor apply, and Audio Dedup deletion. Audio Dedup deletes files,
either from a CLI `--apply` run or from the browser review dialog, and both need the exact phrase
`APPLY DELETE`. Each of the three sits behind a confirmation gate and stays separate from normal
scan, search, and analysis.

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
library paging and chunked loads, analysis, search, Current Set, CLASS, LAB, Rhythm Lab launch,
metadata, preview, and exact-identity writes all use the current typed responses.

## Can I share reports or databases?

Review them first. They can contain local paths, tags, scores, and your listening decisions.

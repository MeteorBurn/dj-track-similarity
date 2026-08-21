# FAQ

Short answers about how the current runtime behaves, with the safe local workflows kept separate
from migration assumptions.

## Does analysis change audio files?

No. SONARA, MAEST, MERT, MuQ, CLAP, and classifier scoring write SQLite data only.

## Which actions can write audio files?

Only MAEST genre-tag apply, Audio Doctor apply, and Audio Dedup apply. Audio Dedup apply can delete
files. Each of the three sits behind a confirmation gate and stays separate from normal scan,
search, and analysis.

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

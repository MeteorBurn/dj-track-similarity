# Manual database validation design

## Scope

Add one explicit, read-only database-validation workflow available from the
desktop UI, the local API, and the CLI. It audits the selected library bundle
and its persisted track, embedding, feature, and model-related rows. It does
not recalculate audio analysis, hash audio, write tags, repair data, mutate the
database, or run automatically at startup or while ordinary counters load.

The workflow is for occasional maintenance. It runs one validation job at a
time and must not run alongside another database job or database switch.

## Validation contract

`DatabaseValidator` owns an ordered set of small validators. It opens the
existing Core/Artifacts bundle in read-only mode and consumes each cursor one
row at a time. It emits a finding after each checked entity.

The audit has three layers:

1. Database-level checks: the managed storage layout, SQLite integrity, and
   foreign-key violations. `foreign_key_check` findings are consumed as rows;
   there are no summary joins or coverage aggregations.
2. Track checks: each `tracks` row has a valid identity and a path that exists
   as a file. The audit does not compare audio bytes, size, mtime, or content
   fingerprint, so harmless file-byte changes do not invalidate a track.
3. Persisted-analysis checks: each managed row is matched to its track and
   validated by the current family specification. Embeddings use the canonical
   identity, dimension, blob-size, float32, finite-value, and normalization
   rules. Feature and weight validators use their owning current schema or
   model specification.

Validators are registered from the current DDL and analysis-specification
registries, not from a fixed snapshot of the user's tracks or columns. A
managed table with no semantic validator is a warning, which makes an
unintegrated new data type visible without treating a user extension as corrupt.

An intentionally unanalyzed track is not an error merely because it has no
embedding or feature row. Errors cover existing corrupt payloads, impossible
relations, orphan rows, or values that contradict the current persisted-data
contract. Unknown unmanaged SQLite objects are warnings, not automatic
deletions.

## Job status, log, and report

The feature introduces a dedicated in-memory `DatabaseValidationJobStatus`,
not a new SQLite audit-log table. It holds job identity, state, current phase,
processed count, warning/error counts, cancellation request, timestamps, and a
bounded tail of structured findings for API/UI polling.

Every result is also emitted through the existing application file logger:

`[OK|WARNING|ERROR] validation job_id=<id> entity=<kind> table=<name> track_id=<id> code=<code> message=<text>`

`OK` is represented as an informational log record with the explicit status in
the message; warnings and errors use their normal log levels. Validation event
logging is never suppressed by the optional analysis-track diagnostics flag.
The job status keeps only a bounded tail so a large library does not become a
large API payload; the normal log remains the complete per-entity record.

The CLI prints the same events and final summary. `--report <path>` optionally
writes a JSON final report outside the database. No report file is created by
default, and no historical run state is persisted in the library database.

## Entry points and lifecycle

- CLI: `dj-sim validate-database --db <core-db> [--report <path>]` runs
  synchronously and exits non-zero for errors or a failed/cancelled audit.
- API: `POST /api/database/validation/jobs` starts an asynchronous job;
  `GET /api/database/validation/jobs/latest`, `GET .../{job_id}`, and
  `POST .../{job_id}/cancel` expose status and cancellation.
- UI: a non-destructive `Проверить БД` action in the library-maintenance area
  starts the API job, displays its progress and summary, and opens the existing
  log view. It is disabled whenever another database job is active.

The API state reserves the selected database for the entire audit. This gives
the audit a stable view and prevents a scan, analysis, reset, or database switch
from changing the data halfway through it. Cancellation is checked between
entities, not by interrupting a SQLite call.

## Test strategy

Use only temporary SQLite bundle and empty-file fixtures. Cover valid rows,
missing paths, malformed embeddings (identity, dimension, blob length,
normalization, non-finite values), orphan rows, unknown managed data, report
format, cancellation, job exclusion, API status routes, CLI exit codes, and the
UI trigger/progress presentation.

Tests prove that every run leaves both database files byte-for-byte unchanged
at the application level: no audit rows, timestamps, tags, analysis rows, or
audio files are written. They do not invoke real models or inspect the user's
library.

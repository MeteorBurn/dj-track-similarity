# SONARA Core-only analysis design

## Goal

The application must request, validate, and persist only the current SONARA
Core result. Timeline, SONARA similarity embedding, and fingerprint must not be
requested as standalone SONARA outputs, converted, written, read, exposed by
the API, or selectable in the UI.

The existing Artifacts database structure remains unchanged. New databases
continue to create the reserved tables for Timeline, SONARA similarity
embeddings, and fingerprints so these outputs can be restored later without a
schema migration.

## Scope

This change removes the active application support for:

- `timeline`
- SONARA `embedding`
- SONARA `fingerprint`

It preserves:

- every current SONARA Core field and its validation;
- the Core feature allowlist needed to produce those fields;
- SONARA Core Search;
- the `sonara_broad` SET signal;
- the SONARA source used by Hybrid;
- SONARA Core inputs used by classifiers and Rhythm Lab;
- the current Artifacts tables, columns, indexes, schema fingerprint, and
  creation order.

No existing or future database row is deleted by this change.

## Runtime contract

SONARA analysis has one application-level output: `("sonara", "core")`.

The native `sonara.analyze_batch()` call receives only the explicit feature
allowlist required by the current Core row. It does not receive the standalone
feature requests `"embedding"` or `"fingerprint"`.

Some Core feature groups also produce time-resolved values internally or in
the returned mapping. For example, `structure`, `beatgrid`, `tempo_curve`, and
`loudness` are still requested when their aggregate Core values are required.
Those supporting arrays are ignored at the conversion boundary and are not
treated as a Timeline result.

The bundled vocalness model may compute a SONARA embedding internally. That is
an implementation detail inside SONARA: the application neither requests an
embedding output nor persists or exposes the internal vector.

## Backend changes

The SONARA runtime exposes one Core feature allowlist and no output-selection
API. `normalize_sonara_outputs`, the four-output constants, and the
Timeline/Embedding/Fingerprint requested-feature groups are removed.

`prepare_sonara_write` validates and constructs only the Core write. The
Timeline payload conversion, SONARA embedding conversion, fingerprint decoding,
and their typed result fields are removed from the active analysis model.

The analysis runner, job configuration, job status, CLI, pipeline request, and
API request no longer accept `sonara_outputs`. SONARA readiness and progress
refer only to Core.

The repository writes only the Core row for a SONARA result. Active-output
registration and candidate selection contain only `("sonara", "core")`.
Timeline loading and optional-output coverage are removed from the public
repository and API surfaces.

## Database compatibility

The following tables and their indexes remain in the Artifacts DDL:

- `sonara_timeline`
- `sonara_similarity_embeddings`
- `sonara_fingerprints`

They remain part of the exact Artifacts schema definition and are created in
their current order. The change does not alter the schema fingerprint, database
structure version, or migration behavior.

No analysis path writes new rows to these tables. Generic schema validation,
track cleanup, reset safety, and migration compatibility may continue to name
the reserved tables where required to preserve database invariants. This
compatibility code is not an active SONARA collection path.

## Frontend and API

The Library analysis panel shows SONARA as a Core-only analyzer. The Core,
Timeline, Embedding, and Fingerprint checkbox group is removed rather than
replaced by a disabled Core checkbox.

Analysis requests do not send `sonara_outputs`. Pipeline requests contain the
SONARA batch size only.

Track metadata no longer shows Timeline, SONARA Embedding, or SONARA Fingerprint
presence blocks. Their optional-output flags and the dedicated Timeline route
are removed from the active API contract.

## Documentation

README and maintained English and Russian documentation describe SONARA
analysis as Core-only. They do not instruct users to select or request Timeline,
Embedding, or Fingerprint. Database reference pages retain the three reserved
tables and state that the current analyzer does not populate them.

Historical Superpowers specifications and plans remain historical records and
are not rewritten.

## Error handling

Missing or invalid required Core fields continue to fail per track through the
existing conversion and repository error paths. Extra fields returned by
SONARA are ignored.

An obsolete client request containing `sonara_outputs` is not interpreted as a
request to collect optional data. The field is removed from typed clients and
is ignored or rejected according to the existing request-schema policy; in
either case, only Core can run.

## Verification

Tests must prove that:

1. the native SONARA feature request excludes `embedding` and `fingerprint`;
2. the registered and persisted SONARA output is Core only;
3. analysis configuration, CLI, API, and pipeline contracts have no selectable
   SONARA outputs;
4. Timeline/Embedding/Fingerprint conversion and public read surfaces are gone;
5. the frontend has no output checkboxes or metadata presence blocks;
6. new Artifacts databases still create the three reserved tables with their
   current columns and indexes;
7. focused SONARA Core, API, repository, and frontend tests pass;
8. the frontend build and typecheck pass after the contract removal.

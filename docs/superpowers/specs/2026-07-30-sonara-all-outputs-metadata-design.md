# SONARA All-Outputs Analysis and Metadata Design

## Goal

Make SONARA analysis one indivisible operation. Every SONARA job produces the
four supported output kinds:

- `core`
- `timeline`
- `embedding`
- `fingerprint`

Users must not choose a subset. The Library panel continues to treat SONARA,
the selectable ML models, and CLASSIFIERS as mutually exclusive analysis
modes.

The track metadata dialog must present Timeline, Embedding, and Fingerprint as
three consistent badge-based categories immediately before the existing
`Analysis` category.

## Scope

This change covers:

- the Library panel's SONARA and FULL controls;
- frontend analysis state and request construction;
- the public analysis API request schemas;
- the `analyze` and `analyze-pipeline` CLI output-selection options;
- backend analysis configuration and job construction;
- typed per-track summaries for stored SONARA artifacts;
- the SONARA portion of the track metadata dialog;
- focused backend and frontend tests for those contracts.

The internal output-kind identifiers remain. They are still required for
artifact registration, storage validation, coverage, completeness checks, job
status, and reporting. Runtime job, runner, conversion, and repository-write
APIs do not accept a subset.

The explicit pipeline engine remains available for sequential orchestration.
This change removes the invalid `FULL` shortcut from the Library panel and
preserves the panel's existing mutually exclusive selection rules; it does not
redesign pipeline orchestration.

## Analysis Selection Behavior

### Library panel

Remove:

- the `FULL` checkbox;
- `toggleAllAnalysisModels`;
- `analysisSelectionOrder` usage that exists only for FULL;
- the `Core`, `Timeline`, `Embedding`, and `Fingerprint` checkboxes;
- `sonaraOutputs` state and `toggleSonaraOutput`;
- the corresponding component props and checkbox-specific CSS.

Keep the current mode rules:

- selecting SONARA leaves SONARA as the only selection;
- selecting CLASSIFIERS leaves CLASSIFIERS as the only selection;
- one or more of MAEST, MERT, MuQ, and CLAP may be selected together;
- the last active selection cannot be unchecked.

The SONARA card shows a non-interactive compact statement such as
`Всегда: Core · Timeline · Embedding · Fingerprint`. It communicates the fixed
contract without looking selectable.

### Public requests and CLI

Remove user-controlled SONARA output lists from:

- `AnalysisJobRequest.sonara_outputs`;
- `SonaraPipelineSettings.outputs`;
- frontend analysis-job and pipeline request payloads;
- `dj-sim analyze --sonara-outputs`;
- `dj-sim analyze-pipeline --sonara-outputs`.

Unknown removed fields remain rejected by the existing `extra="forbid"` API
policy. This makes stale clients fail clearly instead of silently accepting a
setting that no longer has an effect.

When an analysis configuration includes SONARA, the backend assigns
`SONARA_OUTPUT_KINDS` in canonical order. Job status may continue to expose
`sonara_outputs`, but for a SONARA job it always reports all four kinds. For a
non-SONARA job it remains empty.

Internal job and runner construction must not offer an override that can
narrow the set. The canonical tuple is supplied by analysis configuration or
the SONARA runner itself.

### Per-track write invariant

Conversion succeeds only when one analyzer result contains valid Core,
Timeline, Embedding, and Fingerprint data. `SonaraWrite` carries all four
non-optional outputs with one shared timestamp. The repository persists the
four outputs within the existing coordinated per-track savepoint. A conversion
or write error fails that track and does not publish a SONARA result.

If a process interruption leaves unmatched artifact residue, Core remains
missing and existing readiness checks schedule the track again. Such residue
is not a valid or visible SONARA result.

## Storage and UI Loading

Heavy SONARA data stays exclusively in the mandatory Artifacts database:

- `sonara_timeline.payload_json` stores Timeline arrays, events, curves, and
  segments;
- `sonara_similarity_embeddings.embedding_blob` stores the similarity vector;
- `sonara_fingerprints.fingerprint_blob` stores packed fingerprint words, while
  a small `fingerprint_sha256` column stores their persisted digest.

The Core database keeps only the existing queryable SONARA scalars, compact
vector summaries, identity fields, and the shared analysis timestamp. React
state, list responses, and track-detail responses never contain raw Timeline
payloads, embedding vectors, or fingerprint words.

Library-list coverage and track-detail metadata use metadata-only SQL
projections:

- Timeline selects identity, generation, and `analyzed_at`, but not
  `payload_json`. Its field badges come from the canonical
  `SONARA_TIMELINE_KEYS`, because every accepted Timeline result must contain
  exactly that fixed set.
- Embedding selects `dim`, `normalization`, `analyzed_at`, and
  `length(embedding_blob)` for structural validation, but not
  `embedding_blob`.
- Fingerprint selects `fingerprint_version`, `word_count`, `byte_order`,
  `fingerprint_sha256`, `analyzed_at`, and `length(fingerprint_blob)` for
  structural validation, but not `fingerprint_blob`.

Full payload validation happens before every write. Server-side workflows that
actually consume an artifact load and validate it on demand. The existing
Timeline endpoint remains the explicit lazy-load path for Timeline values; the
metadata dialog does not call it. Embeddings and fingerprints remain
server-side inputs and are never serialized into the metadata UI.

The digest is computed once while the canonical fingerprint bytes are already
in memory for a write:

```text
SHA-256(UTF8("sonara-fingerprint") || NUL ||
        ASCII(decimal fingerprint_version) || NUL || fingerprint_blob)
```

Including the internal format version domain-separates digests if SONARA ever
changes the fingerprint bit layout. Reanalyzing unchanged audio with the same
algorithm produces the same digest; the version does not increment per
analysis run.

Adding the digest column requires an explicit Artifacts database migration.
The migration follows the project's normal backup and confirmation rules and
backfills the digest once from existing blobs. Normal UI requests never
recompute it.

## Metadata Contract

Replace the availability-only optional-output fields with one nullable,
indivisible summary:

```text
optional_outputs: {
  analyzed_at: string
  timeline: {
    fields: string[]
  }
  embedding: {
    dim: number
    normalization: string
  }
  fingerprint: {
    sha256: string
    word_count: number
  }
} | null
```

The repository builds this object only when Core and all three artifact rows
pass the existing identity, generation, output-registration, and payload
validators and share one `analyzed_at` value. Otherwise `optional_outputs` is
`null`, and the track is treated as not analyzed by SONARA.

Timeline exposes only its stored top-level field names. Embedding exposes
dimension and normalization. Fingerprint exposes its stored digest and word
count. Format version and byte order remain internal compatibility metadata;
they are not user-facing badges. The API never sends the Timeline value
arrays, embedding vector, or fingerprint blob as part of track details.

`optional_outputs.analyzed_at` is the one timestamp for the complete SONARA
result. The SONARA write path creates it after analysis and shares it across
the four outputs before saving them through the coordinated write path.

The existing dedicated Timeline endpoint remains unchanged for workflows that
explicitly need Timeline values.

## Metadata Presentation

Rename the containing metadata block from `SONARA · Core` to `SONARA`, because
it now contains both Core features and summaries of the three artifact
outputs.

Preserve the current Core feature groups and value formatting, except that the
`Analysis` group's timestamp source changes to
`optional_outputs.analyzed_at`. After `Vector summaries`, use these categories
in order:

1. `Timeline`
2. `Embedding`
3. `Fingerprint`
4. `Analysis`

Timeline, Embedding, and Fingerprint use one shared badge-category renderer.
Example badges:

- Timeline: `beats`, `downbeats`, `segments`, `energy_curve`;
- Embedding: `48D`, `L2`;
- Fingerprint: `ID 7e9a9d2c4b80a1f3`, `1,024 subprints`.

Canonical Timeline field names remain code-like so they map directly to the
stored payload. Human-readable dimensions and counts use the dialog's existing
number and timestamp formatters. Raw vectors and binary values are never
rendered. The UI shows a fixed 16-hex-character prefix of the SHA-256 as the
compact Fingerprint ID and exposes the full digest in the badge tooltip and
accessible label.

The Fingerprint ID identifies an exact stored fingerprint, not a
duplicate-equivalence class. Re-encoded copies may have slightly different
fingerprint bits and therefore different digests even when SONARA's
alignment-aware fingerprint matcher correctly considers them duplicates.

The `Analysis` category contains the single field `Analyzed`. It renders
`optional_outputs.analyzed_at` using the existing timestamp formatter.
Timeline, Embedding, and Fingerprint never render their own timestamps.

When `optional_outputs` is `null`, the metadata dialog shows one SONARA-level
`Не рассчитано` state. It does not present separately missing output
categories, because a subset is not a valid SONARA analysis.

The generic `Embedding analyses` section continues to show MAEST, MERT, MuQ,
and CLAP summaries. It filters out SONARA so the new dedicated Embedding
category is not duplicated.

## Data Flow

1. The user selects SONARA and starts analysis.
2. The frontend sends SONARA batch size and the selected analysis mode, but no
   output list.
3. Backend configuration assigns all four canonical SONARA outputs.
4. The SONARA runner analyzes and stores Core plus all three artifact outputs.
5. Track-detail queries validate the complete four-output bundle through
   metadata-only projections and return its small typed summaries plus one
   shared timestamp.
6. The metadata dialog converts each summary to badges through one shared
   presentation model and renderer.

## Compatibility and Failure Handling

- Any incomplete legacy residue is treated as no SONARA result and is replaced
  by the next SONARA run.
- Existing databases require the explicit, backed-up Artifacts migration that
  adds and backfills `fingerprint_sha256`.
- A failed per-track conversion or write publishes none of the four outputs as
  a valid result. Job status still identifies the failing track and error.
- API clients that still send an output list receive a validation error and
  must remove the obsolete field.
- Artifact validation remains the trust boundary. UI availability is never
  inferred from a row that failed validation.

## Verification

Use test-first slices:

1. Update analysis configuration/API/CLI tests to require all four outputs and
   reject obsolete request fields or CLI flags. Confirm the tests fail before
   changing production code.
2. Update frontend analysis-control tests to require no FULL control, no
   SONARA output checkboxes, no output-selection state, and no output list in
   requests. Confirm the tests fail first.
3. Add repository and API tests for the indivisible typed artifact summary.
   Prove that all three summaries and the one timestamp appear together, and
   that an absent, metadata-invalid, or timestamp-mismatched row makes the
   whole result unavailable. Confirm the tests fail first.
4. Add repository query tests proving that Library coverage and track-detail
   metadata do not select `payload_json`, `embedding_blob`, or
   `fingerprint_blob`; structural byte-length checks may remain in SQL.
   Confirm the tests fail first.
5. Add digest tests proving deterministic SHA-256 generation, version-domain
   separation, migration backfill, full-digest API transport, and abbreviated
   UI rendering without loading the fingerprint BLOB. Confirm the tests fail
   first.
6. Update metadata-model tests for category order, badge content, uniform
   SONARA-level missing state, one `Analyzed` field, no per-output timestamps,
   and SONARA de-duplication from generic embedding summaries. Confirm the
   tests fail first.

After each focused red/green cycle, run:

- the affected backend pytest files;
- `npm test` for the focused frontend contracts;
- `npm run typecheck`;
- `npm run build`.

Inspect the final diff and run `git diff --check` before reporting completion.

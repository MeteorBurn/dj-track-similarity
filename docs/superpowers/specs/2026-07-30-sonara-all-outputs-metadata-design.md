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
artifact registration, storage validation, coverage, missing-result checks,
job status, and reporting. Low-level storage helpers may continue to accept an
explicit output set when that is necessary for isolated validation tests.

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

Internal job and runner construction must not offer a user-derived override
that can narrow the set. The canonical tuple is supplied by analysis
configuration or the SONARA runner itself.

## Metadata Contract

Replace the availability-only optional-output fields with typed summaries:

```text
timeline: {
  fields: string[]
  analyzed_at: string
} | null

embedding: {
  dim: number
  normalization: string
  analyzed_at: string
} | null

fingerprint: {
  version: string
  word_count: number
  byte_order: string
  analyzed_at: string
} | null
```

The repository builds these summaries only from artifact rows that pass the
existing identity, generation, output-registration, and payload validators.
An absent or invalid artifact becomes `null`; it must not leak stale metadata.

Timeline exposes only its stored top-level field names and timestamp. Embedding
exposes dimension, normalization, and timestamp. Fingerprint exposes version,
word count, byte order, and timestamp. The API never sends the Timeline value
arrays, embedding vector, or fingerprint blob as part of track details.

The existing dedicated Timeline endpoint remains unchanged for workflows that
explicitly need Timeline values.

## Metadata Presentation

Rename the containing metadata block from `SONARA · Core` to `SONARA`, because
it now contains both Core features and summaries of the three artifact
outputs.

Preserve the current Core feature groups and formatting. After
`Vector summaries`, insert these categories in order:

1. `Timeline`
2. `Embedding`
3. `Fingerprint`
4. `Analysis`

Timeline, Embedding, and Fingerprint use one shared badge-category renderer.
Example badges:

- Timeline: `beats`, `downbeats`, `segments`, `energy_curve`,
  `Analyzed 30.07.2026 12:34:56`;
- Embedding: `48D`, `L2`, `Analyzed 30.07.2026 12:34:56`;
- Fingerprint: `v7`, `1,024 words`, `little-endian`,
  `Analyzed 30.07.2026 12:34:56`.

Canonical Timeline field names remain code-like so they map directly to the
stored payload. Human-readable dimensions and counts use the dialog's existing
number and timestamp formatters. Raw vectors and binary values are never
rendered.

Each missing category displays the same subdued `Не рассчитано` state. This
is required for databases created before all four outputs became mandatory and
for tracks whose prior job failed after writing only part of its result.

The generic `Embedding analyses` section continues to show MAEST, MERT, MuQ,
and CLAP summaries. It filters out SONARA so the new dedicated Embedding
category is not duplicated.

## Data Flow

1. The user selects SONARA and starts analysis.
2. The frontend sends SONARA batch size and the selected analysis mode, but no
   output list.
3. Backend configuration assigns all four canonical SONARA outputs.
4. The SONARA runner analyzes and stores Core plus all three artifact outputs.
5. Track-detail queries validate current artifact rows and return their small
   typed summaries.
6. The metadata dialog converts each summary to badges through one shared
   presentation model and renderer.

## Compatibility and Failure Handling

- Existing partial SONARA data stays readable. Missing outputs render as
  `Не рассчитано` and will be completed by the next SONARA run.
- Existing databases require no schema migration; the required summary fields
  already exist in the artifact tables.
- A failed SONARA job retains normal per-output status reporting, even though
  the requested set is fixed.
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
3. Add repository and API tests for the three typed artifact summaries,
   including absent and invalid-artifact cases. Confirm the tests fail first.
4. Update metadata-model tests for category order, badge content, uniform
   missing states, and SONARA de-duplication from generic embedding summaries.
   Confirm the tests fail first.

After each focused red/green cycle, run:

- the affected backend pytest files;
- `npm test` for the focused frontend contracts;
- `npm run typecheck`;
- `npm run build`.

Inspect the final diff and run `git diff --check` before reporting completion.

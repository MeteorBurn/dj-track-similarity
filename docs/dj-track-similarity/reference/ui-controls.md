# UI controls status

> Audience: Users looking for browser control ranges.
> Goal: Prevent v7 libraries from being operated through stale frontend controls.
> Type: reference

The frontend v7 port is deferred. The current browser controls are not v7-compatible, so this page
intentionally does not claim current checkbox states, slider ranges, batch defaults, reset actions,
or database-selection behavior.

Use the current Python CLI and API contracts for schema-v7 work. The supported SONARA output names
are `core`, `timeline`, `embedding`, and `fingerprint`; there is no `Representations` output or
separate Timeline/Representations database control. Core and mandatory `*.artifacts.sqlite` are
bound by `catalog_uuid`; `*.evaluation.sqlite` is optional evaluation state.

For analysis commands and storage boundaries, see [Analyze a library with v7](../user-guide/analyze-library.md).
For source-file safety, see [Local-first safety](../concepts/local-first-safety.md).

When the frontend v7 port lands, this reference should be rebuilt from `frontend/src/api.ts` and the
active backend schemas rather than carrying forward values from the removed v5/v6 UI.

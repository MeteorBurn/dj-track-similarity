# Verification by change surface

Read before selecting checks for an implementation change or changing tests, runners, dependencies, persistence, or package/loader boundaries.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## VERIFICATION ROUTING

- While iterating, use the cheapest check that can expose the problem: scoped
  diff, `rg`, `git diff --check`, an import driver, or the owning test file.
  Invoke pytest through the root interpreter:
  `& .\.venv\Scripts\python.exe -m pytest 'tests/test_<area>.py'`; narrow with
  `-k` when useful.
- Do not run `graphify update .`, builds, the docs check, or broad `ml`, `slow`,
  and `evaluation` selections between edits. Run focused owner tests when needed,
  including fake-loader tests marked `ml`; inspect and report skips rather than
  silently excluding the checks relevant to the change.
- Before delivery, ensure checks covering the final changed state have passed.
  Reuse a passed selection unless relevant code, configuration or dependencies
  changed; do not rerun merely for delivery. Instruction-only changes need a
  scoped diff, whitespace check and relevant path/command checks, not application
  tests or a docs build.
- A localized backend change ends at its owning test files. Broaden only for
  affected shared contracts, persistence, broad refactors, releases, unresolved
  failures, or dependency/runtime/test-runner changes with broad impact. Changes
  outside `src/` do not by themselves require or prohibit backend checks.
- Root pytest collects only `tests/`. Name affected script/tool suites explicitly:
  `scripts/tests`, `tools/audio-dedup/tests`, `tools/audio-doctor/tests`,
  `tools/audio-online/tests`, or `tools/rhythm-lab/tests`.
  For Audio Online workbook-bridge changes, also run
  `node --test tools/audio-online/workbook_bridge.test.mjs` with its existing
  runtime and dependencies, including `METADATA_ENRICHMENT_NODE_MODULES`.
  Report unavailable dependencies rather than creating another environment.
- For frontend runtime or build changes, run
  `npm --prefix .\frontend run typecheck` and `npm --prefix .\frontend test`;
  also run `npm --prefix .\frontend run build`
  before a commit. Frontend instruction-only and copy-only edits do not require
  these checks. For maintained docs or docs tooling changes, run
  `npm --prefix .\docs\dj-track-similarity run check`.
- For behavior changes, exercise the matching surface with one happy path and
  one relevant failure path: browser, HTTP request, CLI, or minimal import
  driver. Existing focused tests can satisfy these scenarios when they exercise
  the matching boundary; do not duplicate them with a manual smoke solely for
  this checklist. Follow the temporary-fixture and user-data safety rules in [AGENTS.md](../../AGENTS.md#safety-invariants).
- Diagnose from source first, then confirm the hypothesis on the running
  surface. For browser layout, use DOM geometry, overflow and computed styles
  where supported; use screenshots when visual inspection is needed. Prefer
  semantic locators or element references supported by the active browser tool.
- Before testing database startup or persistence-sensitive refactors, inspect
  constructor/connect/schema paths for implicit migrations or data writes.
  For broad package/loader refactors, retain the same pre-change synthetic
  database and affected classifier artifacts, then compare read/search results,
  readiness and file seals without regenerating fixtures or running analysis.
- If sandbox permissions make the default temporary directory unusable, choose
  a unique workspace `--basetemp`; redirect process `TEMP`/`TMP` and application
  logs there when subprocesses or tools bypass pytest fixtures. Never point test
  temporary paths at user libraries or remove shared temp directories to retry.
- There is no tracked CI workflow. Report checks actually run and any blocked
  verification; do not imply CI or source inspection proves live behavior.

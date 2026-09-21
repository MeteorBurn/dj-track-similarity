# Verification by change surface

Read before selecting checks for an implementation change or changing tests, runners, dependencies, persistence, or package/loader boundaries.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## VERIFICATION ROUTING

Pick the lowest tier that fits the change. Tests are evidence for a touched
contract, not a routine or a delivery ritual.

- **Routine change (default): no test suite.** Use the cheapest check that can
  expose a mistake in the touched file: the scoped diff, `git diff --check`, a
  syntax or import check through the root interpreter
  (`& .\.venv\Scripts\python.exe -m py_compile '<file>'`), Ruff on that file
  (`& 'C:\Utils\tools\ruff\ruff.exe' check '<file>'`),
  `npm --prefix .\frontend run typecheck` for TypeScript, or direct inspection.
  Instruction-only and copy-only changes need a scoped diff, whitespace check
  and relevant path/command checks.
- **Touched durable contract: its owning test only.** When the change touches a
  contract that a test owns (the durable kinds in
  [TEST POLICY](../../AGENTS.md#test-policy)), run that test and nothing wider:
  `& .\.venv\Scripts\python.exe -m pytest 'tests/test_<area>.py' -k '<name>'`,
  the owning file under `tools/<tool>/tests/`, or
  `node --test 'frontend/tests/<name>.test.mjs'`. Root pytest collects only
  `tests/`; tool tests run only when named. A workbook-bridge contract change in
  Audio Online runs `node --test tools/audio-online/workbook_bridge.test.mjs`
  with its existing runtime and dependencies, including
  `METADATA_ENRICHMENT_NODE_MODULES`; report unavailable dependencies rather than
  creating another environment. Inspect and report skips.
- **Full suite: exceptional cases only.** Run root `tests/`, the four
  `tools/*/tests` suites and `npm --prefix .\frontend test`, plus
  `npm --prefix .\frontend run build`, only for a cardinal change that can
  really break the application (schema or persistence, shared infrastructure,
  cross-layer refactors, dependency or runtime upgrades, concurrency or
  file-write safety) or on the owner's explicit request. Broad `ml`, `slow` and
  `evaluation` selections count as full runs. Never run the full suite, a build,
  the docs check or `graphify update .` between edits or merely for delivery, a
  commit or reassurance.
- A passed check stays valid until relevant code, configuration or dependencies
  change; delivery adds no checks.
- While the docs site is paused (see
  [DOCUMENTATION WORKFLOW](../../AGENTS.md#documentation-workflow)), a
  `README.md` edit runs `npm --prefix .\docs\dj-track-similarity run lint:language`;
  the full `run check`, which builds the site, applies only after the site is
  resumed.
- When the tiers above cannot settle a behavior change, exercise the matching
  surface once through its happy path, plus a failure path when the change is
  about failure handling: browser, HTTP request, CLI, or minimal import driver.
  Follow the temporary-fixture and user-data safety rules in
  [AGENTS.md](../../AGENTS.md#safety-invariants).
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
- There is no tracked CI workflow. Always report which checks ran, which did
  not and why, and any blocked verification; do not imply CI or source
  inspection proves live behavior.

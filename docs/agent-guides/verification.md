# Verification by change surface

Read before selecting checks or adding, changing or deleting tests, and before
changing runners, dependencies, persistence or package/loader boundaries.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## VERIFICATION ROUTING

Pick the lowest tier that fits the change. Tests are evidence for a touched
contract, not a routine or a delivery ritual. These tiers select test breadth;
the [required source diagnostics](../../AGENTS.md#execution-and-scope) still
apply. Before runtime commands, follow [Environment](environment.md).

- **Routine change (default): no test suite.** Use the cheapest check that can
  expose a mistake in the touched file: the scoped diff, `git diff --check`, a
  syntax or import check through the root interpreter
  (`& .\.venv\Scripts\python.exe -m py_compile '<file>'`), Ruff on that file
  (`& 'C:\Utils\tools\ruff\ruff.exe' check '<file>'`),
  `npm --prefix .\frontend run typecheck` for TypeScript, or direct inspection.
  Instruction-only and copy-only changes need a scoped diff, whitespace check
  and relevant path/command checks.
- **Touched durable contracts: their owning tests.** For the durable kinds in
  [TEST POLICY](#test-policy), select existing tests for the affected behaviors
  and failure modes; one contract may need more than one test. Keep the run
  scoped to those contracts:
  `& .\.venv\Scripts\python.exe -m pytest 'tests/test_<area>.py' -k '<name>'`,
  the owning file under `tools/<tool>/tests/`, or
  `node --test 'frontend/tests/<name>.test.mjs'`. Root pytest collects only
  `tests/`; tool tests run only when named. A workbook-bridge contract change in
  Audio Online runs `node --test tools/audio-online/workbook_bridge.test.mjs`
  with its existing runtime and dependencies, including
  `METADATA_ENRICHMENT_NODE_MODULES`; report unavailable dependencies rather than
  creating another environment. Report skips that leave a relevant contract unchecked.
- **Full suite: exceptional cases only.** Run root `tests/`, the
  `tools/*/tests` suites and `npm --prefix .\frontend test`, plus
  `npm --prefix .\frontend run build`, only for a cardinal change that can
  really break the application (schema or persistence, shared infrastructure,
  cross-layer refactors, dependency or runtime upgrades, concurrency or
  file-write safety) or on the owner's explicit request. Broad `ml`, `slow` and
  `evaluation` selections count as full runs. Do not repeat broad checks between
  edits or run the full suite, a build, the docs check or `graphify update .`
  merely for delivery, a commit or reassurance.
- A passed check stays valid until relevant code, configuration or dependencies
  change; delivery adds no checks.
- While the docs site is paused (see
  [DOCUMENTATION WORKFLOW](../../AGENTS.md#documentation-workflow)), a
  `README.md` edit runs `npm --prefix .\docs\dj-track-similarity run lint:language`;
  the full `run check`, which builds the site, applies only after the site is
  resumed.

### Runtime evidence and fixture safety

- When the tiers above cannot settle a behavior change, exercise the matching
  surface once through its happy path, plus a failure path when the change is
  about failure handling: browser, HTTP request, CLI, or minimal import driver.
  Follow the temporary-fixture and user-data safety rules in
  [AGENTS.md](../../AGENTS.md#safety-invariants).
- Start with evidence closest to the reported defect, then trace its cause and
  verify the fix on that surface. For browser layout, use DOM geometry and styles
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

## TEST POLICY

The suite protects standing contracts. A change does not earn a test by
existing: growth must protect a distinct durable behavior or failure mode.
Do not remove useful coverage merely to keep the test count unchanged. This
policy overrides TDD skills that require a new test for every change.

- Add a test only for something durable: a persisted schema, migration, or
  on-disk format; an HTTP payload, CLI contract, or other cross-boundary shape;
  a scoring, ranking, or safety invariant; or a reproduced bug whose cause is
  understood, asserted at the cause rather than the symptom.
- A new or extended test must fail without what it protects. Before keeping it,
  revert the fix or break that behavior in a disposable copy, watch the test go
  red, and report that run. A test that stays green protects nothing.
- Add no test for cosmetics, labels, copy, tooltips, colors, class names,
  cosmetic presentation order, or a default, threshold, or option expected to
  keep moving. Ranking order and explicitly defined payload order remain
  eligible contracts.
- Add no test for wiring that the type checker, the import graph, or an existing
  focused run already covers.
- Never assert on the text of a source file. Reading a module, script, or
  `.cmd` file and matching strings pins how the code is written instead of what
  it does. Drive the running module and assert its behavior.
  `frontend/tests/testsExecuteCode.test.mjs` fails every frontend test that
  never reaches the module it checks through a loader or a `../src/` import; it
  does not prove that assertions exercise behavior and does not replace review.
- Prefer extending the test that owns the contract; avoid duplicate assertions
  over the same scenario. Separate tests may protect distinct behaviors or
  failure modes of that contract.
- Delete a test whose contract is gone, and delete a test that blocks an
  intentional change while pinning only an incidental detail. Removing a test is
  a normal part of a change, not a regression.
- Keep Audio Dedup's `DEFAULT_RHYTHM_LAB_DB` as its single default constant;
  isolate tests with `tmp_path` and `monkeypatch`, not additional runtime
  configuration switches.

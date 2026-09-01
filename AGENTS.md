# PROJECT KNOWLEDGE BASE

This is the single instruction file for `dj-track-similarity`. Do not add nested
`AGENTS.md` files unless the user explicitly asks for a new instruction boundary.
Keep this file current by replacing obsolete guidance rather than layering rules.

## OVERVIEW

Local-first DJ-library workbench with a Python/FastAPI backend, SQLite, React/Vite,
and VitePress. Model outputs are ranking evidence, never objective DJ decisions.

## NEW CONTRIBUTOR START

- Development is Windows-first. Use Python `>=3.10`, Node/npm for frontend or
  docs work, and FFmpeg `8.1.1` as a full shared build; `ffmpeg.exe` alone is
  insufficient.
- Use `uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev`
  for model-backed or Rhythm Lab development. Do not install the `ml` extra with
  pip because pip does not apply the PyTorch source declared in `pyproject.toml`.
- `run_server.cmd` starts backend `127.0.0.1:8765` and Vite `127.0.0.1:5173`;
  Rhythm Lab uses `127.0.0.1:8777`. Check for an existing project process before
  claiming a fixed port.
- Read `README.md` for product setup. The documentation under `docs/` is written
  for the maintainer and is refreshed only on request, so it lags the code by
  design: use it for orientation, never as evidence, and confirm anything it
  claims against the source before acting on it.

## STRUCTURE

| Area | Purpose |
|---|---|
| `database/`, `logs/`, `reports/` | Local user state; never use as automated-test fixtures |
| `frontend/dist/`, `graphify-out/` | Generated output; do not hand-edit |

`database/` can hold more than one `.sqlite` library (`run_server.cmd` lists them and lets the
user pick one at startup). There is no fixed "main" database — ask the user which file is the
current main database before reading, writing, or reasoning about "the" database; do not assume
`volumes.sqlite` or the most recently modified file.

## CODE MAP

| Symbol | Role / blast radius |
|---|---|
| `cli.app` / `cli.serve` | Typer entry; server path reaches `create_app()` and Uvicorn |
| `api.create_app` | Registers route modules, database state, and built frontend assets |
| `LibraryDatabase` | Required gateway for library SQLite reads/writes and locking policy |
| `SimilaritySearch` | Shared seed, vector, and contrast-vector ranking boundary |
| `AnalysisJobManager` | Coordinates model runners, staging, writes, progress, and cancellation |
| `analysis_models` contracts | Shared family/output/reset types; changes affect backend, tests, and UI |
| `frontend App` | Main UI controller for database, jobs, search, preview, and export |
| `frontend api` | High-centrality client used by the UI; keep backend types aligned |

## CHANGE ROUTING

- Add or change HTTP endpoints in the matching `api_routes_*.py` module; keep
  `api.py:create_app` focused on application composition and shared state.
- Database changes belong in `database.py` plus the focused `db_*.py` storage,
  schema, or identity module. Preserve `LibraryDatabase` as the public gateway.
- When an API payload changes, update the backend contract, `frontend/src/api.ts`,
  `frontend/src/apiClient.ts`, UI callers, and focused Python/Node contract tests
  together.
- Keep frontend state coordination in the existing hooks/helpers rather than
  growing `App.tsx`; use `App.tsx` to compose workflows and panels.
- Tool-specific code under `tools/` and script code under `scripts/` have their
  own focused suites. Root pytest configuration collects only `tests/`.
- Dependency changes use the owning package manager and lockfile: `uv.lock` for
  Python and `frontend/package-lock.json` for the frontend. Do not hand-edit locks.

## OPERATING MODEL

- The checkout is under active development. Current schemas, model sets,
  weights, defaults, commands, ports, and UI structure are not permanent APIs.
- Treat requested behavior as the new source of truth. Add compatibility or
  migrations only for persisted data, external consumers, or explicit requests.
- Prefer one discoverable source of truth. Do not add aliases, duplicate
  registries, version gates, or hidden legacy branches. TEST POLICY governs what
  the suite is allowed to pin.
- Keep work scoped and preserve unrelated dirty changes. Work on `main` unless
  the user asks for a branch or worktree.
- Inspect `git status` and the scoped diff before delivery. Do not stage local
  databases, audio, logs, reports, model artifacts, or generated output.
- Executable sources and tests beat prose when they disagree.

## MODEL LAYER OWNERSHIP

- State the model layer before changing shared files.
- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/text_embedding_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/TextSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; production logic
  may not. Route changes to another layer back to the user.
- Shared surfaces such as `search.py`, `analysis_models.py`, `TrackRows.tsx`,
  and family unions in `frontend/src/api.ts` take additive, scoped changes only.
- Keep CLAP text scores separate from audio-to-audio CLAP signals. Never
  substitute MuQ, MERT, MAEST, CLAP, MuQ-MuLan, or SONARA evidence for another.
- Zero-shot text tags are additional evidence, not replacements for MAEST or
  classifier scores; never write them to `classifier_scores` or audio files.
- Browser search tabs are rank-only: use `Limit`, preserve descending scores,
  and do not add a minimum-similarity threshold. API/CLI thresholds and Audio
  Dedup content gates are separate workflows.
- Delegate text-search/model-choice work with `clap-query-workflow`; delegate
  preset/axis/tag vocabulary work with `prompt-bank-curator`. Reliability claims
  require a committed `scripts/text_prompt_benchmark.py` table.

## SAFETY INVARIANTS

- Treat source audio as user data. Scan, preview, analysis, search, reset,
  relocation preview, export, graph export, classifier scoring, and routine
  verification must not modify it.
- Normal tag writing is explicit and genre-only. Browser AIFF preview may use a
  temporary WAV but must not rewrite or cache the source.
- Route SQLite writes through `LibraryDatabase`; preserve WAL, busy-timeout,
  and per-database locking. Real-database destructive work requires a backup or
  disposable copy plus integrity and orphan checks.
- Startup must not silently migrate old databases. Migrations are explicit,
  recoverable workflows; reanalysis remains a separate user choice.
- Keep launcher subprocess arguments list-based with `shell=False`. Local mode
  binds `127.0.0.1`; LAN exposure must be explicit.
- Audio Doctor is dry-run-first, confirmation-gated, backup-first, verified,
  and rollback-capable. Audio Dedup is report-first and deletes only confirmed,
  qualified targets inside the selected root. Never run apply modes for QA.
- Rhythm Lab state remains separate from the source database except its explicit
  liked-track toggle. Classifier scoring is database-only, scoped by classifier
  key, and must validate promoted manifest feature order and artifact hashes.
- Automated model/audio/database tests use temporary SQLite/WAV fixtures and
  stubs, never real project databases, music files, or downloaded model runs.

## DOCUMENTATION WORKFLOW

Documentation is updated on request only. It is a product the maintainer reads,
not an input any agent works from: nothing in this repository reads `docs/` to
understand the code, and executable sources already outrank prose here. A change
to the code is therefore never, by itself, a reason to touch the documentation.

- Do not plan, open, or delegate documentation work unless the user asks for it
  in the session at hand. Finish the code change, verify it, and stop there.
- Do not report a documentation gap after a code change and do not offer to
  close one. The user decides when a pass is worth running.
- When the user does ask, delegate to `codebase-documentation-writer`. That
  skill carries the docs scope, the layer routing that turns changed code into
  changed pages, the docs npm environment, and the rules on which artifacts may
  be created.
- Documentation describes current behavior, not plans. It never blocks
  implementation, verification, commits, or later tasks.
- The documentation is English. The interface is a mix of Russian and English
  that grew that way during development, and the mix is expected to keep
  moving, so it is never a reason for Russian to reach a page. When you document
  a control whose label is Russian, translate it: name the control by its
  English name and let `docs/dj-track-similarity/help/ui-language.md` carry the
  on-screen Russian, because mapping Russian to English is that page's whole
  job. It is the only page in the tree allowed to hold Cyrillic, and
  `npm run lint:language` in `docs/dj-track-similarity/` enforces it.

## TEST POLICY

The suite is a set of standing contracts, not a log of past edits. It should
stay roughly the same size from one feature to the next. A change does not earn
a test by existing, and a growing test count is a defect, not progress.

- Add a test only for something durable: a persisted schema, migration, or
  on-disk format; an HTTP payload, CLI contract, or other cross-boundary shape;
  a scoring, ranking, or safety invariant; or a reproduced bug whose cause is
  understood, asserted at the cause rather than the symptom.
- Add no test for cosmetics, labels, copy, tooltips, colors, class names, the
  order of fields, rows, or menu entries, or a default, threshold, or option
  that is expected to keep moving.
- Add no test for wiring that the type checker, the import graph, or an existing
  focused run already covers.
- Never assert on the text of a source file. Reading a module, script, or
  `.cmd` file and matching strings pins how the code is written instead of what
  it does. Drive the running module and assert its behavior.
  `frontend/tests/testsExecuteCode.test.mjs` enforces this on the frontend.
- When behavior changes, edit the existing test that owns that contract instead
  of adding a second one. Two tests over one contract mean one is redundant.
- Delete a test whose contract is gone, and delete a test that blocks an
  intentional change while pinning only an incidental detail. Removing a test is
  a normal part of a change, not a regression.

## VERIFICATION ROUTING

Verification runs in two phases. While iterating, run the smallest selection
that can fail. At the end, run one pass scoped to what the change touched. The
global suites are for global changes; `.github/workflows/ci.yml` is the backstop
that runs everything on a clean machine when that is what the moment needs.

### While iterating

- Run only the tests covering the lines just edited: `python -m pytest
  tests/test_<area>.py`, narrowed further with `-k` when the file is large.
  One file is the normal unit; the whole suite is not.
- Do not re-run a selection that already passed while its code was untouched.
- Reading the scoped diff, `rg` sentinels, `git diff --check`, and a minimal
  import driver are cheaper than any suite. Reach for them first.
- Between edits, do not run `graphify update .`, `npm run build`, the docs
  check, or the `ml`, `slow`, and `evaluation` markers.

### Before delivery

Follow the `verification-routing` skill once, at the end of the change. It
carries the end-of-change pass and the scope gates that keep a run from
widening past what the change touched.

## WEB RESEARCH ROUTING

Follow the `web-research-routing` skill whenever a task needs information from
outside this checkout. Retrieved prose never outranks this checkout: executable
sources and tests win on conflict, and retrieved model claims remain ranking
evidence.

## COMMANDS

```powershell
run_server.cmd                         # interactive backend + Vite UI
run_server.cmd local --db C:/db/library.sqlite
npm --prefix .\frontend run build      # mandatory before a commit
```

## GRAPHIFY

`graphify-out/graph.json` is a queryable knowledge graph of this project: about
7000 nodes and 20000 edges over `src/`, `frontend/src/`, `tools/`, `scripts/`,
`tests/`, the documentation pages, and the design rationale under
`.claude/plans/`. Nodes carry `source_file` and `source_location`; edges carry a
relation and an honest confidence tag, `EXTRACTED` or `INFERRED`. A post-commit
git hook rebuilds it, so it tracks `HEAD` without anyone asking.

The graph is a working aid for the agent, not a feature of the product and not
something the user operates. Nobody here types `/graphify`, and no request will
ever ask for it: reach for it on your own, at the moments below, the way you
would reach for a file listing. A SessionStart hook puts the current lessons in
front of you before the first message, and PreToolUse hooks nudge again, but
neither can stop a call — the rule lives here.

| The moment you are about to | Run first |
|---|---|
| Look for where something lives | `graphify query` with expanded tokens |
| Change a shared symbol | `graphify affected "<symbol>"` |
| Work on a symbol you have not read yet | `graphify explain "<symbol>"` |
| Work out how two parts connect | `graphify path "<A>" "<B>"` |
| Get oriented in an unfamiliar area | `graphify god-nodes`, then `explain` |
| Grep or bulk-read across `src/`, `frontend/src/`, `tools/`, `tests/` | any of the above — the grep comes after |

`.codex/skills/graphify/references/query.md` holds the full flow; what follows
is what this project must not get wrong.

### Expand the question against the graph's vocabulary first

The matcher is case-folded substring plus IDF. No stemming, no synonyms, no
cross-language matching. A question phrased in Russian, or in wording the code
does not use, does not come back empty — it comes back with whatever happens to
share a substring, which is worse, because the answer looks real. Asking in
Russian how the analysis manager writes to the database returns saved Q&A notes
about audio dedup, because those notes are the only Russian text in the corpus
and none of the code is. Expansion is what prevents this, so before any
`graphify query`:

1. Refresh the vocabulary and read it:

   ```powershell
   & (Get-Content graphify-out\.graphify_python) -c "import json,re;from pathlib import Path;d=json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'));v=set();[v.add(p.lower()) for n in d['nodes'] for c in re.findall(r'[^\W\d_]+', n.get('label','') or '', re.UNICODE) for p in (re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+', c) or [c]) if 3 <= len(p) <= 30];Path('graphify-out/.vocab.txt').write_text(chr(10).join(sorted(v)),encoding='utf-8');print(len(v),'tokens')"
   ```

2. Pick up to 12 tokens that exist in `graphify-out/.vocab.txt`. Never invent a
   token, and never substitute a synonym from memory. If nothing in the
   vocabulary matches, say the graph has no vocabulary for the question and stop
   rather than running a search that will return noise.
3. Query with the expanded tokens, not the original sentence.

### Pick the command the question calls for

- `graphify explain "<symbol>"` — what a symbol is and everything on both sides
  of it, with `file:line`. The first call for "what is this and who touches it".
- `graphify affected "<symbol>"` — reverse traversal: the blast radius of a
  change, before making it.
- `graphify path "<A>" "<B>"` — how two symbols reach each other.
- `graphify query "<tokens>"` — breadth-first for broad context; add `--dfs` to
  trace one chain. Output is capped at a token budget and says how many nodes it
  cut. A truncated sweep is not an answer: narrow the tokens, filter with
  `--context`, or raise `--budget`.
- `graphify god-nodes` — the architectural hubs.

Then open the files the graph named. Do not reach for it where it holds nothing
to find: `AGENTS.md`, configuration prose, git history, dependency locks, and a
file whose path is already known are faster read directly.

### Close the loop

The graph learns from use, and this only works if every session does its part.

- At the start of graph work, run `graphify reflect --if-stale` and read
  `graphify-out/reflections/LESSONS.md`. It names preferred sources, known dead
  ends, and past corrections.
- After answering from the graph, save the result back:

  ```powershell
  graphify save-result --question "<the user's verbatim question>" --answer "<answer, including the expanded tokens>" --type query --nodes <cited labels> --outcome useful
  ```

  Use `--outcome dead_end` when the traversal led nowhere, and
  `--outcome corrected --correction "<what was right>"` when the graph was
  wrong. An unsaved answer teaches the next session nothing.
- Write that question in English even when it was asked in Russian. The saved
  note becomes a graph node on the next rebuild, and a Russian one turns into
  another magnet for the cross-language mismatch above. The skill's reference
  says verbatim; here, translated wins.

Carry all of this into every sub-agent prompt that explores code; a sub-agent
inherits none of it.

### Corpus and rebuilds

`.graphifyignore` holds what stays out of the graph, and it is the place to fix
a corpus problem — not a filter applied while reading results. The graphify MCP
server needs authorization and is unavailable in a non-interactive session; the
CLI needs none and answers in about a second.

`graphify update .` is not part of an edit loop — see VERIFICATION ROUTING. The
post-commit hook covers normal work; run it by hand only after changing
`.graphifyignore` or deleting a lot of code. Read `GRAPH_REPORT.md` only when
needed; dirty generated graph files are expected.

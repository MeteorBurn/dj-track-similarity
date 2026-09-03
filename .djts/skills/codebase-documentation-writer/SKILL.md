---
name: codebase-documentation-writer
description: Use when documenting MeteorBurn/dj-track-similarity or writing grounded docs from the current codebase.
context: fork
background: false
---

# Codebase Documentation Writer

## Purpose

Use this skill for documentation work in `dj-track-similarity`, which happens
only when the user asks for it. Keep it as a thin routing layer: current source,
tests, `AGENTS.md`, and the maintained docs tree are the source of truth. Do not
duplicate the full project map here.

## When this skill runs

Only when the user asks for documentation work in the session at hand. Nothing
else summons it: not a code change, not a UI change, not a release, not a run of
the verification pass. `AGENTS.md` states the same rule from the other side.

The user asks after a stretch of development rather than after a single change,
so a pass normally covers many commits at once. Treat the request as "bring the
documentation back to the current code", not as "document the last thing that
happened".

## Scoping an on-request pass

Work out what the pass covers before writing anything.

1. Find the base — the last real documentation pass. No marker file records it;
   git does, but the newest commit touching `docs/` is not automatically the
   right base. List the candidates with the size of their documentation change:

   ```powershell
   git log -12 --format=%h -- docs README.md | ForEach-Object {
     $stat = git show --numstat --format='' $_ -- docs README.md
     $n = ($stat | ForEach-Object { $p = $_ -split "`t"; [int]$p[0] + [int]$p[1] } |
           Measure-Object -Sum).Sum
     '{0,6}  {1}  {2}' -f $n, $_, (git log -1 --format=%s $_)
   }
   ```

   It prints each candidate as documentation lines changed, hash, and subject.

   A commit that moved a handful of documentation lines is a fix, not a pass:
   a linter repair, a renamed path, a single corrected sentence. Walk back past
   those to the last commit that actually brought the documentation up to the
   code, and say which base you picked and why. If the user named a starting
   point — a date, a feature, a commit — that wins over anything derived here.

2. List what landed since that commit, and the paths it touched. Include work
   that is not committed yet:

   ```powershell
   git log --oneline <base>..HEAD
   git diff --name-only <base>..HEAD
   git status --short
   ```

3. Drop every path that the exclusion list below covers, then route what remains
   to layers with the routing table.

4. Report the proposed scope — layers, pages, and the commits behind each one —
   and let the user cut it before you write. Write straight away only when the
   scope came out as a single page. A pass that reaches most of the tree is a
   sign the exclusion list was applied too loosely; check it again before
   proposing that much.

Scope the pass by what changed in the code, not by what a page happens to
mention. A page that names a control is not automatically in scope because the
control moved.

### Layer routing

| Changed path | Pages that can own the change |
|---|---|
| `frontend/src/**` | `user-guide/`, `getting-started/first-*.md`, `reference/ui-controls.md` |
| `api_routes_*.py`, `api_schemas.py`, `api.py` | `reference/api.md` |
| `cli.py`, `run_server.cmd`, `scripts/run_server_launcher.py` | `reference/commands.md`, `getting-started/quickstart.md` |
| `db_*.py`, `database*.py` | `reference/database.md` |
| `analysis_*.py`, model runners | `reference/analysis-families.md`, `user-guide/analyze-library.md` |
| `search.py`, `embedding.py`, scoring and ranking | `concepts/similarity-scores.md`, `user-guide/search-with-seeds.md`, `user-guide/text-search.md` |
| `text_embedding_cache.py`, `frontend/src/textPromptPresets.ts` | `user-guide/text-search.md` |
| `tools/<name>/**` | `tools-and-scripts/<name>.md` |
| `scripts/*.py` | `tools-and-scripts/scripts.md` |
| `pyproject.toml`, `uv.lock`, `ffmpeg_runtime.py` | `getting-started/install.md`, `reference/configuration.md` |
| code carrying a safety invariant | `concepts/local-first-safety.md` |
| `AGENTS.md`, `tests/**`, verification routing | `developer/` |

### Never a documentation change

These reach the documentation only when the user asks for them by name. On their
own they are not in scope, however visible they are on screen:

- moving, resizing, recolouring, regrouping, or reordering a control that keeps
  its function
- renaming a label whose meaning did not change
- CSS, class names, icon choice, spacing, wording of on-screen copy
- a default, threshold, limit, or option that is expected to keep moving
- refactors, performance work, and internal renames with no user-visible effect
- new tests, or changes to how existing behavior is verified

A glossary pass over `docs/dj-track-similarity/help/ui-language.md` is its own
request. Do not rewrite the glossary because a label moved; update it when the
interface grew or lost a string and the user asked for the pass.

## First Reads

Read `AGENTS.md` first, then the source, schema, route, or tool files that own
the behavior in scope. They are the grounding for every claim.

Read these only when the pass reaches them:

- `README.md` and `docs/dj-track-similarity/project-guide.md` — when the scope
  is the product overview or the entry pages
- `docs/dj-track-similarity/.vitepress/config.mts` — when a page is added,
  removed, or renamed
- `docs/dj-track-similarity/developer/architecture.md`,
  `developer/development.md`, `developer/testing-and-verification.md` — when the
  developer layer is in scope

## Current Documentation Surface

The maintained docs surface is:

```text
README.md
docs/dj-track-similarity/
```

Do not create a parallel root docs layout such as `docs/api.md` or
`docs/architecture.md`. Use the existing VitePress sections:

```text
getting-started/
user-guide/
workflows/
concepts/
tools-and-scripts/
reference/
developer/
help/
```

There is no locale tree. The Russian mirror under `ru/` was removed in
`97cd4249`; do not bring it back unless the user asks for localization.

When adding a page, update `docs/dj-track-similarity/.vitepress/config.mts` and
the nearest section `index.md` when that section uses one.

## Rules

- Ground non-obvious claims in current source, tests, configs, schemas, routes,
  scripts, or command output.
- If behavior is not proven by the repository, say it is unknown instead of
  guessing.
- Keep public claims modest: this is a local-first DJ-library workbench whose
  model outputs are ranking signals for listening-led shortlisting.
- Preserve local-first safety language from `AGENTS.md`; do not weaken audio,
  SQLite, Audio Doctor, Audio Dedup, Rhythm Lab, classifier, or CLAP scoring
  boundaries.
- Documentation examples in `README.md` and `docs/dj-track-similarity/` should
  use `python ...` or `dj-sim ...`, not hard-coded `.venv` paths.
- Do not edit generated docs output, release notes, legal docs, product code,
  or helper apply/delete modes unless the user explicitly asks.
- Keep README concise and link to deeper docs instead of duplicating reference
  material.

## Documentation language

The documentation is English. The interface itself is a mix of Russian and
English — it grew that way over the course of development, and which label is in
which language is expected to keep moving. That mix is a property of the product,
not of the documentation. Whichever way a label happens to read on screen today,
it reaches a page in English.

- Name every control by its English name, translating the label when the
  interface shows it in Russian. A Russian interface string is not a
  documentation string, so it does not belong in prose, in a heading, in a table
  cell, or in an inline code span.
- `docs/dj-track-similarity/help/ui-language.md` is the single exception and the
  single source of truth. It maps every Russian interface string to its English
  meaning, and that mapping is its whole reason to exist. Reuse its English
  wording verbatim rather than inventing a second name for the same control, and
  add a row there when the interface grows a string the page does not cover.
- Link a page to that glossary once, where it first names a Russian-labelled
  control, so a reader who needs the on-screen string can find it.
- Reserve backticks for strings the interface really shows in English
  (`Analyze`, `Prev`, `Limit`, `Direct`, `Staged`, the tab names, and the rest of
  the English list at the top of the glossary). Write a translated control name
  in bold, so it never reads as text the user will find on screen verbatim.
- `npm run lint:language` in `docs/dj-track-similarity/` fails on Cyrillic
  anywhere outside the glossary. It runs first inside `npm run check`.

## Verification

For Markdown-only docs changes, run, from `docs/dj-track-similarity/`:

```powershell
npm run lint:language
```

and, from the repository root:

```powershell
git diff --check -- README.md docs/dj-track-similarity
```

For maintained docs-site changes, run from `docs/dj-track-similarity/`:

```powershell
npm run check
```

For this skill itself, run a skill validator against
`.djts\skills\codebase-documentation-writer` when the running harness ships one,
and skip the step when it does not. Under Codex that validator is:

```powershell
python "$env:CODEX_HOME\skills\.system\skill-creator\scripts\quick_validate.py" .djts\skills\codebase-documentation-writer
```

If source behavior changes, use the focused verification matrix in `AGENTS.md`
instead of broad default suites.

## Report Format

When done, report:

```markdown
Documentation updated.

Scope:
- base `<sha>`, `N` commits since, layers covered

Changed files:
- `path` - what changed

Left out of scope:
- `change` - why it is not a documentation change, or `None`

Verification:
- `command` - result

Grounding:
- `doc claim` is based on `source path/symbol`

Still unknown:
- `item`, or `None`
```

## Docs scope and environment

Moved here from `AGENTS.md` so it loads only for documentation work.

- Maintained docs are only `README.md` and `docs/dj-track-similarity/` unless the
  user requests another artifact.
- Docs have their own npm environment. From `docs/dj-track-similarity/`, run
  `npm install`; run `npm run vale:sync` after a fresh checkout or Vale-package
  change. Never edit generated `site/` output.
- Do not create architecture notes, changelogs, migration documents, or local
  docs unless explicitly requested. Docs-only changes use docs-only checks.

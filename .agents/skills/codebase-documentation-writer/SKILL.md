---
name: codebase-documentation-writer
description: Use when documenting MeteorBurn/dj-track-similarity or writing grounded docs from the current codebase.
---

# Codebase Documentation Writer

## Purpose

Use this skill for documentation work in `dj-track-similarity`. Keep it as a
thin routing layer: current source, tests, `AGENTS.md`, and the maintained docs
tree are the source of truth. Do not duplicate the full project map here.

## First Reads

For every docs task, start with:

- `AGENTS.md`
- `README.md`
- `docs/dj-track-similarity/project-guide.md`
- `docs/dj-track-similarity/.vitepress/config.mts`
- the source, schema, route, test, or tool files that own the behavior being
  documented

Read the developer docs only when they are in scope:

- `docs/dj-track-similarity/developer/architecture.md`
- `docs/dj-track-similarity/developer/development.md`
- `docs/dj-track-similarity/developer/testing-and-verification.md`

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
ru/
```

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
- English is primary. Keep Russian mirrors under `docs/dj-track-similarity/ru/`
  aligned when the touched maintained docs page has a mirror.

## Verification

For Markdown-only docs changes, run:

```powershell
git diff --check -- README.md docs/dj-track-similarity
```

For maintained docs-site changes, run from `docs/dj-track-similarity/`:

```powershell
npm run check
```

For this skill itself, run a skill validator against
`.agents\skills\codebase-documentation-writer` when the running harness ships one,
and skip the step when it does not. Under Codex that validator is:

```powershell
python "$env:CODEX_HOME\skills\.system\skill-creator\scripts\quick_validate.py" .agents\skills\codebase-documentation-writer
```

If source behavior changes, use the focused verification matrix in `AGENTS.md`
instead of broad default suites.

## Report Format

When done, report:

```markdown
Documentation updated.

Changed files:
- `path` - what changed

Verification:
- `command` - result

Grounding:
- `doc claim` is based on `source path/symbol`

Still unknown:
- `item`, or `None`
```

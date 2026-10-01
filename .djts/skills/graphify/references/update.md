# Graphify reference: project graph maintenance

Project adaptation for Graphify 0.9.73. Follow `../SKILL.md` and
`docs/agent-guides/graphify.md`; commands run from the repository root in
PowerShell 7 after validating the local runtime.

## Routine freshness

Run one native update when a read guard reports stale source, `built_at_commit`
differs from `git rev-parse HEAD`, or relevant uncommitted code changes require
a fresh graph:

```powershell
$env:PYTHONHASHSEED = '0'
& .\.tools\graphify\bin\graphify.exe update .
if ($LASTEXITCODE -ne 0) { throw 'Graphify code update failed.' }
```

This is local AST extraction with no semantic LLM work. The CLI's generic
API-key tip and doc/media-update suggestion do not apply to this code-only
project. Inspect its output: `No code-graph topology changes detected` is a
successful no-op and can leave the graph timestamp or commit stamp unchanged.
A repeated stale-file reminder after that no-op is not a reason to loop.

`update .` replaces the upstream `/graphify --update` manual extraction/merge
runbook. Do not recreate intermediate JSON, hand-edit generated graphs, run
semantic subagents, or replay community-labeling steps. Do not update after
every edit or merely for delivery.

## Full extraction

Use full extraction only for a requested initial build, corpus-rule changes,
substantial deletions, or an authorized extractor upgrade:

```powershell
$env:PYTHONHASHSEED = '0'
& .\.tools\graphify\bin\graphify.exe extract . --code-only
if ($LASTEXITCODE -ne 0) { throw 'Graphify code extraction failed.' }
```

Add `--force` after corpus-exclusion changes to prune newly excluded sources,
or after an extractor upgrade to re-extract unchanged files. Inspect the cause
of any shrink guard before deciding that a forced rebuild is appropriate.
The `--code-only` flag skips new document/media semantic extraction and
preserves any existing semantic layer; it does not prove that the graph's
existing corpus is clean. Check source paths and node types when verifying
corpus boundaries.

Keep `.graphifyignore` as the corpus authority and keep work-memory notes in
`.workspace/graphify/memory/`. Use deterministic hub community names; do not
run `label` or call an LLM to curate them. The CLI owns its generated files.

## Requested reclustering or export

These are separate opt-in tasks. Inspect the installed CLI's options first;
do not replay upstream pipeline steps or assume reclustering is read-only.
`cluster-only` rewrites graph/report outputs, may generate HTML, and can use a
labeling backend when saved labels are absent. It is not routine freshness.
Do not register MCP, create other corpora, or install dependencies as part of
project graph maintenance.

After a graph change, refresh vocabulary when stale and follow the query
reference's project memory policy. Report the commands and results actually
observed; a successful Git commit or installed hook does not establish freshness.

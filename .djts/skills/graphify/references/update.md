# Graphify reference: project graph maintenance

Project adaptation for Graphify 0.9.73. Follow `../SKILL.md` and
`docs/agent-guides/graphify.md`; commands run from the repository root in
PowerShell 7 after validating the local runtime.

## Routine freshness

Run one native update when the guide's freshness triggers apply:

```powershell
$env:PYTHONHASHSEED = '0'
& .\.tools\graphify\bin\graphify.exe update .
if ($LASTEXITCODE -ne 0) { throw 'Graphify code update failed.' }
```

Set `$env:PYTHONHASHSEED = '0'` for every `update` and `extract` run,
as shown: the Git hooks pin it, and community numbering stays comparable
between hook and agent rebuilds only under the same seed. The CLI also
defaults an unset seed to `0`; keep the explicit setting so an inherited
value cannot change the project convention.

This is local AST extraction that takes seconds and does no semantic LLM work.
The CLI's generic API-key tip and doc/media-update suggestion do not apply to
this code-only project. Inspect its output: the update is idempotent, and
`No code-graph topology changes detected` is a successful no-op meaning the
edit was not structural; it can leave the graph timestamp or commit stamp
unchanged. The read guard may keep flagging the edited file until a later
structural rebuild rewrites `graph.json`; ignore that repeated reminder
instead of looping.

`update .` replaces the upstream `/graphify --update` manual extraction/merge
runbook: the corpus is code-only, so its semantic branches never apply. Do not
recreate intermediate JSON, hand-edit generated graphs, run semantic
subagents, or replay community-labeling steps.

## Full extraction

Use full extraction only in the cases the guide lists:

```powershell
$env:PYTHONHASHSEED = '0'
& .\.tools\graphify\bin\graphify.exe extract . --code-only
if ($LASTEXITCODE -ne 0) { throw 'Graphify code extraction failed.' }
```

Add `--force` after corpus-exclusion changes to prune newly excluded sources,
which are otherwise kept fail-closed, or after an extractor upgrade to
re-extract unchanged files with the new implementation. Inspect the cause of
any shrink guard before deciding that a forced rebuild is appropriate.
The `--code-only` flag skips new document/media semantic extraction and
preserves any existing semantic layer; it does not prove that the graph's
existing corpus is clean. Check source paths and node types when verifying
corpus boundaries.

Use deterministic hub community names; do not run `label` or call an LLM to
curate them. The CLI owns its generated files.

## Requested reclustering or export

These are separate opt-in tasks. Inspect the installed CLI's options first;
do not replay upstream pipeline steps or assume reclustering is read-only.
`cluster-only` rewrites graph/report outputs, may generate HTML, and can use a
labeling backend when saved labels are absent. It is not routine freshness.
Do not register MCP, create other corpora, or install dependencies as part of
project graph maintenance.

After a graph change, follow the guide's vocabulary and memory policy. Report
the commands and results actually observed; a successful Git commit or
installed hook does not establish freshness.

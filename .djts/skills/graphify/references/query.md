# Graphify reference: project queries and work memory

Project adaptation for Graphify 0.9.73. Follow `../SKILL.md` and
`docs/agent-guides/graphify.md`; run commands from the repository root in
PowerShell 7 after the skill's runtime check.

## Select a focused query

Use the existing graph and read `graphify-out/reflections/LESSONS.md` when prior
lessons are useful. Missing lessons never block inspection. Refresh
`graphify-out/.vocab.txt` only when it is older than `graph.json`, using the
guide's snippet; if absent, derive tokens from graph labels in memory.

Select up to 12 actual vocabulary tokens, preferably 3-6 English tokens that
match the user's intent. The matcher has no stemming, synonyms, or translation.
Explain a non-obvious expansion briefly. If no tokens fit, report that limit
and inspect source directly rather than inventing a graph match.

```powershell
& .\.tools\graphify\bin\graphify.exe query '<expanded tokens>' --budget 8000
if ($LASTEXITCODE -ne 0) { throw 'Graphify query failed.' }
```

BFS is the default. Add `--dfs` for a deeper traversal, but do not treat it as
an exact source-to-target path search. For call relationships, restrict the
edge context:

```powershell
& .\.tools\graphify\bin\graphify.exe query '<expanded tokens>' --context call --budget 8000
if ($LASTEXITCODE -ne 0) { throw 'Graphify call query failed.' }
```

Use `--budget 8000` unless the user specifies another budget; this overrides
the CLI default of 2000. The budget is an approximate output target, not a
hard cap. Allow at least 12000 output tokens in the calling tool. This does
not guarantee that all output fits: Graphify can emit
`Complete answer over budget` when all nodes fit and it retains every
connecting edge. Narrow with `--context call` for calls or use `explain`;
increasing the budget cannot shrink this output.

`TRUNCATED` means Graphify omitted nodes, and a tool-level truncation means
the agent has not read the full result; treat both as incomplete. Narrow the
query or use `explain` before treating the result as complete; increase the
query budget only when the user specifies another budget. If the calling tool
truncates an otherwise complete Graphify response, narrow the query as well
or raise that tool's output allowance.

If only the executable launcher is unavailable but the verified project
interpreter imports Graphify, invoke the same CLI through its module with the
same budget:

```powershell
& $graphPython -m graphify query '<expanded tokens>' --budget 8000
if ($LASTEXITCODE -ne 0) { throw 'Graphify module query failed.' }
```

Do not recreate the traversal in a second implementation. If the runtime is
unavailable, inspect `graph.json` as JSON and verify cited files directly,
reporting that CLI navigation could not be checked.

## Inspect exact symbols and callers

```powershell
& .\.tools\graphify\bin\graphify.exe explain '<path::Symbol>'
if ($LASTEXITCODE -ne 0) { throw 'Graphify explain failed.' }
& .\.tools\graphify\bin\graphify.exe affected '<exact node ID>' --relation calls --depth 1
if ($LASTEXITCODE -ne 0) { throw 'Graphify affected query failed.' }
```

Use depth `2` only when the next caller level is relevant. Resolve ambiguous
labels with exact IDs in `graph.json`; use its `links` array when inspecting
directed relationships.

`path` uses fuzzy endpoint matching in 0.9.73: it picks endpoints by token
scoring instead of exact-ID lookup, splits a full node ID into tokens, does
not recognize `path::Symbol`, and often resolves an endpoint to a module,
parent class, or other code node. `No path` or `No directed path` is therefore
not evidence that a relationship is absent. To trace a connection, use a
scoped `explain` with the exact ID or `path::Symbol`, or inspect exact node
IDs and directed `links` in `graph.json` with the project Graphify interpreter,
then verify the source. For incoming calls, use `affected`.

Read each relevant `source_file` and `source_location`. Graph edges, including
`EXTRACTED` and `INFERRED` edges, are navigation leads. Distinguish graph output,
confirmed source behavior, and any runtime behavior actually exercised.

## Save source-grounded findings

Decide what to save under the guide's memory policy. Both the question and
answer must be English, even when the user writes in Russian; this overrides
upstream's rule to save the original question. Include the expanded tokens,
cited node labels, and verified source locations. Do not save a plausible
graph interpretation as a confirmed fact.

Use an argument array for text; replace the placeholders before execution:

```powershell
$graphMemoryArguments = @(
    'save-result',
    '--memory-dir', '.workspace/graphify/memory',
    '--question', '<English question>',
    '--answer', '<English source-grounded answer, tokens, and source locations>',
    '--type', 'query',
    '--outcome', 'useful',
    '--nodes', '<cited node label>'
)
& .\.tools\graphify\bin\graphify.exe @graphMemoryArguments
if ($LASTEXITCODE -ne 0) { throw 'Graphify result save failed.' }
& .\.tools\graphify\bin\graphify.exe reflect --if-stale --memory-dir '.workspace/graphify/memory'
if ($LASTEXITCODE -ne 0) { throw 'Graphify reflection failed.' }
```

Set the actual outcome to `useful`, `dead_end`, or `corrected`; for a correction,
append `--correction` and its English text to the argument array. Use type
`explain` for a node explanation. If no new note qualifies, still run the
reflection command after the investigation under the guide's memory policy.

Always pass this `--memory-dir` to both commands. Notes stay outside the code
corpus; reflection writes `graphify-out/reflections/LESSONS.md` and its overlay
beside the graph. Never use or recreate `graphify-out/memory/`: upstream's
update path force-scans it and would add documentation nodes to the code graph.

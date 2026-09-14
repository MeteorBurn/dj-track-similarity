# Graphify navigation

Read before using Graphify for unfamiliar architecture, relationships, or change
impact. Read known files, symbols, and configuration directly or locate them with `rg`.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## GRAPHIFY

`graphify-out/graph.json` assists navigation over product source, tests, tools,
scripts, and documentation. Read cited `source_file`/`source_location`; graph
edges (`EXTRACTED`/`INFERRED`) are leads, not current runtime proof.
Use it when relationships or unfamiliar architecture help answer the question;
there is no mandatory graph step before a known file or symbol lookup. Read
`AGENTS.md`, configuration, locks, Git state, and the excluded agent layer directly.

Routine lookups use the existing graph. Read vocabulary and lessons only when
they help; do not run `reflect`, vocabulary regeneration, `save-result`, or a
rebuild for each lookup. Refresh vocabulary with an authorized graph update;
reflection and saved findings belong to explicit graph memory maintenance. Read-only
tasks never run these write steps. If vocabulary is missing or stale, derive
tokens from graph labels in memory. Missing lessons do not block inspection.
Report stale or unavailable graph data and verify findings directly in source.

| Navigation task | Tool |
|---|---|
| Locate an unfamiliar area | MCP `query_graph`, or `graphify query "<expanded tokens>"` |
| Inspect a graph node and its neighbors | MCP `get_node` / `get_neighbors` with the exact node ID; CLI fallback: `graphify explain "<path::Symbol>"` |
| Inspect affected callers | `graphify affected "<node_id>" --relation calls --depth 1` (use depth `2` for the next caller level) |
| Trace a connection | Inspect exact-node neighbors and the cited source; see the path limitation below |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

Prefer the already connected MCP server for repeated graph queries. In Graphify
0.9.61, CLI `path` and MCP `shortest_path` can resolve endpoints to semantic memory
instead of code. Full code IDs do not reliably disambiguate those endpoints.
Do not treat `No path` as evidence that a relationship is absent. Use exact IDs
with `get_node` / `get_neighbors`, or a scoped CLI `explain`, and verify the source.
For call relationships, use `get_neighbors` with `relation_filter="calls"` and
read the edge arrows, or `affected` as above for incoming calls.

Follow `.djts/skills/graphify/references/query.md` with these project rules:

1. Use the connected MCP server or installed CLI; for Python helpers, read and
   validate the interpreter in `graphify-out/.graphify_python`. It belongs to Graphify's external tool
   environment. Do not install Graphify into the project or blindly run
   `graphify install`, which can overwrite project instructions/hooks.
2. Read `graphify-out/reflections/LESSONS.md` when prior query lessons are useful.
   Hook configuration alone does not prove a hook ran in the current harness.
3. For a token query, use `.vocab.txt` or graph labels. Select up to 12
   actual vocabulary tokens (prefer 3-6 English tokens). Matching has no stemming,
   synonyms, or cross-language translation. If none fit, stop that graph search
   and use direct source inspection; do not submit a misleading query.
4. Use `--dfs` for a chain. Treat `TRUNCATED` as incomplete: narrow the query,
   use `explain`, or increase `--budget`. Disambiguate repeated labels with the
   exact node ID through `get_node` / `get_neighbors`. Open the named source
   before drawing conclusions.
5. When explicitly maintaining graph memory, use `save-result` with the expanded
   tokens, cited labels, and `--outcome useful|dead_end|corrected`; for a correction add
   `--correction`. Both the saved question and answer must be English even when
   the user's request is Russian; this overrides the reference's verbatim rule.
6. Pass the relevant graph rules to code-exploration workers explicitly; do not
   assume their prompts or tool access match the parent session.

PowerShell vocabulary refresh (during an authorized graph update):

```powershell
$graphPython = (Get-Content -LiteralPath 'graphify-out\.graphify_python' -Raw).Trim()
if (-not (Test-Path -LiteralPath $graphPython -PathType Leaf)) { throw 'Graphify interpreter missing' }
@'
import json, re
from pathlib import Path
data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
vocab = set()
for node in data['nodes']:
    for word in re.findall(r'[^\W\d_]+', node.get('label', '') or '', re.UNICODE):
        for part in re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+', word) or [word]:
            if 3 <= len(part) <= 30:
                vocab.add(part.lower())
Path('graphify-out/.vocab.txt').write_text('\n'.join(sorted(vocab)), encoding='utf-8')
'@ | & $graphPython -
if ($LASTEXITCODE -ne 0) { throw 'Graph vocabulary refresh failed' }
```

`.graphifyignore` owns corpus exclusions, including `.workspace/`, `.djts/`,
`.agents/`, `.claude/`, and `.codex/`. Fix corpus scope there, not by hiding
unwanted hits. The local post-commit hook starts code rebuilds in the background
and skips linked worktrees and some Git operations; a commit does not prove the
graph is current. Check hook output/freshness when it matters.

Do not run `graphify update .` in the edit loop or as a routine delivery check;
manual rebuilds are for corpus-exclusion changes or substantial code deletions.
If the graph/tool is unavailable or stale, report that limit and inspect source
without assuming permission to install or rebuild. Read `GRAPH_REPORT.md` only
when needed; preserve unrelated generated changes.

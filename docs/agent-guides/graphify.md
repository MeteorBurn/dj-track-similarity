# Graphify navigation

Before exploring or changing repository code, read and apply
`.djts/skills/graphify/SKILL.md` and this guide. Start source discovery with a
focused query against the existing graph, then inspect the cited source.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## GRAPHIFY

`graphify-out/graph.json` assists navigation over product source, tools, and
scripts. Tests, project documentation, and media are excluded; notes under
`.workspace/graphify/memory/` feed the work-memory loop (`reflect`, the
`explain` overlay). Locate tests by naming convention (`tests/test_<module>.py`,
`*.test.mjs`) with direct search. Read cited `source_file`/`source_location`; graph
edges (`EXTRACTED`/`INFERRED`) are leads, not current runtime proof.
`AGENTS.md` and this guide own the query-first rule for source discovery.
Tasks confined to instructions, configuration, locks, Git state, or the excluded
agent layer use direct inspection; those files are outside the code graph.
Codex's `.codex/hooks.json` has no Graphify search reminder: the native guard
cannot distinguish these exceptions and emits an unconditional instruction.
Claude deliberately keeps its native search/read guards; they are equally
unconditional: the read guard also fires on project `.md` files and the search
guard on any `rg`/`grep`. Their reminder never overrides this guide: excluded
files are inspected directly, and graph commands follow the invocation rule
below and the budget and `path` rules of the query reference,
`.djts/skills/graphify/references/query.md`. Hook setup belongs to the
[agent-layer guide](agent-layer.md); do not add a wrapper or duplicate rules.

The agent maintains the graph while using it; the owner runs nothing by hand.
Maintenance writes only `graphify-out/` and `.workspace/graphify/`, both local
and ignored, so they are allowed in read-only tasks:

- Freshness: run `update .` once before querying when the read guard flags a
  stale file, `built_at_commit` in `graph.json` differs from
  `git rev-parse HEAD`, or the working tree holds uncommitted code changes.
  Run a full `extract` only for a requested initial build, corpus-rule
  changes, substantial code deletions, or an authorized extractor upgrade.
  Never rebuild after every edit or as a delivery check. Follow
  `.djts/skills/graphify/references/update.md` for the commands and output
  handling.
- Vocabulary: refresh `.vocab.txt` (snippet below) whenever it is older than
  `graph.json`; if it is missing, derive tokens from graph labels in memory.
- Memory: after a graph-guided investigation, always save `dead_end` and
  `corrected` outcomes, and save `useful` findings only when `LESSONS.md` does
  not already list the cited source; then reflect. Notes live in
  `.workspace/graphify/memory/`, never `graphify-out/memory/`; the query
  reference gives the commands.

Missing lessons or vocabulary never block inspection. Verify findings directly
in source; mention graph limitations only when they affect the result.

| Navigation task | Tool |
|---|---|
| Locate an unfamiliar area | `graphify query "<expanded tokens>" --budget 8000` |
| Narrow a query to call relationships | `graphify query "<expanded tokens>" --context call --budget 8000` |
| Inspect a graph node and its neighbors | `graphify explain "<path::Symbol>"`; inspect exact IDs in `graph.json` when ambiguous |
| Inspect affected callers | `graphify affected "<node_id>" --relation calls --depth 1` (use depth `2` for the next caller level) |
| Trace a connection | Inspect exact-node neighbors and the cited source; see the query reference's `path` limitation |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

Run graph commands through the repository-local CLI
`.\.tools\graphify\bin\graphify.exe`, as the skill's runtime check verifies;
this project uses no Graphify MCP server. Never register Graphify globally,
add it to user/system PATH, or run `graphify install`, which can overwrite
project instructions and hooks. Follow
`.djts/skills/graphify/references/query.md` for token selection, budgets and
truncation, the `path` limitation, exact-symbol inspection, and saving
results. Pass the relevant graph rules to code-exploration workers explicitly;
do not assume their prompts or tool access match the parent session.

PowerShell vocabulary refresh (run when `.vocab.txt` is older than `graph.json`):

```powershell
$graphPython = (Resolve-Path -LiteralPath '.tools/graphify/graphifyy/Scripts/python.exe' -ErrorAction Stop).Path
if (Test-Path -LiteralPath 'graphify-out/.graphify_python' -PathType Leaf) {
    $savedGraphPython = (Get-Content -LiteralPath 'graphify-out/.graphify_python' -Raw).Trim()
    if ((Resolve-Path -LiteralPath $savedGraphPython -ErrorAction Stop).Path -ne $graphPython) {
        throw 'Graphify interpreter marker does not match the project runtime'
    }
}
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

`.graphifyignore` owns corpus exclusions, including tests (`tests/`,
`*.test.mjs`), documentation/media, `.workspace/`, `.djts/`, `.agents/`,
`.claude/`, and `.codex/`. The entire
`docs/dj-track-similarity/` tree is excluded: it is not maintained as current
documentation. Fix corpus scope there, not by hiding unwanted hits.

Recheck remembered findings against source; the unmaintained documentation
site is not current evidence. Git hook maintenance follows
`.djts/skills/graphify/references/hooks.md`; package upgrades and plugin
refresh follow the [agent-layer guide](agent-layer.md). Read `GRAPH_REPORT.md`
only when needed; preserve unrelated generated changes.

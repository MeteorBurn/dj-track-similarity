# Graphify navigation

Read before broad source discovery or using Graphify. Known files and configuration can be read directly.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## GRAPHIFY

`graphify-out/graph.json` assists navigation over product source, tests, tools,
scripts, and documentation. Read cited `source_file`/`source_location`; graph
edges (`EXTRACTED`/`INFERRED`) are leads, not current runtime proof.
Use it proactively before broad source searches. Known files, `AGENTS.md`,
configuration, locks, Git state, and the excluded agent layer are read directly.

For read-only tasks or modes, use the existing graph, vocabulary and lessons
without running the write steps below: vocabulary refresh, `reflect`,
`save-result` or rebuilds. If vocabulary is missing or stale, derive tokens from
graph labels in memory. Missing lessons do not block inspection. Report stale
or unavailable graph data and verify findings directly in source.

| Navigation task | Run first |
|---|---|
| Locate an area | `graphify query "<expanded tokens>"` |
| Inspect a symbol and its neighbors | `graphify explain "<symbol>"` |
| Assess a shared-symbol change | `graphify affected "<symbol>"` |
| Trace a connection | `graphify path "<A>" "<B>"` |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

Follow `.djts/skills/graphify/references/query.md` with these project rules:

1. Use the installed CLI; for Python helpers, read and validate the interpreter
   in `graphify-out/.graphify_python`. It belongs to Graphify's external tool
   environment. Do not install Graphify into the project or blindly run
   `graphify install`, which can overwrite project instructions/hooks.
2. At the start of graph work, run `graphify reflect --if-stale` and read
   `graphify-out/reflections/LESSONS.md`. Hook configuration alone does not
   prove a hook ran in the current harness.
3. Before `query`, refresh/read `.vocab.txt` from graph labels. Select up to 12
   actual vocabulary tokens (prefer 3-6 English tokens). Matching has no stemming,
   synonyms, or cross-language translation. If none fit, stop that graph search
   and use direct source inspection; do not submit a misleading query.
4. Use `--dfs` for a chain. Treat `TRUNCATED` as incomplete: narrow the query,
   use `explain`, or increase `--budget`. Disambiguate repeated labels with the
   full node ID. Open the named source before drawing conclusions.
5. Save a graph-derived finding with `save-result`: include the expanded tokens,
   cited labels, and `--outcome useful|dead_end|corrected`; for a correction add
   `--correction`. Both the saved question and answer must be English even when
   the user's request is Russian; this overrides the reference's verbatim rule.
6. Pass the relevant graph rules to code-exploration workers explicitly; do not
   assume their prompts or tool access match the parent session.

PowerShell vocabulary refresh (when writes are allowed and the graph exists):

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

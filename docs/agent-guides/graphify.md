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
`AGENTS.md` routes code work through this guide and the plugin skill. Claude's
upstream PreToolUse guards add query-first reminders. Codex's upstream
`hook-check` is a no-op in 0.9.61; its standing rule comes from these instructions.
Tasks confined to `AGENTS.md`, configuration, locks, Git state, or the excluded
agent layer use direct inspection; those files are outside the code graph.

The agent maintains the graph while using it; the owner runs nothing by hand.
Maintenance writes only `graphify-out/` and `.workspace/graphify/`, both local
and ignored, so they are allowed in read-only tasks:

- Freshness: when the read guard flags a stale file, `built_at_commit` in
  `graph.json` differs from `git rev-parse HEAD`, or the working tree holds
  uncommitted code changes, run `update .` once before querying (AST only,
  seconds, no LLM; set `$env:PYTHONHASHSEED = '0'`). It is idempotent:
  "No code-graph topology changes detected" means the edit was not structural,
  and the guard may keep flagging that file until a later structural rebuild
  rewrites `graph.json`; ignore it then. Do not run `update .` after every
  edit or as a delivery check. The CLI `update .` replaces the skill's
  `--update` runbook here: the corpus is code-only, so the runbook's semantic
  branches never apply.
- Vocabulary: refresh `.vocab.txt` (snippet below) whenever it is older than
  `graph.json`; if it is missing, derive tokens from graph labels in memory.
- Memory: after a graph-guided investigation, always save `dead_end` and
  `corrected` outcomes, and save `useful` findings only when `LESSONS.md` does
  not already list the cited source; then run
  `reflect --if-stale --memory-dir .workspace/graphify/memory`.

Missing lessons or vocabulary never block inspection. Report stale or
unavailable graph data and verify findings directly in source.

| Navigation task | Tool |
|---|---|
| Locate an unfamiliar area | `graphify query "<expanded tokens>" --budget 8000` |
| Inspect a graph node and its neighbors | `graphify explain "<path::Symbol>"`; inspect exact IDs in `graph.json` when ambiguous |
| Inspect affected callers | `graphify affected "<node_id>" --relation calls --depth 1` (use depth `2` for the next caller level) |
| Trace a connection | Inspect exact-node neighbors and the cited source; see the path limitation below |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

This project uses the CLI without a Graphify MCP server. In Graphify 0.9.61,
`path` can resolve endpoints to semantic memory instead of code. Full code IDs
do not reliably disambiguate those endpoints. Do not treat `No path` as evidence
that a relationship is absent. Use a scoped `explain`, or inspect exact node IDs
and directed `links` in `graph.json` with the project Graphify interpreter, then
verify the source. For incoming call relationships, use `affected` as above.

Follow `.djts/skills/graphify/references/query.md` with these project rules:

1. Use `.\.tools\graphify\bin\graphify.exe` for the
   CLI commands below. For Python helpers, read and validate the interpreter in
   `graphify-out/.graphify_python`; it must point into `.tools/graphify/` in this
   repository. Keep the package separate from the application environment.
   Never register Graphify globally or add it to user/system PATH. Do not blindly
   run `graphify install`, which can overwrite project instructions/hooks.
2. Read `graphify-out/reflections/LESSONS.md` when prior query lessons are useful.
   Hook configuration alone does not prove a hook ran in the current harness.
3. For a token query, use `.vocab.txt` or graph labels. Select up to 12
   actual vocabulary tokens (prefer 3-6 English tokens). Matching has no stemming,
   synonyms, or cross-language translation. If none fit, stop that graph search
   and use direct source inspection; do not submit a misleading query.
4. Pass `--budget 8000` on every query unless the user specifies another budget;
   use the same budget for the inline fallback. This overrides the CLI and skill
   reference defaults of 2000. Allow at least 12000 output tokens in the calling
   tool so it does not truncate Graphify's response before the agent reads it.
   Use `--dfs` for a chain. Treat `TRUNCATED` as incomplete: narrow the query,
   use `explain`, or increase `--budget`. Disambiguate repeated labels with the
   exact node ID in `graph.json`. Open the named source
   before drawing conclusions.
5. Save source-grounded code findings (memory policy above)
   with `save-result --memory-dir .workspace/graphify/memory`, expanded tokens,
   cited labels, and `--outcome useful|dead_end|corrected`; for a correction add
   `--correction`.
   Both the saved question and answer must be English even when the user's
   request is Russian; this overrides the reference's verbatim rule.
6. Pass the relevant graph rules to code-exploration workers explicitly; do not
   assume their prompts or tool access match the parent session.

PowerShell vocabulary refresh (run when `.vocab.txt` is older than `graph.json`):

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

`.graphifyignore` owns corpus exclusions, including tests (`tests/`,
`*.test.mjs`), documentation/media, `.workspace/`, `.djts/`, `.agents/`,
`.claude/`, and `.codex/`. The entire
`docs/dj-track-similarity/` tree is excluded: it is not maintained as current
documentation. Fix corpus scope there, not by hiding unwanted hits.

For a full re-extraction after corpus-rule changes or substantial deletions, use
`& .\.tools\graphify\bin\graphify.exe extract . --code-only`. This skips
document/media semantic extraction and preserves the existing semantic layer.
Add `--force` after corpus-exclusion changes so newly excluded sources are
pruned instead of kept fail-closed. Set `$env:PYTHONHASHSEED = '0'` for every
`extract`/`update`/`label` run: the Git hooks pin it, and community numbering
only stays comparable between hook and agent rebuilds under the same seed.
Community names are deterministic hub names; skip the skill's Step 5 and
`label`, since any topology change renumbers communities and drops curated
names.
Saved Q&A lives in `.workspace/graphify/memory/`, outside the scan corpus:
Graphify force-scans its default `graphify-out/memory/`, and the post-commit
`update` path would index those notes as `document` nodes. Do not recreate that
default directory; pass `--memory-dir` to `save-result` and `reflect`, which
keep `graphify-out/reflections/LESSONS.md` and the `explain` overlay next to the
graph. Recheck remembered findings against source; the unmaintained
documentation site is not current evidence.

The local post-commit hook starts code rebuilds in the background
and skips linked worktrees and some Git operations; a commit does not prove the
graph is current. Check hook output/freshness when it matters.

Routine freshness is `update .` under the maintenance policy above; a full
`extract` is only for corpus-rule changes or substantial code deletions.
If the graph/tool is unavailable, report that limit and inspect source
without assuming permission to install. Read `GRAPH_REPORT.md` only
when needed; preserve unrelated generated changes.

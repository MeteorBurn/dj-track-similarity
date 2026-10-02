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
Claude retains its native search/read guards. Hook setup belongs to the
[agent-layer guide](agent-layer.md); do not add a wrapper or duplicate rules.

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

Missing lessons or vocabulary never block inspection. Verify findings directly
in source; mention graph limitations only when they affect the result.

| Navigation task | Tool |
|---|---|
| Locate an unfamiliar area | `graphify query "<expanded tokens>" --budget 8000` |
| Narrow a query to call relationships | `graphify query "<expanded tokens>" --context call --budget 8000` |
| Inspect a graph node and its neighbors | `graphify explain "<path::Symbol>"`; inspect exact IDs in `graph.json` when ambiguous |
| Inspect affected callers | `graphify affected "<node_id>" --relation calls --depth 1` (use depth `2` for the next caller level) |
| Trace a connection | Inspect exact-node neighbors and the cited source; see the path limitation below |
| Orient in unfamiliar architecture | `graphify god-nodes`, then `explain` |

This project uses the CLI without a Graphify MCP server. In Graphify 0.9.73,
`path` picks endpoints by token scoring, not exact-ID lookup: it splits a full
node ID into tokens, does not recognize `path::Symbol`, and often resolves an
endpoint to a module, parent class, or other code node. Do not treat `No path`
or `No directed path` as evidence that a relationship is absent. Use a scoped
`explain` with the exact ID or `path::Symbol`, or inspect exact node IDs and
directed `links` in `graph.json` with the project Graphify interpreter, then
verify the source. For incoming call relationships, use `affected` as above.

Follow `.djts/skills/graphify/references/query.md` with these project rules:

1. Use `.\.tools\graphify\bin\graphify.exe` for the
   CLI commands below. Python helpers use the verified
   `.tools/graphify/graphifyy/Scripts/python.exe`. If
   `graphify-out/.graphify_python` exists, validate that it resolves to this
   interpreter; an absent marker does not require a write during inspection.
   Keep the package separate from the application environment.
   Never register Graphify globally or add it to user/system PATH. Do not blindly
   run `graphify install`, which can overwrite project instructions/hooks.
2. Read `graphify-out/reflections/LESSONS.md` when prior query lessons are useful.
   Hook configuration alone does not prove a hook ran in the current harness.
3. For a token query, use `.vocab.txt` or graph labels. Select up to 12
   actual vocabulary tokens (prefer 3-6 English tokens). Matching has no stemming,
   synonyms, or cross-language translation. If none fit, stop that graph search
   and use direct source inspection; do not submit a misleading query.
4. Pass `--budget 8000` on every query unless the user specifies another budget;
   use the same budget when invoking the CLI through the project Python module.
   This overrides the CLI default of 2000. Allow at least 12000 output tokens
   in the calling tool. The budget is an approximate target: `Complete answer
   over budget` means all nodes fit and Graphify retained every connecting
   edge, so the response can still exceed the tool's output limit. Narrow call
   queries with `--context call` or use `explain`; increasing the budget will
   not shrink that result. Use `--dfs` for a deeper traversal. Treat `TRUNCATED`
   and tool-level truncation as incomplete: narrow the query, use `explain`, or
   increase the output allowance when appropriate. Disambiguate labels with the
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

For a full re-extraction after corpus-rule changes, substantial deletions, or an
authorized extractor upgrade, use
`& .\.tools\graphify\bin\graphify.exe extract . --code-only`. This skips
document/media semantic extraction and preserves the existing semantic layer.
Add `--force` after corpus-exclusion changes so newly excluded sources are
pruned instead of kept fail-closed, and after extractor upgrades so unchanged
files are re-extracted with the new implementation.
Set `$env:PYTHONHASHSEED = '0'` for every `extract`/`update`/`label` run: the Git hooks pin it, and community numbering
only stays comparable between hook and agent rebuilds under the same seed.
The CLI also defaults an unset seed to `0`; retain the explicit setting so an
inherited value cannot change the project convention.
Community names are deterministic hub names; do not run `label` or replay
upstream community-labeling steps.
Saved Q&A lives in `.workspace/graphify/memory/`, outside the scan corpus:
Graphify force-scans its default `graphify-out/memory/`, and the post-commit
`update` path would index those notes as `document` nodes. Do not recreate that
default directory; pass `--memory-dir` to `save-result` and `reflect`, which
keep `graphify-out/reflections/LESSONS.md` and the `explain` overlay next to the
graph. Recheck remembered findings against source; the unmaintained
documentation site is not current evidence.

The local post-commit hook starts code rebuilds in the background
and skips linked worktrees and some Git operations; a commit does not prove the
graph is current. Check hook output/freshness when it matters. During authorized
package maintenance, run `hook status`: it detects outdated Git hook templates.
Refresh those with `hook install`, preserving unrelated hook content, then check
status again. A package upgrade alone does not rewrite installed Git hooks.
Compare the CLI and installed package version with the canonical skill's
`.graphify_version`; review upstream changes before updating that marker.
Refresh and compare both plugin caches after skill changes, following the
agent-layer guide. The project plugin's version is independent of Graphify's.

Routine freshness is `update .` under the maintenance policy above; a full
`extract` is only for corpus-rule changes, substantial code deletions, or an
authorized extractor upgrade.
If the graph/tool is unavailable, inspect source without installing a replacement;
report the limit only if it affects the result. Read `GRAPH_REPORT.md` only
when needed; preserve unrelated generated changes.

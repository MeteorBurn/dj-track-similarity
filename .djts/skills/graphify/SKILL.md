---
name: graphify
description: "Use for dj-track-similarity codebase questions, architecture, file relationships, and source discovery against its existing graph. Available only for C:/projects/dj-track-similarity through the project plugin."
---

# Graphify for dj-track-similarity

This is the project adaptation of Graphify 0.9.73. Work only from
`C:\projects\dj-track-similarity` in PowerShell 7. Read `AGENTS.md` and
`docs/agent-guides/graphify.md` before graph work; their corpus, freshness,
memory, and verification rules govern this skill.

The graph covers code. It helps locate source and relationships; inspect the
cited source before claiming current behavior. Documentation, tests, media,
agent configuration, and working notes are outside the graph corpus.

## Runtime and version check

Use the repository-local CLI and interpreter. At first use in a session, verify
their paths and compare the CLI/package version with this skill's marker:

```powershell
$ErrorActionPreference = 'Stop'
if ((Resolve-Path -LiteralPath '.').Path -ne 'C:\projects\dj-track-similarity') {
    throw 'Run this skill from the dj-track-similarity repository root.'
}
$graphPython = (Resolve-Path -LiteralPath '.tools/graphify/graphifyy/Scripts/python.exe').Path
if (Test-Path -LiteralPath 'graphify-out/.graphify_python' -PathType Leaf) {
    $savedGraphPython = (Get-Content -LiteralPath 'graphify-out/.graphify_python' -Raw).Trim()
    if ((Resolve-Path -LiteralPath $savedGraphPython).Path -ne $graphPython) {
        throw 'Graphify interpreter marker does not match the project runtime.'
    }
}
if (Test-Path -LiteralPath '.tools/graphify/bin/graphify.exe' -PathType Leaf) {
    $graphifyCommand = (Resolve-Path -LiteralPath '.tools/graphify/bin/graphify.exe').Path
    $graphifyCliVersion = (& $graphifyCommand --version | Out-String).Trim()
} else {
    $graphifyCliVersion = (& $graphPython -m graphify --version | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Graphify CLI version check failed.' }
$graphifyPackageVersion = (& $graphPython -c 'from importlib.metadata import version; print(version("graphifyy"))' | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Graphify package version check failed.' }
$graphifySkillVersion = (Get-Content -LiteralPath '.djts/skills/graphify/.graphify_version' -Raw).Trim()
if ($graphifyCliVersion -ne "graphify $graphifyPackageVersion" -or $graphifySkillVersion -ne $graphifyPackageVersion) {
    throw 'Graphify runtime and project skill versions differ; review the skill before refreshing its marker and plugin caches.'
}
```

A missing runtime or mismatch is a maintenance finding. Continue independent
source inspection, but leave dependent graph verification unresolved. Do not
install a replacement, rewrite a marker merely to suppress the finding, add
Graphify to PATH, or modify the application's `.venv`. Reuse successful checks
until the runtime or skill changes. A missing interpreter marker does not block
the verified local interpreter and does not need a write during inspection.

## Navigation

For a code question, use the existing `graphify-out/graph.json` after the
guide's freshness check. Do not run the upstream extraction pipeline, corpus
survey, community labeling, or exports as a prelude to a query. If the graph is
unavailable, report that limit and inspect source; a question alone does not
authorize installing Graphify or building a new graph.

Read [references/query.md](references/query.md) for vocabulary selection,
bounded navigation, source verification, and the project memory loop.

```powershell
& .\.tools\graphify\bin\graphify.exe query '<expanded vocabulary tokens>' --budget 8000
& .\.tools\graphify\bin\graphify.exe query '<expanded vocabulary tokens>' --context call --budget 8000
& .\.tools\graphify\bin\graphify.exe explain '<path::Symbol>'
& .\.tools\graphify\bin\graphify.exe affected '<exact node ID>' --relation calls --depth 1
```

The budget is an approximate output target, not a hard cap. Narrow an oversized
query with `--context call` when investigating calls, or use `explain` for a
specific symbol. `TRUNCATED` output is incomplete; a tool-level truncation also
means the agent has not read the full result. A failed fuzzy `path` lookup is
not proof that no code relationship exists.

## Maintenance and integrations

- Read [references/update.md](references/update.md) for the native `update .`
  and `extract . --code-only` routes. Use the guide's maintenance triggers;
  do not rebuild after every edit or as a delivery check.
- Read [references/hooks.md](references/hooks.md) for requested Git hook work.
  Project agent hooks and plugin refresh belong to
  `docs/agent-guides/agent-layer.md`. Hook configuration is not activation proof.
- After an authorized package upgrade, review the installed upstream skill and
  references, apply relevant changes while retaining this project's rules,
  then update `.graphify_version` and the version statement above. Refresh both
  plugin caches and verify their contents. The containing project's plugin
  version is independent of the Graphify package version.

Only the three references linked above are active procedures. Other bundled
references are upstream background retained for comparison during maintenance;
their generic GitHub cloning, URL ingestion, semantic extraction, media,
watchers, exports, and MCP workflows are inactive here. Do not run them or add
a `CLAUDE.md` instruction boundary. A separately requested supported local
export or reclustering task must use the installed CLI after inspecting its
options; it is never an implicit part of navigation.

For `/graphify --help`, describe the navigation and maintenance routes above
without running them. Report only operations actually executed, including
missing graph data, truncated results, and unresolved integrity issues.

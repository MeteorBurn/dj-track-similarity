# Graphify reference: project Git and agent hooks

Project adaptation for Graphify 0.9.73. Read `docs/agent-guides/agent-layer.md`
and `docs/agent-guides/graphify.md` before changing integrations. Use the local
CLI from the repository root in PowerShell 7.

## Git hooks

Inspect the installed hooks before changing them:

```powershell
& .\.tools\graphify\bin\graphify.exe hook status
if ($LASTEXITCODE -ne 0) { throw 'Graphify hook status failed.' }
```

During authorized installation or package maintenance, refresh outdated native
templates with the command below, then inspect status and the hook files again:

```powershell
& .\.tools\graphify\bin\graphify.exe hook install
if ($LASTEXITCODE -ne 0) { throw 'Graphify hook installation failed.' }
& .\.tools\graphify\bin\graphify.exe hook status
if ($LASTEXITCODE -ne 0) { throw 'Graphify hook status failed.' }
```

The installer preserves unrelated hook content. Verify that preservation when
changing an existing hook. A package upgrade alone does not refresh templates.
The post-commit hook starts a background code rebuild and skips linked
worktrees and some Git operations. A commit does not prove that it ran or that
the graph is current; inspect output and freshness when relevant. Do not make
a commit solely to test a hook.

## Agent integration

The project plugin and `AGENTS.md` already provide the instruction boundary.
Do not run `graphify claude install` or `graphify install`: they can add a
`CLAUDE.md` or overwrite the project's hook and skill arrangement. Do not add
standalone skills, global Graphify configuration, or an MCP server.

Use the agent-layer guide's existing native `hook-guard` commands and matchers.
`hook-check` is a legacy no-op in 0.9.73. Configuration and a successful manual
guard invocation do not prove activation in a host session; new or changed
Codex hooks require the host's native trust review.

For a package/skill refresh, compare the local CLI, package metadata, canonical
`.graphify_version`, and both plugin caches after reviewing upstream changes.
Preserve the containing project plugin's independent version and project-only
enabled scope. An already open session can retain older skill instructions.

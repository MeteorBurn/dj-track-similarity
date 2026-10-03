# Graphify reference: project Git and agent hooks

Project adaptation for Graphify 0.9.73. Read `docs/agent-guides/agent-layer.md`
and `docs/agent-guides/graphify.md` before changing integrations. Use the local
CLI from the repository root in PowerShell 7.

## Git hooks

Inspect the installed hooks before changing them and during authorized
package maintenance; `hook status` reports outdated templates:

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
changing an existing hook. A package upgrade alone does not rewrite installed
hooks. The post-commit hook starts a background code rebuild and skips linked
worktrees and some Git operations. A commit does not prove that it ran or that
the graph is current; inspect output and freshness when relevant. Do not make
a commit solely to test a hook.

## Agent integration

The project plugin and `AGENTS.md` already provide the instruction boundary.
Do not run `graphify claude install` or `graphify install`: they can add a
`CLAUDE.md` or overwrite the project's hook and skill arrangement. Do not add
standalone skills, global Graphify configuration, or an MCP server.

Use the agent-layer guide's native `hook-guard` commands and matchers; neither
configuration nor a successful manual guard invocation proves activation in a
host session.

Package and skill refresh follow the agent-layer guide; an already open
session can retain older skill instructions.

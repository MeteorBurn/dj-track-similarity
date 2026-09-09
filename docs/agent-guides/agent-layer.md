# Project agent and plugin maintenance

Read before editing project agents, skills, plugin files, hooks, generated launchers, or agent configuration, and before assigning work across project roles.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## AGENT LAYER

- `.djts/` is the shared plugin source: `agents/`, `skills/`, `scripts/`,
  matching `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, and
  `dj-track-similarity-note.svg` at its root.
- Edit agent/skill Markdown there. After agent edits, explicitly run
  `.\.djts\scripts\sync-codex-agents.ps1` to regenerate `.codex/agents/*.toml`;
  never edit the generated launchers. Skills are not projected as agents.
- For initial agent setup, run
  `.\.djts\scripts\bootstrap.ps1`: it registers/installs the plugin for available
  Claude Code and Codex CLIs, then generates launchers. It is optional for
  application-only use and is not run automatically at session start.
- For a requested plugin refresh, inspect its registered source and installation
  scope first. Preserve the version unless the user requests a version change.
  Refresh Codex with `codex plugin add dj-track-similarity@dj-track-similarity`.
  For Claude, set `$pluginScope` to the verified existing scope (this checkout
  uses `project`), then run
  `claude plugin update dj-track-similarity@dj-track-similarity --scope $pluginScope --yes`.
  If the installed content remains stale at the same version, run
  `claude plugin uninstall dj-track-similarity@dj-track-similarity --scope $pluginScope --keep-data`
  followed by
  `claude plugin install dj-track-similarity@dj-track-similarity --scope $pluginScope --yes`.
  Target only this plugin; bootstrap or a successful update message alone does
  not prove its cached content was refreshed.
- Compare the installed plugin files and skill inventory with `.djts/`, including
  removal of deleted skills. Verify registration and enabled state separately.
  An already open session can retain old capabilities until restarted.
- `.claude/` holds only Claude configuration, hooks, and runtime state;
  `.codex/` holds Codex configuration and generated launchers. Do not put
  copies or links to shared skills/agents in `.claude/`.
- Keep `.workspace/` scoped as listed in [STRUCTURE](architecture.md#structure). Optional AgentProof/Superpowers
  state stays at its supported roots (`.agentproof/`, `.superpowers/`), without
  junction redirection.
  OpenCode/OMO are external and optional: do not restore `opencode.json`;
  clear `.omo/` only when cleanup is requested and no OMO/OpenCode process runs.

An agent owns a role; a skill is a reusable task. Keep role-specific procedures
inside the owning agent and shared tasks in `.djts/skills/`. Reference current
configuration and source instead of duplicating model lists, paths, or thresholds.

| Agent | Ownership |
|---|---|
| `code-explorer` | Read-only execution paths, architecture, callers, and blast radius |
| `ml-engineer` | Audio representations, inference, classifiers, similarity semantics, ML evaluation |
| `database-expert` | Schema, indexes, queries, migrations, integrity, locking |
| `backend-engineer` | HTTP/CLI contracts, jobs, service Python, environment |
| `frontend-engineer` | React/Vite, client state, typed API client, rendering |
| `design-system-engineer` | Design tokens, reusable UI primitives, visual consistency, accessibility |
| `documentation-expert` | Documentation structure, evidence audits, navigation, tooling, instruction maintenance |
| `technical-writer` | Audience-focused guides, references, runbooks, troubleshooting, requested release and migration notes |
| `performance-optimizer` | Bottleneck localization, profiling, benchmarks, measured improvement |
| `test-reviewer` | Test value, fixtures, suite health, failure triage |
| `code-refactor-master` | Behavior-preserving splits, moves, deduplication, reference updates |
| `codebase-pruner-expert` | Evidence-backed dead-code audits and scoped removal, preserving live behavior and persisted contracts |

Delegate work across these ownership boundaries and integrate it into one answer.
Give each worker a bounded scope, relevant instructions, and dirty-state context;
workers must preserve others' edits. Honor the active harness's delegation rules.
`context: fork` in a skill is effective only in harnesses that support it.

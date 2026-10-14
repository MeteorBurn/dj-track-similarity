# Project agent and plugin maintenance

Read before editing project instructions, agents, skills, plugin files, hooks,
generated launchers or agent configuration, assigning work across project roles,
or preparing requested product/developer documentation.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## AGENT LAYER

### Shared source and generated launchers

- `.djts/` is the shared plugin source: `agents/`, `skills/`, `scripts/`,
  `.claude-plugin/plugin.json` with its `marketplace.json`,
  `.codex-plugin/plugin.json`, and `dj-track-similarity-note.svg` at its root.
- Edit agent/skill Markdown there. After agent edits, explicitly run
  `.\.djts\scripts\sync-codex-agents.ps1` to regenerate `.codex/agents/*.toml`;
  never edit the generated launchers. Skills are not projected as agents.
- `.claude/` holds only Claude configuration, hooks, and runtime state;
  `.codex/` holds Codex configuration and generated launchers. Do not put
  copies or links to shared skills/agents in `.claude/`.

### Initial setup

- For initial agent setup, run `.\.djts\scripts\bootstrap.ps1`: for available
  CLIs it registers the `.djts` marketplace, enables the plugin for Claude Code
  at project scope (no install) and installs it for Codex, then generates
  launchers. It is optional for application-only use and is not run
  automatically at session start.

### Claude: source loaded in place

- Claude loads the plugin in place from `.djts/`: `.claude/settings.json`
  declares the marketplace (`extraKnownMarketplaces`) and enables the plugin
  (`enabledPlugins`) without an install record. `.djts/` edits reach Claude from
  the next session, with no refresh command or version bump; an open session
  keeps old capabilities until restarted. Never install, reinstall or update
  this plugin for Claude: install makes it run a cached copy under
  `~/.claude/plugins/cache/` that drifts from `.djts/`, and update at an
  unchanged version copies nothing. Verify the inventory with
  `claude plugin details dj-track-similarity@dj-track-similarity`; an empty
  `claude plugin list` is expected. To prove the loaded content, ask an edited
  agent in a new session, without tools, to quote a changed line and compare it
  with `.djts/`.

### Codex: requested cache refresh

- For a requested Codex refresh, inspect its registered source and scope first;
  preserve the version unless the user requests a change. Run
  `codex plugin add dj-track-similarity@dj-track-similarity`. It enables the
  plugin globally: restore its global `enabled = false`, retain `enabled = true`
  in this checkout's `.codex/config.toml`, and verify both scopes. Codex uses
  the generated `.codex/agents/*.toml` and only the skills from its plugin
  cache: compare those with `.djts/skills/`, including removal of deleted
  skills; a successful add message alone does not prove a refresh.

### Graphify integration and hooks

- Graphify stays in the `dj-track-similarity` plugin, with its canonical skill at
  `.djts/skills/graphify/`. Keep this project plugin disabled in global Codex
  configuration and enabled in this checkout's `.codex/config.toml`; preserve
  that scope after plugin installation or refresh. Claude uses project scope.
  Do not add standalone skill copies or register a Graphify MCP server.
- Claude's PreToolUse hooks call native `hook-guard search/read` from the
  git-ignored `.claude/settings.json`; bootstrap writes only the marketplace and
  plugin enablement there, never these hooks. Matchers
  `Bash|Grep` and `PowerShell` run `hook-guard search`, `Read|Glob` runs
  `hook-guard read`, each through this checkout's
  `.tools/graphify/bin/graphify.exe` by absolute path with forward slashes.
- Codex's `.codex/hooks.json` calls the same native `hook-guard search` with
  the `Bash` matcher, absolute local CLI path and a 10-second timeout. It adds
  a reminder before recognized shell searches; the [Graphify guide](graphify.md)
  still governs excluded-file exceptions. Do not replace it with the
  `hook-check` no-op or a custom wrapper/SessionStart script.
  New or changed Codex hooks require native trust review; configuration alone
  does not prove activation.

### Graphify package and skill upgrades

- Graphify's automatic skill refresh covers upstream-managed installation
  paths, not `.djts/skills/graphify/` or the Codex plugin cache. After a
  package upgrade, review upstream skill changes against our project overrides
  and update the shared source and its `.graphify_version` together. Claude
  picks it up from the next session; follow the
  [Codex refresh procedure](#codex-requested-cache-refresh), then compare the
  CLI/package version, marker, skill version statement,
  and Codex cached skill contents. The containing project plugin has its own
  version: do not replace it with Graphify's package version.

### Local workspace state

- Keep `.workspace/` scoped as listed in [STRUCTURE](architecture.md#structure).
  Optional AgentProof/Superpowers
  state stays at its supported roots (`.agentproof/`, `.superpowers/`), without
  junction redirection.
  OpenCode/OMO are external and optional: do not restore `opencode.json`;
  clear `.omo/` only when cleanup is requested and no OMO/OpenCode process runs.

### Role ownership and delegation

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

Delegate substantial work across these ownership boundaries or for independent
review; handle small local changes directly. Give workers a bounded scope,
relevant instructions and dirty-state context, preserve others' edits, and
integrate one answer. Honor the active harness's delegation rules.

## REQUESTED DOCUMENTATION

Follow the scope and paused-site rules in
[DOCUMENTATION WORKFLOW](../../AGENTS.md#documentation-workflow).

- For requested product/developer documentation, delegate to
  `documentation-expert` (structure, audits, tooling) or `technical-writer`
  (reader-facing pages). Scope, source ownership and verification come from
  project instructions and executable code. Read `README.md` for setup
  orientation when needed; verify current behavior against executable source
  and tests. Maintained docs can lag the code.
- Document current behavior, not plans. Docs do not block implementation,
  verification, or authorized Git delivery.
- Keep `README.md` concise and UI-first, without CLI/API command recipes.
  Use emoji headings/callouts, meaningful images, and working links.
  Installation order: prerequisites/warnings; one short installation procedure;
  dependencies grouped by role, one package per line with bold name/version and
  a short purpose; Audio Features Extraction Engine (patched SONARA fork and
  original citation); models and disk sizes. Model-specific packages remain
  actual dependencies but appear in their model block, not the general list.
  Verify installer/runtime/launcher claims against executable sources.
  When the user reports GitHub edits, fetch and integrate them before updating
  README; preserve user wording outside the requested scope.
- Documentation is English. Translate Russian UI labels in prose; only
  `docs/dj-track-similarity/help/ui-language.md` may contain Cyrillic to map
  on-screen labels to English.
  `npm --prefix .\docs\dj-track-similarity run lint:language` enforces this;
  follow [Verification](verification.md) for when to run it.

# Prompt-kit role audit

<!-- markdownlint-disable MD013 -->

This working note records the current pass through the required local role
files in `docs-redesign-prompt-kit/documentation-agent-roles/`. It is not a
public docs page.

| Role file | Applied decision |
| --- | --- |
| `README.md` | Used the prescribed order: plan, orchestrate, style/visual, writers, fact-check, Diataxis, editorial, release, quality tools. |
| `docs-redesign-planner.md` | Kept the redesign as a replacement IA with legacy docs snapshotted to root `docs-legacy/` and ignored by git. |
| `docs-orchestrator.md` | Split pages by audience and Diataxis type: getting started, user guide, workflows, concepts, tools, reference, developer, help. |
| `docs-style-guide.md` | Kept the public voice practical, local-first, modest, and safety-explicit; avoided commercial or benchmark claims. |
| `visual-docs-guide.md` | Replaced the default VitePress first viewport with a DJ workbench visual that explains scan/analyze/audition/export and safety boundaries. |
| `documentation-tools-and-plugins.md` | Used local build, Markdown lint, spelling, link checking, and rendered-page screenshots as the verification stack. |
| `user-docs-writer.md` | User-facing pages start from tasks, expected result, safety notes, and common recovery paths. |
| `tutorial-writer.md` | First-run pages use a linear path from environment activation to UI result instead of broad reference detail. |
| `power-user-docs-writer.md` | CLI, automation, and maintenance docs separate dry-run/report paths from explicit apply paths. |
| `technical-docs-writer.md` | API, CLI, database, and developer pages are sourced from code, schemas, config, and focused command output. |
| `human-readme-writer.md` | The docs homepage and guide entrypoint now answer what the project is, who it is for, first useful result, and next path. |
| `docs-fact-checker.md` | High-risk facts are checked against current code and project invariants, not copied from legacy docs as truth. |
| `diataxis-reviewer.md` | Tutorial, how-to, reference, and explanation content are separated into different page families. |
| `editorial-reviewer.md` | Removed marketing tone and template-like first screen; kept direct wording and practical expected outcomes. |
| `docs-quality-tools.md` | Quality gate is build plus markdownlint, cspell, lychee, and browser/screenshot checks for the rendered docs site. |
| `docs-release-auditor.md` | Final audit focuses on stale CLI/API/UI/safety claims, legacy URL coverage, generated site output, and remaining risks. |

## Current correction from audit

The first visual pass still looked too close to stock VitePress because the
homepage used `layout: home` and inherited the built-in hero. The corrective
decision is to make the homepage a custom `layout: page` surface with its own
landing hero, workflow panel, and safety board. This directly addresses the
visual-docs-guide requirement that the visual layer should explain action,
result, and risk instead of decorating the page.

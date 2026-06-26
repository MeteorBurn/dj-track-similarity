# dj-track-similarity docs redesign plan

<!-- markdownlint-disable MD013 -->

> First-stage draft. This file is a planning artifact only. It does not approve
> moving, deleting, renaming, or archiving the existing documentation.

## Executive summary

The current documentation is useful as a technical fact base, but it reads like
a component map: Install, Overview, Models, Analysis, Search, CLI, API,
Database, Architecture, Development, Rhythm Lab, and maintenance scripts. The
redesign should replace that with a user-first documentation set that answers:
what the project is, who it helps, how to get a first useful result, how to use
the UI, and where exact reference details live.

The final served VitePress root should stay at `docs/dj-track-similarity` so
the existing `/docs/` base and main app documentation link can keep working.
The user has now chosen the legacy destination: current docs should be moved to
the project-root `docs-legacy/` folder during the migration step and excluded
from the repository after that. Draft planning still lives under
`docs/_redesign-draft`.

Primary goals:

- Make the first screen explain the local DJ library workflow in human terms.
- Separate user guides, workflows, concepts, tools, reference, developer docs,
  and help.
- Treat current docs as stale-prone topic inventory only. Do not copy facts
  from them into new pages until checked against code, CLI, API schemas,
  frontend API contracts, database schema, tests, or actual command output.
- Finish the complete English documentation first. After English pages are
  fact-checked and reviewed, do one Russian localization pass. After that,
  update Russian pages only on explicit future request.
- Keep destructive/tag-writing workflows visibly separate from read-only
  previews, scans, analysis, and reports.

## First-stage scope

Completed in this stage:

- Read the prompt kit entrypoint, master prompt, terminology, verification
  checklist, and listed role files.
- Inspected the real docs tree and confirmed the current VitePress source root:
  `docs/dj-track-similarity`.
- Inspected `.vitepress/config.mts`, theme files, package scripts, generated
  `site/` path, current Markdown pages, Russian pages, README, API route files,
  CLI command registrations, frontend labels, SET schema/code, database schema,
  audio dedup code, and audio repair script.
- Created this plan under `docs/_redesign-draft`.
- Created the project-root `docs-legacy/` folder and added `docs-legacy/` to
  `.gitignore` so the future legacy snapshot does not get added as new files.

Not done in this stage:

- No legacy docs were moved, renamed, deleted, or archived.
- No VitePress nav/sidebar/config was changed.
- No generated `docs/dj-track-similarity/site` files were rebuilt.
- No full page rewrites were started.

## Current docs structure

Current source root:

```text
docs/dj-track-similarity/
  .vitepress/config.mts
  .vitepress/theme/
  index.md
  project-guide.md
  overview.md
  install.md
  analysis.md
  models.md
  search-and-tags.md
  rhythm-lab.md
  cli.md
  api.md
  database.md
  architecture.md
  development.md
  release-checklist.md
  ideas.md
  scripts/
    repair-audio-metadata.md
    audio-dedup.md
    optimize-database.md
  ru/
    ...
  site/
    generated VitePress output
```

Current VitePress facts:

- Package scripts live in `docs/dj-track-similarity/package.json`.
- `npm run build` runs `vitepress build .`.
- Config path is `docs/dj-track-similarity/.vitepress/config.mts`.
- `base` is `/docs/`.
- `outDir` is `site`.
- Current nav is Guide, Install, CLI, API, Rhythm Lab.
- Current sidebars are component/reference oriented.
- English and Russian locales already exist.

## Fact-use policy for current docs

The existing docs are not a trusted source of current behavior. They are useful
for discovering topics, warnings, older workflows, and places where users may
still expect reference pages. Every behavioral claim copied from old docs must
be rechecked against a current source of truth first.

Rules:

- Use old docs to discover page topics and forgotten edge cases.
- Do not copy old prose as the new style.
- Do not treat old commands, API shapes, UI labels, defaults, paths, or model
  behavior as current until verified.
- If old docs conflict with code, command output, API schemas, frontend source,
  or tests, the current source wins.
- If the current source is unclear, mark the claim as a gap instead of writing
  around it.

## Current docs audit

| Current page | Current role | Diataxis today | Decision | Notes |
| --- | --- | --- | --- | --- |
| `index.md` | Home landing | Explanation/landing | Rewrite | Keep local-first and safety facts; make value and first result clearer. |
| `project-guide.md` | Docs index | Reference/navigation | Rewrite | Use as source for inventory; new entrypoint should route by user goal. |
| `overview.md` | Project overview | Explanation | Split | Move purpose/safety to landing and concepts; move supported files to reference/help. |
| `install.md` | Setup | How-to/reference | Rewrite/split | Keep commands after verifying `pyproject.toml`, `dj-sim doctor`, FFmpeg notes. |
| `analysis.md` | Analysis families | Explanation/reference | Split | User-facing analysis choice guide plus reference for exact families. |
| `models.md` | Model summary | Explanation/reference | Merge/split | Merge human concepts into features/embeddings page; keep exact model reference. |
| `search-and-tags.md` | Search modes and tag writes | How-to/reference | Split | Separate SET, SONARA, MERT, CLAP, CLASS, export, and tag-writing safety. |
| `rhythm-lab.md` | Lab UI/CLI/training | Tutorial/how-to/reference | Split | Needs first classifier tutorial, promotion how-to, and technical reference. |
| `cli.md` | CLI reference | Reference | Preserve/rebuild | Keep as reference; regenerate/check against `src/dj_track_similarity/cli.py` and live help. |
| `api.md` | Web API reference | Reference | Preserve/rebuild | Check against route modules, schemas, and `frontend/src/api.ts`. |
| `database.md` | SQLite/storage | Reference/explanation | Preserve/split | Keep table facts; add a human "what gets stored where" concept page. |
| `architecture.md` | Runtime architecture | Explanation/reference | Preserve/rewrite | Move to developer section; keep dependency and server facts verified. |
| `development.md` | Dev setup/checks | How-to/reference | Preserve/rewrite | Keep focused verification guidance; make it developer-only. |
| `release-checklist.md` | Release gate | Reference/checklist | Preserve | Developer/release page; not primary user navigation. |
| `ideas.md` | Future concepts | Explanation/roadmap | Preserve separately | Keep as future ideas, clearly not implemented behavior. |
| `scripts/repair-audio-metadata.md` | Repair helper | How-to/reference | Rewrite | Emphasize dry-run-first, backups, standalone path. |
| `scripts/audio-dedup.md` | Dedup reports/apply | How-to/reference | Rewrite | Emphasize report-only default and exact `APPLY DELETE` apply mode. |
| `scripts/optimize-database.md` | DB maintenance | How-to/reference | Rewrite | Keep backup, integrity, vacuum/analyze facts after source check. |
| `ru/**` | Russian localization | Mixed | Rebuild once after English completion | Use as language seed only after English pages are complete and verified. |
| `site/**` | Generated output | Generated | Do not edit | Rebuild only after source docs change in final VitePress root. |

## Target audiences

| Audience | First questions | Skill level | Needed docs |
| --- | --- | --- | --- |
| DJ or music collector | What is this, is it safe for my files, how do I see useful matches? | Comfortable with local apps, not necessarily a developer | Landing, quickstart, UI guide, workflows, troubleshooting |
| Existing user | What changed, where did old CLI/API/search pages go? | Knows the project | Migration notes, page map, reference index |
| Power user | How do I batch scan/analyze/search, export, dedup, repair, and automate safely? | CLI/PowerShell capable | CLI how-tos, tools-and-scripts, config, reports, failure handling |
| Rhythm Lab user | How do I label, train, promote, and rescore classifiers? | Intermediate | Tutorial, profile lifecycle how-tos, concepts, classifier reference |
| Developer/integrator | What are the contracts, data model, modules, tests, and API shapes? | Technical | API, CLI, DB, architecture, development, release checklist |
| AI agent/contributor | Which invariants must not be broken? | Technical | Developer docs, safety invariants, verification map |

## User workflow map

| Workflow | Audience | Start point | Successful outcome | New pages |
| --- | --- | --- | --- | --- |
| First useful local run | New user | Fresh clone and test audio folder | Database exists, UI shows scanned tracks | `getting-started/quickstart.md`, `getting-started/first-library.md` |
| Analyze enough data for search | User/power user | Scanned library | SONARA/MERT/CLAP/MAEST state is visible and usable | `user-guide/analyze-library.md`, `reference/analysis-families.md` |
| Find related tracks from seeds | DJ/user | One to five seed tracks | Candidate list or ordered SET preview | `workflows/find-compatible-tracks.md`, `user-guide/search-with-seeds.md`, `user-guide/smart-set-builder.md` |
| Search by text description | User | CLAP embeddings present | Tracks ranked by text prompt | `user-guide/text-search.md`, `concepts/features-embeddings-tags.md` |
| Build a temporary set | DJ/user | Search results or SET preview | Current set can be exported | `workflows/prepare-a-set.md`, `user-guide/export-playlists.md` |
| Train a personal classifier | Power user | Labels in Rhythm Lab | Promoted classifier scores available in main app | `workflows/train-personal-classifier.md`, `tools-and-scripts/rhythm-lab.md` |
| Maintain the local library | Power user | Existing DB and reports | Dedup/repair/optimize run with clear safety boundary | `workflows/maintain-library.md`, `tools-and-scripts/*.md` |
| Integrate or inspect API/DB | Developer | Running app or database | Correct endpoint/schema/table usage | `reference/api.md`, `reference/database.md`, `developer/architecture.md` |

## Proposed final information architecture

Preferred final VitePress root after explicit legacy move approval:
`docs/dj-track-similarity`.

```text
docs/dj-track-similarity/
  index.md
  getting-started/
    index.md
    quickstart.md
    install.md
    first-library.md
    first-analysis.md
  user-guide/
    index.md
    browse-library.md
    analyze-library.md
    search-with-seeds.md
    smart-set-builder.md
    text-search.md
    class-tab.md
    export-playlists.md
    tags-and-audio-writes.md
  workflows/
    index.md
    prepare-a-set.md
    find-compatible-tracks.md
    build-crates.md
    train-personal-classifier.md
    maintain-library.md
  concepts/
    index.md
    local-first-safety.md
    features-embeddings-tags.md
    similarity-scores.md
    smart-set-builder-routing.md
    classifiers-and-rhythm-lab.md
  tools-and-scripts/
    index.md
    rhythm-lab.md
    audio-dedup.md
    repair-audio-metadata.md
    optimize-database.md
  reference/
    index.md
    cli.md
    api.md
    database.md
    configuration.md
    analysis-families.md
    ui-controls.md
  developer/
    index.md
    architecture.md
    development.md
    testing-and-verification.md
    release-checklist.md
  help/
    index.md
    troubleshooting.md
    faq.md
    known-limits.md
  ru/
    ...
```

Draft-only workspace before approval:

```text
docs/_redesign-draft/
  DOCS_REDESIGN_PLAN.md
  skeleton/
    index.md
    ...
```

## Proposed nav and sidebar model

Top nav after content skeleton exists:

- Start
- User Guide
- Workflows
- Tools
- Reference
- Help

Developer docs should be reachable from sidebar and footer, not prioritized in
the top nav for ordinary users. CLI/API/DB links should remain findable from a
Reference landing page and from direct redirects or migration notes if legacy
URLs change.

## Page-by-page plan

| New page | Audience | Goal | Diataxis | Source of truth |
| --- | --- | --- | --- | --- |
| `index.md` | New user | Explain what this is, who it helps, and the first useful result | Explanation/landing | README, current `index.md`, current `overview.md`, AGENTS safety invariants |
| `getting-started/quickstart.md` | New user | Get from install to visible UI with a small library | Tutorial | README, `install.md`, `cli.py`, `api.py`, `scripts/run_server.cmd` |
| `getting-started/install.md` | User/power user | Install base and optional extras | How-to | `pyproject.toml`, `install.md`, `dj-sim doctor`, FFmpeg setup notes |
| `getting-started/first-library.md` | New user | Scan files and understand the database | Tutorial | `scanner.py`, CLI scan, `/api/library/scan`, UI library panel |
| `getting-started/first-analysis.md` | New user | Pick and run first analysis safely | Tutorial | `analysis.md`, `analysis_jobs.py`, `LibraryPanel.tsx`, help text |
| `user-guide/browse-library.md` | User | Browse, search, like, inspect, preview tracks | How-to | `LibraryPanel.tsx`, `TrackPanel.tsx`, `TrackMetadataDialog.tsx`, API routes |
| `user-guide/analyze-library.md` | User | Run SONARA, MAEST, MERT, CLAP, classifiers from UI | How-to | `LibraryPanel.tsx`, `api_routes_analysis.py`, job tests |
| `user-guide/search-with-seeds.md` | DJ/user | Use SONARA and MERT seed search | How-to | `SearchPlaylistPanel.tsx`, `api_routes_search.py`, search modules |
| `user-guide/smart-set-builder.md` | DJ/user | Build read-only SET previews and add them deliberately | How-to | `set_builder.py`, `api_schemas.py`, `SearchPlaylistPanel.tsx`, SET tests |
| `user-guide/text-search.md` | User | Use CLAP prompts without overclaiming mood accuracy | How-to | `api_routes_search.py`, `embedding.py`, `SearchPlaylistPanel.tsx` |
| `user-guide/class-tab.md` | Rhythm Lab user | Use promoted classifier controls and scores | How-to | `classifier_scoring.py`, `classifier_jobs.py`, frontend CLASS tab |
| `user-guide/export-playlists.md` | User | Export current set as M3U/CSV safely | How-to | `api_routes_tags_export.py`, export tests |
| `user-guide/tags-and-audio-writes.md` | Power user | Understand explicit genre tag writes | How-to | `tags.py`, `wave_tags.py`, `/api/tags/genres/apply`, tests |
| `workflows/prepare-a-set.md` | DJ/user | Practical route from seed tracks to export | Tutorial/how-to | UI source, SET/search modules, export route |
| `workflows/find-compatible-tracks.md` | DJ/user | Compare SONARA/MERT/CLAP choices | How-to | Search modules, terminology, current search docs |
| `workflows/build-crates.md` | DJ/user | Create discovery lists without claiming perfect matching | Explanation/how-to | Current search docs, SET docs, frontend UI |
| `workflows/train-personal-classifier.md` | Power user | Label, train, promote, rescore | Tutorial/how-to | Rhythm Lab CLI/UI code, classifier production code, tests |
| `workflows/maintain-library.md` | Power user | Choose dedup, repair, optimize safely | How-to | audio dedup, repair script, optimize script, safety invariants |
| `concepts/local-first-safety.md` | All users | Explain what writes SQLite, reports, tags, or files | Explanation | AGENTS safety invariants, DB/tag/dedup/repair code |
| `concepts/features-embeddings-tags.md` | User | Distinguish tags, SONARA features, embeddings, genres | Explanation | terminology, `sonara_features.py`, `embedding.py`, `genres.py` |
| `concepts/similarity-scores.md` | User | Explain scores as ranking hints, not truth | Explanation | search modules, current docs, evaluation code |
| `concepts/smart-set-builder-routing.md` | User/power user | Explain seeds, auto anchors, BPM trajectory, artist guard | Explanation | `set_builder.py`, `api_schemas.py`, frontend labels |
| `concepts/classifiers-and-rhythm-lab.md` | User/power user | Explain profiles, scores, calibration, promotion | Explanation | Rhythm Lab code, classifier manifests/scoring |
| `tools-and-scripts/rhythm-lab.md` | Power user | Operate the separate labeling/training app | How-to/reference | `tools/rhythm-lab`, current `rhythm-lab.md` |
| `tools-and-scripts/audio-dedup.md` | Power user | Generate reports and understand apply mode | How-to/reference | `tools/audio-dedup`, current docs, tests |
| `tools-and-scripts/repair-audio-metadata.md` | Power user | Dry-run and apply repair helper safely | How-to/reference | `scripts/audio_repair/repair_audio_metadata.py`, tests |
| `tools-and-scripts/optimize-database.md` | Power user | Back up, optimize, and verify SQLite DB | How-to/reference | optimization script, current docs |
| `reference/cli.md` | Power user/dev | Exact commands and flags | Reference | `src/dj_track_similarity/cli.py`, live `--help` output |
| `reference/api.md` | Developer | Exact endpoints and payloads | Reference | `api_routes_*.py`, `api_schemas.py`, `frontend/src/api.ts` |
| `reference/database.md` | Developer/power user | SQLite tables, indexes, stored data | Reference | `db_schema.py`, `database.py`, DB tests |
| `reference/configuration.md` | Power user/dev | DB paths, env vars, FFmpeg, ports | Reference | CLI/API/server code, docs, scripts |
| `reference/analysis-families.md` | Power user/dev | Exact analysis inputs/outputs | Reference | analysis/model modules and tests |
| `reference/ui-controls.md` | User/dev | Current UI controls and labels | Reference | frontend source and browser smoke checks |
| `developer/architecture.md` | Developer | Runtime modules and boundaries | Explanation/reference | source tree, current architecture docs |
| `developer/development.md` | Developer | Local setup and focused checks | How-to | current `development.md`, AGENTS verification guidance |
| `developer/testing-and-verification.md` | Developer/AI agent | Which tests to run for which changes | Reference/how-to | tests, AGENTS, current development docs |
| `developer/release-checklist.md` | Maintainer | Release readiness gate | Reference/checklist | current release checklist, release auditor role |
| `help/troubleshooting.md` | User | Diagnose common install/UI/search problems | How-to | current README, install docs, real error paths |
| `help/faq.md` | New user | Answer common conceptual questions | Explanation | README, concepts, prompt terminology |
| `help/known-limits.md` | All users | State project limits modestly | Explanation | README, current docs, code constraints |

## One-time Russian localization map

Russian localization is intentionally delayed until the full English version is
complete, fact-checked, and reviewed. Do not create or maintain Russian pages
while English structure and wording are still moving.

After English completion, run one coordinated Russian localization pass. The
default scope should mirror the final English IA unless the user narrows it
before localization starts. After that pass, update Russian pages only when the
user explicitly requests translation/localization work.

Expected RU output after the English docs are complete:

- `ru/index.md`
- `ru/getting-started/index.md`
- `ru/getting-started/quickstart.md`
- `ru/getting-started/install.md`
- `ru/getting-started/first-library.md`
- `ru/getting-started/first-analysis.md`
- `ru/user-guide/index.md`
- `ru/user-guide/browse-library.md`
- `ru/user-guide/analyze-library.md`
- `ru/user-guide/search-with-seeds.md`
- `ru/user-guide/smart-set-builder.md`
- `ru/user-guide/text-search.md`
- `ru/user-guide/class-tab.md`
- `ru/user-guide/export-playlists.md`
- `ru/user-guide/tags-and-audio-writes.md`
- `ru/workflows/prepare-a-set.md`
- `ru/workflows/find-compatible-tracks.md`
- `ru/workflows/train-personal-classifier.md`
- `ru/workflows/maintain-library.md`
- `ru/concepts/local-first-safety.md`
- `ru/concepts/features-embeddings-tags.md`
- `ru/concepts/similarity-scores.md`
- `ru/concepts/smart-set-builder-routing.md`
- `ru/concepts/classifiers-and-rhythm-lab.md`
- `ru/tools-and-scripts/audio-dedup.md`
- `ru/tools-and-scripts/repair-audio-metadata.md`
- `ru/tools-and-scripts/optimize-database.md`
- `ru/tools-and-scripts/rhythm-lab.md`
- `ru/help/troubleshooting.md`
- `ru/help/faq.md`
- `ru/help/known-limits.md`
- `ru/reference/index.md`
- `ru/reference/cli.md`
- `ru/reference/api.md`
- `ru/reference/database.md`
- `ru/reference/configuration.md`
- `ru/reference/analysis-families.md`
- `ru/reference/ui-controls.md`
- `ru/developer/index.md`
- `ru/developer/architecture.md`
- `ru/developer/development.md`
- `ru/developer/testing-and-verification.md`
- `ru/developer/release-checklist.md`

## Reuse and rewrite map

| Existing content | New destination | Action | Facts to preserve |
| --- | --- | --- | --- |
| README opening and safety/limits | `index.md`, `concepts/local-first-safety.md` | Rewrite | Local-first, personal/public modest framing, no commercial/research claims |
| `install.md` | `getting-started/install.md`, `reference/configuration.md` | Rewrite/split | Python, extras, FFmpeg, CUDA stack, verification commands |
| `overview.md` | `index.md`, `concepts/local-first-safety.md`, `help/known-limits.md` | Split | Typical workflow, safety model, supported formats |
| `analysis.md` and `models.md` | `user-guide/analyze-library.md`, `concepts/features-embeddings-tags.md`, `reference/analysis-families.md` | Split | SONARA features vs MERT/CLAP/MAEST embeddings, classifier score wording |
| `search-and-tags.md` | `user-guide/search-with-seeds.md`, `user-guide/smart-set-builder.md`, `user-guide/text-search.md`, `user-guide/tags-and-audio-writes.md` | Split | Search tabs, SET read-only preview, tag-write exception |
| `rhythm-lab.md` | `workflows/train-personal-classifier.md`, `tools-and-scripts/rhythm-lab.md`, `concepts/classifiers-and-rhythm-lab.md` | Split | Separate app, labels DB, artifacts, promotion, rescoring |
| `cli.md` | `reference/cli.md` plus selected how-tos | Preserve/rebuild | Commands, flags, defaults, examples after live help check |
| `api.md` | `reference/api.md` | Preserve/rebuild | Endpoint paths, payloads, response shapes |
| `database.md` | `reference/database.md`, `concepts/local-first-safety.md` | Preserve/split | Tables, indexes, SQLite write boundaries |
| `architecture.md` | `developer/architecture.md` | Rewrite | Backend/frontend map, runtime dependencies, logging |
| `development.md` | `developer/development.md`, `developer/testing-and-verification.md` | Rewrite | Focused verification commands |
| `release-checklist.md` | `developer/release-checklist.md` | Preserve | Go/no-go gates |
| `ideas.md` | `developer/roadmap-or-ideas.md` or `help/known-limits.md` links | Preserve as clearly future | Avoid presenting ideas as implemented |
| `scripts/*.md` | `tools-and-scripts/*.md`, `workflows/maintain-library.md` | Rewrite | Dry-run/apply boundaries, report outputs, confirmations |
| Existing `ru/**` | New `ru/**` | Rebuild after English completion | Use checked meaning from final English pages, not old structure/style |

## Legacy move/archive proposal

User-approved direction:

1. Keep the future served docs root as `docs/dj-track-similarity`.
2. Move the current documentation snapshot to project-root `docs-legacy/`.
   Recommended local target: `docs-legacy/dj-track-similarity`.
3. Keep `docs-legacy/` ignored by git. The folder is for local reference only
   and should not be published as new repository content.
4. Remove old tracked legacy docs from the repository only as part of the
   replacement migration, after the new English skeleton is ready to occupy
   `docs/dj-track-similarity`.
5. Keep `base: "/docs/"` and `outDir: "site"` in the new config so the main
   app documentation button can continue serving `/docs/`.
6. Preserve legacy `site/` only as part of the local ignored legacy snapshot
   until the new docs build succeeds.
7. Update `.vitepress/config.mts` nav/sidebar only after content skeleton pages
   exist.

Already done:

- Created empty `docs-legacy/`.
- Added `docs-legacy/` to `.gitignore`.

Not done yet:

- The current docs tree has not been moved.
- The current tracked docs have not been removed from git.
- The new VitePress root has not been created.

The actual move/removal should be one deliberate migration step:

1. Copy or move `docs/dj-track-similarity` to
   `docs-legacy/dj-track-similarity` for local reference.
2. Remove the tracked legacy docs from `docs/dj-track-similarity`.
3. Create the new English docs skeleton in `docs/dj-track-similarity`.
4. Build the new docs and verify `/docs/` still works.

Historical note from the first draft:

- The earlier option `docs/dj-track-similarity-legacy` is no longer preferred.
- The earlier option of keeping old and new docs interleaved under
  `docs/dj-track-similarity/_new` is no longer preferred.

## Fact-check map for high-risk pages

| Area | Claims to verify | Sources |
| --- | --- | --- |
| Install/dependencies | Extras, CUDA stack, FFmpeg, doctor behavior | `pyproject.toml`, `src/dj_track_similarity/cli.py`, current install docs, fresh command output |
| CLI reference | Commands, flags, defaults, output | `src/dj_track_similarity/cli.py`, live `dj-sim --help` and command `--help` output |
| API reference | Endpoint paths, payloads, response shapes | `src/dj_track_similarity/api_routes_*.py`, `api_schemas.py`, `frontend/src/api.ts` |
| UI workflows | Labels, buttons, tabs, disabled states | `frontend/src/*.tsx`, `helpText.ts`, browser smoke check with safe DB/sample data |
| Database/storage | Tables, fields, cache behavior, write boundaries | `db_schema.py`, `database.py`, focused DB tests |
| Smart Set Builder | Seed modes, auto anchors, BPM, classifier flows, artist guard | `set_builder.py`, `api_schemas.py`, `api_routes_set_builder.py`, SET tests |
| Search | SONARA/MERT/CLAP/HYBRID/CLASS behavior | `api_routes_search.py`, search modules, frontend panel |
| Tags/audio writes | Exact tag-write exception and formats | `tags.py`, `wave_tags.py`, `/api/tags/genres/apply`, tag tests |
| Rhythm Lab | Label/profile/training/promotion behavior | `tools/rhythm-lab/rhythm_lab/*.py`, lab CLI help, lab tests |
| Audio dedup | Report-only default, apply confirmation, DB/file deletes | `tools/audio-dedup/audio_dedup/*.py`, CLI help, tests |
| Audio repair | Dry-run, apply, backups, file mutation scope | `scripts/audio_repair/repair_audio_metadata.py`, repair tests |
| Generated docs | Build output path and served `/docs/` base | `.vitepress/config.mts`, package scripts, backend static docs route if touched |

## Writing conventions for examples

- In each scenario that uses the project Python environment, show environment
  activation once near the beginning.
- After activation, all following code blocks assume the environment is active.
  Use `python -m ...`, `pip ...`, `pytest`, `dj-sim ...`, and `npm ...`.
- Do not repeat `.\.venv\Scripts\python.exe` in normal user-facing examples.
- Use an explicit `.venv` executable path only when documenting an unactivated
  shell, a subprocess launcher, or a developer-only edge case where activation
  is not available.
- Keep PowerShell examples copyable and avoid private absolute paths.

## Visual plan

Visuals should be planned before creation and should avoid private library data.

Initial useful visuals:

- Small Mermaid flow: audio folder -> scan -> SQLite -> analysis -> search ->
  preview/export.
- Small Mermaid decision tree: which search path to use: SONARA, MERT, CLAP,
  SET, CLASS.
- Safe workflow callout: what writes SQLite, what writes reports, what can
  write tags, what can delete files.
- UI screenshots only after a safe sample database or anonymized fixture exists.

No screenshots should use private paths, personal track names, unreleased music,
tokens, usernames, or the live personal library.

## Migration phases

### Phase 0: Plan and inventory

Deliverable: this file.

Exit criteria:

- Current docs tree and config inspected.
- New architecture proposed.
- Legacy destination fixed as root `docs-legacy/`.
- Russian localization plan exists and is delayed until English completion.
- Fact-check map exists.

### Phase 1: Legacy snapshot and English skeleton

Deliverable:

- Current docs snapshot moved to ignored `docs-legacy/dj-track-similarity`.
- Old tracked docs removed from `docs/dj-track-similarity` as part of the same
  migration step.
- New English skeleton pages created in `docs/dj-track-similarity`.

Exit criteria:

- Every skeleton page has audience, goal, and Diataxis type.
- No final nav/config change until skeleton exists.
- `docs-legacy/` stays ignored and is not staged.

### Phase 2: Core user path

Deliverable:

- Landing page, quickstart, install, first library, first analysis, browse UI,
  basic search, SET guide, troubleshooting.

Exit criteria:

- Commands fact-checked.
- UI labels fact-checked.
- Safety statements checked against code/project invariants.

### Phase 3: Workflows and concepts

Deliverable:

- DJ workflows, similarity concepts, local safety, features/embeddings/tags,
  classifiers, Rhythm Lab story.

Exit criteria:

- Diataxis review confirms workflows, how-tos, explanations, and reference are
  not mixed accidentally.

### Phase 4: Tools, reference, and developer docs

Deliverable:

- CLI, API, DB, config, analysis-family reference.
- Tools-and-scripts pages.
- Developer architecture, development, testing, release checklist.

Exit criteria:

- CLI/API/DB references checked against source and command output.
- Destructive/apply workflows have explicit warnings and exact confirmations.

### Phase 5: English review gate

Deliverable:

- Complete English docs reviewed by fact-checker, editorial reviewer, and
  Diataxis reviewer.

Exit criteria:

- High-risk facts have source references in the working notes.
- Commands and UI labels are checked against current source/output.
- No Russian pages are generated yet.

### Phase 6: One-time Russian localization

Deliverable:

- One coordinated Russian localization pass from the final English pages.

Exit criteria:

- Russian pages preserve the technical meaning of the English source.
- Russian pages are not updated again unless explicitly requested later.

### Phase 7: VitePress integration

Deliverable:

- Updated `.vitepress/config.mts` nav/sidebar/locales.
- New docs build under `docs/dj-track-similarity/site`.

Exit criteria:

- `npm run build` passes from `docs/dj-track-similarity`.
- Legacy links either redirect, move to a migration page, or remain documented.

### Phase 8: Release audit

Deliverable:

- Fact-check, editorial, Diataxis, quality-tools, and release-auditor findings
  resolved or documented.

Exit criteria:

- Markdown lint/spell/link checks run or explicitly skipped with reason.
- Docs build passes.
- Open risks are listed before publish/merge.

## Open questions and risks

| Question/risk | Impact | Proposed resolution |
| --- | --- | --- |
| Should final URLs preserve old flat pages like `/cli.html` and `/api.html`? | External links and app docs button may break. | Prefer migration pages or keep reference pages reachable at old aliases if VitePress supports it cleanly. |
| Russian localization can drift while English pages are changing. | Translation work may be wasted or inaccurate. | Do no Russian page creation until the English docs are complete and reviewed, then run one localization pass. |
| Existing docs include future `ideas.md`. | Users may confuse ideas with implemented behavior. | Move to clearly labeled future ideas/roadmap and exclude from onboarding path. |
| Screenshots may expose private library data. | Privacy risk. | Use sample/anonymized DB only; otherwise skip screenshots and use Mermaid. |
| Current docs generated `site/` is tracked. | Rebuild diffs may be large. | Do not rebuild until source docs change in final VitePress root; separate generated diff from source review. |
| Some current docs may be stale. | New docs could carry wrong facts. | Treat old docs as topic inventory only; verify all behavior claims through source/commands/tests. |
| Moving the VitePress root while replacing docs could disrupt package-lock/theme assets. | Build may fail or lose theme. | Snapshot legacy docs to ignored root `docs-legacy/`, then recreate only verified theme/config pieces in the served root deliberately. |
| Current frontend text includes mixed English/Russian labels. | User docs may not match UI language. | Quote exact UI labels where needed and plan a UI label audit before screenshots. |

## Mandatory role workflow

Use the local role files from:

```text
docs-redesign-prompt-kit/documentation-agent-roles/
```

These files are mandatory working instructions for this redesign. Every future
page batch should name the relevant writer and reviewers from this folder before
drafting starts.

Required role usage:

- `docs-redesign-planner.md`: maintain IA, phases, page map, migration risk.
- `docs-orchestrator.md`: assign audience, Diataxis type, writer, reviewers,
  and fact sources for each page.
- `docs-style-guide.md`: enforce tone, examples, safety wording, and
  human-readable DJ/workflow framing.
- `visual-docs-guide.md`: plan diagrams/screenshots/tables/callouts before
  creating visuals.
- `human-readme-writer.md`: use if the root README is rewritten or aligned to
  the new docs.
- `user-docs-writer.md`: quickstart, UI guide, help, and normal user pages.
- `tutorial-writer.md`: first run, first library, first analysis, first
  classifier.
- `power-user-docs-writer.md`: CLI workflows, automation, maintenance tools,
  batch operations.
- `technical-docs-writer.md`: API, CLI, database, architecture, developer
  reference.
- `docs-fact-checker.md`: verify behavior claims before editorial review.
- `editorial-reviewer.md`: review tone, clarity, anti-marketing, and
  usefulness.
- `diataxis-reviewer.md`: confirm page type separation.
- `docs-quality-tools.md`: run or explicitly skip markdownlint, cspell, and
  lychee at the right stage.
- `docs-release-auditor.md`: final docs release audit.

## Validation plan

During future writing:

- Run `git status --short` before edits.
- For changed Markdown under `docs/dj-track-similarity`, run docs build from
  `docs/dj-track-similarity`.
- For CLI claims, activate the local `.venv` once, then run focused
  `dj-sim ... --help` and related commands from that activated environment.
  User-facing examples should follow the same pattern.
- For API claims, check route modules, schemas, and frontend API mirror.
- For UI claims, check frontend source and run a browser smoke test when
  screenshots or user steps change.
- For DB/storage claims, check `db_schema.py`, `database.py`, and focused tests.
- For destructive workflows, verify dry-run/preview/apply confirmations in code
  and tests, not from memory.

First-stage actual checks:

- `git status --short --branch`: PASS, branch is `main...origin/main` and no
  dirty files were reported before creating this draft.
- Docs inventory: PASS, source root, generated output, Russian tree, package
  scripts, and VitePress config were inspected.
- Code/source spot checks: PASS for route names, CLI command registrations,
  frontend search labels, SET schema/code, database schema, audio dedup apply
  confirmation, and audio repair dry-run/apply/backups.
- `docs-legacy/`: PASS, project-root folder exists locally.
- `git check-ignore -v docs-legacy/`: PASS, `.gitignore` excludes the future
  legacy snapshot path.
- `git diff --check`: PASS after creating this draft.
- `markdownlint docs/_redesign-draft/DOCS_REDESIGN_PLAN.md`: initially failed
  only on `MD013/line-length` in plan tables; the draft now disables `MD013`
  locally because wide planning tables are intentional.
- `cspell`: not run; this first-stage planning file includes Russian text,
  project names, file paths, and code identifiers, so spelling review should be
  done after the content pages exist and the project dictionary is decided.
- `lychee`: not run; this plan adds no new public external links.
- `npm run build`: not run, because source docs under
  `docs/dj-track-similarity` were not changed.
- Full fact-check of every existing page: not run; this is planned for writing
  and review phases.

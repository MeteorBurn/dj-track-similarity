---
name: codebase-documentation-writer
description: Use when documenting MeteorBurn/dj-track-similarity or when writing grounded technical and user-facing docs from an actual codebase; includes project-specific rules for the dj-track-similarity VitePress docs tree.
---

# Codebase Documentation Writer

## Purpose

Use this skill to document a repository from zero context without inventing behavior. For `MeteorBurn/dj-track-similarity`, this skill is project-aware: it should update the existing `README.md` plus the VitePress source tree under `docs/dj-track-similarity/`, preserve the project's local-first DJ-library safety model, and keep claims practical and modest.

The output should serve two audiences:

1. **Technical readers**: maintainers, contributors, operators, API consumers.
2. **Users**: people installing, configuring, running, or using the product.

The job is not to make the project sound impressive. The job is to make the project understandable, accurate, and maintainable.

## Core Rules For Any Repository

- Start with repository discovery before writing docs.
- Ground every non-obvious technical claim in actual files, commands, configs, schemas, routes, tests, or source symbols.
- If something is not proven by the repository, write `Unknown from current codebase` or `TODO: verify`, not a confident guess.
- Preserve existing documentation style and language unless the user requested a change.
- Do not edit release notes, changelogs, legal docs, or generated docs unless explicitly asked.
- Do not expose secrets, local private paths, tokens, cookies, or machine-specific credentials.
- Do not refactor product code. Documentation edits only, unless the user explicitly expands scope.
- Ignore generated, vendored, cache, build, dependency, and artifact directories unless they are relevant to setup or deployment.

## Detecting dj-track-similarity

Treat the repository as `dj-track-similarity` when any of these are true:

- the remote is `https://github.com/MeteorBurn/dj-track-similarity`;
- `pyproject.toml` has `name = "dj-track-similarity"`;
- `AGENTS.md` describes a local DJ music-library analysis workbench;
- the repo contains `src/dj_track_similarity/` and `docs/dj-track-similarity/`.

When detected, follow the project-specific section below before the generic workflow.

# dj-track-similarity Project Profile

## Source Of Truth

For this project, docs are navigation aids, not the authority for logic. Verify behavior from current source, tests, schemas, and runtime evidence.

Read these first:

- `AGENTS.md`
- `README.md`
- `pyproject.toml`
- `docs/dj-track-similarity/project-guide.md`
- `docs/dj-track-similarity/.vitepress/config.mts`
- `docs/dj-track-similarity/developer/architecture.md`
- `docs/dj-track-similarity/developer/development.md`
- `docs/dj-track-similarity/developer/testing-and-verification.md`
- `src/dj_track_similarity/cli.py`
- `src/dj_track_similarity/api.py`
- `src/dj_track_similarity/api_schemas.py`
- `frontend/src/api.ts`

Do not rely on stale docs when source or tests disagree. If you find a mismatch, document the current source behavior and note the docs inconsistency for review.

## Project Tone And Claims

Keep public claims practical and modest:

- This is a public personal/enthusiast local-first DJ library workbench.
- It is not a polished commercial product.
- It is not a formal recommendation benchmark.
- Model outputs are useful ranking signals, not objective truth.
- The app helps shortlist listening candidates; final DJ decisions are by ear.

Avoid marketing filler such as `enterprise-grade`, `seamless`, `state-of-the-art`, `robust AI`, or `production-ready` unless the source and tests prove exactly that. They usually do not.

## Documentation Surface

Tracked documentation is:

```text
README.md
docs/dj-track-similarity/
```

The English entrypoint is:

```text
docs/dj-track-similarity/project-guide.md
```

Do **not** create a generic root docs layout like:

```text
docs/architecture.md
docs/user-guide.md
docs/api.md
```

That would be wrong for this repository. Use the existing VitePress sections instead:

```text
docs/dj-track-similarity/getting-started/
docs/dj-track-similarity/user-guide/
docs/dj-track-similarity/workflows/
docs/dj-track-similarity/concepts/
docs/dj-track-similarity/tools-and-scripts/
docs/dj-track-similarity/reference/
docs/dj-track-similarity/developer/
docs/dj-track-similarity/help/
```

If adding a new VitePress page, also update:

```text
docs/dj-track-similarity/.vitepress/config.mts
```

and the nearest section `index.md`, otherwise the page exists but users will not find it. Tiny orphan docs are how documentation becomes a haunted attic.

## Language And Command Style

- User-facing project docs are English unless the user asks otherwise.
- README is the public landing page: concise, workflow-oriented, and linked to the docs tree.
- Documentation command examples assume the Python environment is already activated.
- In README and `docs/dj-track-similarity/`, prefer `python ...` or the installed `dj-sim` console script.
- Do not write project docs examples using `.\.venv\Scripts\python.exe` unless documenting a local troubleshooting command where that exact path matters.
- The project is Windows-first for verified local development. Use PowerShell examples for normal setup and commands.

## Project Map To Preserve

High-level map:

- `src/dj_track_similarity/`: backend, Typer CLI, FastAPI routes, SQLite access, scanning, analysis, embeddings, classifiers, search, exports, tags, media preview, logging, runtime helpers.
- `frontend/`: React/Vite/TypeScript UI. `frontend/src/api.ts` mirrors backend API contracts; `frontend/dist` is the backend-served bundle.
- `tests/`: backend/API/search/jobs/tags/evaluation pytest coverage.
- `scripts/`: focused maintenance and benchmark scripts plus script tests.
- `docs/dj-track-similarity/`: VitePress source; `npm run build` writes ignored `site/` output.
- `tools/rhythm-lab/`: standalone classifier labeling/training UI and CLI.
- `tools/audio-doctor/`: dry-run-first metadata/container diagnostic and repair helper plus UI jobs.
- `tools/audio-dedup/`: duplicate-audio candidate reporter plus explicit confirmed cleanup mode.

Hot source areas:

- SQLite: `database.py`, `db_schema.py`, `db_*`, `LibraryDatabase`.
- API contracts: `api.py`, `api_schemas.py`, `api_routes_*.py`, `frontend/src/api.ts`.
- CLI: `cli.py` with `dj-sim`, `eval`, `classifier`, and `index` command groups.
- Scanning and audio: `scanner.py`, `audio_loader.py`, `media_preview.py`.
- Analysis: `analysis_jobs.py`, `analysis_config.py`, `analysis_model_runners.py`, `sonara_features.py`, `genres.py`, `embedding.py`.
- Search and sets: `search.py`, `sonara_similarity.py`, `sonara_similarity_scoring.py`, `hybrid_search.py`, `set_builder.py`, `transition_diagnostics.py`.
- Tags and exports: `tags.py`, `wave_tags.py`, `exporter.py`.
- Classifiers: `classifier_manifest.py`, `classifier_production.py`, `classifier_scoring.py`, `classifier_jobs.py`, `rhythm_lab_collections.py`, `rhythm_lab_launcher.py`.
- Tools: `tools/audio-doctor/`, `tools/audio-dedup/`, `tools/rhythm-lab/`.

## Safety Invariants To Keep In Docs

Do not weaken or blur these invariants:

### Audio files and tags

- Scan, Refresh Tags, analysis, search, preview, reset, relocation preview, export, and classifier scoring must not modify source audio.
- Browser preview may transcode `.aif`/`.aiff` to temporary WAV for streaming, but it must not rewrite or cache source audio.
- `/api/tags/genres/apply` is the explicit standard genre tag write path. It writes only the stored MAEST-derived genre field and preserves normal tags such as title, artist, album, BPM, and key.
- WAV genre writes use Mutagen WAVE/ID3 handling and read back `TCON`; do not document custom RIFF repair as part of the app tag-write path.

### SQLite and destructive state

- SQLite writes route through `LibraryDatabase` with path-scoped write locking, WAL, and busy timeout.
- `dj-track-similarity.sqlite` and user-selected `.sqlite` files are local user state.
- Tests use temp DBs and deterministic fixtures, not the real music library.
- Relocation apply updates stored `tracks.path` values only; it does not move, copy, delete, or retag audio.
- Reset controls are database-only per analysis family.
- Database clear deletes SQLite records only and requires explicit UI confirmation.
- Destructive SQLite maintenance on real DBs needs backup/copy first and should finish with integrity/orphan checks.

### Audio Doctor and Audio Dedup

- Audio Doctor is dry-run-first. `--apply` may rewrite only files previously reported as `REPAIRABLE`, runs sequentially, and creates backups by default.
- Audio Doctor UI/API apply mode requires exact `APPLY REPAIR` confirmation.
- Audio Dedup is report-only by default and opens SQLite read-only.
- Audio Dedup `--apply` requires exact `APPLY DELETE`, deletes only safe duplicate candidates inside selected `--root`, and removes SQLite rows only for tracks whose files were deleted.
- Do not use apply modes in routine verification or tests.
- Do not compare Audio Dedup thresholds with CLAP text-search scores; they are different scoring surfaces.

### Classifiers and Rhythm Lab

- Promoted classifier scoring is database-only: it reads existing SONARA features plus MERT and MAEST embeddings and writes only `track_classifier_scores`.
- Scoring is scoped by `classifier_key`; do not imply one classifier recomputes or deletes another classifier's scores.
- Rhythm Lab reads the main SQLite DB mostly read-only; labels, predictions, and checkpoints stay under `tools/rhythm-lab/data/`.
- Rhythm Lab's explicit liked-track toggle is the narrow source-DB write path.
- Classifier calibration is optional and data-gated.

### Runtime and dependencies

- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`.
- Keep one instance per fixed port: backend `8765`, Vite frontend `5173`, Rhythm Lab `8777`.
- Windows CUDA ML stack currently expects synchronized PyTorch-family packages from the project docs. Do not invent alternate tested stacks.

## Domain Terms To Document Accurately

- **SONARA**: explainable audio features and SONARA similarity.
- **MERT, MAEST, CLAP**: embedding/label model families. Keep their scoring semantics separate.
- **CLAP text search**: text-to-audio cosine or contrast evidence, often lower than seed-based scores. Do not describe it as probability.
- **SET / Smart Set Builder**: read-only set preview generation from manual seeds or automatic anchors.
- **CLASS**: optional promoted classifier score modifiers and filters.
- **Rhythm Lab**: separate labeling/training/promote workflow.
- **Audio Doctor**: repair helper that is dry-run-first and confirmation-gated.
- **Audio Dedup**: duplicate candidate reporting by default, confirmation-gated delete mode.
- **Local-first safety**: no upload requirement for normal local workflows; local DB/log/report/model artifacts may reveal library information and stay out of Git.

## Existing Docs Routing

When adding or updating docs, choose the right page family:

- Installation and first run: `getting-started/quickstart.md`, `install.md`, `first-library.md`, `first-analysis.md`.
- Daily UI use: `user-guide/browse-library.md`, `analyze-library.md`, `search-with-seeds.md`, `smart-set-builder.md`, `text-search.md`, `class-tab.md`, `export-playlists.md`, `tags-and-audio-writes.md`.
- DJ workflows: `workflows/prepare-a-set.md`, `find-compatible-tracks.md`, `build-crates.md`, `train-personal-classifier.md`, `maintain-library.md`.
- Explanations: `concepts/local-first-safety.md`, `features-embeddings-tags.md`, `similarity-scores.md`, `smart-set-builder-routing.md`, `classifiers-and-rhythm-lab.md`.
- Helper tools: `tools-and-scripts/rhythm-lab.md`, `audio-dedup.md`, `audio-doctor.md`, `persistent-ann-indexes.md`, `optimize-database.md`.
- Facts and contracts: `reference/cli.md`, `api.md`, `database.md`, `configuration.md`, `analysis-families.md`, `ui-controls.md`.
- Developer docs: `developer/architecture.md`, `development.md`, `testing-and-verification.md`, `release-checklist.md`.
- Support: `help/troubleshooting.md`, `faq.md`, `known-limits.md`.

If changing README, keep it short and link to these pages instead of duplicating whole references.

## Verification For dj-track-similarity Docs

Before changing docs:

```powershell
git status --short --branch
git diff --stat
```

After Markdown-only docs changes, run at least:

```powershell
git diff --check -- README.md docs/dj-track-similarity
```

When practical for docs-tree changes, run the VitePress build from the docs package and do not commit generated output:

```powershell
cd docs\dj-track-similarity
npm run build
```

If the change affects source behavior, use the project verification matrix from `AGENTS.md`. Common checks:

```powershell
python -m pytest
cd frontend
npm run build
cd ..\docs\dj-track-similarity
npm run build
```

Use focused tests for touched behavior rather than full slow runs when appropriate. Examples:

```powershell
python -m pytest tests\test_api_text_search.py --override-ini addopts=
python -m pytest tests\test_api_set_builder.py --override-ini addopts=
python -m pytest tests\test_tags.py --override-ini addopts=
python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```

Do not run destructive helper apply modes just to verify docs.

# Generic Codebase Documentation Workflow

Use this section for other repositories, or as the base process before applying the `dj-track-similarity` profile.

## 1. Inspect Project Instructions And Existing Docs

First read repository guidance and docs:

- `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/*`, `.agents/*`, `.codex/*`
- `README*`, `CONTRIBUTING*`, `ARCHITECTURE*`, `TESTING*`, `CHANGELOG*`
- `docs/`, `examples/`, `scripts/`, CI files, Docker files, package manifests

Check repository state before edits:

```bash
git status --short --branch || true
git diff --stat || true
```

If the tree is dirty, avoid broad rewrites and mention pre-existing changes in the final report.

## 2. Build An Inventory Before Writing

Map the project:

- entry points and runtime commands;
- package managers and scripts;
- modules/packages and their responsibilities;
- public APIs, routes, CLI commands, events, jobs, or plugin points;
- configuration files and environment variables;
- persistence, state, queues, cache, file storage, network dependencies;
- auth, permissions, security boundaries;
- tests and verification commands;
- deployment and operational behavior;
- existing documentation gaps or contradictions.

Write a short internal plan before editing docs:

```markdown
## Repository map
## Existing docs
## Runtime and dev commands
## Architecture findings
## User-facing behavior
## Proposed docs
## Risks and unknowns
```

## 3. Choose Documentation Structure

Prefer existing project conventions. If none exist, use this default shape where applicable:

```text
README.md                         # overview, quickstart, docs index
docs/
  architecture.md                 # architecture and module map
  developer-guide.md              # local dev, tests, contribution workflow
  user-guide.md                   # user-facing setup and usage
  configuration.md                # env vars, config files, feature flags
  operations.md                   # deploy/run/backup/monitor/troubleshoot, if applicable
  api.md                          # APIs, CLI commands, events, contracts, if applicable
  troubleshooting.md              # known failures and fixes
```

For `dj-track-similarity`, do not use this generic layout. Use the VitePress tree described above.

Adapt by project type:

- **CLI**: command reference, common workflows, examples, config, troubleshooting.
- **Web app**: user flows, setup, auth, environment, deployment, UI behavior, screenshots only if available.
- **Service/API**: endpoints, auth, request/response examples, data flow, health checks, operations.
- **Library**: install, quickstart, public API, examples, compatibility, testing.
- **Plugin/integration**: prerequisites, setup, permissions, data flow, failure modes.

## 4. Write Technical Documentation

Technical docs should include:

- high-level architecture;
- module/package map;
- lifecycle/data flow;
- config and environment variables;
- public APIs/contracts/events/CLI commands;
- persistence/state/storage;
- security/auth/permissions model;
- testing strategy and exact safe commands;
- deployment/runtime/operations if applicable;
- extension points and known boundaries;
- troubleshooting tied to real errors or code paths.

Use concrete references, for example:

- `server.py` defines the HTTP app and health route.
- `src/auth/session.ts` manages session cookies.
- `package.json` exposes `npm run test` and `npm run build`.

Do not write vague filler like `robust scalable architecture` unless the repo proves it.

## 5. Write User-Facing Documentation

User docs should answer:

- What is this project?
- Who is it for?
- What do I need before installing/running it?
- How do I install or start it?
- How do I perform the main workflows?
- What should I see when it works?
- How do I configure it?
- What are common errors and fixes?
- Where do I go next?

Keep user docs task-oriented. Avoid dumping internal architecture into the user guide unless it helps the user make a decision or fix a problem.

## 6. Verify Documentation

After writing, verify rather than trusting your own final message.

Minimum verification:

```bash
git diff --stat
git diff -- README.md docs/ || true
```

If project tooling exists, run the relevant safe docs/build checks:

```bash
npm run docs:build || npm run build || true
pnpm docs:build || pnpm build || true
make docs || true
mkdocs build || true
sphinx-build -b html docs docs/_build/html || true
```

Do not run destructive commands, deployments, migrations, publishes, credential setup, deletes, resets, or external side-effect workflows just to verify documentation.

Check local markdown links when no docs tool exists:

```bash
python3 - <<'PY'
from pathlib import Path
import re
roots = [Path('README.md'), Path('docs')]
files = []
for root in roots:
    if root.is_file():
        files.append(root)
    elif root.is_dir():
        files.extend(root.rglob('*.md'))
for p in files:
    text = p.read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r'\[[^\]]+\]\(([^)]+)\)', text):
        target = m.group(1).split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'):
            continue
        q = (p.parent / target).resolve()
        if not q.exists():
            print(f'BROKEN_LINK {p}:{m.start()} -> {target}')
PY
```

## Final Response Format

When done, report:

```markdown
Documentation updated.

Changed files:
- `path` - what changed

Verification:
- `command` - result

Grounding examples:
- `doc claim` is based on `source path/symbol`

Still unknown / needs human input:
- `item`, or `None`
```

## Pitfalls

- Do not document filenames as behavior. Read the implementation path.
- Do not turn README into a dumping ground. Link to deeper docs.
- Do not overwrite existing careful docs with generic prose.
- Do not claim commands work unless they exist in manifests/scripts or were safely verified.
- Do not hide uncertainty. Good docs say what is unknown.
- Do not confuse maintainer docs with user docs. They answer different questions.
- For `dj-track-similarity`, do not create docs outside the tracked README plus VitePress tree unless the user explicitly asks.

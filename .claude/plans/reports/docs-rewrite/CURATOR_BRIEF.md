# Curator brief — documentation rewrite for dj-track-similarity

Prepared 2026-08-29 from three parallel `code-explorer` sessions plus curator verification.

Source reports, all in this directory. Read the ones your wave points you at, in full:

- `EXPLORER_1_BACKEND.md` — entry points, CLI contract, complete 76-route HTTP inventory, database model, job orchestration, runtime and file safety, dependency facts.
- `EXPLORER_2_MODELS.md` — model family matrix, SONARA depth, search and ranking, text-to-track, Evaluation package, classifiers and Rhythm Lab, the invariants, shipped-vs-WIP separation.
- `EXPLORER_3_FRONTEND_DOCS.md` — frontend UI map, `api.ts` contract surface, in-product help, tools and scripts inventory, test suite map, docs build and Vale rules, complete page-by-page drift table.

---

## 0. Curator corrections — the explorers got these wrong

Verify nothing against the reports alone where this section contradicts them. These four points were checked against the running repository.

**0.1 Classifier artifact layout is flat. There are no generations and no `current.json`.**
`EXPLORER_3` section 4 says Rhythm Lab writes "promoted generations under `models/classifiers/<prefix>/generations/` + `current.json`", and its page table calls `concepts/classifiers-and-rhythm-lab.md` ACCURATE for "the immutable-generation layout". Both statements are wrong. `EXPLORER_2` is right. Verified on disk:

```
models/classifiers/abstract-edge/{model.joblib,model.json}
models/classifiers/break-energy/{model.joblib,model.json}
models/classifiers/live-instrumentation/{model.joblib,model.json}
models/classifiers/minimal-deep-tech/{model.joblib,model.json}
models/classifiers/voice-presence/{model.joblib,model.json}
```

No `generations/` directory exists anywhere. `current.json` appears in no source file, and `tools/rhythm-lab/tests/test_consumers.py:1826` asserts `not (profile_dir / "current.json").exists()`. Every documentation passage describing immutable generations or a `current.json` switch is fiction and must be deleted: `concepts/classifiers-and-rhythm-lab.md:62`, `user-guide/class-tab.md:29-42`, `workflows/train-personal-classifier.md:177-179`.

**0.2 Audio Doctor state and report files are NOT committed.**
`EXPLORER_3` claims "~63 committed JSON artifacts" under `tools/audio-doctor/data/`. False. `git ls-files tools/audio-doctor/data` returns exactly three `.gitkeep` files. The JSON files exist on the working disk and are correctly ignored. Do not write that the repository ships local user state.

**0.3 SONARA version — CORRECTED 2026-08-29 by the owner. The project requires 0.3.6.**
An earlier revision of this brief told the writers to publish `0.3.5` because that is what the
manifest pins. That was wrong, and the README's `0.3.6` was right.

`src/dj_track_similarity/sonara_storage.py` reads `provenance.bpm_min` and `provenance.bpm_max`
through `_required_float`. The SONARA changelog records that BPM range provenance was added in
`0.3.6`. On `0.3.5` that read raises and every SONARA analysis fails, so the manifest pin does not
describe a working environment.

The tested runtime is a `0.3.6` wheel built from the SONARA repository at tag `v0.3.6`, commit
`15fb81d`, with the build patches the owner maintains locally. Publish `0.3.6` as the tested
version and describe `sonara==0.3.5` as a stale pin. Do not publish the private build path.

**0.4 The stale Vale vocabulary is harmless.**
`EXPLORER_3` flags `accept.txt` as missing MuQ, MuQ-MuLan, PROMPT, PyAV. `.vale.ini` sets `BasedOnStyles = ai-tells`, which contains no spelling or terminology rule, so the vocabulary list is inert. Do not edit `.vale/`.

---

## 1. The hard gate

`docs/dj-track-similarity` currently reports **0 errors, 0 warnings, 0 suggestions across 52 files**. Verified by the curator immediately before this brief. Your work must leave it at zero.

```bash
npm --prefix ./docs/dj-track-similarity run check
```

`check` = `lint:style:strict && build`. Strict mode exits nonzero on any single alert, so one em dash fails the docs build.

`EXPLORER_3` section 7 lists all 61 `ai-tells` rules with the exact message each produces. Read that table before writing. The rules that will bite hardest:

- No em dashes. No semicolons. Use a comma, a period, or parentheses.
- No "not X, but Y" and no trailing negation ("It is fast, not slow").
- No three parallel verbs in series, and never two such series in one paragraph.
- Lowercase after a colon unless the next word is a proper noun.
- No headings named "Conclusion", "Summary", "Wrapping up", "What is X?", or anything with marketing puffery.
- No opening lead-ins, closing pleasantries, hedges, throat-clearing, or "as mentioned above" cross-references.
- No "serves as" or "functions as" where "is" works.
- Every absolute assertion must be verifiable or softened.

Prose that states a measured fact with a number and a file reference passes these rules naturally. Prose that summarizes and reassures does not.

---

## 2. What the documentation is for

Read `README.md`, `CLAUDE.md`, and `AGENTS.md` before writing. The product framing is not decoration, it is a constraint on what you may claim.

- The project is a local-first DJ library workbench. Model outputs are **ranking evidence, never objective DJ decisions**. Never write that a score means two tracks are objectively similar.
- Score spaces never mix. `EXPLORER_2` section 7 enumerates eight distinct scales. Comparing across them is undefined, and the documentation must say so wherever two families appear on one page.
- Source audio is user data. Scan, preview, analysis, search, reset, relocation preview, export, graph export, and classifier scoring must not modify it. The genre tag write is the single backend audio writer.
- The checkout is under active development. Schemas, weights, defaults, and UI structure are not permanent APIs. Document current behavior, not plans, and keep aspiration clearly labelled as direction.

---

## 3. The five defects that dominate everything else

Fix these first, in every page your wave owns.

### 3.1 The shipped UI is in Russian. All 51 pages describe an English UI.

Verified by the curator. Panel headings (`1. База и анализ`, `2. Библиотека и прослушивание`, `3. Поиск и прослушивание`), every button title, every tooltip, every notice, and the whole of `frontend/src/helpText.ts` are Russian. Only technical tokens stay English: model names, `LAB`, `SONARA`, `SIMILARITY`, `PROMPT`, `CLASS`, mode names such as `Balanced` and `DJ transition`, and field labels such as `Limit` and `Mode`.

Every English control name in the current documentation is unfindable on screen. This is the single largest gap and no page acknowledges it.

**Required response.** Where a page names a control, give the Russian string the user will actually see, with the English meaning alongside. Example form:

> Press **Загрузить треки в базу** (load tracks into the database) in panel `1. База и анализ`.

Wave C additionally creates one label glossary and every other page links to it rather than repeating the mapping.

### 3.2 `uv sync --locked` fails today.

Verified by the curator with a dry run:

```
The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
```

`uv.lock:573` records `provides-extras = ["ann", "sonara", "ml", "rhythm-lab", "dev"]` while `pyproject.toml` declares only four extras. There is no `ann` extra. The documented install command is broken in `README.md:371`, `getting-started/install.md:81,123`, `getting-started/quickstart.md:21`, and `developer/development.md:23`.

**Required response.** Do not silently change the command to something you have not run. Document `uv sync --extra sonara --extra ml --extra rhythm-lab --extra dev` as the working form, and state plainly that `--locked` currently fails because the lockfile and the manifest disagree about extras. The lockfile fix is a code change the curator is routing separately, not yours to make.

### 3.3 Persistent ANN indexes do not exist.

No code, no extra, no `.dj-track-similarity-indexes/` writer. `src/dj_track_similarity/vector_index.py` contains only `ExactVectorSearchBackend`. Delete every mention: `reference/configuration.md:41`, `getting-started/install.md:114-118`, `concepts/local-first-safety.md:14`, `reference/analysis-families.md:41`, `getting-started/first-analysis.md:32`, and the README link to a `persistent-ann-indexes.md` page that has never existed.

### 3.4 Audio Doctor has no confirmation phrase.

Verified by the curator. The string `APPLY REPAIR` appears in five prose files and in zero Python sources. `tools/audio-doctor/audio_doctor/core.py` contains no `input()` call and no occurrence of the word "confirm". Line 268 reads `apply_changes = args.apply`, so `--apply` writes immediately.

Audio Doctor is genuinely dry-run-first, backup-by-default, verified, and restore-on-failure. It is **not** confirmation-gated.

**Required response.** State the real protections and remove the phrase claim from `concepts/local-first-safety.md:44`, `user-guide/tags-and-audio-writes.md:44`, `tools-and-scripts/audio-doctor.md:31-35`, `index.md:79`, and `help/faq.md:12`. Overstating a safety gate on the canonical safety page is the most damaging error in the current documentation. The curator is reporting the missing gate to the owner as a code question.

Related and separate: Audio Dedup **does** enforce `APPLY DELETE`, but only the CLI makes a human type it. The browser client inserts the phrase itself (`frontend/src/audioDedupView.ts:17`) and the user answers a **Да / Нет** dialog. Say exactly that, and stop writing that the browser delete button stays disabled until a phrase matches. It does not: `canDelete = summary.files > 0 && !dedup.busy`.

### 3.5 Phantom analysis controls.

There is no `CLASSIFIERS` checkbox and no `FULL` button. Stages come only from `sonara` and `ml` (`frontend/src/App.tsx:1157-1161`, `analysisSelection.ts:5`). Remove the claim from `getting-started/first-analysis.md:119,124`, `user-guide/analyze-library.md:12,27`, `user-guide/class-tab.md:69-76`, and `reference/ui-controls.md:47-49`.

Conversely, **ML Staged Mode is real** and three pages deny it. It has a Direct/Staged selector, a staging folder, Workers `1..16` default 4, and StageSize `1..512` default 64 (`LibraryPanel.tsx:232-250`, `mlAnalysisSettings.ts:17-24`), a CLI surface (`dj-sim analyze --ml-staged --ml-staging-path`), a pipeline API block, and a test file (`tests/test_ml_staging.py`).

There are no per-model tabs. `MERT tab`, `MULAN tab`, and `MUQ tab` do not exist. Seed search is the **SIMILARITY** tab with a model selector over `maest, mert, muq, mulan`. CLAP has no browser seed entry, though `/api/search` and LAB accept it.

The text tab renders as **PROMPT**, not TEXT. The internal key is still `text`. `frontend/tests/searchPlaylistLayout.test.mjs:119` pins the label.

---

## 4. Rules for the writing itself

**Ground every factual claim.** A number, a default, a range, a path, or a table name must come from the reports or from a file you opened. Where the reports mark something `NOT VERIFIED`, either verify it yourself or drop the claim. Do not carry an unverified number forward because it was already published.

**Do not cite `file.py:line` in the published prose.** Line numbers rot. Name the module or the command when the reader needs to act on it, and keep the citation in your own working notes.

**Delete rather than soften.** A passage describing a feature that does not exist is removed, not hedged. `AGENTS.md` calls for one discoverable source of truth and forbids aliases, duplicate registries, and hidden legacy branches. The same applies to prose.

**Do not duplicate.** `EXPLORER_3` section 9 found the SONARA three-output rule restated in seven places and the audio-write path list in four. Each fact gets one owner page. Other pages link to it. Wave assignments below name the owner for each contested fact.

**Respect the audience separation.** `getting-started` and `user-guide` describe what a person does in the running app. `reference` states contracts exhaustively. `concepts` explains why a signal means what it means. `developer` addresses someone changing the code. `workflows` chains existing pages into an outcome. Do not turn a user page into a schema dump.

**Preserve the front-matter convention.** Pages carry `> Audience:`, `> Goal:`, `> Type:` blocks that `.vale.ini` deliberately ignores. Keep the pattern on every page you touch, including new ones.

**Do not edit these files.** Report needed changes in your final summary instead:
- `docs/dj-track-similarity/.vitepress/config.mts` (the curator owns the sidebar and nav)
- `README.md`, `README_RU.md`, `CLAUDE.md`, `AGENTS.md`
- `.vale.ini` and anything under `.vale/`
- any file outside `docs/dj-track-similarity/`

**Do not touch code.** You are documenting the codebase, not fixing it. Every code defect the explorers found is already routed to the owner.

---

## 5. Wave assignments

Each wave owns a disjoint page set. No page is touched by two waves.

### Wave A — Reference and Developer (15 pages)

`reference/`: index, commands, cli, api, database, configuration, analysis-families, sonara-integration, model-citations, ui-controls.
`developer/`: index, architecture, development, testing-and-verification, release-checklist.

Primary sources: `EXPLORER_1_BACKEND.md` in full, `EXPLORER_2_MODELS.md` sections 1-7, `EXPLORER_3_FRONTEND_DOCS.md` sections 2, 4, 5, 6, 7.

This wave owns, as the single source of truth:
- the complete CLI contract, including the seven `dj-sim analyze` options currently missing and the `validate-database` exit code 2
- the complete HTTP inventory, including the 12 endpoints the shipped client calls that `api.md` omits and the entire 7-route Evaluation group
- the database table inventory, including `text_preset_feedback` and its lazy creation
- every environment variable and every browser `localStorage` key
- the SONARA three-output rule, in `reference/analysis-families.md`
- every UI control, in `reference/ui-controls.md`, with Russian labels

`reference/cli.md` is a six-line redirect occupying a primary sidebar slot. Empty its content into `reference/commands.md`, retitle that page "CLI reference", and leave `cli.md` for the curator to delete along with its sidebar entry and inbound links.

### Wave B — Getting started, User guide, Workflows (19 pages)

`getting-started/`: index, quickstart, install, first-library, first-analysis.
`user-guide/`: index, browse-library, analyze-library, search-with-seeds, text-search, class-tab, export-playlists, tags-and-audio-writes.
`workflows/`: index, find-compatible-tracks, build-crates, train-personal-classifier, reanalyze-sonara-split-storage, maintain-library.

Primary sources: `EXPLORER_3_FRONTEND_DOCS.md` sections 1, 3, 8 in full, `EXPLORER_2_MODELS.md` sections 2, 3, 4, 6, 10, `EXPLORER_1_BACKEND.md` sections 2, 5, 6.

This wave carries the heaviest Russian-label burden, because these are the pages a person reads with the app open. Every control name needs its real string.

Specific work beyond the five dominant defects:
- the scan dialog ships 14 format badges, not 10. AAC, APE, WMA, and WavPack are missing from `first-library.md:55` and are pinned by `tests/test_supported_audio_formats.py`
- the scan dialog's SONARA BPM range section, with presets, the lock, the octave rule, and the reset requirement, is undocumented in `first-library.md`
- scan does not read catalog number, disc number, or ISRC. It reads exactly artist, title, album, genre, year, country, label, track number, BPM, key, comment
- `quickstart.md:111` uses the prompt `"no vocals"`, which violates the project's own documented rule against negation in prompts. Replace it and name the Negative field instead
- the PROMPT tab auto-switches models when a preset's measured axis disagrees with the current selection, and shows a "Переключить на …" button. Undocumented
- the PROMPT tab fires a warmup request on open and on model change. Undocumented, and it explains the visible loading banner
- classifier scoring is incremental and never re-scores. A retrain requires an explicit reset first, or the job finds zero work. `train-personal-classifier.md` step 8 and `reanalyze-sonara-split-storage.md` step 6 both need this
- resetting SONARA does not delete classifier scores. `first-analysis.md:200` says it does
- promotion binds an artifact to one `source_catalog_uuid` and requires calibration by default
- `maintain-library.md` claims a browser relocation preview. Relocation is CLI-only
- `train-personal-classifier.md:193` sends `{"classifier_keys": [...]}`. The real payload is `{"classifier_key": "..."}`
- "Add Random Track" exists in both SONARA and SIMILARITY and is undocumented
- the text contrast score subtracts the **mean of the two highest** negative similarities scaled by the weight, not the single strongest. `text-search.md:247` is wrong

### Wave C — Root pages, Concepts, Tools and scripts, Help (18 existing pages plus 3 new)

`index.md`, `project-guide.md`.
`concepts/`: index, project-idea, local-first-safety, features-embeddings-tags, similarity-scores, classifiers-and-rhythm-lab.
`tools-and-scripts/`: index, rhythm-lab, audio-dedup, audio-doctor, optimize-database.
`help/`: index, troubleshooting, faq, known-limits.

New pages this wave creates:
1. `tools-and-scripts/audio-online.md` — an entire undocumented tool. 16 modules, 11 test files, Discogs, MusicBrainz, Last.fm, and Beatport v4 OAuth, read-only, produces one formatted XLSX. Its own README is the only current documentation. Cover credential configuration through `config.toml` and the `METADATA_ENRICHMENT_NODE` variables, and state that it never writes tags.
2. `tools-and-scripts/scripts.md` — the section is titled "Tools and scripts" and lists zero scripts. Cover `qa_database.py`, `benchmark_search.py`, `clap_checkpoint_embed.py`, `text_prompt_benchmark.py`, `text_fusion_benchmark.py`, `text_tag_crosscheck.py`, `prompt_preset_tune.py`, plus `spectral_check_cli.py` and `benchmark_fingerprint_candidates.py` under `tools/audio-dedup/`. `AGENTS.md` requires a committed `text_prompt_benchmark.py` table for any reliability claim, so that script in particular needs a real entry.
3. `help/ui-language.md` — the Russian label glossary. Panel headings, top-bar buttons, the five tabs, the analysis cards, the scan dialog, the dedup reviewer, and the confirmation dialog. Waves A and B link here rather than repeating the mapping.

This wave owns, as the single source of truth:
- the audio-write path list, in `concepts/local-first-safety.md`. It currently appears in four places, all four carrying the false `APPLY REPAIR` claim
- the score-space separation rules, in `concepts/similarity-scores.md`, including the eight scales and the contrast formula
- the shipped-versus-direction boundary, in `concepts/project-idea.md` and `help/known-limits.md`

Specific work beyond the five dominant defects:
- `index.md:45` promises "Draft a musical route — turn a few anchors into an editable sequence with a chosen energy, diversity, and tempo direction". No such generator exists. The current set is manual. Remove the promise or move it to a clearly labelled direction section
- `concepts/features-embeddings-tags.md:43` and the equivalent line in `analysis-families.md` claim the `sonara` classifier source includes vocalness. Rhythm Lab excludes `vocal_probability` and the whole aggression family by design
- `help/known-limits.md` omits the real current limits: the Russian UI against English documentation, the absence of automatic set generation, the unauthenticated local API on LAN, and Audio Doctor having no in-app surface
- `help/troubleshooting.md` needs the symptoms a user actually hits: greyed-out ML checkboxes before the first SONARA row, a greyed-out PROMPT search with no stored embeddings, Staged Mode refusing to start without a folder, and the BPM range locking after the first SONARA analysis
- `tools-and-scripts/audio-doctor.md` documents 5 of 22 CLI flags and claims an app integration that does not exist. Audio Doctor has no API route at all
- `tools-and-scripts/optimize-database.md` omits the fields the script actually prints
- `help/faq.md:48` describes chunked loading. Loading is one fixed 200-track page per request

---

## 6. What to hand back

Finish with a summary that names:

1. Every page you rewrote, updated, expanded, or created, one line each, saying what changed.
2. The result of `npm --prefix ./docs/dj-track-similarity run check`, quoted. If it does not reach zero alerts, say so and name the rules that fired.
3. Sidebar and nav changes the curator must make in `.vitepress/config.mts`, as exact entries.
4. Changes needed in `README.md` that you were not permitted to make.
5. Anything you could not verify and therefore left out, and any claim in the explorer reports you found to be wrong.

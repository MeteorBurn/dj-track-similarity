I have everything needed. Here is my report.

---

# EXPLORER REPORT: Frontend, tools, scripts, tests, and full docs-vs-code drift audit

**Tooling note:** graphify CLI was unavailable in this read-only role (no Bash tool), so all findings come from direct file reads. Every claim below is cited to `path:line`.

**Systemic finding that dominates everything else:** the shipped UI is written entirely in **Russian**. Every panel heading, button title, tooltip, empty state, confirmation dialog, and the whole of `helpText.ts` is Russian prose. All 51 documentation pages describe an **English** UI with invented English control names. Users reading the docs will not find the labels described. This is the single largest docs-vs-code gap and no page acknowledges it.

---

## 1. Frontend UI map

`main.tsx` mounts `App` (`frontend/src/App.tsx:106`). The shell is a top bar plus a three-column `section.workspace` (`App.tsx:1648`), with dialogs rendered as siblings.

### Top bar (`App.tsx:1581-1646`)

| Control | Code | Behavior | Endpoint | Docs page that should own it |
|---|---|---|---|---|
| Title link "DJ Track Similarity" | `App.tsx:1584`, `openDocumentationWindow` `:93` | Opens `/docs/` in a new window | static `/docs/` | `reference/ui-controls.md` |
| Theme toggle (Sun/Moon) | `App.tsx:1590-1599`, `theme.ts` | Light/dark, persisted at `localStorage["dj-track-similarity-theme"]` (`theme.ts:3`) | none | `reference/ui-controls.md` — **undocumented** |
| Log button (ScrollText) | `App.tsx:1600-1609` | Opens `LogFrameDialog`; gets a `has-errors` class when any job/activity event is `error` (`:322-329`) | none | `reference/ui-controls.md` — **undocumented** |
| Rhythm Lab flask | `App.tsx:1610-1620`, `handleLaunchRhythmLab` `:1541` | Opens a blank tab first, then redirects it to the launch URL | `POST /api/rhythm-lab/launch`, `GET /api/rhythm-lab/status` | `tools-and-scripts/rhythm-lab.md` (documented) |
| Power button | `App.tsx:1621-1630`, `shutdownApplication.ts:7` | Shutdown → acknowledge → `window.close()`; on block, renders the "Серверы остановлены" screen (`App.tsx:1567-1577`) | `POST /api/server/shutdown` with header `X-DJ-Track-Similarity-Action: shutdown-server` (`apiClient.ts:274-279`) | `reference/ui-controls.md` (documented) |
| Stop button (Square) | `App.tsx:1631-1640`, `handleStopActiveStage` `:1424` | Cancels the active scan → analysis → genre-tag stage in that priority | scan/analysis/pipeline/genre cancel routes | `reference/ui-controls.md` — **undocumented** |
| Process indicator + notice | `App.tsx:1641-1644`, `stageIndicatorLabel` in `jobUi.tsx:229` | Spinner + Russian status text | none | — |

### Panel 1 — `LibraryPanel.tsx` ("1. База и анализ")

| Element | Code | Endpoint |
|---|---|---|
| Read-only DB path + picker | `LibraryPanel.tsx:182-185` | `POST /api/database/dialog`, `GET /api/database/current` |
| "Загрузить треки в базу" | `:187` | opens `ScanImportDialog` |
| Refresh tags (RefreshCcw) | `:188` | `POST /api/library/tags/refresh` with `workers: 8` (`App.tsx:1256`) |
| Save genres (Save) | `:189` | `POST /api/tags/genres/jobs` |
| **Validate database (ShieldCheck, "Проверить базу")** | `:190` | `POST /api/database/validation/jobs` — **zero documentation anywhere** |
| Audio Dedup (CopyCheck) | `:191` | opens `AudioDedupDialog` |
| Clear database (Trash2) | `:192` | `POST /api/database/clear`, confirmation-gated (`App.tsx:1678-1682`) |
| SONARA card: checkbox, counter, reset, Mode Direct/Staged, staging folder picker, BatchSize / Processes / Threads / StageSize | `:199-226` | `POST /api/analysis/pipelines`, `POST /api/analysis/reset` |
| ML card: 5 checkboxes (MAEST, MERT, MUQ, MULAN, CLAP), **Mode Direct/Staged**, **ML staging folder**, **Workers**, **StageSize**, Device segmented, Track batch, Inference batch | `:228-272` | same |
| Analyze limit stepper (`0..100000`) | `:274-282` | — |
| Single **Analyze** button | `:283-292` | `POST /api/analysis/pipelines` |

There is **no `CLASSIFIERS` checkbox and no `FULL` button**. Stages are computed only from `sonara` + `ml` (`App.tsx:1157-1161`). Model rows come from `audioAnalysisModelOrder` = `["sonara","maest","mert","muq","mulan","clap"]` (`analysisSelection.ts:5`). ML checkboxes are disabled until `analysisCounts.sonara >= 1` (`LibraryPanel.tsx:164`).

### Panel 2 — `TrackPanel.tsx` ("2. Библиотека и прослушивание")

Search box with LIKE/FTS toggle (`:135-168`); pagination group `Prev` / `Next` / page-number input / `current/total` / range / filtered-total (`:170-213`); liked filter, syncopated preset, shuffle, sort-direction (`:214-261`); add-visible-tracks (`:262-271`); then `TrackList` (`TrackRows.tsx:16`).

Row actions (`TrackRows.tsx:39-88`): index, play/pause, title, inline seek bar when selected, like, tags, seed, playlist toggle.

**Pagination verified:** `libraryPageSize = 200` (`libraryLoading.ts:3`); one `/api/tracks` request per page (`useLibraryState.ts:212-221`); page math in `libraryView.ts:49-67`. README's claim is accurate. **However** sort direction and shuffle are purely client-side over the loaded page (`libraryView.ts:29-45`), contradicting `ui-controls.md:20`.

### Panel 3 — `SearchPlaylistPanel.tsx` ("3. Поиск и прослушивание")

Seed chip strip (`:346-353`), then a five-tab strip with roving ARIA and Arrow/Home/End navigation (`:354-372`, `searchSurfaceState.ts:29-40`).

**Tab order and labels (`searchSurfaceState.ts:6-12`, `SearchPlaylistPanel.tsx:94-100`):**

| Key | **Rendered label** | Panel | Endpoint |
|---|---|---|---|
| `lab` | LAB | `ReferenceComparePanel` | `POST /api/reference/compare`, `POST /api/reference/compare/verdict` |
| `sonara` | SONARA | inline mixer/modifiers | `POST /api/search/sonara`, `POST /api/search/sonara/random-track` |
| `similarity` | SIMILARITY | `EmbeddingSearchTab` | `POST /api/search`, `POST /api/search/random-track` |
| `text` | **PROMPT** | `TextSearchTab` | `POST /api/search/text`, `/warmup`, `/feedback` |
| `class` | CLASS | inline classifier list | `GET /api/classifiers`, `/analyze`, `/reset` |

**The tab is labeled `PROMPT`, not `TEXT`** (`SearchPlaylistPanel.tsx:97`). The frontend test suite confirms this is the maintained contract: `frontend/tests/searchPlaylistLayout.test.mjs:119` is named *"PROMPT tab keeps results from both text embedding models visible"*. Every docs page says "TEXT tab".

- **SONARA tab** (`:391-501`): Mixer 5 sliders `0..5` step `0.05` (defaults timbre 1, rhythm 1, dynamics 0.8, harmonic 0.8, tempo 0.35 — `App.tsx:222-228`); Modifiers 9 sliders `-1..1` with per-control Off reset; Reset button; **"Add Random Track"**; Mode select (Balanced/Vibe/Sound/DJ transition/Custom mixer); Limit `1..500`; SONARA search button.
- **SIMILARITY tab** (`EmbeddingSearchTab.tsx`): Model select over `["maest","mert","muq","mulan"]`, "Add Random Track", Limit `1..500`, Search. Disabled with a per-family reason when embedding count is 0 (`:39-44`). Default family is `mert` (`App.tsx:189`).
- **PROMPT tab** (`TextSearchTab.tsx`): preset picker (21 axes × 153 presets), selection chips, **model-advice block that can auto-switch CLAP↔MuQ-MuLan** (`:428-467`, `App.tsx:250-266`), "Prompt bank" textarea with line count, Negatives toggle + hard-negative textarea + weight readout, Model select (MuQ-MuLan default), Limit, **automatic warmup on open/model change** (`:188-202`), Search.
- **CLASS tab** (`SearchPlaylistPanel.tsx:549-672`): `available N · blocked N` summary; per profile a manifest fact row (Status, Type, Models, Features, Labels, Calibrated, Validation F1, Promoted), a rescore play button (reset then analyze, `App.tsx:941-942`), a delete button, and a `0..1` min-score slider disabled when `scored_tracks == 0`.
- **Results list** (`:673-711`): provenance header, `ResultRow` per hit with score meter, contrast positive/negative split for text search (`TrackRows.tsx:294-305`), and **thumbs-up / thumbs-down preset feedback buttons** when a preset built the list (`TrackRows.tsx:243-266`).
- **"Сет и экспорт"** collapsed `<details>` (`:713-779`): name input, 20-per-page playlist with Prev/Next (`playlistPageSize = 20`, `:29`), output dir + picker, `Collection` / `M3U` / `CSV` buttons.

### Dialogs

| Dialog | File | Purpose |
|---|---|---|
| `ScanImportDialog` | `ScanImportDialog.tsx` | 14 format chips, Scan limit, Min/Max seconds, Workers, **SONARA BPM range with presets + lock**, folder picker, Старт |
| `TrackMetadataDialog` | `TrackMetadataDialog.tsx` | MAEST genres, Track Details (copy path / copy name / **reveal folder**), Tags, Data, 10 SONARA feature groups with inline `#` descriptions, Classifier scores, Scan analyses details, delete-track action |
| `AudioDedupDialog` | `AudioDedupDialog.tsx` | Search / Report+filters / group list / footer |
| `AudioDedupReview` | `AudioDedupReview.tsx` | per-group card, per-copy card, per-group "mark all but keeper" and "clear group" |
| `ConfirmationDialog` | `dialogs.tsx:61` | title + message + **Нет / Да**. No phrase input anywhere. |
| `LogFrameDialog` | `dialogs.tsx:8` | unified process box + merged event log (max 200 events, `jobUi.tsx:6`) |
| `TooltipLayer` | `tooltipLayer.tsx` | viewport-clamped tooltips |

---

## 2. Frontend contract surface

### Endpoint inventory the UI actually calls (`apiClient.ts`)

| Endpoint | Method | Line | In `reference/api.md`? |
|---|---|---|---|
| `/api/database/current` | GET | 173 | yes |
| `/api/database/dialog` | POST | 175 | yes |
| `/api/database/clear` | POST | 180 | yes |
| `/api/tracks/{id}` | DELETE | 188 | yes |
| `/api/tracks?…` | GET | 206 | yes |
| `/api/tracks/filtered` | POST | 211 | yes |
| `/api/tracks/{id}` | GET | 222 | yes |
| **`/api/tracks/{id}/reveal`** | POST | 226 | **NO** |
| `/api/tracks/{id}/liked` | POST | 231 | yes |
| `/api/library/summary` | GET | 239 | yes |
| `/api/library/scan` | POST | 241 | yes |
| `/api/library/tags/refresh` | POST | 246 | yes |
| **`/api/library/scan/jobs/{id}`** | GET | 250 | **NO** |
| **`/api/library/scan/jobs/latest`** | GET | 251 | **NO** |
| **`/api/library/scan/jobs/{id}/cancel`** | POST | 253 | **NO** |
| **`/api/database/validation/jobs`** | POST | 257 | **NO** |
| **`/api/database/validation/jobs/{id}`** | GET | 258 | **NO** |
| **`/api/database/validation/jobs/latest`** | GET | 259 | **NO** |
| `/api/dialog/folder` | POST | 264 | yes |
| `/api/rhythm-lab/status` | GET | 268 | yes |
| `/api/rhythm-lab/launch` | POST | 269 | yes |
| `/api/server/shutdown` | POST | 274 | yes |
| `/api/analysis/sonara/status` | GET | 283 | yes |
| `/api/analysis/reset` | POST | 285 | yes |
| `/api/analysis/jobs/{id}`, `/latest`, `/cancel` | — | 289-292 | yes |
| `/api/classifiers/{k}/analyze` | POST | 297 | yes |
| `/api/analysis/pipelines` (+ `{id}`, `/latest`, `/cancel`) | — | 301-304 | yes |
| `/api/classifiers/reset` | POST | 306 | yes |
| **`/api/classifiers/{k}/analyze/jobs/{id}`** | GET | 310 | **NO** |
| **`/api/classifiers/{k}/analyze/jobs/latest`** | GET | 311 | **NO** |
| **`/api/classifiers/{k}/analyze/jobs/{id}/cancel`** | POST | 313 | **NO** |
| `/api/classifiers` | GET | 317 | yes |
| `/api/search` | POST | 322 | yes |
| `/api/search/sonara` | POST | 328 | yes |
| **`/api/search/sonara/random-track`** | POST | 334 | **NO** |
| **`/api/search/random-track`** | POST | 340 | **NO** |
| `/api/search/text` | POST | 346 | yes |
| **`/api/search/text/warmup`** | POST | 352 | **NO** |
| **`/api/search/text/feedback`** | POST | 358 | **NO** |
| `/api/reference/compare` + `/verdict` | POST | 366, 371 | yes |
| `/api/export` | POST | 379 | yes |
| `/api/rhythm-lab/collections` | POST | 384 | yes |
| `/api/tags/genres/jobs` + `/latest`, `{id}`, `/cancel` | — | 401-408 | yes |
| `/api/audio-dedup/*` (7 routes + xlsx URL) | — | 414-445 | yes |
| `/media/{track_id}` | GET (audio src) | `App.tsx:1821` | yes |

**12 endpoints the UI calls are absent from `reference/api.md`.** Conversely `api.md:14` documents `POST /api/database/switch`, which the client never calls (NOT VERIFIED whether the backend still exposes it).

### Key types (`api.ts`)

Family unions:
- `EmbeddingSource = "mert" | "maest" | "muq" | "mulan" | "clap"` (`:1`)
- `AnalysisModel = "sonara" | EmbeddingSource` (`:2`)
- `AnalysisPipelineStage = "sonara" | "ml" | "classifiers"` (`:3`) — **`"classifiers"` is in the type but the UI never emits it** (`App.tsx:1159-1161`)
- `ReferenceCompareModel = "clap"|"mert"|"muq"|"mulan"|"maest"|"sonara"` (`:219`)
- `ReferenceCompareVerdict = "mood"|"palette"|"instruments"|"groove"|"genre"|"transition"|"miss"` (`:220`)
- `SonaraSearchMode = "balanced"|"vibe"|"sound"|"dj_transition"|"custom"` (`:286`)
- `AudioDedupSearchMode = "fingerprint" | "embedding"` (`:551`); `AudioDedupDeletionMode = "trash" | "permanent"` (`:553`)
- UI-only: `PrimarySearchTab`, `SeedEmbeddingFamily = "maest"|"mert"|"muq"|"mulan"`, `GenericSearchTab` (`searchSurfaceState.ts:1-3`)

Response types: `Track` (`:34`), `TrackDetail` (`:180`), `SonaraCore` (63 fields, `:88-150`), `LibrarySummary` (`:271`), `AnalysisJobStatus` (`:336`), `AnalysisPipelineStatus` (`:382`), `PromotedClassifier` (`:393`), `AudioDedup*` (`:551-723`), `DatabaseValidationJobStatus` (`:467`).

Client behavior worth documenting: a dropped pooled connection retries **GET/HEAD once, never a write** (`apiClient.ts:160-170`); `ApiError` carries `status` and prefers the JSON `detail` field (`:110-136`).

---

## 3. In-product help (`helpText.ts`) vs published docs

`frontend/src/helpText.ts` is 41 lines, 40 keys, **100% Russian**. It is the only in-product documentation and it is enforced by `frontend/tests/helpText.test.mjs`.

**Where it agrees with the docs:**
- `textPrompt` (`:37`) matches `user-guide/text-search.md:82-87`: short tag lines beat long scene descriptions; never write `no`/`without`; name unwanted classes in Negative.
- `clapAnalyze` (`:14`) matches the safety invariant keeping CLAP text scores separate from audio-to-audio CLAP evidence.
- `audioDedupSearchMode` (`:17`) matches `tools-and-scripts/audio-dedup.md:33-47`: fingerprint mode loads no embeddings and every candidate stays manual-review; embedding mode is the superset and the only auto-delete path.
- SONARA mixer/modifier help (`:23-36`) matches `user-guide/search-with-seeds.md:72-85` in substance.

**Where it contradicts or diverges:**

| helpText key | Says | Reality / docs |
|---|---|---|
| `scanWorkers` (`:5`) | "целое число 1-8. Для библиотеки на M: дефолт 8" | Range is **1..16** (`App.tsx:91` `maxScanWorkers = 16`); docs say `1..16`. Also leaks a private drive letter `M:`. |
| `analysisDevice` (`:8`) | "для MAEST/MERT/MuQ/CLAP" | Omits **MuQ-MuLan**, which also uses the device. |
| `analysisInferenceBatchSize` (`:16`) | "MAEST, MERT, MuQ и CLAP" + "дефолт для RTX 3090" | Omits MuQ-MuLan; names the author's specific GPU. |
| `refreshTags` (`:6`) | "Sonara, MAEST, MERT и CLAP не трогаются" | Omits MuQ and MuQ-MuLan. |
| `analyzeLimit` (`:4`) | "0-100000" | Matches `LibraryPanel.tsx:278`. Agrees. |
| `limit` (`:38`) | "1-500" | Agrees with all search tabs. |
| — | no entry | **No help for the ML Staged Mode, the database-validation button, the theme toggle, the log button, or the preset picker.** |

**Net:** in-product help is a fifth documentation surface in a different language from the published docs, with its own drift. The docs never mention it exists.

---

## 4. Tools inventory

### `tools/audio-dedup`

| Aspect | Fact |
|---|---|
| Invocation | `python tools/audio-dedup/audio_dedup_cli.py --root PATH [...]` (thin wrapper → `audio_dedup.core.main`, `audio_dedup_cli.py:3`) |
| Also ships | `spectral_check_cli.py` (standalone transcode detector over files/dirs/`--list`, `--csv`), `benchmark_fingerprint_candidates.py` (synthetic recall/cost benchmark) |
| Modes | `--fingerprint` (default) vs `--embedding`, mutually exclusive (`core.py:402-427`) |
| Sources | `SUPPORTED_EMBEDDINGS = ("mert","maest","muq","clap")` (`core.py:44`) — **no `mulan`** |
| Defaults | `--db` → `<repo>/database/volumes.sqlite` (`core.py:41`); `--out-dir` → `tools/audio-dedup/data/reports` (`:43`); `--preset safe`; fingerprint review floor `0.45` (`:47`) |
| **CLI safety gating** | Report-first. `--apply` prints a `DESTRUCTIVE APPLY REQUESTED` block and requires the user to type **exactly** `APPLY DELETE` (`core.py:2519-2531`). Deletes only safe candidates inside `--root`; skips a candidate whose keeper is missing. |
| **Browser safety gating** | The reviewer marks copies, chooses trash/permanent, and answers a **Да/Нет** dialog (`AudioDedupDialog.tsx:91-104`). The phrase `APPLY DELETE` is inserted by the **client**, not typed (`audioDedupView.ts:17`, `:389`). The source comment says so explicitly: *"this is the client speaking the word the API demands rather than something anyone types."* Delete button enablement is `summary.files > 0 && !dedup.busy` (`AudioDedupDialog.tsx:70`) — no phrase check. |
| Client-side pre-refusal | A selection that would empty a group is rejected before the request (`audioDedupView.ts:336-338`, `:375-383`) |
| Outputs | JSON + XLSX + text log under `tools/audio-dedup/data/reports/` |
| Tests | `tools/audio-dedup/tests/`: `test_cli_output.py`, `test_fingerprint_candidates.py`, `test_fingerprint_benchmark.py`, `test_spectral.py`. Plus `scripts/tests/test_audio_dedup.py` and `tests/test_api_audio_dedup.py` (5 tests, incl. `test_audio_dedup_delete_requires_the_confirmation_phrase:211`). |
| Docs status | Well covered by `tools-and-scripts/audio-dedup.md` (449 lines) except the browser confirmation claim. |

### `tools/audio-doctor`

| Aspect | Fact |
|---|---|
| Invocation | `python tools/audio-doctor/audio_doctor_cli.py [paths] [--folder|--log|--db ...]` |
| Options | 22 flags (`core.py:1125-1239`): `--folder`, `--log`, `--db`, `--db-root`, `--file-root`, `--since`, `--until`, `--apply`, `--backup-dir`, `--no-backup`, `--keep-id3 first|last|none`, `--limit`, `--summary-only`, `--color`, `--file-log`, `--no-file-log`, `--out-dir`, `--no-report`, `--state`, `--workers`, `--reason` |
| **Safety gating — CRITICAL FINDING** | Dry-run-first: yes. Backup-by-default: yes. Verify + restore-on-failure: yes. Sequential apply: yes. **Confirmation phrase: NO.** A repo-wide grep for `APPLY REPAIR` matches only 5 files, all prose: `README.md`, `tools/audio-doctor/README.md:29`, `docs/.../tools-and-scripts/audio-doctor.md:34`, `docs/.../concepts/local-first-safety.md:44`, `docs/.../user-guide/tags-and-audio-writes.md:44`. **No Python source contains the phrase, and `core.py` has no `input()` prompt at all.** `--apply` writes immediately. |
| API surface | **None.** A grep for `audio.doctor|audio_doctor` across `src/` returns zero files. It is CLI-only. |
| Outputs | JSON/XLSX/log under `tools/audio-doctor/data/reports/`, state under `data/state/`, backups under `data/backups/`. **The checked-out tree contains ~60 committed state JSON files and 3 report JSONs referencing `library.sqlite`** — local user state living in the repo. |
| Tests | `scripts/tests/test_repair_audio_metadata.py` (40 tests) |
| Docs status | `tools-and-scripts/audio-doctor.md` is 44 lines, documents 5 of 22 flags, and states a confirmation that does not exist. |

### `tools/rhythm-lab`

| Aspect | Fact |
|---|---|
| Invocation | `python tools/rhythm-lab/rhythm_lab_cli.py <subcommand>` |
| Subcommands (`rhythm_lab/cli.py`) | `train` (51), `benchmark-ablation` (66), `predict` (76), `export-predictions` (82), `promote` (88), `calibration-report` (119), `suggest-labels` (130), `queue` (139), `queue-export` (145), `queue-mark` (152), `queue-clear` (159), `collection-save` (165), `collection-list` (176), `delete-profile` (180), `serve` (188) |
| Also | `python -m rhythm_lab.label_transfer {export,preview,rebound,restore}` |
| Safety gating | `delete-profile` requires `--confirm` matching the exact key or name (`cli.py:184`). `label_transfer restore` is preview-by-default; `--apply` backs up the target Lab DB plus `-wal`/`-shm` first and is idempotent. Source DB is opened read-only except the liked-track toggle. |
| **Code smell** | `DEFAULT_SOURCE_DB = Path(r"C:\db\abstracted.sqlite")` (`cli.py:35`) — a hard-coded personal absolute path shipped as a CLI default, and faithfully reproduced in `reference/commands.md:318`. This is exactly what `developer/release-checklist.md:7` forbids. |
| UI | Standalone at `127.0.0.1:8777` (`web_app.py`), page sizes 50/100/200/500 |
| Outputs | `tools/rhythm-lab/database/rhythm_lab.sqlite`, `tools/rhythm-lab/profiles/<key>/`, promoted generations under `models/classifiers/<prefix>/generations/` + `current.json` |
| Tests | `tools/rhythm-lab/tests/`: `test_rhythm_lab.py`, `test_label_transfer.py`, `test_consumers.py`; plus `tests/test_rhythm_lab_bridge.py` (10) |
| Docs status | Good (`tools-and-scripts/rhythm-lab.md`, 110 lines + `reference/commands.md`) |

### `tools/audio-online` — **completely undocumented**

| Aspect | Fact |
|---|---|
| What it is | A standalone read-only metadata-enrichment CLI producing one formatted XLSX where each provider gets its own column (`tools/audio-online/README.md:1-11`) |
| Invocation | `python tools/audio-online/metadata_enrichment_cli.py {enrich,authorize,check-auth}` (`metadata_enrichment_cli.py:24-38`) |
| Sources | Discogs, MusicBrainz, Last.fm, **Beatport v4 OAuth**, local file tags, MAEST |
| Config | `tools/audio-online/config.toml` (git-ignored) + `config.example.toml`; env `METADATA_ENRICHMENT_NODE`, `METADATA_ENRICHMENT_NODE_MODULES` |
| Inputs | folder of audio, plain-text `Artist - Title`, CSV/XLSX, M3U/M3U8 |
| Safety | Read-only. DB access is read-only by exact path. Never writes tags. |
| Modules | 16 Python modules (`config`, `auth`, `beatport_auth`, `beatport`, `discogs`, `lastfm`, `musicbrainz`, `http`, `inputs`, `local_library`, `matching`, `models`, `report`, `sources`, `workbook_format`) |
| **Tests** | **11 test files** — `test_config`, `test_auth`, `test_cli`, `test_local_library`, `test_inputs`, `test_matching`, `test_sources`, `test_report`, `test_workbook_format`, `test_http`, `conftest` |
| Docs status | **Confirmed: no sidebar entry, no page, not in `tools-and-scripts/index.md`.** The only mentions are `reference/cli.md:5` (a name in a sentence) and one `<details>` block in `reference/commands.md:453-471`. Its own README is the only real documentation. Its test suite is also absent from `developer/testing-and-verification.md`. |

---

## 5. Scripts inventory

| Script | Purpose | Invocation | Documented? |
|---|---|---|---|
| `run_server_launcher.py` | Builds the `dj-sim serve` argv and the `npm run dev`/`dev:lan` child; mode aliases `local/localhost/127.0.0.1/--local/lan/network/0.0.0.0/--lan` (`:11-22`); env overrides `DJ_TRACK_SIMILARITY_LAUNCHER_{HOST,PORT,DATABASE,FRONTEND_DEV,FRONTEND_HOST}` (`:23-27`); list-based args, `shell=False` | via `run_server.cmd` | Partly — `commands.md:260-274`. **The five env vars are documented nowhere**, including `reference/configuration.md`. |
| `optimize_database.py` | Backup → integrity check → SQLite maintenance; prints `database_kind`, integrity before/after, size before/after, per-file backup paths (`:182-201`) | `--db PATH` | Yes (`tools-and-scripts/optimize-database.md`, 19 lines) |
| `qa_database.py` | Read-only integrity QA for a library + optional Evaluation sidecar (`:1`, `:124`) | `--db`, `--evaluation-db` | `commands.md:285-292` only. **No `tools-and-scripts/` page.** |
| `benchmark_search.py` | Synthetic greenfield DB + MERT/MAEST vector-search benchmark (`:431-451`) | `--output` (req), `--track-count(s)`, `--seed-count`, `--per-source`, `--random-seed`, `--keep-db` | `commands.md:294-307` — **that table row is broken Markdown** (`||` at `:307`) |
| `clap_checkpoint_embed.py` | Embeds the labelled pool with one pinned LAION-CLAP checkpoint into an `.npz` sidecar; owns the checkpoint registry (`:34-48`) | `--db` (req), `--labels`, `--checkpoint`, `--out` (req), `--source`, `--device`, `--batch-size` | **NO — absent from `commands.md` and every page** |
| `text_prompt_benchmark.py` | Ranks a labelled library with prompt forms and reports ROC-AUC per form; the committed evidence base for every reliability claim (`:1-14`) | `--db` (req), `--labels`, `--prompts`, `--models`, `--device`, `--concepts`, `--out` | Named in `text-search.md:77,166,209` but **has no command reference entry** |
| `text_fusion_benchmark.py` | Measures whether CLAP+MuQ-MuLan rank fusion beats the better single model; the measurement that rejected fusion (`:1-11`) | `--db` (req), `--references`, `--device`, `--out` | **NO command reference entry** |
| `text_tag_crosscheck.py` | Cross-checks text-layer labels against SONARA signals; produces the `ok/weak/suspect/INVERTED` verdicts (`:1-13`) | `--db` (req), `--references`, `--models`, `--device`, `--out` | Named in `text-search.md:158`, **no command reference entry** |
| `prompt_preset_tune.py` | Report-first tuner over accumulated `text_preset_feedback` verdicts; weight grid + leave-one-out per bank line (`:1-17`) | `--db` (req), `--models`, `--device`, `--min-per-class`, `--out` | Named in `text-search.md:145`, **no command reference entry** |
| `scripts/tests/` | 7 files: `test_repair_audio_metadata`, `test_optimize_database_script`, `test_qa_database_script`, `test_run_server_lan_script`, `test_audio_dedup`, `test_clap_checkpoint_embed`, `test_benchmark_search` | `pytest scripts/tests` | Mentioned in `developer/*` |

`reference/commands.md:3-5` claims it covers "the public scripts located under `tools/` and `scripts/`". **Five of nine scripts are missing**, as are `spectral_check_cli.py` and `benchmark_fingerprint_candidates.py`.

---

## 6. Test suite map

### Python `tests/` — 81 files, 612 test functions

Standing contracts pinned, by cluster:

| Cluster | Files | What is pinned |
|---|---|---|
| HTTP payload contracts | `test_api_tracks` (12), `test_api_text_search` (16), `test_api_sonara_search` (10), `test_api_analysis_jobs` (19), `test_api_audio_dedup` (5), `test_api_reference_compare` (5), `test_api_database_selection` (12), `test_api_rhythm_lab` (14), `test_api_evaluation` (7), `test_api_dialog` (7), `test_api_server_shutdown` (4), `test_api_runtime` (9), `test_api_route_modules` (2), `test_api_database_validation` (1), `test_api_docs` (1) | Request/response shapes, range validation, `extra=forbid` rejection of unknown fields |
| Persisted schema/format | `test_sonara_storage` (19), `test_db_library_queries` (4), `test_db_repository_modules` (2), `test_embedding` (26), `test_legacy_single_library_migration` (3), `test_single_library_runtime` (10) | Table layout, identity binding, migration |
| Scoring/ranking invariants | `test_scoring_invariants` (5), `test_sonara_similarity` (24), `test_search` (11), `test_transition_diagnostics` (21), `test_tempo_resolution` (10), `test_track_resolution` (5), `test_contract_free_retrieval` (1) | Score behavior under weights, confidence, and missing evidence |
| Safety | `test_genre_tag_workflow` (4), `test_media_preview` (1), `test_tags` (22), `test_database_validation` (6) | Tag writes, preview transcode, validation |
| Analysis orchestration | `test_analysis_orchestration` (16), `test_analysis_pipeline` (8), `test_multi_model_analysis_jobs` (6), `test_analysis_sonara_preflight` (4), `test_sonara_staging` (10), `test_ml_staging` (5), `test_maest_windows` (6), `test_model_adapter_identity` (16) | Stage ordering, staging windows, model identity |
| Runtime/infra | `test_ffmpeg_runtime` (3), `test_audio_loader` (7), `test_logging_config` (18), `test_runtime` (3), `test_supported_audio_formats` (1) | FFmpeg discovery, decode chain, log filtering |
| Evaluation | 14 `test_evaluation_*` files (~92 tests) | Marked `evaluation`, another explorer's area |

**What the tests reveal that the docs do not state:**

1. **`tests/test_supported_audio_formats.py:4-16` pins `.aac`, `.ape`, `.wma`, `.wv` (WavPack) as supported and display-named.** This contradicts `first-library.md:55-56` and `ui-controls.md:68-69`, which list only 10 formats.
2. `tests/test_ml_staging.py` (5 tests) proves ML Staged Mode is a real, maintained backend feature — which three docs pages deny.
3. `tests/test_api_text_search.py:371` pins `/api/search/text/warmup` as *"loads the family without touching the library"*, and `:505` pins `/api/search/text/feedback` verdict store/update/withdraw. Neither endpoint is in `api.md`.
4. `tests/test_api_text_search.py:277,286,410,429` pin `extra=forbid` on the text-search and warmup contracts — a real client-breaking rule stated only in prose.
5. `tests/test_api_database_validation.py` and `tests/test_database_validation_jobs.py` (3 tests) pin a whole job family with no documentation.
6. `tests/test_clap_query_workflow_scripts.py` (5) pins the text-benchmark script family that `commands.md` omits.

### Frontend `frontend/tests/` — 31 files, ~130 tests

Run with `node --test tests/*.test.mjs` (`frontend/package.json:10`).

**`testsExecuteCode.test.mjs` is the meta-guard.** It enforces AGENTS.md's "never assert on the text of a source file" rule with three tests (`:50`, `:65`, `:80`): every new test must load its module through `ssrLoadModule`, `transpileModule`+`vm`, or a direct `../src/` import (`:32-37`); a 12-entry `SOURCE_TEXT_ONLY_LEGACY` list (`:17-30`) is allowed to shrink but never grow, must stay sorted and duplicate-free, must not name a missing file, and must not retain a file that has since been converted.

Notable pinned contracts:
- `libraryLoading.test.mjs:54` — "library uses one fixed 200-track page per API request"
- `searchPlaylistLayout.test.mjs:87` — "five maintained workflows with roving ARIA relationships"; `:119` — **"PROMPT tab"**; `:39` — "20-track pagination"
- `textPromptPresets.test.mjs` (14 tests) — every preset has a declared axis + unique key (`:44`), every bank holds exactly four prompts (`:195`), lines fit the CLAP token ceiling and avoid negation (`:213`), presets with measured-harmful negatives carry none (`:242`), an axis names a model only where the measurement supports it (`:74`)
- `audioDedupSelection.test.mjs:39` — "a delete batch **carries** the confirmation phrase" (confirming the client supplies it); `:63` — a selection emptying a group is refused
- `sonaraBpmRange.test.mjs` (8 tests) — Rekordbox default, octave rule, preset validity, storage round-trip, staging folder never restored
- `mlAnalysisSettings.test.mjs` (2) — ML staging settings are independent and the folder is not restored

---

## 7. Docs build and style infrastructure

### Commands (`docs/dj-track-similarity/package.json`)

| Script | Command | Effect |
|---|---|---|
| `dev` | `vitepress dev . --host 127.0.0.1` | live docs |
| `vale:sync` | `node scripts/run-vale.mjs sync` | downloads the `ai-tells` package |
| `lint:style` | `node scripts/run-vale.mjs report` | Vale with `--no-exit` (non-failing report) |
| `lint:style:strict` | `node scripts/run-vale.mjs strict` | Vale, exits nonzero on any alert |
| `check` | `lint:style:strict && build` | the gate |
| `build` | `vitepress build .` | writes `site/` |
| `preview` | `vitepress preview . --host 127.0.0.1` | serves `site/` |

### `scripts/run-vale.mjs`

Resolves Vale from `$VALE_EXE` → `vale` on PATH → `C:\Utils\tools\vale\vale.exe` (`:14-18`); throws a clear install message otherwise (`:31-33`). Base args `--config <repo>/.vale.ini --no-global --no-wrap` (`:11`). Lints `README.md` plus every `.md` under the docs root, skipping `node_modules`, `site`, `.vitepress` (`:10`, `:72`). Runs with `cwd = repoRoot` and forwards Vale's exit code (`:60-64`).

### `.vale.ini`

```
StylesPath = .vale/styles
MinAlertLevel = suggestion
Packages = https://github.com/tbhb/vale-ai-tells/releases/download/v1.19.0/ai-tells.zip
Vocab = DJTrackSimilarity
[*.md]
BasedOnStyles = ai-tells
BlockIgnores = (?m)^(> (Audience|Goal|Type): .+)$
[docs/dj-track-similarity/ru/**/*.md]
BasedOnStyles =
```

**`docs/dj-track-similarity/ru/` does not exist** — dead configuration for a Russian localization that was never created (ironic given the UI language).

### THE FULL VALE RULE SET — `ai-tells` v1.19.0, 61 rules

Every rule is `level: error` except `AIAdjectiveNounPairs` (`warning`). Because `check` runs `strict`, **any single hit fails the docs build.**

| Rule | Kind | Message the writer will see |
|---|---|---|
| `AbsoluteAssertions` | existence, ignorecase | AI overreach. Verify this claim or soften it. |
| `AIAdjectiveNounPairs` | sequence, **warning** | AI adjective-noun pair. Use concrete description instead. |
| `AICompoundPhrases` | existence, ignorecase | AI fingerprint. Rewrite with concrete specifics instead of this clichéd phrase. |
| `AffirmativeFormulas` | existence | AI affirmation. Cut the flourish and state the point plainly. |
| `AnnouncementHeadings` | existence, ignorecase, **scope: heading** | AI announcement heading. Cut the heading or rename it to the topic. |
| `AnthropomorphicJustification` | existence, ignorecase | AI cliché. Say what you mean directly. |
| `ClosingPleasantries` | existence, ignorecase | AI closing. Delete it and end with your actual content. |
| `ColloquialAssessments` | existence, nonword, ignorecase | AI colloquial assessment. State the assessment directly. |
| `ColonUsage` | existence, nonword, scoped | AI punctuation. Lowercase the word after the colon unless it is a proper noun. |
| `ConclusionMarkers` | existence, ignorecase | AI conclusion. Delete this and end on your final point. |
| `ContrastiveFormulas` | existence | AI contrast. State the positive claim directly without the "not X, but Y" formula. |
| `ContrastiveNegation` | existence, nonword, ignorecase | AI contrast by negation. State the positive directly without the trailing negation. |
| `DefensiveHedges` | existence, nonword | AI defensive hedge. State your point directly without pre-defending it. |
| `DespiteChallenges` | existence, ignorecase | AI despite-formula. Engage with the challenges substantively or remove the hedge. |
| `EmDashUsage` | existence, nonword | **AI punctuation: em-dash detected. Use a comma, period, or parentheses instead.** |
| `EmphaticCopula` | existence, nonword, scope: raw | AI emphasis. Remove the italics. Emphasizing a copula rarely adds meaning. |
| `EmptyPadding` | sequence, ignorecase | AI empty modifier (2-word). Delete the modifier and keep the noun. |
| `EmptyPaddingStacked` | sequence, ignorecase | AI empty modifier (3-word). Delete the modifier and keep the noun. |
| `ExplainerHeadings` | existence, ignorecase, **scope: heading** | AI explainer heading. Name what you're explaining instead. |
| `FalseBalance` | existence, ignorecase | AI evasion. Take a clear position or remove the hedge. |
| `FalseExclusivity` | existence, ignorecase | AI false exclusivity. State the point directly without claiming insider knowledge. |
| `FigurativeLands` | existence, nonword, ignorecase | AI overused verb. Name the literal action: is merged or is routed to. |
| `FillerPhrases` | existence, ignorecase | AI filler. Delete this phrase. It adds no meaning. |
| `FormalRegister` | existence | AI formalism. Use a plainer everyday word (e.g. "use", "help", "start"). |
| `FormalTransitions` | existence, ignorecase | AI transition. Delete it, or use a simpler connector like "and", "but", or "so". |
| `GrowthMetaphors` | existence, nonword, ignorecase | AI growth metaphor. Say what literally happens. |
| `HedgingPhrases` | existence, ignorecase | AI hedge. Delete this throat-clearing and state your point directly. |
| `ListIntroductions` | existence, ignorecase | AI list intro. Skip the announcement and present the content directly. |
| `MarketingHeadings` | existence, ignorecase, **scope: heading** | AI marketing heading. Strip the puffery and name the topic plainly. |
| `Metacommentary` | existence, nonword, scope: raw | AI metacommentary. Delete it or replace it with substantive content. |
| `MicDrop` | existence, nonword | AI mic-drop. Integrate the point into the surrounding text or cut it. |
| `MicDropHeadings` | existence, nonword, **scope: heading** | AI mic-drop heading. Use a descriptive heading instead. |
| `NarrativePivots` | existence, ignorecase | AI narrative pivot. State your point directly. |
| `OpeningCliches` | existence, ignorecase | AI opening. Start with your actual point instead of this generic lead-in. |
| `OrganicConsequence` | existence | AI inevitability. Say the choice was designed that way. |
| `OverusedVocabulary` | existence | AI vocabulary. Replace with a more specific or common word. |
| `OverusedVocabularyVerbs` | sequence | AI vocabulary (verb form). Replace with a direct verb. |
| `ParallelStaccato` | existence, nonword | AI staccato. Combine these clipped parallel sentences or vary the structure. |
| `ParticipialPadding` | existence, ignorecase | AI participial padding. Delete it or make the point concrete. |
| `PromotionalPuffery` | existence, ignorecase | AI puffery. Use neutral, specific language. |
| `RedundantPrecaution` | existence, ignorecase | AI cliché. Name the specific safeguard or cut the phrase. |
| `ResonateOveruse` | existence, nonword, ignorecase | AI overused verb. Name what connects and why. |
| `RestatementMarkers` | existence, ignorecase | AI restatement. Delete it and trust your original phrasing. |
| `RhetoricalDevices` | existence, nonword | AI rhetoric. Remove it or rephrase as a plain statement. |
| `RhetoricalSelfAnswer` | existence, nonword, scope: raw | AI rhetorical self-answer. State the point directly instead of posing and answering your own question. |
| `SelfReference` | existence, ignorecase | AI cross-reference. Rewrite the passage to work without the cross-reference. |
| `SemicolonUsage` | existence, nonword | **AI punctuation. Replace the semicolon with a period or two sentences.** |
| `SequencingMarkers` | existence | AI sequencing. Use natural transitions or write an actual list. |
| `ServesAsDodge` | existence, ignorecase | AI copula dodge. Use "is" or "are" instead of this inflated construction. |
| `ShipOveruse` | existence, nonword, ignorecase | AI overused word. Name the specific action or object. |
| `StackedAnaphora` | existence, nonword | AI anaphora. Vary the sentence openings or combine into a single statement. |
| `StrategyBuzzwords` | existence, nonword, ignorecase | AI strategy buzzword. Describe the actual mechanism or advantage plainly. |
| `StructureAnnouncements` | existence, ignorecase | AI structure announcement. Present the content instead of narrating that you're about to. |
| `SycophancyMarkers` | existence, ignorecase | AI sycophancy. Delete this. It sounds robotic and insincere. |
| `UnpackExplore` | existence, ignorecase | AI explainer prompt. Explain it directly instead of announcing it. |
| `UrgencyInflation` | existence, ignorecase | AI urgency. Delete it or show the stakes concretely. |
| `VagueAttributions` | existence, ignorecase | AI vague attribution. Name the specific source or delete the claim. |
| `VerbTricolon` | existence, nonword | AI tricolon. Three parallel verbs in series. Restructure or vary the count. |
| `VerbTricolonDensity` | occurrence, **scope: paragraph** | AI tricolon: multiple verb tricolons in one paragraph. Rewrite some with two or four items. |
| `WrapUpHeadings` | existence, ignorecase, **scope: heading** | AI wrap-up heading. Delete the section or rename the heading to the topic. |

**Practical rules for the writer:** no em dashes, no semicolons, no "not X but Y", no three-verb series, sentence-case after a colon, no "Let's explore/unpack", no "Conclusion"/"In summary"/"Wrapping up" headings, no "What is X?" explainer headings, no marketing headings, no closing pleasantries, no hedging or throat-clearing, no cross-references phrased as "as mentioned above", no vague attributions, and no "serves as / functions as" in place of "is".

**Vocabulary** (`.vale/styles/config/vocabularies/DJTrackSimilarity/accept.txt`, 59 entries): `dj-track-similarity, DJ, VitePress, FastAPI, PowerShell, Typer, Uvicorn, Diataxis, AGENTS, SONARA, MAEST, MERT, CLAP, Rhythm Lab, Audio Doctor, Audio Dedup, SQLite, Mutagen, FFmpeg, TorchCodec, Torchaudio, PyTorch, nnaudio, laion-clap, maest-infer, hnswlib, HNSW, Vorbis, WAL, CUDA, cuda, pytest, venv, frontend, metadata, multiclass, classifier, classifiers, embeddings, rescoring, retag, shortlist, syncopated, transcoded, BPM, Camelot, M3U, CSV, WAV, AIFF, FLAC, MP3, M4A, ALAC, ID3, TCON, GENRE`. `reject.txt` is **empty**. **`MuQ`, `MuQ-MuLan`, `MuLan`, `PROMPT`, `Audio Online`, `PyAV`, `Vite`, `React` are missing** — the vocabulary is stale.

### Theme

`.vitepress/theme/index.ts` extends `DefaultTheme` with JetBrains Mono Variable (regular + italic) and `custom.css`. `public/` holds `favicon.svg`, `logo-light.svg`, `logo-dark.svg`. Config: `base: "/docs/"`, `outDir: "site"`, `cleanUrls: false`, `appearance: true`, `lastUpdated: true`, local search, outline levels 2-3.

### How the app serves docs

`src/dj_track_similarity/api_routes_docs.py:10-13` mounts `docs/dj-track-similarity/site` at `/docs` via `StaticFiles(html=True)` when it exists. When absent, it registers `GET /docs` and `GET /docs/{path:path}` returning a **503** HTML page reading "Documentation is not built. Run `npm run build` from `docs/dj-track-similarity`" (`:16-37`). Pinned by `tests/test_api_docs.py`. The UI links to `/docs/` from the title (`App.tsx:1584`).

---

## 8. COMPLETE PAGE-BY-PAGE DRIFT TABLE

All 51 pages. (The IA promises 52 counting `persistent-ann-indexes.md`, which README links to but which does not exist.)

| page | lines | verdict | specific defects with the contradicting code fact | action |
|---|---|---|---|---|
| `index.md` | 103 | **WRONG** | (a) `:79` "Audio Doctor apply repairs files only after dry-run state exists and **exact confirmation is typed**" — no confirmation exists in `tools/audio-doctor/audio_doctor/core.py`. (b) `:80` "Audio Dedup deletes … only after exact confirmation is typed, **whether the run comes from the CLI or the browser**" — the browser client sends the phrase itself (`audioDedupView.ts:17,389`); the user answers Да/Нет. (c) `:45` promises "Draft a musical route — turn a few anchors into an editable sequence with a chosen energy, diversity, and tempo direction" — no such generator exists; the set is manual (`useSearchPlaylist.ts`). (d) `:69` claims scan reads "catalog number, ISRC" — `FileTags` (`api.ts:73-86`) has neither (NOT VERIFIED against the scanner). | REWRITE |
| `project-guide.md` | 77 | OUTDATED | `:60` sends readers to `reference/cli.md`, a 6-line stub. Routing table omits the CLASS tab, LAB, Audio Online, and database validation. No mention that the UI is Russian. | UPDATE |
| `getting-started/index.md` | 38 | INCOMPLETE | `:33` "SONARA, MAEST, MERT, MuQ, or CLAP" omits **MuQ-MuLan**, a first-class family. `:16` "Current Set or crate building" is vague. | UPDATE |
| `getting-started/quickstart.md` | 139 | **WRONG** | (a) `:111` example prompt contains `"no vocals"` — directly violates `text-search.md:86-87` and `helpText.ts:37` ("Never write `no`, `not` or `without`"). (b) `:119` "In **Database and analysis**, confirm the SQLite path **and music root**" — the panel is `1. База и анализ` and has **no music-root field**; the root lives in `ScanImportDialog`. (c) `:123` "Open **MERT**, **MUQ**, or **MULAN**" — these are not tabs; they are options in the SIMILARITY tab's Model select (`EmbeddingSearchTab.tsx:60-74`). (d) `:37` extension list is correct and contradicts `first-library.md:55`. | REWRITE |
| `getting-started/install.md` | 177 | ACCURATE | `:84` `sonara 0.3.5` matches `pyproject.toml:24`. Only gap: omits `--extra rhythm-lab` from the main example while listing it separately, and omits the `ann` extra name resolution. | KEEP |
| `getting-started/first-library.md` | 121 | **WRONG** | (a) `:55-56` "The dialog starts with all format badges selected: MP3, FLAC, ALAC, WAV, WAVE, AIFF, AIF, M4A, OGG, and OPUS" — **10 of 14**. `ScanImportDialog.tsx:30-45` also ships AAC, APE, WMA, WavPack, and `tests/test_supported_audio_formats.py` pins all four. The same page lists all 14 correctly at `:88`. (b) The whole **SONARA BPM range section of the dialog** (`ScanImportDialog.tsx:203-246`: presets, lock icon, octave rule, "reset SONARA to change") is missing. (c) `:95` claims scan reads "catalog number … ISRC"; `FileTags` has neither. | REWRITE |
| `getting-started/first-analysis.md` | 208 | **WRONG** | (a) `:119` "**CLASSIFIERS** stays a separate stage; **FULL** runs SONARA, ML, and CLASSIFIERS in order" — neither control exists (`LibraryPanel.tsx`, `analysisSelection.ts:5-8`). (b) `:173` "**Staged Mode applies only to SONARA.** MAEST, MERT, MuQ, MuQ-MuLan, and CLAP read the original source paths" — **false**: ML Direct/Staged with folder, Workers, StageSize exists (`LibraryPanel.tsx:232-250`, `mlAnalysisSettings.ts:17-24`, sent at `App.tsx:1224-1234`, tested in `tests/test_ml_staging.py`). (c) `:124` repeats the CLASSIFIERS claim. Everything else (BPM range, staging semantics, decode recovery, reset boundaries) is accurate and valuable. | UPDATE |
| `user-guide/index.md` | 33 | ACCURATE | Table row `:12` says "Open: CLAP or MuQ-MuLan" where the actual tab is PROMPT. Minor. | UPDATE |
| `user-guide/browse-library.md` | 105 | ACCURATE | Best page in the set. 200-page loading, prev/next/page-number, continuous playback, shuffle, add-visible, likes, identity dedup, preview transcode — all verified. Missing: the **database-validation button** and the fact that sort/shuffle are client-side over the loaded page (`libraryView.ts:29-45`), contradicting `ui-controls.md:20`. | UPDATE |
| `user-guide/analyze-library.md` | 95 | **WRONG** | `:12` and `:27` assert the CLASSIFIERS stage and the FULL button. No ML Staged Mode. No SONARA Direct/Staged UI detail (deferred to `first-analysis.md`, which makes this page thin for its own title). | REWRITE |
| `user-guide/search-with-seeds.md` | 118 | ACCURATE | Solid. Missing: the **"Add Random Track"** buttons in both SONARA and SIMILARITY (`SearchPlaylistPanel.tsx:471`, `EmbeddingSearchTab.tsx:48`) and their two endpoints; the score-breakdown tooltip (`TrackRows.tsx:307-335`). `:13` "MERT search" names a button that does not exist. | EXPAND |
| `user-guide/text-search.md` | 289 | INCOMPLETE | Content is excellent and reproducible. Defects: (a) `:15` "**TEXT** tab" — it is **PROMPT** (`SearchPlaylistPanel.tsx:97`, pinned by `frontend/tests/searchPlaylistLayout.test.mjs:119`). (b) `:91` "153 presets on 21 semantic spaces" — verified correct. (c) Never states that **selecting a preset can switch the model automatically** (`App.tsx:250-258`, `TextSearchTab.tsx:125-158`) or that a **"Переключить на …" button** appears. (d) No mention of the **automatic warmup on tab open** (`TextSearchTab.tsx:188-202`, `POST /api/search/text/warmup`) despite documenting the 40-second load. (e) `:141` names `text_preset_feedback`, a table absent from `reference/database.md`. | UPDATE |
| `user-guide/class-tab.md` | 81 | **WRONG** | `:69-76` "CLASSIFIERS analysis stage — the left panel includes a standalone **CLASSIFIERS** checkbox … **FULL** is the explicit way to combine all stages" — neither exists. The rest (manifest layout, blockers, rescore = reset + analyze at `App.tsx:941-942`, filtering) is accurate. Missing: the manifest fact chips (Status/Type/Models/Features/Labels/Calibrated/Validation/Promoted, `SearchPlaylistPanel.tsx:795-830`) and the `available N · blocked N` line. | UPDATE |
| `user-guide/export-playlists.md` | 58 | ACCURATE | 20-per-page verified (`SearchPlaylistPanel.tsx:29`), collapsed disclosure verified (`:713-726`). Missing: the Rhythm Lab collection name is collected with a **`window.prompt`** (`App.tsx:1480`) and defaults to `Collection <YYYY-MM-DD>`; `exportDirectoryError` blocks a blank path (`exportView.ts:1`). | EXPAND |
| `user-guide/tags-and-audio-writes.md` | 53 | **WRONG** | `:44` "Apply mode requires exact `APPLY REPAIR`" — the phrase exists in no source file. This is the page whose entire job is naming the exact write paths, so the error is maximally damaging. `:48` Audio Dedup line is CLI-accurate but omits the browser trash/permanent path. | REWRITE |
| `workflows/index.md` | 29 | INCOMPLETE | The outcome table (`:8-13`) omits the Reanalyze-SONARA workflow that the Pages list and sidebar both carry. | UPDATE |
| `workflows/find-compatible-tracks.md` | 33 | OUTDATED | `:13` "Run **MERT search**" — no such button; MERT is the default option in SIMILARITY (`App.tsx:189`). `:25` "Below `0.45` confidence" matches `FINGERPRINT_REVIEW_MIN_SIMILARITY`-adjacent prose elsewhere; NOT VERIFIED against the tempo resolver. | UPDATE |
| `workflows/build-crates.md` | 29 | ACCURATE | Thin but correct. | KEEP |
| `workflows/train-personal-classifier.md` | 211 | INCOMPLETE | `:193` uses `POST /api/classifiers/reset` with `{"classifier_keys":["…"]}` (plural array); the client sends `{"classifier_key": "…"}` (singular, `apiClient.ts:305-309`) and `reference/api.md:179` documents the singular form. **Two docs pages disagree with each other.** | UPDATE |
| `workflows/reanalyze-sonara-split-storage.md` | 62 | ACCURATE | Consistent with the fingerprint/embedding/Core three-output rule. | KEEP |
| `workflows/maintain-library.md` | 23 | OUTDATED | `:21` "The browser supports scan, Refresh Tags, **relocation preview**, and report-first helper jobs" — there is **no relocation endpoint in `apiClient.ts`**; relocation is CLI-only (`dj-sim relocate-library`). The browser's actual maintenance surfaces are Refresh Tags, **Validate database**, Audio Dedup, and Clear. | UPDATE |
| `concepts/index.md` | 25 | ACCURATE | `:18` omits MuQ-MuLan from the "Features, embeddings, tags" summary line. | KEEP |
| `concepts/project-idea.md` | 63 | ACCURATE | Faithful to README's framing. | KEEP |
| `concepts/local-first-safety.md` | 66 | **WRONG** | (a) `:44` "**Audio Doctor apply** repairs files from a prior dry-run state after exact `APPLY REPAIR` confirmation" — no such gate. (b) `:48` "both leave source audio untouched **until the phrase is typed**" — in the browser nobody types it. This is the canonical safety page; both errors overstate protection. | REWRITE |
| `concepts/features-embeddings-tags.md` | 112 | OUTDATED | `:79` "The **MERT tab**" and `:91` "Use the **MULAN tab**" — neither exists; both are Model options in SIMILARITY. `:91-92` "In the **TEXT** tab" — it is PROMPT. `:26` repeats the "catalog number … ISRC" claim absent from `FileTags`. | UPDATE |
| `concepts/similarity-scores.md` | 52 | ACCURATE | `:43` "`0.45` … creates manual-review candidates" matches `FINGERPRINT_REVIEW_MIN_SIMILARITY = 0.45` (`audio_dedup/core.py:47`). `:41` correctly limits dedup sources to MERT/MAEST/MuQ/CLAP, matching `SUPPORTED_EMBEDDINGS` (`:44`). | KEEP |
| `concepts/classifiers-and-rhythm-lab.md` | 94 | ACCURATE | Matches the CLI and the immutable-generation layout. | KEEP |
| `tools-and-scripts/index.md` | 24 | INCOMPLETE | Titled "Tools **and scripts**" but lists zero scripts. Omits **Audio Online** entirely. Omits `qa_database.py`, `benchmark_search.py`, and the five text-layer scripts. Omits `.dj-track-similarity-indexes/` context (the ANN page it implies does not exist). | EXPAND |
| `tools-and-scripts/rhythm-lab.md` | 110 | ACCURATE | Matches `rhythm_lab/cli.py` and the label-transfer flow. Omits `suggest-labels`/queue commands and `delete-profile` (delegated to `commands.md`, acceptable). Does not warn about the `C:\db\abstracted.sqlite` default (`cli.py:35`). | KEEP |
| `tools-and-scripts/audio-dedup.md` | 449 | INCOMPLETE | Deepest page in the set and mostly exact. Two defects: (a) `:167-169` "Deletion needs a **Recycle bin** or **Permanent** choice **and the exact phrase `APPLY DELETE`**. The delete button stays disabled until both are set" — false; `canDelete = summary.files > 0 && !dedup.busy` (`AudioDedupDialog.tsx:70`) and no phrase field exists. (b) `:388-392` "both require the exact phrase" — the API requires it in the body; the browser client supplies it (`audioDedupView.ts:17`). Also `:158` names a button "**Use the suggestion**"; the real per-group control is Russian (`AudioDedupReview.tsx:157-164`). | UPDATE |
| `tools-and-scripts/audio-doctor.md` | 44 | **WRONG / THIN** | (a) `:31-35` states `APPLY REPAIR` as the apply gate — the phrase exists nowhere in code. (b) Documents 5 of 22 CLI flags. (c) `:37` "The app also requires prior dry-run state" implies an app integration; **Audio Doctor has no API route at all** (zero matches for `audio_doctor` under `src/`). (d) Never mentions the `--reason`-scoped apply workflow, `--workers`, `--keep-id3`, or the report bundle contents. | REWRITE |
| `tools-and-scripts/optimize-database.md` | 19 | THIN | Accurate but omits the exact printed fields (`database_kind`, `integrity_before/after`, `size_before/after`, per-role backup paths — `optimize_database.py:192-200`) and the actual maintenance statements. | EXPAND |
| `reference/index.md` | 20 | ACCURATE | `:19` states the correct precedence rule (source wins). | KEEP |
| `reference/commands.md` | 478 | INCOMPLETE | (a) `:307` is a **broken table row**: `|| \`--keep-db PATH\` |` (doubled leading pipe). (b) `:318` publishes the private default `C:\db\abstracted.sqlite`, which `release-checklist.md:7` forbids. (c) Claims to cover all public scripts (`:3-5`) but omits `clap_checkpoint_embed.py`, `text_prompt_benchmark.py`, `text_fusion_benchmark.py`, `text_tag_crosscheck.py`, `prompt_preset_tune.py`, `spectral_check_cli.py`, `benchmark_fingerprint_candidates.py`. Otherwise verified accurate against `audio_dedup/core.py:370-443`, `audio_doctor/core.py:1125-1239`, `rhythm_lab/cli.py`, `metadata_enrichment_cli.py`. | UPDATE |
| `reference/cli.md` | 6 | **SHOULD-BE-DELETED** | A 6-line redirect to `commands.md`. It occupies a sidebar slot, is linked from `project-guide.md:60` and README, and adds one hop. Either fold it into `commands.md` (retitle that page "CLI reference") or delete it and repoint the links. | DELETE |
| `reference/api.md` | 246 | INCOMPLETE | Omits **12 endpoints the shipped client calls**: `/api/tracks/{id}/reveal`, the three `/api/library/scan/jobs/*`, the three `/api/database/validation/jobs/*`, the three `/api/classifiers/{k}/analyze/jobs/*`, `/api/search/sonara/random-track`, `/api/search/random-track`, `/api/search/text/warmup`, `/api/search/text/feedback`. Lists `POST /api/database/switch` (`:14`), which no client calls (NOT VERIFIED server-side). Otherwise the text-search contract table (`:196-204`), dedup delete semantics, and warm-up phase description are exact. | EXPAND |
| `reference/database.md` | 99 | INCOMPLETE | Table list omits **`text_preset_feedback`**, which `user-guide/text-search.md:141` says holds one verdict per (track, preset, model) and which `POST /api/search/text/feedback` writes. Otherwise accurate. | UPDATE |
| `reference/configuration.md` | 135 | INCOMPLETE | Documents exactly one environment variable. Missing: the five launcher vars `DJ_TRACK_SIMILARITY_LAUNCHER_{HOST,PORT,DATABASE,FRONTEND_DEV,FRONTEND_HOST}` (`run_server_launcher.py:23-27`), the Audio Online vars `METADATA_ENRICHMENT_NODE`/`METADATA_ENRICHMENT_NODE_MODULES`, the Vale var `VALE_EXE` (`run-vale.mjs:15`), and the three browser `localStorage` keys `dj-track-similarity.sonara-analysis-settings` (`sonaraAnalysisSettings.ts:20`), `dj-track-similarity.ml-analysis-settings` (`mlAnalysisSettings.ts:15`), `dj-track-similarity-theme` (`theme.ts:3`) — the last being real user-visible configuration with a documented "staging folder is never persisted" rule. | EXPAND |
| `reference/analysis-families.md` | 243 | INCOMPLETE | (a) Internal contradiction: the SONARA row at `:37` says it writes "Core feature rows **and a dedicated 48D embedding**", omitting the fingerprint that `:110-122` and `:211-213` say is always written. (b) Second internal contradiction: `:97` says a SONARA native decode failure "falls back to a direct **TorchCodec** shared-library decode", while `:31-33` and `reference/sonara-integration.md:22-28` say it falls back to **PyAV**. (c) `:137-138` "Staged Mode does not apply to the GPU model families" — false (ML Staged Mode exists). Everything else, including the warm-up log-entry table, is high quality. | UPDATE |
| `reference/sonara-integration.md` | 107 | OUTDATED | (a) `:7` "The current project uses SONARA in `playlist` mode **with a `70..180` BPM range**" — contradicts `:55-59` on the same page, which correctly says the range is a per-library choice locked by the first analysis. Stale opening sentence. (b) `:50` "For SONARA **0.3.6** Core results" while `pyproject.toml:24` pins `sonara==0.3.5` and `model-citations.md:11,18` says `0.3.5`. README:167 repeats the 0.3.6 claim. | UPDATE |
| `reference/model-citations.md` | 32 | ACCURATE | Verified against `pyproject.toml:24` and `scripts/clap_checkpoint_embed.py` (checkpoint `music_audioset_epoch_15_esc_90.14.pt`). Best-maintained reference page. | KEEP |
| `reference/ui-controls.md` | 163 | **WRONG** | (a) `:47-49` "**SONARA**, **ML**, and **CLASSIFIERS** distinct. **FULL** runs the ordered pipeline" — no CLASSIFIERS checkbox, no FULL button. (b) `:48` SONARA "Core plus its dedicated embedding" omits the fingerprint. (c) `:63` "These controls affect **SONARA only**, so GPU model analysis does not use the staging folder" — false; ML has its own mode, folder, Workers `1..16` and StageSize `1..512` defaulting to 4/64 (`mlAnalysisSettings.ts:17-24`). (d) `:68-69` format defaults list 10 of 14. (e) `:113` "The footer … takes the exact confirmation phrase `APPLY DELETE`. The delete button stays disabled until copies are marked **and the phrase matches**" — no phrase field; the footer is summary + Куда select + delete button (`AudioDedupDialog.tsx:436-468`). (f) `:125` names the tab **TEXT**; it renders **PROMPT**. (g) `:20` calls sort a "server-backed filter"; sort and shuffle are client-side (`libraryView.ts:29-45`). (h) Omits the theme toggle, log button, stop button, database-validation button, Add-Random-Track buttons, preset picker, and result feedback buttons. Verified correct: 200-page rule, `25`-group dedup page, `1200 ms` poll, dedup button placement. | REWRITE |
| `developer/index.md` | 15 | ACCURATE | — | KEEP |
| `developer/architecture.md` | 71 | INCOMPLETE | `:13` shows staging only feeding SONARA and `:49` names only `sonara_staging.py`; `tests/test_ml_staging.py` proves an ML staging path exists. `:55-56` "SONARA Core and embedding data use one transaction with a savepoint per track" omits the fingerprint. `:63` describes `frontend/src/` in one line for a 44-file, 5-panel UI. | UPDATE |
| `developer/development.md` | 56 | INCOMPLETE | `:44-45` tells the reader to run `tools/rhythm-lab/tests` and `scripts/tests` explicitly, omitting `tools/audio-dedup/tests` (4 files) and `tools/audio-online/tests` (11 files). No mention of `frontend/tests/testsExecuteCode.test.mjs`, which is a hard rule for anyone touching the frontend. | UPDATE |
| `developer/testing-and-verification.md` | 50 | **WRONG** | `:30` points at **`tests\test_api_audio_doctor.py`, which does not exist** (verified against the full `tests/*.py` glob — there is no Audio Doctor API surface at all). `:19` omits `tools/audio-online/tests`. Never states the no-source-text rule enforced by `frontend/tests/testsExecuteCode.test.mjs`, nor names `frontend/tests/` at all beyond `npm test`. | UPDATE |
| `developer/release-checklist.md` | 20 | INCOMPLETE | `:7` "No examples expose private paths" is violated by `commands.md:318` (`C:\db\abstracted.sqlite`) and by `helpText.ts:5` (`M:` drive) and `audio-dedup.md:302` (`M:/Volumes`). `:15` "Sidebar entries and local links include every new documentation page" is violated by the missing `persistent-ann-indexes.md` and the absent Audio Online page. The checklist is correct; it just is not being run. | KEEP |
| `help/index.md` | 19 | ACCURATE | — | KEEP |
| `help/troubleshooting.md` | 84 | ACCURATE | Good symptom coverage. Missing symptoms: "the UI is in Russian and the docs are in English", "the PROMPT tab search button is greyed out" (needs stored embeddings, `SearchPlaylistPanel.tsx:280`), "the ML checkboxes are greyed out" (needs ≥1 SONARA row, `LibraryPanel.tsx:164`), "Staged Mode will not start" (needs a folder, `App.tsx:1166-1175`), "I cannot change the BPM range" (locked after first SONARA, `App.tsx:332-336`). | EXPAND |
| `help/faq.md` | 54 | OUTDATED | (a) `:13-14` "both need the exact phrase `APPLY DELETE`" — the browser user never types it. (b) `:12` implies Audio Doctor apply is confirmation-gated; it is not. (c) `:48` "library paging **and chunked loads**" — chunked loading no longer exists; one page of 200 per request (`useLibraryState.ts:212-221`), and `browse-library.md:24` explicitly says "There is no second row-window paginator". | UPDATE |
| `help/known-limits.md` | 33 | INCOMPLETE | Omits the biggest current limits: **the UI is Russian while the docs are English**; there is no automatic set generation despite `index.md:45` implying one; the local API is unauthenticated on LAN; Audio Doctor has no in-app surface; Audio Online is undocumented; the ANN indexes page README links to does not exist. | EXPAND |

---

## 9. STRUCTURAL FINDINGS

**Broken links**
1. `README.md:462` → `docs/dj-track-similarity/tools-and-scripts/persistent-ann-indexes.md` — **the file does not exist**. This is the only broken cross-document link in the project; every one of the ~115 internal doc-to-doc links resolves (verified by enumerating all relative `.md` links against the page inventory).
2. `developer/testing-and-verification.md:30` → `tests\test_api_audio_doctor.py` — file does not exist.
3. `.vale.ini:13` scopes a section to `docs/dj-track-similarity/ru/**/*.md` — that directory does not exist.

**Orphan pages:** none. All 51 pages appear in `englishSidebar` (`config.mts:13-23`), and every sidebar link resolves to a real page.

**Pages the IA promises but does not have**
- `tools-and-scripts/persistent-ann-indexes.md` (README links to it; `configuration.md:41` and `local-first-safety.md:14` reference ANN sidecars with nowhere to send the reader).
- `tools-and-scripts/audio-online.md` — a whole tool with 16 modules, 11 test files, and four external API integrations.
- No page owns `scripts/` despite the section being titled "Tools **and scripts**".

**Duplicated content across pages**
- The **SONARA Direct/Staged mode table** appears three times: `first-analysis.md:126-185`, `reference/ui-controls.md:37-63`, `reference/sonara-integration.md:14-42`. The three copies already disagree about ML staging.
- The **fixed SONARA three-output rule** is restated in `analyze-library.md:55-66`, `first-analysis.md:187-207`, `reanalyze-sonara-split-storage.md:45-49`, `features-embeddings-tags.md:47-56`, `analysis-families.md:113-122`, `sonara-integration.md:44-59`, and `troubleshooting.md:46-53` — seven near-identical passages.
- The **audio-write path list** appears in `index.md:76-82`, `local-first-safety.md:39-48`, `tags-and-audio-writes.md:24-52`, and `faq.md:10-15`. All four carry the false `APPLY REPAIR` claim, so a single fix must touch four pages.
- The **scan-batching paragraph** is byte-similar in `first-library.md:61-74` and `ui-controls.md:74-87`.

**Nav vs sidebar asymmetry:** `englishNav` (`config.mts:5-11`) exposes only Home, Guide, Getting Started, User Guide, Reference. Workflows, Concepts, Tools and scripts, Developer, and Help are sidebar-only.

**IA changes I recommend**
1. **Delete `reference/cli.md`** and retitle `reference/commands.md` to "CLI reference"; repoint `project-guide.md:60`, `reference/index.md:8`, README, and the sidebar.
2. **Add `tools-and-scripts/audio-online.md`** and a sidebar entry.
3. **Add `tools-and-scripts/persistent-ann-indexes.md`** or remove the README link and the two dangling ANN references.
4. **Add `tools-and-scripts/scripts.md`** (or split into `qa-database.md` + `benchmarks-and-text-tools.md`) so `scripts/` has an owner.
5. **Collapse the SONARA three-output rule into `reference/analysis-families.md`** and make the other six passages link to it.
6. **Make `reference/ui-controls.md` the single owner of every control**, and have `browse-library.md` / `analyze-library.md` / `class-tab.md` link into it instead of restating defaults.
7. **Add a "Language" note to `help/known-limits.md` and `getting-started/quickstart.md`** stating that the shipped UI is Russian, with a label glossary mapping the Russian strings to the English names the docs use. Without this, every UI-referencing page is unusable as written.
8. Add `Workflows`, `Tools`, and `Help` to `englishNav`.

---

## 10. UNDOCUMENTED SURFACE, ranked by user need

| # | Surface | Where it lives | Why a user needs it | Current coverage |
|---|---|---|---|---|
| 1 | **The UI is entirely in Russian** | every `.tsx`, all of `helpText.ts` | Every English control name in all 51 pages is unfindable on screen | **none** |
| 2 | **ML Direct/Staged Mode** (folder, Workers `1..16` def 4, StageSize `1..512` def 64) | `LibraryPanel.tsx:232-250`, `mlAnalysisSettings.ts:17-24`, `App.tsx:1224-1234`, `tests/test_ml_staging.py` | Required for ML analysis on slow disks; three pages actively deny it exists | **contradicted** |
| 3 | **Database validation job** ("Проверить базу", ShieldCheck) | `LibraryPanel.tsx:190`, `apiClient.ts:257-259`, `tests/test_api_database_validation.py` | A primary maintenance action in the main panel | **zero mentions anywhere** |
| 4 | **`tools/audio-online`** (Discogs, MusicBrainz, Last.fm, Beatport OAuth, MAEST → XLSX) | 16 modules, 11 tests, own README | An entire tool with credential handling and external API calls | one `<details>` in `commands.md` |
| 5 | **PROMPT-tab preset picker** (21 axes, 153 presets, model auto-switch, measured ROC-AUC chips, bank preview) | `TextSearchTab.tsx:218-468`, `textPromptPresets.ts` | The main way to build a working prompt bank | axes/presets described in `text-search.md`; the **auto-switch and the "Переключить на …" button are undocumented** |
| 6 | **Text-search warmup** (`POST /api/search/text/warmup`, fired on tab open and model change) | `TextSearchTab.tsx:188-202`, `apiClient.ts:351` | Explains the visible "загружается" banner and why the first search is fast | **not in `api.md`** |
| 7 | **Result feedback buttons** (thumbs up/down → `POST /api/search/text/feedback`) | `TrackRows.tsx:243-266`, `App.tsx:1365-1387` | Feeds `prompt_preset_tune.py`; behavior page exists but the endpoint and table are unreferenced | partial |
| 8 | **"Add Random Track"** in SONARA and SIMILARITY (`/api/search/sonara/random-track`, `/api/search/random-track`) | `SearchPlaylistPanel.tsx:471`, `EmbeddingSearchTab.tsx:48` | The fastest way to start exploring with no seed in mind | **none** |
| 9 | **Reveal-in-folder** (`POST /api/tracks/{id}/reveal`) | `TrackMetadataDialog.tsx:209-216`, `apiClient.ts:225` | Bridges the library to the filesystem | **none** |
| 10 | **Top-bar theme toggle, log button, stop button** | `App.tsx:1590-1640` | Three of six always-visible global controls | **none** |
| 11 | **`clap_checkpoint_embed.py`, `text_prompt_benchmark.py`, `text_fusion_benchmark.py`, `text_tag_crosscheck.py`, `prompt_preset_tune.py`** | `scripts/` | AGENTS.md requires a committed `text_prompt_benchmark.py` table for any reliability claim, yet the script has no command reference | named in prose only |
| 12 | **`scripts/qa_database.py`, `spectral_check_cli.py`, `benchmark_fingerprint_candidates.py`** | `scripts/`, `tools/audio-dedup/` | Read-only diagnostics a maintainer would want | `commands.md` covers only `qa_database.py` |
| 13 | **Launcher env vars** (`DJ_TRACK_SIMILARITY_LAUNCHER_HOST/PORT/DATABASE/FRONTEND_DEV/FRONTEND_HOST`) | `run_server_launcher.py:23-27` | Non-interactive launcher configuration | **none** |
| 14 | **Browser `localStorage` keys and the "staging folder is never persisted" rule** | `sonaraAnalysisSettings.ts:20,42-44`, `mlAnalysisSettings.ts:15,26-28`, `theme.ts:3` | Explains why the staging folder must be re-picked every session | partially in `first-analysis.md:140` for SONARA only |
| 15 | **`text_preset_feedback` table** | `text-search.md:141` names it; `reference/database.md` does not list it | Schema reference completeness | **missing from the DB reference** |
| 16 | **Scan formats AAC, APE, WMA, WavPack** | `ScanImportDialog.tsx:30-45`, `tests/test_supported_audio_formats.py` | Users with those files are told they are unsupported | **two pages list 10 of 14** |
| 17 | **`frontend/tests/testsExecuteCode.test.mjs` rule** | that file | A hard contributor rule that fails CI | **not in any developer page** |

**Code-quality observations for the curator (not documentation defects, but worth routing):**
- `jobUi.tsx:5` — `AUDIO_MODELS` omits `"mulan"`, so MuQ-MuLan per-model progress rows fall into the classifier-rows branch (`:327-332`) and render after the audio rows. A real ordering bug.
- `rhythm_lab/cli.py:35` — hard-coded `C:\db\abstracted.sqlite` as a shipped CLI default.
- `tools/audio-doctor/data/state/` and `data/reports/` contain ~63 committed JSON artifacts naming `library.sqlite`, contradicting `tools-and-scripts/index.md:16` ("ignored by Git by default") and AGENTS.md's "never stage local reports".agentId: a17b6e8c5c8606dfa (use SendMessage with to: 'a17b6e8c5c8606dfa', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 498745
tool_uses: 155
duration_ms: 859305</usage>
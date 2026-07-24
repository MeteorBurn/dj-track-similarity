# Frontend v7 Port — ExecPlan

This document follows the repository root `PLANS.md`.

## Progress

- [x] Baseline captured: instructions, commits, dependencies, dirty tree and existing tests.
- [x] Phase A read-only audits completed.
- [x] Backend API → TypeScript → UI consumer → test matrix completed.
- [x] MuQ consumer matrix completed.
- [x] File ownership drafted for the write phase; activation waits for Phase A closure.
- [x] Shared v7 TypeScript/API contracts integrated.
- [x] Independent implementation workstreams integrated.
- [x] SET and Hybrid state/provenance separation completed.
- [x] Library loading 100/500/1000/All completed.
- [x] Standalone Rhythm Lab v7/MuQ UI completed.
- [x] SQLite measurement and allowed query optimization completed.
- [x] Frontend/backend/Rhythm Lab/docs gates completed.
- [x] Browser/runtime smoke completed.
- [x] First independent final review completed; three request/identity race
  findings reproduced and corrected with focused regression tests.
- [x] Corrective full validation, browser race smoke and independent re-review
  completed.
- [x] Independent final review completed and every item in
  `50-ACCEPTANCE.md` closed with evidence.
- [x] Post-acceptance Rhythm Lab startup regression audited against the
  preserved legacy Lab DB and label-transfer boundary.
- [x] Versioned Lab default, immutable schema preflight, mirrored docs and
  corrective runtime validation completed.
- [x] Shared exact Lab schema matrix, partial-schema and real-WAL regressions,
  full validation, and independent corrective re-review completed.
- [x] Replace the SONARA preparation UI with the confirmed Reset → Analyze
  workflow while preserving exact internal v7 contract identity.
- [x] Revalidate the simplified SONARA workflow across focused, full-suite,
  documentation and browser evidence.

## Current phase

Post-acceptance SONARA workflow simplification is complete. SONARA and its
mandatory locked Core output are selected at startup; Timeline, Embedding and
Fingerprint are optional. Selecting ML removes SONARA and classifiers without
changing either family’s results. The ordinary workflow is Analyze missing
outputs, or Reset SONARA followed by Analyze for a complete rebuild. Exact
contract hashes remain internal v7 provenance; the removed release card,
preparation dialog and frontend readiness gate no longer form a user workflow.

## Baseline

### Applicable instructions

- Read in full before the first edit: root `AGENTS.md`, `frontend/AGENTS.md`,
  `src/dj_track_similarity/AGENTS.md`, `tools/audio-doctor/AGENTS.md`,
  `tools/audio-dedup/AGENTS.md`, and `tools/rhythm-lab/AGENTS.md`.
- No applicable `AGENTS.override.md` exists.
- Read root `PLANS.md`, then `00-GOAL.md`, `10-CONTEXT.md`, `20-SPEC.md`,
  `30-ORCHESTRATION.md`, `40-VALIDATION.md`, and `50-ACCEPTANCE.md` in the
  prescribed order.
- Read the SQLite toolkit instructions at
  `C:\Utils\tools\sqlite-toolkit\AGENTS.md`; all measurements use disposable
  fixtures and explicit toolkit paths.
- Read `README.md`, `pyproject.toml`, `frontend/package.json`, `DESIGN.md`, the
  authoritative backend schemas/routes/repositories, and the current frontend
  API/client/consumer files.
- Inspected required history for `79295a0`, `b3b512a`, and `387a6e8`.
- `.omo/drafts/database-schema-redesign.md` was initially absent. The user added
  it during Phase C; it was then read in full (866 physical lines). Its ratified
  Core + mandatory Artifacts + optional Evaluation topology and exact
  `catalog_uuid + track_uuid + content_generation + contract_hash` invariants
  agree with the executable v7 design used here. Its historical SONARA 0.2.9 /
  schema 4 / revision 5 examples are superseded by the current executable
  `sonara_contract.py` pin (0.3.1 / schema 5 / revision 6).

### Git status and preserved unrelated changes

- Baseline branch: `main`; local and remote SHA both
  `96dd663bd75ddd1b6a46890054779b2878f1cc20`.
- Pre-existing untracked user files are preserved verbatim:
  `.kglite/code-review.kgl`, `.kglite/code-review.kgl.meta.json`, `PLANS.md`,
  and all static files under `plans/frontend-v7-port/`.
- The user-added `.omo/drafts/database-schema-redesign.md` is also preserved
  verbatim and is not part of this port's writable scope.
- `frontend/.playwright-cli/` appeared during the delegated baseline browser
  audit. It is task-generated evidence, not user work, and will be removed
  before closure after its observations are transferred here.
- No commit, push, PR, real database write, or audio-file operation is
  authorized.

### Baseline commands and results

- `frontend: npm run typecheck` — exit 0.
- `frontend: npm test` — exit 1, 139 tests: 127 passed and 12 pre-existing
  source-regex/legacy-fixture failures. The failures are one legacy MAEST field
  assertion, three SONARA display assertions, and eight SONARA feature-label
  assertions; they are in scope for replacement by v7 behavioral checks.
- `frontend: npm run build` — exit 0; Vite 7.3.6, 1,730 modules.
- Focused backend v7/API suite — 208 passed, one warning, 22.40 s.
- Rhythm Lab baseline suite — 26 passed, 4.84 s.
- Ports 5173, 8765, and 8777 were clear before and after the delegated baseline
  browser audit.

## Contract / consumer matrix

| Backend contract / route | TypeScript contract | UI consumers | Tests | Status / drift |
|---|---|---|---|---|
| `GET /api/tracks` → `TrackPageV7` / `TrackSummaryV7` | `Track` is the exact v7 summary with `track_id`, `catalog_uuid`, `track_uuid`, and `content_generation` | Library, rows, player, playlist, seeds, export, SET, Hybrid, Reference Compare | `apiContract`, `libraryView`, `playerAutoplay`, `metadataReferenceV7` | Implemented; no active `id/path` compatibility branch |
| `GET /api/tracks/{id}` → `TrackDetailV7` | `TrackDetailV7` extends the exact v7 summary with file/tags/Core/MAEST/embeddings/classifier details | Metadata dialog and track detail | `metadataReferenceV7`, `sonaraDisplay`, `sonaraFeatureLabels` | Implemented; detail is fetched before the dialog opens |
| `POST /api/tracks/filtered` → raw `TrackSummaryV7[]` | Client returns the bare typed array | Add all filtered | Exact mocked-fetch response/payload test in `apiContract` | Implemented |
| `POST /api/tracks/{id}/liked` + `TrackMutationIdentity` | Exact `catalog_uuid`, `track_uuid`, `expected_content_generation`, `liked` | Row/detail/search/SET/Hybrid liked controls | Mocked-fetch serializer plus backend CAS tests | Implemented |
| `GET /api/library/summary` | Exact `maest_analysis` and `maest_embedding` counts plus MERT/MuQ/CLAP/SONARA/classifiers | Counts and genre-write readiness | Header/library hook tests | Implemented; summary is not re-read on pure page/chunk navigation |
| Database current/switch state | Exact paths, optional Evaluation path, `catalog_uuid`, and `selected` | Startup, switch dialog, request keys | API/client and library request-key tests | Implemented; catalog identity participates in stale guards |
| Analysis/classifier reset and clear | Exact `analysis_family` / `classifier_keys` bodies and Core/Artifacts/classifier deleted-row result | Reset/clear dialogs and status | Exact mocked-fetch MuQ/reset serialization | Implemented; removed legacy body/result names |
| `POST /api/search` (`mert` / `muq`) | `EmbeddingSearchRequest` requires `analysis_family`; removed v6 tuning fields | Shared typed MERT and MUQ tab component | Exact mocked-fetch MuQ serialization plus UI current/missing/stale tests | Implemented |
| SONARA output selection | Exact `core`, `timeline`, `embedding`, `fingerprint` union | Library analysis controls and detail manifest | SONARA storage/identifier tests | Implemented; `representations` removed |
| `POST /api/set-builder/generate` | Exact source/weight request and response `sources`, `weights_used`, coverage including `missing_muq` | Nested `Set Builder` surface with its own request/result provenance | `setBuilderControls`, `searchPlaylistLayout`, mocked-fetch contract | Implemented |
| `POST /api/search/hybrid` | Five-source union including MuQ and `source_contract_hashes` keyed by all Hybrid sources including SONARA | Independent nested `Hybrid Preview` surface | `hybridPreviewState`, mocked-fetch contract, backend API tests | Implemented; readiness conflicts map to 409 |
| Audio Dedup start/status | Exact `sources` and exact-key `weights`, echoed by status | Audio Dedup advanced source/weight controls and applied-profile display | `audioDedupControls`, `audioDoctorSurface`, mocked-fetch contract | Implemented; apply safety remains unchanged |
| Reference Compare + verdict | Exact v7 result tracks and nested seed/candidate mutation identities with notes | Main LAB panel including independent MuQ group | Frontend contract/state tests and backend 422/409/no-write tests | Implemented |
| Rhythm Lab launch/status | Nested source binding with database path and catalog UUID; standalone parser accepts the binding flag | Main toolbar launch/status | Main bridge tests plus standalone CLI/web tests | Implemented |
| Standalone Rhythm Lab track/liked/status | Exact v7 identity and structured five-family `current/missing/stale` status | Static UI uses `track_id`/`file_path`, exact liked identity, five-source recipes | `test_rhythm_lab.py`, `test_v7_consumers.py` | Implemented |
| Library pagination | Route page max remains 500 | 100/500 plus sequential 500-row chunks for 1000/All, progress/cancel, request-key/catalog guards, 120-row render window | `libraryLoading`, `libraryWindow`, library hook/view tests | Implemented without raising backend limit |

## MuQ consumer matrix

| Backend contract | TypeScript type | UI file/control | Behavior | Test | Status |
|---|---|---|---|---|---|
| Analysis/pipeline and reset | `AnalysisModel` and exact reset `analysis_family` include MuQ | Library analysis selection, job status and reset | MuQ runs in ML order; reset returns current deleted-row counters | Exact mocked-fetch reset plus backend job/reset tests | Complete |
| Generic seed search | Canonical `EmbeddingSource` includes MuQ | Dedicated MUQ tab using shared `EmbeddingSearchTab` | Calls `/api/search` with `analysis_family="muq"`; remains visible at zero coverage with scoped reason | `apiContract`, `sonaraSearchControls`, `helpTextV7` | Complete |
| SET | Exact source/weight/coverage/result types include MuQ | Nested Set Builder advanced source controls and response evidence | Backend raw default is MERT/MAEST/MuQ/CLAP `.30/.18/.15/.22` plus SONARA broad `.30`; exact pre-MuQ opt-out remains representable | Payload/signature/provenance, UI and serializer tests | Complete |
| Hybrid | `HybridSearchSource` and returned contract-hash map include MuQ | Independent nested Hybrid Preview source controls and result support | Backend default is five equal normalized `.20`; four-source opt-out normalizes to `.25` | Payload/signature/request-guard/UI/serializer tests plus backend API | Complete |
| Hybrid explanation | No special MuQ semantic axis required | Result explanation | MuQ cosine uses `(score + 1) / 2` | Existing `-1→0`, `0→.5`, `1→1` test | Complete; preserve |
| LAB / Reference Compare | Model union and exact mutation identities include MuQ | Visible MuQ group, model-scoped reason, notes and verdict | Independent group or unavailable reason; verdict writes `model="muq"` only for the exact displayed pair | Frontend stale/serialization tests and backend no-write 409 tests | Complete |
| Classifier inputs/readiness | Typed manifests/status include MuQ and `required_families` | Class tab/help | Help names SONARA/MERT/MAEST/MuQ/CLAP and UI retains manifest-scoped readiness | `helpTextV7` plus backend manifest/scoring tests | Complete |
| Audio Dedup | Request/status exact source/weight types include MuQ | Default-enabled toggle/weight and actual status profile | Default `.43/.32/.12/.04`; exact pre-MuQ `.43/.32/.04`; MuQ never replaces MERT+MAEST delete-safety gate | UI, payload and safety tests | Complete |
| Track coverage/detail | Exact coverage record and typed MuQ embedding detail | Summary coverage, metadata and rows | Current-contract MuQ is separate from other embeddings | `metadataReferenceV7`, display and coverage tests | Complete |
| Evaluation profiles | Canonical typed source unions include MuQ | Hybrid evaluation/session tooling | Returned support remains source-scoped and contract hashes retain SONARA as well | Typecheck and Hybrid tests | Complete |
| Standalone Rhythm Lab | Structured five-family status and recipe-derived required sources | Track/features/readiness UI | Distinguishes current/missing/stale MuQ; `combined` remains `sonara+mert+maest`; MuQ is required only by recipes that select it | 33 standalone tests including static/API payloads | Complete |

## Active ownership

Phase A is closed. Shared/fan-in contracts, CSS, conflict
resolution, integration, validation, and final review remain with the primary
agent.

| Workstream | Agent | Mode | Writable scope | Forbidden shared/fan-in files | Status |
|---|---|---|---|---|---|
| Main integration | Primary agent | write | `plans/frontend-v7-port/EXECPLAN.md`, `frontend/src/api.ts`, `apiClient.ts`, `App.tsx`, `useSearchPlaylist.ts`, `styles.css`; main backend schemas/routes/launcher/collections; fan-in tests | — | Complete; corrective search/detail scoping, atomic identity boundaries and all full gates green |
| Library loading/rendering | `/root/frontend_library_implementation` | write | `useLibraryState.ts`, `libraryView.ts`, `LibraryPanel.tsx`, `TrackPanel.tsx`, `TrackRows.tsx`, new isolated loading/window helpers and their tests | `api.ts`, `apiClient.ts`, `App.tsx`, `SearchPlaylistPanel.tsx`, `styles.css` | Complete; integrated |
| Search / SET / Hybrid surface | `/root/frontend_search_implementation` | write | `SearchPlaylistPanel.tsx`, isolated state/tab helpers, related tests | `api.ts`, `apiClient.ts`, `App.tsx`, `styles.css` | Complete; integrated |
| Metadata / Reference Compare | `/root/frontend_metadata_reference_implementation` | write | `TrackMetadataDialog.tsx`, `trackDisplay.ts`, `syncopatedRhythm.ts`, `ReferenceComparePanel.tsx`, `helpText.ts`, related tests | Shared contracts, main backend routes, `styles.css` | Complete; integrated |
| Audio Dedup UI | `/root/frontend_audio_dedup_implementation` | write | `AudioDedupDialog.tsx`, `audioDedupControls.test.mjs`, Audio-Dedup-only assertions in `audioDoctorSurface.test.mjs` and `clapSimilaritySemantics.test.mjs` | Shared contracts, helper backend, `styles.css` | Complete; integrated diff reviewed |
| Standalone Rhythm Lab | `/root/rhythm_lab_implementation` | write | `tools/rhythm-lab/rhythm_lab/{source_db.py,features.py,web_app.py,training.py,cli.py,static/index.html,static/app.js,static/styles.css}` and `tools/rhythm-lab/tests/{test_rhythm_lab.py,test_v7_consumers.py}` plus new standalone-only tests | Main `src/`, React shared files, v7/Lab schemas, `lab_db.py`, `predictions.py` | Complete; integrated and independently retested |
| Backend query optimization | `/root/backend_query_implementation` | write | `src/dj_track_similarity/db_library_queries.py`, `tests/test_library_repository_v7.py`, and one new focused repository benchmark/helper test if needed | Schemas, indexes, migrations, frontend, all `tools/rhythm-lab/` files | Complete; integrated diff reviewed |
| Backend contract tests | `/root/backend_contract_tests` | write | `tests/test_api_reference_compare.py`, `tests/test_api_rhythm_lab.py`, `tests/test_api_hybrid_search.py`, plus one new API-contract-only test if needed | Runtime source, frontend, query-worker tests, helper tests | Complete; integrated diff reviewed |
| Documentation mirror | `/root/frontend_v7_docs` | write | `README.md` and only directly affected EN/RU Markdown under `docs/dj-track-similarity/` | Runtime source, plans, generated `site/`, unrelated dirty files | Complete; 30 EN pages and 30 mirrored RU pages integrated, docs gate green |
| Independent final review | `/root/frontend_v7_final_review` | read-only | Entire final diff, plans and acceptance evidence | All files are read-only; no real data, commit, push or PR | Complete; focused re-review confirms all three findings resolved with no remaining P0/P1/P2 in scope |
| Rhythm Lab startup regression audit | `/root/rhythm_lab_audit` | read-only | Current launcher/CLI/Lab DB/default-path sources, docs and tests | No edits, services, DB opens, audio, commit, push or PR | Complete; final re-review found no remaining P0/P1/P2 after exact-schema and WAL corrections |
| Rhythm Lab default-path correction | Primary agent | write | Shared labels-path/schema helpers, launcher, standalone CLI/Lab preflight, focused bridge/helper tests, directly affected docs and this ExecPlan | Real Lab/Core/Artifacts DBs, audio, label migration/apply, generated state | Complete; 92 focused tests, 1,093 root tests and docs gate green; real legacy file hash unchanged |
| SONARA simple workflow correction | Primary plus non-overlapping backend/docs workers | write | Backend worker: `db_analysis.py`, `analysis_jobs.py`, focused tests. Primary: `App.tsx`, `LibraryPanel.tsx`, selection/tests/CSS and integration. Docs worker: assigned README plus four EN/RU page pairs. Primary retains this ExecPlan and final fan-in. | Real Core/Artifacts databases, audio, actual analysis/reanalysis, schema/DDL/index changes, overlapping file edits, worker commit/push/PR | Implemented; validation and browser evidence in progress |

## Dependency graph and phase plan

### Phase A — parallel read-only audit

- Six delegated investigations completed: backend v7 contracts, frontend consumer
  inventory, MuQ/model consumers, standalone Rhythm Lab, SQLite/query behavior,
  and visual/test baseline.
- The reports independently converge on identity loss,
  invalid write payloads, stale model unions/copy, absent large-library
  controls, shared SET provenance, and Rhythm Lab launcher/static-UI breaks.
- No delegated audit edited repository source or used a real database/audio file.

### Phase B — bounded implementation

- Primary first establishes exact shared TypeScript/client contracts and the
  narrow backend 409/identity corrections.
- Non-overlapping UI, standalone Rhythm Lab, and query workstreams then run in
  parallel against those contracts.
- Primary owns CSS and integrates each completed bounded diff after focused
  tests.

### Phase C — integration and focused verification

- Remove all active legacy Track consumers, integrate SET/Hybrid provenance,
  synchronize liked state, and close exact serializer/response tests.
- Run focused frontend, backend, helper, and SQLite performance checks after
  each fan-in.

### Phase D — full validation and browser smoke

- Run frontend typecheck/test/build; focused and then safe broader backend and
  Rhythm Lab suites; docs check; `git diff --check`.
- Use disposable v7 Core+Artifacts fixtures only. Exercise desktop, narrow, and
  200% zoom in the in-app browser; inspect console and API failures.

### Phase E — independent final review and closure

- Delegate a read-only final diff/acceptance review.
- Close every AC with exact evidence, remove task-generated local files, verify
  unrelated user files remain, then mark the Goal complete.

## Surprises & Discoveries

Record facts discovered from the executable code, tests, database fixtures or runtime behavior. Do not record unsupported assumptions.

- Active React code has two incompatible track models; the nominal v7 types are
  not the runtime client boundary.
- `/api/tracks/filtered` returns an array, while the client invents an envelope.
- Generic MERT search currently sends forbidden v6 fields and returns 422 under
  the v7 `extra="forbid"` schema.
- Backend MuQ support is already complete across analysis, generic search, SET,
  Hybrid, Reference Compare, classifier scoring, and Audio Dedup. Nearly all
  missing work is frontend integration, not a new backend model path.
- Hybrid missing/stale embedding readiness raises `RuntimeError`; its route
  catches only `ValueError`, so the intended conflict currently becomes 500.
- The main launcher emits `--source-catalog-uuid`, but the standalone Rhythm Lab
  parser does not accept or forward it.
- `library_summary()` measured 1,477.31 ms on the disposable 6,000-track fixture,
  yet the current hook calls it for every page request whose own median is only
  52–150 ms.
- Main list coverage hydration is batched rather than per-track N+1, but its
  contract-first plans scan all rows for an active contract. Driving bounded
  pages from requested IDs changes the plan to primary-key lookup and improved
  same-run medians.
- Rhythm Lab prediction pagination repeats an expensive ranked CTE for count and
  page. `COUNT(*) OVER()` improved the 500-row case there, but regressed the main
  list and therefore is not a general replacement.
- No new SQLite index is justified; the allowed wins are query direction,
  removing duplicate work, bounded batching, and fail-closed validation caching.
- Every existing frontend test reads source text; only two suites execute a
  transpiled client with mocked fetch. Browser and overlapping-request behavior
  have no baseline automated gate.
- The installed Vite resolved to 7.3.6 although package metadata uses a
  compatible range around the documented 7.2.x baseline.
- The user-supplied schema draft confirms the exact v7 identity and sidecar
  topology used by this port, but contains historical SONARA pins and migration
  rollout commands. Executable source/tests override those historical examples;
  this task does not execute the draft's schema migration or real-library
  rollout.
- Hybrid `source_contract_hashes` includes `sonara` in addition to the four
  embedding sources. The TypeScript response and UI provenance map must
  therefore use `HybridSearchSource`, not the narrower `EmbeddingSource`.
- A liked mutation handler that reports an API error and then rethrows can
  create an unhandled browser promise when used by an icon-button callback.
  The integrated handler now returns `null` after reporting failure, and local
  SET/Hybrid synchronization updates only after a non-null current track.
- The initial catalog-binding effect can invalidate an already-started summary
  request while the duplicate refresh guard suppresses its replacement. The
  library hook now adopts the selected database scope before React publishes
  the new database state, so summary and page requests share one request key.
  Browser reload then converges to `TRACKS 5941` and `1–100 / 5941`.
- At 640 CSS px the SET and Hybrid advanced source grids still retained two
  columns even though the page itself did not overflow. A `max-width: 720px`
  rule now makes both grids single-column; the same layout remains clean under
  a 640 CSS px viewport and a 2× device-scale emulation.
- The first independent final review found that SONARA/MERT/MUQ/CLAP shared one
  provenance-free result array. A late response could overwrite a newer
  tab/seed/filter scope and the same rows could render beneath another tab.
- The same review found two exact-identity TOCTOU boundaries: Reference Compare
  validated identities before a later numeric-ID write, while Rhythm Lab
  collections validated then re-resolved numeric IDs. The corrective backend
  path now guards feedback in the same `BEGIN IMMEDIATE` upsert statement and
  builds a collection from one exact snapshot without a second numeric rebind.
- Track detail used a numeric ID and committed every response, so rapid A→B
  selection or a catalog switch could display late A data. The corrective
  client aborts superseded requests and commits only an exact four-field v7
  identity in the still-current catalog.
- Greenfield activation made the Lab schema exact-identity-only but left three
  implicit writable defaults on the preserved `rhythm_lab.sqlite`: standalone
  CLI, main launcher and main-app collection saves. The production default
  therefore selected recovery input instead of a new v7 Lab database.
- A temporary legacy fixture showed that rejecting after ordinary
  `sqlite3.connect()` preserved logical rows but still changed physical SQLite
  bytes. Existing Lab files now receive an immutable main-file preflight before
  any writable connection, followed by a live WAL-visible exact check before
  DDL. Main-file legacy fixtures remain byte-identical on rejection.
- The collection bridge originally accepted a partially converted
  `classifier_labels` table when it contained only the four v7 identity fields.
  One shared exact matrix now validates all six Lab classifier tables for both
  the bridge and standalone runtime before any DDL.
- A real WAL fixture with committed frames and a closed writer confirmed that
  validation preserves the durable main database and WAL byte-for-byte.
  SQLite may update read marks inside the transient SHM WAL index while reading;
  tests therefore require that SHM remains present at the same size and separately
  prove that no table or row was created, removed, or rebound.
- The user does not need a distinct SONARA release workflow. The useful
  invariant is simpler: exact contract hashes remain internal provenance,
  ordinary runs fill missing requested outputs, and an explicit full SONARA
  reset removes old rows and active pointers so the next Analyze can register
  the current exact four-output identity automatically.
- The first implementation of that simplification handled a fresh SONARA state
  but retained old active settings after reset. A focused old-runtime → reset →
  current-runtime test exposed the gap; full SONARA reset now clears those
  settings in the same transaction while historical immutable contracts remain.
- Independent review exposed two corrupt-pointer reset states: one missing
  active contract, or all active settings missing while SONARA rows survive.
  Both must return `409` before mutation; only a genuinely empty state is a
  successful no-op. Parameterized route tests preserve settings and Core rows
  in both rejected cases.
- Browser QA against the existing read-only catalog exposed duplicate React
  keys when several classifier artifacts returned the same blocker text.
  Classifier identity plus blocker position now supplies a stable unique key;
  no new console error appeared after the corrective render.

## Decision Log

| Date/time | Decision | Evidence / rationale | Consequences |
|---|---|---|---|
| 2026-07-24 12:40 +03:00 | Treat backend schemas/routes/repositories/tests as the contract source of truth | The referenced `.omo` draft is absent; executable v7 sources are present and focused tests are green | No inferred schema redesign and no real-data migration |
| 2026-07-24 12:55 +03:00 | Replace the active legacy Track graph instead of adding another compatibility mapper | Identity loss begins at the declared client return type and fans out through every consumer | Shared contracts land first; leaf consumers migrate afterward |
| 2026-07-24 13:05 +03:00 | Preserve backend MuQ semantics and defaults | Backend tests already prove rank effect, clean disable, classifier identity, and delete safety | Frontend exposes actual sources/weights; no duplicate model logic |
| 2026-07-24 13:10 +03:00 | Keep CLAP text search distinct from CLAP audio-to-audio evidence | Search embeds text; SET/Hybrid/Dedup consume stored audio embeddings | UI copy and thresholds remain workflow-specific |
| 2026-07-24 13:15 +03:00 | Use sequential chunks of at most 500 with cancellation and generation-aware dedupe for 1000/All | Backend page limit is 500 and current loader has a stale overwrite race | No backend max-page increase or unbounded response |
| 2026-07-24 13:20 +03:00 | Keep shared contracts, `App.tsx`, `styles.css`, and final integration with the primary | They are fan-in files referenced by every proposed workstream | Workers receive strict non-overlapping ownership |
| 2026-07-24 13:30 +03:00 | Make no schema or index change | The 6,000-track query-plan audit found measurable query-shape wins using existing primary keys and indexes | AC-16 can be closed with before/after plans while AC-17 remains invariant |
| 2026-07-24 13:32 +03:00 | Do not refresh full library summary on pure page/chunk navigation | `library_summary()` median 1,477.31 ms versus 52.42/149.84 ms for 100/500-row pages | Refresh summary only on database or data-changing events; keep exact liked-count adjustment |
| 2026-07-24 13:34 +03:00 | Apply `COUNT(*) OVER()` only to the measured Rhythm Lab track/prediction paths | Main list prototype regressed 15.02→16.72 ms; Lab tracks improved 26.32→19.59 ms and predictions 237.87→166.17 ms | Preserve explicit empty/out-of-range fallback and avoid indiscriminate SQL rewrites |
| 2026-07-24 Phase C | Treat the newly supplied schema draft as architecture context, not an instruction to execute its migration | The draft explicitly keeps real migration/reanalysis behind separate approval and contains historical SONARA pins; current schemas/contracts/tests are newer | Preserve Core 7 / Artifacts 1 topology, make no DDL/version/index/real-data change, and use current executable contracts |
| 2026-07-24 Phase C | Type Hybrid contract hashes over all Hybrid sources and make liked UI failures non-throwing after reporting | Backend includes a SONARA contract hash; icon callbacks do not await rejected promises | Provenance stays exact and an API error does not create an unrelated console rejection |
| 2026-07-24 Phase D | Adopt a database scope before publishing database selection/reset state | A browser reload exposed a summary request invalidated between database initialization effects | Summary, list chunks and stale guards start from the same `catalog_uuid`-qualified scope |
| 2026-07-24 Phase D | Collapse SET and Hybrid source controls to one column below 720 CSS px | 640 px browser measurement found no page overflow but source rows were unnecessarily compressed | Labels, toggles and weights remain readable at narrow and 200%-equivalent layouts |
| 2026-07-24 Phase E | Give each generic search response an origin and exact catalog/seed-identity/filter/query key | Independent review demonstrated cross-tab rendering and late overwrite despite separate SET/Hybrid guards | SONARA/MERT/MUQ/CLAP requests share an abort/token guard but results render only under their originating tab and current key |
| 2026-07-24 Phase E | Move verdict identity predicates into the feedback upsert and persist Rhythm Lab selections from one exact snapshot | Validate-then-resolve left a generation-change window in both mutation paths | Stale races fail with 409 and cannot write or rebind a replacement generation |
| 2026-07-24 Phase E | Treat track detail as an exact-identity request even though the route is numeric | A late numeric response could replace the current dialog selection | Abort/token/catalog guards plus four-field response comparison prevent A→B and database-switch overwrite |
| 2026-07-24 follow-up | Move every implicit writable Lab consumer to shared `rhythm_lab_v7.sqlite`; retain explicit legacy-path rejection and label transfer | Numeric/path-keyed legacy labels cannot be converted to exact v7 identity in place, and the old DB is the recovery source | Normal launch and collection saves create/use a separate greenfield file; no rename, migration, checkpoint or write to the preserved DB |
| 2026-07-24 follow-up | Preflight the main-file view through an immutable read-only URI, then repeat exact validation on the live WAL-visible view before DDL | A focused byte snapshot proved rollback after main-file schema rejection was not physically byte-preserving, while immutable mode intentionally ignores WAL | Main-file legacy paths fail before any writable SQLite open; WAL-only legacy frames fail before DDL and point to `rhythm_lab.label_transfer` |
| 2026-07-24 follow-up | Share one exact column matrix for all six Lab classifier tables between standalone and collection code | A four-field subset check allowed partially converted classifier tables to reach collection DDL | Every existing classifier/review table is exact-checked before schema creation; partial v7 tables fail closed |
| 2026-07-24 follow-up | Define WAL rejection durability over the main database and WAL; treat SHM as a transient WAL index | A closed-writer real-WAL fixture showed SQLite validation reads can change only SHM read marks | Main and WAL bytes, logical schema and rows must remain unchanged; SHM must remain present with stable size |
| 2026-07-24 SONARA follow-up, superseded | Expose active-release readiness and explicit preparation in the main UI | This was a fail-closed interpretation of exact contract identity | Superseded after user workflow review; retained only as historical decision evidence |
| 2026-07-24 SONARA simplification | Keep version identity internal and restore Reset → Analyze as the ordinary workflow | The user runs one SONARA configuration, accepts full reset/reanalysis after a future update, and does not need release management | Startup is SONARA + locked Core; no release card/dialog/gate; first/no-result Analyze registers exact contracts automatically |
| 2026-07-24 SONARA reset semantics | Clear SONARA active settings only during a complete four-output reset, then allow activation when no SONARA rows or dependent scores remain | Otherwise a future old-runtime → Reset → new-runtime sequence would stay blocked by old metadata | Historical contracts remain immutable; partial resets do not strand remaining data; no schema or index change |
| 2026-07-24 SONARA reset fail-closed correction | Require the exact release plus four active contract pointers before deleting; when every pointer is absent, inspect Core, Artifacts and dependent classifier rows before accepting an empty no-op | Independent review found that partial pointers could trigger partial deletion and zero pointers could hide surviving data | Inconsistent pointer/data states return `409` with zero mutation; parameterized route coverage closes both cases |
| 2026-07-24 SONARA follow-up | Bind every prepare request to the reviewed `catalog_uuid` and check it inside `exclusive_db` before `_prepare` | Independent review reproduced catalog A status followed by a switch and successful mutation of catalog B | Stale confirmations fail with `409 SONARA_CATALOG_CHANGED` before backup or activation |
| 2026-07-24 SONARA follow-up | Hold the application state lock from job availability check through manager queueing | Independent review reproduced preparation acquiring exclusivity during SONARA preflight | `job_start()` serializes every API job-start boundary against switch/exclusive maintenance; preparation either wins first or observes a queued/running job |
| 2026-07-24 SONARA follow-up | Preserve `unavailable` as distinct from `preparation_required` | The generic error mapper prefixed any detail containing `release`, even a missing runtime package | Only an explicit readiness marker recommends preparation; runtime-unavailable details remain actionable and fail closed |

## Validation Evidence

| Gate | Exact command / action | Result | Evidence | Related AC |
|---|---|---|---|---|
| Baseline frontend types | `cd frontend; npm run typecheck` | Exit 0 | TypeScript baseline only; semantic contract drift remains | AC-18 |
| Baseline frontend tests | `cd frontend; npm test` | Exit 1: 127/139 pass | 12 named legacy/source-regex failures recorded above | AC-18 |
| Baseline frontend build | `cd frontend; npm run build` | Exit 0 | 1,730 modules, no tracked generated files | AC-18, AC-23 |
| Backend v7/API baseline | `.venv\Scripts\python.exe -m pytest` with 13 focused v7/API files and `--override-ini addopts=` | 208 passed; one warning; 22.40 s | Temporary test fixtures only | AC-02, AC-17, AC-19 |
| Rhythm Lab baseline | `.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py tools\rhythm-lab\tests\test_v7_consumers.py --override-ini addopts=` | 26 passed; 4.84 s | Temporary test fixtures only | AC-10, AC-19 |
| Baseline browser | Vite-only no-backend audit at desktop and 640 CSS px | Safe empty/error state; two expected `/api/database/current` proxy 500s | Found missing tab ARIA/keyboard behavior and wrapped six-tab strip | AC-15, AC-20 |
| SQLite audit integrity | Explicit toolkit `sqlite3.exe`; `PRAGMA integrity_check` on disposable Core, Artifacts, Lab | `ok` for all three | 6,000 Core/Artifacts tracks and 12,000 Lab predictions; no real DB | AC-16, AC-17 |
| SQLite audit topology | Inspect fixture versions and repository schemas | Core 7, Artifacts 1, Lab 0; no DDL/index/version change | Mandatory bound Core+Artifacts preserved | AC-16, AC-17 |
| Main query implementation | `.venv\Scripts\python.exe -m pytest tests\test_library_repository_v7.py tests\test_api_tracks.py --override-ini addopts=` | 20 passed; one external deprecation warning | ID-driven bounded hydration, indexed primary classifier drive, stale/multi-filter/order tests | AC-01, AC-16, AC-17, AC-19 |
| Main query static checks | `.venv\Scripts\python.exe -m compileall -q src\dj_track_similarity\db_library_queries.py`; `git diff --check -- ...` | Both exit 0 | No DDL/index/schema/topology change | AC-16, AC-17, AC-21 |
| Audio Dedup UI | `node --test tests/audioDedupControls.test.mjs tests/audioDoctorSurface.test.mjs tests/clapSimilaritySemantics.test.mjs` | 17/17 passed | Default/custom/legacy MuQ profiles, exact apply confirmation, MERT+MAEST guard, truthful CLAP semantics | AC-04, AC-09, AC-11, AC-18 |
| Backend identity/readiness contracts | `.venv\Scripts\python.exe -m pytest tests\test_api_reference_compare.py tests\test_api_rhythm_lab.py tests\test_api_hybrid_search.py --override-ini addopts=` | 34 passed; one external warning; 11.73 s | Exact MuQ verdict/collection identities, legacy 422, stale 409 without writes, Hybrid RuntimeError 409 | AC-02, AC-06, AC-17, AC-19 |
| Frontend TypeScript fan-in | `cd frontend; npm run typecheck` | Exit 0 | Exact v7 contracts and all integrated consumers compile under `--noUnusedLocals --noUnusedParameters` | AC-01, AC-02, AC-18 |
| Frontend full Node suite | `cd frontend; npm test` | 154 passed, 0 failed; 1.47 s | Exact mocked-fetch serializers, pure payload/signature/request guards, keyboard state, loading/windowing, metadata/LAB and safety assertions | AC-01–AC-15, AC-18 |
| Rhythm Lab integrated suite | `.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py tools\rhythm-lab\tests\test_v7_consumers.py --override-ini addopts=` | 33 passed; one external warning; 5.72 s | Exact Core+Artifacts binding, identity/CAS, MuQ current/missing/stale, recipe readiness, chunked queries and stale-artifact 409 | AC-10, AC-17, AC-19 |
| Focused integrated backend | `.venv\Scripts\python.exe -m pytest` with 19 v7/API/search/SET/Hybrid/LAB/Dedup/runtime files and `--override-ini addopts=` | 293 passed; one external warning; 40.48 s | Every changed backend contract plus schema/bundle identity and classifier boundary | AC-01, AC-02, AC-06, AC-09–AC-11, AC-17, AC-19 |
| Full safe root backend | `.venv\Scripts\python.exe -m pytest` | Exit 0; 1,089 passed; one external warning; 201.88 s | Root `testpaths=tests`; includes both forced identity-race regressions; temporary fixtures only, no real library | AC-01, AC-02, AC-06, AC-10, AC-17, AC-19 |
| Final frontend types | `cd frontend; npm run typecheck` | Exit 0 | Integrated v7 contracts compile with unused checks after the final request-scope and exact-detail fixes | AC-01, AC-02, AC-18 |
| Final frontend tests | `cd frontend; npm test` | 161 passed, 0 failed; 1.68 s | Includes exact serializers, generic tab/request-key races, exact-detail guards, loading/windowing, keyboard state, responsive grids, metadata/LAB and safety assertions | AC-01–AC-15, AC-18 |
| Final frontend build | `cd frontend; npm run build` | Exit 0; Vite 7.3.6, 1,734 modules; 2.75 s | Production bundle built after corrective fixes; `dist/` remains ignored generated output | AC-18, AC-23 |
| Documentation | `cd docs/dj-track-similarity; npm run check` | Exit 0 | Final repeat: Vale 0 errors/0 warnings/0 suggestions across 109 files; locale parity 54/54; VitePress 1.6.4 build 8.46 s | AC-24 |
| Documentation diff hygiene | `git diff --check -- README.md docs/dj-track-similarity` | Exit 0 | Thirty affected EN pages and all thirty RU mirrors plus README are source-only; generated `site/` remains absent from Git | AC-21, AC-23, AC-24 |
| Full diff hygiene | `git diff --check`; `git diff --no-index --check -- /dev/null <file>` for ten untracked task files | Exit 0 / no check output | Final tracked diff and all new implementation/test/ExecPlan files contain no whitespace errors | AC-21 |
| Task-local cleanup | Verify absolute targets, stop verified fixture process trees, then remove browser/SQLite-audit/full-pytest/race artifacts | Ports 8765/8777 clear; all exact cleanup targets absent | Removed only task-created browser, SQLite-audit, pytest-log and `dj-front-v7-race-019f9393` disposable directories | AC-17, AC-23 |
| Corrective frontend regressions | `cd frontend; node --test tests/metadataReferenceV7.test.mjs tests/hybridPreviewState.test.mjs tests/apiContract.test.mjs` | 29 passed, 0 failed; 0.73 s | Exact detail matching, AbortSignal forwarding, tab/request-key provenance and late-response guards | AC-02, AC-04, AC-05, AC-15, AC-18 |
| Corrective backend race regressions | `.venv\Scripts\python.exe -m pytest tests\test_api_reference_compare.py tests\test_api_rhythm_lab.py --override-ini addopts=` | 26 passed; one external warning; 6.58 s | Forced generation change at the final verdict write and collection snapshot boundaries returns 409 with no feedback/rebind | AC-02, AC-06, AC-10, AC-17, AC-19 |
| Corrective compile/type gates | `.venv\Scripts\python.exe -m compileall -q src\dj_track_similarity`; `cd frontend; npm run typecheck` | Both exit 0 | Backend exact-identity code compiles and the corrected shared UI contracts pass unused checks | AC-02, AC-18 |
| Corrective browser race smoke | In-app Browser against a three-track disposable Core 7 + Artifacts 1 bundle with deterministic 1,500 ms search/detail latency | Late SONARA rendered 0 blocks under MUQ; completed MUQ showed `MUQ results 1` only under MUQ, restored only on return and cleared after a seed change; overlapping A→B detail stayed Beta | Clean repeat used valid temporary WAVs: 25 HTTP request lines, no non-2xx/3xx, empty development log, and `scrollWidth 914 < viewport 929` | AC-02, AC-04, AC-05, AC-15, AC-20 |
| Focused independent re-review | `/root/frontend_v7_final_review` read-only re-review of the three prior findings | All three resolved; no remaining P0/P1/P2 or new regression in scope | Reviewer reran 5/5 frontend and 2/2 forced backend race tests and explicitly supports AC-02/04/05/06/10/15 | AC-02, AC-04–AC-06, AC-10, AC-15 |
| Rhythm Lab labels-path follow-up | `.venv\Scripts\python.exe -m pytest tests\test_api_rhythm_lab.py tests\test_rhythm_lab_bridge_v7.py tools\rhythm-lab\tests\test_rhythm_lab.py tools\rhythm-lab\tests\test_v7_consumers.py tools\rhythm-lab\tests\test_label_transfer.py --override-ini addopts=` | 92 passed; one external warning; 10.38 s | Shared `rhythm_lab_v7.sqlite` default, exact six-table validation, partial-v7 rejection, exact launcher argument, direct startup, collection save, label recovery, and closed-writer committed-WAL fixtures; durable main/WAL bytes unchanged and transient SHM retained at the same size | AC-10, AC-17, AC-19 |
| Full backend after labels-path correction | `.venv\Scripts\python.exe -m pytest` | Exit 0; 1,093 passed; one external warning; 195.17 s | All root API/bridge consumers, including partial-schema and WAL regressions, remain green; temporary fixture DBs only | AC-10, AC-17, AC-19 |
| Rhythm Lab corrective re-review | `/root/rhythm_lab_audit` read-only review of the final source, disposable-fixture tests and evidence | No remaining P0/P1/P2 | Confirmed shared six-table matrix, pre-DDL partial-schema rejection, closed writer with committed WAL frames, durable byte boundary and explicit transient-SHM contract; no real DB was opened | AC-10, AC-17, AC-19, AC-21 |
| Follow-up documentation | `cd docs/dj-track-similarity; npm run check` | Exit 0 | Vale 0 errors/0 warnings/0 suggestions across 109 files; locale parity 54/54; VitePress 1.6.4 build 8.32 s | AC-24 |
| Preserved real Lab state | Before/after length, UTC mtime and SHA-256 for `tools/rhythm-lab/data/rhythm_lab.sqlite`; verify v7 default absent | 212,320,256 bytes; `2026-07-21T02:47:43.9331908Z`; `E07B4B39A9239ED95791AAB5443F77CE8F42CE67C30B253A341A211BA7CCCA09`; `rhythm_lab_v7.sqlite` absent | An early toolkit read created an empty WAL and 32 KiB SHM at 13:24:06; exact path/size/process checks proved they were task-generated, both were removed, and the original no-sidecar state was restored | AC-17, AC-22, AC-23 |
| Follow-up diff hygiene | `git diff --check`; changed-path/generated-state/status inspection | Exit 0; 19 scoped tracked files | No SQLite/log/dist/site file in diff; v7 default and legacy sidecars absent; `.kglite`, root `PLANS.md` and ignored `.omo` draft preserved; port 8777 clear | AC-21–AC-23 |
| SONARA focused backend | `.venv\Scripts\python.exe -m pytest tests\test_api_runtime_v7.py tests\test_analysis_sonara_preflight_v7.py tests\test_api_analysis_jobs.py --override-ini addopts=` | 29 passed; one external warning; 6.63 s | Fresh/ready status, pipeline-before-queue 409, stale catalog rejected before `_prepare`, exclusive/job-start TOCTOU, active-job prepare 409, and unavailable semantic regression | AC-02, AC-17, AC-19 |
| SONARA final frontend | `cd frontend; npm run typecheck`; `npm test`; `npm run build` | Exit 0; 166 passed; Vite 7.3.6, 1,736 modules, 2.57 s | Exact status/prepare serializer, catalog/request-token guard, startup/output selection, confirmation/focus assertions, and production bundle | AC-02, AC-15, AC-18 |
| SONARA full backend | `.venv\Scripts\python.exe -m pytest` | Exit 0; 1,099 passed; one external warning; 191.71 s | Final repeat after active-job HTTP 409 correction; all root API/job/exclusive-operation and v7 consumers pass on temporary fixtures only | AC-02, AC-10, AC-17, AC-19 |
| SONARA Rhythm Lab repeat | `.venv\Scripts\python.exe -m pytest tests\test_api_rhythm_lab.py tests\test_rhythm_lab_bridge_v7.py tools\rhythm-lab\tests\test_rhythm_lab.py tools\rhythm-lab\tests\test_v7_consumers.py tools\rhythm-lab\tests\test_label_transfer.py --override-ini addopts=` | 92 passed; one external warning; 11.16 s | Greenfield path, exact schema/WAL and label recovery boundaries remain green | AC-10, AC-17, AC-19 |
| SONARA documentation repeat | `cd docs\dj-track-similarity; npm run check` | Exit 0 | Vale 0 errors/0 warnings/0 suggestions across 109 files; locale parity 54/54; VitePress 1.6.4 build 8.06 s | AC-24 |
| SONARA independent re-review | `/root/sonara_readiness_final_review`, read-only initial and targeted repeat | P0/P1/P2 none after fixes | Reviewer reproduced and then verified closure of stale-catalog preparation, job-start/exclusive TOCTOU, unavailable semantic drift, and active-job 500→409; no files, services or real databases touched | AC-02, AC-15, AC-17, AC-19 |
| SONARA final hygiene | `git diff --check`; no-index checks for three new task files; generated/status/port/process inspection | All clean; zero generated tracked files, unsafe SQLite/audio/log status entries, watched listeners or task processes | Branch `main` remains at `6e431114`; unrelated `.kglite/` and root `PLANS.md` remain untracked and preserved | AC-17, AC-21–AC-23 |
| Simplified SONARA focused backend | `.venv\Scripts\python.exe -m pytest tests\test_analysis_sonara_preflight_v7.py tests\test_analysis_repository_v7.py tests\test_api_runtime_v7.py tests\test_api_analysis_jobs.py --override-ini addopts=` | 86 passed; one external warning; 22.81 s | First/no-result activation, exact-ready no-op, complete Reset → current runtime, and route-level 409/no-mutation coverage for one or all missing active settings with surviving rows; temporary fixtures only | AC-02, AC-03, AC-17, AC-19 |
| Simplified SONARA full backend | `.venv\Scripts\python.exe -m pytest` | Exit 0; 1,110 passed; one external warning; 267.17 s | Final complete root suite after all Reset fail-closed corrections; no real library or audio used | AC-02, AC-10, AC-17, AC-19 |
| Simplified SONARA frontend | `cd frontend; npm run typecheck`; `npm test`; `npm run build` | Exit 0; 162 passed; Vite 7.3.6, 1,734 modules; 2.59 s build | Startup SONARA/Core, locked Core, optional row, ML exclusivity, selection persistence, removed release surface and equal-height count contract | AC-03, AC-15, AC-18 |
| Simplified SONARA docs | `cd docs\dj-track-similarity; npm run check:locales`; `npm run check` | Exit 0; locale parity 54/54; Vale 0 errors/0 warnings; VitePress build complete | README plus affected EN/RU workflow pages describe Analyze missing outputs and Reset → Analyze; prepare CLI remains advanced recovery only | AC-24 |
| Simplified SONARA independent final review | `/root/sonara_simple_workflow_review`, read-only initial and two corrective repeats | No remaining P0/P1/P2 or acceptance gaps | Reviewer verified exact four-setting Reset, zero/all-setting missing fail-closed checks across Core/Artifacts/dependent classifiers, genuine-empty no-op, updated docs and explicitly superseded historical browser evidence | AC-03, AC-15, AC-17, AC-19, AC-24 |

## SQLite query-plan and benchmark evidence

| Query/workflow | Fixture size | Before plan/median | Change | After plan/median | Conclusion |
|---|---:|---|---|---|---|
| Core + Artifacts validation | 6,000 tracks / 6,000 embeddings | Connection pair 5.79 ms median | None; fail-closed validation deliberately retained | Not applicable because the path is unchanged | Safety invariant retained; no optimization claimed |
| Main page summaries | Audit: 5,941 current; implementation: 50,000 tracks / 500 requested | Audit 100: 52.42 ms; 500: 149.84 ms; offset 5000: 147.86 ms. Implementation legacy artifact query: 5.842 ms | ID-driven requested-row joins via `json_each` → integer PK lookup for bounded `<=500`; full summary remains contract-driven | 0.870 ms median over 25 warm runs | Implemented; 85.1% query microbenchmark reduction |
| Main full summary | 5,941 current tracks | 1,477.31 ms median | Decouple from pure page/chunk navigation | Zero summary calls during pure page/chunk continuation; focused hook tests green | Implemented; summary refresh is limited to selection and data-changing events |
| Primary classifier filter | Audit: 1,200 matches; implementation: 50,000 tracks / 500 results | Audit raw count+page 10.81 ms; implementation legacy query 39.776 ms | Drive from existing `idx_classifier_scores_lookup`, reuse joined score; extra filters remain `EXISTS` | 1.005 ms median over 25 warm runs | Implemented; 97.5% query microbenchmark reduction |
| Chunk loading | 5,941 current tracks | 100: 46.20 ms/1 call; 500: 156.03 ms/1; 1000: 306.51 ms/2; All: 2,011.71 ms/12 | Sequential chunks `<=500`; summary excluded; AbortController/request-key/catalog guards; generation-aware dedupe; render window max 120 | Implemented and covered by 11 focused loading/window tests | Bounded requests and bounded DOM now enforced |
| Rhythm Lab connection | 6,000 tracks | 12.59 ms median (same-run cache prototype 14.51 ms) | No cache change in this task | Unchanged fail-closed full validation | Safety retained; cache optimization deliberately not claimed |
| Rhythm Lab track page | 5,941 current tracks | 500 offset 5000: 92.33 ms end-to-end; query-only prototype 26.32 ms | One `COUNT(*) OVER()` query with empty-page fallback | Integrated end-to-end median 93.329 ms over 9 warm runs; query-only prototype 19.59 ms | Query duplication removed; full call remains effectively flat because bundle validation dominates |
| Rhythm Lab prediction page | 12,000 stored revisions / 6,000 latest rows | 500 offset 5000: 288.65 ms end-to-end; query-only prototype 237.87 ms | Evaluate ranked CTE once with `COUNT(*) OVER()` | Integrated end-to-end median 238.254 ms over 9 warm runs; query-only prototype 166.17 ms | Implemented; 17.5% end-to-end reduction on the retained fixture |

## Browser observations

| Surface | Viewport / zoom | Scenario | Result | Console/network evidence | Related AC |
|---|---|---|---|---|---|
| Main UI baseline | Desktop | No backend selected | Safe zero-track surface; top-level tabs lack IDs/controls and arrow-key navigation | Two expected proxy errors because no backend was running | AC-15, AC-20 |
| Main UI baseline | 640 CSS px (200%-zoom equivalent) | No backend selected | No page overflow, but topbar consumes ~400 px and LAB wraps to a second row | Same expected proxy errors | AC-15, AC-20 |
| Main UI final | 1440×900 | Fresh disposable v7 Core+Artifacts catalog with 5,941 tracks | Header converged to `TRACKS 5941`; library showed `1–100 / 5941` and exactly 100 rendered rows; all seven main tabs present | No alert, console warning or console error; no document overflow | AC-01, AC-12, AC-15, AC-20 |
| Main library | 1440×900 | Select 100, 500, 1000 and All | Exact loaded totals 100/500/1000/5941; 500/1000/All retained a 120-row render window | Requests remained successful; no console/API errors | AC-12–AC-14, AC-20 |
| Main library | 1440×900 plus 1,500 ms synthetic request latency | All loading, progress and cancellation | Observed `Загружено 1500 из 5941`; cancellation stopped at `Остановлено 4000 из 5941` | Cancellation produced no rejected-promise or stale-state error | AC-13, AC-20 |
| Main library | 1440×900 plus synthetic latency | Change filter while an All request is active | Old request was cancelled; final state contained only exact `Title 000001`, `1–1 / 1` | No stale rows or console/API error | AC-13, AC-20 |
| Main library | 1440×900 | Switch to an empty bound v7 bundle and back | Empty catalog showed `0 / 0`, explicit empty state and scoped disabled MUQ reason; returning restored 5,941-track state | No identity leak between catalogs and no console/API error | AC-01, AC-05, AC-13, AC-20 |
| Main UI failure state | 1440×900, isolated disposable tab | Browser network forced offline | Visible `Failed to fetch` alert and zero rows; recovery succeeded after network restore | Intentional failure was contained to the isolated tab, which was then closed | AC-07, AC-20 |
| Tab navigation | 1440×900 | ArrowRight/End/Home on main tabs; ArrowRight/ArrowLeft on nested SET tabs | Roving `tabindex` and `aria-selected` moved SONARA→MERT→LAB→SET; nested selection moved Set Builder↔Hybrid without changing outer SET | No errors | AC-07, AC-15, AC-20 |
| SET Builder | 1440×900 | Generate from selected seeds with all default sources | Response showed actual `mert, maest, muq, clap` sources, normalized weights plus SONARA broad and 36/5,941 coverage; `Add preview` added exactly 24 current SET rows | Successful API response; no Hybrid result entered the SET preview | AC-07–AC-09, AC-20 |
| Hybrid Preview | 1440×900 | Generate with five equal sources | Returned 25 rows, all five actual sources, `.20` weights and hashes for CLAP/MAEST/MERT/MuQ/SONARA; no SET `Add preview` action present | Successful API response; independent request/result state | AC-07–AC-09, AC-20 |
| MUQ search | 1440×900 | Generic seed search | Captured `POST /api/search` payload with `analysis_family: "muq"` and ten results | HTTP 200; no navigation, console or API error | AC-04, AC-05, AC-20 |
| Generic search race correction | 929 CSS px, deterministic 1,500 ms responses | Start SONARA then switch to MUQ; complete MUQ, switch to SONARA/back, then add a seed | Late SONARA produced no block/provenance under MUQ; completed result showed `MUQ results 1` and Gamma only under MUQ; seed change cleared it | Clean repeat had 25 successful HTTP request lines, empty development log and no horizontal overflow | AC-02, AC-04, AC-05, AC-15, AC-20 |
| LAB | 1440×900 | Reference Compare and MuQ verdict | Five independent groups (CLAP, MERT, MuQ, MAEST, SONARA), eight candidates each; MuQ notes and Mood verdict stayed attached to the displayed MuQ identity | Successful exact-identity write; no error | AC-04, AC-06, AC-20 |
| Metadata | 1440×900 | Open v7 track detail | Displayed exact file/Mutagen fields, SONARA Core plus timeline/embedding/fingerprint availability, MAEST/MERT/MuQ/CLAP contract details and classifier scores | Successful detail fetch; no fallback legacy fields | AC-01–AC-04, AC-20 |
| Metadata race correction | 929 CSS px, track 1 delayed 1,500 ms | Fire overlapping Alpha then Beta detail clicks | Only `/api/tracks/2` completed after Alpha was aborted; dialog remained Beta after the late window and contained no Alpha data | Empty development log; exact four-field identity tests cover non-abort stale completion | AC-01, AC-02, AC-15, AC-20 |
| Audio Dedup | 1440×900 | Inspect default, pre-MuQ legacy and apply gate | Default MuQ `.12`; pre-MuQ profile removed MuQ and preserved `.43/.32/.04`; apply revealed exact `APPLY DELETE` confirmation and was not started | No job or source-file mutation; dialog closed cleanly | AC-09, AC-11, AC-17, AC-20 |
| Main UI responsive | 640×900 | All main/nested tabs and SET/Hybrid controls | No page overflow; all seven main and two nested tabs remained in DOM; SET/Hybrid source grids were one column with MuQ label/input intact | No console/API error | AC-09, AC-15, AC-20 |
| Main UI effective 200% | 1,280 physical px → 640×450 CSS px, DPR 2 | Hybrid five-source controls | No overflow; one-column source grid; all main/nested tabs and MuQ controls accessible | No console/API error | AC-09, AC-15, AC-20 |
| Standalone Rhythm Lab | 1440×900 | Load disposable bound v7 catalog and training view | Page `1 / 60 (1-100 / 5941)`; coverage SONARA 36, MERT 5941, MAEST 36, CLAP 36, MuQ 36; full `sonara+mert+maest+clap+muq` recipe reported all five required/current | No console warning or error | AC-04, AC-10, AC-20 |
| Standalone Rhythm Lab | 640×900 | Library track statuses and five-source recipe | Per-track SONARA/MERT/MAEST/CLAP/MuQ current/missing statuses remained readable; document width 625 for 640 CSS px | No overflow, console warning or error | AC-10, AC-15, AC-20 |
| Historical SONARA readiness (superseded) | Desktop, existing selected catalog, synthetic read-only status response | This observation described the removed release-card design: initial SONARA/Core were both unchecked; selecting SONARA checked Core and disabled Analyze under `preparation_required` | Retained only as historical evidence for the design that was replaced; no prepare or analysis request was sent and the catalog remained read only | Superseded by the simplified AC-02, AC-15, AC-17, AC-20 workflow |
| Historical SONARA prepare dialog (superseded) | Desktop and 640×900 | This observation described the removed preparation dialog, including focus wrapping and narrow viewport geometry | Retained only as historical evidence for the removed design; the final Prepare action was never invoked | Superseded by the simplified AC-15, AC-17, AC-20 workflow |
| SONARA console correction | Live HMR render after classifier blocker key fix | Repeated identical manifest blockers remained visible without duplicate-key identity | Last log entry after the fix was the expected Vite HMR update; no later React warning/error | AC-15, AC-20 |
| Simplified SONARA controls | Default 1,265 CSS px, Vite-only read-only UI | SONARA initially checked; Core checked+disabled; Timeline/Embedding/Fingerprint share one desktop row; no Active release/Prepare UI | Optional labels share `y=557.43`; release text absent; no warning/error logs | AC-03, AC-15, AC-20 |
| Simplified analysis row geometry | Default 1,265 CSS px | Measure first `analysis-model-name` and `analysis-model-count` after corrective CSS reload | Both `52.1429 px` high at `y=414.2857`; actual outer geometry matches | AC-15, AC-20 |
| Simplified selection state | Default 1,265 CSS px | Select MAEST, return to SONARA, select Timeline, switch to MERT, return to SONARA | ML cleared SONARA and classifiers; return restored SONARA with mandatory Core and preserved Timeline preference; no analysis request sent | AC-03, AC-15, AC-17, AC-20 |
| Simplified SONARA narrow | 640×900 | Inspect optional outputs and overflow | Three optional outputs stack below 720 px; document `625 px` equals viewport `625 px`; no horizontal overflow or release surface | AC-15, AC-20 |

## Remaining Acceptance Criteria

Use stable identifiers `AC-01` … `AC-24` matching `50-ACCEPTANCE.md`.

| ID | Closure evidence | Status |
|---|---|---|
| AC-01 | Exact `TrackSummaryV7`/`TrackDetailV7` client graph, no active `track.id`/`track.path` consumers; 156 frontend tests, typecheck, full backend and clean browser catalog switch/reload | Closed |
| AC-02 | Backend routes/repositories, TypeScript/client signals and exact identities agree; 166 frontend, 1,099 full backend, stale-catalog/job-start races, 409 contention and unavailable semantics are covered | Closed |
| AC-03 | Active SONARA selectors/types/UI use only `core`, `timeline`, `embedding`, `fingerprint`; legacy `representations` is absent from active frontend source | Closed |
| AC-04 | MuQ remains present across every required consumer; focused tests and clean browser race smoke prove generic result provenance is source scoped | Closed |
| AC-05 | Dedicated MUQ tab sends the current contract, labels its results, hides them under other tabs and clears them on request-key changes | Closed |
| AC-06 | MuQ LAB verdict carries exact submitted identities into one atomic guarded upsert; forced generation race returns 409 without feedback | Closed |
| AC-07 | Nested Set Builder/Hybrid tabs have separate payloads, semantics, loading/errors/results/stale guards; keyboard and browser evidence confirms separation | Closed |
| AC-08 | `Add preview` is SET-response keyed only; tests reject stale/MERT/MuQ/SONARA/CLAP/Hybrid provenance and browser added exactly the current 24 SET rows | Closed |
| AC-09 | SET/Hybrid/Dedup expose MuQ, actual backend sources/weights, and tested/browser-verified MuQ-disabled legacy profiles | Closed |
| AC-10 | Standalone UI remains v7/MuQ complete; collection selection uses one exact snapshot, the forced generation race returns 409, and every implicit Lab consumer shares the separate v7 labels path | Closed |
| AC-11 | Audio Dedup tests and browser prove dry-run default, exact `APPLY DELETE`, root/identity/file-state gates and mandatory MERT+MAEST deletion corroboration | Closed |
| AC-12 | Browser exercised 100/500/1000/All with exact totals | Closed |
| AC-13 | Sequential requests are capped at 500; progress/cancel/filter race/catalog/request-key/generation guards covered by tests and throttled browser observations | Closed |
| AC-14 | `libraryWindow` caps rendered rows at 120; browser observed 120 rows for 500/1000/5,941 loaded tracks | Closed |
| AC-15 | Existing desktop/640 px/2×/keyboard evidence plus the simplified SONARA desktop/narrow observations, exact equal-height row measurement, clean provenance and overlapping-detail observations have no overflow or stale content | Closed |
| AC-16 | Disposable 6k/12k SQLite query plans and retained before/after medians document ID-driven hydration, classifier drive and Rhythm Lab prediction improvement | Closed |
| AC-17 | Core 7/Artifacts 1 topology, `muq_embeddings`, catalog identity and indexes remain unchanged; follow-up tests use disposable fixtures and the preserved real Lab file matches its before hash/mtime/size with no sidecars left | Closed |
| AC-18 | Final `npm run typecheck`, 162/162 tests and a 1,734-module production build are green after removing the release-only frontend files | Closed |
| AC-19 | Focused backend 86 passed for the final SONARA lifecycle, including both partial-pointer fail-closed cases; prior integration suites remain recorded, and final full root backend 1,110 passed | Closed |
| AC-20 | Final desktop/narrow main UI, Rhythm Lab, corrective race and simplified SONARA observations are complete; actual name/count geometry matches and the final console is clean | Closed |
| AC-21 | Full tracked `git diff --check` exits 0 and all ten new task files pass `--no-index --check` | Closed |
| AC-22 | Baseline `.kglite`, `PLANS.md`, task-plan files and the 92,725-byte user-added `.omo` draft remain present; no unrelated edit was reverted | Closed |
| AC-23 | `dist/`, docs `site/` and browser state remain ignored/untracked; final ports 5173/8765/8777 are clear, and task cleanup targeted only the verified Vite process tree rather than the pre-existing backend/Rhythm Lab PIDs | Closed |
| AC-24 | Original README, affected EN/RU page pairs and follow-up SONARA/Lab pages remain mirrored; final Vale/locales/VitePress docs gate is green | Closed |

## Blockers

A blocker is valid only when it cannot be safely bypassed in the current task. Include attempts, evidence and the exact required input/permission.

- None.

## Outcomes & Retrospective

Complete only after validation or a genuine blocker.

- Complete. The active React graph now consumes exact v7 summary/detail
  contracts, all required MuQ consumers are present, SET and Hybrid are
  independent, large-library loading is bounded/cancellable/windowed, and
  standalone Rhythm Lab is bound to current Core + Artifacts identity.
- The final review was useful rather than ceremonial: its two P1 and one P2
  findings produced origin-qualified generic results, an atomic
  exact-identity verdict upsert, a one-snapshot collection boundary and guarded
  track details. Forced races, full suites and a clean deterministic browser
  repeat verify those corrections.
- The final SONARA simplification removes release management from the ordinary
  UI. Startup is SONARA plus locked Core; three optional outputs remain
  independent, ML-only work is order-independent, and output preferences survive
  mode switches. First/no-result Analyze records internal v7 identity
  automatically; complete Reset clears rows, dependent scores and active
  pointers so a later version can be analyzed without a preparation dialog.
  Focused tests, 1,110 root tests, 162 frontend tests, mirrored docs and a
  no-write desktop/narrow browser run close the correction.
- The user then authorized direct publication; the completed port was committed
  and pushed to `main` as `6e431114a797824ff71028866dc883d46f832968`.
- The startup follow-up keeps the preserved `rhythm_lab.sqlite` as recovery
  input, uses `rhythm_lab_v7.sqlite` for normal writes, and rejects explicit
  legacy paths before DDL. Standalone and collection paths share an exact
  six-table classifier schema matrix; partial-v7 and closed-writer real-WAL
  regressions are covered. The real legacy file matches its before hash, mtime
  and size; task-created empty WAL/SHM sidecars were removed after exact
  validation. No audio, Core, Artifacts, schema, index, database version,
  migration, training, promotion or scoring changed.
- The follow-up is intentionally uncommitted and unpushed pending separate user
  authorization.

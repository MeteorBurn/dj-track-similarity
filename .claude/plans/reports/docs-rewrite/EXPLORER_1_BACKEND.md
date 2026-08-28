I have everything I need. Here is the report.

---

# Backend Core Report — entry points, HTTP surface, database, jobs, safety

## 1. Entry points and startup

| Entry point | File | What it does |
|---|---|---|
| `dj-sim` console script | `pyproject.toml:68` → `dj_track_similarity.cli:app` | Typer app; sub-apps `eval` and `classifier` registered at `src/dj_track_similarity/cli.py:85-86` |
| `dj-sim serve` | `src/dj_track_similarity/cli.py:1171-1223` | `configure_logging()` → `configure_shared_ffmpeg_runtime()` → optional `LibraryDatabase(db_path)` to resolve the path → `uvicorn.run(create_app(...), host, port, log_config=uvicorn_log_config(level))` |
| `create_app()` | `src/dj_track_similarity/api.py:97-170` | Composition root only |
| `run_server.cmd` | `run_server.cmd:1-185` | Batch wrapper: mode prompt, DB prompt, venv activation, `npm`/`dj-sim` presence checks, LAN IP detection, then `python scripts\run_server_launcher.py %*` |
| `scripts/run_server_launcher.py` | `scripts/run_server_launcher.py:90-123` | Starts Vite child (`npm run dev` / `dev:lan`) with `shell=False`, then runs `dj-sim serve` synchronously; stops the Vite child in `finally` |
| Rhythm Lab child process | `src/dj_track_similarity/rhythm_lab_launcher.py:110-157` | List-based `subprocess.Popen`, `.venv` python, hidden window, log to `logs/rhythm-lab.log` |

### `create_app` order (api.py:107-170)
1. `configure_logging` (api.py:103) and `configure_shared_ffmpeg_runtime` (api.py:104) — **FFmpeg validation happens at app construction, so an invalid runtime fails app creation, not the first decode.**
2. `AppDatabaseState(db_path)` (api.py:107).
3. `FastAPI(title="dj-track-similarity Utility")` (api.py:108) — no version, no custom `openapi_url`.
4. Startup hooks: `install_asyncio_exception_logging`, `install_standard_stream_logging` (api.py:109-110).
5. HTTP middleware logging any response `>= 400` and re-raising crashes (api.py:112-126).
6. Exception handlers: `DatabaseNotSelected → 400`, `DatabaseBusy → 409` (api.py:128-134). These are the *global* mapping; individual routes add their own.
7. Route registration in this order: database, audio-dedup, library, analysis, evaluation, reference-compare, search, server, tags/export, rhythm-lab (api.py:136-161).
8. `register_docs_routes(app, package_path)` (api.py:164).
9. `app.mount("/", StaticFiles(directory=<repo>/frontend/dist, html=True))` **only when `frontend/dist` exists** (api.py:166-168). Mounted last, so it never shadows `/api`.

Static paths are computed from `Path(__file__).resolve().parents[2]` — i.e. the repo root **relative to `src/dj_track_similarity/api.py`**. In a non-editable site-packages install, `frontend/dist` and `docs/.../site` will not be found.

### Shutdown
`POST /api/server/shutdown` requires header `X-DJ-Track-Similarity-Action: shutdown-server`, else `403` (`api_routes_server.py:51-52`). It returns `{"status":"shutdown_requested"}` and schedules a background task that first calls `stop_rhythm_lab()` (failures logged, not fatal) then `os.kill(os.getpid(), signal.SIGTERM)` after 0.25 s (`api_routes_server.py:17-37`).

---

## 2. CLI contract (complete)

Global: Typer defaults only (`--install-completion`, `--show-completion`, `--help`). `_db()` (cli.py:90-106) defaults `--db` to **`dj-track-similarity.sqlite`** in CWD and exits 1 on `OSError/RuntimeError/ValueError`.

### Root commands

| Command | Args / options | Defaults | Effect | Confirmation gate |
|---|---|---|---|---|
| `scan MUSIC_ROOT` (cli.py:770) | `MUSIC_ROOT` (arg), `--db` | db default | `scan_library()` — full walk, `record_library_root`, `mark_unseen_missing`. Prints `added/updated/unchanged/skipped` | none |
| `validate-database` (cli.py:779) | `--db` **required**, `--report PATH` | — | Read-only `DatabaseValidator.run`; prints JSON; **exit 2 when `error_count > 0`**, exit 1 on FileNotFound/sqlite/ValueError | none |
| `migrate-database` (cli.py:794) | `--db` **required**, `--backup-root`, `--confirm` | backup root = `<db>.parent/backups` | Legacy Core+Artifacts → one library; timestamped backup, staged build, count/integrity/FK verification, receipt JSON | **`--confirm 'MIGRATE SINGLE LIBRARY'` or interactive `typer.prompt`** (cli.py:811) |
| `relocate-library OLD NEW` (cli.py:833) | `OLD_ROOT`, `NEW_ROOT` args; `--apply`; `--db` | `--apply` off | Preview or DB-only path rewrite | `--apply` flag only (no phrase) |
| `analyze` (cli.py:859) | see table below | see below | Creates + runs one `AnalysisJobManager` job synchronously with an ASCII progress bar | none |
| `analyze-pipeline` (cli.py:994) | `--stages`, `--ml-models`, `--db`, `--limit`, `--device`, `--track-batch-size`, `--inference-batch-size`, `--sonara-batch-size`, `--sonara-bpm-min`, `--sonara-bpm-max` | `--stages sonara,ml`; `--ml-models maest,mert,muq,mulan,clap`; device `auto`; 8 / 16 / 8; bpm 70 / 180 | Runs `AnalysisPipelineManager` synchronously. Exits 1 if `sonara` appears in `--ml-models` (cli.py:1009-1015) | none |
| `analyze-classifier CLASSIFIER` (cli.py:1050) | `CLASSIFIER` arg; `--db`; `--model PATH`; `--limit` | — | DB-only classifier scoring | none |
| `doctor` (cli.py:1070) | none | — | Prints python/torch/CUDA/nvidia-smi, then FFmpeg dir+version+library paths and PyAV version/module/libavcodec. Returns early when torch missing (never reaches the audio check) | none |
| `text-search QUERY` (cli.py:1116) | `QUERY` arg; `--db`; `--model clap\|mulan`; `--limit 1..500`; `--min-similarity`; `--device` | model `clap`, limit `50`, device `auto` | Embeds one prompt, `SimilaritySearch.search_vector`, prints `score\ttrack_id\ttrack_uuid\tfile_path` | none |
| `serve` (cli.py:1171) | `--host`, `--port`, `--db`, `--log-level`, `--log-track-events` | `127.0.0.1`, `8765`, no DB, `info`, off | Starts Uvicorn | none |

### `dj-sim analyze` full option set (cli.py:859-912)

| Option | Range | Default | Notes |
|---|---|---|---|
| `--db` | path | `dj-track-similarity.sqlite` | |
| `--limit` | int ≥ 0 or None | None (all) | `_normalize_limit` rejects negatives (analysis_config.py:193) |
| `--models` | `maest,mert,muq,mulan,clap` or `sonara` alone | all five ML | SONARA cannot be mixed (analysis_config.py:65-68) |
| `--device` | `auto\|cpu\|cuda` | `auto` | |
| `--top-k` | 1..10 | 3 | |
| `--track-batch-size` | 1..64 | 8 | |
| `--inference-batch-size` | 1..128 | 16 | |
| `--diagnostics` | flag | off | `set_analysis_diagnostics_enabled` |
| `--sonara-batch-size` | 1..16 | 8 | |
| **`--sonara-bpm-min`** | 20.0..400.0 | **70.0** | undocumented |
| **`--sonara-bpm-max`** | 20.0..400.0 | **180.0**, must be ≥ 2×min | undocumented |
| **`--ml-staged`** | flag | off | requires `--ml-staging-path`; exits 1 otherwise (cli.py:918-933) |
| **`--ml-staging-path`** | existing dir | None | |
| **`--ml-copy-workers`** | 1..16 | 4 | |
| **`--ml-decode-workers`** | 1..32 | 8 | |
| **`--ml-stage-size`** | 1..512 | 64 | |

### `dj-sim eval …` (all in cli.py:256-720)

| Command | Key options / defaults |
|---|---|
| `export-candidates` (256) | `--output` req; `--seed-track-id` rep; `--source` rep; `--per-source 10`; `--random-seed 123`; `--record-session/--no-record-session` (default record) |
| `export-weighted-candidates` (292) | `--profile` req; `--output` req; `--seed-sample`; `--seed-track-id` rep; `--sample-count 50`; `--source` rep; `--per-source 30`; `--random-seed 123`; `--rrf-k 60`; `--transition-risk-weight 0.0` (0..1); `--record-session` default on |
| `export-seed-sample` (346) | `--output` req; `--count 50`; `--random-seed 123`; `--require-complete-analysis/--allow-partial-analysis` |
| `import-pair-feedback` (379) | `--input` req (existing file) |
| `import-transition-feedback` (402) | `--input` req |
| `report` (425) | `--output` req; `--k` rep (default `[5,10,20]`); `--judged-only` |
| `run-ablation` (446) | `--output` req; `--k` rep; `--rrf-k 60`; `--score-profile`; `--judged-only` |
| `build-score-profile` (471) | `--source-profile-report` req; `--output` req; `--name` req; `--rrf-k 60` (**accepted but unused** — `_ = rrf_k` at cli.py:480) |
| `run-calibration` (491) | `--output` req; `--score-mode rrf`; `--bins 10`; `--min-samples 30`; `--accepted-threshold 2` (0..3); `--rrf-k 60`; `--judged-only`; `--record/--no-record` |
| `optimize-score-profile` (536) | `--output` optional; `--profile-name weighted_candidates_judged_v1`; `--objective balanced`; `--split-by seed`; `--min-judged-pairs 200`; `--rrf-k 60`; `--k` rep (default `[10]`); `--random-seed 123`; `--grid-step 0.25` (0.01..1); `--bootstrap-samples 30`; `--record/--no-record`; `--save-profile/--no-save-profile` |
| `profile-sources` (612) | `--output` req; `--profile-output`; `--profile-name auto-source-profile`; `--seed-sample`; `--source` rep; `--sample-count 50`; `--per-source 30`; `--top-k` rep; `--random-seed 123` |
| `apply-score-profile` (658) | `--profile` req; `--output` req; `--k` rep; `--rrf-k 60` |
| `sweep-risk-penalty` (682) | `--profile` req; `--output` req; `--weight` rep; `--k` rep; `--rrf-k 60`; `--transition-risk-version v2` |

### `dj-sim classifier …`

| Command | Options |
|---|---|
| `calibration-report` (cli.py:723) | `--classifier` req; `--db`; `--output` (omit → print JSON); `--min-feedback 30` |
| `suggest-labels` (cli.py:747) | `--classifier` req; `--mode uncertainty`; `--db`; `--limit 25` (1..500); `--random-seed 123`; `--output` |

---

## 3. HTTP API inventory (complete)

76 JSON routes + 2 static mounts. Global handlers: `DatabaseNotSelected → 400`, `DatabaseBusy → 409` (api.py:128-134).

### Database — `api_routes_database.py`
| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| GET | `/api/database/current` | – | `DatabaseStateResponse` | `{path, evaluation_path, catalog_uuid, selected}` (:18) |
| POST | `/api/database/switch` | `DatabaseSwitchRequest{path}` | `DatabaseStateResponse` | 400 ValueError, 409 busy (:22) |
| POST | `/api/database/dialog` | – | `DatabaseStateResponse` | Tk save-dialog; 503 when Tk unavailable; cancel returns current (:31) |
| POST | `/api/database/validation/jobs` | – | `DatabaseValidationJobStatus` | 409 if one already runs (:46) |
| GET | `/api/database/validation/jobs/latest` | – | status or `null` | (:54) |
| GET | `/api/database/validation/jobs/{job_id}` | – | status | 404 (:58) |
| POST | `/api/database/validation/jobs/{job_id}/cancel` | – | status | 404 (:65) |

### Library / media — `api_routes_library.py`
| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| POST | `/api/library/scan` | `ScanRequest` | `ScanJobStatus` | 400 on missing/not-a-dir root (:40) |
| POST | `/api/library/tags/refresh` | `TagRefreshRequest{workers 1..64=8}` | `ScanJobStatus` | (:55) |
| POST | `/api/library/relocate` | `RelocateLibraryRequest{old_root,new_root,apply}` | `RelocationResult` dict | Preview uses `require_db`; apply uses `exclusive_db` (:60-74) |
| POST | `/api/database/clear` | – | `ClearLibraryResponse` | Registered in the **library** module, not the database module (:78) |
| GET | `/api/library/scan/jobs/latest` | – | status or `null` | (:86) |
| GET | `/api/library/scan/jobs/{job_id}` | – | status | 404 (:90) |
| POST | `/api/library/scan/jobs/{job_id}/cancel` | – | status | 404 (:97) |
| GET | `/api/tracks` | query `q`, `preset=all\|syncopated`, `liked`, `search_mode=like\|fts`, `classifier_min_scores` (JSON string), `limit 1..500=100`, `offset ≥0` | `TrackPageResponse` | `classifier_min_scores` must be a JSON object of 0..1 floats else **422** (`api_route_utils.py:36-48`) (:104) |
| POST | `/api/tracks/{track_id}/liked` | `TrackLikedRequest{catalog_uuid,track_uuid,liked}` | `TrackSummaryResponse` | Identity mismatch raises **RuntimeError → 409** (never 404) (`db_library_queries.py:1451`) |
| DELETE | `/api/tracks/{track_id}` | `TrackDeleteRequest{catalog_uuid,track_uuid}` | `TrackDeleteResponse` | `exclusive_db`; FK cascade + FTS delete + evaluation sidecar purge (:148) |
| GET | `/api/tracks/{track_id}` | – | `TrackDetailResponse` | 404 (:165) |
| POST | `/api/tracks/{track_id}/reveal` | – | `{"path": str}` | Spawns `explorer.exe /select,"<path>"` with `shell=False`; 404 missing file, 503 OSError (:178; api.py:91-94) |
| POST | `/api/tracks/filtered` | `FilteredTracksRequest` | `list[TrackSummaryResponse]` | Unbounded row count (:195) |
| GET | `/api/library/summary` | – | `LibrarySummaryResponse` | includes `sonara_bpm_min/max` (:209) |
| GET | `/media/{track_id}` | – | `FileResponse` | Transcodes to a temp WAV for the formats in `BROWSER_PREVIEW_TRANSCODE_SUFFIXES`; 404 / 422 (:213) |

### Analysis & classifiers — `api_routes_analysis.py`
| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| POST | `/api/analysis/reset` | `AnalysisResetRequest{analysis_family}` | `AnalysisResetResponse` | `exclusive_db`; family→outputs map at :333-347 |
| POST | `/api/analysis/jobs` | `AnalysisJobRequest` | `AnalysisJobStatus` | 400 config error, 409 busy (:49) |
| GET | `/api/classifiers` | – | `list[dict]` with `scored_tracks` | Works with no DB selected (returns profiles only) (:87-104) |
| POST | `/api/classifiers/{key}/analyze` | `ClassifierAnalyzeRequest{limit}` | `ClassifierJobStatus` | 400 for unknown / manifest-incompatible key (:106) |
| POST | `/api/analysis/pipelines` | `AnalysisPipelineRequest` | `AnalysisPipelineStatus` | Validates SONARA range **before** queueing (:148) |
| GET | `/api/analysis/pipelines/latest` | – | status or `null` | (:228) |
| GET | `/api/analysis/pipelines/{job_id}` | – | status | 404 (:232) |
| POST | `/api/analysis/pipelines/{job_id}/cancel` | – | status | 404 (:239) |
| GET | `/api/classifiers/{key}/calibration-report` | – | report dict | 400 unknown key (:246) |
| GET | `/api/classifiers/{key}/label-suggestions` | query `mode=uncertainty`, `limit 1..500=25`, `random_seed=123` | report dict | (:255) |
| POST | `/api/classifiers/reset` | `ClassifierResetRequest{classifier_key}` | `AnalysisResetResponse` | `exclusive_db` (:276) |
| GET | `/api/classifiers/{key}/analyze/jobs/latest` | – | status or `null` | filtered by classifier (:286) |
| GET | `/api/classifiers/{key}/analyze/jobs/{job_id}` | – | status | 404 (:290) |
| POST | `/api/classifiers/{key}/analyze/jobs/{job_id}/cancel` | – | status | 404 (:297) |
| GET | `/api/analysis/jobs/latest` | – | status or `null` | (:304) |
| GET | `/api/analysis/jobs/{job_id}` | – | status | 404 (:308) |
| POST | `/api/analysis/jobs/{job_id}/cancel` | – | status | 404 (:315) |
| GET | `/api/analysis/sonara/status` | – | `SonaraStatusResponse` | core / embedding / fingerprint present+missing counts (:322) |

### Evaluation — `api_routes_evaluation.py` (entirely undocumented in `reference/api.md`)
| Method | Path | Request | Notes |
|---|---|---|---|
| GET | `/api/evaluation/summary` | – | `{counts:{pair_feedback, transition_feedback, evaluation_profiles, search_sessions, search_session_seeds, search_result_events, calibration_runs}}`; sidecar tables report `0` when absent (:35; `db_evaluation.py:261-298`) |
| POST | `/api/evaluation/feedback/pair` | `EvaluationPairFeedbackRequest` | 1..5 unique seeds, `rating 0..3`, closed `reason_tags` vocabulary (`api_schemas.py:36-50`) |
| POST | `/api/evaluation/feedback/transition` | `EvaluationTransitionFeedbackRequest` | free-form `risk_tags` |
| POST | `/api/evaluation/run/source-profile` | `EvaluationSourceProfileRunRequest` | returns `{source_profile, score_profile}` |
| POST | `/api/evaluation/run/apply-score-profile` | `EvaluationApplyScoreProfileRequest` | exactly one of `profile` / `weights` |
| POST | `/api/evaluation/run/weighted-candidates` | `EvaluationWeightedCandidatesRunRequest` | `limit_per_seed 1..100=30`; `record_session` default **false** |
| GET | `/api/evaluation/reports/latest` | – | last 10 `calibration_runs`, or `{"status":"no_persisted_reports"}` |

Any `RuntimeError`/`sqlite3.OperationalError` in this group becomes `409 "Evaluation API requires the current SQLite structure. …"` (:273-277).

### Search — `api_routes_search.py`
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/api/search` | `SearchRequest{analysis_family=mert, seed_track_ids 1..5 unique, limit 1..500=10, min_similarity, epsilon ≥0, noise 0..1=0}` | `list[SimilaritySearchResultResponse]` (:87) |
| POST | `/api/search/random-track` | `EmbeddingRandomTrackRequest{analysis_family, exclude_track_ids}` | `TrackSummaryResponse` (:121) |
| POST | `/api/search/sonara` | `SonaraSearchRequest{seed_track_ids, limit, mode=balanced\|vibe\|sound\|dj_transition\|custom, min_similarity, mixer_weights, modifiers}` | `list[SimilaritySearchResultResponse]` (:148) |
| POST | `/api/search/sonara/random-track` | `SonaraRandomTrackRequest` | `TrackSummaryResponse` (:172) |
| POST | `/api/search/text` | `TextSearchRequest` | `list[SimilaritySearchResultResponse]` (:191) |
| POST | `/api/search/text/warmup` | `TextSearchWarmupRequest{analysis_family, device}` | `TextSearchWarmupResponse{analysis_family, device, seconds}` — **touches no database** (:221) |
| POST | `/api/search/text/feedback` | `TextSearchFeedbackRequest{track_uuid, preset_keys, analysis_family, verdict ∈ {-1,0,1}}` | `TextSearchFeedbackResponse{presets, verdict}` (:250) |

`SonaraMixerWeights` defaults: `timbre 1.0, rhythm 1.0, dynamics 0.8, harmonic 0.8, tempo 0.35`, each 0..5 (`api_schemas.py:316-322`). `SonaraModifiers` are nine fields each `-1..1` default `0.0` (`api_schemas.py:324-333`).

Every result-returning search re-validates `catalog_uuid`+`track_uuid` against fresh summaries and raises `RuntimeError → 409` on staleness (`api_routes_search.py:333-341`).

### Reference Compare — `api_routes_reference_compare.py`
| Method | Path | Request | Notes |
|---|---|---|---|
| POST | `/api/reference/compare` | `ReferenceCompareRequest{seed_track_id, models (default all six, unique, 1..6), limit 1..100=10}` | 400 only (:18) |
| POST | `/api/reference/compare/verdict` | `ReferenceCompareVerdictRequest{seed, candidate, model, verdict, notes}` | 404/409/400 (:32) |

### Tags / export / dialog — `api_routes_tags_export.py`
| Method | Path | Request | Notes |
|---|---|---|---|
| POST | `/api/export` | `ExportRequest{name, track_ids, output_dir, format=m3u\|csv}` | `{"path": str}`; unknown IDs → 404 (`db_library_queries.py:1604-1608`) |
| POST | `/api/tags/genres/apply` | `GenreTagRequest` (empty, `extra=forbid`) | Synchronous; `exclusive_db`; **writes audio files** (:34) |
| POST | `/api/tags/genres/jobs` | `GenreTagRequest` | Background job; **writes audio files** (:59) |
| GET | `/api/tags/genres/jobs/latest` | – | (:64) |
| GET | `/api/tags/genres/jobs/{job_id}` | – | 404 (:68) |
| POST | `/api/tags/genres/jobs/{job_id}/cancel` | – | 404 (:75) |
| POST | `/api/dialog/folder` | – | `{"path": str\|null}`; 503 without Tk (:82) |

### Rhythm Lab — `api_routes_rhythm_lab.py`
| Method | Path | Request | Notes |
|---|---|---|---|
| GET | `/api/rhythm-lab/status` | – | `{running, managed, url, source}` (:53) |
| POST | `/api/rhythm-lab/launch` | – | Binds current DB + `catalog_uuid`; 503 on RuntimeError (:57) |
| POST | `/api/rhythm-lab/collections` | `RhythmLabCollectionSaveRequest{name, tracks[≥1 unique], source="main_ui_playlist", note, mode=append\|replace}` | 404/400/409 (:71) |

### Audio Dedup — `api_routes_audio_dedup.py`
| Method | Path | Request | Notes |
|---|---|---|---|
| POST | `/api/audio-dedup/jobs` | `AudioDedupScanRequest` | 400 invalid preset/source/weight; 409 if a scan runs (`audio_dedup_jobs.py:141-143`) |
| GET | `/api/audio-dedup/jobs/latest` | – | (:45) |
| GET | `/api/audio-dedup/jobs/{job_id}` | – | 404 (:49) |
| POST | `/api/audio-dedup/jobs/{job_id}/cancel` | – | Sets a `threading.Event` read by the core (:56) |
| GET | `/api/audio-dedup/reports` | – | Directory listing (:63) |
| GET | `/api/audio-dedup/reports/{report_id}` | – | 404/400 (:67) |
| GET | `/api/audio-dedup/reports/{report_id}/groups` | query `offset`, `limit` (clamped 1..200, default 25 — `audio_dedup_reports.py:28,29,251`), `confidence` (repeatable), `min_fingerprint`, `fake_bitrate_only`, `path_contains` | (:77) |
| GET | `/api/audio-dedup/reports/{report_id}/xlsx` | – | `FileResponse` xlsx (:106) |
| POST | `/api/audio-dedup/reports/{report_id}/delete` | `AudioDedupDeleteRequest{selections, deletion_mode=trash\|permanent, confirmation}` | **`confirmation` must equal `"APPLY DELETE"` exactly** (:20, :123); track/group membership validated (:179-209); report DB path must match the open DB (:212-222); runs under `exclusive_db` |

### Static / docs
| Path | Notes |
|---|---|
| `/docs` + `/docs/{path}` | `StaticFiles` mount when `docs/dj-track-similarity/site` exists; otherwise a `503` HTML page (`api_routes_docs.py:11-37`) |
| `/` | `StaticFiles(frontend/dist, html=True)` when present (`api.py:166-168`) |

---

## 4. Database model

### Single-file library — actual table inventory (`db_ddl.py:373-392`, emission order)

| # | Table | Key columns / constraints |
|---|---|---|
| 1 | `library` | `singleton_id=1`, `catalog_uuid UNIQUE`, `created_at`, `updated_at`, `schema_version INTEGER CHECK(=1)`, `roots_json` (JSON array) — db_ddl.py:37-47 |
| 2 | `tracks` | `track_id AUTOINCREMENT`, `track_uuid UNIQUE`, `file_path UNIQUE`, `file_size_bytes`, `file_modified_ns`, `audio_format`, `sample_rate_hz`, `channel_count`, `bit_rate_bps`, `bit_depth`, `audio_duration_seconds` (must equal `round(x,2)`), `last_scanned_at`, `missing_since`, `created_at`, `updated_at`; partial index on `missing_since` — db_ddl.py:49-74. **There is no `content_generation` column.** |
| 3 | `tags` | PK=`track_id`; `title, artist, album, track_number, label, country, year, tag_key, tag_bpm, comment, genres_json, tags_read_at` — db_ddl.py:76-93 |
| 4 | `sonara_features` | PK=`track_id`; ~60 scalar columns + three NOT NULL BLOBs `mfcc_mean_blob (13×4)`, `chroma_mean_blob (12×4)`, `spectral_contrast_mean_blob (7×4)`; provenance `analysis_schema_version`, `bpm_min`, `bpm_max CHECK(bpm_max >= 2*bpm_min)`, `analyzed_at` — db_ddl.py:95-175 |
| 5 | `sonara_embeddings` | PK=`track_id`; `track_uuid`, `dim CHECK(=48)`, `normalization CHECK(='none')`, `embedding_blob CHECK(len=192)`, `analyzed_at` — db_ddl.py:177-187 |
| 6 | `sonara_fingerprints` | PK=`track_id`; `track_uuid`, `fingerprint_version>0`, `fingerprint_base64`, `analyzed_at` — db_ddl.py:189-198 |
| 7 | `maest_genres` | PK=`track_id`; `syncopated_rhythm 0/1/NULL`, `genres_json` array, `analyzed_at` — db_ddl.py:200-207 |
| 8-12 | `maest_embeddings`, `mert_embeddings`, `muq_embeddings`, `mulan_embeddings`, `clap_embeddings` | Identical shape: PK=`track_id`, `track_uuid`, `dim>0`, `normalization IN ('none','l2')`, `embedding_blob CHECK(len = dim*4)`, `analyzed_at`, index on `track_uuid` — db_ddl.py:209-267 |
| 13 | `classifier_scores` | PK=`(track_id, classifier_key)`; `track_uuid, feature_set, feature_names_json, positive_label, predicted_class, score_bucket IN (low,medium,high), score 0..1, confidence 0..1, probabilities_json, analyzed_at`; index `(classifier_key, score DESC, track_id)` — db_ddl.py:269-286 |
| 14 | `likes` | PK=`track_id`, `liked_at` — db_ddl.py:288-294 |
| 15 | `pair_feedback` | `feedback_id`, `seed_track_id`, `candidate_track_id`, `rating 0..3`, `reason_tags_json`, `notes`, `source`, `created_at`, `updated_at`, `UNIQUE(seed,candidate,source)` — db_ddl.py:296-311 |
| 16 | `transition_feedback` | `transition_feedback_id`, `outgoing_track_id`, `incoming_track_id`, `rating 0..3`, `risk_tags_json`, `notes`, `source='manual'`, `created_at` — db_ddl.py:313-326 |
| 17 | **`text_preset_feedback`** | PK=`(track_id, preset_key, analysis_family)`; `analysis_family IN ('clap','mulan')`, `verdict IN (-1,1)`, `created_at`, `updated_at`. Emitted with `IF NOT EXISTS`, and additively re-created on the first verdict write (`db_evaluation.py:81-82`) — db_ddl.py:333-352 |
| 18 | `track_search_fts` | FTS5 virtual table, `tokenize='unicode61'`, columns `track_id UNINDEXED, file_path, title, artist, album, comment, label, country, year, track_number, file_genres, maest_genres` — db_ddl.py:354-370 |

Every derived table references `tracks(track_id) ON DELETE CASCADE`.

### Evaluation sidecar (`db_evaluation_sidecar.py`)
Path is `<library-stem>.evaluation.sqlite` beside the library (`db_storage.py:16-27`). Tables: `evaluation_profiles`, `search_sessions`, `search_session_seeds`, `search_result_events`, `calibration_runs` (:21-79). It is created only with `create=True` under a cross-process file lock (:105-124); reads return `None` when absent. Rows name a track but cannot FK-reference it, so deletion is manual via `delete_evaluation_track_rows` (:145-163), chunked at 800 ids.

### Connection / locking policy
- Per-resolved-path process-wide `threading.RLock` registry, `write_lock_for_path` (`db_connection.py:19-39`). `LibraryDatabase` holds one (`database.py:39`) and takes it around every write.
- `:memory:` and `file::memory:` are rejected (`db_connection.py:27-28`).
- Existing DBs open as `file:...?mode=rw` with `timeout=30 s` (`db_connection.py:124-128`, `SQLITE_BUSY_TIMEOUT_SECONDS = 30` at `db_schema.py:11`).
- Every connection sets `busy_timeout=30000`, `foreign_keys=ON`, `synchronous=NORMAL`, `temp_store=MEMORY`, `cache_size=-32768` (`db_connection.py:137-143`).
- WAL is **enforced**, not merely requested: a non-WAL journal mode raises (`db_connection.py:146-152`).
- Fresh creation is staged (`.<name>.<hex>.create.tmp`), integrity-checked, then `os.replace`d, guarded by a crash-releasing OS file lock `.<name>.create.lock` (msvcrt on Windows, fcntl elsewhere) — `db_connection.py:96-118, 155-233`.
- Open-time validation checks **only** the singleton `library` identity row; it deliberately does not maintain a table/column allow-list (`db_schema.py:48-76`).
- `PRAGMA user_version` is a **write generation counter**, bumped inside every embedding-writing transaction, used to date the in-process library-vector cache (`db_analysis.py:540-560, 563-615`). It is not a schema version.

### Migration (`db_migration.py`)
`migrate_legacy_library_database` requires the exact phrase `MIGRATE SINGLE LIBRARY` (:25, :73-78). It:
1. Requires `<db>` and `<stem>.artifacts<suffix>` to exist (:79-83).
2. Reserves both with `PRAGMA locking_mode = EXCLUSIVE` + `BEGIN EXCLUSIVE`; a busy DB fails with "stop the server and all database tools" (:236-268).
3. Checks matching catalog UUIDs, `integrity_check`, `foreign_key_check` (:100-105).
4. Refuses any non-empty legacy table with no destination (:317-367). `library_settings` is the one recorded exclusion ("obsolete derived counters").
5. Infers roots by drive-grouped `commonpath` (:370-383).
6. Backs both files up into `<backup-root>/<UTC-timestamp>-single-library-migration/` (default `<db>.parent/backups`) (:224-232).
7. Builds a staged DB, copies 13 tables (`_COPY_TABLES` :28-42), rebuilds FTS, compares source vs. target row counts, checkpoints and switches to `journal_mode=DELETE` (:407-507).
8. Moves the legacy pair (+`-wal`/`-shm`) aside, publishes the staged file, re-validates, and restores everything on any failure (:140-182).
9. Writes `migration-receipt.json` (:586-609).

`_COPY_TABLES` does **not** include `sonara_embeddings`, `sonara_fingerprints`, or `text_preset_feedback` — the legacy layout had none, so they start empty and are refilled by reanalysis.

### Write-boundary details worth documenting
- `clear_library` (`db_tracks.py:1275-1333`): deletes `track_search_fts` and `tracks` (cascade does the rest) and resets `roots_json` to `[]`. Its returned counters are computed **only** over `_DERIVED_TRACK_TABLES` = `sonara_features, maest_genres, classifier_scores, maest_embeddings, mert_embeddings, muq_embeddings, mulan_embeddings, clap_embeddings` (`db_tracks.py:35-51`). SONARA embedding/fingerprint, likes, and feedback rows are also removed by cascade but are **not counted**.
- `delete_track` (`db_tracks.py:1462-1495`): identity-checked, transactional, then purges evaluation sidecar rows outside the transaction.
- `remove_deleted_track` (`db_tracks.py:1335-1460`): used by Audio Dedup; **refuses to remove a row while the file still exists on disk** (:1363-1366, re-checked at :1403).
- `relocate_library` (`db_tracks.py:1117-1273`): apply rewrites `tracks.file_path` in two passes through temporary unique paths to avoid UNIQUE collisions, updates FTS, and rewrites matching `library.roots_json` entries. It never touches audio.
- `reset_analysis_outputs` (`db_analysis.py:1369-1419`): deletes whole tables per requested output and **always returns `classifier_rows_deleted = 0`** (hard-coded at :1408).

---

## 5. Job orchestration and lifecycle

### Shared plumbing
`JobStore` (`job_runtime.py:14-70`) — a dict keyed by job id, a `threading.Lock`, `copy_status` on every read, and an event ring capped at `MAX_JOB_EVENTS = 200`. **Jobs are never evicted**; the store grows for the process lifetime. `latest()` returns the last inserted job.

`AnalysisStageQueue` (`analysis_queue.py:12-33`) — one daemon thread with an unbounded `queue.Queue`. Shared by `AnalysisJobManager` and `ClassifierJobManager` (created together in `AppDatabaseState.switch`, `api_state.py:73-79`), so **SONARA, ML and classifier stages are strictly serialized**.

`AppDatabaseState` concurrency contract (`api_state.py`):
- `require_db()` → `DatabaseNotSelected` (400).
- `require_idle_db(op)` → `DatabaseBusy` when any manager's `latest()` is `queued`/`running` (:103-112, :192-208).
- `exclusive_db(op)` context manager sets `_exclusive_operation`, blocking DB switch and job starts (:114-133).
- `job_start()` holds the RLock across manager lookup + `start()` to close a check-then-act race (:135-146).

### `AnalysisJobManager` (`analysis_jobs.py`)
- **BPM range binding**: `resolve_sonara_range` (:194-230). Empty library → requested/default. One stored pair → the request must match it exactly, else `ValueError` telling the user to reset SONARA. More than one stored pair → hard error.
- `create_job` builds a validated `AnalysisJobConfig`, rejects ML when no track has current SONARA (`require_current_sonara`, :271-275), assigns a UUID, and emits one "queued" event whose text contains **only** the settings that stage actually uses (:302-338).
- `start()` submits to the stage queue when one exists, else spawns a daemon thread (:370-380).
- `run_job` phases: `preparing` → `warmup` → `analyzing` (`analysis_job_state.py:18`).
  - `_prepare_job` (:457-572): builds runners, validates that each runner's declared family matches, warms up models, registers active outputs, lists candidates, maps candidates→models, and only then sets `status.total` and `model_progress`. **Candidate selection happens after warm-up**, so `total` stays 0 during warm-up.
  - `_warm_up_models` (:574-627): per-model `preflight()` under a per-runner lock, with `preflight_complete` so a resident model is reported as "already resident".
- Batching (:411-426): SONARA staged = one batch of everything; SONARA direct = chunks of `sonara_batch_size`; ML staged = one batch; ML direct = chunks of `track_batch_size`.
- Failure policy (`_run_model_batch` :811-905): a SONARA batch failure **fails the whole job**; an ML batch failure is retried track-by-track, and each track's error is recorded individually.
- Cancellation is cooperative: `cancel()` only sets `cancel_requested` (:1136-1138); the run loop checks it between batches and between models.
- Counting (`analysis_job_state.py:153-176`): a track counts as `analyzed` only when successes ≥ its target model count; any failure counts `failed`; otherwise `skipped`.
- Runner reuse: non-SONARA runners are cached per `(model, device_requested, inference_batch_size, top_k)` for the process lifetime (:791-809). SONARA runners are created fresh per job (:780-789).

### `AnalysisPipelineManager` (`analysis_pipeline.py`)
Parent/child. `PIPELINE_STAGE_ORDER = ("sonara","ml")` is fixed regardless of request order (:19, :67). Requesting `ml` without `sonara` when no current SONARA rows exist is rejected at create time (:73-81). Cancelling propagates to the running child (:183-200).

### `ScanJobManager` (`scan_jobs.py`)
- Unlimited scan materializes the whole path list up front; a limited scan keeps discovery lazy and pre-filters already-stored paths (:167-189).
- Metadata reading runs in a `ProcessPoolExecutor` in batches of 64, with at most `workers × 2` batches in flight; **all SQLite writes stay on the parent thread** (:461-549).
- A file whose size/mtime changed between metadata read and write is failed, not written (:622-629).
- `reconcile_missing` (and therefore `mark_unseen_missing`) is enabled **only** for an unlimited scan with the full extension set and no duration bounds (:157-162).
- Tag refresh is a separate job (`create_tag_refresh_job` :256-291) using `ThreadPoolExecutor`.

### `ClassifierJobManager` (`classifier_jobs.py`)
Constructs the scorer (which re-verifies the artifact digest) **before** any mutation (:138-146), preflights that every required analysis output is active (:360-371), pages work with `CLASSIFIER_SCORE_BATCH_SIZE` keyed on `after_track_id`, and writes in batches. `get`/`latest`/`cancel` accept an optional `classifier=` filter (:373-391).

### `AudioDedupJobManager` (`audio_dedup_jobs.py`)
Report-first. Presets/sources/weights are resolved at queue time so a bad value is a request error (:127-136). Only one scan at a time (`_start_lock`, :140-143). Cancellation uses a `threading.Event` polled by the core (:90, :205). Completed status carries `report_id` = the JSON file stem (:240).

### `DatabaseValidationJobManager` (`database_validation_jobs.py`)
Single-flight (:57-64), streams findings through `emit`, ends `completed` / `cancelled` / `failed`. `DatabaseValidator` opens the file read-only (`database_validation.py:84`).

### `GenreTagJobManager` (`tags.py:92-236`)
The one job manager that writes audio. Sequential over `list_genre_tag_candidates()`; each write goes through `apply_self_tag_write` with an expected `TrackFileState`, a write callback, a tag re-read, and a readback verification that the stored genres round-trip (`tags.py:289-301`, `_verify_genre_readback` :360-371).

---

## 6. Runtime, decoding, and file-safety behavior

### FFmpeg discovery (`ffmpeg_runtime.py`)
- Required: FFmpeg **8.1.1** with `avcodec 62, avformat 62, avutil 60, avfilter 11, swresample 6, swscale 9` (:14-22) and PyAV **17.1.0** (:23).
- Order: `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` (hard-fails if set but invalid, :101-108), then each `PATH` entry (:110-116).
- A candidate must contain the complete library set **and** an `ffmpeg`/`ffmpeg.exe` reporting exactly `8.1.1` via `ffmpeg -version` (:119-136, :152-168). Rejected candidates are named in the error.
- On Windows the directory is registered with `os.add_dll_directory` and the handle is kept alive in a module list (:41-42).
- `inspect_audio_runtime` additionally requires PyAV to be imported from inside `sys.prefix` (:52-57) and its `libavcodec` major to be 62 (:65-72).

### Decoding
- Primary: `torchcodec.decoders.AudioDecoder(path, num_channels=1).get_all_samples()`; the result must be 2-D with shape `[1, N]`, `float32`, non-empty, positive sample rate (`audio_loader.py:51-74`).
- Recovery: `shared_ffmpeg_decoder.load_tolerant_mono_audio` via PyAV over the same shared libraries, wrapped back into a tensor (`audio_loader.py:77-81`). **No `ffmpeg.exe` process is started for decoding.**
- Decode failure inside a batch becomes a `DecodeFailure` carried on the item rather than an exception (`analysis_job_batch.py:44-47`), so a bad file does not abort the batch.

### Browser preview (`media_preview.py`)
`requires_browser_preview_transcode` returns true for `.aif .aiff .dff .dsd .dsf .flac .ape .wv .m4b .m4r .tak .tta .wma` and for any `.wav` that is not 16-bit with valid channels/rate (:13-40). Transcoding uses **TorchCodec's `AudioDecoder` + `AudioEncoder`** to a `NamedTemporaryFile` at 44.1 kHz stereo, served with a `BackgroundTask` that unlinks it (:43-63). The source is never rewritten or cached.

### Logging (`logging_config.py`)
- Default file `logs/dj-track-similarity.log`; env overrides `DJ_TRACK_SIMILARITY_LOG`, `DJ_TRACK_SIMILARITY_LOG_LEVEL`, `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS`, `DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS` (:16-19).
- Startup date rollover + 8 MiB `RotatingFileHandler` with `backupCount = 1` (:23-24, :501-516, :518-529).
- `sys.stdout`/`sys.stderr` are wrapped by `StandardStreamLogMirror` and mirrored at INFO; ANSI stripped; weight-loading progress bars and the `transformers` `LOAD REPORT` block are suppressed (:171-277).
- A root-logger `ForeignRecordFileHandler` captures third-party `logging` records while skipping project records (:141-169).
- Uvicorn access records go to a console-only handler so job polling does not fill the file (:287-297, :299-341).

### Scanner file safety (`scanner.py`)
- 14 extensions (:27-42). Names beginning `._` are skipped (:355). Directory walk is name-sorted, depth-first, symlinked directories are not followed, resolved paths are de-duplicated (:342-372).
- Mutagen tag lookup covers exactly: `artist, title, album, genre, year, country, label, track_number, bpm, key, comment` (:60-84).
- An unchanged size/mtime pair deliberately **skips tag decoding** — tag-only edits need Refresh Tags (:148-152).

### Process spawning with `shell=False`
`api.reveal_track_file` (`api.py:94`), `run_server_launcher` (`scripts/run_server_launcher.py:107-116`), Rhythm Lab launch (`rhythm_lab_launcher.py:146`), `taskkill` (`rhythm_lab_launcher.py:448`, `run_server_launcher.py:71`), `netstat` (`rhythm_lab_launcher.py:377`), `powershell.exe Get-CimInstance` (`rhythm_lab_launcher.py:425-431`), `ffmpeg -version` (`ffmpeg_runtime.py:156`), `nvidia-smi` (`runtime.py:81`). All list-based.

`reveal_track_file` builds the command as a **single string** `f'explorer.exe /select,"{path}"'` with `shell=False` (`api.py:94`). On Windows that is passed to `CreateProcess` verbatim, so no shell is involved, but it is the one non-list argument in the codebase.

### SONARA staging ownership (`sonara_staging.py`)
Each run gets `<root>/sonara-stage-<uuid4hex>` with a `.owner` file holding the PID (:93-99). Before creating it, `cleanup_orphaned_sonara_staging` removes directories whose recorded owner process is gone, and `rmdir`s (i.e. only when empty) directories with an unreadable/missing marker (:148-166). A live owner is preserved; a non-empty unmarked directory survives.

---

## 7. Dependency and configuration facts

### `pyproject.toml` (verified)
- `requires-python = ">=3.10"`; version `0.1.0`; build backend setuptools; packages found under `src/`.
- Base deps: `numpy>=1.26,<2.0`, `mutagen>=1.47`, `pydantic>=2`, `typer>=0.12`, `fastapi>=0.115`, `uvicorn>=0.30`, `joblib>=1.3`, `av==17.1.0`, `send2trash>=1.8`.
- Extras — **exactly four**: `sonara` (`sonara==0.3.5`), `ml`, `rhythm-lab` (`scikit-learn>=1.4`), `dev` (`httpx2>=2.0.0`, `pytest>=7.4`, `ruff>=0.8`). **There is no `ann` extra.**
- `ml`: `torch==2.11.0`, `torchaudio==2.11.0`, `torchvision==0.26.0`, TorchCodec via direct `+cu130` wheel URL for cp310/win/AMD64 else `torchcodec==0.16.0`, `nnaudio`, `transformers==5.13.0`, `huggingface-hub==1.22.0`, `laion-clap==1.1.7`, `maest-infer==0.2.0`, `muq==0.1.0`.
- `[tool.uv.sources]` routes `torch`/`torchaudio`/`torchvision` to the explicit index `pytorch-cu130` for `python==3.10 and win32 and AMD64` only.
- Ruff lint select: `["E4","E7","E9","F"]`.
- Pytest: `testpaths=["tests"]`, `addopts="-q"`, markers `ml`, `slow`, `evaluation`.
- `[dependency-groups] dev = ["pytest>=9.1.1"]` — a second, higher pytest floor than the `dev` extra's `>=7.4`.

### Ports / binding
| Service | Value | Source |
|---|---|---|
| Backend | `127.0.0.1:8765` | `cli.py:1173-1174`, `run_server.cmd:5` |
| Vite | `5173` | `run_server.cmd:6` |
| Rhythm Lab | `127.0.0.1:8777` | `rhythm_lab_launcher.py:18-20` |
| LAN mode | backend `0.0.0.0`, Vite `npm run dev:lan` | `run_server.cmd:46-50, 89-99`; `run_server_launcher.py:58` |

### Launcher environment contract
`DJ_TRACK_SIMILARITY_LAUNCHER_HOST`, `_PORT`, `_DATABASE`, `_FRONTEND_DEV`, `_FRONTEND_HOST` (`scripts/run_server_launcher.py:23-27`, set in `run_server.cmd:124-128`). Missing host/port → exit 2. A leading mode alias is stripped before forwarding, then `--host/--port` (and `--db` when the prompt supplied one) are appended (`run_server_launcher.py:37-46`).

### Other constants
- SQLite busy timeout: 30 s (`db_schema.py:11`); sidecar 30 000 ms (`db_evaluation_sidecar.py:18`).
- `MAX_JOB_EVENTS = 200` (`job_runtime.py:11`).
- SONARA defaults: mode `direct`, batch 8, BPM 70-180, bounds 20-400, `bpm_max ≥ 2×bpm_min` (`analysis_config.py:16-33`, `sonara_runtime.py:10-11`).
- `SonaraStagingConfig` defaults: `stage_size 32, copy_workers 16, processes 4, rayon_threads 4, max_native_batch_size 4` (`sonara_staging.py:36-41`). Note the **API schema default for staged `batch_size` is 4** (`api_schemas.py:197`) while the direct default is 8.
- `MLStagingConfig` defaults: `stage_size 64, copy_workers 4, decode_workers 8, inference_batch_size 16, preflight_copy_enabled True, preflight_copy_count 64` (`ml_staging.py:38-46`).
- Embedding dims: MAEST 768, MERT 768, MuQ 1024, MuLan 512, CLAP 512, SONARA 48; all `l2` except SONARA `none` (`analysis_models.py:162-188`).

---

## 8. Architectural observations

**Layering.** Three clean seams: (1) Typer CLI and FastAPI routes are both thin adapters over the same managers; (2) `AppDatabaseState` is the only place that owns manager lifetimes and concurrency; (3) `LibraryDatabase` is a mixin composition (`TrackRepository + AnalysisRepository + SummaryRepository + EvaluationRepository`, `database.py:32-34`) that is the sole SQLite write gateway.

**The composition root is genuinely thin.** `api.py` contains no business logic — only dialogs, `reveal_track_file`, the text-adapter cache wiring, and route registration. Change routing in AGENTS.md matches the code.

**Concurrency model is a single global funnel.** One `AnalysisStageQueue` thread serializes SONARA, ML and classifier work; `_has_active_jobs()` scans *all* managers, so a running Audio Dedup scan blocks a database switch and any analysis start. `exclusive_db` adds a second, stronger gate for clear/delete/reset/relocate-apply/genre-write/dedup-delete. This is simple and safe, but it means one long report blocks unrelated work, and there is no per-manager granularity.

**Identity is the core invariant.** Nearly every mutation and every search result carries `(catalog_uuid, track_id, track_uuid)` and re-checks it against fresh rows before responding or writing (`analysis_models.py:1-7` states the rationale; `api_routes_search.py:323-371`, `db_tracks.py:1469-1483`, `db_analysis.py:205`). A doc reader must understand that a bare `track_id` is never a safe write target.

**Fail-closed startup.** FFmpeg validation, WAL enforcement, and library-identity validation all happen before anything useful runs, and none of them mutates an existing database.

**High-centrality modules.** `api_state.py` (every route touches it), `database.py`/`db_library_queries.py` (1691 lines, all read paths), `analysis_jobs.py` (1252 lines, all analysis paths), `analysis_config.py` (defaults consumed by CLI, schemas, and managers), `job_runtime.py` (all six managers).

**Known rough edges.**
- `JobStore` never evicts jobs; a long-lived server accumulates one status object per job forever.
- `_record_staged_ml_result` (`analysis_jobs.py:928-938`) is an intentional no-op — ML staged mode does not record per-model success/failure, only overall track processing. `model_progress` is therefore not comparable between ML direct and ML staged runs.
- `api_routes_audio_dedup.py:168-176` and `api_routes_reference_compare.py:61-62` contain `_ = handler` lines to silence unused-name warnings — a small style inconsistency versus the other route modules.
- `analysis_config.py` uses `sonara_mode` / staging config while `AnalysisJobRequest` (the plain `/api/analysis/jobs` body) exposes neither, so browser Staged Mode is reachable **only** through `/api/analysis/pipelines`.

---

## 9. DOCUMENTATION FINDINGS

### `docs/dj-track-similarity/reference/commands.md` — **INCOMPLETE**
- `dj-sim analyze` table (lines 80-90) omits **seven real options**: `--sonara-bpm-min` (default 70.0, 20..400), `--sonara-bpm-max` (default 180.0, must be ≥2×min), `--ml-staged`, `--ml-staging-path`, `--ml-copy-workers` (1..16, default 4), `--ml-decode-workers` (1..32, default 8), `--ml-stage-size` (1..512, default 64). Proof: `cli.py:894-912`.
- `dj-sim analyze-pipeline` table (lines 96-105) omits `--sonara-bpm-min` / `--sonara-bpm-max` (`cli.py:1004-1005`).
- Line 21 says the default `--db` is `dj-track-similarity.sqlite` — correct (`cli.py:96`).
- `dj-sim validate-database` (lines 42-49) does not state that it **exits with code 2** when errors are found (`cli.py:788`).
- `dj-sim eval build-score-profile` documents `--rrf-k` as meaningful; the parameter is accepted and discarded (`cli.py:480: _ = rrf_k`).
- Missing entirely from the "standalone maintenance scripts" section: `scripts/text_prompt_benchmark.py`, `scripts/text_fusion_benchmark.py`, `scripts/text_tag_crosscheck.py`, `scripts/prompt_preset_tune.py`, `scripts/clap_checkpoint_embed.py`, `tools/audio-dedup/benchmark_fingerprint_candidates.py`, `tools/audio-dedup/spectral_check_cli.py`.
- Line 307 has a Markdown table defect: `|| --keep-db PATH |` (double leading pipe).
- Line 316 documents the Rhythm Lab default source DB as `C:\db\abstracted.sqlite` — a private local path, which contradicts `developer/index.md`'s own privacy rule. NOT VERIFIED against `rhythm_lab_cli.py` (tools/ is another explorer's area).

### `docs/dj-track-similarity/reference/cli.md` — **SHOULD-BE-DELETED**
Five lines that only redirect to `commands.md` (`reference/cli.md:1-5`), yet it holds its own sidebar slot (`config.mts:20`) and is the link README uses for "CLI reference" (`README.md:517`). It also claims coverage of "Audio Online", which `commands.md` does document. Either fold it into `commands.md` and repoint README + sidebar, or give it real content. As written it is a redirect page occupying primary IA.

### `docs/dj-track-similarity/reference/api.md` — **INCOMPLETE and WRONG in two places**

Wrong:
1. Line 180: "SONARA removes only dependent classifier rows". **False.** `reset_analysis_outputs` sets `classifier_deleted = 0` unconditionally and never touches `classifier_scores` (`db_analysis.py:1408, 1415-1419`). `/api/analysis/reset` always returns `classifier_rows_deleted: 0`.
2. Line 122: "Standalone SONARA runs in Direct Mode" — true for `/api/analysis/jobs`, but the page never says that Staged Mode is reachable only through `/api/analysis/pipelines`, and lines 156-163 imply the reverse ("ML models do not use this staging configuration") without mentioning that ML has **its own** staged block.

Missing endpoints (29 of the 76 routes are absent):
- `/api/database/validation/jobs` (POST), `…/latest`, `…/{job_id}`, `…/{job_id}/cancel` — `api_routes_database.py:46-70`.
- `/api/library/scan/jobs/latest`, `…/{job_id}`, `…/{job_id}/cancel` — `api_routes_library.py:86-102`.
- `POST /api/tracks/{track_id}/reveal` — `api_routes_library.py:178`.
- `POST /api/search/random-track`, `POST /api/search/sonara/random-track`, `POST /api/search/text/warmup`, `POST /api/search/text/feedback` — `api_routes_search.py:121, 172, 221, 250`.
- `GET /api/classifiers/{key}/calibration-report`, `GET /api/classifiers/{key}/label-suggestions`, `GET /api/classifiers/{key}/analyze/jobs/latest`, `GET …/{job_id}`, `POST …/{job_id}/cancel` — `api_routes_analysis.py:246, 255, 286, 290, 297`.
- The **entire Evaluation group** (7 routes) — `api_routes_evaluation.py:35-199`.
- The `/docs` mount and its 503 fallback — `api_routes_docs.py:11-37`.

Missing payload facts:
- `AnalysisJobRequest` also accepts `sonara_bpm_min` / `sonara_bpm_max` (`api_schemas.py:175-184`); line 119-121 omits them.
- `POST /api/search` also accepts `epsilon` (≥0) and `noise` (0..1), and enforces 1..5 **unique** seeds (`api_schemas.py:286-300`).
- `POST /api/search/sonara` request shape (`mode`, `mixer_weights` with its five named weights and defaults, `modifiers` with its nine `-1..1` fields) is undocumented (`api_schemas.py:316-352`).
- The ML pipeline staged block (`ml.mode`, `ml.staged.{folder,copy_workers,decode_workers,stage_size,inference_batch_size,preflight_copy_enabled,preflight_copy_count}`) is undocumented (`api_schemas.py:223-262`).
- `LibrarySummaryResponse` also returns `sonara_bpm_min` / `sonara_bpm_max` (`api_schemas.py:796-797`).
- `classifier_min_scores` on `GET /api/tracks` is a **JSON-object string** and returns **422**, not 400, on a bad value (`api_route_utils.py:36-48`).
- `POST /api/tracks/{track_id}/liked` with a mismatched identity returns **409**, not 404 (`db_library_queries.py:1451-1454`).

### `docs/dj-track-similarity/reference/database.md` — **INCOMPLETE, one WRONG claim**
- Line 33: "`tracks`: … plus technical facts, scan state, **and current content generation**." There is no content-generation column; the content facts are `file_size_bytes` and `file_modified_ns` (`db_ddl.py:49-72`; `rg content_generation src/` returns nothing).
- The "Library tables" list omits **`text_preset_feedback`** entirely (`db_ddl.py:333-352`), including the fact that it is created lazily with `IF NOT EXISTS` on the first verdict write (`db_evaluation.py:81-82`) — the one place in the codebase where a table appears in an existing library at runtime. This is precisely the kind of thing a database reference must state.
- The migration paragraph does not say that `sonara_embeddings`, `sonara_fingerprints`, and `text_preset_feedback` are **not** copied (they have no legacy source): `_COPY_TABLES` at `db_migration.py:28-42`.
- Lines 73-78 do not mention that `clear_library`'s reported counts cover only eight tables (`db_tracks.py:35-51`) and exclude the SONARA embedding/fingerprint, likes and feedback rows the cascade also removes.
- Not stated: WAL is *enforced* (open fails if the DB cannot enter WAL, `db_connection.py:146-152`); busy timeout is 30 s (`db_schema.py:11`); creation is staged + `os.replace` under an OS file lock (`db_connection.py:96-118`).
- Line 25-27 mentions an out-of-CLI one-time `mulan_embeddings` addition. No such code path exists in `src/`. NOT VERIFIED whether it is a manual owner procedure; as written the reader cannot act on it.

### `docs/dj-track-similarity/reference/configuration.md` — **INCOMPLETE, one WRONG row**
- The environment-variable table (lines 8-10) lists **one** variable. Missing, all real: `DJ_TRACK_SIMILARITY_LOG`, `DJ_TRACK_SIMILARITY_LOG_LEVEL`, `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS`, `DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS` (`logging_config.py:16-19`); `DJ_TRACK_SIMILARITY_LAUNCHER_HOST/_PORT/_DATABASE/_FRONTEND_DEV/_FRONTEND_HOST` (`scripts/run_server_launcher.py:23-27`); `RAYON_NUM_THREADS`, which SONARA staging **sets** for its workers (`sonara_staging.py:364`).
- Line 41: "Persistent ANN sidecars | `.dj-track-similarity-indexes/` beside the selected DB by default". **WRONG.** No such path, and no ANN backend, exists anywhere in `src/`. `vector_index.py` contains only `ExactVectorSearchBackend` (`vector_index.py:13, 47-75`); the string `dj-track-similarity-indexes` appears only in `.gitignore`, docs, README, and the Vale vocabulary.
- Not stated: the docs mount lives at `/docs` while VitePress `base` is `/docs/` (`api_routes_docs.py:13`, `config.mts:36`) — correct as built, but the reader has no way to know the two must stay in sync.

### `docs/dj-track-similarity/developer/architecture.md` — **ACCURATE but INCOMPLETE**
Everything checked in the "Code map" matches the code (decode path, staging, pipeline order, fail-closed startup, migration). Missing pieces a developer needs:
- `api_state.py` — the concurrency contract (`DatabaseBusy`, `exclusive_db`, `job_start`) is the single most important backend invariant and is not mentioned at all.
- `job_runtime.JobStore` and the fact that six managers share it, with a 200-event cap and no eviction.
- The `PRAGMA user_version` write-generation counter and the in-process library-vector cache with its 512 MiB budget (`db_analysis.py:537-615`) — a real performance mechanism a reader will otherwise misread as schema versioning.
- `db_library_queries.py` (1691 lines) is the largest read-path module and is not in the code map.
- The Mermaid diagram shows `Lab[Rhythm Lab] --> DB` but not that the backend **launches and stops** the Lab process (`rhythm_lab_launcher.py`).

### `docs/dj-track-similarity/developer/development.md` — **OUTDATED (will fail as written)**
- Line 23: `uv sync --locked --extra sonara --extra ml --extra rhythm-lab --extra dev`. **`uv.lock` is out of sync with `pyproject.toml`**: the lock still records an `ann` extra requiring `hnswlib>=0.8` (`uv.lock:503-506, 545`), while `pyproject.toml:22-46` declares only `sonara`, `ml`, `rhythm-lab`, `dev`. `--locked` verifies the lock against the manifest, so this command is expected to fail with an out-of-date-lockfile error. This is the highest-impact factual defect in the developer docs, and it is repeated in `README.md:371`, `getting-started/install.md:81,123`, and `getting-started/quickstart.md:21`.
- Line 44-45: "run `tools/rhythm-lab/tests` and `scripts/tests` explicitly" — correct, but incomplete: `tools/audio-dedup/tests` and `tools/audio-online/tests` also exist and are not collected by root pytest.
- Not stated: the `dev` extra pins `pytest>=7.4` while `[dependency-groups].dev` pins `pytest>=9.1.1` (`pyproject.toml:43, 85`), so `pip install -e ".[dev]"` and `uv sync` can land on different pytest majors.

### `docs/dj-track-similarity/developer/index.md` — **ACCURATE**
Four links, all targets exist. No factual claims to check.

### `docs/dj-track-similarity/developer/release-checklist.md` — **INCOMPLETE**
- Line 9 "API docs mention active endpoints only" is the right instinct but the inverse defect (29 missing endpoints) is what actually happened; the checklist needs a "every registered route appears in `reference/api.md`" item.
- No item covers CLI option drift (7 `analyze` options missing) or lock/manifest agreement — both currently broken.
- No item covers env-var drift.

### `docs/dj-track-similarity/getting-started/install.md` — **WRONG in two places**
1. Lines 114-118: `python -m pip install -e ".[ann,dev]"` for "optional ANN support". **There is no `ann` extra in `pyproject.toml`** (`pyproject.toml:22-46`); pip will warn/fail on the unknown extra, and nothing in `src/` consumes ANN. Delete this section.
2. Lines 81 and 123: `uv sync --locked …` — same stale-lock problem described above.
- Line 71-73 lists base dependencies but omits `send2trash>=1.8` (`pyproject.toml:19`).
- Lines 84-95 state SONARA `0.3.5`; that matches `pyproject.toml:24` and `uv.lock:2578-2579`, and therefore **contradicts README.md:167** which says "SONARA 0.3.6". The code is right; README is wrong.

### `docs/dj-track-similarity/getting-started/quickstart.md` — **OUTDATED (one command), otherwise ACCURATE**
- Line 21: `uv sync --locked --extra sonara --extra ml --extra dev` — stale-lock problem.
- Extension list (line 37) matches `SUPPORTED_AUDIO_EXTENSIONS` exactly (`scanner.py:27-42`). Launcher prompts, power-button shutdown, and `--db`-omitted behavior all match the code.
- Line 65-66: "In the browser, **Analyze limit** `0` means the same whole-eligible-library thing." NOT VERIFIED here (frontend), but the backend accepts `limit: null` and `_normalize_limit` accepts `0` as a distinct value meaning "zero candidates" (`analysis_config.py:193-201`) — a `0` sent literally to `/api/analysis/jobs` would select nothing. If the frontend maps `0 → null` this is fine; the doc should say which.

### `docs/dj-track-similarity/getting-started/first-library.md` — **WRONG in one place, otherwise ACCURATE**
- Line 95: "Scan reads a fixed, human-useful metadata set through Mutagen: artist, title, album, genre, year, country, label, **catalog number**, track number, **disc number**, BPM, key, comments, **ISRC**, duration, audio format, and codec data." **Catalog number, disc number and ISRC are not read and have no column.** `MUTAGEN_TAG_LOOKUP` covers exactly artist, title, album, genre, year, country, label, track_number, bpm, key, comment (`scanner.py:60-84`); the `tags` table has no such columns (`db_ddl.py:76-93`).
- Line 58: "**Workers** starts at `8` and accepts `1..16`" describes the dialog; the API accepts `1..64` (`api_schemas.py:60`). Worth stating so an API caller is not misled.
- Everything else verified: AppleDouble skip (`scanner.py:355`), batch-of-64 + 2× in-flight process pool with parent-thread writes (`scan_jobs.py:471-511`), PyAV container-duration fallback that decodes no frames (`scanner.py:375-385`), unchanged size/mtime skipping tag decode (`scanner.py:148-152`).

### `docs/dj-track-similarity/concepts/local-first-safety.md` — **INCOMPLETE**
- Line 14 "Optional ANN sidecar indexes" lists a local artifact the app cannot produce (see `vector_index.py`). Remove.
- The read-only table (lines 24-37) omits three real workflows: **single-track catalog delete** (`DELETE /api/tracks/{track_id}`, which writes SQLite and the evaluation sidecar but never touches audio), **Reveal in Explorer** (spawns `explorer.exe`, reads nothing), and **text-search preset feedback** (`POST /api/search/text/feedback`, which writes `text_preset_feedback` and may create that table).
- It does not mention that `remove_deleted_track` refuses to delete a catalog row while the source file still exists (`db_tracks.py:1363-1366`) — a safety property worth advertising.
- Everything in "Source-file write paths" (lines 41-48) matches the backend: genre apply is the only backend audio writer (`tags.py:390-422`), `APPLY DELETE` is enforced verbatim (`api_routes_audio_dedup.py:20, 123`).

### `docs/dj-track-similarity/help/troubleshooting.md` — **ACCURATE**
Every check verified against code: FFmpeg DLL set and discovery order (`ffmpeg_runtime.py:15-22, 97-116`), PyAV `17.1.0` from the active environment (`ffmpeg_runtime.py:52-63`), library-identity open failure and the migration phrase (`db_schema.py:48-76`, `db_migration.py:25`), two-decoder ML path with `[ffmpeg] Track analyzed` labelling (`analysis_jobs.py:1089-1101`, `analysis_job_state.py:20-23`), access records console-only (`logging_config.py:287-297`), `--device cpu` fallback (`runtime.py:25-33`). One gap: it does not cover the two most likely startup failures after the FFmpeg one — `DatabaseBusy` 409 responses while a job runs, and `uv sync --locked` failing on the stale lock.

---

## 10. UNDOCUMENTED SURFACE (ranked)

1. **The whole Evaluation HTTP group (7 routes).** `api_routes_evaluation.py:35-199`. `reference/api.md` documents zero of them, yet `dj-sim eval` has 13 documented CLI commands that write to the same storage. A user who found the CLI has no way to discover the API. Include the `409 "Evaluation API requires the current SQLite structure"` behavior.

2. **`uv.lock` / `pyproject.toml` disagreement over the `ann` extra.** `uv.lock:503-506, 545` vs `pyproject.toml:22-46`. Four documentation pages and the README tell users to run `uv sync --locked`, which is expected to fail. This is the single highest-impact undocumented fact.

3. **`text_preset_feedback` table and `POST /api/search/text/feedback`.** `db_ddl.py:333-352`, `db_evaluation.py:48-129`, `api_routes_search.py:250-270`. A persisted user-data table with a documented downstream consumer (`scripts/prompt_preset_tune.py`) that appears in no reference page, and the only runtime-additive DDL in the project.

4. **Database validation as a background job.** `POST /api/database/validation/jobs` + 3 companions (`api_routes_database.py:46-70`), backed by `database_validation_jobs.py`. Only the CLI `validate-database` is documented, and even that omits exit code 2.

5. **`POST /api/search/text/warmup`.** `api_routes_search.py:221-248`. A first-class latency mitigation (tens of seconds of weight deserialization) with an explicit response shape, documented nowhere.

6. **ML Staged Mode.** CLI flags `--ml-staged/--ml-staging-path/--ml-copy-workers/--ml-decode-workers/--ml-stage-size` (`cli.py:908-912`) and the `ml.staged` API block (`api_schemas.py:223-262`). README describes ML Staged Mode in prose (README.md:435-440) but neither the command reference nor the API reference exposes any of its parameters.

7. **`GET /api/analysis/sonara/status`, and SONARA reset semantics.** The endpoint is listed in `api.md:109` but the crucial consequence is not: `/api/analysis/reset` with `analysis_family="sonara"` deletes **only `sonara_features`** (`api_routes_analysis.py:337`, `db_analysis.py:1383-1390`). `sonara_embeddings` and `sonara_fingerprints` rows survive the reset; the next SONARA run re-selects those tracks (core missing) and rewrites all three. A user reading "reset SONARA analysis first" to change the BPM range needs this.

8. **Environment variables beyond the FFmpeg one.** Nine real variables (see §7) against one documented row.

9. **`POST /api/tracks/{track_id}/reveal`.** `api_routes_library.py:178-193` — the only route that launches an external GUI process.

10. **Random-seed endpoints.** `POST /api/search/random-track` and `POST /api/search/sonara/random-track` (`api_routes_search.py:121, 172`) — the "start from an unusual opener" entry point the README's product framing depends on (README.md:76), with no reference entry.

11. **Genre-apply readback verification.** `tags.py:289-301, 360-371` — the audio-write path re-reads the file and fails the write if the genres do not round-trip. `user-guide/tags-and-audio-writes.md` NOT VERIFIED (outside my listed set), but neither `local-first-safety.md` nor `api.md` mentions this guarantee, which is the strongest argument that the one audio-write path is safe.

12. **A latent FTS defect: MAEST genres are never indexed.** `db_search_fts._maest_genres_text` accepts only plain strings or dicts with a `genre_name` key (`db_search_fts.py:39-57`), but canonical `maest_genres.genres_json` entries are validated to have exactly the keys `{"label","score"}` (`maest_analysis_validation.py:106-107`, written by `MaestWrite.genres_json` at `analysis_models.py:684-691`). The `maest_genres` FTS column therefore always stores `""`. `search_mode=fts` cannot find a track by its MAEST genre label, while `search_mode=like` is unaffected. This is a code bug, not a doc bug — hand it to the main session rather than documenting the current behavior as intended.

13. **README internal link that 404s.** `README.md:462` links `docs/dj-track-similarity/tools-and-scripts/persistent-ann-indexes.md`; that file does not exist (verified against the full docs glob). It should be removed together with the ANN claims.agentId: a22687a2d42c3eec4 (use SendMessage with to: 'a22687a2d42c3eec4', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 434842
tool_uses: 119
duration_ms: 710591</usage>
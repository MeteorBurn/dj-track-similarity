# Graph Report - dj-track-similarity  (2026-08-24)

## Corpus Check
- 444 files · ~447,866 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6809 nodes · 19169 edges · 306 communities (276 shown, 30 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 1611 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `87617f05`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- AnalysisJobManager
- sonara_similarity_scoring.py
- label_transfer.py
- source_db.py
- FileTags
- Main project
- SonaraSimilaritySearch
- RhythmLabDatabase
- App
- app.js
- test_audio_dedup.py
- reports.py
- scan_library
- web_app.py
- ann_index.py
- api_schemas.py
- Reference Index
- PersistentAnnVectorSearchBackend
- ScanJobManager
- api.ts
- AnalysisBatchItem
- TrackInput
- source_profile.py
- test_consumers.py
- score_profiles.py
- tags.py
- db_migration.py
- evaluation/ablation.py
- TrackMetadataDialog.tsx
- risk_sweep.py
- Features, embeddings, and tags
- test_evaluation_cli.py
- metadata_enrichment_cli.py
- calibration.py
- api.py
- DecodedAudio
- ClapEmbeddingAdapter
- test_repair_audio_metadata.py
- ReferenceComparePanel.tsx
- compute_transition_diagnostics
- db_connection.py
- TrackIdentity
- MLStagingConfig
- db_analysis.py
- SourceTrack
- classifier_manifest.py
- test_multi_model_analysis_jobs.py
- transition_diagnostics.py
- current_embedding_spec
- export_seed_sample
- create_app
- test_sonara_storage.py
- EvaluationRepository
- TextEmbeddingAdapterCache
- sonara_features.py
- SearchPlaylistPanel.tsx
- benchmark_search.py
- TrackRows.tsx
- test_analysis_orchestration.py
- rhythm_lab/ablation.py
- classifier_production.py
- AnalysisPipelineManager
- jobUi.tsx
- rhythm_lab_launcher.py
- rhythm_lab/cli.py
- useLibraryState.ts
- escapeHtml
- App.tsx
- score_profile_optimizer.py
- test_embedding.py
- labels.py
- test_vector_index.py
- frontend/package.json
- artifact_io.py
- ffmpeg_runtime.py
- test_classifier_scoring.py
- test_api_reference_compare.py
- TrackSummary
- sonara_storage.py
- candidates.py
- tempo_resolution.py
- audio_doctor/core.py
- training.py
- text_tag_crosscheck.py
- exporter.py
- main
- Path
- RepairError
- embedding.py
- test_rhythm_lab.py
- configure_logging
- analysis_models.py
- load_tracks
- report.py
- seed_sampling.py
- build_score_profile_optimizer_report
- .connect
- audio_dedup/core.py
- Separable head, models disagree
- compilerOptions
- EmbeddingTrackIdentity
- EvaluationRepository
- test_api_rhythm_lab.py
- AppDatabaseState
- select_torch_device
- AnalysisTarget
- SimilaritySearch
- main
- PresetConfig
- loadActive
- connect_evaluation_sidecar
- media_preview.py
- SonaraStagingConfig
- audio_loader.py
- DJ Track Similarity Banner
- MaestWindowContext
- tests/test_cli.py
- optimize_database.py
- Q: Какая версия FAST API у меня сейчас?
- wave_tags.py
- ClassifierScoreDetail
- TrackRecord
- FileRepairResult
- score_prompt_bank.py
- scripts
- track_models.py
- test_api_database_selection.py
- Workflows
- api_routes_analysis.py
- loadTrainingReadiness
- run_report
- Personal Classifier Workflow
- test_scan_jobs.py
- ClassifierSpecification
- qa_database.py
- read_local_evidence
- judged.py
- api_routes_search.py
- Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?
- Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?
- test_break_energy.py
- models.py
- Classifier Workflow
- Russian Project Overview
- AnalysisOutput
- RhythmLabCollections
- run-vale.mjs
- Search with Seed Tracks
- Know When Audio Files Can Be Written
- tooltipLayer.tsx
- test_run_server_lan_script.py
- ScannedFile
- text_prompt_benchmark.py
- database.py
- Audio Online
- metadataReference.test.mjs
- rhythm_lab_impact_payload
- build_report_payload
- collect_repository_paths
- Normalized Prompt Ensemble
- validate_prompt_bank.py
- _coverage_and_classifiers
- run_server_launcher.py
- Unified SQLite Music Library
- test_api_sonara_search.py
- workbook_bridge.mjs
- CLAP Query Workflow
- DJ Track Similarity Agent Instructions
- Q: How does Rhythm Lab persist classifier scores?
- Temporary Current Set
- mlAnalysisSettings.test.mjs
- Response
- Codebase Documentation Writer
- OptimizerExample
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- Local-First DJ Library Workbench
- test_benchmark_search.py
- isMulticlassProfile
- _required_text
- Rhythm Lab Page
- DJ Track Similarity Project Overview
- DJ Track Similarity Dark Logo
- CLAP Text Search
- Audio-Online/tests/test_cli.py
- DJ Track Similarity
- DatabaseValidationJobManager
- config.mts
- db_embeddings.py
- apiContract.test.mjs
- sonara_core_validation.py
- playerAutoplay.test.mjs
- referenceCompareContract.test.mjs
- sonaraSearchControls.test.mjs
- _track_from_row
- Rhythm Lab Favicon
- DJ Track Similarity Favicon Artwork
- Music Favicon
- appHeaderMeta.test.mjs
- logging_config.py
- helpText.test.mjs
- libraryRendering.test.mjs
- sonaraDisplay.test.mjs
- tooltipPosition.test.mjs
- dj-track-similarity Frontend Page
- frontendHooks.test.mjs
- jobUi.test.mjs
- sonaraFeatureLabels.test.mjs
- audio_dedup/__init__.py
- audio_doctor/__init__.py
- JobStore
- Empty Rejection Vocabulary
- dj-track-similarity
- db_library_queries.py
- textPromptPresets.ts
- Q: как реализована передача аудио в MULAN
- What You Must Do When Invoked
- classifier_scoring.py
- Q: Проанализируй реализацию извлечения эмбов в MULam в проекте
- Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA
- dj_track_similarity/cli.py
- test_evaluation_weighted_candidates.py
- VerifiedAssetBinding
- StandardStreamLogMirror
- scanImportDialog.test.mjs
- recorded_sessions.py
- project_text_search.py
- Q: Почему LibraryDatabase стал главным мостом между сообществами?
- Q: Path from LibraryDatabase to AnalysisOutput
- Q: Trace AnalysisOutput through ClassifierScorer to classifier_scores
- Q: Trace ClassifierJobManager through scoring to save_classifier_scores
- Q: Trace AnalysisOutput to ClassifierFeatureRow to score_row
- Q: го
- Q: го
- Q: го
- Q: го
- Q: го
- Q: го
- Q: го
- Q: classifier_score_counts в UI должен вызываться
- sonaraAnalysisMode.test.mjs
- ClassifierJobManager
- rhythm_lab_collections.py
- Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть.
- Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?
- Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?
- LibraryDatabase
- test_api_tracks.py
- AnalysisCandidate
- Q: Убери глобальный барьер и ожидание считывания всех файлов
- Q: Анализ MULAN как декодируется?
- Q: Проанализируй изменения TorchCodec 0.16.0 и CUDA-производительность применительно к аудио-анализу и отдельному SONARA fallback.
- Q: Какие текущие точки декодирования и база путей нужны для честного бенчмарка аудиодекодеров?
- Q: Какие новые нативные возможности TorchCodec 0.16, TorchAudio 2.11 и PyTorch заменяют пользовательскую логику decode, mono, resample и window preparation в dj-track-similarity?
- Q: Как закрепить анализ ML моделей MAEST MERT MuQ MuLan CLAP с TorchCodec и конечным FFmpeg fallback?
- Q: Давай уже определим: WavDecoder или AudioDecoder для ML моделей, которым нужен mono?
- Q: analysis pipeline job queue decode decoded embedding runner sonara maest mert muq
- Q: Как выполнить контракт maest_infer_input_contract.json через проект с TorchCodec 0.16?
- test_database_validation.py
- Q: как определяются есть ли уже трек в базе или нет при загркузке новых?
- handle_asyncio_exception_context
- test_api_runtime.py
- playlistAddHandler.test.mjs
- Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе.
- Q: Почему данные в базу не пишутся?
- trackMarkup
- Q: где проблема
- loadCandidates
- User Guide
- rank_maest_genres
- test_classifier_jobs.py
- api_routes_rhythm_lab.py
- test_config.py
- test_classifier_manifest.py
- install_standard_stream_logging
- api_routes_database.py
- db_search_fts.py
- _ReadyClassifier
- Exception
- MonkeyPatch
- TrackIdentity
- storage_database_paths
- _scan_track
- test_qa_database_script.py
- graphify reference: extra exports and benchmark
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- validate_maest_analysis_row
- Prompt Bank Curator
- textPromptPresets.test.mjs

## God Nodes (most connected - your core abstractions)
1. `LibraryDatabase` - 280 edges
2. `AnalysisOutput` - 188 edges
3. `AnalysisTarget` - 163 edges
4. `RhythmLabDatabase` - 86 edges
5. `AnalysisJobManager` - 82 edges
6. `App()` - 82 edges
7. `TrackIdentity` - 80 edges
8. `create_app()` - 69 edges
9. `EvaluationRepository` - 65 edges
10. `AnalysisCandidate` - 60 edges

## Surprising Connections (you probably didn't know these)
- `CLAP Text-to-Audio and Audio-to-Audio Search` --semantically_similar_to--> `Russian CLAP Text Search Explanation`  [INFERRED] [semantically similar]
  README.md → README_RU.md
- `Separated Model Evidence Sources` --semantically_similar_to--> `Russian Multi-Model Similarity Explanation`  [INFERRED] [semantically similar]
  README.md → README_RU.md
- `Auxiliary Classifier UI` --semantically_similar_to--> `Rhythm Lab Collection Save`  [INFERRED] [semantically similar]
  tools/rhythm-lab/README.md → docs/dj-track-similarity/user-guide/export-playlists.md
- `Local-First Safety Baseline` --semantically_similar_to--> `Report-First Maintenance Tools`  [INFERRED] [semantically similar]
  AGENTS.md → README.md
- `Local-First DJ Library Workbench` --semantically_similar_to--> `Russian Local-First Workbench Description`  [INFERRED] [semantically similar]
  README.md → README_RU.md

## Import Cycles
- 2-file cycle: `frontend/src/api.ts -> frontend/src/apiClient.ts -> frontend/src/api.ts`

## Communities (306 total, 30 thin omitted)

### Community 0 - "AnalysisJobManager"
Cohesion: 0.07
Nodes (39): AnalysisJobStatus, Item, RunnerFactory, AnalysisJobStatus, AnalysisLogEvent, AnalysisModelProgress, AnalysisTrackError, AnalysisTrackOutcome (+31 more)

### Community 1 - "sonara_similarity_scoring.py"
Cohesion: 0.12
Nodes (40): _merge_targets(), _optional_targets(), _optional_track_ids(), RuntimeError, Resolve request IDs to current tracks with active SONARA Core., Choose one unselected current track with valid SONARA Core features., Raised when no current SONARA Core data can serve search., _requested_track_ids() (+32 more)

### Community 2 - "label_transfer.py"
Cohesion: 0.08
Nodes (104): _absolute_lexical_path(), _backup_restore_target(), _build_parser(), build_rebound_bundle(), _build_restore_plan(), _canonical_json_bytes(), _canonical_json_text(), canonical_path_key() (+96 more)

### Community 3 - "source_db.py"
Cohesion: 0.05
Nodes (73): _attach_labels(), _base_track_query(), _clean_path_text(), _count_sonara_features(), _embedding_family(), _embedding_vector(), _feature_counts(), _feature_source_states() (+65 more)

### Community 4 - "FileTags"
Cohesion: 0.17
Nodes (38): ID3, _load_id3(), _write_genre_tag(), FileTags, Human-readable tags read from an audio file., _decoded_audio_md5(), _make_tone(), parametrize (+30 more)

### Community 5 - "Main project"
Cohesion: 0.06
Nodes (32): Audio Dedup, Audio Doctor, Audio Online, Commands and arguments, `dj-sim analyze`, `dj-sim analyze-classifier CLASSIFIER`, `dj-sim analyze-pipeline`, `dj-sim classifier calibration-report` (+24 more)

### Community 6 - "SonaraSimilaritySearch"
Cohesion: 0.22
Nodes (37): SONARA feature-mixer search over current Core data. The separate 48-dimensional…, SonaraSimilaritySearch, _add_sonara_track(), _add_track_without_sonara(), _core_row(), _feature_value(), _float_or_none(), _int_or_none() (+29 more)

### Community 7 - "RhythmLabDatabase"
Cohesion: 0.07
Nodes (54): _canonical_json(), _classifier_label_from_row(), _classifier_label_queue_table_sql(), _classifier_labels_table_sql(), _classifier_predictions_table_sql(), _classifier_training_checkpoints_table_sql(), ClassifierLabel, ClassifierPredictionWrite (+46 more)

### Community 8 - "App"
Cohesion: 0.07
Nodes (68): App(), addVisibleTracksToPlaylist(), adoptClassifierProfiles(), beginGenericSearchRequest(), cancelGenericSearchRequest(), cancelTrackDetailRequest(), commitGenericSearchResults(), finishGenericSearchRequest() (+60 more)

### Community 9 - "app.js"
Cohesion: 0.04
Nodes (58): addMulticlassLabelRow(), binaryLabelGridEl, bpmMaxEl, bpmMinEl, candidateFiltersEl, candidateMinBrokenEl, candidateMinPositiveEl, candidatePredictedEl (+50 more)

### Community 10 - "test_audio_dedup.py"
Cohesion: 0.18
Nodes (40): _create_library_db(), _create_rhythm_lab_db(), _current_embedding_fixture(), _identity_tuple(), _insert_track(), _load_dedup_module(), CaptureFixture, MonkeyPatch (+32 more)

### Community 11 - "reports.py"
Cohesion: 0.13
Nodes (54): _aggregate_variant_metrics(), average_precision_at_k(), _axis_value(), bad_suggestion_rate_at_k(), _comparison_match_character(), _comparison_rank(), _comparison_reason_tags(), dcg_at_k() (+46 more)

### Community 12 - "scan_library"
Cohesion: 0.13
Nodes (34): ScanStats, Scan one root through the sole TrackRepository write path., scan_library(), Aggregate result returned by the synchronous scanner., ScanStats, _library_roots(), _mert_output(), MonkeyPatch (+26 more)

### Community 13 - "web_app.py"
Cohesion: 0.08
Nodes (48): ClassifierProfile, _artifact_feature(), _artifact_feature_summary(), _artifact_groups(), _artifact_metrics_path(), _artifact_summary(), CalibrateRequest, _calibration_readiness() (+40 more)

### Community 14 - "ann_index.py"
Cohesion: 0.09
Nodes (62): _active_index_output(), _artifact_path_from_manifest(), _artifact_paths(), _assert_inside_directory(), _benchmark_k_values(), benchmark_persistent_index(), _build_manifest(), build_persistent_index() (+54 more)

### Community 15 - "api_schemas.py"
Cohesion: 0.10
Nodes (42): field_validator, FastAPI, Path, register_library_routes(), AnalysisCoverageResponse, ClassifierScoreDetailResponse, ClassifierScoreSummaryResponse, ClearLibraryResponse (+34 more)

### Community 16 - "Reference Index"
Cohesion: 0.05
Nodes (63): Explicit Audio Write Boundary, DJ Track Similarity Documentation Home, Local-First Ranked Workflow, Listening-Led Shortlisting, Project Guide, Analysis Families Reference, Database-Only Classifier Scoring, ML Embedding Families (+55 more)

### Community 17 - "PersistentAnnVectorSearchBackend"
Cohesion: 0.15
Nodes (15): PersistentAnnVectorSearchBackend, Strict persistent HNSW search over one current embedding output. The backend…, fake_hnsw(), FakeHnswModule, Index, fixture, MonkeyPatch, ndarray (+7 more)

### Community 18 - "ScanJobManager"
Cohesion: 0.18
Nodes (12): log_failure(), Collection, Exception, Path, Run parallel discovery work against one thread-safe TrackRepository., Prepare bounded path batches and write ready results on this thread., Apply worker results to job state without writing to SQLite., ScanJobManager (+4 more)

### Community 19 - "api.ts"
Cohesion: 0.05
Nodes (61): AnalysisCoverage, AnalysisJobStatus, AnalysisPipelineRequest, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail, ClassifierScoreSummary (+53 more)

### Community 20 - "AnalysisBatchItem"
Cohesion: 0.06
Nodes (25): ArrayLike, AnalysisBatchItem, _LibrarySummary, Protocol, _SonaraStatusRepository, AnalysisWriteRepository, _decoded_items(), default_model_runners() (+17 more)

### Community 21 - "TrackInput"
Cohesion: 0.09
Nodes (36): BeatportSource, DiscogsSource, _first_label(), Discogs database adapter using only its documented API surface., _strings(), _track_title(), LastFmSource, Last.fm community tag adapter. (+28 more)

### Community 22 - "source_profile.py"
Cohesion: 0.12
Nodes (47): build_source_profile(), _clean_profile_request(), _clean_sources(), _clean_top_k_values(), _consensus_report(), _coverage_fallback_factors(), _effective_sources(), _int_value() (+39 more)

### Community 23 - "test_consumers.py"
Cohesion: 0.18
Nodes (50): PredictionProgressCallback, PromotionProgressCallback, Resolve the root model and its matching root manifest., resolve_classifier_artifact_paths(), promote_profile_model(), _report_promotion_progress(), apply_model_to_lab(), create_app() (+42 more)

### Community 24 - "score_profiles.py"
Cohesion: 0.09
Nodes (57): _inline_score_profile_payload(), Any, FastAPI, register_evaluation_routes(), _score_profile_from_request(), _score_profile_from_source_profile(), _score_profile_name(), _utc_timestamp() (+49 more)

### Community 25 - "tags.py"
Cohesion: 0.11
Nodes (30): GenreTagCandidate, _apply_genre_tag_to_candidate(), apply_genre_tags_to_tracks(), _clean_genre_label(), genre_tag_apply_summary(), _genre_tags_for_candidate(), GenreTagApplyResult, GenreTagError (+22 more)

### Community 26 - "db_migration.py"
Cohesion: 0.11
Nodes (54): _apply_schema(), create_library_schema(), Connection, Create the current single-library schema in *db*. Args: db: An open…, _attached_row_count(), _attached_table_exists(), _backup_sqlite(), _build_staged_library() (+46 more)

### Community 27 - "evaluation/ablation.py"
Cohesion: 0.10
Nodes (51): _ablated_signal(), _build_session_variants(), build_source_ablation_report(), _candidate_contributions_from_source_ranks(), _candidate_event(), _candidate_pool_sessions(), CandidateEvent, CandidatePoolSession (+43 more)

### Community 28 - "TrackMetadataDialog.tsx"
Cohesion: 0.06
Nodes (55): formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureDescriptor, CoreFeatureGroup (+47 more)

### Community 29 - "risk_sweep.py"
Cohesion: 0.10
Nodes (53): _average_transition_risk_at_k(), _best_by_metric(), _best_source_rank(), build_risk_penalty_sweep_report(), _cached_track(), _candidate_payload(), _candidate_with_risk_weight(), _clean_k_values() (+45 more)

### Community 30 - "Features, embeddings, and tags"
Cohesion: 0.06
Nodes (53): Classifiers and Rhythm Lab, Database-only classifier scoring, Immutable-generation promotion, Personal classifier, Rhythm Lab workflow, CLAP audio embedding, Features, embeddings, and tags, File tags (+45 more)

### Community 31 - "test_evaluation_cli.py"
Cohesion: 0.16
Nodes (44): AnalysisTarget, SonaraRow, _add_cli_track(), _build_candidate_export_library(), _build_optimizer_cli_library(), _expanded_unit_vector(), _identity_payload(), _maest_outputs() (+36 more)

### Community 32 - "metadata_enrichment_cli.py"
Cohesion: 0.10
Nodes (46): FormPost, JsonGet, Request, authorize_lastfm(), Explicit documented authorization flows for sources that support them., Open Last.fm consent and exchange its one-time token for a session key., _access_token(), _auth_values() (+38 more)

### Community 33 - "calibration.py"
Cohesion: 0.13
Nodes (40): _average_score(), _binary_label(), brier_score(), build_calibration_report(), _calibration_report(), _calibration_samples(), _calibration_status(), CalibrationSample (+32 more)

### Community 34 - "api.py"
Cohesion: 0.10
Nodes (21): open_database_file_dialog(), open_folder_dialog(), FastAPI, Path, Open Windows Explorer with the supplied audio file selected., reveal_track_file(), FastAPI, Path (+13 more)

### Community 35 - "DecodedAudio"
Cohesion: 0.11
Nodes (20): DecodedAudio, _array_output_to_numpy(), _average_l2_window_embeddings(), _masked_time_mean(), MertEmbeddingAdapter, _normalize_rows(), _normalized_embedding_rows(), _prepare_muq_compatible_windows() (+12 more)

### Community 36 - "ClapEmbeddingAdapter"
Cohesion: 0.09
Nodes (23): _text_embedding_adapter(), ClapEmbeddingAdapter, _ensure_verified_maest_checkpoint(), MaestEmbeddingAdapter, MuqEmbeddingAdapter, MuqMulanEmbeddingAdapter, Populate and verify the torch-hub cache before maest-infer loads it., Verify model assets and construct the configured loader. (+15 more)

### Community 37 - "test_repair_audio_metadata.py"
Cohesion: 0.12
Nodes (45): _aiff_chunk(), _load_repair_module(), _minimal_aiff_with_empty_id3_chunks(), _minimal_pcm_wave(), Path, _riff_chunk(), test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload(), test_apply_forces_single_worker() (+37 more)

### Community 38 - "ReferenceComparePanel.tsx"
Cohesion: 0.16
Nodes (21): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareResponse, ReferenceCompareVerdict, TrackIdentity, api, normalizeLimit(), orderedReferenceCompareGroups() (+13 more)

### Community 39 - "compute_transition_diagnostics"
Cohesion: 0.19
Nodes (26): compute_transition_diagnostics(), Compute transition risk from identity-validated repository rows., _classifier_score(), ClassifierScoreSummary, test_adjacent_camelot_key_has_lower_risk_than_clash(), test_aggregate_ignores_missing_components(), test_bpm_exact_match_has_low_risk(), test_bpm_half_double_compatible_has_low_risk() (+18 more)

### Community 40 - "db_connection.py"
Cohesion: 0.13
Nodes (30): RLock, Path, _bootstrap_file_lock(), _bootstrap_lock_path(), _cleanup_staged_sqlite(), _configure_connection(), connect_database(), _create_fresh_library() (+22 more)

### Community 41 - "TrackIdentity"
Cohesion: 0.13
Nodes (34): SonaraFeatureRow, CsvRow, _optional_number(), _optional_text(), CsvRow, TrackIdentity, TrackSummary, Resolve tempo from one current summary and optional SONARA row. (+26 more)

### Community 42 - "MLStagingConfig"
Cohesion: 0.14
Nodes (22): AnalysisJobConfig, build_analysis_job_config(), _int_in_range(), normalize_analysis_device(), normalize_analysis_models(), _normalize_limit(), normalize_sonara_mode(), MLStagingConfig (+14 more)

### Community 43 - "db_analysis.py"
Cohesion: 0.08
Nodes (52): AnalysisResetResult, AnalysisWriteResult, RuntimeError, Raised when a write target no longer names the current track content., StaleAnalysisTargetError, AnalysisRepository, collect_analysis_candidates(), current_sonara_target_keys() (+44 more)

### Community 44 - "SourceTrack"
Cohesion: 0.18
Nodes (23): build_feature_matrix(), build_labeled_feature_matrix(), build_labeled_feature_matrix_from_sources(), _cached_embedding_vectors(), _feature_names(), FeatureMatrix, _finite_float(), _parse_feature_names() (+15 more)

### Community 45 - "classifier_manifest.py"
Cohesion: 0.13
Nodes (24): current_classifier_specifications(), classifier_manifest_api_fields(), classifier_manifest_from_info(), ClassifierArtifactPaths, ClassifierManifestSummary, _clean_classifier_key(), _feature_sources(), _invalid_manifest() (+16 more)

### Community 46 - "test_multi_model_analysis_jobs.py"
Cohesion: 0.18
Nodes (14): _candidate(), _decoded(), _maest_output(), _mert_output(), Exception, Path, _Repository, _Runner (+6 more)

### Community 47 - "transition_diagnostics.py"
Cohesion: 0.08
Nodes (61): _active_sonara_rows(), _analysis_target(), load_all_transition_tracks(), _load_transition_tracks(), load_transition_tracks_for_ids(), load_transition_tracks_for_targets(), TrackIdentity, Identity-bound typed track views for evaluation workflows. (+53 more)

### Community 48 - "current_embedding_spec"
Cohesion: 0.11
Nodes (33): current_embedding_spec(), _hydrate_similarity_results(), Attach current typed library summaries to validated search identities., _validate_feature_inputs(), _apply_epsilon(), _contrast_score_breakdown(), _contrast_vector_scores(), _finite_number() (+25 more)

### Community 49 - "export_seed_sample"
Cohesion: 0.25
Nodes (21): _weighted_candidate_seed_track_ids(), export_seed_sample(), SeedSampleResult, _ml_outputs(), ndarray, Path, TrackIdentity, _save_complete_analysis() (+13 more)

### Community 50 - "create_app"
Cohesion: 0.20
Nodes (20): create_app(), FakeClapAdapter, FakeMulanAdapter, ndarray, Path, A multi-line bank is never reduced to its first line. The removed…, test_repeated_text_search_reuses_one_loaded_adapter(), test_text_search_applies_a_requested_negative_weight() (+12 more)

### Community 51 - "test_sonara_storage.py"
Cohesion: 0.19
Nodes (24): _analysis(), _candidate(), _prepare(), float32, MonkeyPatch, ndarray, parametrize, Path (+16 more)

### Community 52 - "EvaluationRepository"
Cohesion: 0.14
Nodes (24): _canonical_json_value(), _clean_tags(), EvaluationRepository, _finite_float(), _json_load(), _json_object(), _json_text(), _load_track_snapshots() (+16 more)

### Community 53 - "TextEmbeddingAdapterCache"
Cohesion: 0.09
Nodes (22): AdapterT, _cache_key(), _CacheEntry, Keep one loaded text-embedding model per family and device. Building a fresh…, Return dropped weights to the CUDA allocator, not just to Python., Reuse one adapter per ``(family, device)`` across text search requests., Yield one adapter, held against eviction and other callers. Sync FastAPI…, Drop adapters nobody has used for longer than the idle TTL. (+14 more)

### Community 54 - "sonara_features.py"
Cohesion: 0.06
Nodes (47): load_audio_mono_with_ffmpeg(), ndarray, Decode one SONARA recovery source through shared FFmpeg to mono float32 PCM., _analysis_mapping(), _analysis_mapping_with_ffmpeg_fallback(), analysis_outputs_for_sonara_runtime(), analyze_and_store_sonara_batch(), _import_sonara() (+39 more)

### Community 55 - "SearchPlaylistPanel.tsx"
Cohesion: 0.07
Nodes (43): EmbeddingSource, PromotedClassifier, SonaraMixerWeights, SonaraModifiers, SonaraSearchMode, classifierIsAvailable(), classifierProfileStatus(), classifierScoringBlockedReason() (+35 more)

### Community 56 - "benchmark_search.py"
Cohesion: 0.14
Nodes (38): _active_embedding_output(), _benchmark_database_path(), _benchmark_track_count(), BenchmarkConfig, _camelot_key(), _conflicting_kept_database_path(), _environment_summary(), _insert_synthetic_tracks() (+30 more)

### Community 57 - "TrackRows.tsx"
Cohesion: 0.22
Nodes (13): emptyPreviewPosition, listeners, PreviewPosition, previewPositionForTrack(), readPreviewPosition(), subscribePreviewPosition(), usePreviewPosition(), contrastParts() (+5 more)

### Community 58 - "test_analysis_orchestration.py"
Cohesion: 0.06
Nodes (42): AnalysisCandidate, AnalysisWriteResult, DecodedAudio, EmbeddingWrite, Exception, MaestAnalysisResult, MaestEmbeddingAdapter, MaestWindowContext (+34 more)

### Community 59 - "rhythm_lab/ablation.py"
Cohesion: 0.19
Nodes (22): benchmark_profile_ablation(), cli_summary(), _compact_row(), _default_output_path(), _elapsed_seconds(), _metrics_summary(), _normalize_feature_sets(), _optional_float() (+14 more)

### Community 60 - "classifier_production.py"
Cohesion: 0.13
Nodes (32): build_classifier_calibration_report(), _calibration_report_status(), _candidate_feedback_aggregates(), _classifier_feedback_summary(), _classifier_score_detail(), ClassifierScoreRow, _clean_classifier_key(), _count_values() (+24 more)

### Community 61 - "AnalysisPipelineManager"
Cohesion: 0.06
Nodes (55): AnalysisPipelineManager, AnalysisPipelineStatus, _PipelinePayload, PipelineStageStatus, AnalysisStageQueue, One in-memory worker shared by SONARA, ML, and classifier stages., create_api_client(), MonkeyPatch (+47 more)

### Community 62 - "jobUi.tsx"
Cohesion: 0.10
Nodes (29): AnalysisModel, ACTIVE_JOB_STATES, ActivityEvent, analysisJobRequest(), AnalysisProcessStatus(), analysisRuntimeLabel(), AUDIO_MODELS, calculateEta() (+21 more)

### Community 63 - "rhythm_lab_launcher.py"
Cohesion: 0.17
Nodes (32): _clear_pid(), _file_size(), _is_rhythm_lab_process(), launch_rhythm_lab(), _listener_process_id(), _log_path(), _managed_process_id(), _mirror_log_to_console() (+24 more)

### Community 64 - "rhythm_lab/cli.py"
Cohesion: 0.14
Nodes (34): _add_data_options(), _artifact_calibration_payload(), _artifact_matches_calibration_filter(), _benchmark_ablation(), build_parser(), _calibration_report(), _collection_list(), _collection_save() (+26 more)

### Community 65 - "useLibraryState.ts"
Cohesion: 0.11
Nodes (37): Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts, libraryTrackIdentityKey() (+29 more)

### Community 66 - "escapeHtml"
Cohesion: 0.10
Nodes (38): actionIcon(), canPromoteArtifact(), coverageBadge(), escapeHtml(), formatFeatureGroupWeights(), formatHumanDate(), formatLabelCounts(), formatMetricDelta() (+30 more)

### Community 67 - "App.tsx"
Cohesion: 0.04
Nodes (59): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, defaultNotice, DeviceMode (+51 more)

### Community 68 - "score_profile_optimizer.py"
Cohesion: 0.14
Nodes (40): _assert_normalized_weights(), _base_report(), build_saved_score_profile_payload(), _clean_k_values(), _grid_step(), _guardrails(), _int_value(), _matched_optimizer_examples() (+32 more)

### Community 69 - "test_embedding.py"
Cohesion: 0.05
Nodes (35): adapter_factories(), _move_maest_runtime_modules(), BatchMaestAdapter, FakeClapAudioModel, FakeMaestModel, FakeMertModel, FakeMertProcessor, FakeMulanModel (+27 more)

### Community 70 - "labels.py"
Cohesion: 0.22
Nodes (22): _json_object(), _load_csv_labels(), _load_jsonl_labels(), load_pair_feedback_labels(), load_transition_feedback_labels(), _optional_text(), PairFeedbackLabel, _parse_pair_feedback_row() (+14 more)

### Community 71 - "test_vector_index.py"
Cohesion: 0.22
Nodes (17): ExactVectorSearchBackend, Deterministic exact cosine search over validated unit vectors., _add_track(), _mert_unit_vector(), MonkeyPatch, ndarray, Path, TrackIdentity (+9 more)

### Community 72 - "frontend/package.json"
Cohesion: 0.07
Nodes (29): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+21 more)

### Community 73 - "artifact_io.py"
Cohesion: 0.18
Nodes (22): PublicationProgressCallback, artifact_sha256(), ArtifactIntegrityError, _AvailableOutputRepository, _default_metadata_path(), _fsync_directory(), load_verified_artifact(), publish_promoted_artifact() (+14 more)

### Community 74 - "ffmpeg_runtime.py"
Cohesion: 0.12
Nodes (29): ModuleType, AudioRuntimeInfo, configure_shared_ffmpeg_runtime(), _configured_or_path_shared_directory(), _contains_any_ffmpeg_library(), _ffmpeg_release_version(), inspect_audio_runtime(), load_project_pyav() (+21 more)

### Community 75 - "test_classifier_scoring.py"
Cohesion: 0.18
Nodes (31): load_classifier_requirements(), Validate the classifier recipe, required inputs, and artifact. This function is…, _require_available_outputs(), _artifact_hash(), _insert_track(), _install_fake_joblib(), _manifest_payload(), _mert_output() (+23 more)

### Community 76 - "test_api_reference_compare.py"
Cohesion: 0.31
Nodes (16): _client(), _embedding(), _embedding_outputs(), _identity_payload(), _maest_analysis_output(), parametrize, Path, TestClient (+8 more)

### Community 77 - "TrackSummary"
Cohesion: 0.20
Nodes (22): TrackSummary, build_reference_compare(), _embedding_group(), _feedback_source(), _hydrate_results(), Protocol, TrackIdentity, TrackSummary (+14 more)

### Community 78 - "sonara_storage.py"
Cohesion: 0.10
Nodes (34): FingerprintOutput, One versioned SONARA acoustic fingerprint in native base64 form., SonaraWrite, SONARA Core row from the ``sonara_features`` table. The three timbre BLOBs are…, SonaraRow, Protocol, Repository boundary required by the SONARA batch orchestrator., SonaraAnalysisRepository (+26 more)

### Community 79 - "candidates.py"
Cohesion: 0.06
Nodes (63): _analysis_target(), _blind_candidate_rows(), _CandidateAccumulator, CandidateExportRequest, CandidateExportResult, CandidatePoolRow, CandidateSourceContribution, _clean_sources() (+55 more)

### Community 80 - "tempo_resolution.py"
Cohesion: 0.17
Nodes (30): best_tempo_distance(), _candidate_bpms(), _clamp01(), confidence_aware_target_score(), confidence_aware_tempo_risk(), confidence_aware_tempo_score(), _finite_float(), measured_tempo_score() (+22 more)

### Community 81 - "audio_doctor/core.py"
Cohesion: 0.13
Nodes (29): escaped_codepoint(), is_xml_character(), load_state(), new_state(), normalize_state_sources(), _problems_sheet_rows(), resolve_state_path(), _results_sheet_rows() (+21 more)

### Community 82 - "training.py"
Cohesion: 0.18
Nodes (27): benchmark_lab_database(), _bounded_top_n_values(), _calibration_gate(), _calibration_thresholds(), _cross_validation_metrics(), expected_calibration_error(), _feature_group_indices(), _feature_group_weights() (+19 more)

### Community 83 - "text_tag_crosscheck.py"
Cohesion: 0.10
Nodes (37): float64, auc(), binary_truth(), build_arms(), cascade(), crosscheck_module(), label_scores(), LabelScores (+29 more)

### Community 84 - "exporter.py"
Cohesion: 0.44
Nodes (7): export_tracks(), Path, Playlist export for typed library rows., _safe_filename(), _write_csv(), _write_m3u(), ExportTrackRow

### Community 85 - "main"
Cohesion: 0.11
Nodes (19): configure_stdio(), main(), normalize_reason_filter(), parse_args(), Namespace, RunReporter, should_use_color(), state_entry_current() (+11 more)

### Community 86 - "Path"
Cohesion: 0.17
Nodes (21): add_path(), apply_repaired_file(), collect_paths(), delete_backup(), detect_format_from_header(), FileInspectionResult, full_decode_error(), inspect_file() (+13 more)

### Community 87 - "RepairError"
Cohesion: 0.13
Nodes (33): aiff_sound_payload(), aiff_sound_payload_hash(), aligned_pcm_data_payload_hash(), ByteRepairResult, create_backup(), data_payload(), data_payload_hash(), dedupe() (+25 more)

### Community 88 - "embedding.py"
Cohesion: 0.12
Nodes (21): _average_maest_embeddings(), _construct_clap_module_with_pinned_text_model(), _construct_muq_mulan_with_pinned_text_model(), _download_verified_hf_checkpoint(), _download_verified_hf_snapshot(), _local_only_from_pretrained_proxy(), _maest_embedding_rows(), _maest_float_list() (+13 more)

### Community 89 - "test_rhythm_lab.py"
Cohesion: 0.04
Nodes (70): SimpleNamespace, feature_recipe_readiness(), feature_sources(), _feature_state_payload(), Describe readiness strictly for the selected feature recipe., _predict_probabilities(), ndarray, Current-generation availability for one classifier feature source. (+62 more)

### Community 90 - "configure_logging"
Cohesion: 0.14
Nodes (21): configure_logging(), event_log_level(), log_job_event(), parse_log_level(), track_event_logging_enabled(), uvicorn_log_config(), test_configure_logging_archives_previous_day_project_logs_on_startup(), test_configure_logging_defaults_to_info_and_higher() (+13 more)

### Community 91 - "analysis_models.py"
Cohesion: 0.15
Nodes (29): _adapter_identity(), embedding_analysis_output(), _has_syncopated_rhythm(), _maest_genres(), Build the current embedding output for one production adapter., _required_adapter_text(), _runtime_parameters(), clap_embedding_output() (+21 more)

### Community 92 - "load_tracks"
Cohesion: 0.16
Nodes (23): Standalone online track-metadata enrichment tool., _load_audio_file(), _load_csv(), _load_directory(), _load_m3u(), load_tracks(), _load_xlsx(), Path (+15 more)

### Community 93 - "report.py"
Cohesion: 0.16
Nodes (17): build_report_contract(), _clean(), _column(), _join(), _maest(), Path, Source-preserving intermediate report contract., Build one flat, source-preserving data row per track. (+9 more)

### Community 94 - "seed_sampling.py"
Cohesion: 0.14
Nodes (27): _analysis_flag(), _bpm_bucket(), _bucket_for_values(), _buckets_used(), _clean_required_sources(), _energy_bucket(), _finite_number(), _finite_positive_number() (+19 more)

### Community 95 - "build_score_profile_optimizer_report"
Cohesion: 0.20
Nodes (23): _accepted_decision(), build_score_profile_optimizer_report(), _decision_guidance(), _equal_weights(), _sources_seen(), _add_two_candidate_session(), _build_bad_rate_increase_library(), _build_empty_seed_shell() (+15 more)

### Community 96 - ".connect"
Cohesion: 0.22
Nodes (11): _collection_from_row(), _insert_collection_tracks(), _positive_int(), Row, Ordered collection input bound to one library catalog., _require_collection_catalog(), _required_text(), ReviewCollection (+3 more)

### Community 97 - "audio_dedup/core.py"
Cohesion: 0.16
Nodes (24): _bool_text(), _candidates_sheet_rows(), _evidence_by_candidate(), _groups_sheet_rows(), _pair_evidence_sheet_rows(), rhythm_lab_cli_summary(), _rhythm_lab_sheet_rows(), rhythm_lab_summary() (+16 more)

### Community 98 - "Separable head, models disagree"
Cohesion: 0.12
Nodes (15): energy/ambient, instruments/guitar, instruments/kora, instruments/live, instruments/organ, instruments/sitar, instruments/steel-drum, instruments/strings-brass (+7 more)

### Community 99 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+14 more)

### Community 100 - "EmbeddingTrackIdentity"
Cohesion: 0.23
Nodes (10): DatabaseValidationReport, DatabaseValidator, Connection, Path, Row, Explicit, read-only validation of persisted library data., Stream current persisted rows without changing the library database., ValidationFinding (+2 more)

### Community 101 - "EvaluationRepository"
Cohesion: 0.10
Nodes (23): _embedding_output(), EvaluationRepository, _identity(), identity_payload(), profile(), AnalysisCoverage, Any, TrackIdentity (+15 more)

### Community 102 - "test_api_rhythm_lab.py"
Cohesion: 0.20
Nodes (17): _add_track(), _identity_payload(), Path, TrackIdentity, test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(), test_rhythm_lab_collection_save_rejects_legacy_numeric_only_body(), test_rhythm_lab_default_log_path_uses_logs_directory(), test_rhythm_lab_launch_endpoint_allows_no_selected_database() (+9 more)

### Community 103 - "AppDatabaseState"
Cohesion: 0.13
Nodes (12): FastAPI, register_reference_compare_routes(), ReferenceCompareRequest, ReferenceCompareVerdictRequest, AppDatabaseState, DatabaseBusy, DatabaseNotSelected, Path (+4 more)

### Community 104 - "select_torch_device"
Cohesion: 0.11
Nodes (16): Any, select_torch_device(), collapsed(), load_score_prompt_bank_module(), Path, Compare wording, not line wrapping., test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(), test_checkpoint_loading_forces_weights_only() (+8 more)

### Community 105 - "AnalysisTarget"
Cohesion: 0.14
Nodes (26): AnalysisTarget, HnswPersistentIndexSearcher, PersistentIndexSearcher, ndarray, _vector_content_hash(), _hydrate_search_target(), Return one current track summary after checking its exact identity., _hnsw_hits() (+18 more)

### Community 106 - "SimilaritySearch"
Cohesion: 0.38
Nodes (17): Cosine search over one current ML embedding family., SimilaritySearch, _add_track(), _library(), _output(), ndarray, Path, _query() (+9 more)

### Community 107 - "main"
Cohesion: 0.13
Nodes (14): apply_duplicate_deletions(), apply_result_payload(), ApplyResult, _candidate_track_id(), configure_stdio(), confirm_apply(), ConsoleProgressReporter, main() (+6 more)

### Community 108 - "PresetConfig"
Cohesion: 0.15
Nodes (22): _bits_to_int(), _candidate_duration_compatible(), _candidate_pair_ids(), _candidate_reason_lines(), _candidate_safety(), _connected_components(), _content_similarity(), _duration_distance() (+14 more)

### Community 109 - "loadActive"
Cohesion: 0.14
Nodes (28): addOption(), applySourceState(), chooseSource(), clearActiveProfile(), collectNewProfileLabels(), createProfile(), deleteActiveProfile(), deleteSelectedCollection() (+20 more)

### Community 110 - "connect_evaluation_sidecar"
Cohesion: 0.35
Nodes (11): _apply_schema(), _configure_connection(), connect_evaluation_sidecar(), create_evaluation_sidecar_schema(), _creation_lock_path(), _enforce_wal(), Connection, Path (+3 more)

### Community 111 - "media_preview.py"
Cohesion: 0.33
Nodes (9): FileResponse, AudioPreviewError, _delete_temp_file(), _is_browser_safe_wav(), Path, RuntimeError, Raised when an audio preview response cannot be prepared., requires_browser_preview_transcode() (+1 more)

### Community 112 - "SonaraStagingConfig"
Cohesion: 0.10
Nodes (35): LogCaptureFixture, ProcessPoolExecutor, analyze_and_store_staged_sonara(), cleanup_orphaned_sonara_staging(), _initialize_sonara_process(), _process_exists(), Any, Path (+27 more)

### Community 113 - "audio_loader.py"
Cohesion: 0.19
Nodes (21): ml, load_decoded_audio(), load_decoded_audio_with_ffmpeg(), _load_with_shared_ffmpeg(), _load_with_torchcodec(), Path, Tensor, Decode one ML recovery source through shared FFmpeg into a tensor-backed value. (+13 more)

### Community 114 - "DJ Track Similarity Banner"
Cohesion: 0.16
Nodes (20): AI-Assisted Music Analysis, CLAP, Classifiers, DJ Set Building, DJ Track Similarity Banner, Genre Detection, High Resolution Audio Insights, Library Exploration (+12 more)

### Community 115 - "MaestWindowContext"
Cohesion: 0.22
Nodes (15): _pad_or_trim_audio_tensor(), Tensor, MaestWindowContext, _optional_boundary(), _positive_finite(), select_maest_window_starts(), _selected_range(), test_pad_or_trim_audio_tensor_returns_fixed_length_float32() (+7 more)

### Community 116 - "tests/test_cli.py"
Cohesion: 0.21
Nodes (15): _FakeAnalysisManager, MonkeyPatch, Path, test_analyze_cli_passes_separate_ml_batch_sizes(), test_analyze_cli_prints_default_ml_progress_and_settings(), test_analyze_cli_rejects_unknown_device_before_opening_manager(), test_analyze_cli_runs_sonara_core_only(), test_relocate_library_cli_applies_typed_current_path_update() (+7 more)

### Community 117 - "optimize_database.py"
Cohesion: 0.19
Nodes (12): _backup_database(), _database_files(), _detect_database_kind(), _integrity_check(), main(), OptimizationSummary, optimize_database(), _optimize_one_database() (+4 more)

### Community 118 - "Q: Какая версия FAST API у меня сейчас?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Какая версия FAST API у меня сейчас?, Source Nodes

### Community 119 - "wave_tags.py"
Cohesion: 0.17
Nodes (14): Frame, _AudioWithId3Tags, _genre_frame_text(), _Id3Tags, Path, Protocol, _replace_id3_genre(), _require_readable_wave_audio() (+6 more)

### Community 120 - "ClassifierScoreDetail"
Cohesion: 0.15
Nodes (16): _classifier_summaries(), ClassifierScoreSummary, ClassifierScoreDetail, ClassifierScoreSummary, _manifest_payload(), _PublicClassifierReader, ClassifierScoreDetail, Path (+8 more)

### Community 121 - "TrackRecord"
Cohesion: 0.21
Nodes (20): _bpm_distance(), build_report(), choose_keeper(), confidence_category(), DuplicateGroup, _float_or_none(), _format_float(), format_rank() (+12 more)

### Community 122 - "FileRepairResult"
Cohesion: 0.20
Nodes (19): AudioDoctorCancelled, file_result_payload(), FileRepairResult, format_result(), format_status(), primary_action(), process_paths(), repair_file() (+11 more)

### Community 123 - "score_prompt_bank.py"
Cohesion: 0.33
Nodes (17): build_label_bank(), build_negative_banks(), embed_negative_prompts(), embed_prompt_ensemble(), l2norm(), load_audio_windows(), load_checkpoint_weights_only(), load_prompt_bank() (+9 more)

### Community 124 - "scripts"
Cohesion: 0.11
Nodes (17): devDependencies, @fontsource-variable/jetbrains-mono, vitepress, name, private, scripts, build, check (+9 more)

### Community 125 - "track_models.py"
Cohesion: 0.07
Nodes (63): canonical_file_path(), _chunks(), _genres_json(), _identity_from_row(), _library_roots_from_json(), _library_roots_json(), _normalized_audio_duration(), ordinal_path_key() (+55 more)

### Community 126 - "test_api_database_selection.py"
Cohesion: 0.18
Nodes (15): _add_track(), fixture, parametrize, Path, _selected_state(), _shared_ffmpeg(), test_database_file_dialog_switches_to_selected_current_bundle(), test_database_switch_creates_selected_current_bundle() (+7 more)

### Community 127 - "Workflows"
Cohesion: 0.25
Nodes (9): Workflows, Backed-Up Database Optimization, Explicit Single-Library Migration, Maintain a Library Safely, Bounded Reanalysis Pilot, Dependent Classifier Refresh, Legacy Split-Storage Migration, Reanalyze SONARA Data (+1 more)

### Community 128 - "api_routes_analysis.py"
Cohesion: 0.17
Nodes (19): HTTPException, AnalysisResetResult, query_classifier_min_scores(), valid_classifier_min_scores(), _classifier_info_by_key(), _classifier_manifest_error_text(), _outputs_for_family(), FastAPI (+11 more)

### Community 129 - "loadTrainingReadiness"
Cohesion: 0.39
Nodes (18): calibrateClassifier(), fileName(), handleTrainingActionClick(), loadTrainingReadiness(), parseRefreshResponse(), pollTrainingProgress(), promoteClassifier(), refreshCandidates() (+10 more)

### Community 130 - "run_report"
Cohesion: 0.24
Nodes (18): CancelCheck, ProgressCallback, _attach_embeddings(), AudioDedupCancelled, _connect_readonly(), count_database_tracks(), find_duplicate_groups(), load_tracks() (+10 more)

### Community 131 - "Personal Classifier Workflow"
Cohesion: 0.17
Nodes (17): Feature Ablation Benchmark, Calibration Data Gate, Database-Only Classifier Scoring, Immutable Generation Promotion, Ordered Classifier Feature Recipe, Personal Classifier Workflow, Reusable Ranking Signal, Not Truth, Rhythm Lab Isolated State (+9 more)

### Community 132 - "test_scan_jobs.py"
Cohesion: 0.26
Nodes (16): ScanJobPayload, _audio(), Path, test_duration_filtered_scan_limit_counts_only_eligible_tracks(), test_limited_scan_does_not_mark_unseen_tracks_missing(), test_parallel_scan_uses_process_workers_and_writes_on_calling_thread(), test_parallel_scan_writes_ready_batches_before_all_paths_are_prepared(), test_prepare_audio_path_group_reads_duration_once() (+8 more)

### Community 133 - "ClassifierSpecification"
Cohesion: 0.13
Nodes (19): LibrarySummary, ClassifierSpecification, _assemble_summaries(), _base_select_fields(), _classifier_specifications_by_key(), LibraryQueryRepository, Path, TrackIdentity (+11 more)

### Community 134 - "qa_database.py"
Cohesion: 0.23
Nodes (16): _build_parser(), _fail(), _foreign_key_check(), _integrity_check(), main(), _open_read_only(), ArgumentParser, Connection (+8 more)

### Community 135 - "read_local_evidence"
Cohesion: 0.22
Nodes (14): _find_by_metadata(), _find_by_path(), Connection, Path, Row, Return tags and at most three MAEST genres from one unambiguous local track., read_local_evidence(), Path (+6 more)

### Community 136 - "judged.py"
Cohesion: 0.23
Nodes (18): build_judged_label_gate(), _first_label_for_any_source(), judged_label_guidance(), judged_label_status(), _labels_by_rating(), matched_judged_labels(), MatchedJudgedLabel, matching_label() (+10 more)

### Community 137 - "api_routes_search.py"
Cohesion: 0.11
Nodes (19): AbstractContextManager, _clap_text_search_plan(), _ClapTextSearchPlan, _clean_text_queries(), FastAPI, FloatArray, Protocol, register_search_routes() (+11 more)

### Community 138 - "Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?, Source Nodes

### Community 139 - "Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?, Source Nodes

### Community 140 - "test_break_energy.py"
Cohesion: 0.31
Nodes (11): _FixedProbabilityModel, _insert_track(), _mert_output(), ndarray, Path, test_break_energy_job_scores_tracks_with_required_rows(), test_break_energy_public_scorer_preserves_probability_precision(), test_classifier_artifact_loads_without_version_or_contract_identity() (+3 more)

### Community 141 - "models.py"
Cohesion: 0.15
Nodes (23): _artists(), _label(), Beatport v4 Catalog Search adapter using documented bearer authentication., _record(), _text(), _year(), Read local genre evidence without modifying a library database., _normalized() (+15 more)

### Community 142 - "Classifier Workflow"
Cohesion: 0.22
Nodes (13): Benchmark Variants, Broken vs Straight Beat Classifier, Classifier Workflow, Collect Labels, Local Music Library, Music Attribute Classifiers, Personal Music Classifiers, Production Readiness (+5 more)

### Community 143 - "Russian Project Overview"
Cohesion: 0.25
Nodes (8): Accepted Project Vocabulary, Report-First Maintenance Tools, Rhythm Lab Personal Classifiers, Russian CLAP Text Search Explanation, Russian Multi-Model Similarity Explanation, Russian Project Overview, Russian Report-First Helper Tools, Russian Rhythm Lab Explanation

### Community 144 - "AnalysisOutput"
Cohesion: 0.06
Nodes (17): EmbeddingModelRunner, AnalysisOutput, AnalysisVectorRow, AnalysisSearchRepository, EmbeddingFamily, Protocol, Public repository surface required by embedding search., Protocol (+9 more)

### Community 145 - "RhythmLabCollections"
Cohesion: 0.27
Nodes (13): Repository for review collections in the Rhythm Lab database only., RhythmLabCollections, MonkeyPatch, Path, _selection(), test_collection_append_never_rebinds_and_replace_is_explicit(), test_collection_catalog_mismatch_is_fail_closed(), test_collection_repository_rejects_legacy_labels_without_mutation() (+5 more)

### Community 146 - "run-vale.mjs"
Cohesion: 0.18
Nodes (12): baseValeArgs, collectMarkdownFiles(), walk(), docsRoot, markdownFiles, repoRoot, resolveVale(), runVale() (+4 more)

### Community 147 - "Search with Seed Tracks"
Cohesion: 0.26
Nodes (12): MERT Seed Search, Model Listening Lab, MuQ Seed Search, Ranked Candidates Are Not Guaranteed Compatibility, Search with Seed Tracks, Seed Search, SONARA Feature Search, Tempo Evidence Fallback (+4 more)

### Community 148 - "Know When Audio Files Can Be Written"
Cohesion: 0.24
Nodes (12): Audio Dedup Apply, Audio Doctor Apply, Explicit Audio Write Boundary, Know When Audio Files Can Be Written, MAEST Genre Tag Apply, Relocation Apply, Safe Library Maintenance, Separate Reanalysis and Retraining Choices (+4 more)

### Community 149 - "tooltipLayer.tsx"
Cohesion: 0.26
Nodes (10): clamp(), placeTooltip(), RectLike, SizeLike, TooltipPlacement, TooltipPosition, ActiveTooltip, rectToPlainObject() (+2 more)

### Community 150 - "test_run_server_lan_script.py"
Cohesion: 0.36
Nodes (11): CompletedProcess, MonkeyPatch, Path, skipif, _run_isolated_launcher(), test_explicit_lan_mode_uses_only_supplied_arguments(), test_explicit_local_mode_does_not_inject_a_database(), test_no_argument_launcher_accepts_custom_database_and_lan_mode() (+3 more)

### Community 151 - "ScannedFile"
Cohesion: 0.11
Nodes (39): Background and synchronous jobs for the sole scan repository path., _audio_format(), _audio_format_from_mime(), _contains_tag(), file_tags_from_metadata(), _genres(), iter_audio_files(), _positive_float_or_none() (+31 more)

### Community 152 - "text_prompt_benchmark.py"
Cohesion: 0.20
Nodes (20): int64, _centered(), LabelledConcept, _load_concepts(), _load_matrix(), main(), _measure(), _measure_family() (+12 more)

### Community 153 - "database.py"
Cohesion: 0.15
Nodes (16): _add_track(), fixture, Path, _shared_ffmpeg(), test_choose_folder_endpoint_allows_cancel(), test_choose_folder_endpoint_reports_unavailable_dialog(), test_choose_folder_endpoint_returns_selected_path(), test_create_app_requires_shared_ffmpeg() (+8 more)

### Community 154 - "Audio Online"
Cohesion: 0.20
Nodes (12): Audio Online, Beatport Client-Credentials OAuth, Exact Local Path Lookup, Local OAuth Configuration, Matched Does Not Mean Correct Genre, MusicBrainz User-Agent and Rate Limit, Provider Evidence Workbook, Standalone Read-Only Boundary (+4 more)

### Community 155 - "metadataReference.test.mjs"
Cohesion: 0.15
Nodes (9): detail(), metadataDialog, metadataDialogUi, referenceCompare, sonaraFeatures(), srcDir, summary(), syncopatedRhythm (+1 more)

### Community 156 - "rhythm_lab_impact_payload"
Cohesion: 0.31
Nodes (11): _candidate_identity(), _candidate_text(), _chunks(), cleanup_rhythm_lab_database(), _has_identity_columns(), _identity_predicate(), _T, TrackIdentity (+3 more)

### Community 157 - "build_report_payload"
Cohesion: 0.22
Nodes (10): build_report_payload(), RuntimeError, RepairRunResult, ReportResult, summarize_report_problem_types(), summarize_report_reason_counts(), summarize_report_status_counts(), _unique_report_path() (+2 more)

### Community 158 - "collect_repository_paths"
Cohesion: 0.24
Nodes (10): collect_db_paths(), collect_repository_paths(), paths_from_track_records(), Protocol, Resolve typed repository paths and count files absent on disk., Map canonical ``TrackPath.file_path`` values to local audio paths., Typed repository projection used for database-backed path collection., remap_db_track_path() (+2 more)

### Community 159 - "Normalized Prompt Ensemble"
Cohesion: 0.25
Nodes (9): Prompt Calibration Workflow, Hard-Negative Margin Scoring, Normalized Prompt Ensemble, CLAP Prompt Families, Text as Audible Shared-Embedding Anchor, Project CLAP Profiles, Positive Ensemble and Hard-Negative Contrast Scoring, Compact English CLAP Prompt Bank (+1 more)

### Community 160 - "validate_prompt_bank.py"
Cohesion: 0.39
Nodes (8): fail(), load_json(), main(), Any, Path, tokenish_count(), validate_bank(), warn()

### Community 161 - "_coverage_and_classifiers"
Cohesion: 0.20
Nodes (20): SonaraCore, _coverage_and_classifiers(), _current_classifier_details(), _file_tags(), _identity_map(), _json_ids(), _optional_float(), _optional_int() (+12 more)

### Community 162 - "run_server_launcher.py"
Cohesion: 0.36
Nodes (8): Popen, build_frontend_command(), build_server_command(), frontend_directory(), main(), Path, resolve_npm_executable(), stop_process()

### Community 163 - "Unified SQLite Music Library"
Cohesion: 0.44
Nodes (9): CLAP Text-to-Audio and Audio-to-Audio Search, Explicit Backup-First Legacy Database Migration, MAEST Genre and Audio Embedding, MERT Audio Embedding, Separated Model Evidence Sources, MuQ Audio Embedding, SONARA Audio Features, Unified SQLite Music Library (+1 more)

### Community 164 - "test_api_sonara_search.py"
Cohesion: 0.27
Nodes (18): _add_embedding_track(), _add_sonara_track(), _blob(), _float(), _mert_output(), parametrize, Path, _sonara_library() (+10 more)

### Community 165 - "workbook_bridge.mjs"
Cohesion: 0.28
Nodes (7): artifactToolPath, buildWorkbook(), main(), require, artifactToolPath, execFile, require

### Community 166 - "CLAP Query Workflow"
Cohesion: 0.29
Nodes (8): CLAP Query Workflow Agent Interface, CLAP Prompting Reference, Deterministic 10-Second Audio Segmentation, LAION-CLAP Music Configuration, Audio Read-Only CLAP Search Boundary, CLAP Query Workflow, Stored CLAP Database Seed Search, Temporary CLAP Audio Analysis Search

### Community 167 - "DJ Track Similarity Agent Instructions"
Cohesion: 0.36
Nodes (8): Local-First Safety Documentation Language, Active-Development Operating Model, Executable Sources as Authority, Graphify Codebase Query Workflow, Local-First Safety Baseline, Direct Main-Branch Development Workflow, DJ Track Similarity Agent Instructions, Risk-Scoped Verification Routing

### Community 168 - "Q: How does Rhythm Lab persist classifier scores?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: How does Rhythm Lab persist classifier scores?, Source Nodes

### Community 169 - "Temporary Current Set"
Cohesion: 0.36
Nodes (8): Temporary Current Set, Export a Playlist Preview, Local Path Export Privacy, M3U and CSV Playlist Export, Rhythm Lab Collection Save, Build Crates for Later Listening, Crate-Building Workflow, Crate as a Reviewed Pool

### Community 171 - "Response"
Cohesion: 0.25
Nodes (3): OAuth token requests must send fields as a form, not URL query data., Response, test_post_form_json_uses_urlencoded_post_body()

### Community 172 - "Codebase Documentation Writer"
Cohesion: 0.29
Nodes (7): Documentation Writer Agent Interface, Codebase Documentation Writer, Documentation Verification Workflow, Maintained Documentation Surface, Source-Grounded Documentation, VitePress Documentation Information Architecture, VitePress Documentation Pointer

### Community 173 - "OptimizerExample"
Cohesion: 0.20
Nodes (17): _bootstrap_stability(), _candidate_tie_break(), _example_score(), _examples_by_seed(), _examples_for_seeds(), _is_better_candidate(), _mean(), _metrics_for_examples() (+9 more)

### Community 175 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 176 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.25
Nodes (5): appSource, embeddingTabSource, panelSource, styles, trackPanelSource

### Community 178 - "Local-First DJ Library Workbench"
Cohesion: 0.29
Nodes (7): Browser-Local Current Set, Listening-Led Ranking Signals, Local-First DJ Library Workbench, Russian Project Limitations, Russian Local-First Workbench Description, DJ Set Dramaturgy, Three-Layer Set Compatibility Model

### Community 179 - "test_benchmark_search.py"
Cohesion: 0.35
Nodes (10): CompletedProcess, parametrize, Path, _run_benchmark(), _run_benchmark_raw(), test_benchmark_search_keep_db_preserves_current_bundle(), test_benchmark_search_rejects_invalid_vector_backend(), test_benchmark_search_rejects_output_that_overlaps_keep_db() (+2 more)

### Community 180 - "isMulticlassProfile"
Cohesion: 0.33
Nodes (9): assignedLabelStatus(), displayLabel(), isMulticlassProfile(), labelByKey(), nextStepText(), profileSignalText(), renderProfileControls(), trackStatusLine() (+1 more)

### Community 182 - "Rhythm Lab Page"
Cohesion: 0.29
Nodes (7): Track Filtering and Pagination, Rhythm Lab Process Control, Classifier Profile Management, Library, Candidates, and Collection Tabs, Rhythm Lab Page, Read-Only Source Database Loading, Training and Profile Creation UI

### Community 183 - "DJ Track Similarity Project Overview"
Cohesion: 0.47
Nodes (6): Accessible Non-Decorative Interaction Policy, CSS Custom-Property Token System, Dense Local Workbench Interface, DJ Track Similarity Design System, Responsive Panel and Internal-Scroll Layout, DJ Track Similarity Project Overview

### Community 184 - "DJ Track Similarity Dark Logo"
Cohesion: 0.53
Nodes (6): Audio Level Motif, Audio Waveform Motif, Dark Theme Palette, DJ Track Similarity, DJ Track Similarity Dark Logo, Vinyl Record Motif

### Community 185 - "CLAP Text Search"
Cohesion: 0.53
Nodes (6): Adaptive Negative Contrast, ANN Sidecar Exact-Search Fallback, CLAP Text Search, Positive Prompt Aggregation, Separate Score Surfaces, Search by Text with CLAP

### Community 186 - "Audio-Online/tests/test_cli.py"
Cohesion: 0.40
Nodes (5): Path, Token check reports the response status but never an access token., CLI authorization forwards only the config path and keeps secrets out of output., test_authorize_beatport_uses_local_config_without_printing_secret(), test_check_auth_beatport_reports_only_non_secret_status()

### Community 187 - "DJ Track Similarity"
Cohesion: 0.60
Nodes (5): Audio Signal Motif, DJ Track Similarity, DJ Track Similarity Light Logo, Similarity Spectrum, Vinyl Record

### Community 188 - "DatabaseValidationJobManager"
Cohesion: 0.26
Nodes (6): DatabaseValidationEvent, DatabaseValidationJobManager, DatabaseValidationJobStatus, Single-threaded lifecycle for explicit database validation., Path, test_validation_job_api_exposes_completed_job_and_its_ui_events()

### Community 189 - "config.mts"
Cohesion: 0.40
Nodes (4): commonTheme, englishNav, englishSidebar, SidebarSection

### Community 190 - "db_embeddings.py"
Cohesion: 0.17
Nodes (24): EmbeddingFamilySpec, current_track_identity(), _is_l2_unit_vector(), _positive_int(), Connection, ndarray, Row, Identity-aware embedding storage inside the single library database. (+16 more)

### Community 192 - "sonara_core_validation.py"
Cohesion: 0.21
Nodes (23): SonaraCoreRow, _exact_object(), _json_array(), _optional_int(), _optional_number(), _optional_text(), Canonical semantic validation for persisted SONARA Core rows., Validate one complete SONARA Core row against writer semantics. (+15 more)

### Community 193 - "playerAutoplay.test.mjs"
Cohesion: 0.50
Nodes (3): appPath, searchHookPath, trackRowsPath

### Community 195 - "sonaraSearchControls.test.mjs"
Cohesion: 0.50
Nodes (3): embeddingTabSource, panelSource, stylesSource

### Community 196 - "_track_from_row"
Cohesion: 0.50
Nodes (4): _json_string_list(), Row, _string_or_none(), _track_from_row()

### Community 197 - "Rhythm Lab Favicon"
Cohesion: 0.67
Nodes (4): Audio Waveform Motif, Recording Indicator, Rhythm Lab Favicon, Dark Rounded Square Background

### Community 198 - "DJ Track Similarity Favicon Artwork"
Cohesion: 1.00
Nodes (3): DJ Track Similarity Favicon Artwork, Horizontal Audio Bars, Vinyl Record

### Community 199 - "Music Favicon"
Cohesion: 1.00
Nodes (3): Music Favicon, Music Note, Vinyl Record

### Community 201 - "logging_config.py"
Cohesion: 0.28
Nodes (13): _archive_active_log_path(), _current_date_suffix(), _delete_old_log_backups(), _file_mtime_date_suffix(), install_asyncio_exception_logging(), project_file_handler(), ProjectStartupFileHandler, Path (+5 more)

### Community 224 - "db_library_queries.py"
Cohesion: 0.10
Nodes (30): _base_from_sql(), _current_analysis_row_count(), _current_artifact_row_count(), _filter_sql(), _fts_query(), _json_array(), _json_identity_rows(), _json_object() (+22 more)

### Community 225 - "textPromptPresets.ts"
Cohesion: 0.11
Nodes (26): applyPromptPresets(), changeTextEmbeddingFamily(), togglePromptPreset(), ClapSearchTab(), axisByKey(), ComposedPromptBanks, composePromptBanks(), defaultNegativeWeight (+18 more)

### Community 226 - "Q: как реализована передача аудио в MULAN"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как реализована передача аудио в MULAN, Source Nodes

### Community 227 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 228 - "classifier_scoring.py"
Cohesion: 0.09
Nodes (33): ClassifierFeatureRow, ClassifierScoreWrite, analyze_classifier(), _argmax_with_tiebreak(), classifier_artifact_slug(), _classifier_key_from_metadata_or_slug(), ClassifierScorer, default_classifier_model_path() (+25 more)

### Community 229 - "Q: Проанализируй реализацию извлечения эмбов в MULam в проекте"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Проанализируй реализацию извлечения эмбов в MULam в проекте, Source Nodes

### Community 230 - "Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA, Source Nodes

### Community 231 - "dj_track_similarity/cli.py"
Cohesion: 0.09
Nodes (67): command, parse_analysis_models_text(), analyze(), analyze_classifier(), analyze_pipeline(), classifier_calibration_report(), classifier_suggest_labels(), _db() (+59 more)

### Community 232 - "test_evaluation_weighted_candidates.py"
Cohesion: 0.38
Nodes (17): _candidate_row(), EvaluationRepository, MonkeyPatch, _score_profile(), _sonara_with_energy(), _summary_with_tags(), test_weighted_candidate_csv_row_contains_expected_manual_columns(), test_weighted_candidates_exclude_seed_and_tie_order_is_deterministic() (+9 more)

### Community 233 - "VerifiedAssetBinding"
Cohesion: 0.20
Nodes (14): BaseException, bind_verified_file(), bind_verified_snapshot(), _close_guard(), _copy_verified(), _open_read_only_guard(), _open_windows_read_only_guard(), Path (+6 more)

### Community 235 - "scanImportDialog.test.mjs"
Cohesion: 0.40
Nodes (4): appPath, dialogPath, panelPath, srcDir

### Community 236 - "recorded_sessions.py"
Cohesion: 0.10
Nodes (36): _Repository, _contains_legacy_version_identity(), _current_session(), _event_provenance_matches(), load_current_evaluation_sessions(), _mapping_sequence(), _persisted_snapshot_matches(), _positive_int_or_none() (+28 more)

### Community 237 - "project_text_search.py"
Cohesion: 0.27
Nodes (14): clean_lines(), db_path_from_env(), get_json(), main(), post_json(), print_results(), Any, Namespace (+6 more)

### Community 238 - "Q: Почему LibraryDatabase стал главным мостом между сообществами?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Почему LibraryDatabase стал главным мостом между сообществами?, Source Nodes

### Community 239 - "Q: Path from LibraryDatabase to AnalysisOutput"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Path from LibraryDatabase to AnalysisOutput, Source Nodes

### Community 240 - "Q: Trace AnalysisOutput through ClassifierScorer to classifier_scores"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Trace AnalysisOutput through ClassifierScorer to classifier_scores, Source Nodes

### Community 241 - "Q: Trace ClassifierJobManager through scoring to save_classifier_scores"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Trace ClassifierJobManager through scoring to save_classifier_scores, Source Nodes

### Community 242 - "Q: Trace AnalysisOutput to ClassifierFeatureRow to score_row"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Trace AnalysisOutput to ClassifierFeatureRow to score_row, Source Nodes

### Community 243 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 244 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 245 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 246 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 247 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 248 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 249 - "Q: го"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: го, Source Nodes

### Community 250 - "Q: classifier_score_counts в UI должен вызываться"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: classifier_score_counts в UI должен вызываться, Source Nodes

### Community 251 - "sonaraAnalysisMode.test.mjs"
Cohesion: 0.18
Nodes (10): apiClientPath, apiClientSource, apiPath, apiSource, appPath, appSource, frontendRoot, panelPath (+2 more)

### Community 252 - "ClassifierJobManager"
Cohesion: 0.12
Nodes (12): ClassifierCandidate, ClassifierJobManager, ClassifierJobStatus, ClassifierLogEvent, _ClassifierPayload, ClassifierTrackError, Exception, Path (+4 more)

### Community 253 - "rhythm_lab_collections.py"
Cohesion: 0.18
Nodes (19): _collection_tracks(), _configure_collection_connection(), ensure_review_collection_schema(), _immutable_read_only_connection(), _nonempty_path(), Connection, Path, Review-collection persistence for the separately owned Rhythm Lab database.… (+11 more)

### Community 254 - "Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть., Source Nodes

### Community 255 - "Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?, Source Nodes

### Community 256 - "Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?, Source Nodes

### Community 257 - "LibraryDatabase"
Cohesion: 0.08
Nodes (52): current_embedding_analysis_output(), Build current adapter identity without loading model weights., EmbeddingOutput, EmbeddingWrite, LibraryDatabase, Connection, EvaluationRepository, ndarray (+44 more)

### Community 258 - "test_api_tracks.py"
Cohesion: 0.32
Nodes (18): _add_track(), _client(), _liked_payload(), Path, TestClient, TrackIdentity, test_delete_track_removes_catalog_data_but_keeps_source_audio(), test_media_endpoint_reports_missing_audio_file_without_traceback() (+10 more)

### Community 259 - "AnalysisCandidate"
Cohesion: 0.06
Nodes (49): decode_analysis_batch(), DecodeFailure, DecodeAudio, A full-track decode error deferred to a model-specific recovery path., AnalysisCandidate, analyze_and_store_staged_ml(), cleanup_orphaned_ml_staging(), _decode_staged() (+41 more)

### Community 260 - "Q: Убери глобальный барьер и ожидание считывания всех файлов"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Убери глобальный барьер и ожидание считывания всех файлов, Source Nodes

### Community 261 - "Q: Анализ MULAN как декодируется?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Анализ MULAN как декодируется?, Source Nodes

### Community 262 - "Q: Проанализируй изменения TorchCodec 0.16.0 и CUDA-производительность применительно к аудио-анализу и отдельному SONARA fallback."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Проанализируй изменения TorchCodec 0.16.0 и CUDA-производительность применительно к аудио-анализу и отдельному SONARA fallback., Source Nodes

### Community 263 - "Q: Какие текущие точки декодирования и база путей нужны для честного бенчмарка аудиодекодеров?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Какие текущие точки декодирования и база путей нужны для честного бенчмарка аудиодекодеров?, Source Nodes

### Community 264 - "Q: Какие новые нативные возможности TorchCodec 0.16, TorchAudio 2.11 и PyTorch заменяют пользовательскую логику decode, mono, resample и window preparation в dj-track-similarity?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Какие новые нативные возможности TorchCodec 0.16, TorchAudio 2.11 и PyTorch заменяют пользовательскую логику decode, mono, resample и window preparation в dj-track-similarity?, Source Nodes

### Community 265 - "Q: Как закрепить анализ ML моделей MAEST MERT MuQ MuLan CLAP с TorchCodec и конечным FFmpeg fallback?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Как закрепить анализ ML моделей MAEST MERT MuQ MuLan CLAP с TorchCodec и конечным FFmpeg fallback?, Source Nodes

### Community 266 - "Q: Давай уже определим: WavDecoder или AudioDecoder для ML моделей, которым нужен mono?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Давай уже определим: WavDecoder или AudioDecoder для ML моделей, которым нужен mono?, Source Nodes

### Community 267 - "Q: analysis pipeline job queue decode decoded embedding runner sonara maest mert muq"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: analysis pipeline job queue decode decoded embedding runner sonara maest mert muq, Source Nodes

### Community 268 - "Q: Как выполнить контракт maest_infer_input_contract.json через проект с TorchCodec 0.16?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Как выполнить контракт maest_infer_input_contract.json через проект с TorchCodec 0.16?, Source Nodes

### Community 269 - "test_database_validation.py"
Cohesion: 0.58
Nodes (9): LibraryDatabase, Path, test_validate_database_cli_uses_concise_human_messages(), test_validator_reports_corrupt_embedding_payload(), test_validator_reports_each_track_and_does_not_mutate_database(), test_validator_reports_invalid_classifier_probabilities(), test_validator_reports_non_finite_sonara_feature_vector(), test_validator_warns_when_stored_track_path_is_missing() (+1 more)

### Community 270 - "Q: как определяются есть ли уже трек в базе или нет при загркузке новых?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как определяются есть ли уже трек в базе или нет при загркузке новых?, Source Nodes

### Community 271 - "handle_asyncio_exception_context"
Cohesion: 0.29
Nodes (8): AbstractEventLoop, ConnectionResetError, _connection_reset_code(), handle_asyncio_exception_context(), _is_windows_transport_reset(), _safe_asyncio_context(), test_asyncio_transport_reset_is_logged_without_default_traceback(), test_unknown_asyncio_exception_is_logged_and_forwarded()

### Community 272 - "test_api_runtime.py"
Cohesion: 0.24
Nodes (14): Local dj-track-similarity toolkit., _client(), Path, TestClient, test_classifier_preflight_conflict_returns_http_409_before_start(), test_database_switch_bootstraps_clean_selected_current_bundle(), test_exclusive_database_operation_blocks_new_jobs(), test_job_start_reservation_closes_exclusive_operation_toctou() (+6 more)

### Community 274 - "Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе., Source Nodes

### Community 275 - "Q: Почему данные в базу не пишутся?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Почему данные в базу не пишутся?, Source Nodes

### Community 276 - "trackMarkup"
Cohesion: 0.13
Nodes (18): badgeRow(), displayTrackTitle(), featuresIndicator(), featuresReady(), featureStateReason(), featureStateStatus(), formatMaestGenreLabel(), genreBadges() (+10 more)

### Community 277 - "Q: где проблема"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: где проблема, Source Nodes

### Community 278 - "loadCandidates"
Cohesion: 0.22
Nodes (17): submitPageInput(), bpmFilterValue(), currentPage(), jumpToPage(), loadCandidates(), loadCollectionTracks(), loadLikedTracks(), loadSettingsView() (+9 more)

### Community 279 - "User Guide"
Cohesion: 0.40
Nodes (5): Listening-Led Shortlisting, DJ Library UI Workbench, User Guide, Outcome-Oriented Workflow Routing, Preview-First Working Habit

### Community 280 - "rank_maest_genres"
Cohesion: 0.36
Nodes (6): rank_genres(), rank_maest_genres(), Turn MAEST genre logits, already activated by the model adapter, into labels., Average MAEST genre scores from each track's analysis windows, then rank., test_rank_genres_orders_scores_and_limits_results(), test_rank_maest_genres_averages_each_tracks_windows_before_top_k()

### Community 281 - "test_classifier_jobs.py"
Cohesion: 0.35
Nodes (10): _insert_present_classifier_inputs(), _insert_track(), _mert_output(), MonkeyPatch, Path, Create more persisted classifier inputs than one job batch holds., _requirements(), _score_count() (+2 more)

### Community 282 - "api_routes_rhythm_lab.py"
Cohesion: 0.14
Nodes (15): RhythmLabSourceBinding, BaseModel, FastAPI, model_validator, register_rhythm_lab_routes(), RhythmLabCollectionSaveRequest, build_rhythm_lab_collection_selection_exact(), default_rhythm_lab_labels_path() (+7 more)

### Community 283 - "test_config.py"
Cohesion: 0.33
Nodes (6): CaptureFixture, Path, Prevent silently sending a credential to an unimplemented service., Prevent OAuth session material from leaking into normal CLI output., test_load_config_rejects_unknown_configured_source(), test_save_auth_data_persists_session_without_printing_secret()

### Community 284 - "test_classifier_manifest.py"
Cohesion: 0.68
Nodes (7): _manifest_payload(), Path, test_manifest_derives_input_families_from_ordered_feature_names(), test_manifest_rejects_duplicate_feature_names(), test_mulan_manifest_checks_current_embedding_dimension(), test_muq_manifest_checks_current_embedding_dimension(), _write_manifest()

### Community 285 - "install_standard_stream_logging"
Cohesion: 0.33
Nodes (7): Handler, Logger, _detach_standard_stream_file_handler(), _detach_standard_stream_file_handlers(), install_standard_stream_logging(), Mirror direct stdout/stderr writes into the configured app file log., _wrap_standard_stream()

### Community 286 - "api_routes_database.py"
Cohesion: 0.53
Nodes (5): FastAPI, Path, register_database_routes(), DatabaseStateResponse, DatabaseSwitchRequest

### Community 287 - "db_search_fts.py"
Cohesion: 0.25
Nodes (12): delete_track_search_fts(), _file_genres_text(), _maest_genres_text(), Connection, Track-search FTS maintenance. The FTS index contains only text a person can…, Delete one track from the live FTS index without committing., Refresh one track's human-text FTS row without committing., Rebuild the human-text FTS index atomically. If the caller already owns a… (+4 more)

### Community 293 - "storage_database_paths"
Cohesion: 0.24
Nodes (11): _load_script(), Path, test_optimize_database_backs_up_library_and_existing_evaluation_sidecar(), test_optimize_database_does_not_reject_future_library_tables(), test_optimize_database_handles_generic_sqlite_file(), Path, Filesystem topology for the library and optional Evaluation sidecar., Optional sidecars belonging to one library catalog. (+3 more)

### Community 294 - "_scan_track"
Cohesion: 0.52
Nodes (6): Path, TrackIdentity, _scan_track(), test_export_endpoint_writes_current_track_list_without_saving_playlist(), test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(), test_saved_playlist_endpoint_is_absent()

### Community 295 - "test_qa_database_script.py"
Cohesion: 0.70
Nodes (4): _load_script(), Path, test_qa_database_allows_future_library_tables(), test_qa_database_checks_library_and_optional_evaluation()

### Community 302 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 303 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 304 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 305 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 306 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 311 - "validate_maest_analysis_row"
Cohesion: 0.26
Nodes (10): MaestAnalysisRow, Explicitly repair MAEST syncopated-rhythm flags from stored genres., parse_maest_genres_json(), Canonical semantic validation for persisted MAEST analysis rows., Validate one complete MAEST analysis row against writer semantics., Parse canonical MAEST genre JSON without silently dropping entries., _required_int(), _required_text() (+2 more)

### Community 313 - "Prompt Bank Curator"
Cohesion: 0.20
Nodes (9): Axes, Genres, Granularity Honesty, Layer Boundary, Prompt Bank Curator, Source Of Truth, Verification, What A Good Label Looks Like (+1 more)

## Ambiguous Edges - Review These
- `Recording Indicator` → `Rhythm Lab Favicon`  [AMBIGUOUS]
  tools/rhythm-lab/rhythm_lab/static/favicon.svg · relation: references

## Knowledge Gaps
- **506 isolated node(s):** `DatabaseValidationEvent`, `_UnusedClassifierJobs`, `SizeLike`, `TooltipPlacement`, `ActiveTooltip` (+501 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `DecodedAudio` (9× useful, score=7.269177866)
- `EmbeddingModelRunner` (9× useful, score=7.262935176)
- `MaestEmbeddingAdapter` (5× useful, score=4.043629368)
- `ClassifierScoreWrite` (5× useful, score=3.926268937)
- `ScanJobManager` (4× useful, score=3.425973683)
- `MertEmbeddingAdapter` (4× useful, score=3.23211728)
- `MuqEmbeddingAdapter` (4× useful, score=3.23211728)
- `load_decoded_audio()` (4× useful, score=3.23110518)
- `scanner.py` (3× useful, score=2.574885712)
- `scan_jobs.py` (3× useful, score=2.566144268)

**Known dead ends** — questions that led nowhere; don't re-derive.
- "Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?" -> `docsRoot`

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Recording Indicator` and `Rhythm Lab Favicon`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `LibraryDatabase` connect `LibraryDatabase` to `test_api_tracks.py`, `run_report`, `test_scan_jobs.py`, `ClassifierSpecification`, `SonaraSimilaritySearch`, `FileTags`, `api_routes_search.py`, `test_audio_dedup.py`, `reports.py`, `test_break_energy.py`, `scan_library`, `test_api_runtime.py`, `AnalysisOutput`, `source_profile.py`, `score_profiles.py`, `database.py`, `test_classifier_jobs.py`, `evaluation/ablation.py`, `tags.py`, `risk_sweep.py`, `collect_repository_paths`, `calibration.py`, `test_api_sonara_search.py`, `test_repair_audio_metadata.py`, `storage_database_paths`, `test_qa_database_script.py`, `db_connection.py`, `TrackIdentity`, `_scan_track`, `db_analysis.py`, `transition_diagnostics.py`, `current_embedding_spec`, `export_seed_sample`, `create_app`, `test_sonara_storage.py`, `EvaluationRepository`, `benchmark_search.py`, `classifier_production.py`, `AnalysisPipelineManager`, `DatabaseValidationJobManager`, `rhythm_lab/cli.py`, `score_profile_optimizer.py`, `test_vector_index.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `candidates.py`, `seed_sampling.py`, `build_score_profile_optimizer_report`, `classifier_scoring.py`, `EmbeddingTrackIdentity`, `test_api_rhythm_lab.py`, `AppDatabaseState`, `dj_track_similarity/cli.py`, `AnalysisTarget`, `SimilaritySearch`, `main`, `recorded_sessions.py`, `tests/test_cli.py`, `ClassifierJobManager`, `track_models.py`, `test_api_database_selection.py`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Why does `TrackIdentity` connect `TrackIdentity` to `LibraryDatabase`, `test_api_tracks.py`, `FileTags`, `ClassifierSpecification`, `api_schemas.py`, `AnalysisOutput`, `tags.py`, `database.py`, `api_routes_rhythm_lab.py`, `rhythm_lab_impact_payload`, `_scan_track`, `compute_transition_diagnostics`, `transition_diagnostics.py`, `export_seed_sample`, `EvaluationRepository`, `_required_text`, `test_vector_index.py`, `TrackSummary`, `candidates.py`, `tempo_resolution.py`, `db_library_queries.py`, `EvaluationRepository`, `test_api_rhythm_lab.py`, `AppDatabaseState`, `main`, `recorded_sessions.py`, `rhythm_lab_collections.py`, `track_models.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `AnalysisOutput` connect `AnalysisOutput` to `AnalysisJobManager`, `LibraryDatabase`, `api_routes_analysis.py`, `sonara_similarity_scoring.py`, `AnalysisCandidate`, `ClassifierSpecification`, `SonaraSimilaritySearch`, `test_break_energy.py`, `ann_index.py`, `PersistentAnnVectorSearchBackend`, `AnalysisBatchItem`, `test_consumers.py`, `test_classifier_jobs.py`, `_coverage_and_classifiers`, `test_api_sonara_search.py`, `db_analysis.py`, `classifier_manifest.py`, `test_multi_model_analysis_jobs.py`, `current_embedding_spec`, `export_seed_sample`, `create_app`, `test_sonara_storage.py`, `sonara_features.py`, `benchmark_search.py`, `test_vector_index.py`, `artifact_io.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `sonara_storage.py`, `candidates.py`, `analysis_models.py`, `db_library_queries.py`, `classifier_scoring.py`, `EvaluationRepository`, `AnalysisTarget`, `SimilaritySearch`, `recorded_sessions.py`, `SonaraStagingConfig`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 120 inferred relationships involving `LibraryDatabase` (e.g. with `_active_embedding_output()` and `_insert_synthetic_tracks()`) actually correct?**
  _`LibraryDatabase` has 120 INFERRED edges - model-reasoned connections that need verification._
- **Are the 94 inferred relationships involving `AnalysisOutput` (e.g. with `_active_embedding_output()` and `_store_synthetic_embeddings()`) actually correct?**
  _`AnalysisOutput` has 94 INFERRED edges - model-reasoned connections that need verification._
- **Are the 90 inferred relationships involving `AnalysisTarget` (e.g. with `_store_synthetic_embeddings()` and `_candidates_without_seed()`) actually correct?**
  _`AnalysisTarget` has 90 INFERRED edges - model-reasoned connections that need verification._
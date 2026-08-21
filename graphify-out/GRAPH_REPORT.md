# Graph Report - dj-track-similarity  (2026-08-21)

## Corpus Check
- 440 files · ~416,285 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6739 nodes · 18997 edges · 310 communities (275 shown, 35 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1620 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `764c39b4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- AnalysisJobManager
- test_sonara_similarity.py
- label_transfer.py
- source_db.py
- database.py
- Main project
- weighted_candidates.py
- RhythmLabDatabase
- App
- app.js
- test_audio_dedup.py
- metrics.py
- scan_library
- analysis_model_runners.py
- ann_index.py
- api_schemas.py
- Reference Index
- test_ann_runtime.py
- ScanJobManager
- api.ts
- db_analysis.py
- TrackInput
- web_app.py
- test_consumers.py
- score_profiles.py
- tags.py
- db_migration.py
- evaluation/ablation.py
- TrackMetadataDialog.tsx
- risk_sweep.py
- Features, embeddings, and tags
- LibraryDatabase
- metadata_enrichment_cli.py
- source_profile.py
- candidates.py
- ndarray
- ClapEmbeddingAdapter
- test_repair_audio_metadata.py
- features.py
- test_api_analysis_jobs.py
- sonara_similarity_scoring.py
- TrackIdentity
- MLStagingConfig
- logging_config.py
- EvaluationRepository
- classifier_manifest.py
- test_multi_model_analysis_jobs.py
- transition_diagnostics.py
- AnalysisOutput
- verified_assets.py
- calibration.py
- compute_transition_diagnostics
- EvaluationRepository
- TextEmbeddingAdapterCache
- sonara_features.py
- SearchPlaylistPanel.tsx
- benchmark_search.py
- ReferenceComparePanel.tsx
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
- ClassifierRequirements
- frontend/package.json
- artifact_io.py
- ffmpeg_runtime.py
- test_classifier_scoring.py
- test_api_reference_compare.py
- TrackSummary
- sonara_storage.py
- ClassifierFeatureRow
- tempo_resolution.py
- audio_doctor/core.py
- training.py
- Any
- api_routes_tags_export.py
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
- BaseModel
- recorded_sessions.py
- audio_dedup/core.py
- current_embedding_spec
- compilerOptions
- .random_target
- _move_maest_runtime_modules
- text_tag_crosscheck.py
- AppDatabaseState
- select_torch_device
- vector_index.py
- SimilaritySearch
- main
- PresetConfig
- parseJsonResponse
- handle_asyncio_exception_context
- media_preview.py
- SonaraStagingConfig
- api_routes_evaluation.py
- DJ Track Similarity Banner
- MaestWindowContext
- tests/test_cli.py
- optimize_database.py
- Q: Какая версия FAST API у меня сейчас?
- audio_loader.py
- _PublicClassifierReader
- TrackRecord
- FileRepairResult
- score_prompt_bank.py
- scripts
- track_models.py
- test_api_database_selection.py
- Workflows
- test_vector_index.py
- loadTrainingReadiness
- run_report
- Personal Classifier Workflow
- install_standard_stream_logging
- db_library_queries.py
- qa_database.py
- read_local_evidence
- reports.py
- api_routes_search.py
- Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?
- Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?
- test_break_energy.py
- models.py
- Classifier Workflow
- Russian Project Overview
- test_reference_compare_uses_current_outputs_and_current_summaries
- test_rhythm_lab_bridge.py
- run-vale.mjs
- Search with Seed Tracks
- Know When Audio Files Can Be Written
- tooltipLayer.tsx
- test_run_server_lan_script.py
- FileTags
- StandardStreamLogMirror
- test_api_dialog.py
- Audio Online
- metadataReference.test.mjs
- rhythm_lab_impact_payload
- build_report_payload
- collect_repository_paths
- Normalized Prompt Ensemble
- validate_prompt_bank.py
- DatabaseValidationJobManager
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
- write_csv_rows
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- Local-First DJ Library Workbench
- loadActive
- isMulticlassProfile
- test_analysis_sonara_preflight.py
- Rhythm Lab Page
- DJ Track Similarity Project Overview
- DJ Track Similarity Dark Logo
- CLAP Text Search
- Audio-Online/tests/test_cli.py
- DJ Track Similarity
- create_app
- config.mts
- test_database_validation.py
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
- runtime.py
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
- _parse_args
- Empty Rejection Vocabulary
- dj-track-similarity
- _SonaraStatusRepository
- textPromptPresets.ts
- Q: как реализована передача аудио в MULAN
- What You Must Do When Invoked
- test_api_rhythm_lab.py
- Q: Проанализируй реализацию извлечения эмбов в MULam в проекте
- Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA
- dj_track_similarity/cli.py
- build_weighted_candidate_pool
- register_server_routes
- classifier_scoring.py
- scanImportDialog.test.mjs
- _Repository
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
- db_search_fts.py
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
- Namespace
- Q: как определяются есть ли уже трек в базе или нет при загркузке новых?
- Path
- test_api_runtime.py
- playlistAddHandler.test.mjs
- Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе.
- Q: Почему данные в базу не пишутся?
- RuntimeError
- Q: где проблема
- User Guide
- FloatArray
- test_classifier_jobs.py
- api_routes_rhythm_lab.py
- test_config.py
- test_api_evaluation.py
- _scan_track
- useConfirmation
- Protocol
- BaseModel
- model_validator
- Tensor
- test_benchmark_search.py
- DatabaseValidator
- storage_database_paths
- test_qa_database_script.py
- parametrize
- rank_maest_genres
- api_routes_analysis.py
- graphify reference: extra exports and benchmark
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- validate_maest_analysis_row
- TransitionTrack
- Prompt Bank Curator
- _ReadyClassifier
- textPromptPresets.test.mjs

## God Nodes (most connected - your core abstractions)
1. `LibraryDatabase` - 307 edges
2. `AnalysisOutput` - 198 edges
3. `AnalysisTarget` - 160 edges
4. `RhythmLabDatabase` - 86 edges
5. `TrackIdentity` - 83 edges
6. `AnalysisJobManager` - 82 edges
7. `App()` - 80 edges
8. `EvaluationRepository` - 65 edges
9. `create_app()` - 64 edges
10. `AnalysisCandidate` - 63 edges

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

## Communities (310 total, 35 thin omitted)

### Community 0 - "AnalysisJobManager"
Cohesion: 0.07
Nodes (40): AnalysisJobStatus, Item, RunnerFactory, AnalysisJobStatus, AnalysisLogEvent, AnalysisModelProgress, AnalysisTrackError, AnalysisTrackOutcome (+32 more)

### Community 1 - "test_sonara_similarity.py"
Cohesion: 0.22
Nodes (37): SONARA feature-mixer search over current Core data. The separate 48-dimensional…, SonaraSimilaritySearch, _add_sonara_track(), _add_track_without_sonara(), _core_row(), _feature_value(), _float_or_none(), _int_or_none() (+29 more)

### Community 2 - "label_transfer.py"
Cohesion: 0.08
Nodes (104): _absolute_lexical_path(), _backup_restore_target(), _build_parser(), build_rebound_bundle(), _build_restore_plan(), _canonical_json_bytes(), _canonical_json_text(), canonical_path_key() (+96 more)

### Community 3 - "source_db.py"
Cohesion: 0.05
Nodes (75): FileTags, _attach_labels(), _base_track_query(), _clean_path_text(), _count_sonara_features(), _embedding_family(), _embedding_vector(), _feature_counts() (+67 more)

### Community 4 - "database.py"
Cohesion: 0.11
Nodes (37): FingerprintOutput, One versioned SONARA acoustic fingerprint in native base64 form., TrackIdentity, collect_analysis_candidates(), current_sonara_target_keys(), _current_tracks(), _maest_window_context(), missing_outputs_for_target() (+29 more)

### Community 5 - "Main project"
Cohesion: 0.06
Nodes (32): Audio Dedup, Audio Doctor, Audio Online, Commands and arguments, `dj-sim analyze`, `dj-sim analyze-classifier CLASSIFIER`, `dj-sim analyze-pipeline`, `dj-sim classifier calibration-report` (+24 more)

### Community 6 - "weighted_candidates.py"
Cohesion: 0.11
Nodes (29): CandidatePoolRow, _clean_sources(), _effective_source_count(), _identity_payload(), _int_value(), _non_negative_finite_float(), _normalized_response_score(), _optional_number() (+21 more)

### Community 7 - "RhythmLabDatabase"
Cohesion: 0.07
Nodes (55): _canonical_json(), _classifier_label_from_row(), _classifier_label_queue_table_sql(), _classifier_labels_table_sql(), _classifier_predictions_table_sql(), _classifier_training_checkpoints_table_sql(), ClassifierLabel, ClassifierPredictionWrite (+47 more)

### Community 8 - "App"
Cohesion: 0.07
Nodes (66): App(), addVisibleTracksToPlaylist(), adoptClassifierProfiles(), applyPromptPresets(), beginGenericSearchRequest(), cancelGenericSearchRequest(), cancelTrackDetailRequest(), changeTextEmbeddingFamily() (+58 more)

### Community 9 - "app.js"
Cohesion: 0.04
Nodes (69): badgeRow(), binaryLabelGridEl, bpmMaxEl, bpmMinEl, candidateFiltersEl, candidateMinBrokenEl, candidateMinPositiveEl, candidatePredictedEl (+61 more)

### Community 10 - "test_audio_dedup.py"
Cohesion: 0.18
Nodes (40): _create_library_db(), _create_rhythm_lab_db(), _current_embedding_fixture(), _identity_tuple(), _insert_track(), _load_dedup_module(), CaptureFixture, MonkeyPatch (+32 more)

### Community 11 - "metrics.py"
Cohesion: 0.18
Nodes (39): _aggregate_variant_metrics(), average_precision_at_k(), _axis_value(), bad_suggestion_rate_at_k(), _comparison_match_character(), _comparison_rank(), _comparison_reason_tags(), dcg_at_k() (+31 more)

### Community 12 - "scan_library"
Cohesion: 0.13
Nodes (34): ScanStats, Scan one root through the sole TrackRepository write path., scan_library(), Aggregate result returned by the synchronous scanner., ScanStats, _library_roots(), _mert_output(), MonkeyPatch (+26 more)

### Community 13 - "analysis_model_runners.py"
Cohesion: 0.08
Nodes (23): ArrayLike, AnalysisBatchItem, _decoded_items(), default_model_runners(), EmbeddingModelRunner, _has_syncopated_rhythm(), _l2_normalize(), _maest_genres() (+15 more)

### Community 14 - "ann_index.py"
Cohesion: 0.09
Nodes (62): _active_index_output(), _artifact_path_from_manifest(), _artifact_paths(), _assert_inside_directory(), _benchmark_k_values(), benchmark_persistent_index(), _build_manifest(), build_persistent_index() (+54 more)

### Community 15 - "api_schemas.py"
Cohesion: 0.13
Nodes (34): field_validator, HTTPException, current_classifier_specifications(), query_classifier_min_scores(), valid_classifier_min_scores(), FastAPI, Path, register_library_routes() (+26 more)

### Community 16 - "Reference Index"
Cohesion: 0.05
Nodes (63): Explicit Audio Write Boundary, DJ Track Similarity Documentation Home, Local-First Ranked Workflow, Listening-Led Shortlisting, Project Guide, Analysis Families Reference, Database-Only Classifier Scoring, ML Embedding Families (+55 more)

### Community 17 - "test_ann_runtime.py"
Cohesion: 0.15
Nodes (13): fake_hnsw(), FakeAnalysisRepository, FakeHnswModule, Index, fixture, MonkeyPatch, ndarray, Path (+5 more)

### Community 18 - "ScanJobManager"
Cohesion: 0.11
Nodes (28): log_failure(), Collection, Exception, Path, Run parallel discovery work against one thread-safe TrackRepository., Prepare bounded path batches and write ready results on this thread., Apply worker results to job state without writing to SQLite., ScanJobManager (+20 more)

### Community 19 - "api.ts"
Cohesion: 0.05
Nodes (59): AnalysisCoverage, AnalysisJobStatus, AnalysisPipelineRequest, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail, ClassifierScoreSummary (+51 more)

### Community 20 - "db_analysis.py"
Cohesion: 0.07
Nodes (44): AnalysisResetResult, AnalysisWriteRepository, _store_staged_sonara_write(), AnalysisWriteResult, ClassifierCandidate, MaestWrite, Raised when a write target no longer names the current track content., SonaraWrite (+36 more)

### Community 21 - "TrackInput"
Cohesion: 0.09
Nodes (36): BeatportSource, DiscogsSource, _first_label(), Discogs database adapter using only its documented API surface., _strings(), _track_title(), LastFmSource, Last.fm community tag adapter. (+28 more)

### Community 22 - "web_app.py"
Cohesion: 0.06
Nodes (52): _artifact_feature(), _artifact_feature_summary(), _artifact_groups(), _artifact_metrics_path(), _artifact_source_data_readiness(), _artifact_summary(), _bind_artifact_source_readiness(), CalibrateRequest (+44 more)

### Community 23 - "test_consumers.py"
Cohesion: 0.19
Nodes (47): PredictionProgressCallback, apply_model_to_lab(), Mostly read-only Rhythm Lab view over one library database., SourceDatabase, create_app(), _complete_all_tracks_for_rhythm_lab(), _create_focused_profile(), _insert_complete_rhythm_lab_rows() (+39 more)

### Community 24 - "score_profiles.py"
Cohesion: 0.12
Nodes (45): build_score_profile_application_report(), build_score_profile_from_source_report(), _candidate_source_contributions(), _clean_k_values(), _consensus_summary(), _empty_metrics(), _limitations(), _limitations_are_explicit() (+37 more)

### Community 25 - "tags.py"
Cohesion: 0.05
Nodes (80): Frame, ID3, GenreTagCandidate, _apply_genre_tag_to_candidate(), apply_genre_tags_to_tracks(), _clean_genre_label(), genre_tag_apply_summary(), _genre_tags_for_candidate() (+72 more)

### Community 26 - "db_migration.py"
Cohesion: 0.05
Nodes (96): RLock, Path, _bootstrap_file_lock(), _bootstrap_lock_path(), _cleanup_staged_sqlite(), _configure_connection(), connect_database(), _create_fresh_library() (+88 more)

### Community 27 - "evaluation/ablation.py"
Cohesion: 0.10
Nodes (50): _ablated_signal(), _build_session_variants(), build_source_ablation_report(), _candidate_contributions_from_source_ranks(), _candidate_event(), _candidate_pool_sessions(), CandidateEvent, CandidatePoolSession (+42 more)

### Community 28 - "TrackMetadataDialog.tsx"
Cohesion: 0.06
Nodes (56): SonaraCore, formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureDescriptor (+48 more)

### Community 29 - "risk_sweep.py"
Cohesion: 0.10
Nodes (51): _average_transition_risk_at_k(), _best_by_metric(), _best_source_rank(), build_risk_penalty_sweep_report(), _candidate_payload(), _candidate_with_risk_weight(), _clean_k_values(), _clean_risk_weights() (+43 more)

### Community 30 - "Features, embeddings, and tags"
Cohesion: 0.06
Nodes (53): Classifiers and Rhythm Lab, Database-only classifier scoring, Immutable-generation promotion, Personal classifier, Rhythm Lab workflow, CLAP audio embedding, Features, embeddings, and tags, File tags (+45 more)

### Community 31 - "LibraryDatabase"
Cohesion: 0.11
Nodes (51): LibraryDatabase, Connection, EvaluationRepository, ndarray, _add_track(), Path, test_classifier_score_counts_use_keys_and_count_rows_only(), test_public_library_filter_combines_search_and_liked_state() (+43 more)

### Community 32 - "metadata_enrichment_cli.py"
Cohesion: 0.10
Nodes (46): FormPost, JsonGet, Request, authorize_lastfm(), Explicit documented authorization flows for sources that support them., Open Last.fm consent and exchange its one-time token for a session key., _access_token(), _auth_values() (+38 more)

### Community 33 - "source_profile.py"
Cohesion: 0.17
Nodes (37): build_source_profile(), _clean_profile_request(), _clean_sources(), _clean_top_k_values(), _consensus_report(), _coverage_fallback_factors(), _effective_sources(), _int_value() (+29 more)

### Community 34 - "candidates.py"
Cohesion: 0.13
Nodes (29): _analysis_target(), _blind_candidate_rows(), _CandidateAccumulator, CandidateExportRequest, CandidateExportResult, CandidateSourceContribution, _clean_sources(), _collect_candidates_for_seed() (+21 more)

### Community 35 - "ndarray"
Cohesion: 0.12
Nodes (15): DecodedAudio, _array_output_to_numpy(), _average_l2_window_embeddings(), _normalize_rows(), _normalized_embedding_rows(), ndarray, Embed a whole prompt bank in one forward pass., Verify model assets and construct the configured loader. (+7 more)

### Community 36 - "ClapEmbeddingAdapter"
Cohesion: 0.11
Nodes (21): parametrize, _text_embedding_adapter(), ClapEmbeddingAdapter, MaestEmbeddingAdapter, MertEmbeddingAdapter, MuqEmbeddingAdapter, MuqMulanEmbeddingAdapter, Verify model assets and construct the configured loader. (+13 more)

### Community 37 - "test_repair_audio_metadata.py"
Cohesion: 0.12
Nodes (45): _aiff_chunk(), _load_repair_module(), _minimal_aiff_with_empty_id3_chunks(), _minimal_pcm_wave(), Path, _riff_chunk(), test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload(), test_apply_forces_single_worker() (+37 more)

### Community 38 - "features.py"
Cohesion: 0.15
Nodes (25): build_feature_matrix(), build_labeled_feature_matrix(), build_labeled_feature_matrix_from_sources(), _cached_embedding_vectors(), _feature_names(), feature_recipe_readiness(), _feature_state_payload(), FeatureMatrix (+17 more)

### Community 39 - "test_api_analysis_jobs.py"
Cohesion: 0.20
Nodes (29): create_api_client(), MonkeyPatch, Path, TestClient, _analysis_start(), _client(), MonkeyPatch, parametrize (+21 more)

### Community 40 - "sonara_similarity_scoring.py"
Cohesion: 0.18
Nodes (32): _merge_targets(), _optional_targets(), _result_limit(), centroid(), clean_mixer_weights(), clean_modifiers(), ComparableTrack, custom_numeric_fields() (+24 more)

### Community 41 - "TrackIdentity"
Cohesion: 0.12
Nodes (40): SonaraFeatureRow, CsvRow, CsvRow, TrackIdentity, TrackSummary, Resolve tempo from one current summary and optional SONARA row., resolve_tempo_evidence(), Stable identity of one library track. (+32 more)

### Community 42 - "MLStagingConfig"
Cohesion: 0.14
Nodes (22): AnalysisJobConfig, build_analysis_job_config(), _int_in_range(), normalize_analysis_device(), normalize_analysis_models(), _normalize_limit(), normalize_sonara_mode(), MLStagingConfig (+14 more)

### Community 43 - "logging_config.py"
Cohesion: 0.22
Nodes (16): _archive_active_log_path(), _current_date_suffix(), _delete_old_log_backups(), event_log_level(), _file_mtime_date_suffix(), install_asyncio_exception_logging(), log_job_event(), project_file_handler() (+8 more)

### Community 44 - "EvaluationRepository"
Cohesion: 0.08
Nodes (37): _embedding_output(), EvaluationRepository, _identity(), identity_payload(), profile(), AnalysisCoverage, Any, TrackIdentity (+29 more)

### Community 45 - "classifier_manifest.py"
Cohesion: 0.12
Nodes (29): ClassifierArtifactPaths, ClassifierManifestSummary, _clean_classifier_key(), _feature_sources(), _invalid_manifest(), load_classifier_manifest_summary(), _manifest_error_text(), _optional_text() (+21 more)

### Community 46 - "test_multi_model_analysis_jobs.py"
Cohesion: 0.18
Nodes (14): _candidate(), _decoded(), _maest_output(), _mert_output(), Exception, Path, _Repository, _Runner (+6 more)

### Community 47 - "transition_diagnostics.py"
Cohesion: 0.13
Nodes (36): _best_relative_tempo_delta(), _bpm_risk(), _clamp(), _classifier_scores(), _clean_classifier_risk_weights(), _confidence_missingness_risk(), _contains_keyword(), _energy_curve_summary_values() (+28 more)

### Community 48 - "AnalysisOutput"
Cohesion: 0.07
Nodes (43): _write_outputs(), AnalysisOutput, AnalysisTarget, AnalysisVectorRow, AnalysisSearchRepository, _apply_epsilon(), _contrast_score_breakdown(), _contrast_vector_scores() (+35 more)

### Community 49 - "verified_assets.py"
Cohesion: 0.20
Nodes (14): BaseException, bind_verified_file(), bind_verified_snapshot(), _close_guard(), _copy_verified(), _open_read_only_guard(), _open_windows_read_only_guard(), Path (+6 more)

### Community 50 - "calibration.py"
Cohesion: 0.15
Nodes (38): _average_score(), _binary_label(), brier_score(), build_calibration_report(), _calibration_report(), _calibration_samples(), _calibration_status(), CalibrationSample (+30 more)

### Community 51 - "compute_transition_diagnostics"
Cohesion: 0.16
Nodes (29): compute_transition_diagnostics(), _mean_available(), Compute transition risk from identity-validated repository rows., _risk_version(), TransitionDiagnostics, _classifier_score(), ClassifierScoreSummary, test_adjacent_camelot_key_has_lower_risk_than_clash() (+21 more)

### Community 52 - "EvaluationRepository"
Cohesion: 0.14
Nodes (24): _canonical_json_value(), _clean_tags(), EvaluationRepository, _finite_float(), _json_load(), _json_object(), _json_text(), _load_track_snapshots() (+16 more)

### Community 53 - "TextEmbeddingAdapterCache"
Cohesion: 0.09
Nodes (22): AdapterT, _cache_key(), _CacheEntry, Keep one loaded text-embedding model per family and device. Building a fresh…, Return dropped weights to the CUDA allocator, not just to Python., Reuse one adapter per ``(family, device)`` across text search requests., Yield one adapter, held against eviction and other callers. Sync FastAPI…, Drop adapters nobody has used for longer than the idle TTL. (+14 more)

### Community 54 - "sonara_features.py"
Cohesion: 0.07
Nodes (37): Any, _analysis_mapping(), analysis_outputs_for_sonara_runtime(), analyze_and_store_sonara_batch(), Native SONARA batch orchestration for the analysis repository., Return the current SONARA Core, embedding, and fingerprint outputs., Analyze one native batch and persist successful results in input order.…, SonaraBatchTrackResult (+29 more)

### Community 55 - "SearchPlaylistPanel.tsx"
Cohesion: 0.07
Nodes (42): PromotedClassifier, SonaraMixerWeights, SonaraModifiers, SonaraSearchMode, classifierIsAvailable(), classifierProfileStatus(), classifierScoringBlockedReason(), filterAvailableClassifierValues() (+34 more)

### Community 56 - "benchmark_search.py"
Cohesion: 0.17
Nodes (30): _active_embedding_output(), _benchmark_database_path(), _benchmark_track_count(), BenchmarkConfig, _camelot_key(), _conflicting_kept_database_path(), _environment_summary(), _insert_synthetic_tracks() (+22 more)

### Community 57 - "ReferenceComparePanel.tsx"
Cohesion: 0.12
Nodes (28): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareResponse, ReferenceCompareVerdict, TrackIdentity, api, normalizeLimit(), orderedReferenceCompareGroups() (+20 more)

### Community 58 - "test_analysis_orchestration.py"
Cohesion: 0.08
Nodes (31): MaestAnalysisResult, _candidate(), _clap_output(), _decoded(), _EmbeddingWriteRepository, _FakeMaestAdapter, _FakeMertAdapter, _FakeMulanAdapter (+23 more)

### Community 59 - "rhythm_lab/ablation.py"
Cohesion: 0.17
Nodes (25): benchmark_profile_ablation(), cli_summary(), _compact_row(), _default_output_path(), _elapsed_seconds(), _metrics_summary(), _normalize_feature_sets(), _optional_float() (+17 more)

### Community 60 - "classifier_production.py"
Cohesion: 0.13
Nodes (32): build_classifier_calibration_report(), _calibration_report_status(), _candidate_feedback_aggregates(), _classifier_feedback_summary(), _classifier_score_detail(), ClassifierScoreRow, _clean_classifier_key(), _count_values() (+24 more)

### Community 61 - "AnalysisPipelineManager"
Cohesion: 0.08
Nodes (17): JobStatus, AnalysisPipelineManager, AnalysisPipelineStatus, _PipelinePayload, PipelineStageStatus, AnalysisStageQueue, One in-memory worker shared by SONARA, ML, and classifier stages., JobStore (+9 more)

### Community 62 - "jobUi.tsx"
Cohesion: 0.10
Nodes (28): ACTIVE_JOB_STATES, ActivityEvent, analysisJobRequest(), AnalysisProcessStatus(), analysisRuntimeLabel(), AUDIO_MODELS, calculateEta(), calculateProgressPercent() (+20 more)

### Community 63 - "rhythm_lab_launcher.py"
Cohesion: 0.15
Nodes (35): _clear_pid(), _file_size(), _is_rhythm_lab_process(), launch_rhythm_lab(), _listener_process_id(), _log_path(), _managed_process_id(), _mirror_log_to_console() (+27 more)

### Community 64 - "rhythm_lab/cli.py"
Cohesion: 0.13
Nodes (37): PromotionProgressCallback, _add_data_options(), _artifact_calibration_payload(), _artifact_matches_calibration_filter(), _benchmark_ablation(), build_parser(), _calibration_report(), _collection_list() (+29 more)

### Community 65 - "useLibraryState.ts"
Cohesion: 0.11
Nodes (39): Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts, libraryTrackIdentityKey() (+31 more)

### Community 66 - "escapeHtml"
Cohesion: 0.10
Nodes (38): actionIcon(), canPromoteArtifact(), coverageBadge(), escapeHtml(), formatFeatureGroupWeights(), formatHumanDate(), formatLabelCounts(), formatMetricDelta() (+30 more)

### Community 67 - "App.tsx"
Cohesion: 0.04
Nodes (56): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, AnalysisModel, defaultNotice (+48 more)

### Community 68 - "score_profile_optimizer.py"
Cohesion: 0.07
Nodes (80): _accepted_decision(), _assert_normalized_weights(), _base_report(), _bootstrap_stability(), build_saved_score_profile_payload(), build_score_profile_optimizer_report(), _candidate_tie_break(), _clean_k_values() (+72 more)

### Community 69 - "test_embedding.py"
Cohesion: 0.05
Nodes (33): adapter_factories(), BatchMaestAdapter, FakeClapAudioModel, FakeMertModel, FakeMertProcessor, FakeMulanModel, FakeMuqAudioModel, ndarray (+25 more)

### Community 70 - "labels.py"
Cohesion: 0.22
Nodes (22): _json_object(), _load_csv_labels(), _load_jsonl_labels(), load_pair_feedback_labels(), load_transition_feedback_labels(), _optional_text(), PairFeedbackLabel, _parse_pair_feedback_row() (+14 more)

### Community 71 - "ClassifierRequirements"
Cohesion: 0.22
Nodes (3): ClassifierRequirements, Fully validated immutable inputs for one promoted classifier., _validate_payload_identity()

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
Cohesion: 0.22
Nodes (27): _artifact_hash(), _insert_track(), _install_fake_joblib(), _manifest_payload(), _mert_output(), _muq_output(), _ProbabilityModel, Exception (+19 more)

### Community 76 - "test_api_reference_compare.py"
Cohesion: 0.27
Nodes (17): SONARA Core row from the ``sonara_features`` table. The three timbre BLOBs are…, SonaraRow, _client(), _embedding_outputs(), _identity_payload(), _maest_analysis_output(), parametrize, Path (+9 more)

### Community 77 - "TrackSummary"
Cohesion: 0.17
Nodes (26): FastAPI, register_reference_compare_routes(), ReferenceCompareRequest, ReferenceCompareVerdictRequest, TrackSummary, build_reference_compare(), _embedding_group(), _feedback_source() (+18 more)

### Community 78 - "sonara_storage.py"
Cohesion: 0.10
Nodes (46): _beat_count(), _bpm_candidates_json(), _candidate_sequence(), _canonical_json_array(), _float32_blob(), _float32_policy_bound(), _float32_vector(), _frame_indices() (+38 more)

### Community 79 - "ClassifierFeatureRow"
Cohesion: 0.18
Nodes (11): ClassifierFeatureRow, ClassifierScoreWrite, Protocol, _Scorer, _argmax_with_tiebreak(), ClassifierScorer, Loaded classifier for persisted classifier inputs., _score_bucket_from_score() (+3 more)

### Community 80 - "tempo_resolution.py"
Cohesion: 0.17
Nodes (30): best_tempo_distance(), _candidate_bpms(), _clamp01(), confidence_aware_target_score(), confidence_aware_tempo_risk(), confidence_aware_tempo_score(), _finite_float(), measured_tempo_score() (+22 more)

### Community 81 - "audio_doctor/core.py"
Cohesion: 0.14
Nodes (27): escaped_codepoint(), is_xml_character(), normalize_state_sources(), _problems_sheet_rows(), resolve_state_path(), _results_sheet_rows(), safe_filename_part(), source_signature() (+19 more)

### Community 82 - "training.py"
Cohesion: 0.18
Nodes (27): benchmark_lab_database(), _bounded_top_n_values(), _calibration_gate(), _calibration_thresholds(), _cross_validation_metrics(), expected_calibration_error(), _feature_group_indices(), _feature_group_weights() (+19 more)

### Community 84 - "api_routes_tags_export.py"
Cohesion: 0.24
Nodes (13): FastAPI, Path, register_tags_export_routes(), ExportRequest, GenreTagApplyResultResponse, GenreTagRequest, export_tracks(), Path (+5 more)

### Community 85 - "main"
Cohesion: 0.10
Nodes (21): configure_stdio(), load_state(), main(), new_state(), normalize_reason_filter(), parse_args(), Namespace, RunReporter (+13 more)

### Community 86 - "Path"
Cohesion: 0.14
Nodes (27): add_path(), aiff_sound_payload_hash(), apply_repaired_file(), collect_paths(), create_backup(), delete_backup(), detect_format_from_header(), FileInspectionResult (+19 more)

### Community 87 - "RepairError"
Cohesion: 0.15
Nodes (27): aiff_sound_payload(), aligned_pcm_data_payload_hash(), ByteRepairResult, data_payload(), data_payload_hash(), dedupe(), find_next_id3_chunk(), has_empty_aiff_id3_chunks() (+19 more)

### Community 88 - "embedding.py"
Cohesion: 0.10
Nodes (31): MaestWindowContext, RuntimeError, _average_maest_embeddings(), _construct_clap_module_with_pinned_text_model(), _construct_muq_mulan_with_pinned_text_model(), _download_verified_hf_checkpoint(), _download_verified_hf_snapshot(), _ensure_verified_maest_checkpoint() (+23 more)

### Community 89 - "test_rhythm_lab.py"
Cohesion: 0.05
Nodes (56): SimpleNamespace, _predict_probabilities(), ndarray, One ordered, structurally valid embedding matrix., SourceEmbeddingMatrix, Exception, Small in-process progress registry for an active profile workflow., TrainingProgress (+48 more)

### Community 90 - "configure_logging"
Cohesion: 0.16
Nodes (18): configure_logging(), parse_log_level(), uvicorn_log_config(), test_configure_logging_archives_previous_day_project_logs_on_startup(), test_configure_logging_defaults_to_info_and_higher(), test_configure_logging_defaults_to_logs_directory(), test_configure_logging_does_not_roll_over_active_log_during_emit(), test_configure_logging_writes_file() (+10 more)

### Community 91 - "analysis_models.py"
Cohesion: 0.19
Nodes (22): _adapter_identity(), embedding_analysis_output(), Build the current embedding output for one production adapter., _required_adapter_text(), _runtime_parameters(), clap_embedding_output(), _embedding_output(), _finite_number() (+14 more)

### Community 92 - "load_tracks"
Cohesion: 0.16
Nodes (23): Standalone online track-metadata enrichment tool., _load_audio_file(), _load_csv(), _load_directory(), _load_m3u(), load_tracks(), _load_xlsx(), Path (+15 more)

### Community 93 - "report.py"
Cohesion: 0.16
Nodes (17): build_report_contract(), _clean(), _column(), _join(), _maest(), Path, Source-preserving intermediate report contract., Build one flat, source-preserving data row per track. (+9 more)

### Community 94 - "seed_sampling.py"
Cohesion: 0.10
Nodes (47): _analysis_flag(), _bpm_bucket(), _bucket_for_values(), _buckets_used(), _clean_required_sources(), _energy_bucket(), export_seed_sample(), _finite_number() (+39 more)

### Community 95 - "BaseModel"
Cohesion: 0.19
Nodes (13): BaseModel, FastAPI, Path, register_database_routes(), DatabaseStateResponse, DatabaseSwitchRequest, MlPipelineSettings, MLStagedSettings (+5 more)

### Community 96 - "recorded_sessions.py"
Cohesion: 0.32
Nodes (16): _contains_legacy_version_identity(), _current_session(), _event_provenance_matches(), load_current_evaluation_sessions(), _mapping_sequence(), _persisted_snapshot_matches(), _positive_int_or_none(), Any (+8 more)

### Community 97 - "audio_dedup/core.py"
Cohesion: 0.16
Nodes (24): _bool_text(), _candidates_sheet_rows(), _evidence_by_candidate(), _groups_sheet_rows(), _pair_evidence_sheet_rows(), rhythm_lab_cli_summary(), _rhythm_lab_sheet_rows(), rhythm_lab_summary() (+16 more)

### Community 98 - "current_embedding_spec"
Cohesion: 0.13
Nodes (24): _store_synthetic_embeddings(), current_embedding_spec(), EmbeddingFamilySpec, EmbeddingOutput, EmbeddingWrite, ndarray, _readonly_float32_vector(), _embedding() (+16 more)

### Community 99 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+14 more)

### Community 100 - ".random_target"
Cohesion: 0.27
Nodes (8): _optional_track_ids(), RuntimeError, Resolve request IDs to current tracks with active SONARA Core., Choose one unselected current track with valid SONARA Core features., Raised when no current SONARA Core data can serve search., _requested_track_ids(), SonaraSearchUnavailable, _validate_rows()

### Community 101 - "_move_maest_runtime_modules"
Cohesion: 0.24
Nodes (4): _move_maest_runtime_modules(), FakeMaestModel, MovableModule, test_maest_initializes_only_missing_melspectrogram()

### Community 102 - "text_tag_crosscheck.py"
Cohesion: 0.08
Nodes (51): float64, FloatArray, int64, NDArray, Path, auc(), binary_truth(), build_arms() (+43 more)

### Community 103 - "AppDatabaseState"
Cohesion: 0.16
Nodes (8): AppDatabaseState, DatabaseBusy, DatabaseNotSelected, Path, RuntimeError, Return the selected database only when no background job is active., Reserve the selected database for one synchronous maintenance task., Keep selection and exclusivity stable until a job is queued. Manager lookup…

### Community 104 - "select_torch_device"
Cohesion: 0.11
Nodes (16): Any, select_torch_device(), collapsed(), load_score_prompt_bank_module(), Path, Compare wording, not line wrapping., test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(), test_checkpoint_loading_forces_weights_only() (+8 more)

### Community 105 - "vector_index.py"
Cohesion: 0.13
Nodes (26): HnswPersistentIndexSearcher, load_persistent_index_searcher(), PersistentAnnVectorSearchBackend, PersistentIndexSearcher, ndarray, Strict persistent HNSW search over one current embedding output. The backend…, _vector_content_hash(), _hnsw_hits() (+18 more)

### Community 106 - "SimilaritySearch"
Cohesion: 0.26
Nodes (20): EmbeddingFamily, Cosine search over one current ML embedding family., SimilaritySearch, Protocol, Cosine backend for production ``normalization='l2'`` embeddings., VectorSearchBackend, _add_track(), _library() (+12 more)

### Community 107 - "main"
Cohesion: 0.13
Nodes (14): apply_duplicate_deletions(), apply_result_payload(), ApplyResult, _candidate_track_id(), configure_stdio(), confirm_apply(), ConsoleProgressReporter, main() (+6 more)

### Community 108 - "PresetConfig"
Cohesion: 0.15
Nodes (22): _bits_to_int(), _candidate_duration_compatible(), _candidate_pair_ids(), _candidate_reason_lines(), _candidate_safety(), _connected_components(), _content_similarity(), _duration_distance() (+14 more)

### Community 109 - "parseJsonResponse"
Cohesion: 0.18
Nodes (19): addMulticlassLabelRow(), addOption(), applySourceState(), chooseSource(), clearActiveProfile(), collectNewProfileLabels(), createProfile(), deleteActiveProfile() (+11 more)

### Community 110 - "handle_asyncio_exception_context"
Cohesion: 0.29
Nodes (8): AbstractEventLoop, ConnectionResetError, _connection_reset_code(), handle_asyncio_exception_context(), _is_windows_transport_reset(), _safe_asyncio_context(), test_asyncio_transport_reset_is_logged_without_default_traceback(), test_unknown_asyncio_exception_is_logged_and_forwarded()

### Community 111 - "media_preview.py"
Cohesion: 0.33
Nodes (9): FileResponse, AudioPreviewError, _delete_temp_file(), _is_browser_safe_wav(), Path, RuntimeError, Raised when an audio preview response cannot be prepared., requires_browser_preview_transcode() (+1 more)

### Community 112 - "SonaraStagingConfig"
Cohesion: 0.08
Nodes (42): LogCaptureFixture, ProcessPoolExecutor, _analysis_mapping_with_ffmpeg_fallback(), _import_sonara(), Any, Current unversioned SONARA analysis selection and value constants., sonara_requested_features(), analyze_and_store_staged_sonara() (+34 more)

### Community 113 - "api_routes_evaluation.py"
Cohesion: 0.13
Nodes (18): model_validator, _evaluation_schema_error(), _inline_score_profile_payload(), Any, Exception, FastAPI, register_evaluation_routes(), _score_profile_from_request() (+10 more)

### Community 114 - "DJ Track Similarity Banner"
Cohesion: 0.16
Nodes (20): AI-Assisted Music Analysis, CLAP, Classifiers, DJ Set Building, DJ Track Similarity Banner, Genre Detection, High Resolution Audio Insights, Library Exploration (+12 more)

### Community 115 - "MaestWindowContext"
Cohesion: 0.32
Nodes (12): MaestWindowContext, _optional_boundary(), _positive_finite(), select_maest_window_starts(), _selected_range(), parametrize, test_centered_full_duration_starts(), test_invalid_context_falls_back_without_failure() (+4 more)

### Community 116 - "tests/test_cli.py"
Cohesion: 0.21
Nodes (15): _FakeAnalysisManager, MonkeyPatch, Path, test_analyze_cli_passes_separate_ml_batch_sizes(), test_analyze_cli_prints_default_ml_progress_and_settings(), test_analyze_cli_rejects_unknown_device_before_opening_manager(), test_analyze_cli_runs_sonara_core_only(), test_relocate_library_cli_applies_typed_current_path_update() (+7 more)

### Community 117 - "optimize_database.py"
Cohesion: 0.19
Nodes (12): _backup_database(), _database_files(), _detect_database_kind(), _integrity_check(), main(), OptimizationSummary, optimize_database(), _optimize_one_database() (+4 more)

### Community 118 - "Q: Какая версия FAST API у меня сейчас?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Какая версия FAST API у меня сейчас?, Source Nodes

### Community 119 - "audio_loader.py"
Cohesion: 0.16
Nodes (24): ml, load_audio_mono_with_ffmpeg(), load_decoded_audio(), load_decoded_audio_with_ffmpeg(), _load_with_shared_ffmpeg(), _load_with_torchcodec(), ndarray, Path (+16 more)

### Community 120 - "_PublicClassifierReader"
Cohesion: 0.18
Nodes (12): _manifest_payload(), _PublicClassifierReader, ClassifierScoreDetail, Path, TrackDetail, TrackSummary, Classifier production reader with no SQLite/direct-SQL surface., _score_detail() (+4 more)

### Community 121 - "TrackRecord"
Cohesion: 0.21
Nodes (20): _bpm_distance(), build_report(), choose_keeper(), confidence_category(), DuplicateGroup, _float_or_none(), _format_float(), format_rank() (+12 more)

### Community 122 - "FileRepairResult"
Cohesion: 0.20
Nodes (19): AudioDoctorCancelled, file_result_payload(), FileRepairResult, format_result(), format_status(), primary_action(), process_paths(), repair_report_action() (+11 more)

### Community 123 - "score_prompt_bank.py"
Cohesion: 0.33
Nodes (17): build_label_bank(), build_negative_banks(), embed_negative_prompts(), embed_prompt_ensemble(), l2norm(), load_audio_windows(), load_checkpoint_weights_only(), load_prompt_bank() (+9 more)

### Community 124 - "scripts"
Cohesion: 0.11
Nodes (17): devDependencies, @fontsource-variable/jetbrains-mono, vitepress, name, private, scripts, build, check (+9 more)

### Community 125 - "track_models.py"
Cohesion: 0.06
Nodes (65): canonical_file_path(), _chunks(), _genres_json(), _identity_from_row(), _library_roots_from_json(), _library_roots_json(), _normalized_audio_duration(), ordinal_path_key() (+57 more)

### Community 126 - "test_api_database_selection.py"
Cohesion: 0.18
Nodes (15): _add_track(), fixture, parametrize, Path, _selected_state(), _shared_ffmpeg(), test_database_file_dialog_switches_to_selected_current_bundle(), test_database_switch_creates_selected_current_bundle() (+7 more)

### Community 127 - "Workflows"
Cohesion: 0.25
Nodes (9): Workflows, Backed-Up Database Optimization, Explicit Single-Library Migration, Maintain a Library Safely, Bounded Reanalysis Pilot, Dependent Classifier Refresh, Legacy Split-Storage Migration, Reanalyze SONARA Data (+1 more)

### Community 128 - "test_vector_index.py"
Cohesion: 0.19
Nodes (20): create_vector_backend(), ExactVectorSearchBackend, Create one explicitly named backend; legacy aliases are not accepted., Deterministic exact cosine search over validated unit vectors., _add_track(), _mert_output(), _mert_unit_vector(), MonkeyPatch (+12 more)

### Community 129 - "loadTrainingReadiness"
Cohesion: 0.39
Nodes (18): calibrateClassifier(), fileName(), handleTrainingActionClick(), loadTrainingReadiness(), parseRefreshResponse(), pollTrainingProgress(), promoteClassifier(), refreshCandidates() (+10 more)

### Community 130 - "run_report"
Cohesion: 0.24
Nodes (18): CancelCheck, ProgressCallback, _attach_embeddings(), AudioDedupCancelled, _connect_readonly(), count_database_tracks(), find_duplicate_groups(), load_tracks() (+10 more)

### Community 131 - "Personal Classifier Workflow"
Cohesion: 0.17
Nodes (17): Feature Ablation Benchmark, Calibration Data Gate, Database-Only Classifier Scoring, Immutable Generation Promotion, Ordered Classifier Feature Recipe, Personal Classifier Workflow, Reusable Ranking Signal, Not Truth, Rhythm Lab Isolated State (+9 more)

### Community 132 - "install_standard_stream_logging"
Cohesion: 0.33
Nodes (7): Handler, Logger, _detach_standard_stream_file_handler(), _detach_standard_stream_file_handlers(), install_standard_stream_logging(), Mirror direct stdout/stderr writes into the configured app file log., _wrap_standard_stream()

### Community 133 - "db_library_queries.py"
Cohesion: 0.06
Nodes (71): LibrarySummary, SonaraCore, ClassifierSpecification, _assemble_summaries(), _base_from_sql(), _base_select_fields(), _classifier_specifications_by_key(), _classifier_summaries() (+63 more)

### Community 134 - "qa_database.py"
Cohesion: 0.23
Nodes (16): _build_parser(), _fail(), _foreign_key_check(), _integrity_check(), main(), _open_read_only(), ArgumentParser, Connection (+8 more)

### Community 135 - "read_local_evidence"
Cohesion: 0.22
Nodes (14): _find_by_metadata(), _find_by_path(), Connection, Path, Row, Return tags and at most three MAEST genres from one unambiguous local track., read_local_evidence(), Path (+6 more)

### Community 136 - "reports.py"
Cohesion: 0.14
Nodes (34): build_judged_label_gate(), _first_label_for_any_source(), judged_label_guidance(), judged_label_status(), _labels_by_rating(), matched_judged_labels(), MatchedJudgedLabel, matching_label() (+26 more)

### Community 137 - "api_routes_search.py"
Cohesion: 0.11
Nodes (25): AbstractContextManager, AppDatabaseState, Protocol, SimilaritySearch, SimilaritySearchResult, SonaraSearchMode, _clap_text_search_plan(), _ClapTextSearchPlan (+17 more)

### Community 138 - "Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?, Source Nodes

### Community 139 - "Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?, Source Nodes

### Community 140 - "test_break_energy.py"
Cohesion: 0.29
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

### Community 144 - "test_reference_compare_uses_current_outputs_and_current_summaries"
Cohesion: 0.43
Nodes (7): _insert_track(), _mert_output(), _mert_vector(), ndarray, Path, _sonara_row(), test_reference_compare_uses_current_outputs_and_current_summaries()

### Community 145 - "test_rhythm_lab_bridge.py"
Cohesion: 0.33
Nodes (10): Path, _selection(), test_collection_append_never_rebinds_and_replace_is_explicit(), test_collection_catalog_mismatch_is_fail_closed(), test_collection_repository_rejects_legacy_labels_without_mutation(), test_collection_repository_rejects_partial_current_labels_before_ddl(), test_collection_repository_rejects_wal_visible_legacy_identity_before_ddl(), test_default_rhythm_lab_labels_path_is_stable_current() (+2 more)

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

### Community 151 - "FileTags"
Cohesion: 0.09
Nodes (45): Background and synchronous jobs for the sole scan repository path., _audio_format(), _audio_format_from_mime(), _contains_tag(), file_tags_from_metadata(), _genres(), iter_audio_files(), _positive_float_or_none() (+37 more)

### Community 153 - "test_api_dialog.py"
Cohesion: 0.32
Nodes (11): _add_track(), fixture, Path, _shared_ffmpeg(), test_choose_folder_endpoint_allows_cancel(), test_choose_folder_endpoint_reports_unavailable_dialog(), test_choose_folder_endpoint_returns_selected_path(), test_create_app_requires_shared_ffmpeg() (+3 more)

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

### Community 161 - "DatabaseValidationJobManager"
Cohesion: 0.26
Nodes (6): DatabaseValidationEvent, DatabaseValidationJobManager, DatabaseValidationJobStatus, Single-threaded lifecycle for explicit database validation., Path, test_validation_job_api_exposes_completed_job_and_its_ui_events()

### Community 162 - "run_server_launcher.py"
Cohesion: 0.36
Nodes (8): Popen, build_frontend_command(), build_server_command(), frontend_directory(), main(), Path, resolve_npm_executable(), stop_process()

### Community 163 - "Unified SQLite Music Library"
Cohesion: 0.44
Nodes (9): CLAP Text-to-Audio and Audio-to-Audio Search, Explicit Backup-First Legacy Database Migration, MAEST Genre and Audio Embedding, MERT Audio Embedding, Separated Model Evidence Sources, MuQ Audio Embedding, SONARA Audio Features, Unified SQLite Music Library (+1 more)

### Community 164 - "test_api_sonara_search.py"
Cohesion: 0.28
Nodes (16): _add_embedding_track(), _add_sonara_track(), _blob(), _float(), _mert_output(), parametrize, Path, _sonara_library() (+8 more)

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

### Community 173 - "write_csv_rows"
Cohesion: 0.33
Nodes (5): CsvExportRow, CsvRow, Path, Protocol, write_csv_rows()

### Community 175 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 176 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.29
Nodes (4): appSource, panelSource, styles, trackPanelSource

### Community 178 - "Local-First DJ Library Workbench"
Cohesion: 0.29
Nodes (7): Browser-Local Current Set, Listening-Led Ranking Signals, Local-First DJ Library Workbench, Russian Project Limitations, Russian Local-First Workbench Description, DJ Set Dramaturgy, Three-Layer Set Compatibility Model

### Community 179 - "loadActive"
Cohesion: 0.15
Nodes (27): bpmFilterValue(), currentPage(), deleteSelectedCollection(), jumpToPage(), loadActive(), loadCandidates(), loadCollections(), loadCollectionTracks() (+19 more)

### Community 180 - "isMulticlassProfile"
Cohesion: 0.20
Nodes (14): assignedLabelStatus(), displayLabel(), formatProbability(), formatScore(), isMulticlassProfile(), labelByKey(), nextStepText(), positiveScore() (+6 more)

### Community 181 - "test_analysis_sonara_preflight.py"
Cohesion: 0.22
Nodes (12): _candidate(), _client(), _CoverageRepository, _PreflightTrapAnalysisJobs, MonkeyPatch, Path, TestClient, test_pipeline_job_creation_does_not_run_release_preflight() (+4 more)

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

### Community 188 - "create_app"
Cohesion: 0.12
Nodes (32): current_embedding_analysis_output(), Build current adapter identity without loading model weights., create_app(), open_database_file_dialog(), open_folder_dialog(), FastAPI, Path, Open Windows Explorer with the supplied audio file selected. (+24 more)

### Community 189 - "config.mts"
Cohesion: 0.40
Nodes (4): commonTheme, englishNav, englishSidebar, SidebarSection

### Community 190 - "test_database_validation.py"
Cohesion: 0.53
Nodes (8): Path, test_validate_database_cli_uses_concise_human_messages(), test_validator_reports_corrupt_embedding_payload(), test_validator_reports_each_track_and_does_not_mutate_database(), test_validator_reports_invalid_classifier_probabilities(), test_validator_reports_non_finite_sonara_feature_vector(), test_validator_warns_when_stored_track_path_is_missing(), _track()

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

### Community 201 - "runtime.py"
Cohesion: 0.52
Nodes (6): doctor(), _detect_nvidia_smi_cuda(), get_torch_runtime_info(), _parse_cuda_version(), recommended_torch_index(), TorchRuntimeInfo

### Community 216 - "_parse_args"
Cohesion: 0.60
Nodes (5): _parse_args(), _parse_track_counts(), _positive_int(), _track_count_value(), _vector_backend_name()

### Community 224 - "_SonaraStatusRepository"
Cohesion: 0.67
Nodes (3): _LibrarySummary, Protocol, _SonaraStatusRepository

### Community 225 - "textPromptPresets.ts"
Cohesion: 0.13
Nodes (19): EmbeddingSource, ClapSearchTab(), ComposedPromptBanks, composePromptBanks(), defaultTextPromptModel, MeasuredPreset, NegativeWeight, normalizePrompt() (+11 more)

### Community 226 - "Q: как реализована передача аудио в MULAN"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как реализована передача аудио в MULAN, Source Nodes

### Community 227 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 228 - "test_api_rhythm_lab.py"
Cohesion: 0.21
Nodes (16): _add_track(), _identity_payload(), Path, TrackIdentity, test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(), test_rhythm_lab_collection_save_rejects_legacy_numeric_only_body(), test_rhythm_lab_default_pid_path_uses_database_directory(), test_rhythm_lab_launch_endpoint_allows_no_selected_database() (+8 more)

### Community 229 - "Q: Проанализируй реализацию извлечения эмбов в MULam в проекте"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Проанализируй реализацию извлечения эмбов в MULam в проекте, Source Nodes

### Community 230 - "Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA, Source Nodes

### Community 231 - "dj_track_similarity/cli.py"
Cohesion: 0.10
Nodes (60): command, parse_analysis_models_text(), analyze(), analyze_classifier(), analyze_pipeline(), classifier_calibration_report(), classifier_suggest_labels(), _db() (+52 more)

### Community 232 - "build_weighted_candidate_pool"
Cohesion: 0.39
Nodes (18): build_weighted_candidate_pool(), _candidate_row(), EvaluationRepository, MonkeyPatch, _score_profile(), _sonara_with_energy(), _summary_with_tags(), test_weighted_candidate_csv_row_contains_expected_manual_columns() (+10 more)

### Community 233 - "register_server_routes"
Cohesion: 0.38
Nodes (4): FastAPI, register_server_routes(), test_shutdown_route_requires_explicit_action_header(), test_shutdown_route_schedules_shutdown_after_acknowledgement()

### Community 234 - "classifier_scoring.py"
Cohesion: 0.13
Nodes (27): classifier_manifest_api_fields(), analyze_classifier(), classifier_artifact_slug(), _classifier_key_from_metadata_or_slug(), default_classifier_model_path(), default_classifier_models_root(), load_classifier_requirements(), _load_payload() (+19 more)

### Community 235 - "scanImportDialog.test.mjs"
Cohesion: 0.40
Nodes (4): appPath, dialogPath, panelPath, srcDir

### Community 236 - "_Repository"
Cohesion: 0.13
Nodes (21): _Repository, AnalysisCoverage, _expanded_vector(), _identity(), _identity_payload(), AnalysisCoverage, ndarray, parametrize (+13 more)

### Community 237 - "project_text_search.py"
Cohesion: 0.27
Nodes (14): clean_lines(), db_path_from_env(), get_json(), main(), post_json(), print_results(), Path, Print the API response using its current field names. (+6 more)

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
Cohesion: 0.21
Nodes (7): ClassifierJobManager, ClassifierJobStatus, ClassifierLogEvent, _ClassifierPayload, ClassifierTrackError, Exception, Path

### Community 253 - "rhythm_lab_collections.py"
Cohesion: 0.11
Nodes (33): _collection_from_row(), _collection_tracks(), _configure_collection_connection(), default_rhythm_lab_labels_path(), ensure_review_collection_schema(), _immutable_read_only_connection(), _insert_collection_tracks(), _nonempty_path() (+25 more)

### Community 254 - "Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть., Source Nodes

### Community 255 - "Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?, Source Nodes

### Community 256 - "Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?, Source Nodes

### Community 257 - "db_search_fts.py"
Cohesion: 0.25
Nodes (12): delete_track_search_fts(), _file_genres_text(), _maest_genres_text(), Connection, Track-search FTS maintenance. The FTS index contains only text a person can…, Delete one track from the live FTS index without committing., Refresh one track's human-text FTS row without committing., Rebuild the human-text FTS index atomically. If the caller already owns a… (+4 more)

### Community 258 - "test_api_tracks.py"
Cohesion: 0.23
Nodes (19): Local dj-track-similarity toolkit., _add_track(), _client(), _liked_payload(), Path, TestClient, TrackIdentity, test_delete_track_removes_catalog_data_but_keeps_source_audio() (+11 more)

### Community 259 - "AnalysisCandidate"
Cohesion: 0.06
Nodes (50): decode_analysis_batch(), DecodeFailure, DecodeAudio, A full-track decode error deferred to a model-specific recovery path., AnalysisCandidate, DecodedAudio, analyze_and_store_staged_ml(), cleanup_orphaned_ml_staging() (+42 more)

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

### Community 270 - "Q: как определяются есть ли уже трек в базе или нет при загркузке новых?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как определяются есть ли уже трек в базе или нет при загркузке новых?, Source Nodes

### Community 272 - "test_api_runtime.py"
Cohesion: 0.35
Nodes (13): _client(), Path, TestClient, test_classifier_preflight_conflict_returns_http_409_before_start(), test_database_switch_bootstraps_clean_selected_current_bundle(), test_exclusive_database_operation_blocks_new_jobs(), test_job_start_reservation_closes_exclusive_operation_toctou(), test_liked_mutation_requires_current_composite_identity() (+5 more)

### Community 274 - "Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе., Source Nodes

### Community 275 - "Q: Почему данные в базу не пишутся?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Почему данные в базу не пишутся?, Source Nodes

### Community 277 - "Q: где проблема"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: где проблема, Source Nodes

### Community 279 - "User Guide"
Cohesion: 0.40
Nodes (5): Listening-Led Shortlisting, DJ Library UI Workbench, User Guide, Outcome-Oriented Workflow Routing, Preview-First Working Habit

### Community 281 - "test_classifier_jobs.py"
Cohesion: 0.35
Nodes (10): _insert_present_classifier_inputs(), _insert_track(), _mert_output(), MonkeyPatch, Path, Create more persisted classifier inputs than one job batch holds., _requirements(), _score_count() (+2 more)

### Community 282 - "api_routes_rhythm_lab.py"
Cohesion: 0.15
Nodes (14): RhythmLabSourceBinding, BaseModel, FastAPI, model_validator, register_rhythm_lab_routes(), RhythmLabCollectionSaveRequest, TrackIdentityRequest, build_rhythm_lab_collection_selection_exact() (+6 more)

### Community 283 - "test_config.py"
Cohesion: 0.33
Nodes (6): CaptureFixture, Path, Prevent silently sending a credential to an unimplemented service., Prevent OAuth session material from leaking into normal CLI output., test_load_config_rejects_unknown_configured_source(), test_save_auth_data_persists_session_without_printing_secret()

### Community 284 - "test_api_evaluation.py"
Cohesion: 0.32
Nodes (14): _client(), ndarray, parametrize, Path, TestClient, test_evaluation_api_rejects_unselected_and_legacy_database(), test_evaluation_feedback_does_not_touch_audio_path(), test_evaluation_feedback_endpoints_validate_and_preserve_seed_scope() (+6 more)

### Community 285 - "_scan_track"
Cohesion: 0.52
Nodes (6): Path, TrackIdentity, _scan_track(), test_export_endpoint_writes_current_track_list_without_saving_playlist(), test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(), test_saved_playlist_endpoint_is_absent()

### Community 286 - "useConfirmation"
Cohesion: 0.29
Nodes (4): ConfirmationRequest, ConfirmationState, useConfirmation(), requestConfirmation()

### Community 291 - "test_benchmark_search.py"
Cohesion: 0.35
Nodes (10): CompletedProcess, parametrize, Path, _run_benchmark(), _run_benchmark_raw(), test_benchmark_search_keep_db_preserves_current_bundle(), test_benchmark_search_rejects_invalid_vector_backend(), test_benchmark_search_rejects_output_that_overlaps_keep_db() (+2 more)

### Community 292 - "DatabaseValidator"
Cohesion: 0.26
Nodes (8): DatabaseValidationReport, DatabaseValidator, Connection, Path, Row, Explicit, read-only validation of persisted library data., Stream current persisted rows without changing the library database., ValidationFinding

### Community 294 - "storage_database_paths"
Cohesion: 0.24
Nodes (11): _load_script(), Path, test_optimize_database_backs_up_library_and_existing_evaluation_sidecar(), test_optimize_database_does_not_reject_future_library_tables(), test_optimize_database_handles_generic_sqlite_file(), Path, Filesystem topology for the library and optional Evaluation sidecar., Optional sidecars belonging to one library catalog. (+3 more)

### Community 295 - "test_qa_database_script.py"
Cohesion: 0.70
Nodes (4): _load_script(), Path, test_qa_database_allows_future_library_tables(), test_qa_database_checks_library_and_optional_evaluation()

### Community 297 - "rank_maest_genres"
Cohesion: 0.36
Nodes (6): rank_genres(), rank_maest_genres(), Turn MAEST genre logits, already activated by the model adapter, into labels., Average MAEST genre scores from each track's analysis windows, then rank., test_rank_genres_orders_scores_and_limits_results(), test_rank_maest_genres_averages_each_tracks_windows_before_top_k()

### Community 300 - "api_routes_analysis.py"
Cohesion: 0.21
Nodes (16): AnalysisResetResult, _classifier_info_by_key(), _classifier_manifest_error_text(), _outputs_for_family(), FastAPI, register_analysis_routes(), _require_known_classifier(), _require_scoring_compatible_classifier() (+8 more)

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

### Community 312 - "TransitionTrack"
Cohesion: 0.21
Nodes (15): _cached_track(), _recomputed_transition_risk(), _active_sonara_rows(), _analysis_target(), load_all_transition_tracks(), _load_transition_tracks(), load_transition_tracks_for_ids(), load_transition_tracks_for_targets() (+7 more)

### Community 313 - "Prompt Bank Curator"
Cohesion: 0.20
Nodes (9): Axes, Genres, Granularity Honesty, Layer Boundary, Prompt Bank Curator, Source Of Truth, Verification, What A Good Label Looks Like (+1 more)

## Ambiguous Edges - Review These
- `Recording Indicator` → `Rhythm Lab Favicon`  [AMBIGUOUS]
  tools/rhythm-lab/rhythm_lab/static/favicon.svg · relation: references

## Knowledge Gaps
- **491 isolated node(s):** `SizeLike`, `TooltipPlacement`, `ActiveTooltip`, `DatabaseValidationEvent`, `_UnusedClassifierJobs` (+486 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `EmbeddingModelRunner` (9× useful, score=7.745923131)
- `MuqMulanEmbeddingAdapter` (7× useful, score=6.024491646)
- `AnalysisOutput` (7× useful, score=5.960626275)
- `MaestEmbeddingAdapter` (5× useful, score=4.312532261)
- `ClassifierScoreWrite` (5× useful, score=4.187367317)
- `ScanJobManager` (4× useful, score=3.653802237)
- `ClapEmbeddingAdapter` (4× useful, score=3.44705431)
- `MertEmbeddingAdapter` (4× useful, score=3.44705431)
- `MuqEmbeddingAdapter` (4× useful, score=3.44705431)
- `load_decoded_audio()` (4× useful, score=3.445974905)

**Known dead ends** — questions that led nowhere; don't re-derive.
- "Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?" -> `docsRoot`

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Recording Indicator` and `Rhythm Lab Favicon`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `LibraryDatabase` connect `LibraryDatabase` to `test_vector_index.py`, `test_sonara_similarity.py`, `test_api_tracks.py`, `run_report`, `database.py`, `db_library_queries.py`, `weighted_candidates.py`, `reports.py`, `collect_repository_paths`, `test_audio_dedup.py`, `test_break_energy.py`, `scan_library`, `test_api_runtime.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `ScanJobManager`, `db_analysis.py`, `FileTags`, `score_profiles.py`, `test_api_dialog.py`, `db_migration.py`, `evaluation/ablation.py`, `test_api_evaluation.py`, `risk_sweep.py`, `test_classifier_jobs.py`, `_scan_track`, `tags.py`, `source_profile.py`, `candidates.py`, `DatabaseValidationJobManager`, `test_api_sonara_search.py`, `test_repair_audio_metadata.py`, `storage_database_paths`, `test_qa_database_script.py`, `test_api_analysis_jobs.py`, `TrackIdentity`, `AnalysisOutput`, `calibration.py`, `EvaluationRepository`, `benchmark_search.py`, `TransitionTrack`, `test_analysis_orchestration.py`, `classifier_production.py`, `AnalysisPipelineManager`, `test_database_validation.py`, `rhythm_lab/cli.py`, `score_profile_optimizer.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `ClassifierFeatureRow`, `seed_sampling.py`, `recorded_sessions.py`, `current_embedding_spec`, `test_api_rhythm_lab.py`, `AppDatabaseState`, `dj_track_similarity/cli.py`, `build_weighted_candidate_pool`, `classifier_scoring.py`, `SimilaritySearch`, `main`, `api_routes_evaluation.py`, `tests/test_cli.py`, `ClassifierJobManager`, `track_models.py`, `test_api_database_selection.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `AnalysisOutput` connect `AnalysisOutput` to `AnalysisJobManager`, `test_sonara_similarity.py`, `test_vector_index.py`, `AnalysisCandidate`, `database.py`, `db_library_queries.py`, `test_break_energy.py`, `analysis_model_runners.py`, `ann_index.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `test_ann_runtime.py`, `db_analysis.py`, `test_consumers.py`, `test_classifier_jobs.py`, `LibraryDatabase`, `candidates.py`, `test_api_sonara_search.py`, `sonara_similarity_scoring.py`, `api_routes_analysis.py`, `EvaluationRepository`, `test_multi_model_analysis_jobs.py`, `test_analysis_sonara_preflight.py`, `sonara_features.py`, `benchmark_search.py`, `test_analysis_orchestration.py`, `classifier_production.py`, `create_app`, `artifact_io.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `sonara_storage.py`, `analysis_models.py`, `seed_sampling.py`, `current_embedding_spec`, `.random_target`, `vector_index.py`, `classifier_scoring.py`, `SimilaritySearch`, `_Repository`, `SonaraStagingConfig`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `RhythmLabDatabase` connect `RhythmLabDatabase` to `rhythm_lab/cli.py`, `label_transfer.py`, `source_db.py`, `features.py`, `training.py`, `web_app.py`, `test_consumers.py`, `test_rhythm_lab.py`, `rhythm_lab/ablation.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 134 inferred relationships involving `LibraryDatabase` (e.g. with `_active_embedding_output()` and `_insert_synthetic_tracks()`) actually correct?**
  _`LibraryDatabase` has 134 INFERRED edges - model-reasoned connections that need verification._
- **Are the 101 inferred relationships involving `AnalysisOutput` (e.g. with `_active_embedding_output()` and `_store_synthetic_embeddings()`) actually correct?**
  _`AnalysisOutput` has 101 INFERRED edges - model-reasoned connections that need verification._
- **Are the 91 inferred relationships involving `AnalysisTarget` (e.g. with `_store_synthetic_embeddings()` and `_candidates_without_seed()`) actually correct?**
  _`AnalysisTarget` has 91 INFERRED edges - model-reasoned connections that need verification._
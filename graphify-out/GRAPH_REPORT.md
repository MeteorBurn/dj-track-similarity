# Graph Report - dj-track-similarity  (2026-08-19)

## Corpus Check
- 432 files · ~400,024 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6578 nodes · 18775 edges · 296 communities (270 shown, 26 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1631 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `39348a69`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_tags.py
- candidates.py
- label_transfer.py
- source_db.py
- database.py
- Main project
- weighted_candidates.py
- RhythmLabDatabase
- App
- app.js
- build_analysis_job_config
- reports.py
- ClassifierJobManager
- sonara_similarity_scoring.py
- ann_index.py
- api_schemas.py
- Reference Index
- classifier_jobs.py
- ScanJobManager
- api.ts
- AnalysisOutput
- TrackInput
- web_app.py
- test_consumers.py
- score_profiles.py
- analysis_models.py
- db_migration.py
- evaluation/ablation.py
- TrackMetadataDialog.tsx
- risk_sweep.py
- Features, embeddings, and tags
- test_evaluation_cli.py
- metadata_enrichment_cli.py
- source_profile.py
- test_scan_jobs.py
- test_audio_dedup.py
- current_embedding_analysis_output
- test_repair_audio_metadata.py
- test_evaluation_source_profile.py
- DecodedAudio
- SonaraSimilaritySearch
- TrackIdentity
- export_seed_sample
- audio_loader.py
- EvaluationRepository
- classifier_manifest.py
- _Repository
- transition_diagnostics.py
- AnalysisTarget
- test_multi_model_analysis_jobs.py
- calibration.py
- compute_transition_diagnostics
- EvaluationRepository
- AnalysisJobManager
- analyze_and_store_sonara_batch
- SearchPlaylistPanel.tsx
- benchmark_search.py
- analysis_jobs.py
- test_analysis_orchestration.py
- rhythm_lab/ablation.py
- classifier_production.py
- ClassifierSpecification
- jobUi.tsx
- rhythm_lab_launcher.py
- rhythm_lab/cli.py
- useLibraryState.ts
- escapeHtml
- App.tsx
- score_profile_optimizer.py
- test_embedding.py
- labels.py
- recorded_sessions.py
- frontend/package.json
- artifact_io.py
- EmbeddingTrackIdentity
- test_classifier_scoring.py
- test_api_reference_compare.py
- TrackSummary
- sonara_storage.py
- SourceTrack
- tempo_resolution.py
- audio_doctor/core.py
- training.py
- project_clap_search.py
- exporter.py
- main
- Path
- RepairError
- ReferenceComparePanel.tsx
- test_rhythm_lab.py
- logging_config.py
- build_score_profile_optimizer_report
- load_tracks
- report.py
- seed_sampling.py
- FileTags
- JobStore
- audio_dedup/core.py
- rank_maest_genres
- compilerOptions
- DatabaseValidator
- create_app
- AnalysisModelRunner
- AppDatabaseState
- select_torch_device
- vector_index.py
- embedding.py
- main
- PresetConfig
- parseJsonResponse
- scan_library
- wave_tags.py
- sonara_features.py
- .connect
- DJ Track Similarity Banner
- MaestWindowContext
- tests/test_cli.py
- optimize_database.py
- Q: Какая версия FAST API у меня сейчас?
- build_weighted_candidate_pool
- _PublicClassifierReader
- TrackRecord
- FileRepairResult
- score_prompt_bank.py
- scripts
- TrackRepository
- test_api_database_selection.py
- Workflows
- sonara_similarity.py
- loadTrainingReadiness
- run_report
- Personal Classifier Workflow
- test_api_rhythm_lab.py
- StandardStreamLogMirror
- qa_database.py
- read_local_evidence
- judged.py
- api_routes_search.py
- Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?
- Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?
- load_classifier_requirements
- models.py
- Classifier Workflow
- LibraryDatabase
- api_routes_analysis.py
- RhythmLabCollections
- run-vale.mjs
- Search with Seed Tracks
- Know When Audio Files Can Be Written
- tooltipLayer.tsx
- test_run_server_lan_script.py
- ScannedFile
- AnalysisPipelineManager
- test_api_dialog.py
- Audio Online
- metadataReference.test.mjs
- rhythm_lab_impact_payload
- build_report_payload
- collect_repository_paths
- Normalized Prompt Ensemble
- validate_prompt_bank.py
- GenreTagJobManager
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
- renderGuidance
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- Local-First DJ Library Workbench
- loadActive
- .tags
- test_api_analysis_jobs.py
- Rhythm Lab Page
- DJ Track Similarity Project Overview
- DJ Track Similarity Dark Logo
- CLAP Text Search
- Audio-Online/tests/test_cli.py
- DJ Track Similarity
- validate_maest_analysis_row
- config.mts
- test_analysis_sonara_preflight.py
- apiContract.test.mjs
- _coverage_and_classifiers
- playerAutoplay.test.mjs
- referenceCompareContract.test.mjs
- sonaraSearchControls.test.mjs
- _track_from_row
- Rhythm Lab Favicon
- DJ Track Similarity Favicon Artwork
- Music Favicon
- appHeaderMeta.test.mjs
- clapPrompt.test.mjs
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
- connect_evaluation_sidecar
- Empty Rejection Vocabulary
- dj-track-similarity
- api_state.py
- EmbeddingOutput
- Q: как реализована передача аудио в MULAN
- What You Must Do When Invoked
- dj_track_similarity/__init__.py
- Q: Проанализируй реализацию извлечения эмбов в MULam в проекте
- Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA
- dj_track_similarity/cli.py
- _library_with_maest_candidate
- api_routes_library.py
- classifier_scoring.py
- scanImportDialog.test.mjs
- test_reference_compare_uses_current_outputs_and_current_summaries
- useConfirmation
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
- _scan_track
- rhythm_lab_collections.py
- Q: Добавь рассчёт embeddings для SONARA во время анализа с записью данных в отдельную таблицу, которая уже должна быть.
- Q: Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?
- Q: Можно ли добиться идентичного декодирования FFmpeg или другим декодером с SONARA/Symphonia?
- db_search_fts.py
- test_api_tracks.py
- track_views.py
- Q: Убери глобальный барьер и ожидание считывания всех файлов
- Q: Анализ MULAN как декодируется?
- Q: Проанализируй изменения TorchCodec 0.16.0 и CUDA-производительность применительно к аудио-анализу и отдельному SONARA fallback.
- Q: Какие текущие точки декодирования и база путей нужны для честного бенчмарка аудиодекодеров?
- Q: Какие новые нативные возможности TorchCodec 0.16, TorchAudio 2.11 и PyTorch заменяют пользовательскую логику decode, mono, resample и window preparation в dj-track-similarity?
- Q: Как закрепить анализ ML моделей MAEST MERT MuQ MuLan CLAP с TorchCodec и конечным FFmpeg fallback?
- Q: Давай уже определим: WavDecoder или AudioDecoder для ML моделей, которым нужен mono?
- Q: analysis pipeline job queue decode decoded embedding runner sonara maest mert muq
- Q: Как выполнить контракт maest_infer_input_contract.json через проект с TorchCodec 0.16?
- User Guide
- Q: как определяются есть ли уже трек в базе или нет при загркузке новых?
- Russian Project Overview
- playlistAddHandler.test.mjs
- Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе.
- Q: Почему данные в базу не пишутся?
- track_models.py
- Q: где проблема
- runtime.py
- test_classifier_jobs.py
- api_routes_rhythm_lab.py
- test_config.py
- test_api_evaluation.py
- test_scanner_runtime.py
- db_library_queries.py
- storage_database_paths
- test_qa_database_script.py
- AnalysisCandidate
- graphify reference: extra exports and benchmark
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- _ReadyClassifier

## God Nodes (most connected - your core abstractions)
1. `LibraryDatabase` - 317 edges
2. `AnalysisOutput` - 198 edges
3. `AnalysisTarget` - 160 edges
4. `RhythmLabDatabase` - 86 edges
5. `TrackIdentity` - 83 edges
6. `AnalysisJobManager` - 82 edges
7. `App()` - 75 edges
8. `EvaluationRepository` - 65 edges
9. `AnalysisCandidate` - 64 edges
10. `create_app()` - 62 edges

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

## Communities (296 total, 26 thin omitted)

### Community 0 - "test_tags.py"
Cohesion: 0.26
Nodes (22): ID3, _set_id3_genre(), _write_genre_tag(), _decoded_audio_md5(), _make_tone(), parametrize, Path, _require_ffmpeg() (+14 more)

### Community 1 - "candidates.py"
Cohesion: 0.11
Nodes (29): _analysis_target(), _blind_candidate_rows(), _CandidateAccumulator, CandidateExportRequest, CandidateExportResult, CandidatePoolRow, CandidateSourceContribution, _clean_sources() (+21 more)

### Community 2 - "label_transfer.py"
Cohesion: 0.08
Nodes (104): _absolute_lexical_path(), _backup_restore_target(), _build_parser(), build_rebound_bundle(), _build_restore_plan(), _canonical_json_bytes(), _canonical_json_text(), canonical_path_key() (+96 more)

### Community 3 - "source_db.py"
Cohesion: 0.05
Nodes (69): _attach_labels(), _base_track_query(), _clean_path_text(), _count_sonara_features(), _embedding_family(), _embedding_vector(), _feature_counts(), _feature_source_states() (+61 more)

### Community 4 - "database.py"
Cohesion: 0.12
Nodes (31): RLock, Path, _bootstrap_file_lock(), _bootstrap_lock_path(), _cleanup_staged_sqlite(), _configure_connection(), connect_database(), _create_fresh_library() (+23 more)

### Community 5 - "Main project"
Cohesion: 0.06
Nodes (32): Audio Dedup, Audio Doctor, Audio Online, Commands and arguments, `dj-sim analyze`, `dj-sim analyze-classifier CLASSIFIER`, `dj-sim analyze-pipeline`, `dj-sim classifier calibration-report` (+24 more)

### Community 6 - "weighted_candidates.py"
Cohesion: 0.10
Nodes (32): _clean_sources(), _effective_source_count(), _identity_payload(), _int_value(), limit_weighted_candidate_rows_per_seed(), _non_negative_finite_float(), _normalized_response_score(), _optional_number() (+24 more)

### Community 7 - "RhythmLabDatabase"
Cohesion: 0.07
Nodes (53): _canonical_json(), _classifier_label_from_row(), _classifier_label_queue_table_sql(), _classifier_labels_table_sql(), _classifier_predictions_table_sql(), _classifier_training_checkpoints_table_sql(), ClassifierLabel, ClassifierPredictionWrite (+45 more)

### Community 8 - "App"
Cohesion: 0.07
Nodes (62): App(), addVisibleTracksToPlaylist(), adoptClassifierProfiles(), beginGenericSearchRequest(), cancelGenericSearchRequest(), cancelTrackDetailRequest(), commitGenericSearchResults(), finishGenericSearchRequest() (+54 more)

### Community 9 - "app.js"
Cohesion: 0.04
Nodes (78): assignedLabelStatus(), badgeRow(), binaryLabelGridEl, bpmMaxEl, bpmMinEl, candidateFiltersEl, candidateMinBrokenEl, candidateMinPositiveEl (+70 more)

### Community 10 - "build_analysis_job_config"
Cohesion: 0.15
Nodes (22): AnalysisJobConfig, build_analysis_job_config(), _int_in_range(), normalize_analysis_device(), normalize_analysis_models(), _normalize_limit(), normalize_sonara_mode(), parse_analysis_models_text() (+14 more)

### Community 11 - "reports.py"
Cohesion: 0.13
Nodes (54): _aggregate_variant_metrics(), average_precision_at_k(), _axis_value(), bad_suggestion_rate_at_k(), _comparison_match_character(), _comparison_rank(), _comparison_reason_tags(), dcg_at_k() (+46 more)

### Community 12 - "ClassifierJobManager"
Cohesion: 0.25
Nodes (5): ClassifierCandidate, ClassifierJobManager, ClassifierJobStatus, Exception, Path

### Community 13 - "sonara_similarity_scoring.py"
Cohesion: 0.20
Nodes (27): centroid(), clean_mixer_weights(), clean_modifiers(), ComparableTrack, custom_numeric_fields(), denormalize_feature(), feature_value(), feature_values() (+19 more)

### Community 14 - "ann_index.py"
Cohesion: 0.06
Nodes (77): _artifact_path_from_manifest(), _artifact_paths(), _assert_inside_directory(), _benchmark_k_values(), benchmark_persistent_index(), _build_manifest(), build_persistent_index(), _candidates_without_seed() (+69 more)

### Community 15 - "api_schemas.py"
Cohesion: 0.09
Nodes (45): FastAPI, Path, register_database_routes(), register_evaluation_routes(), FastAPI, Path, register_tags_export_routes(), AnalysisCoverageResponse (+37 more)

### Community 16 - "Reference Index"
Cohesion: 0.05
Nodes (63): Explicit Audio Write Boundary, DJ Track Similarity Documentation Home, Local-First Ranked Workflow, Listening-Led Shortlisting, Project Guide, Analysis Families Reference, Database-Only Classifier Scoring, ML Embedding Families (+55 more)

### Community 17 - "classifier_jobs.py"
Cohesion: 0.11
Nodes (16): ClassifierFeatureRow, ClassifierScoreWrite, ClassifierLogEvent, _ClassifierPayload, ClassifierTrackError, Protocol, _Scorer, analyze_classifier() (+8 more)

### Community 18 - "ScanJobManager"
Cohesion: 0.18
Nodes (12): exception_summary(), log_failure(), Exception, Collection, Exception, Path, Run parallel discovery work against one thread-safe TrackRepository., Prepare bounded path batches and write ready results on this thread. (+4 more)

### Community 19 - "api.ts"
Cohesion: 0.05
Nodes (64): AnalysisCoverage, AnalysisJobStatus, AnalysisModel, AnalysisPipelineRequest, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail (+56 more)

### Community 20 - "AnalysisOutput"
Cohesion: 0.05
Nodes (67): AnalysisResetResult, AnalysisOutput, AnalysisWriteResult, FingerprintOutput, MaestWrite, RuntimeError, Raised when a write target no longer names the current track content., One versioned SONARA acoustic fingerprint in native base64 form. (+59 more)

### Community 21 - "TrackInput"
Cohesion: 0.09
Nodes (36): BeatportSource, DiscogsSource, _first_label(), Discogs database adapter using only its documented API surface., _strings(), _track_title(), LastFmSource, Last.fm community tag adapter. (+28 more)

### Community 22 - "web_app.py"
Cohesion: 0.07
Nodes (48): _artifact_feature(), _artifact_feature_summary(), _artifact_groups(), _artifact_metrics_path(), _artifact_summary(), CalibrateRequest, _calibration_readiness(), cleanup_training_artifacts() (+40 more)

### Community 23 - "test_consumers.py"
Cohesion: 0.17
Nodes (51): PredictionProgressCallback, Resolve the root model and its matching root manifest., resolve_classifier_artifact_paths(), build_labeled_feature_matrix(), Path, apply_model_to_lab(), Mostly read-only Rhythm Lab view over one library database., SourceDatabase (+43 more)

### Community 24 - "score_profiles.py"
Cohesion: 0.11
Nodes (51): _inline_score_profile_payload(), Any, FastAPI, _score_profile_from_request(), _score_profile_from_source_profile(), _score_profile_name(), _utc_timestamp(), _clean_score_profile() (+43 more)

### Community 25 - "analysis_models.py"
Cohesion: 0.06
Nodes (48): ArrayLike, _adapter_identity(), AnalysisWriteRepository, _decoded_items(), default_model_runners(), embedding_analysis_output(), EmbeddingModelRunner, _has_syncopated_rhythm() (+40 more)

### Community 26 - "db_migration.py"
Cohesion: 0.11
Nodes (54): _apply_schema(), create_library_schema(), Connection, Create the current single-library schema in *db*. Args: db: An open…, _attached_row_count(), _attached_table_exists(), _backup_sqlite(), _build_staged_library() (+46 more)

### Community 27 - "evaluation/ablation.py"
Cohesion: 0.10
Nodes (49): _ablated_signal(), _build_session_variants(), build_source_ablation_report(), _candidate_contributions_from_source_ranks(), _candidate_event(), _candidate_pool_sessions(), CandidateEvent, CandidatePoolSession (+41 more)

### Community 28 - "TrackMetadataDialog.tsx"
Cohesion: 0.06
Nodes (56): SonaraCore, formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureGroup (+48 more)

### Community 29 - "risk_sweep.py"
Cohesion: 0.10
Nodes (53): _average_transition_risk_at_k(), _best_by_metric(), _best_source_rank(), build_risk_penalty_sweep_report(), _cached_track(), _candidate_payload(), _candidate_with_risk_weight(), _clean_k_values() (+45 more)

### Community 30 - "Features, embeddings, and tags"
Cohesion: 0.06
Nodes (53): Classifiers and Rhythm Lab, Database-only classifier scoring, Immutable-generation promotion, Personal classifier, Rhythm Lab workflow, CLAP audio embedding, Features, embeddings, and tags, File tags (+45 more)

### Community 31 - "test_evaluation_cli.py"
Cohesion: 0.15
Nodes (40): _add_cli_track(), _build_candidate_export_library(), _build_optimizer_cli_library(), _expanded_unit_vector(), _identity_payload(), _maest_outputs(), ndarray, Path (+32 more)

### Community 32 - "metadata_enrichment_cli.py"
Cohesion: 0.10
Nodes (46): FormPost, JsonGet, Request, authorize_lastfm(), Explicit documented authorization flows for sources that support them., Open Last.fm consent and exchange its one-time token for a session key., _access_token(), _auth_values() (+38 more)

### Community 33 - "source_profile.py"
Cohesion: 0.17
Nodes (37): build_source_profile(), _clean_profile_request(), _clean_sources(), _clean_top_k_values(), _consensus_report(), _coverage_fallback_factors(), _effective_sources(), _int_value() (+29 more)

### Community 34 - "test_scan_jobs.py"
Cohesion: 0.26
Nodes (16): ScanJobPayload, _audio(), Path, test_duration_filtered_scan_limit_counts_only_eligible_tracks(), test_limited_scan_does_not_mark_unseen_tracks_missing(), test_parallel_scan_uses_process_workers_and_writes_on_calling_thread(), test_parallel_scan_writes_ready_batches_before_all_paths_are_prepared(), test_prepare_audio_path_group_reads_duration_once() (+8 more)

### Community 35 - "test_audio_dedup.py"
Cohesion: 0.18
Nodes (40): _create_library_db(), _create_rhythm_lab_db(), _current_embedding_fixture(), _identity_tuple(), _insert_track(), _load_dedup_module(), CaptureFixture, MonkeyPatch (+32 more)

### Community 36 - "current_embedding_analysis_output"
Cohesion: 0.09
Nodes (24): current_embedding_analysis_output(), Build current adapter identity without loading model weights., _text_embedding_adapter(), ClapEmbeddingAdapter, MaestEmbeddingAdapter, MertEmbeddingAdapter, MuqEmbeddingAdapter, MuqMulanEmbeddingAdapter (+16 more)

### Community 37 - "test_repair_audio_metadata.py"
Cohesion: 0.12
Nodes (45): _aiff_chunk(), _load_repair_module(), _minimal_aiff_with_empty_id3_chunks(), _minimal_pcm_wave(), Path, _riff_chunk(), test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload(), test_apply_forces_single_worker() (+37 more)

### Community 38 - "test_evaluation_source_profile.py"
Cohesion: 0.33
Nodes (12): _activate_runtime_embedding_outputs(), _profile_library(), EvaluationRepository, _row(), _save_profile_embeddings(), test_source_profile_accepts_muq_candidate_source(), test_source_profile_consensus_source_outweighs_isolated_source(), test_source_profile_default_muq_and_clap_without_rows_are_neutral() (+4 more)

### Community 39 - "DecodedAudio"
Cohesion: 0.11
Nodes (21): DecodedAudio, _array_output_to_numpy(), _average_l2_window_embeddings(), _masked_time_mean(), _normalize_rows(), _normalized_embedding_rows(), _pad_or_trim_audio_tensor(), _prepare_muq_compatible_windows() (+13 more)

### Community 40 - "SonaraSimilaritySearch"
Cohesion: 0.22
Nodes (37): SONARA feature-mixer search over current Core data. The separate 48-dimensional…, SonaraSimilaritySearch, _add_sonara_track(), _add_track_without_sonara(), _core_row(), _feature_value(), _float_or_none(), _int_or_none() (+29 more)

### Community 41 - "TrackIdentity"
Cohesion: 0.16
Nodes (31): Stable identity of one library track., TrackIdentity, camelot_compatibility(), canonical_camelot(), _finite_float(), key_name_to_camelot(), _parse_camelot(), TrackIdentity (+23 more)

### Community 42 - "export_seed_sample"
Cohesion: 0.25
Nodes (21): _weighted_candidate_seed_track_ids(), export_seed_sample(), SeedSampleResult, _ml_outputs(), ndarray, Path, TrackIdentity, _save_complete_analysis() (+13 more)

### Community 43 - "audio_loader.py"
Cohesion: 0.08
Nodes (50): ml, load_audio_mono_with_ffmpeg(), load_decoded_audio(), load_decoded_audio_with_ffmpeg(), _load_with_shared_ffmpeg(), _load_with_torchcodec(), ndarray, Path (+42 more)

### Community 44 - "EvaluationRepository"
Cohesion: 0.10
Nodes (24): _embedding_output(), EvaluationRepository, _identity(), identity_payload(), profile(), AnalysisCoverage, Any, TrackIdentity (+16 more)

### Community 45 - "classifier_manifest.py"
Cohesion: 0.13
Nodes (27): ClassifierArtifactPaths, ClassifierManifestSummary, _clean_classifier_key(), _feature_sources(), _invalid_manifest(), load_classifier_manifest_summary(), _manifest_error_text(), _optional_text() (+19 more)

### Community 46 - "_Repository"
Cohesion: 0.13
Nodes (21): _Repository, _expanded_vector(), _identity(), _identity_payload(), AnalysisCoverage, ndarray, parametrize, TrackIdentity (+13 more)

### Community 47 - "transition_diagnostics.py"
Cohesion: 0.13
Nodes (40): _best_relative_tempo_delta(), _bpm_risk(), _clamp(), _classifier_scores(), _clean_classifier_risk_weights(), _confidence_aware_bpm_risk(), _confidence_missingness_risk(), _contains_keyword() (+32 more)

### Community 48 - "AnalysisTarget"
Cohesion: 0.07
Nodes (61): AnalysisTarget, AnalysisVectorRow, current_embedding_spec(), EmbeddingFamilySpec, _search_source(), AnalysisSearchRepository, _apply_epsilon(), _contrast_score_breakdown() (+53 more)

### Community 49 - "test_multi_model_analysis_jobs.py"
Cohesion: 0.18
Nodes (14): _candidate(), _decoded(), _maest_output(), _mert_output(), Exception, Path, _Repository, _Runner (+6 more)

### Community 50 - "calibration.py"
Cohesion: 0.15
Nodes (38): _average_score(), _binary_label(), brier_score(), build_calibration_report(), _calibration_report(), _calibration_samples(), _calibration_status(), CalibrationSample (+30 more)

### Community 51 - "compute_transition_diagnostics"
Cohesion: 0.16
Nodes (29): compute_transition_diagnostics(), _mean_available(), Compute transition risk from identity-validated repository rows., _risk_version(), TransitionDiagnostics, _classifier_score(), ClassifierScoreSummary, test_adjacent_camelot_key_has_lower_risk_than_clash() (+21 more)

### Community 52 - "EvaluationRepository"
Cohesion: 0.14
Nodes (24): _canonical_json_value(), _clean_tags(), EvaluationRepository, _finite_float(), _json_load(), _json_object(), _json_text(), _load_track_snapshots() (+16 more)

### Community 53 - "AnalysisJobManager"
Cohesion: 0.18
Nodes (6): AnalysisJobStatus, AnalysisJobManager, DecodeMethod, Record ML staged result (called incrementally per track)., Progress callback for ML staged pipeline phases., _RunnerLifecycle

### Community 54 - "analyze_and_store_sonara_batch"
Cohesion: 0.06
Nodes (36): Any, SONARA requires no model preflight beyond normal batch execution., SonaraModelRunner, analysis_outputs_for_sonara_runtime(), analyze_and_store_sonara_batch(), Return the current SONARA Core, embedding, and fingerprint outputs., Analyze one native batch and persist successful results in input order.…, SonaraBatchMetrics (+28 more)

### Community 55 - "SearchPlaylistPanel.tsx"
Cohesion: 0.07
Nodes (40): EmbeddingSource, ClapPromptPreset, clapPromptPresets, defaultClapPromptPresetKey, normalizePrompt(), promptLinesFromText(), promptQueriesFromText(), ClapSearchTab() (+32 more)

### Community 56 - "benchmark_search.py"
Cohesion: 0.15
Nodes (36): _active_embedding_output(), _benchmark_database_path(), _benchmark_track_count(), BenchmarkConfig, _camelot_key(), _conflicting_kept_database_path(), _environment_summary(), _insert_synthetic_tracks() (+28 more)

### Community 57 - "analysis_jobs.py"
Cohesion: 0.14
Nodes (23): Item, AnalysisJobStatus, AnalysisLogEvent, AnalysisModelProgress, AnalysisTrackError, AnalysisTrackOutcome, copy_analysis_status(), initial_model_progress() (+15 more)

### Community 58 - "test_analysis_orchestration.py"
Cohesion: 0.09
Nodes (29): _candidate(), _clap_output(), _decoded(), _EmbeddingWriteRepository, _FakeMertAdapter, _FakeMulanAdapter, _FakeRepository, _FakeRunner (+21 more)

### Community 59 - "rhythm_lab/ablation.py"
Cohesion: 0.19
Nodes (22): benchmark_profile_ablation(), cli_summary(), _compact_row(), _default_output_path(), _elapsed_seconds(), _metrics_summary(), _normalize_feature_sets(), _optional_float() (+14 more)

### Community 60 - "classifier_production.py"
Cohesion: 0.13
Nodes (31): build_classifier_calibration_report(), _calibration_report_status(), _candidate_feedback_aggregates(), _classifier_feedback_summary(), _classifier_score_detail(), ClassifierScoreRow, _clean_classifier_key(), _count_values() (+23 more)

### Community 61 - "ClassifierSpecification"
Cohesion: 0.13
Nodes (19): LibrarySummary, ClassifierSpecification, _assemble_summaries(), _base_select_fields(), _classifier_specifications_by_key(), LibraryQueryRepository, Path, TrackIdentity (+11 more)

### Community 62 - "jobUi.tsx"
Cohesion: 0.10
Nodes (28): ACTIVE_JOB_STATES, ActivityEvent, analysisJobRequest(), AnalysisProcessStatus(), analysisRuntimeLabel(), AUDIO_MODELS, calculateEta(), calculateProgressPercent() (+20 more)

### Community 63 - "rhythm_lab_launcher.py"
Cohesion: 0.17
Nodes (32): _clear_pid(), _file_size(), _is_rhythm_lab_process(), launch_rhythm_lab(), _listener_process_id(), _log_path(), _managed_process_id(), _mirror_log_to_console() (+24 more)

### Community 64 - "rhythm_lab/cli.py"
Cohesion: 0.12
Nodes (40): PromotionProgressCallback, _add_data_options(), _artifact_calibration_payload(), _artifact_matches_calibration_filter(), _benchmark_ablation(), build_parser(), _calibration_report(), _collection_list() (+32 more)

### Community 65 - "useLibraryState.ts"
Cohesion: 0.11
Nodes (39): Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts, libraryTrackIdentityKey() (+31 more)

### Community 66 - "escapeHtml"
Cohesion: 0.15
Nodes (23): actionIcon(), canPromoteArtifact(), coverageBadge(), escapeHtml(), formatFeatureGroupWeights(), formatLabelCounts(), labelCountBadges(), loadTrainingView() (+15 more)

### Community 67 - "App.tsx"
Cohesion: 0.04
Nodes (56): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, defaultNotice, DeviceMode (+48 more)

### Community 68 - "score_profile_optimizer.py"
Cohesion: 0.10
Nodes (58): _assert_normalized_weights(), _base_report(), _bootstrap_stability(), build_saved_score_profile_payload(), _candidate_tie_break(), _clean_k_values(), _example_score(), _examples_by_seed() (+50 more)

### Community 69 - "test_embedding.py"
Cohesion: 0.05
Nodes (33): adapter_factories(), _move_maest_runtime_modules(), BatchMaestAdapter, FakeClapAudioModel, FakeMaestModel, FakeMertModel, FakeMertProcessor, FakeMulanModel (+25 more)

### Community 70 - "labels.py"
Cohesion: 0.22
Nodes (22): _json_object(), _load_csv_labels(), _load_jsonl_labels(), load_pair_feedback_labels(), load_transition_feedback_labels(), _optional_text(), PairFeedbackLabel, _parse_pair_feedback_row() (+14 more)

### Community 71 - "recorded_sessions.py"
Cohesion: 0.32
Nodes (16): _contains_legacy_version_identity(), _current_session(), _event_provenance_matches(), load_current_evaluation_sessions(), _mapping_sequence(), _persisted_snapshot_matches(), _positive_int_or_none(), Any (+8 more)

### Community 72 - "frontend/package.json"
Cohesion: 0.07
Nodes (29): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+21 more)

### Community 73 - "artifact_io.py"
Cohesion: 0.18
Nodes (22): PublicationProgressCallback, artifact_sha256(), ArtifactIntegrityError, _AvailableOutputRepository, _default_metadata_path(), _fsync_directory(), load_verified_artifact(), publish_promoted_artifact() (+14 more)

### Community 74 - "EmbeddingTrackIdentity"
Cohesion: 0.19
Nodes (20): TrackIdentity, current_track_identity(), EmbeddingTrackIdentity, _is_l2_unit_vector(), _positive_int(), Connection, ndarray, Row (+12 more)

### Community 75 - "test_classifier_scoring.py"
Cohesion: 0.22
Nodes (27): _artifact_hash(), _insert_track(), _install_fake_joblib(), _manifest_payload(), _mert_output(), _muq_output(), _ProbabilityModel, Exception (+19 more)

### Community 76 - "test_api_reference_compare.py"
Cohesion: 0.33
Nodes (15): _client(), _embedding_outputs(), _identity_payload(), _maest_analysis_output(), parametrize, Path, TestClient, _reference_library() (+7 more)

### Community 77 - "TrackSummary"
Cohesion: 0.20
Nodes (22): TrackSummary, build_reference_compare(), _embedding_group(), _feedback_source(), _hydrate_results(), Protocol, TrackIdentity, TrackSummary (+14 more)

### Community 78 - "sonara_storage.py"
Cohesion: 0.07
Nodes (70): SonaraCoreRow, SONARA Core row from the ``sonara_features`` table. The three timbre BLOBs are…, SonaraRow, _exact_object(), _json_array(), _optional_int(), _optional_number(), _optional_text() (+62 more)

### Community 79 - "SourceTrack"
Cohesion: 0.18
Nodes (23): build_feature_matrix(), build_labeled_feature_matrix_from_sources(), _cached_embedding_vectors(), _feature_names(), FeatureMatrix, _finite_float(), _parse_feature_names(), ndarray (+15 more)

### Community 80 - "tempo_resolution.py"
Cohesion: 0.15
Nodes (33): best_tempo_distance(), _candidate_bpms(), _clamp01(), confidence_aware_target_score(), confidence_aware_tempo_risk(), confidence_aware_tempo_score(), _finite_float(), measured_tempo_score() (+25 more)

### Community 81 - "audio_doctor/core.py"
Cohesion: 0.14
Nodes (27): escaped_codepoint(), is_xml_character(), normalize_state_sources(), _problems_sheet_rows(), resolve_state_path(), _results_sheet_rows(), safe_filename_part(), source_signature() (+19 more)

### Community 82 - "training.py"
Cohesion: 0.18
Nodes (27): benchmark_lab_database(), _bounded_top_n_values(), _calibration_gate(), _calibration_thresholds(), _cross_validation_metrics(), expected_calibration_error(), _feature_group_indices(), _feature_group_weights() (+19 more)

### Community 83 - "project_clap_search.py"
Cohesion: 0.21
Nodes (26): add_repo_src_to_path(), clean_lines(), db_path_from_env(), find_repo_root(), get_json(), main(), matching_source_track_ids(), normalize_path_for_db() (+18 more)

### Community 84 - "exporter.py"
Cohesion: 0.44
Nodes (7): export_tracks(), Path, Playlist export for typed library rows., _safe_filename(), _write_csv(), _write_m3u(), ExportTrackRow

### Community 85 - "main"
Cohesion: 0.10
Nodes (21): configure_stdio(), load_state(), main(), new_state(), normalize_reason_filter(), parse_args(), Namespace, RunReporter (+13 more)

### Community 86 - "Path"
Cohesion: 0.14
Nodes (27): add_path(), aiff_sound_payload_hash(), apply_repaired_file(), collect_paths(), create_backup(), delete_backup(), detect_format_from_header(), FileInspectionResult (+19 more)

### Community 87 - "RepairError"
Cohesion: 0.15
Nodes (27): aiff_sound_payload(), aligned_pcm_data_payload_hash(), ByteRepairResult, data_payload(), data_payload_hash(), dedupe(), find_next_id3_chunk(), has_empty_aiff_id3_chunks() (+19 more)

### Community 88 - "ReferenceComparePanel.tsx"
Cohesion: 0.13
Nodes (26): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareVerdict, TrackIdentity, normalizeLimit(), orderedReferenceCompareGroups(), ReferenceCompareGroupCard(), referenceCompareModels (+18 more)

### Community 89 - "test_rhythm_lab.py"
Cohesion: 0.05
Nodes (67): feature_recipe_readiness(), _feature_state_payload(), Describe readiness strictly for the selected feature recipe., _predict_probabilities(), ndarray, Current-generation availability for one classifier feature source., One ordered, structurally valid embedding matrix., Return availability for all feature sources. (+59 more)

### Community 90 - "logging_config.py"
Cohesion: 0.08
Nodes (46): AbstractEventLoop, ConnectionResetError, Handler, Logger, _archive_active_log_path(), configure_logging(), _connection_reset_code(), _current_date_suffix() (+38 more)

### Community 91 - "build_score_profile_optimizer_report"
Cohesion: 0.21
Nodes (22): _accepted_decision(), build_score_profile_optimizer_report(), _decision_guidance(), _equal_weights(), _add_two_candidate_session(), _build_bad_rate_increase_library(), _build_empty_seed_shell(), _build_two_candidate_optimizer_library() (+14 more)

### Community 92 - "load_tracks"
Cohesion: 0.16
Nodes (23): Standalone online track-metadata enrichment tool., _load_audio_file(), _load_csv(), _load_directory(), _load_m3u(), load_tracks(), _load_xlsx(), Path (+15 more)

### Community 93 - "report.py"
Cohesion: 0.16
Nodes (17): build_report_contract(), _clean(), _column(), _join(), _maest(), Path, Source-preserving intermediate report contract., Build one flat, source-preserving data row per track. (+9 more)

### Community 94 - "seed_sampling.py"
Cohesion: 0.11
Nodes (32): CsvExportRow, CsvRow, Path, Protocol, write_csv_rows(), _analysis_flag(), _bpm_bucket(), _bucket_for_values() (+24 more)

### Community 95 - "FileTags"
Cohesion: 0.20
Nodes (20): GenreTagCandidate, _apply_genre_tag_to_candidate(), apply_genre_tags_to_tracks(), _clean_genre_label(), genre_tag_apply_summary(), _genre_tags_for_candidate(), GenreTagApplyResult, _GenreTagRepository (+12 more)

### Community 97 - "audio_dedup/core.py"
Cohesion: 0.16
Nodes (24): _bool_text(), _candidates_sheet_rows(), _evidence_by_candidate(), _groups_sheet_rows(), _pair_evidence_sheet_rows(), rhythm_lab_cli_summary(), _rhythm_lab_sheet_rows(), rhythm_lab_summary() (+16 more)

### Community 98 - "rank_maest_genres"
Cohesion: 0.36
Nodes (6): rank_genres(), rank_maest_genres(), Turn MAEST genre logits, already activated by the model adapter, into labels., Average MAEST genre scores from each track's analysis windows, then rank., test_rank_genres_orders_scores_and_limits_results(), test_rank_maest_genres_averages_each_tracks_windows_before_top_k()

### Community 99 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+14 more)

### Community 100 - "DatabaseValidator"
Cohesion: 0.10
Nodes (21): DatabaseValidationReport, DatabaseValidator, format_validation_finding(), DatabaseValidationEvent, DatabaseValidationJobManager, DatabaseValidationJobStatus, Single-threaded lifecycle for explicit database validation., Connection (+13 more)

### Community 101 - "create_app"
Cohesion: 0.12
Nodes (29): create_app(), open_database_file_dialog(), open_folder_dialog(), FastAPI, Path, Open Windows Explorer with the supplied audio file selected., reveal_track_file(), FastAPI (+21 more)

### Community 102 - "AnalysisModelRunner"
Cohesion: 0.11
Nodes (12): RunnerFactory, DecodeAudio, Exception, RuntimeError, _RunnerHandle, _RunnerInitializationError, _RunnerPreflightError, _RunnerRuntimeKey (+4 more)

### Community 103 - "AppDatabaseState"
Cohesion: 0.14
Nodes (9): FastAPI, register_reference_compare_routes(), ReferenceCompareRequest, ReferenceCompareVerdictRequest, AppDatabaseState, Path, Return the selected database only when no background job is active., Reserve the selected database for one synchronous maintenance task. (+1 more)

### Community 104 - "select_torch_device"
Cohesion: 0.13
Nodes (13): Any, select_torch_device(), load_score_prompt_bank_module(), Path, test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(), test_checkpoint_loading_forces_weights_only(), test_clap_model_load_stdout_and_stderr_are_written_to_app_log(), test_clap_text_embedding_preflights_pinned_verified_checkpoint_once() (+5 more)

### Community 105 - "vector_index.py"
Cohesion: 0.08
Nodes (42): PersistentAnnVectorSearchBackend, ndarray, Strict persistent HNSW search over one current embedding output. The backend…, create_vector_backend(), ExactVectorSearchBackend, _hnsw_hits(), HnswVectorSearchBackend, _l2_query_vector() (+34 more)

### Community 106 - "embedding.py"
Cohesion: 0.09
Nodes (32): BaseException, _average_maest_embeddings(), _construct_clap_module_with_pinned_text_model(), _download_verified_hf_checkpoint(), _download_verified_hf_snapshot(), _ensure_verified_maest_checkpoint(), _local_only_from_pretrained_proxy(), _maest_embedding_rows() (+24 more)

### Community 107 - "main"
Cohesion: 0.13
Nodes (14): apply_duplicate_deletions(), apply_result_payload(), ApplyResult, _candidate_track_id(), configure_stdio(), confirm_apply(), ConsoleProgressReporter, main() (+6 more)

### Community 108 - "PresetConfig"
Cohesion: 0.15
Nodes (22): _bits_to_int(), _candidate_duration_compatible(), _candidate_pair_ids(), _candidate_reason_lines(), _candidate_safety(), _connected_components(), _content_similarity(), _duration_distance() (+14 more)

### Community 109 - "parseJsonResponse"
Cohesion: 0.17
Nodes (21): addMulticlassLabelRow(), addOption(), applySourceState(), chooseSource(), clearActiveProfile(), collectNewProfileLabels(), createProfile(), deleteSelectedCollection() (+13 more)

### Community 110 - "scan_library"
Cohesion: 0.21
Nodes (21): ScanStats, Scan one root through the sole TrackRepository write path., scan_library(), Aggregate result returned by the synchronous scanner., ScanStats, _library_roots(), _mert_output(), MonkeyPatch (+13 more)

### Community 111 - "wave_tags.py"
Cohesion: 0.17
Nodes (14): Frame, _AudioWithId3Tags, _genre_frame_text(), _Id3Tags, Path, Protocol, _replace_id3_genre(), _require_readable_wave_audio() (+6 more)

### Community 112 - "sonara_features.py"
Cohesion: 0.08
Nodes (44): LogCaptureFixture, ProcessPoolExecutor, _analysis_mapping(), _analysis_mapping_with_ffmpeg_fallback(), _import_sonara(), Any, Native SONARA batch orchestration for the analysis repository., Current unversioned SONARA analysis selection and value constants. (+36 more)

### Community 113 - ".connect"
Cohesion: 0.22
Nodes (11): _collection_from_row(), _insert_collection_tracks(), _positive_int(), Row, Ordered collection input bound to one library catalog., _require_collection_catalog(), _required_text(), ReviewCollection (+3 more)

### Community 114 - "DJ Track Similarity Banner"
Cohesion: 0.16
Nodes (20): AI-Assisted Music Analysis, CLAP, Classifiers, DJ Set Building, DJ Track Similarity Banner, Genre Detection, High Resolution Audio Insights, Library Exploration (+12 more)

### Community 115 - "MaestWindowContext"
Cohesion: 0.21
Nodes (14): MaestAnalysisResult, MaestWindowContext, _optional_boundary(), _positive_finite(), select_maest_window_starts(), _selected_range(), _FakeMaestAdapter, parametrize (+6 more)

### Community 116 - "tests/test_cli.py"
Cohesion: 0.21
Nodes (15): _FakeAnalysisManager, MonkeyPatch, Path, test_analyze_cli_passes_separate_ml_batch_sizes(), test_analyze_cli_prints_default_ml_progress_and_settings(), test_analyze_cli_rejects_unknown_device_before_opening_manager(), test_analyze_cli_runs_sonara_core_only(), test_relocate_library_cli_applies_typed_current_path_update() (+7 more)

### Community 117 - "optimize_database.py"
Cohesion: 0.19
Nodes (12): _backup_database(), _database_files(), _detect_database_kind(), _integrity_check(), main(), OptimizationSummary, optimize_database(), _optimize_one_database() (+4 more)

### Community 118 - "Q: Какая версия FAST API у меня сейчас?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Какая версия FAST API у меня сейчас?, Source Nodes

### Community 119 - "build_weighted_candidate_pool"
Cohesion: 0.39
Nodes (18): build_weighted_candidate_pool(), _candidate_row(), EvaluationRepository, MonkeyPatch, _score_profile(), _sonara_with_energy(), _summary_with_tags(), test_weighted_candidate_csv_row_contains_expected_manual_columns() (+10 more)

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

### Community 125 - "TrackRepository"
Cohesion: 0.10
Nodes (33): canonical_file_path(), _chunks(), _genres_json(), _identity_from_row(), _normalized_audio_duration(), Connection, FileTags, Path (+25 more)

### Community 126 - "test_api_database_selection.py"
Cohesion: 0.18
Nodes (15): _add_track(), fixture, parametrize, Path, _selected_state(), _shared_ffmpeg(), test_database_file_dialog_switches_to_selected_current_bundle(), test_database_switch_creates_selected_current_bundle() (+7 more)

### Community 127 - "Workflows"
Cohesion: 0.25
Nodes (9): Workflows, Backed-Up Database Optimization, Explicit Single-Library Migration, Maintain a Library Safely, Bounded Reanalysis Pilot, Dependent Classifier Refresh, Legacy Split-Storage Migration, Reanalyze SONARA Data (+1 more)

### Community 128 - "sonara_similarity.py"
Cohesion: 0.18
Nodes (15): _merge_targets(), _optional_targets(), _optional_track_ids(), RuntimeError, Resolve request IDs to current tracks with active SONARA Core., Choose one unselected current track with valid SONARA Core features., Raised when no current SONARA Core data can serve search., _requested_track_ids() (+7 more)

### Community 129 - "loadTrainingReadiness"
Cohesion: 0.39
Nodes (18): calibrateClassifier(), fileName(), handleTrainingActionClick(), loadTrainingReadiness(), parseRefreshResponse(), pollTrainingProgress(), promoteClassifier(), refreshCandidates() (+10 more)

### Community 130 - "run_report"
Cohesion: 0.24
Nodes (18): CancelCheck, ProgressCallback, _attach_embeddings(), AudioDedupCancelled, _connect_readonly(), count_database_tracks(), find_duplicate_groups(), load_tracks() (+10 more)

### Community 131 - "Personal Classifier Workflow"
Cohesion: 0.17
Nodes (17): Feature Ablation Benchmark, Calibration Data Gate, Database-Only Classifier Scoring, Immutable Generation Promotion, Ordered Classifier Feature Recipe, Personal Classifier Workflow, Reusable Ranking Signal, Not Truth, Rhythm Lab Isolated State (+9 more)

### Community 132 - "test_api_rhythm_lab.py"
Cohesion: 0.20
Nodes (17): _add_track(), _identity_payload(), Path, TrackIdentity, test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(), test_rhythm_lab_collection_save_rejects_legacy_numeric_only_body(), test_rhythm_lab_default_log_path_uses_logs_directory(), test_rhythm_lab_launch_endpoint_allows_no_selected_database() (+9 more)

### Community 134 - "qa_database.py"
Cohesion: 0.23
Nodes (16): _build_parser(), _fail(), _foreign_key_check(), _integrity_check(), main(), _open_read_only(), ArgumentParser, Connection (+8 more)

### Community 135 - "read_local_evidence"
Cohesion: 0.22
Nodes (14): _find_by_metadata(), _find_by_path(), Connection, Path, Row, Return tags and at most three MAEST genres from one unambiguous local track., read_local_evidence(), Path (+6 more)

### Community 136 - "judged.py"
Cohesion: 0.21
Nodes (19): build_judged_label_gate(), _first_label_for_any_source(), judged_label_guidance(), judged_label_status(), _labels_by_rating(), matched_judged_labels(), MatchedJudgedLabel, matching_label() (+11 more)

### Community 137 - "api_routes_search.py"
Cohesion: 0.10
Nodes (19): _clap_text_search_plan(), _ClapTextSearchPlan, _clean_text_queries(), _hydrate_search_target(), _hydrate_similarity_results(), FastAPI, FloatArray, Protocol (+11 more)

### Community 138 - "Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Есть ли смысл сделать копию всех треков в самом низком и оптимизированном качестве для быстрой прогрузки, прослушивания и переноски вместе с базой, оставив анализ на оригиналах?, Source Nodes

### Community 139 - "Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Как сейчас реализована передача аудиоданных в ML-модели и как перевести ее на TorchCodec 0.16 CUDA без смены preprocessing revisions?, Source Nodes

### Community 140 - "load_classifier_requirements"
Cohesion: 0.25
Nodes (13): load_classifier_requirements(), Validate the classifier recipe, required inputs, and artifact. This function is…, _require_available_outputs(), _FixedProbabilityModel, _insert_track(), _mert_output(), ndarray, Path (+5 more)

### Community 141 - "models.py"
Cohesion: 0.15
Nodes (23): _artists(), _label(), Beatport v4 Catalog Search adapter using documented bearer authentication., _record(), _text(), _year(), Read local genre evidence without modifying a library database., _normalized() (+15 more)

### Community 142 - "Classifier Workflow"
Cohesion: 0.22
Nodes (13): Benchmark Variants, Broken vs Straight Beat Classifier, Classifier Workflow, Collect Labels, Local Music Library, Music Attribute Classifiers, Personal Music Classifiers, Production Readiness (+5 more)

### Community 143 - "LibraryDatabase"
Cohesion: 0.21
Nodes (18): LibraryDatabase, Connection, EvaluationRepository, ndarray, Path, test_validate_database_cli_uses_concise_human_messages(), test_validator_reports_corrupt_embedding_payload(), test_validator_reports_each_track_and_does_not_mutate_database() (+10 more)

### Community 144 - "api_routes_analysis.py"
Cohesion: 0.24
Nodes (14): AnalysisResetResult, _classifier_info_by_key(), _classifier_manifest_error_text(), _outputs_for_family(), FastAPI, register_analysis_routes(), _require_known_classifier(), _require_scoring_compatible_classifier() (+6 more)

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
Nodes (39): Background and synchronous jobs for the sole scan repository path., ScanLogEvent, _validate_duration_bounds(), _audio_format(), _audio_format_from_mime(), _contains_tag(), file_tags_from_metadata(), _genres() (+31 more)

### Community 152 - "AnalysisPipelineManager"
Cohesion: 0.13
Nodes (15): AnalysisPipelineManager, AnalysisPipelineStatus, _PipelinePayload, PipelineStageStatus, AnalysisStageQueue, One in-memory worker shared by SONARA, ML, and classifier stages., FakeJobs, test_parent_cancel_before_start_removes_pending_stages() (+7 more)

### Community 153 - "test_api_dialog.py"
Cohesion: 0.32
Nodes (11): _add_track(), fixture, Path, _shared_ffmpeg(), test_choose_folder_endpoint_allows_cancel(), test_choose_folder_endpoint_reports_unavailable_dialog(), test_choose_folder_endpoint_returns_selected_path(), test_create_app_requires_shared_ffmpeg() (+3 more)

### Community 154 - "Audio Online"
Cohesion: 0.20
Nodes (12): Audio Online, Beatport Client-Credentials OAuth, Exact Local Path Lookup, Local OAuth Configuration, Matched Does Not Mean Correct Genre, MusicBrainz User-Agent and Rate Limit, Provider Evidence Workbook, Standalone Read-Only Boundary (+4 more)

### Community 155 - "metadataReference.test.mjs"
Cohesion: 0.22
Nodes (8): detail(), metadataDialog, referenceCompare, sonaraFeatures(), srcDir, summary(), syncopatedRhythm, trackDisplay

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

### Community 161 - "GenreTagJobManager"
Cohesion: 0.31
Nodes (4): GenreTagError, GenreTagJobManager, GenreTagJobStatus, GenreTagLogEvent

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

### Community 173 - "renderGuidance"
Cohesion: 0.21
Nodes (15): formatHumanDate(), formatMetricDelta(), formatMetricPercent(), metricNumberText(), metricPercentText(), parseTrainingDate(), promotionOptionLabel(), refreshTrainingInformation() (+7 more)

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
Cohesion: 0.12
Nodes (31): submitPageInput(), bpmFilterValue(), currentPage(), deleteActiveProfile(), jumpToPage(), loadActive(), loadCandidates(), loadCollectionTracks() (+23 more)

### Community 180 - ".tags"
Cohesion: 0.29
Nodes (13): TrackIdentity, _save_maest_genres(), _scan_track(), test_apply_genre_tags_overwrites_standard_genre_tag(), test_apply_genre_tags_refreshes_database_metadata_and_preserves_existing_file_tags(), test_apply_genre_tags_reports_failed_invalid_wave_and_continues(), test_custom_tag_api_is_not_available(), test_genre_tag_job_api_rejects_specific_track_ids() (+5 more)

### Community 181 - "test_api_analysis_jobs.py"
Cohesion: 0.20
Nodes (29): create_api_client(), MonkeyPatch, Path, TestClient, _analysis_start(), _client(), MonkeyPatch, parametrize (+21 more)

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

### Community 188 - "validate_maest_analysis_row"
Cohesion: 0.33
Nodes (9): MaestAnalysisRow, parse_maest_genres_json(), Canonical semantic validation for persisted MAEST analysis rows., Validate one complete MAEST analysis row against writer semantics., Parse canonical MAEST genre JSON without silently dropping entries., _required_int(), _required_text(), _row_values() (+1 more)

### Community 189 - "config.mts"
Cohesion: 0.40
Nodes (4): commonTheme, englishNav, englishSidebar, SidebarSection

### Community 190 - "test_analysis_sonara_preflight.py"
Cohesion: 0.16
Nodes (12): SimpleNamespace, _client(), _CoverageRepository, _PreflightTrapAnalysisJobs, MonkeyPatch, Path, TestClient, test_pipeline_job_creation_does_not_run_release_preflight() (+4 more)

### Community 192 - "_coverage_and_classifiers"
Cohesion: 0.26
Nodes (16): _classifier_summaries(), _coverage_and_classifiers(), _current_classifier_details(), _identity_map(), _json_ids(), AnalysisCoverage, ClassifierScoreDetail, ClassifierScoreSummary (+8 more)

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

### Community 216 - "connect_evaluation_sidecar"
Cohesion: 0.35
Nodes (11): _apply_schema(), _configure_connection(), connect_evaluation_sidecar(), create_evaluation_sidecar_schema(), _creation_lock_path(), _enforce_wal(), Connection, Path (+3 more)

### Community 224 - "api_state.py"
Cohesion: 0.25
Nodes (16): DatabaseBusy, DatabaseNotSelected, RuntimeError, _client(), Path, TestClient, test_classifier_preflight_conflict_returns_http_409_before_start(), test_database_switch_bootstraps_clean_selected_current_bundle() (+8 more)

### Community 225 - "EmbeddingOutput"
Cohesion: 0.32
Nodes (12): EmbeddingOutput, Path, test_current_embedding_removes_track_from_its_analysis_candidates(), test_embedding_round_trip_uses_the_library_connection(), test_evaluation_profile_creates_the_optional_sidecar_on_save(), test_library_records_each_scanned_root_once(), test_library_summary_counts_embedding_rows_directly(), test_new_library_database_bootstraps_one_sqlite_file() (+4 more)

### Community 226 - "Q: как реализована передача аудио в MULAN"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как реализована передача аудио в MULAN, Source Nodes

### Community 227 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 228 - "dj_track_similarity/__init__.py"
Cohesion: 0.25
Nodes (4): ModuleType, Local dj-track-similarity toolkit., Path, test_transcoded_wav_preview_uses_torchcodec_without_executable()

### Community 229 - "Q: Проанализируй реализацию извлечения эмбов в MULam в проекте"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Проанализируй реализацию извлечения эмбов в MULam в проекте, Source Nodes

### Community 230 - "Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA, Source Nodes

### Community 231 - "dj_track_similarity/cli.py"
Cohesion: 0.10
Nodes (59): command, analyze(), analyze_classifier(), analyze_pipeline(), classifier_calibration_report(), classifier_suggest_labels(), _db(), _emit_json_report() (+51 more)

### Community 232 - "_library_with_maest_candidate"
Cohesion: 0.61
Nodes (7): _library_with_maest_candidate(), _make_tagged_wave(), Path, test_genre_tag_apply_rejects_cross_catalog_candidate_before_source_write(), test_genre_tag_apply_rejects_stale_files_before_source_write(), test_genre_tag_apply_requires_readback_before_recording_self_write(), test_genre_tag_job_uses_current_candidate_and_preserves_tags()

### Community 233 - "api_routes_library.py"
Cohesion: 0.13
Nodes (27): field_validator, FileResponse, HTTPException, current_classifier_specifications(), query_classifier_min_scores(), valid_classifier_min_scores(), _evaluation_schema_error(), Exception (+19 more)

### Community 234 - "classifier_scoring.py"
Cohesion: 0.10
Nodes (28): classifier_manifest_api_fields(), _manifest_for_classifier(), _argmax_with_tiebreak(), classifier_artifact_slug(), _classifier_key_from_metadata_or_slug(), default_classifier_model_path(), default_classifier_models_root(), _load_payload() (+20 more)

### Community 235 - "scanImportDialog.test.mjs"
Cohesion: 0.40
Nodes (4): appPath, dialogPath, panelPath, srcDir

### Community 236 - "test_reference_compare_uses_current_outputs_and_current_summaries"
Cohesion: 0.43
Nodes (7): _insert_track(), _mert_output(), _mert_vector(), ndarray, Path, _sonara_row(), test_reference_compare_uses_current_outputs_and_current_summaries()

### Community 237 - "useConfirmation"
Cohesion: 0.29
Nodes (4): ConfirmationRequest, ConfirmationState, useConfirmation(), requestConfirmation()

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

### Community 252 - "_scan_track"
Cohesion: 0.52
Nodes (6): Path, TrackIdentity, _scan_track(), test_export_endpoint_writes_current_track_list_without_saving_playlist(), test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(), test_saved_playlist_endpoint_is_absent()

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

### Community 257 - "db_search_fts.py"
Cohesion: 0.25
Nodes (12): delete_track_search_fts(), _file_genres_text(), _maest_genres_text(), Connection, Track-search FTS maintenance. The FTS index contains only text a person can…, Delete one track from the live FTS index without committing., Refresh one track's human-text FTS row without committing., Rebuild the human-text FTS index atomically. If the caller already owns a… (+4 more)

### Community 258 - "test_api_tracks.py"
Cohesion: 0.33
Nodes (17): _add_track(), _client(), _liked_payload(), Path, TestClient, TrackIdentity, test_media_endpoint_reports_missing_audio_file_without_traceback(), test_media_endpoint_reports_transcode_failure_without_traceback() (+9 more)

### Community 259 - "track_views.py"
Cohesion: 0.27
Nodes (11): _active_sonara_rows(), _analysis_target(), load_all_transition_tracks(), _load_transition_tracks(), load_transition_tracks_for_ids(), load_transition_tracks_for_targets(), TrackIdentity, Identity-bound typed track views for evaluation workflows. (+3 more)

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

### Community 269 - "User Guide"
Cohesion: 0.40
Nodes (5): Listening-Led Shortlisting, DJ Library UI Workbench, User Guide, Outcome-Oriented Workflow Routing, Preview-First Working Habit

### Community 270 - "Q: как определяются есть ли уже трек в базе или нет при загркузке новых?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как определяются есть ли уже трек в базе или нет при загркузке новых?, Source Nodes

### Community 271 - "Russian Project Overview"
Cohesion: 0.25
Nodes (8): Accepted Project Vocabulary, Report-First Maintenance Tools, Rhythm Lab Personal Classifiers, Russian CLAP Text Search Explanation, Russian Multi-Model Similarity Explanation, Russian Project Overview, Russian Report-First Helper Tools, Russian Rhythm Lab Explanation

### Community 274 - "Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе., Source Nodes

### Community 275 - "Q: Почему данные в базу не пишутся?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Почему данные в базу не пишутся?, Source Nodes

### Community 276 - "track_models.py"
Cohesion: 0.09
Nodes (34): _library_roots_from_json(), _library_roots_json(), ordinal_path_key(), _plan_relocation(), Row, Thread-safe track repository for the single library database., Record a scan root in ``library.roots_json`` without duplicates., Return the deterministic identity key for an already absolute path. Windows… (+26 more)

### Community 277 - "Q: где проблема"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: где проблема, Source Nodes

### Community 279 - "runtime.py"
Cohesion: 0.52
Nodes (6): doctor(), _detect_nvidia_smi_cuda(), get_torch_runtime_info(), _parse_cuda_version(), recommended_torch_index(), TorchRuntimeInfo

### Community 281 - "test_classifier_jobs.py"
Cohesion: 0.35
Nodes (10): _insert_present_classifier_inputs(), _insert_track(), _mert_output(), MonkeyPatch, Path, Create more persisted classifier inputs than one job batch holds., _requirements(), _score_count() (+2 more)

### Community 282 - "api_routes_rhythm_lab.py"
Cohesion: 0.14
Nodes (15): RhythmLabSourceBinding, BaseModel, FastAPI, model_validator, register_rhythm_lab_routes(), RhythmLabCollectionSaveRequest, build_rhythm_lab_collection_selection_exact(), default_rhythm_lab_labels_path() (+7 more)

### Community 283 - "test_config.py"
Cohesion: 0.33
Nodes (6): CaptureFixture, Path, Prevent silently sending a credential to an unimplemented service., Prevent OAuth session material from leaking into normal CLI output., test_load_config_rejects_unknown_configured_source(), test_save_auth_data_persists_session_without_printing_secret()

### Community 284 - "test_api_evaluation.py"
Cohesion: 0.32
Nodes (14): _client(), ndarray, parametrize, Path, TestClient, test_evaluation_api_rejects_unselected_and_legacy_database(), test_evaluation_feedback_does_not_touch_audio_path(), test_evaluation_feedback_endpoints_validate_and_preserve_seed_scope() (+6 more)

### Community 287 - "test_scanner_runtime.py"
Cohesion: 0.31
Nodes (14): Reconcile one audio file using exact nanosecond filesystem facts. An unchanged…, scan_audio_file(), _make_tagged_wav(), _make_wav(), Path, test_iter_audio_files_skips_an_unreadable_subdirectory(), test_parallel_tag_refresh_updates_tags_and_fts_without_generation_change(), test_scan_audio_file_never_persists_mixed_metadata_after_bounded_churn() (+6 more)

### Community 289 - "db_library_queries.py"
Cohesion: 0.09
Nodes (38): SonaraCore, _base_from_sql(), _current_analysis_row_count(), _current_artifact_row_count(), _file_tags(), _filter_sql(), _fts_query(), _json_array() (+30 more)

### Community 294 - "storage_database_paths"
Cohesion: 0.14
Nodes (21): CompletedProcess, parametrize, Path, _run_benchmark(), _run_benchmark_raw(), test_benchmark_search_keep_db_preserves_current_bundle(), test_benchmark_search_rejects_invalid_vector_backend(), test_benchmark_search_rejects_output_that_overlaps_keep_db() (+13 more)

### Community 295 - "test_qa_database_script.py"
Cohesion: 0.70
Nodes (4): _load_script(), Path, test_qa_database_allows_future_library_tables(), test_qa_database_checks_library_and_optional_evaluation()

### Community 298 - "AnalysisCandidate"
Cohesion: 0.05
Nodes (58): AnalysisBatchItem, decode_analysis_batch(), DecodeFailure, DecodeAudio, A full-track decode error deferred to a model-specific recovery path., AnalysisCandidate, analyze_and_store_staged_ml(), cleanup_orphaned_ml_staging() (+50 more)

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

## Ambiguous Edges - Review These
- `Recording Indicator` → `Rhythm Lab Favicon`  [AMBIGUOUS]
  tools/rhythm-lab/rhythm_lab/static/favicon.svg · relation: references

## Knowledge Gaps
- **476 isolated node(s):** `SidebarSection`, `englishNav`, `englishSidebar`, `commonTheme`, `name` (+471 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `DecodedAudio` (9× useful, score=8.227351765)
- `EmbeddingModelRunner` (9× useful, score=8.220286205)
- `MuqMulanEmbeddingAdapter` (7× useful, score=6.393433647)
- `MaestEmbeddingAdapter` (5× useful, score=4.576633263)
- `ScanJobManager` (4× useful, score=3.87756238)
- `ClapEmbeddingAdapter` (4× useful, score=3.658153136)
- `MertEmbeddingAdapter` (4× useful, score=3.658153136)
- `MuqEmbeddingAdapter` (4× useful, score=3.658153136)
- `load_decoded_audio()` (4× useful, score=3.657007628)
- `scanner.py` (3× useful, score=2.914289744)

**Known dead ends** — questions that led nowhere; don't re-derive.
- "Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?" -> `docsRoot`

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Recording Indicator` and `Rhythm Lab Favicon`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `LibraryDatabase` connect `LibraryDatabase` to `candidates.py`, `test_api_tracks.py`, `track_views.py`, `database.py`, `test_api_rhythm_lab.py`, `weighted_candidates.py`, `run_report`, `api_routes_search.py`, `reports.py`, `ClassifierJobManager`, `load_classifier_requirements`, `classifier_jobs.py`, `AnalysisOutput`, `score_profiles.py`, `test_api_dialog.py`, `test_classifier_jobs.py`, `evaluation/ablation.py`, `test_api_evaluation.py`, `risk_sweep.py`, `collect_repository_paths`, `test_evaluation_cli.py`, `test_scanner_runtime.py`, `source_profile.py`, `test_scan_jobs.py`, `test_audio_dedup.py`, `test_api_sonara_search.py`, `test_repair_audio_metadata.py`, `storage_database_paths`, `test_qa_database_script.py`, `SonaraSimilaritySearch`, `TrackIdentity`, `export_seed_sample`, `AnalysisCandidate`, `AnalysisTarget`, `calibration.py`, `EvaluationRepository`, `test_api_analysis_jobs.py`, `.tags`, `benchmark_search.py`, `test_analysis_orchestration.py`, `classifier_production.py`, `ClassifierSpecification`, `rhythm_lab/cli.py`, `score_profile_optimizer.py`, `recorded_sessions.py`, `EmbeddingTrackIdentity`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `project_clap_search.py`, `build_score_profile_optimizer_report`, `seed_sampling.py`, `FileTags`, `api_state.py`, `EmbeddingOutput`, `DatabaseValidator`, `create_app`, `AppDatabaseState`, `dj_track_similarity/cli.py`, `_library_with_maest_candidate`, `classifier_scoring.py`, `vector_index.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `main`, `scan_library`, `tests/test_cli.py`, `build_weighted_candidate_pool`, `_scan_track`, `TrackRepository`, `test_api_database_selection.py`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `AnalysisTarget` connect `AnalysisTarget` to `sonara_similarity.py`, `candidates.py`, `track_views.py`, `api_routes_search.py`, `load_classifier_requirements`, `sonara_similarity_scoring.py`, `ann_index.py`, `AnalysisOutput`, `test_consumers.py`, `analysis_models.py`, `test_classifier_jobs.py`, `test_api_evaluation.py`, `test_evaluation_cli.py`, `test_api_sonara_search.py`, `SonaraSimilaritySearch`, `TrackIdentity`, `AnalysisCandidate`, `export_seed_sample`, `EvaluationRepository`, `_Repository`, `test_multi_model_analysis_jobs.py`, `compute_transition_diagnostics`, `.tags`, `analyze_and_store_sonara_batch`, `benchmark_search.py`, `test_analysis_orchestration.py`, `artifact_io.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `TrackSummary`, `tempo_resolution.py`, `EmbeddingOutput`, `create_app`, `_library_with_maest_candidate`, `vector_index.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `sonara_features.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `AnalysisOutput` connect `AnalysisOutput` to `sonara_similarity.py`, `candidates.py`, `load_classifier_requirements`, `ann_index.py`, `api_routes_analysis.py`, `test_consumers.py`, `analysis_models.py`, `test_classifier_jobs.py`, `test_evaluation_cli.py`, `db_library_queries.py`, `current_embedding_analysis_output`, `test_api_sonara_search.py`, `SonaraSimilaritySearch`, `AnalysisCandidate`, `export_seed_sample`, `EvaluationRepository`, `_Repository`, `AnalysisTarget`, `test_multi_model_analysis_jobs.py`, `analyze_and_store_sonara_batch`, `benchmark_search.py`, `analysis_jobs.py`, `test_analysis_orchestration.py`, `classifier_production.py`, `ClassifierSpecification`, `_coverage_and_classifiers`, `artifact_io.py`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `sonara_storage.py`, `EmbeddingOutput`, `create_app`, `AnalysisModelRunner`, `vector_index.py`, `classifier_scoring.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `sonara_features.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 138 inferred relationships involving `LibraryDatabase` (e.g. with `run_source_file_search()` and `_active_embedding_output()`) actually correct?**
  _`LibraryDatabase` has 138 INFERRED edges - model-reasoned connections that need verification._
- **Are the 101 inferred relationships involving `AnalysisOutput` (e.g. with `_active_embedding_output()` and `_store_synthetic_embeddings()`) actually correct?**
  _`AnalysisOutput` has 101 INFERRED edges - model-reasoned connections that need verification._
- **Are the 91 inferred relationships involving `AnalysisTarget` (e.g. with `_store_synthetic_embeddings()` and `_candidates_without_seed()`) actually correct?**
  _`AnalysisTarget` has 91 INFERRED edges - model-reasoned connections that need verification._
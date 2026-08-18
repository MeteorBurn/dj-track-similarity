# Graph Report - dj-track-similarity  (2026-08-18)

## Corpus Check
- 432 files · ~398,964 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6559 nodes · 18715 edges · 306 communities (278 shown, 28 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1625 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d383cf68`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- FileTags
- _required_text
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
- compute_transition_diagnostics
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
- tags.py
- test_audio_dedup.py
- current_embedding_analysis_output
- test_repair_audio_metadata.py
- candidates.py
- DecodedAudio
- SonaraSimilaritySearch
- TrackIdentity
- test_evaluation_seed_sampling.py
- ffmpeg_runtime.py
- EvaluationRepository
- classifier_manifest.py
- _Repository
- transition_diagnostics.py
- current_embedding_spec
- test_multi_model_analysis_jobs.py
- calibration.py
- audio_loader.py
- EvaluationRepository
- AnalysisJobManager
- analyze_and_store_sonara_batch
- SearchPlaylistPanel.tsx
- benchmark_search.py
- AnalysisBatchItem
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
- DatabaseValidator
- EmbeddingTrackIdentity
- test_classifier_scoring.py
- test_api_reference_compare.py
- reference_compare.py
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
- isMulticlassProfile
- load_tracks
- report.py
- seed_sampling.py
- test_sonara_storage.py
- JobStore
- audio_dedup/core.py
- embedding.py
- compilerOptions
- DatabaseValidationJobManager
- create_app
- AnalysisPipelineManager
- AppDatabaseState
- select_torch_device
- AnalysisTarget
- VerifiedAssetBinding
- main
- PresetConfig
- loadActive
- wave_tags.py
- artifact_io.py
- sonara_features.py
- test_benchmark_search.py
- DJ Track Similarity Banner
- MaestWindowContext
- tests/test_cli.py
- optimize_database.py
- Q: Какая версия FAST API у меня сейчас?
- build_weighted_candidate_pool
- ClassifierScoreDetail
- TrackRecord
- FileRepairResult
- score_prompt_bank.py
- scripts
- track_models.py
- test_api_database_selection.py
- Workflows
- AnalysisVectorRow
- loadTrainingReadiness
- run_report
- Personal Classifier Workflow
- test_vector_index.py
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
- test_evaluation_score_profile_optimizer.py
- SimilaritySearch
- trackMarkup
- run-vale.mjs
- Search with Seed Tracks
- Know When Audio Files Can Be Written
- tooltipLayer.tsx
- test_run_server_lan_script.py
- scanner.py
- AnalysisStageQueue
- test_api_dialog.py
- Audio Online
- metadataReference.test.mjs
- rhythm_lab_impact_payload
- build_report_payload
- TrackPathRecord
- Normalized Prompt Ensemble
- validate_prompt_bank.py
- dj_track_similarity/__init__.py
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
- api_routes_analysis.py
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- Local-First DJ Library Workbench
- loadCandidates
- test_api_rhythm_lab.py
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
- test_api_runtime.py
- .get_track_detail
- Q: как реализована передача аудио в MULAN
- What You Must Do When Invoked
- _move_maest_runtime_modules
- Q: Проанализируй реализацию извлечения эмбов в MULam в проекте
- Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA
- dj_track_similarity/cli.py
- create_library_schema
- media_preview.py
- classifier_scoring.py
- scanImportDialog.test.mjs
- ._device
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
- sonara_core_validation.py
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
- api_routes_tags_export.py
- playlistAddHandler.test.mjs
- Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе.
- Q: Почему данные в базу не пишутся?
- _add_track
- Q: где проблема
- _parse_source_contribution
- runtime.py
- TrainingProgress
- test_classifier_jobs.py
- api_routes_rhythm_lab.py
- test_config.py
- test_api_evaluation.py
- _scan_track
- test_evaluation_optimizer_e2e.py
- scan_library
- LibraryQueryRepository
- db_library_queries.py
- test_ffmpeg_runtime.py
- _parse_args
- create_api_client
- storage_database_paths
- test_qa_database_script.py
- AnalysisCandidate
- LibraryDatabase
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
- `Russian CLAP Text Search Explanation` --semantically_similar_to--> `CLAP Text-to-Audio and Audio-to-Audio Search`  [INFERRED] [semantically similar]
  README_RU.md → README.md
- `Russian Multi-Model Similarity Explanation` --semantically_similar_to--> `Separated Model Evidence Sources`  [INFERRED] [semantically similar]
  README_RU.md → README.md
- `Rhythm Lab Collection Save` --semantically_similar_to--> `Auxiliary Classifier UI`  [INFERRED] [semantically similar]
  docs/dj-track-similarity/user-guide/export-playlists.md → tools/rhythm-lab/README.md
- `Report-First Maintenance Tools` --semantically_similar_to--> `Local-First Safety Baseline`  [INFERRED] [semantically similar]
  README.md → AGENTS.md
- `Russian Local-First Workbench Description` --semantically_similar_to--> `Local-First DJ Library Workbench`  [INFERRED] [semantically similar]
  README_RU.md → README.md

## Import Cycles
- 2-file cycle: `frontend/src/api.ts -> frontend/src/apiClient.ts -> frontend/src/api.ts`

## Hyperedges (group relationships)
- **SONARA, ML, and Classifier Stage Separation** — docs_dj_track_similarity_reference_analysis_families_sonara_core, docs_dj_track_similarity_reference_analysis_families_ml_embedding_families, docs_dj_track_similarity_reference_analysis_families_database_only_classifier_scoring, docs_dj_track_similarity_user_guide_analyze_library_staged_analysis_workflow [EXTRACTED 1.00]
- **Core Music Workbench Capabilities** — img_dj_track_similarity_banner_genre_detection, img_dj_track_similarity_banner_music_classification, img_dj_track_similarity_banner_similarity_search, img_dj_track_similarity_banner_dj_set_building, img_dj_track_similarity_banner_track_diagnostics, img_dj_track_similarity_banner_library_exploration [EXTRACTED 1.00]
- **Classifier Lifecycle** — img_rhythm_lab_banner_collect_labels, img_rhythm_lab_banner_train_model, img_rhythm_lab_banner_review_candidates, img_rhythm_lab_banner_benchmark_variants, img_rhythm_lab_banner_promote_model [EXTRACTED 1.00]
- **Local-first safety boundaries** — docs_dj_track_similarity_concepts_local_first_safety_read_only_audio_workflows, docs_dj_track_similarity_concepts_local_first_safety_source_file_write_paths, docs_dj_track_similarity_concepts_local_first_safety_database_boundary [EXTRACTED 1.00]
- **Model evidence surfaces** — docs_dj_track_similarity_concepts_features_embeddings_tags_sonara_features, docs_dj_track_similarity_concepts_features_embeddings_tags_maest_representation, docs_dj_track_similarity_concepts_features_embeddings_tags_mert_embedding, docs_dj_track_similarity_concepts_features_embeddings_tags_muq_embedding, docs_dj_track_similarity_concepts_features_embeddings_tags_clap_audio_embedding [EXTRACTED 1.00]
- **DJ Audio Visual Identity** — docs_dj_track_similarity_public_logo_dark_logo, docs_dj_track_similarity_public_logo_dark_vinyl_record_motif, docs_dj_track_similarity_public_logo_dark_audio_level_motif, docs_dj_track_similarity_public_logo_dark_audio_waveform_motif [INFERRED 0.85]
- **DJ Track Similarity Brand Identity** — docs_dj_track_similarity_public_logo_light_logo, docs_dj_track_similarity_public_logo_light_dj_track_similarity, docs_dj_track_similarity_public_logo_light_vinyl_record, docs_dj_track_similarity_public_logo_light_audio_signal_motif, docs_dj_track_similarity_public_logo_light_similarity_spectrum [INFERRED 0.85]
- **Listening-Led Discovery Surfaces** — docs_dj_track_similarity_user_guide_search_with_seeds_seed_search, docs_dj_track_similarity_user_guide_text_search_clap_text_search, docs_dj_track_similarity_workflows_build_crates_crate_workflow, docs_dj_track_similarity_workflows_find_compatible_tracks_compatible_track_workflow [INFERRED 0.85]
- **Local Data Safety Model** — docs_dj_track_similarity_index_local_first_ranked_workflow, docs_dj_track_similarity_index_explicit_audio_write_boundary, docs_dj_track_similarity_reference_database_unified_library_database, docs_dj_track_similarity_tools_and_scripts_audio_doctor_dry_run_first_repair, docs_dj_track_similarity_tools_and_scripts_audio_dedup_destructive_apply_guard, docs_dj_track_similarity_tools_and_scripts_optimize_database_verified_sqlite_maintenance [INFERRED 0.85]
- **Rhythm Lab Visual Identity** — tools_rhythm_lab_rhythm_lab_static_favicon_audio_waveform_motif, tools_rhythm_lab_rhythm_lab_static_favicon_recording_indicator, tools_rhythm_lab_rhythm_lab_static_favicon_rounded_square_background [INFERRED 0.85]
- **CLAP Retrieval and Prompting Stack** — _agents_skills_clap_query_workflow_skill_clap_query_workflow, _agents_skills_clap_query_workflow_references_clap_prompting_reference_clap_prompting_reference, readme_clap [INFERRED 0.95]
- **Local Classifier Lifecycle** — docs_dj_track_similarity_tools_and_scripts_rhythm_lab_isolated_rhythm_lab_state, docs_dj_track_similarity_tools_and_scripts_rhythm_lab_promoted_classifier_artifacts, docs_dj_track_similarity_reference_analysis_families_database_only_classifier_scoring, docs_dj_track_similarity_user_guide_class_tab_personal_classifier_score, docs_dj_track_similarity_user_guide_class_tab_atomic_classifier_generation, docs_dj_track_similarity_user_guide_class_tab_manifest_compatibility_guard [INFERRED 0.95]
- **Confirmation-Gated Audio Operations** — docs_dj_track_similarity_user_guide_tags_and_audio_writes_audio_write_boundary, tools_audio_doctor_readme_dry_run_repair, tools_audio_dedup_readme_report_first_deletion [INFERRED 0.95]
- **Model Evidence Stack** — img_dj_track_similarity_banner_sonara, img_dj_track_similarity_banner_maest, img_dj_track_similarity_banner_mert, img_dj_track_similarity_banner_muq, img_dj_track_similarity_banner_clap, img_dj_track_similarity_banner_classifiers [INFERRED 0.95]
- **Listening-led selection loop** — docs_dj_track_similarity_concepts_project_idea_listening_led_local_workbench, docs_dj_track_similarity_concepts_similarity_scores_audition_order_scores, docs_dj_track_similarity_getting_started_quickstart_listening_led_quickstart_loop [INFERRED 0.95]
- **Local-First Safety Contract** — agents_local_first_safety_baseline, readme_report_first_maintenance, _agents_skills_codebase_documentation_writer_skill_local_first_safety_language, _agents_skills_clap_query_workflow_skill_audio_read_only_search [INFERRED 0.95]
- **Personal Classifier Lifecycle** — docs_dj_track_similarity_workflows_train_personal_classifier_personal_classifier_workflow, tools_rhythm_lab_readme_auxiliary_classifier_ui, tools_rhythm_lab_rhythm_lab_static_index_training_and_profile_creation, docs_dj_track_similarity_workflows_reanalyze_sonara_split_storage_classifier_refresh [INFERRED 0.95]

## Communities (306 total, 28 thin omitted)

### Community 0 - "FileTags"
Cohesion: 0.17
Nodes (37): ID3, _write_genre_tag(), FileTags, Human-readable tags read from an audio file., _decoded_audio_md5(), _make_tone(), parametrize, Path (+29 more)

### Community 2 - "label_transfer.py"
Cohesion: 0.08
Nodes (104): _absolute_lexical_path(), _backup_restore_target(), _build_parser(), build_rebound_bundle(), _build_restore_plan(), _canonical_json_bytes(), _canonical_json_text(), canonical_path_key() (+96 more)

### Community 3 - "source_db.py"
Cohesion: 0.05
Nodes (73): _attach_labels(), _base_track_query(), _clean_path_text(), _count_sonara_features(), _embedding_family(), _embedding_vector(), _feature_counts(), _feature_source_states() (+65 more)

### Community 4 - "database.py"
Cohesion: 0.12
Nodes (31): RLock, Path, _bootstrap_file_lock(), _bootstrap_lock_path(), _cleanup_staged_sqlite(), _configure_connection(), connect_database(), _create_fresh_library() (+23 more)

### Community 5 - "Main project"
Cohesion: 0.06
Nodes (32): Audio Dedup, Audio Doctor, Audio Online, Commands and arguments, `dj-sim analyze`, `dj-sim analyze-classifier CLASSIFIER`, `dj-sim analyze-pipeline`, `dj-sim classifier calibration-report` (+24 more)

### Community 6 - "weighted_candidates.py"
Cohesion: 0.11
Nodes (29): CandidatePoolRow, CandidateSourceContribution, _clean_sources(), _effective_source_count(), _identity_payload(), _int_value(), _non_negative_finite_float(), _normalized_response_score() (+21 more)

### Community 7 - "RhythmLabDatabase"
Cohesion: 0.07
Nodes (52): _canonical_json(), _classifier_label_from_row(), _classifier_label_queue_table_sql(), _classifier_labels_table_sql(), _classifier_predictions_table_sql(), _classifier_training_checkpoints_table_sql(), ClassifierLabel, ClassifierPredictionWrite (+44 more)

### Community 8 - "App"
Cohesion: 0.07
Nodes (62): App(), addVisibleTracksToPlaylist(), adoptClassifierProfiles(), beginGenericSearchRequest(), cancelGenericSearchRequest(), cancelTrackDetailRequest(), commitGenericSearchResults(), finishGenericSearchRequest() (+54 more)

### Community 9 - "app.js"
Cohesion: 0.04
Nodes (58): addMulticlassLabelRow(), binaryLabelGridEl, bpmMaxEl, bpmMinEl, candidateFiltersEl, candidateMinBrokenEl, candidateMinPositiveEl, candidatePredictedEl (+50 more)

### Community 10 - "build_analysis_job_config"
Cohesion: 0.17
Nodes (19): build_analysis_job_config(), _int_in_range(), normalize_analysis_device(), normalize_analysis_models(), _normalize_limit(), normalize_sonara_mode(), parametrize, test_build_analysis_job_config_has_no_sonara_output_selection() (+11 more)

### Community 11 - "reports.py"
Cohesion: 0.11
Nodes (58): _aggregate_variant_metrics(), report_status_for_judged_gate(), average_precision_at_k(), _axis_value(), bad_suggestion_rate_at_k(), _comparison_match_character(), _comparison_rank(), _comparison_reason_tags() (+50 more)

### Community 12 - "ClassifierJobManager"
Cohesion: 0.12
Nodes (12): ClassifierCandidate, ClassifierJobManager, ClassifierJobStatus, ClassifierLogEvent, _ClassifierPayload, ClassifierTrackError, Exception, Path (+4 more)

### Community 13 - "sonara_similarity_scoring.py"
Cohesion: 0.12
Nodes (42): _merge_targets(), _optional_targets(), _optional_track_ids(), RuntimeError, Resolve request IDs to current tracks with active SONARA Core., Choose one unselected current track with valid SONARA Core features., Raised when no current SONARA Core data can serve search., _requested_track_ids() (+34 more)

### Community 14 - "ann_index.py"
Cohesion: 0.08
Nodes (64): _active_index_output(), _artifact_path_from_manifest(), _artifact_paths(), _assert_inside_directory(), _benchmark_k_values(), benchmark_persistent_index(), _build_manifest(), build_persistent_index() (+56 more)

### Community 15 - "api_schemas.py"
Cohesion: 0.09
Nodes (44): field_validator, HTTPException, current_classifier_specifications(), query_classifier_min_scores(), valid_classifier_min_scores(), _evaluation_schema_error(), Exception, FastAPI (+36 more)

### Community 16 - "Reference Index"
Cohesion: 0.05
Nodes (63): Explicit Audio Write Boundary, DJ Track Similarity Documentation Home, Local-First Ranked Workflow, Listening-Led Shortlisting, Project Guide, Analysis Families Reference, Database-Only Classifier Scoring, ML Embedding Families (+55 more)

### Community 17 - "compute_transition_diagnostics"
Cohesion: 0.16
Nodes (29): compute_transition_diagnostics(), _mean_available(), Compute transition risk from identity-validated repository rows., _risk_version(), TransitionDiagnostics, _classifier_score(), ClassifierScoreSummary, test_adjacent_camelot_key_has_lower_risk_than_clash() (+21 more)

### Community 18 - "ScanJobManager"
Cohesion: 0.14
Nodes (24): log_failure(), Collection, Path, Run parallel discovery work against one thread-safe TrackRepository., ScanJobManager, ScanJobPayload, ScanJobStatus, ScanLogEvent (+16 more)

### Community 19 - "api.ts"
Cohesion: 0.05
Nodes (63): AnalysisCoverage, AnalysisJobStatus, AnalysisModel, AnalysisPipelineRequest, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail (+55 more)

### Community 20 - "AnalysisOutput"
Cohesion: 0.05
Nodes (66): AnalysisResetResult, AnalysisWriteRepository, Protocol, _write_outputs(), AnalysisOutput, AnalysisWriteResult, EmbeddingWrite, MaestWrite (+58 more)

### Community 21 - "TrackInput"
Cohesion: 0.09
Nodes (36): BeatportSource, DiscogsSource, _first_label(), Discogs database adapter using only its documented API surface., _strings(), _track_title(), LastFmSource, Last.fm community tag adapter. (+28 more)

### Community 22 - "web_app.py"
Cohesion: 0.07
Nodes (42): _artifact_feature_summary(), _artifact_metrics_path(), CalibrateRequest, _calibration_readiness(), CollectionSaveRequest, CollectionTracksRequest, _default_promotion_feature_set(), delete_profile_artifacts() (+34 more)

### Community 23 - "test_consumers.py"
Cohesion: 0.18
Nodes (50): PredictionProgressCallback, PromotionProgressCallback, Resolve the root model and its matching root manifest., resolve_classifier_artifact_paths(), promote_profile_model(), _report_promotion_progress(), apply_model_to_lab(), create_app() (+42 more)

### Community 24 - "score_profiles.py"
Cohesion: 0.09
Nodes (60): _inline_score_profile_payload(), Any, FastAPI, register_evaluation_routes(), _score_profile_from_request(), _score_profile_from_source_profile(), _score_profile_name(), _utc_timestamp() (+52 more)

### Community 25 - "analysis_models.py"
Cohesion: 0.14
Nodes (30): _adapter_identity(), embedding_analysis_output(), _has_syncopated_rhythm(), _maest_genres(), Build the current embedding output for one production adapter., _required_adapter_text(), _runtime_parameters(), clap_embedding_output() (+22 more)

### Community 26 - "db_migration.py"
Cohesion: 0.15
Nodes (43): _attached_row_count(), _attached_table_exists(), _backup_sqlite(), _build_staged_library(), _cleanup_companions(), _cleanup_sqlite(), _create_backup_directory(), _foreign_key_violation_count() (+35 more)

### Community 27 - "evaluation/ablation.py"
Cohesion: 0.10
Nodes (49): _ablated_signal(), _build_session_variants(), build_source_ablation_report(), _candidate_contributions_from_source_ranks(), _candidate_event(), _candidate_pool_sessions(), CandidateEvent, CandidatePoolSession (+41 more)

### Community 28 - "TrackMetadataDialog.tsx"
Cohesion: 0.06
Nodes (54): SonaraCore, formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureGroup (+46 more)

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
Cohesion: 0.09
Nodes (48): FormPost, JsonGet, Request, authorize_lastfm(), Explicit documented authorization flows for sources that support them., Open Last.fm consent and exchange its one-time token for a session key., _access_token(), _auth_values() (+40 more)

### Community 33 - "source_profile.py"
Cohesion: 0.16
Nodes (38): build_source_profile(), _clean_profile_request(), _clean_sources(), _clean_top_k_values(), _consensus_report(), _coverage_fallback_factors(), _effective_sources(), _int_value() (+30 more)

### Community 34 - "tags.py"
Cohesion: 0.13
Nodes (24): GenreTagCandidate, _apply_genre_tag_to_candidate(), apply_genre_tags_to_tracks(), _clean_genre_label(), genre_tag_apply_summary(), _genre_tags_for_candidate(), GenreTagApplyResult, GenreTagError (+16 more)

### Community 35 - "test_audio_dedup.py"
Cohesion: 0.18
Nodes (40): _create_library_db(), _create_rhythm_lab_db(), _current_embedding_fixture(), _identity_tuple(), _insert_track(), _load_dedup_module(), CaptureFixture, MonkeyPatch (+32 more)

### Community 36 - "current_embedding_analysis_output"
Cohesion: 0.12
Nodes (20): current_embedding_analysis_output(), Build current adapter identity without loading model weights., ClapEmbeddingAdapter, MaestEmbeddingAdapter, MertEmbeddingAdapter, MuqEmbeddingAdapter, MuqMulanEmbeddingAdapter, Verify model assets and construct the configured loader. (+12 more)

### Community 37 - "test_repair_audio_metadata.py"
Cohesion: 0.12
Nodes (45): _aiff_chunk(), _load_repair_module(), _minimal_aiff_with_empty_id3_chunks(), _minimal_pcm_wave(), Path, _riff_chunk(), test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload(), test_apply_forces_single_worker() (+37 more)

### Community 38 - "candidates.py"
Cohesion: 0.13
Nodes (26): _analysis_target(), _blind_candidate_rows(), _CandidateAccumulator, CandidateExportRequest, CandidateExportResult, _clean_sources(), _collect_candidates_for_seed(), export_candidate_pools() (+18 more)

### Community 39 - "DecodedAudio"
Cohesion: 0.15
Nodes (13): DecodedAudio, _array_output_to_numpy(), _average_l2_window_embeddings(), _normalize_rows(), _normalized_embedding_rows(), ndarray, Verify model assets and construct the configured loader., Verify model assets and construct the configured loader. (+5 more)

### Community 40 - "SonaraSimilaritySearch"
Cohesion: 0.22
Nodes (37): SONARA feature-mixer search over current Core data. The separate 48-dimensional…, SonaraSimilaritySearch, _add_sonara_track(), _add_track_without_sonara(), _core_row(), _feature_value(), _float_or_none(), _int_or_none() (+29 more)

### Community 41 - "TrackIdentity"
Cohesion: 0.13
Nodes (37): SonaraFeatureRow, _optional_number(), _optional_text(), CsvRow, _optional_number(), _optional_text(), CsvRow, TrackSummary (+29 more)

### Community 42 - "test_evaluation_seed_sampling.py"
Cohesion: 0.31
Nodes (18): _ml_outputs(), ndarray, Path, TrackIdentity, _save_complete_analysis(), _save_ml_embeddings(), _save_sonara_core(), _seed_sample_library() (+10 more)

### Community 43 - "ffmpeg_runtime.py"
Cohesion: 0.18
Nodes (21): AudioRuntimeInfo, configure_shared_ffmpeg_runtime(), _configured_or_path_shared_directory(), _contains_any_ffmpeg_library(), _ffmpeg_release_version(), inspect_audio_runtime(), load_project_pyav(), _missing_runtime_message() (+13 more)

### Community 44 - "EvaluationRepository"
Cohesion: 0.10
Nodes (28): _embedding_output(), EvaluationRepository, _identity(), identity_payload(), profile(), AnalysisCoverage, Any, TrackIdentity (+20 more)

### Community 45 - "classifier_manifest.py"
Cohesion: 0.13
Nodes (28): classifier_manifest_api_fields(), ClassifierArtifactPaths, ClassifierManifestSummary, _clean_classifier_key(), _feature_sources(), _invalid_manifest(), load_classifier_manifest_summary(), _manifest_error_text() (+20 more)

### Community 46 - "_Repository"
Cohesion: 0.12
Nodes (21): _Repository, AnalysisCoverage, _expanded_vector(), _identity(), _identity_payload(), AnalysisCoverage, ndarray, parametrize (+13 more)

### Community 47 - "transition_diagnostics.py"
Cohesion: 0.12
Nodes (45): camelot_compatibility(), canonical_camelot(), key_name_to_camelot(), _parse_camelot(), _wrap_camelot(), _best_relative_tempo_delta(), _bpm_risk(), _clamp() (+37 more)

### Community 48 - "current_embedding_spec"
Cohesion: 0.11
Nodes (31): current_embedding_spec(), _search_source(), _apply_epsilon(), _contrast_score_breakdown(), _contrast_vector_scores(), _finite_number(), _matrix(), _merge_targets() (+23 more)

### Community 49 - "test_multi_model_analysis_jobs.py"
Cohesion: 0.19
Nodes (13): _candidate(), _maest_output(), _mert_output(), Exception, Path, _Repository, _Runner, test_direct_sonara_uses_configured_batches_while_staged_uses_one_queue() (+5 more)

### Community 50 - "calibration.py"
Cohesion: 0.13
Nodes (40): _average_score(), _binary_label(), brier_score(), build_calibration_report(), _calibration_report(), _calibration_samples(), _calibration_status(), CalibrationSample (+32 more)

### Community 51 - "audio_loader.py"
Cohesion: 0.16
Nodes (24): ml, load_audio_mono_with_ffmpeg(), load_decoded_audio(), load_decoded_audio_with_ffmpeg(), _load_with_shared_ffmpeg(), _load_with_torchcodec(), ndarray, Path (+16 more)

### Community 52 - "EvaluationRepository"
Cohesion: 0.14
Nodes (24): _canonical_json_value(), _clean_tags(), EvaluationRepository, _finite_float(), _json_load(), _json_object(), _json_text(), _load_track_snapshots() (+16 more)

### Community 53 - "AnalysisJobManager"
Cohesion: 0.06
Nodes (43): AnalysisJobStatus, Item, RunnerFactory, AnalysisJobConfig, AnalysisJobStatus, AnalysisLogEvent, AnalysisModelProgress, AnalysisTrackError (+35 more)

### Community 54 - "analyze_and_store_sonara_batch"
Cohesion: 0.07
Nodes (33): analysis_outputs_for_sonara_runtime(), analyze_and_store_sonara_batch(), Return the current SONARA Core, embedding, and fingerprint outputs., Analyze one native batch and persist successful results in input order.…, SonaraBatchTrackResult, BoundarySonara, _candidate(), FakeSonara (+25 more)

### Community 55 - "SearchPlaylistPanel.tsx"
Cohesion: 0.08
Nodes (35): EmbeddingSource, PromotedClassifier, ClapPromptPreset, ClapSearchTab(), classifierIsAvailable(), classifierProfileStatus(), classifierScoringBlockedReason(), filterAvailableClassifierValues() (+27 more)

### Community 56 - "benchmark_search.py"
Cohesion: 0.17
Nodes (30): _active_embedding_output(), _benchmark_database_path(), _benchmark_track_count(), BenchmarkConfig, _camelot_key(), _conflicting_kept_database_path(), _environment_summary(), _insert_synthetic_tracks() (+22 more)

### Community 57 - "AnalysisBatchItem"
Cohesion: 0.09
Nodes (17): ArrayLike, AnalysisBatchItem, _decoded_items(), _l2_normalize(), MaestModelRunner, _merge_write_results(), Any, Exception (+9 more)

### Community 58 - "test_analysis_orchestration.py"
Cohesion: 0.07
Nodes (32): default_model_runners(), EmbeddingModelRunner, _candidate(), _clap_output(), _decoded(), _EmbeddingWriteRepository, _FakeMertAdapter, _FakeMulanAdapter (+24 more)

### Community 59 - "rhythm_lab/ablation.py"
Cohesion: 0.19
Nodes (22): benchmark_profile_ablation(), cli_summary(), _compact_row(), _default_output_path(), _elapsed_seconds(), _metrics_summary(), _normalize_feature_sets(), _optional_float() (+14 more)

### Community 60 - "classifier_production.py"
Cohesion: 0.13
Nodes (32): build_classifier_calibration_report(), _calibration_report_status(), _candidate_feedback_aggregates(), _classifier_feedback_summary(), _classifier_score_detail(), ClassifierScoreRow, _clean_classifier_key(), _count_values() (+24 more)

### Community 61 - "ClassifierSpecification"
Cohesion: 0.31
Nodes (9): ClassifierSpecification, _assemble_summaries(), _base_select_fields(), _classifier_specifications_by_key(), TrackIdentity, TrackSummary, _query_base_rows(), Hydrate a strict selection in caller order. Unknown or unavailable IDs fail… (+1 more)

### Community 62 - "jobUi.tsx"
Cohesion: 0.12
Nodes (20): ActivityEvent, analysisJobRequest(), AnalysisProcessStatus(), analysisRuntimeLabel(), cancelAnalysisJob(), GenreTagProcessStatus(), isPerClassifierAnalysisEvent(), ProgressItem (+12 more)

### Community 63 - "rhythm_lab_launcher.py"
Cohesion: 0.16
Nodes (34): _clear_pid(), _file_size(), _is_rhythm_lab_process(), launch_rhythm_lab(), _listener_process_id(), _log_path(), _managed_process_id(), _mirror_log_to_console() (+26 more)

### Community 64 - "rhythm_lab/cli.py"
Cohesion: 0.14
Nodes (33): _add_data_options(), _artifact_calibration_payload(), _artifact_matches_calibration_filter(), _benchmark_ablation(), build_parser(), _calibration_report(), _collection_list(), _collection_save() (+25 more)

### Community 65 - "useLibraryState.ts"
Cohesion: 0.11
Nodes (39): Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts, libraryTrackIdentityKey() (+31 more)

### Community 66 - "escapeHtml"
Cohesion: 0.10
Nodes (38): actionIcon(), canPromoteArtifact(), coverageBadge(), escapeHtml(), formatFeatureGroupWeights(), formatHumanDate(), formatLabelCounts(), formatMetricDelta() (+30 more)

### Community 67 - "App.tsx"
Cohesion: 0.04
Nodes (62): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, defaultNotice, DeviceMode (+54 more)

### Community 68 - "score_profile_optimizer.py"
Cohesion: 0.11
Nodes (55): _accepted_decision(), _assert_normalized_weights(), _base_report(), _bootstrap_stability(), build_saved_score_profile_payload(), build_score_profile_optimizer_report(), _candidate_tie_break(), _clean_k_values() (+47 more)

### Community 69 - "test_embedding.py"
Cohesion: 0.05
Nodes (33): adapter_factories(), BatchMaestAdapter, FakeClapAudioModel, FakeMertModel, FakeMertProcessor, FakeMulanModel, FakeMuqAudioModel, parametrize (+25 more)

### Community 70 - "labels.py"
Cohesion: 0.22
Nodes (22): _json_object(), _load_csv_labels(), _load_jsonl_labels(), load_pair_feedback_labels(), load_transition_feedback_labels(), _optional_text(), PairFeedbackLabel, _parse_pair_feedback_row() (+14 more)

### Community 71 - "recorded_sessions.py"
Cohesion: 0.32
Nodes (16): _contains_legacy_version_identity(), _current_session(), _event_provenance_matches(), load_current_evaluation_sessions(), _mapping_sequence(), _persisted_snapshot_matches(), _positive_int_or_none(), Any (+8 more)

### Community 72 - "frontend/package.json"
Cohesion: 0.07
Nodes (29): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+21 more)

### Community 73 - "DatabaseValidator"
Cohesion: 0.20
Nodes (15): DatabaseValidationReport, DatabaseValidator, Connection, Path, Row, Stream current persisted rows without changing the library database., ValidationFinding, Path (+7 more)

### Community 74 - "EmbeddingTrackIdentity"
Cohesion: 0.19
Nodes (20): Explicit, read-only validation of persisted library data., current_track_identity(), EmbeddingTrackIdentity, _is_l2_unit_vector(), _positive_int(), Connection, ndarray, Row (+12 more)

### Community 75 - "test_classifier_scoring.py"
Cohesion: 0.21
Nodes (28): _artifact_hash(), _insert_track(), _install_fake_joblib(), _manifest_payload(), _mert_output(), _muq_output(), _ProbabilityModel, Exception (+20 more)

### Community 76 - "test_api_reference_compare.py"
Cohesion: 0.31
Nodes (16): _client(), _embedding(), _embedding_outputs(), _identity_payload(), _maest_analysis_output(), parametrize, Path, TestClient (+8 more)

### Community 77 - "reference_compare.py"
Cohesion: 0.12
Nodes (32): FastAPI, register_reference_compare_routes(), ReferenceCompareRequest, ReferenceCompareVerdictRequest, build_reference_compare(), _embedding_group(), _feedback_source(), _hydrate_results() (+24 more)

### Community 78 - "sonara_storage.py"
Cohesion: 0.12
Nodes (31): FingerprintOutput, One versioned SONARA acoustic fingerprint in native base64 form., Current single-library database DDL and typed Python domain models. This module…, SONARA Core row from the ``sonara_features`` table. The three timbre BLOBs are…, SonaraRow, _beat_count(), _bpm_candidates_json(), _candidate_sequence() (+23 more)

### Community 79 - "SourceTrack"
Cohesion: 0.16
Nodes (25): build_feature_matrix(), build_labeled_feature_matrix(), build_labeled_feature_matrix_from_sources(), _cached_embedding_vectors(), _feature_names(), FeatureMatrix, _finite_float(), _parse_feature_names() (+17 more)

### Community 80 - "tempo_resolution.py"
Cohesion: 0.14
Nodes (33): best_tempo_distance(), _candidate_bpms(), _clamp01(), confidence_aware_target_score(), confidence_aware_tempo_risk(), confidence_aware_tempo_score(), _finite_float(), measured_tempo_score() (+25 more)

### Community 81 - "audio_doctor/core.py"
Cohesion: 0.13
Nodes (29): escaped_codepoint(), is_xml_character(), load_state(), new_state(), normalize_state_sources(), _problems_sheet_rows(), resolve_state_path(), _results_sheet_rows() (+21 more)

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
Cohesion: 0.11
Nodes (19): configure_stdio(), main(), normalize_reason_filter(), parse_args(), Namespace, RunReporter, should_use_color(), state_entry_current() (+11 more)

### Community 86 - "Path"
Cohesion: 0.17
Nodes (21): add_path(), apply_repaired_file(), collect_paths(), delete_backup(), detect_format_from_header(), FileInspectionResult, full_decode_error(), inspect_file() (+13 more)

### Community 87 - "RepairError"
Cohesion: 0.13
Nodes (33): aiff_sound_payload(), aiff_sound_payload_hash(), aligned_pcm_data_payload_hash(), ByteRepairResult, create_backup(), data_payload(), data_payload_hash(), dedupe() (+25 more)

### Community 88 - "ReferenceComparePanel.tsx"
Cohesion: 0.13
Nodes (26): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareVerdict, TrackIdentity, normalizeLimit(), orderedReferenceCompareGroups(), ReferenceCompareGroupCard(), referenceCompareModels (+18 more)

### Community 89 - "test_rhythm_lab.py"
Cohesion: 0.05
Nodes (73): SimpleNamespace, feature_recipe_readiness(), feature_sources(), _feature_state_payload(), Describe readiness strictly for the selected feature recipe., _predict_probabilities(), ndarray, Current-generation availability for one classifier feature source. (+65 more)

### Community 90 - "logging_config.py"
Cohesion: 0.08
Nodes (44): AbstractEventLoop, ConnectionResetError, Handler, Logger, _archive_active_log_path(), configure_logging(), _connection_reset_code(), _current_date_suffix() (+36 more)

### Community 91 - "isMulticlassProfile"
Cohesion: 0.33
Nodes (9): assignedLabelStatus(), displayLabel(), isMulticlassProfile(), labelByKey(), nextStepText(), profileSignalText(), renderProfileControls(), trackStatusLine() (+1 more)

### Community 92 - "load_tracks"
Cohesion: 0.16
Nodes (23): Standalone online track-metadata enrichment tool., _load_audio_file(), _load_csv(), _load_directory(), _load_m3u(), load_tracks(), _load_xlsx(), Path (+15 more)

### Community 93 - "report.py"
Cohesion: 0.16
Nodes (17): build_report_contract(), _clean(), _column(), _join(), _maest(), Path, Source-preserving intermediate report contract., Build one flat, source-preserving data row per track. (+9 more)

### Community 94 - "seed_sampling.py"
Cohesion: 0.14
Nodes (28): _weighted_candidate_seed_track_ids(), _analysis_flag(), _bpm_bucket(), _bucket_for_values(), _buckets_used(), _clean_required_sources(), _energy_bucket(), export_seed_sample() (+20 more)

### Community 95 - "test_sonara_storage.py"
Cohesion: 0.19
Nodes (24): _analysis(), _candidate(), _prepare(), float32, MonkeyPatch, ndarray, parametrize, Path (+16 more)

### Community 97 - "audio_dedup/core.py"
Cohesion: 0.16
Nodes (24): _bool_text(), _candidates_sheet_rows(), _evidence_by_candidate(), _groups_sheet_rows(), _pair_evidence_sheet_rows(), rhythm_lab_cli_summary(), _rhythm_lab_sheet_rows(), rhythm_lab_summary() (+16 more)

### Community 98 - "embedding.py"
Cohesion: 0.15
Nodes (16): _average_maest_embeddings(), _maest_embedding_rows(), _maest_float_list(), _maest_score_rows(), _masked_time_mean(), _pad_or_trim_audio_tensor(), _prepare_muq_compatible_windows(), Tensor (+8 more)

### Community 99 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+14 more)

### Community 100 - "DatabaseValidationJobManager"
Cohesion: 0.16
Nodes (12): format_validation_finding(), DatabaseValidationEvent, DatabaseValidationJobManager, DatabaseValidationJobStatus, Single-threaded lifecycle for explicit database validation., Return the short human-facing form used by the UI, API job and CLI., Path, test_validation_job_api_exposes_completed_job_and_its_ui_events() (+4 more)

### Community 101 - "create_app"
Cohesion: 0.09
Nodes (35): create_app(), open_database_file_dialog(), open_folder_dialog(), FastAPI, Path, Open Windows Explorer with the supplied audio file selected., reveal_track_file(), FastAPI (+27 more)

### Community 102 - "AnalysisPipelineManager"
Cohesion: 0.29
Nodes (4): AnalysisPipelineManager, AnalysisPipelineStatus, _PipelinePayload, PipelineStageStatus

### Community 103 - "AppDatabaseState"
Cohesion: 0.14
Nodes (10): FastAPI, Path, register_database_routes(), DatabaseStateResponse, DatabaseSwitchRequest, AppDatabaseState, Path, Return the selected database only when no background job is active. (+2 more)

### Community 104 - "select_torch_device"
Cohesion: 0.13
Nodes (13): Any, select_torch_device(), load_score_prompt_bank_module(), Path, test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(), test_checkpoint_loading_forces_weights_only(), test_clap_model_load_stdout_and_stderr_are_written_to_app_log(), test_clap_text_embedding_preflights_pinned_verified_checkpoint_once() (+5 more)

### Community 105 - "AnalysisTarget"
Cohesion: 0.13
Nodes (27): AnalysisTarget, _candidates_without_seed(), HnswPersistentIndexSearcher, PersistentIndexSearcher, ndarray, _vector_content_hash(), _target_for_hit(), _hnsw_hits() (+19 more)

### Community 106 - "VerifiedAssetBinding"
Cohesion: 0.20
Nodes (14): BaseException, bind_verified_file(), bind_verified_snapshot(), _close_guard(), _copy_verified(), _open_read_only_guard(), _open_windows_read_only_guard(), Path (+6 more)

### Community 107 - "main"
Cohesion: 0.13
Nodes (14): apply_duplicate_deletions(), apply_result_payload(), ApplyResult, _candidate_track_id(), configure_stdio(), confirm_apply(), ConsoleProgressReporter, main() (+6 more)

### Community 108 - "PresetConfig"
Cohesion: 0.15
Nodes (22): _bits_to_int(), _candidate_duration_compatible(), _candidate_pair_ids(), _candidate_reason_lines(), _candidate_safety(), _connected_components(), _content_similarity(), _duration_distance() (+14 more)

### Community 109 - "loadActive"
Cohesion: 0.14
Nodes (28): addOption(), applySourceState(), chooseSource(), clearActiveProfile(), collectNewProfileLabels(), createProfile(), deleteActiveProfile(), deleteSelectedCollection() (+20 more)

### Community 110 - "wave_tags.py"
Cohesion: 0.17
Nodes (14): Frame, _AudioWithId3Tags, _genre_frame_text(), _Id3Tags, Path, Protocol, _replace_id3_genre(), _require_readable_wave_audio() (+6 more)

### Community 111 - "artifact_io.py"
Cohesion: 0.18
Nodes (22): PublicationProgressCallback, artifact_sha256(), ArtifactIntegrityError, _AvailableOutputRepository, _default_metadata_path(), _fsync_directory(), load_verified_artifact(), publish_promoted_artifact() (+14 more)

### Community 112 - "sonara_features.py"
Cohesion: 0.08
Nodes (44): LogCaptureFixture, ProcessPoolExecutor, _analysis_mapping(), _analysis_mapping_with_ffmpeg_fallback(), _import_sonara(), Any, Native SONARA batch orchestration for the analysis repository., Current unversioned SONARA analysis selection and value constants. (+36 more)

### Community 113 - "test_benchmark_search.py"
Cohesion: 0.35
Nodes (10): CompletedProcess, parametrize, Path, _run_benchmark(), _run_benchmark_raw(), test_benchmark_search_keep_db_preserves_current_bundle(), test_benchmark_search_rejects_invalid_vector_backend(), test_benchmark_search_rejects_output_that_overlaps_keep_db() (+2 more)

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
Cohesion: 0.36
Nodes (19): build_weighted_candidate_pool(), WeightedCandidatePoolResult, _candidate_row(), EvaluationRepository, MonkeyPatch, _score_profile(), _sonara_with_energy(), _summary_with_tags() (+11 more)

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

### Community 128 - "AnalysisVectorRow"
Cohesion: 0.09
Nodes (22): AnalysisVectorRow, PersistentAnnVectorSearchBackend, Strict persistent HNSW search over one current embedding output. The backend…, AnalysisSearchRepository, Protocol, Public repository surface required by embedding search., fake_hnsw(), FakeAnalysisRepository (+14 more)

### Community 129 - "loadTrainingReadiness"
Cohesion: 0.39
Nodes (18): calibrateClassifier(), fileName(), handleTrainingActionClick(), loadTrainingReadiness(), parseRefreshResponse(), pollTrainingProgress(), promoteClassifier(), refreshCandidates() (+10 more)

### Community 130 - "run_report"
Cohesion: 0.24
Nodes (18): CancelCheck, ProgressCallback, _attach_embeddings(), AudioDedupCancelled, _connect_readonly(), count_database_tracks(), find_duplicate_groups(), load_tracks() (+10 more)

### Community 131 - "Personal Classifier Workflow"
Cohesion: 0.17
Nodes (17): Feature Ablation Benchmark, Calibration Data Gate, Database-Only Classifier Scoring, Immutable Generation Promotion, Ordered Classifier Feature Recipe, Personal Classifier Workflow, Reusable Ranking Signal, Not Truth, Rhythm Lab Isolated State (+9 more)

### Community 132 - "test_vector_index.py"
Cohesion: 0.19
Nodes (20): create_vector_backend(), ExactVectorSearchBackend, Create one explicitly named backend; legacy aliases are not accepted., Deterministic exact cosine search over validated unit vectors., _add_track(), _mert_output(), _mert_unit_vector(), MonkeyPatch (+12 more)

### Community 134 - "qa_database.py"
Cohesion: 0.23
Nodes (16): _build_parser(), _fail(), _foreign_key_check(), _integrity_check(), main(), _open_read_only(), ArgumentParser, Connection (+8 more)

### Community 135 - "read_local_evidence"
Cohesion: 0.22
Nodes (14): _find_by_metadata(), _find_by_path(), Connection, Path, Row, Return tags and at most three MAEST genres from one unambiguous local track., read_local_evidence(), Path (+6 more)

### Community 136 - "judged.py"
Cohesion: 0.32
Nodes (15): build_judged_label_gate(), _first_label_for_any_source(), judged_label_guidance(), judged_label_status(), _labels_by_rating(), matched_judged_labels(), MatchedJudgedLabel, matching_label() (+7 more)

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
Cohesion: 0.19
Nodes (17): classifier_artifact_slug(), default_classifier_model_path(), load_classifier_requirements(), Validate the classifier recipe, required inputs, and artifact. This function is…, _require_available_outputs(), _FixedProbabilityModel, _insert_track(), _mert_output() (+9 more)

### Community 141 - "models.py"
Cohesion: 0.15
Nodes (23): _artists(), _label(), Beatport v4 Catalog Search adapter using documented bearer authentication., _record(), _text(), _year(), Read local genre evidence without modifying a library database., _normalized() (+15 more)

### Community 142 - "Classifier Workflow"
Cohesion: 0.22
Nodes (13): Benchmark Variants, Broken vs Straight Beat Classifier, Classifier Workflow, Collect Labels, Local Music Library, Music Attribute Classifiers, Personal Music Classifiers, Production Readiness (+5 more)

### Community 143 - "test_evaluation_score_profile_optimizer.py"
Cohesion: 0.25
Nodes (18): _add_two_candidate_session(), _build_bad_rate_increase_library(), _build_empty_seed_shell(), _build_two_candidate_optimizer_library(), _candidate_event(), _optimizer_example_for_missing_source_test(), EvaluationRepository, test_optimizer_does_not_write_database_rows_by_default() (+10 more)

### Community 144 - "SimilaritySearch"
Cohesion: 0.39
Nodes (16): Cosine search over one current ML embedding family., SimilaritySearch, _add_track(), _library(), _output(), ndarray, Path, _query() (+8 more)

### Community 145 - "trackMarkup"
Cohesion: 0.13
Nodes (18): badgeRow(), displayTrackTitle(), featuresIndicator(), featuresReady(), featureStateReason(), featureStateStatus(), formatMaestGenreLabel(), genreBadges() (+10 more)

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

### Community 151 - "scanner.py"
Cohesion: 0.12
Nodes (37): Background and synchronous jobs for the sole scan repository path., _audio_format(), _audio_format_from_mime(), _contains_tag(), file_tags_from_metadata(), _genres(), iter_audio_files(), _positive_float_or_none() (+29 more)

### Community 152 - "AnalysisStageQueue"
Cohesion: 0.17
Nodes (11): AnalysisStageQueue, One in-memory worker shared by SONARA, ML, and classifier stages., FakeJobs, test_parent_cancel_before_start_removes_pending_stages(), test_parent_cancel_propagates_to_current_child_and_cancels_pending_stages(), test_pipeline_forwards_staged_ml_configuration_to_child_job(), test_pipeline_forwards_staged_sonara_configuration_to_child_job(), test_pipeline_stops_after_fatal_stage_failure() (+3 more)

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

### Community 158 - "TrackPathRecord"
Cohesion: 0.24
Nodes (10): collect_db_paths(), collect_repository_paths(), paths_from_track_records(), Protocol, Resolve typed repository paths and count files absent on disk., Map canonical ``TrackPath.file_path`` values to local audio paths., Typed repository projection used for database-backed path collection., remap_db_track_path() (+2 more)

### Community 159 - "Normalized Prompt Ensemble"
Cohesion: 0.25
Nodes (9): Prompt Calibration Workflow, Hard-Negative Margin Scoring, Normalized Prompt Ensemble, CLAP Prompt Families, Text as Audible Shared-Embedding Anchor, Project CLAP Profiles, Positive Ensemble and Hard-Negative Contrast Scoring, Compact English CLAP Prompt Bank (+1 more)

### Community 160 - "validate_prompt_bank.py"
Cohesion: 0.39
Nodes (8): fail(), load_json(), main(), Any, Path, tokenish_count(), validate_bank(), warn()

### Community 161 - "dj_track_similarity/__init__.py"
Cohesion: 0.21
Nodes (11): ModuleType, Local dj-track-similarity toolkit., _library_with_maest_candidate(), _make_tagged_wave(), Path, test_genre_tag_apply_rejects_cross_catalog_candidate_before_source_write(), test_genre_tag_apply_rejects_stale_files_before_source_write(), test_genre_tag_apply_requires_readback_before_recording_self_write() (+3 more)

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

### Community 172 - "Codebase Documentation Writer"
Cohesion: 0.29
Nodes (7): Documentation Writer Agent Interface, Codebase Documentation Writer, Documentation Verification Workflow, Maintained Documentation Surface, Source-Grounded Documentation, VitePress Documentation Information Architecture, VitePress Documentation Pointer

### Community 173 - "api_routes_analysis.py"
Cohesion: 0.23
Nodes (15): AnalysisResetResult, _classifier_info_by_key(), _classifier_manifest_error_text(), _outputs_for_family(), FastAPI, register_analysis_routes(), _require_known_classifier(), _require_scoring_compatible_classifier() (+7 more)

### Community 175 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 176 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.29
Nodes (4): appSource, panelSource, styles, trackPanelSource

### Community 178 - "Local-First DJ Library Workbench"
Cohesion: 0.29
Nodes (7): Browser-Local Current Set, Listening-Led Ranking Signals, Local-First DJ Library Workbench, Russian Project Limitations, Russian Local-First Workbench Description, DJ Set Dramaturgy, Three-Layer Set Compatibility Model

### Community 179 - "loadCandidates"
Cohesion: 0.22
Nodes (17): submitPageInput(), bpmFilterValue(), currentPage(), jumpToPage(), loadCandidates(), loadCollectionTracks(), loadLikedTracks(), loadSettingsView() (+9 more)

### Community 180 - "test_api_rhythm_lab.py"
Cohesion: 0.20
Nodes (17): _add_track(), _identity_payload(), Path, TrackIdentity, test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(), test_rhythm_lab_collection_save_rejects_legacy_numeric_only_body(), test_rhythm_lab_default_log_path_uses_logs_directory(), test_rhythm_lab_default_pid_path_uses_database_directory() (+9 more)

### Community 181 - "test_api_analysis_jobs.py"
Cohesion: 0.26
Nodes (25): _analysis_start(), _client(), MonkeyPatch, parametrize, Path, TestClient, test_api_defaults_audio_job_to_ml_models_only(), test_api_does_not_register_bulk_classifier_analysis() (+17 more)

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
Cohesion: 0.26
Nodes (10): MaestAnalysisRow, Explicitly repair MAEST syncopated-rhythm flags from stored genres., parse_maest_genres_json(), Canonical semantic validation for persisted MAEST analysis rows., Validate one complete MAEST analysis row against writer semantics., Parse canonical MAEST genre JSON without silently dropping entries., _required_int(), _required_text() (+2 more)

### Community 189 - "config.mts"
Cohesion: 0.40
Nodes (4): commonTheme, englishNav, englishSidebar, SidebarSection

### Community 190 - "test_analysis_sonara_preflight.py"
Cohesion: 0.20
Nodes (12): _candidate(), _client(), _CoverageRepository, _PreflightTrapAnalysisJobs, MonkeyPatch, Path, TestClient, test_pipeline_job_creation_does_not_run_release_preflight() (+4 more)

### Community 192 - "_coverage_and_classifiers"
Cohesion: 0.23
Nodes (15): _coverage_and_classifiers(), _current_analysis_row_count(), _current_artifact_row_count(), _current_classifier_details(), _identity_map(), _json_identity_rows(), _json_ids(), AnalysisCoverage (+7 more)

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

### Community 224 - "test_api_runtime.py"
Cohesion: 0.29
Nodes (15): DatabaseBusy, RuntimeError, _client(), Path, TestClient, test_classifier_preflight_conflict_returns_http_409_before_start(), test_database_switch_bootstraps_clean_selected_current_bundle(), test_exclusive_database_operation_blocks_new_jobs() (+7 more)

### Community 225 - ".get_track_detail"
Cohesion: 0.33
Nodes (10): SonaraCore, _file_tags(), _optional_float(), _optional_int(), _optional_text(), FileTags, Row, TrackDetail (+2 more)

### Community 226 - "Q: как реализована передача аудио в MULAN"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: как реализована передача аудио в MULAN, Source Nodes

### Community 227 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 228 - "_move_maest_runtime_modules"
Cohesion: 0.28
Nodes (4): _move_maest_runtime_modules(), FakeMaestModel, MovableModule, test_maest_initializes_only_missing_melspectrogram()

### Community 229 - "Q: Проанализируй реализацию извлечения эмбов в MULam в проекте"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Проанализируй реализацию извлечения эмбов в MULam в проекте, Source Nodes

### Community 230 - "Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Изучи реализацию передачи аудиоданных в ML модели проекта. Как сейчас это реализовано? Ибо будем менять на torchocodec 16.0 CUDA, Source Nodes

### Community 231 - "dj_track_similarity/cli.py"
Cohesion: 0.10
Nodes (60): command, parse_analysis_models_text(), analyze(), analyze_classifier(), analyze_pipeline(), classifier_calibration_report(), classifier_suggest_labels(), _db() (+52 more)

### Community 232 - "create_library_schema"
Cohesion: 0.33
Nodes (11): _apply_schema(), create_library_schema(), Connection, Create the current single-library schema in *db*. Args: db: An open…, _create_legacy_artifacts(), _create_legacy_core(), _create_legacy_pair(), Path (+3 more)

### Community 233 - "media_preview.py"
Cohesion: 0.33
Nodes (9): FileResponse, AudioPreviewError, _delete_temp_file(), _is_browser_safe_wav(), Path, RuntimeError, Raised when an audio preview response cannot be prepared., requires_browser_preview_transcode() (+1 more)

### Community 234 - "classifier_scoring.py"
Cohesion: 0.10
Nodes (30): ClassifierFeatureRow, ClassifierScoreWrite, analyze_classifier(), _argmax_with_tiebreak(), _classifier_key_from_metadata_or_slug(), ClassifierScorer, default_classifier_models_root(), _load_payload() (+22 more)

### Community 235 - "scanImportDialog.test.mjs"
Cohesion: 0.40
Nodes (4): appPath, dialogPath, panelPath, srcDir

### Community 236 - "._device"
Cohesion: 0.15
Nodes (14): _construct_clap_module_with_pinned_text_model(), _download_verified_hf_checkpoint(), _download_verified_hf_snapshot(), _ensure_verified_maest_checkpoint(), _local_only_from_pretrained_proxy(), Path, Populate and verify the torch-hub cache before maest-infer loads it., Resolve and privately bind one exact Hub file for deserialization. (+6 more)

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

### Community 252 - "sonara_core_validation.py"
Cohesion: 0.21
Nodes (22): SonaraCoreRow, _exact_object(), _json_array(), _optional_int(), _optional_number(), _optional_text(), Canonical semantic validation for persisted SONARA Core rows., Validate one complete SONARA Core row against writer semantics. (+14 more)

### Community 253 - "rhythm_lab_collections.py"
Cohesion: 0.09
Nodes (41): _collection_from_row(), _collection_tracks(), _configure_collection_connection(), ensure_review_collection_schema(), _immutable_read_only_connection(), _insert_collection_tracks(), _nonempty_path(), _positive_int() (+33 more)

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

### Community 272 - "api_routes_tags_export.py"
Cohesion: 0.48
Nodes (6): FastAPI, Path, register_tags_export_routes(), ExportRequest, GenreTagApplyResultResponse, GenreTagRequest

### Community 274 - "Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе."
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Сейчас есть проблема, если вызывавать одно  и тоже количество тпреков с одними и теми же фильтрами из одной папки. Все файлы будут пропущены и не учтены, что уже есть в базе., Source Nodes

### Community 275 - "Q: Почему данные в базу не пишутся?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Почему данные в базу не пишутся?, Source Nodes

### Community 276 - "_add_track"
Cohesion: 0.62
Nodes (6): _add_track(), Path, test_classifier_score_counts_use_keys_and_count_rows_only(), test_public_library_filter_combines_search_and_liked_state(), test_public_library_filter_rejects_unknown_search_mode(), test_public_library_order_is_deterministic_by_artist_title_and_path()

### Community 277 - "Q: где проблема"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: где проблема, Source Nodes

### Community 278 - "_parse_source_contribution"
Cohesion: 0.33
Nodes (7): _optional_finite_float(), _optional_positive_int(), _parse_source_contribution(), _source_contributions(), _source_payload(), SourceContribution, _transition_risk()

### Community 279 - "runtime.py"
Cohesion: 0.52
Nodes (6): doctor(), _detect_nvidia_smi_cuda(), get_torch_runtime_info(), _parse_cuda_version(), recommended_torch_index(), TorchRuntimeInfo

### Community 280 - "TrainingProgress"
Cohesion: 0.22
Nodes (4): Exception, Small in-process progress registry for an active profile workflow., TrainingProgress, test_training_progress_reports_lifecycle()

### Community 281 - "test_classifier_jobs.py"
Cohesion: 0.35
Nodes (10): _insert_present_classifier_inputs(), _insert_track(), _mert_output(), MonkeyPatch, Path, Create more persisted classifier inputs than one job batch holds., _requirements(), _score_count() (+2 more)

### Community 282 - "api_routes_rhythm_lab.py"
Cohesion: 0.13
Nodes (17): RhythmLabSourceBinding, BaseModel, FastAPI, model_validator, register_rhythm_lab_routes(), RhythmLabCollectionSaveRequest, TrackIdentityRequest, build_rhythm_lab_collection_selection_exact() (+9 more)

### Community 283 - "test_config.py"
Cohesion: 0.33
Nodes (6): CaptureFixture, Path, Prevent silently sending a credential to an unimplemented service., Prevent OAuth session material from leaking into normal CLI output., test_load_config_rejects_unknown_configured_source(), test_save_auth_data_persists_session_without_printing_secret()

### Community 284 - "test_api_evaluation.py"
Cohesion: 0.32
Nodes (14): _client(), ndarray, parametrize, Path, TestClient, test_evaluation_api_rejects_unselected_and_legacy_database(), test_evaluation_feedback_does_not_touch_audio_path(), test_evaluation_feedback_endpoints_validate_and_preserve_seed_scope() (+6 more)

### Community 285 - "_scan_track"
Cohesion: 0.52
Nodes (6): Path, TrackIdentity, _scan_track(), test_export_endpoint_writes_current_track_list_without_saving_playlist(), test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(), test_saved_playlist_endpoint_is_absent()

### Community 286 - "test_evaluation_optimizer_e2e.py"
Cohesion: 0.70
Nodes (4): _build_weighted_feedback_fixture(), _classifier_adjusted_event_count(), EvaluationRepository, test_weighted_feedback_optimizer_profile_save_e2e_fixture()

### Community 287 - "scan_library"
Cohesion: 0.13
Nodes (35): ScanStats, Scan one root through the sole TrackRepository write path., Reconcile one audio file using exact nanosecond filesystem facts. An unchanged…, scan_audio_file(), scan_library(), Aggregate result returned by the synchronous scanner., ScanStats, _library_roots() (+27 more)

### Community 288 - "LibraryQueryRepository"
Cohesion: 0.18
Nodes (8): LibrarySummary, LibraryQueryRepository, Path, Read-model mixin for the single library database., Return present tracks with current, non-empty MAEST genre scores., Library summary repository export., Composition name used by :class:`LibraryDatabase`., SummaryRepository

### Community 289 - "db_library_queries.py"
Cohesion: 0.12
Nodes (26): _base_from_sql(), _filter_sql(), _fts_query(), _json_array(), _json_object(), _json_object_sequence(), _like_pattern(), _maest_analysis() (+18 more)

### Community 290 - "test_ffmpeg_runtime.py"
Cohesion: 0.67
Nodes (5): Path, test_configure_shared_runtime_prefers_explicit_environment_over_path(), test_configure_shared_runtime_registers_path_dll_directory(), test_configure_shared_runtime_rejects_explicit_directory_without_ffmpeg_dlls(), _write_required_libraries()

### Community 291 - "_parse_args"
Cohesion: 0.60
Nodes (5): _parse_args(), _parse_track_counts(), _positive_int(), _track_count_value(), _vector_backend_name()

### Community 292 - "create_api_client"
Cohesion: 0.40
Nodes (4): create_api_client(), MonkeyPatch, Path, TestClient

### Community 294 - "storage_database_paths"
Cohesion: 0.22
Nodes (12): _prepare_kept_database_path(), _load_script(), Path, test_optimize_database_backs_up_library_and_existing_evaluation_sidecar(), test_optimize_database_does_not_reject_future_library_tables(), test_optimize_database_handles_generic_sqlite_file(), Path, Filesystem topology for the library and optional Evaluation sidecar. (+4 more)

### Community 295 - "test_qa_database_script.py"
Cohesion: 0.70
Nodes (4): _load_script(), Path, test_qa_database_allows_future_library_tables(), test_qa_database_checks_library_and_optional_evaluation()

### Community 298 - "AnalysisCandidate"
Cohesion: 0.06
Nodes (51): decode_analysis_batch(), DecodeFailure, DecodeAudio, A full-track decode error deferred to a model-specific recovery path., AnalysisCandidate, analyze_and_store_staged_ml(), cleanup_orphaned_ml_staging(), _decode_staged() (+43 more)

### Community 299 - "LibraryDatabase"
Cohesion: 0.21
Nodes (17): EmbeddingOutput, LibraryDatabase, Connection, EvaluationRepository, ndarray, TrackIdentity, Path, test_current_embedding_removes_track_from_its_analysis_candidates() (+9 more)

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
- **472 isolated node(s):** `SidebarSection`, `englishNav`, `englishSidebar`, `commonTheme`, `name` (+467 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `EmbeddingModelRunner` (9× useful, score=8.365588022)
- `MuqMulanEmbeddingAdapter` (7× useful, score=6.506444009)
- `AnalysisOutput` (7× useful, score=6.437469482)
- `MaestEmbeddingAdapter` (5× useful, score=4.657529854)
- `ClassifierScoreWrite` (5× useful, score=4.522351858)
- `ScanJobManager` (4× useful, score=3.94610219)
- `ClapEmbeddingAdapter` (4× useful, score=3.722814667)
- `MertEmbeddingAdapter` (4× useful, score=3.722814667)
- `MuqEmbeddingAdapter` (4× useful, score=3.722814667)
- `load_decoded_audio()` (4× useful, score=3.721648911)

**Known dead ends** — questions that led nowhere; don't re-derive.
- "Что значит, что docs/superpowers намеренно игнорируется репозиторием, и почему ему желательно не игнорировать staging?" -> `docsRoot`

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Recording Indicator` and `Rhythm Lab Favicon`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `LibraryDatabase` connect `LibraryDatabase` to `FileTags`, `test_api_tracks.py`, `track_views.py`, `database.py`, `test_vector_index.py`, `weighted_candidates.py`, `run_report`, `TrackPathRecord`, `api_routes_search.py`, `reports.py`, `ClassifierJobManager`, `load_classifier_requirements`, `SimilaritySearch`, `ScanJobManager`, `AnalysisOutput`, `_add_track`, `score_profiles.py`, `test_api_dialog.py`, `test_classifier_jobs.py`, `evaluation/ablation.py`, `test_api_evaluation.py`, `risk_sweep.py`, `_scan_track`, `test_evaluation_cli.py`, `LibraryQueryRepository`, `source_profile.py`, `dj_track_similarity/__init__.py`, `test_audio_dedup.py`, `test_api_sonara_search.py`, `test_repair_audio_metadata.py`, `storage_database_paths`, `test_qa_database_script.py`, `candidates.py`, `TrackIdentity`, `test_evaluation_seed_sampling.py`, `scan_library`, `SonaraSimilaritySearch`, `current_embedding_spec`, `calibration.py`, `EvaluationRepository`, `test_api_analysis_jobs.py`, `test_api_rhythm_lab.py`, `benchmark_search.py`, `test_analysis_orchestration.py`, `classifier_production.py`, `rhythm_lab/cli.py`, `score_profile_optimizer.py`, `recorded_sessions.py`, `DatabaseValidator`, `EmbeddingTrackIdentity`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `reference_compare.py`, `project_clap_search.py`, `seed_sampling.py`, `test_sonara_storage.py`, `test_api_runtime.py`, `DatabaseValidationJobManager`, `create_app`, `AnalysisPipelineManager`, `AppDatabaseState`, `dj_track_similarity/cli.py`, `classifier_scoring.py`, `main`, `tests/test_cli.py`, `build_weighted_candidate_pool`, `track_models.py`, `test_api_database_selection.py`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Why does `TrackIdentity` connect `TrackIdentity` to `FileTags`, `_required_text`, `test_api_tracks.py`, `track_views.py`, `database.py`, `test_vector_index.py`, `api_schemas.py`, `compute_transition_diagnostics`, `api_routes_rhythm_lab.py`, `rhythm_lab_impact_payload`, `_scan_track`, `test_evaluation_cli.py`, `LibraryQueryRepository`, `db_library_queries.py`, `tags.py`, `candidates.py`, `test_evaluation_seed_sampling.py`, `LibraryDatabase`, `EvaluationRepository`, `_Repository`, `transition_diagnostics.py`, `EvaluationRepository`, `test_api_rhythm_lab.py`, `recorded_sessions.py`, `reference_compare.py`, `tempo_resolution.py`, `AnalysisTarget`, `main`, `track_models.py`, `rhythm_lab_collections.py`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `AnalysisOutput` connect `AnalysisOutput` to `AnalysisVectorRow`, `test_vector_index.py`, `load_classifier_requirements`, `sonara_similarity_scoring.py`, `ann_index.py`, `SimilaritySearch`, `test_consumers.py`, `analysis_models.py`, `test_classifier_jobs.py`, `test_evaluation_cli.py`, `db_library_queries.py`, `current_embedding_analysis_output`, `test_api_sonara_search.py`, `candidates.py`, `SonaraSimilaritySearch`, `AnalysisCandidate`, `test_evaluation_seed_sampling.py`, `EvaluationRepository`, `api_routes_analysis.py`, `_Repository`, `LibraryDatabase`, `current_embedding_spec`, `test_multi_model_analysis_jobs.py`, `AnalysisJobManager`, `analyze_and_store_sonara_batch`, `benchmark_search.py`, `AnalysisBatchItem`, `test_analysis_orchestration.py`, `classifier_production.py`, `test_analysis_sonara_preflight.py`, `_coverage_and_classifiers`, `test_classifier_scoring.py`, `test_api_reference_compare.py`, `reference_compare.py`, `test_sonara_storage.py`, `.get_track_detail`, `create_app`, `AnalysisTarget`, `classifier_scoring.py`, `artifact_io.py`, `sonara_features.py`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 138 inferred relationships involving `LibraryDatabase` (e.g. with `run_source_file_search()` and `_active_embedding_output()`) actually correct?**
  _`LibraryDatabase` has 138 INFERRED edges - model-reasoned connections that need verification._
- **Are the 101 inferred relationships involving `AnalysisOutput` (e.g. with `_active_embedding_output()` and `_store_synthetic_embeddings()`) actually correct?**
  _`AnalysisOutput` has 101 INFERRED edges - model-reasoned connections that need verification._
- **Are the 91 inferred relationships involving `AnalysisTarget` (e.g. with `_store_synthetic_embeddings()` and `_candidates_without_seed()`) actually correct?**
  _`AnalysisTarget` has 91 INFERRED edges - model-reasoned connections that need verification._
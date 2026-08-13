# Graph Report - dj-track-similarity  (2026-08-13)

## Corpus Check
- 383 files · ~363,579 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 5978 nodes · 18616 edges · 254 communities (234 shown, 20 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 1813 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c78a5d95`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- dj_track_similarity/cli.py
- FileTags
- label_transfer.py
- source_db.py
- db_analysis.py
- SourceDatabase
- AnalysisCandidate
- RhythmLabDatabase
- sonara_features.py
- app.js
- classifier_scoring.py
- EmbeddingTrackIdentity
- track_models.py
- JobStore
- ann_index.py
- api_schemas.py
- Reference Index
- logging_config.py
- App.tsx
- api.ts
- reports.py
- TrackInput
- test_rhythm_lab.py
- test_consumers.py
- score_profiles.py
- db_library_queries.py
- db_migration.py
- evaluation/ablation.py
- TrackMetadataDialog.tsx
- risk_sweep.py
- Features, embeddings, and tags
- test_evaluation_cli.py
- metadata_enrichment_cli.py
- source_profile.py
- MuqEmbeddingAdapter
- SimilaritySearch
- sonara_similarity_scoring.py
- test_repair_audio_metadata.py
- test_break_energy.py
- sonara_storage.py
- rhythm_lab/ablation.py
- SonaraFeatureRow
- weighted_candidates.py
- TrackIdentity
- EvaluationRepository
- database.py
- analysis_model_runners.py
- transition_diagnostics.py
- test_audio_dedup.py
- current_embedding_spec
- calibration.py
- create_app
- EvaluationRepository
- score_profile_optimizer.py
- AnalysisJobManager
- SearchPlaylistPanel.tsx
- benchmark_search.py
- ClapEmbeddingAdapter
- SonaraSimilaritySearch
- test_analysis_orchestration.py
- classifier_production.py
- analysis_models.py
- ScanJobManager
- rhythm_lab_launcher.py
- rhythm_lab/cli.py
- useLibraryState.ts
- escapeHtml
- _Repository
- AnalysisTarget
- ScannedFile
- tempo_resolution.py
- embedding.py
- frontend/package.json
- scan_library
- compute_transition_diagnostics
- test_classifier_scoring.py
- DecodedAudio
- MaestWindowContext
- candidates.py
- seed_sampling.py
- loadActive
- audio_doctor/core.py
- training.py
- project_clap_search.py
- classifier_manifest.py
- main
- Path
- RepairError
- ReferenceComparePanel.tsx
- AnalysisVectorRow
- tags.py
- LibraryDatabase
- load_tracks
- report.py
- DatabaseValidator
- media_preview.py
- test_audio_loader.py
- audio_dedup/core.py
- storage_database_paths
- compilerOptions
- sonara_core_validation.py
- audio_loader.py
- MaestEmbeddingAdapter
- AppDatabaseState
- select_torch_device
- build_saved_score_profile_payload
- test_evaluation_seed_sampling.py
- main
- PresetConfig
- parseJsonResponse
- jobUi.tsx
- _add_track
- test_evaluation_score_profile_optimizer.py
- test_api_tracks.py
- DJ Track Similarity Banner
- ExactVectorSearchBackend
- tests/test_cli.py
- artifact_io.py
- optimize_database.py
- build_weighted_candidate_pool
- _PublicClassifierReader
- TrackRecord
- FileRepairResult
- score_prompt_bank.py
- scripts
- test_api_analysis_jobs.py
- test_api_database_selection.py
- test_api_rhythm_lab.py
- AnalysisOutput
- loadTrainingReadiness
- run_report
- Personal Classifier Workflow
- qa_database.py
- recorded_sessions.py
- test_api_sonara_search.py
- read_local_evidence
- judged.py
- test_api_reference_compare.py
- db_analysis_candidates.py
- db_search_fts.py
- test_api_runtime.py
- beatport.py
- Classifier Workflow
- test_api_evaluation.py
- wave_tags.py
- formatHumanDate
- run-vale.mjs
- Search with Seed Tracks
- Know When Audio Files Can Be Written
- tooltipLayer.tsx
- test_run_server_lan_script.py
- connect_evaluation_sidecar
- track_views.py
- test_api_dialog.py
- Audio Online
- metadataReference.test.mjs
- rhythm_lab_impact_payload
- build_report_payload
- TrackPathRecord
- Normalized Prompt Ensemble
- validate_prompt_bank.py
- Workflows
- run_server_launcher.py
- Unified SQLite Music Library
- ExportTrackRow
- workbook_bridge.mjs
- CLAP Query Workflow
- DJ Track Similarity Agent Instructions
- Russian Project Overview
- Temporary Current Set
- rank_maest_genres
- Response
- Codebase Documentation Writer
- Audio Online Metadata Workbook Layout
- buttonClasses.test.mjs
- libraryView.test.mjs
- searchPlaylistLayout.test.mjs
- themeMode.test.mjs
- Local-First DJ Library Workbench
- test_classifier_manifest.py
- test_export.py
- test_config.py
- Rhythm Lab Page
- DJ Track Similarity Project Overview
- DJ Track Similarity Dark Logo
- CLAP Text Search
- Audio-Online/tests/test_cli.py
- DJ Track Similarity
- User Guide
- config.mts
- test_qa_database_script.py
- apiContract.test.mjs
- libraryLoading.test.mjs
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
- Terminal Design Waiting State
- Empty Rejection Vocabulary
- dj-track-similarity
- DatabaseValidationJobManager
- register_library_routes
- validate_maest_analysis_row
- api_routes_evaluation.py
- test_benchmark_search.py
- test_classifier_jobs.py
- model_validator
- _parse_source_contribution
- test_database_validation.py
- _library_with_maest_candidate
- test_reference_compare_uses_current_outputs_and_current_summaries
- register_server_routes
- db_schema.py
- _client
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
- test_evaluation_optimizer_e2e.py
- _required_text

## God Nodes (most connected - your core abstractions)
1. `LibraryDatabase` - 360 edges
2. `AnalysisOutput` - 243 edges
3. `AnalysisTarget` - 205 edges
4. `RhythmLabDatabase` - 110 edges
5. `AnalysisJobManager` - 85 edges
6. `SourceDatabase` - 84 edges
7. `AnalysisCandidate` - 83 edges
8. `TrackIdentity` - 69 edges
9. `TrackInput` - 59 edges
10. `create_app()` - 58 edges

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
- **Audio Online Metadata Workbook Layout Evolution** — _superpowers_brainstorm_110_1786570313_content_xlsx_source_columns_source_columns_layout, _superpowers_brainstorm_110_1786570313_content_xlsx_source_columns_semicolon_source_columns_semicolon_layout, _superpowers_brainstorm_110_1786570313_content_xlsx_track_fields_track_fields_layout, _superpowers_brainstorm_110_1786570313_content_xlsx_genres_styles_tags_metadata_genres_styles_tags_layout, _superpowers_brainstorm_110_1786570313_content_xlsx_maest_last_top3_maest_last_top_three_layout, _superpowers_brainstorm_110_1786570313_content_xlsx_track_name_added_track_name_added_layout, _superpowers_brainstorm_656_1786571367_content_xlsx_track_name_layout_audio_online_metadata_layout [INFERRED 0.95]
- **CLAP Retrieval and Prompting Stack** — _agents_skills_clap_query_workflow_skill_clap_query_workflow, _agents_skills_clap_query_workflow_references_clap_prompting_reference_clap_prompting_reference, readme_clap [INFERRED 0.95]
- **Local Classifier Lifecycle** — docs_dj_track_similarity_tools_and_scripts_rhythm_lab_isolated_rhythm_lab_state, docs_dj_track_similarity_tools_and_scripts_rhythm_lab_promoted_classifier_artifacts, docs_dj_track_similarity_reference_analysis_families_database_only_classifier_scoring, docs_dj_track_similarity_user_guide_class_tab_personal_classifier_score, docs_dj_track_similarity_user_guide_class_tab_atomic_classifier_generation, docs_dj_track_similarity_user_guide_class_tab_manifest_compatibility_guard [INFERRED 0.95]
- **Confirmation-Gated Audio Operations** — docs_dj_track_similarity_user_guide_tags_and_audio_writes_audio_write_boundary, tools_audio_doctor_readme_dry_run_repair, tools_audio_dedup_readme_report_first_deletion [INFERRED 0.95]
- **Model Evidence Stack** — img_dj_track_similarity_banner_sonara, img_dj_track_similarity_banner_maest, img_dj_track_similarity_banner_mert, img_dj_track_similarity_banner_muq, img_dj_track_similarity_banner_clap, img_dj_track_similarity_banner_classifiers [INFERRED 0.95]
- **Listening-led selection loop** — docs_dj_track_similarity_concepts_project_idea_listening_led_local_workbench, docs_dj_track_similarity_concepts_similarity_scores_audition_order_scores, docs_dj_track_similarity_getting_started_quickstart_listening_led_quickstart_loop [INFERRED 0.95]
- **Local-First Safety Contract** — agents_local_first_safety_baseline, readme_report_first_maintenance, _agents_skills_codebase_documentation_writer_skill_local_first_safety_language, _agents_skills_clap_query_workflow_skill_audio_read_only_search [INFERRED 0.95]
- **Personal Classifier Lifecycle** — docs_dj_track_similarity_workflows_train_personal_classifier_personal_classifier_workflow, tools_rhythm_lab_readme_auxiliary_classifier_ui, tools_rhythm_lab_rhythm_lab_static_index_training_and_profile_creation, docs_dj_track_similarity_workflows_reanalyze_sonara_split_storage_classifier_refresh [INFERRED 0.95]

## Communities (254 total, 20 thin omitted)

### Community 0 - "dj_track_similarity/cli.py"
Cohesion: 0.05
Nodes (101): command, build_analysis_job_config(), _int_in_range(), normalize_analysis_device(), normalize_analysis_models(), _normalize_limit(), parse_analysis_models_text(), analyze() (+93 more)

### Community 1 - "FileTags"
Cohesion: 0.17
Nodes (37): ID3, _write_genre_tag(), FileTags, Human-readable tags read from an audio file., _decoded_audio_md5(), _make_tone(), parametrize, Path (+29 more)

### Community 2 - "label_transfer.py"
Cohesion: 0.08
Nodes (104): _absolute_lexical_path(), _backup_restore_target(), _build_parser(), build_rebound_bundle(), _build_restore_plan(), _canonical_json_bytes(), _canonical_json_text(), canonical_path_key() (+96 more)

### Community 3 - "source_db.py"
Cohesion: 0.04
Nodes (79): AnalysisCoverage, FileTags, MaestAnalysis, MaestGenre, _attach_labels(), _base_track_query(), _clean_path_text(), _count_sonara_features() (+71 more)

### Community 4 - "db_analysis.py"
Cohesion: 0.11
Nodes (31): RuntimeError, Raised when a write target no longer names the current track content., StaleAnalysisTargetError, AnalysisRepository, require_active_analysis_outputs(), _catalog_uuid(), _classifier_feature_vector_from_row(), _classifier_input_query_parts() (+23 more)

### Community 5 - "SourceDatabase"
Cohesion: 0.06
Nodes (77): One exact current track snapshot selected for a review collection., Ordered collection input bound to one library catalog., Repository for review collections in the Rhythm Lab database only., RhythmLabCollections, RhythmLabCollectionSelection, RhythmLabTrackSelection, Path, _selection() (+69 more)

### Community 6 - "AnalysisCandidate"
Cohesion: 0.17
Nodes (37): AnalysisJobConfig, decode_analysis_batch(), DecodeAudio, Exception, AnalysisJobStatus, AnalysisLogEvent, AnalysisModelProgress, AnalysisTrackError (+29 more)

### Community 7 - "RhythmLabDatabase"
Cohesion: 0.07
Nodes (51): _canonical_json(), _classifier_label_from_row(), _classifier_label_queue_table_sql(), _classifier_labels_table_sql(), _classifier_predictions_table_sql(), _classifier_training_checkpoints_table_sql(), ClassifierLabel, ClassifierPredictionWrite (+43 more)

### Community 8 - "sonara_features.py"
Cohesion: 0.06
Nodes (46): Any, _analysis_mapping(), _analysis_mapping_with_ffmpeg_fallback(), analysis_outputs_for_sonara_runtime(), analyze_and_store_sonara_batch(), _import_sonara(), Any, Protocol (+38 more)

### Community 9 - "app.js"
Cohesion: 0.04
Nodes (70): badgeRow(), binaryLabelGridEl, bpmMaxEl, bpmMinEl, candidateFiltersEl, candidateMinBrokenEl, candidateMinPositiveEl, candidatePredictedEl (+62 more)

### Community 10 - "classifier_scoring.py"
Cohesion: 0.07
Nodes (46): ClassifierCandidate, ClassifierFeatureRow, ClassifierScoreWrite, ClassifierJobManager, ClassifierJobStatus, ClassifierLogEvent, _ClassifierPayload, ClassifierTrackError (+38 more)

### Community 11 - "EmbeddingTrackIdentity"
Cohesion: 0.19
Nodes (20): TrackIdentity, current_track_identity(), EmbeddingTrackIdentity, _is_l2_unit_vector(), _positive_int(), Connection, ndarray, Row (+12 more)

### Community 12 - "track_models.py"
Cohesion: 0.07
Nodes (61): canonical_file_path(), _chunks(), _genres_json(), _identity_from_row(), _library_roots_from_json(), _library_roots_json(), _normalized_audio_duration(), ordinal_path_key() (+53 more)

### Community 13 - "JobStore"
Cohesion: 0.07
Nodes (26): Item, JobStatus, AnalysisPipelineManager, AnalysisPipelineStatus, _PipelinePayload, PipelineStageStatus, AnalysisStageQueue, One in-memory worker shared by SONARA, ML, and classifier stages. (+18 more)

### Community 14 - "ann_index.py"
Cohesion: 0.10
Nodes (59): _active_index_output(), _artifact_path_from_manifest(), _artifact_paths(), _assert_inside_directory(), _benchmark_k_values(), benchmark_persistent_index(), _build_manifest(), build_persistent_index() (+51 more)

### Community 15 - "api_schemas.py"
Cohesion: 0.10
Nodes (42): _outputs_for_family(), FastAPI, AnalysisCoverageResponse, AnalysisJobRequest, AnalysisPipelineRequest, AnalysisResetRequest, AnalysisResetResponse, ClassifierAnalyzeRequest (+34 more)

### Community 16 - "Reference Index"
Cohesion: 0.05
Nodes (63): Explicit Audio Write Boundary, DJ Track Similarity Documentation Home, Local-First Ranked Workflow, Listening-Led Shortlisting, Project Guide, Analysis Families Reference, Database-Only Classifier Scoring, ML Embedding Families (+55 more)

### Community 17 - "logging_config.py"
Cohesion: 0.06
Nodes (47): AbstractEventLoop, ConnectionResetError, Handler, Logger, _archive_active_log_path(), configure_logging(), _connection_reset_code(), _current_date_suffix() (+39 more)

### Community 18 - "App.tsx"
Cohesion: 0.06
Nodes (49): AnalysisSelection, analysisSelectionOrder, analysisStartBlockedByMissingSonara(), audioAnalysisModelOrder, defaultAnalysisSelections, mlAnalysisModelOrder, AnalysisModel, RhythmLabStatus (+41 more)

### Community 19 - "api.ts"
Cohesion: 0.05
Nodes (56): AnalysisCoverage, AnalysisJobStatus, AnalysisPipelineStatus, AnalysisResetResult, ClassifierResetResult, ClassifierScoreDetail, ClassifierScoreSummary, DatabaseClearResult (+48 more)

### Community 20 - "reports.py"
Cohesion: 0.13
Nodes (54): _aggregate_variant_metrics(), average_precision_at_k(), _axis_value(), bad_suggestion_rate_at_k(), _comparison_match_character(), _comparison_rank(), _comparison_reason_tags(), dcg_at_k() (+46 more)

### Community 21 - "TrackInput"
Cohesion: 0.09
Nodes (41): BeatportSource, DiscogsSource, _first_label(), Discogs database adapter using only its documented API surface., _strings(), _track_title(), LastFmSource, Last.fm community tag adapter. (+33 more)

### Community 22 - "test_rhythm_lab.py"
Cohesion: 0.09
Nodes (49): _predict_probabilities(), ndarray, _artifact_source_data_readiness(), _bind_artifact_source_readiness(), _create_profile(), _identity(), MonkeyPatch, parametrize (+41 more)

### Community 23 - "test_consumers.py"
Cohesion: 0.14
Nodes (57): PredictionProgressCallback, PromotionProgressCallback, _invalid_manifest(), load_classifier_manifest_summary(), Path, Resolve the root model and its matching root manifest., resolve_classifier_artifact_paths(), install_asyncio_exception_logging() (+49 more)

### Community 24 - "score_profiles.py"
Cohesion: 0.12
Nodes (43): build_score_profile_application_report(), build_score_profile_from_source_report(), _candidate_source_contributions(), _clean_k_values(), _consensus_summary(), _empty_metrics(), _limitations(), _limitations_are_explicit() (+35 more)

### Community 25 - "db_library_queries.py"
Cohesion: 0.07
Nodes (71): LibrarySummary, SonaraCore, ClassifierSpecification, _require_available_outputs(), _assemble_summaries(), _base_from_sql(), _base_select_fields(), _classifier_specifications_by_key() (+63 more)

### Community 26 - "db_migration.py"
Cohesion: 0.11
Nodes (53): _apply_schema(), create_library_schema(), Connection, Current single-library database DDL and typed Python domain models. This module…, Create the current single-library schema in *db*. Args: db: An open…, _attached_row_count(), _backup_sqlite(), _build_staged_library() (+45 more)

### Community 27 - "evaluation/ablation.py"
Cohesion: 0.10
Nodes (50): _ablated_signal(), _build_session_variants(), build_source_ablation_report(), _candidate_contributions_from_source_ranks(), _candidate_event(), _candidate_pool_sessions(), CandidateEvent, CandidatePoolSession (+42 more)

### Community 28 - "TrackMetadataDialog.tsx"
Cohesion: 0.07
Nodes (50): SonaraCore, formatMaestGenreLabel(), hasMaestSyncopatedRhythm(), SYNCOPATED_RHYTHM_LABEL, candidateRank(), copyTextToClipboard(), CoreFeature, CoreFeatureGroup (+42 more)

### Community 29 - "risk_sweep.py"
Cohesion: 0.10
Nodes (53): _average_transition_risk_at_k(), _best_by_metric(), _best_source_rank(), build_risk_penalty_sweep_report(), _cached_track(), _candidate_payload(), _candidate_with_risk_weight(), _clean_k_values() (+45 more)

### Community 30 - "Features, embeddings, and tags"
Cohesion: 0.06
Nodes (53): Classifiers and Rhythm Lab, Database-only classifier scoring, Immutable-generation promotion, Personal classifier, Rhythm Lab workflow, CLAP audio embedding, Features, embeddings, and tags, File tags (+45 more)

### Community 31 - "test_evaluation_cli.py"
Cohesion: 0.14
Nodes (42): current_embedding_analysis_output(), Build current adapter identity without loading model weights., _add_cli_track(), _build_candidate_export_library(), _build_optimizer_cli_library(), _expanded_unit_vector(), _identity_payload(), _maest_outputs() (+34 more)

### Community 32 - "metadata_enrichment_cli.py"
Cohesion: 0.10
Nodes (46): FormPost, JsonGet, Request, authorize_lastfm(), Explicit documented authorization flows for sources that support them., Open Last.fm consent and exchange its one-time token for a session key., _access_token(), _auth_values() (+38 more)

### Community 33 - "source_profile.py"
Cohesion: 0.12
Nodes (47): build_source_profile(), _clean_profile_request(), _clean_sources(), _clean_top_k_values(), _consensus_report(), _coverage_fallback_factors(), _effective_sources(), _int_value() (+39 more)

### Community 34 - "MuqEmbeddingAdapter"
Cohesion: 0.06
Nodes (28): MuqEmbeddingAdapter, Verify model assets and construct the configured loader., BatchMaestAdapter, FakeClapAudioModel, FakeMertModel, FakeMertProcessor, FakeMuqAudioModel, parametrize (+20 more)

### Community 35 - "SimilaritySearch"
Cohesion: 0.07
Nodes (65): FastAPI, register_reference_compare_routes(), _clap_text_search_plan(), _ClapTextSearchPlan, _clean_text_queries(), _hydrate_similarity_results(), FastAPI, FloatArray (+57 more)

### Community 36 - "sonara_similarity_scoring.py"
Cohesion: 0.12
Nodes (40): _merge_targets(), _optional_targets(), _optional_track_ids(), RuntimeError, Resolve request IDs to current tracks with active SONARA Core., Choose one unselected current track with valid SONARA Core features., _requested_track_ids(), _result_limit() (+32 more)

### Community 37 - "test_repair_audio_metadata.py"
Cohesion: 0.12
Nodes (45): _aiff_chunk(), _load_repair_module(), _minimal_aiff_with_empty_id3_chunks(), _minimal_pcm_wave(), Path, _riff_chunk(), test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload(), test_apply_forces_single_worker() (+37 more)

### Community 38 - "test_break_energy.py"
Cohesion: 0.31
Nodes (11): _FixedProbabilityModel, _insert_track(), _mert_output(), ndarray, Path, test_break_energy_job_scores_tracks_with_required_rows(), test_break_energy_public_scorer_preserves_probability_precision(), test_classifier_artifact_loads_without_version_or_contract_identity() (+3 more)

### Community 39 - "sonara_storage.py"
Cohesion: 0.11
Nodes (41): _beat_count(), _bpm_candidates_json(), _candidate_sequence(), _canonical_json_array(), _float32_blob(), _float32_policy_bound(), _float32_vector(), _frame_indices() (+33 more)

### Community 40 - "rhythm_lab/ablation.py"
Cohesion: 0.08
Nodes (52): benchmark_profile_ablation(), cli_summary(), _compact_row(), _default_output_path(), _elapsed_seconds(), _metrics_summary(), _normalize_feature_sets(), _optional_float() (+44 more)

### Community 41 - "SonaraFeatureRow"
Cohesion: 0.11
Nodes (40): SonaraFeatureRow, _optional_number(), _optional_text(), CsvRow, _optional_number(), _optional_text(), CsvRow, TrackIdentity (+32 more)

### Community 42 - "weighted_candidates.py"
Cohesion: 0.10
Nodes (40): CandidatePoolRow, CandidateSourceContribution, Path, save_score_profile(), score_profile_to_dict(), ScoreProfile, _clean_sources(), _effective_source_count() (+32 more)

### Community 43 - "TrackIdentity"
Cohesion: 0.07
Nodes (45): RhythmLabSourceBinding, BaseModel, FastAPI, model_validator, register_rhythm_lab_routes(), RhythmLabCollectionSaveRequest, TrackIdentityRequest, build_rhythm_lab_collection_selection_exact() (+37 more)

### Community 44 - "EvaluationRepository"
Cohesion: 0.11
Nodes (19): _embedding_output(), EvaluationRepository, _identity(), identity_payload(), profile(), AnalysisCoverage, Any, TrackIdentity (+11 more)

### Community 45 - "database.py"
Cohesion: 0.17
Nodes (24): RLock, Path, _bootstrap_file_lock(), _bootstrap_lock_path(), _cleanup_staged_sqlite(), _configure_connection(), connect_database(), _create_fresh_library() (+16 more)

### Community 46 - "analysis_model_runners.py"
Cohesion: 0.07
Nodes (41): ArrayLike, _store_synthetic_embeddings(), AnalysisBatchItem, _decoded_items(), default_model_runners(), EmbeddingModelRunner, _has_syncopated_rhythm(), _l2_normalize() (+33 more)

### Community 47 - "transition_diagnostics.py"
Cohesion: 0.13
Nodes (40): _best_relative_tempo_delta(), _bpm_risk(), _clamp(), _classifier_scores(), _clean_classifier_risk_weights(), _confidence_aware_bpm_risk(), _confidence_missingness_risk(), _contains_keyword() (+32 more)

### Community 48 - "test_audio_dedup.py"
Cohesion: 0.18
Nodes (40): _create_library_db(), _create_rhythm_lab_db(), _current_embedding_fixture(), _identity_tuple(), _insert_track(), _load_dedup_module(), CaptureFixture, MonkeyPatch (+32 more)

### Community 49 - "current_embedding_spec"
Cohesion: 0.16
Nodes (22): current_embedding_spec(), _apply_epsilon(), _contrast_score_breakdown(), _contrast_vector_scores(), _finite_number(), _matrix(), _merge_targets(), _normalize() (+14 more)

### Community 50 - "calibration.py"
Cohesion: 0.13
Nodes (40): _average_score(), _binary_label(), brier_score(), build_calibration_report(), _calibration_report(), _calibration_samples(), _calibration_status(), CalibrationSample (+32 more)

### Community 51 - "create_app"
Cohesion: 0.17
Nodes (21): create_app(), open_database_file_dialog(), open_folder_dialog(), FastAPI, Path, FastAPI, Path, register_docs_routes() (+13 more)

### Community 52 - "EvaluationRepository"
Cohesion: 0.14
Nodes (24): _canonical_json_value(), _clean_tags(), EvaluationRepository, _finite_float(), _json_load(), _json_object(), _json_text(), _load_track_snapshots() (+16 more)

### Community 53 - "score_profile_optimizer.py"
Cohesion: 0.16
Nodes (35): _accepted_decision(), _base_report(), _bootstrap_stability(), build_score_profile_optimizer_report(), _candidate_tie_break(), _decision_guidance(), _equal_weights(), _example_score() (+27 more)

### Community 54 - "AnalysisJobManager"
Cohesion: 0.16
Nodes (7): AnalysisJobStatus, RunnerFactory, AnalysisJobManager, DecodeAudio, Exception, exception_summary(), Exception

### Community 55 - "SearchPlaylistPanel.tsx"
Cohesion: 0.10
Nodes (32): EmbeddingSource, ClapPromptPreset, ClapSearchTab(), classifierIsAvailable(), classifierProfileStatus(), classifierScoringBlockedReason(), filterAvailableClassifierValues(), formatClassifierScoredTracks() (+24 more)

### Community 56 - "benchmark_search.py"
Cohesion: 0.13
Nodes (38): _active_embedding_output(), _benchmark_database_path(), _benchmark_track_count(), BenchmarkConfig, _camelot_key(), _conflicting_kept_database_path(), _environment_summary(), _insert_synthetic_tracks() (+30 more)

### Community 57 - "ClapEmbeddingAdapter"
Cohesion: 0.09
Nodes (16): ClapEmbeddingAdapter, _ensure_verified_maest_checkpoint(), MertEmbeddingAdapter, Verify model assets and construct the configured loader., Verify model assets and construct the configured loader., Populate and verify the torch-hub cache before maest-infer loads it., test_adapter_runtime_parameters_do_not_encode_loader_package_identity(), test_adapters_expose_dimensions_and_normalization_before_model_load() (+8 more)

### Community 58 - "SonaraSimilaritySearch"
Cohesion: 0.22
Nodes (37): SONARA feature-mixer search over current Core data. The separate 48-dimensional…, SonaraSimilaritySearch, _add_sonara_track(), _add_track_without_sonara(), _core_row(), _feature_value(), _float_or_none(), _int_or_none() (+29 more)

### Community 59 - "test_analysis_orchestration.py"
Cohesion: 0.12
Nodes (21): Local dj-track-similarity toolkit., _candidate(), _clap_output(), _decoded(), _FakeRepository, _mert_output(), MonkeyPatch, Path (+13 more)

### Community 60 - "classifier_production.py"
Cohesion: 0.12
Nodes (34): register_analysis_routes(), build_classifier_calibration_report(), _calibration_report_status(), _candidate_feedback_aggregates(), _classifier_feedback_summary(), _classifier_score_detail(), ClassifierScoreRow, _clean_classifier_key() (+26 more)

### Community 61 - "analysis_models.py"
Cohesion: 0.13
Nodes (25): _adapter_identity(), embedding_analysis_output(), Build the current embedding output for one production adapter., _required_adapter_text(), _runtime_parameters(), AnalysisResetResult, clap_embedding_output(), _embedding_output() (+17 more)

### Community 62 - "ScanJobManager"
Cohesion: 0.17
Nodes (15): log_failure(), Path, Run parallel discovery work against one thread-safe TrackRepository., ScanJobManager, ScanJobPayload, ScanJobStatus, ScanLogEvent, _audio() (+7 more)

### Community 63 - "rhythm_lab_launcher.py"
Cohesion: 0.15
Nodes (35): default_rhythm_lab_labels_path(), _clear_pid(), _file_size(), _is_rhythm_lab_process(), launch_rhythm_lab(), _listener_process_id(), _log_path(), _managed_process_id() (+27 more)

### Community 64 - "rhythm_lab/cli.py"
Cohesion: 0.14
Nodes (32): _add_data_options(), _artifact_calibration_payload(), _artifact_matches_calibration_filter(), _benchmark_ablation(), build_parser(), _calibration_report(), _collection_list(), _collection_save() (+24 more)

### Community 65 - "useLibraryState.ts"
Cohesion: 0.15
Nodes (29): LibrarySummary, Track, createLibraryLoadCoordinator(), LibraryLoadCoordinator, LibraryLoadTicket, libraryPageSize, libraryRequestKey(), LibraryRequestKeyParts (+21 more)

### Community 66 - "escapeHtml"
Cohesion: 0.12
Nodes (32): actionIcon(), canPromoteArtifact(), coverageBadge(), displayLabel(), escapeHtml(), formatFeatureGroupWeights(), formatLabelCounts(), isMulticlassProfile() (+24 more)

### Community 67 - "_Repository"
Cohesion: 0.12
Nodes (20): _Repository, _expanded_vector(), _identity(), _identity_payload(), AnalysisCoverage, ndarray, parametrize, TrackIdentity (+12 more)

### Community 68 - "AnalysisTarget"
Cohesion: 0.13
Nodes (27): AnalysisTarget, _candidates_without_seed(), HnswPersistentIndexSearcher, PersistentIndexBuildResult, PersistentIndexClearResult, PersistentIndexSearcher, ndarray, _vector_content_hash() (+19 more)

### Community 69 - "ScannedFile"
Cohesion: 0.14
Nodes (29): Background and synchronous jobs for the sole scan repository path., _audio_format(), _audio_format_from_mime(), _contains_tag(), file_tags_from_metadata(), _genres(), iter_audio_files(), _positive_float_or_none() (+21 more)

### Community 70 - "tempo_resolution.py"
Cohesion: 0.18
Nodes (28): best_tempo_distance(), _candidate_bpms(), _clamp01(), confidence_aware_target_score(), confidence_aware_tempo_risk(), confidence_aware_tempo_score(), _finite_float(), measured_tempo_score() (+20 more)

### Community 71 - "embedding.py"
Cohesion: 0.13
Nodes (24): BaseException, adapter_factories(), _download_verified_hf_checkpoint(), _download_verified_hf_snapshot(), _maest_float_list(), _maest_score_rows(), _masked_time_mean(), Resolve and privately bind one exact Hub file for deserialization. (+16 more)

### Community 72 - "frontend/package.json"
Cohesion: 0.07
Nodes (29): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+21 more)

### Community 73 - "scan_library"
Cohesion: 0.15
Nodes (30): ScanStats, Scan one root through the sole TrackRepository write path., scan_library(), Aggregate result returned by the synchronous scanner., ScanStats, _library_roots(), _mert_output(), MonkeyPatch (+22 more)

### Community 74 - "compute_transition_diagnostics"
Cohesion: 0.17
Nodes (28): compute_transition_diagnostics(), _mean_available(), Compute transition risk from identity-validated repository rows., _risk_version(), _classifier_score(), ClassifierScoreSummary, test_adjacent_camelot_key_has_lower_risk_than_clash(), test_aggregate_ignores_missing_components() (+20 more)

### Community 75 - "test_classifier_scoring.py"
Cohesion: 0.19
Nodes (30): load_classifier_requirements(), Validate the classifier recipe, required inputs, and artifact. This function is…, _artifact_hash(), _insert_track(), _install_fake_joblib(), _manifest_payload(), _mert_output(), _muq_output() (+22 more)

### Community 76 - "DecodedAudio"
Cohesion: 0.16
Nodes (15): DecodedAudio, torch_compatible_audio(), _array_output_to_numpy(), _construct_clap_module_with_pinned_text_model(), _local_only_from_pretrained_proxy(), _normalize_rows(), _pad_or_trim_audio_window(), ndarray (+7 more)

### Community 77 - "MaestWindowContext"
Cohesion: 0.29
Nodes (12): MaestWindowContext, _optional_boundary(), _positive_finite(), select_maest_window_starts(), _selected_range(), parametrize, test_centered_full_duration_starts(), test_invalid_context_falls_back_without_failure() (+4 more)

### Community 78 - "candidates.py"
Cohesion: 0.13
Nodes (26): _analysis_target(), _blind_candidate_rows(), _CandidateAccumulator, CandidateExportRequest, CandidateExportResult, _clean_sources(), _collect_candidates_for_seed(), export_candidate_pools() (+18 more)

### Community 79 - "seed_sampling.py"
Cohesion: 0.15
Nodes (27): _analysis_flag(), _bpm_bucket(), _bucket_for_values(), _buckets_used(), _clean_required_sources(), _energy_bucket(), export_seed_sample(), _finite_number() (+19 more)

### Community 80 - "loadActive"
Cohesion: 0.13
Nodes (29): bpmFilterValue(), currentPage(), jumpToPage(), loadActive(), loadCandidates(), loadCollectionTracks(), loadLikedTracks(), loadSettingsView() (+21 more)

### Community 81 - "audio_doctor/core.py"
Cohesion: 0.14
Nodes (27): escaped_codepoint(), is_xml_character(), normalize_state_sources(), _problems_sheet_rows(), resolve_state_path(), _results_sheet_rows(), safe_filename_part(), source_signature() (+19 more)

### Community 82 - "training.py"
Cohesion: 0.19
Nodes (26): benchmark_lab_database(), _bounded_top_n_values(), _calibration_gate(), _calibration_thresholds(), _cross_validation_metrics(), expected_calibration_error(), _feature_group_indices(), _feature_group_weights() (+18 more)

### Community 83 - "project_clap_search.py"
Cohesion: 0.21
Nodes (26): add_repo_src_to_path(), clean_lines(), db_path_from_env(), find_repo_root(), get_json(), main(), matching_source_track_ids(), normalize_path_for_db() (+18 more)

### Community 84 - "classifier_manifest.py"
Cohesion: 0.14
Nodes (18): classifier_manifest_api_fields(), ClassifierArtifactPaths, ClassifierManifestSummary, _clean_classifier_key(), _feature_sources(), _manifest_error_text(), _optional_text(), _parse_manifest_payload() (+10 more)

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
Cohesion: 0.14
Nodes (24): ReferenceCompareGroup, ReferenceCompareModel, ReferenceCompareVerdict, TrackIdentity, normalizeLimit(), orderedReferenceCompareGroups(), ReferenceCompareGroupCard(), referenceCompareModels (+16 more)

### Community 89 - "AnalysisVectorRow"
Cohesion: 0.11
Nodes (19): AnalysisVectorRow, PersistentAnnVectorSearchBackend, Strict persistent HNSW search over one current embedding output. The backend…, fake_hnsw(), FakeAnalysisRepository, FakeHnswModule, Index, fixture (+11 more)

### Community 90 - "tags.py"
Cohesion: 0.13
Nodes (24): GenreTagCandidate, _apply_genre_tag_to_candidate(), apply_genre_tags_to_tracks(), _clean_genre_label(), genre_tag_apply_summary(), _genre_tags_for_candidate(), GenreTagApplyResult, GenreTagError (+16 more)

### Community 91 - "LibraryDatabase"
Cohesion: 0.18
Nodes (19): LibraryDatabase, Connection, EvaluationRepository, ndarray, _add_track(), Path, test_classifier_score_counts_use_keys_and_count_rows_only(), test_public_library_filter_combines_search_and_liked_state() (+11 more)

### Community 92 - "load_tracks"
Cohesion: 0.16
Nodes (23): Standalone online track-metadata enrichment tool., _load_audio_file(), _load_csv(), _load_directory(), _load_m3u(), load_tracks(), _load_xlsx(), Path (+15 more)

### Community 93 - "report.py"
Cohesion: 0.14
Nodes (22): LocalEvidence, build_report_contract(), _clean(), _column(), _join(), _maest(), Path, Source-preserving intermediate report contract. (+14 more)

### Community 94 - "DatabaseValidator"
Cohesion: 0.16
Nodes (14): DatabaseValidationReport, DatabaseValidator, format_validation_finding(), DatabaseValidationEvent, Single-threaded lifecycle for explicit database validation., Connection, Path, Row (+6 more)

### Community 95 - "media_preview.py"
Cohesion: 0.23
Nodes (13): CalledProcessError, FileResponse, OSError, AudioPreviewError, _decode_stderr(), _delete_temp_file(), _is_browser_safe_wav(), _preview_error_message() (+5 more)

### Community 96 - "test_audio_loader.py"
Cohesion: 0.18
Nodes (23): SimpleNamespace, set_analysis_diagnostics_enabled(), _make_malformed_wave(), ndarray, Path, skipif, test_ffmpeg_decode_pins_first_audio_stream_and_disables_non_audio(), test_ffmpeg_decode_reports_invalid_audio_stream_when_ffmpeg_fails() (+15 more)

### Community 97 - "audio_dedup/core.py"
Cohesion: 0.16
Nodes (24): _bool_text(), _candidates_sheet_rows(), _evidence_by_candidate(), _groups_sheet_rows(), _pair_evidence_sheet_rows(), rhythm_lab_cli_summary(), _rhythm_lab_sheet_rows(), rhythm_lab_summary() (+16 more)

### Community 98 - "storage_database_paths"
Cohesion: 0.24
Nodes (11): _load_script(), Path, test_optimize_database_backs_up_library_and_existing_evaluation_sidecar(), test_optimize_database_does_not_reject_future_library_tables(), test_optimize_database_handles_generic_sqlite_file(), Path, Filesystem topology for the library and optional Evaluation sidecar., Optional sidecars belonging to one library catalog. (+3 more)

### Community 99 - "compilerOptions"
Cohesion: 0.09
Nodes (22): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+14 more)

### Community 100 - "sonara_core_validation.py"
Cohesion: 0.21
Nodes (22): SonaraCoreRow, _exact_object(), _json_array(), _optional_int(), _optional_number(), _optional_text(), Canonical semantic validation for persisted SONARA Core rows., Validate one complete SONARA Core row against writer semantics. (+14 more)

### Community 101 - "audio_loader.py"
Cohesion: 0.25
Nodes (22): _decode_pcm_bytes(), _ffmpeg_path(), _ffprobe_path(), _invalid_audio_stream_message(), _is_mono_wave(), load_audio_mono(), load_audio_mono_with_ffmpeg(), load_decoded_audio() (+14 more)

### Community 102 - "MaestEmbeddingAdapter"
Cohesion: 0.13
Nodes (9): _average_maest_embeddings(), _maest_embedding_rows(), MaestAnalysisResult, MaestEmbeddingAdapter, _move_maest_runtime_modules(), Verify model assets and construct the configured loader., FakeMaestModel, MovableModule (+1 more)

### Community 103 - "AppDatabaseState"
Cohesion: 0.13
Nodes (10): FastAPI, Path, register_database_routes(), DatabaseStateResponse, DatabaseSwitchRequest, AppDatabaseState, Path, Return the selected database only when no background job is active. (+2 more)

### Community 104 - "select_torch_device"
Cohesion: 0.13
Nodes (13): Any, select_torch_device(), load_score_prompt_bank_module(), Path, test_checkpoint_loading_fails_closed_when_torch_lacks_weights_only(), test_checkpoint_loading_forces_weights_only(), test_clap_model_load_stdout_and_stderr_are_written_to_app_log(), test_clap_text_embedding_preflights_pinned_verified_checkpoint_once() (+5 more)

### Community 105 - "build_saved_score_profile_payload"
Cohesion: 0.19
Nodes (20): _assert_normalized_weights(), build_saved_score_profile_payload(), _clean_k_values(), _grid_step(), _int_value(), _non_negative_finite_float(), _non_negative_int(), _objective() (+12 more)

### Community 106 - "test_evaluation_seed_sampling.py"
Cohesion: 0.31
Nodes (18): _ml_outputs(), ndarray, Path, TrackIdentity, _save_complete_analysis(), _save_ml_embeddings(), _save_sonara_core(), _seed_sample_library() (+10 more)

### Community 107 - "main"
Cohesion: 0.13
Nodes (14): apply_duplicate_deletions(), apply_result_payload(), ApplyResult, _candidate_track_id(), configure_stdio(), confirm_apply(), ConsoleProgressReporter, main() (+6 more)

### Community 108 - "PresetConfig"
Cohesion: 0.15
Nodes (22): _bits_to_int(), _candidate_duration_compatible(), _candidate_pair_ids(), _candidate_reason_lines(), _candidate_safety(), _connected_components(), _content_similarity(), _duration_distance() (+14 more)

### Community 109 - "parseJsonResponse"
Cohesion: 0.16
Nodes (22): addMulticlassLabelRow(), addOption(), applySourceState(), chooseSource(), clearActiveProfile(), collectNewProfileLabels(), createProfile(), deleteActiveProfile() (+14 more)

### Community 110 - "jobUi.tsx"
Cohesion: 0.16
Nodes (15): AnalysisProcessStatus(), analysisRuntimeLabel(), GenreTagProcessStatus(), isPerClassifierAnalysisEvent(), ProgressItem, ProgressRow, ScanProcessStatus(), sourceLabel() (+7 more)

### Community 111 - "_add_track"
Cohesion: 0.44
Nodes (13): _add_track(), _library(), _output(), ndarray, Path, _query(), test_search_contrast_vectors_rank_positive_over_negative_match(), test_search_contrast_vectors_use_hard_negative_margin_not_probability() (+5 more)

### Community 112 - "test_evaluation_score_profile_optimizer.py"
Cohesion: 0.29
Nodes (16): _add_two_candidate_session(), _build_bad_rate_increase_library(), _build_empty_seed_shell(), _build_two_candidate_optimizer_library(), _candidate_event(), EvaluationRepository, test_optimizer_does_not_write_database_rows_by_default(), test_optimizer_ignores_unmatched_feedback_rows() (+8 more)

### Community 113 - "test_api_tracks.py"
Cohesion: 0.37
Nodes (15): _add_track(), _client(), _liked_payload(), Path, TestClient, TrackIdentity, test_media_endpoint_reports_missing_audio_file_without_traceback(), test_media_endpoint_reports_transcode_failure_without_traceback() (+7 more)

### Community 114 - "DJ Track Similarity Banner"
Cohesion: 0.16
Nodes (20): AI-Assisted Music Analysis, CLAP, Classifiers, DJ Set Building, DJ Track Similarity Banner, Genre Detection, High Resolution Audio Insights, Library Exploration (+12 more)

### Community 115 - "ExactVectorSearchBackend"
Cohesion: 0.21
Nodes (16): ExactVectorSearchBackend, Deterministic exact cosine search over validated unit vectors., _mert_output(), _mert_unit_vector(), MonkeyPatch, ndarray, Path, TrackIdentity (+8 more)

### Community 116 - "tests/test_cli.py"
Cohesion: 0.21
Nodes (15): _FakeAnalysisManager, MonkeyPatch, Path, test_analyze_cli_passes_separate_ml_batch_sizes(), test_analyze_cli_prints_default_ml_progress_and_settings(), test_analyze_cli_rejects_unknown_device_before_opening_manager(), test_analyze_cli_runs_sonara_core_only(), test_relocate_library_cli_applies_typed_current_path_update() (+7 more)

### Community 117 - "artifact_io.py"
Cohesion: 0.17
Nodes (21): PublicationProgressCallback, artifact_sha256(), ArtifactIntegrityError, _default_metadata_path(), _fsync_directory(), load_verified_artifact(), publish_promoted_artifact(), PublishedArtifact (+13 more)

### Community 118 - "optimize_database.py"
Cohesion: 0.19
Nodes (12): _backup_database(), _database_files(), _detect_database_kind(), _integrity_check(), main(), OptimizationSummary, optimize_database(), _optimize_one_database() (+4 more)

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

### Community 125 - "test_api_analysis_jobs.py"
Cohesion: 0.37
Nodes (17): _analysis_start(), _client(), MonkeyPatch, Path, TestClient, test_api_defaults_audio_job_to_ml_models_only(), test_api_does_not_register_bulk_classifier_analysis(), test_api_lists_classifier_manifests_with_direct_score_counts() (+9 more)

### Community 126 - "test_api_database_selection.py"
Cohesion: 0.18
Nodes (14): _add_track(), _ffmpeg(), fixture, parametrize, Path, _selected_state(), test_database_file_dialog_switches_to_selected_current_bundle(), test_database_switch_creates_selected_current_bundle() (+6 more)

### Community 127 - "test_api_rhythm_lab.py"
Cohesion: 0.19
Nodes (18): _add_track(), _identity_payload(), Path, TrackIdentity, test_rhythm_lab_collection_save_endpoint_writes_default_lab_database(), test_rhythm_lab_collection_save_rejects_legacy_numeric_only_body(), test_rhythm_lab_default_log_path_uses_logs_directory(), test_rhythm_lab_default_pid_path_uses_database_directory() (+10 more)

### Community 128 - "AnalysisOutput"
Cohesion: 0.10
Nodes (13): AnalysisOutput, Exception, _candidate(), _maest_output(), _mert_output(), Exception, _Repository, _Runner (+5 more)

### Community 129 - "loadTrainingReadiness"
Cohesion: 0.39
Nodes (18): calibrateClassifier(), fileName(), handleTrainingActionClick(), loadTrainingReadiness(), parseRefreshResponse(), pollTrainingProgress(), promoteClassifier(), refreshCandidates() (+10 more)

### Community 130 - "run_report"
Cohesion: 0.24
Nodes (18): CancelCheck, ProgressCallback, _attach_embeddings(), AudioDedupCancelled, _connect_readonly(), count_database_tracks(), find_duplicate_groups(), load_tracks() (+10 more)

### Community 131 - "Personal Classifier Workflow"
Cohesion: 0.17
Nodes (17): Feature Ablation Benchmark, Calibration Data Gate, Database-Only Classifier Scoring, Immutable Generation Promotion, Ordered Classifier Feature Recipe, Personal Classifier Workflow, Reusable Ranking Signal, Not Truth, Rhythm Lab Isolated State (+9 more)

### Community 132 - "qa_database.py"
Cohesion: 0.23
Nodes (16): _build_parser(), _fail(), _foreign_key_check(), _integrity_check(), main(), _open_read_only(), ArgumentParser, Connection (+8 more)

### Community 133 - "recorded_sessions.py"
Cohesion: 0.32
Nodes (16): _contains_legacy_version_identity(), _current_session(), _event_provenance_matches(), load_current_evaluation_sessions(), _mapping_sequence(), _persisted_snapshot_matches(), _positive_int_or_none(), Any (+8 more)

### Community 134 - "test_api_sonara_search.py"
Cohesion: 0.28
Nodes (16): _add_embedding_track(), _add_sonara_track(), _blob(), _float(), _mert_output(), parametrize, Path, _sonara_library() (+8 more)

### Community 135 - "read_local_evidence"
Cohesion: 0.21
Nodes (15): _find_by_metadata(), _find_by_path(), Connection, Path, Row, Read local genre evidence without modifying a library database., Return tags and at most three MAEST genres from one unambiguous local track., read_local_evidence() (+7 more)

### Community 136 - "judged.py"
Cohesion: 0.21
Nodes (19): build_judged_label_gate(), _first_label_for_any_source(), judged_label_guidance(), judged_label_status(), _labels_by_rating(), matched_judged_labels(), MatchedJudgedLabel, matching_label() (+11 more)

### Community 137 - "test_api_reference_compare.py"
Cohesion: 0.33
Nodes (15): _client(), _embedding_outputs(), _identity_payload(), _maest_analysis_output(), parametrize, Path, TestClient, _reference_library() (+7 more)

### Community 138 - "db_analysis_candidates.py"
Cohesion: 0.20
Nodes (17): AnalysisResetResult, collect_analysis_candidates(), current_sonara_target_keys(), _current_tracks(), _maest_window_context(), missing_outputs_for_target(), normalize_analysis_outputs(), Connection (+9 more)

### Community 139 - "db_search_fts.py"
Cohesion: 0.25
Nodes (12): delete_track_search_fts(), _file_genres_text(), _maest_genres_text(), Connection, Track-search FTS maintenance. The FTS index contains only text a person can…, Delete one track from the live FTS index without committing., Refresh one track's human-text FTS row without committing., Rebuild the human-text FTS index atomically. If the caller already owns a… (+4 more)

### Community 140 - "test_api_runtime.py"
Cohesion: 0.35
Nodes (13): _client(), Path, TestClient, test_classifier_preflight_conflict_returns_http_409_before_start(), test_database_switch_bootstraps_clean_selected_current_bundle(), test_exclusive_database_operation_blocks_new_jobs(), test_job_start_reservation_closes_exclusive_operation_toctou(), test_liked_mutation_requires_current_composite_identity() (+5 more)

### Community 141 - "beatport.py"
Cohesion: 0.25
Nodes (12): _artists(), _label(), Beatport v4 Catalog Search adapter using documented bearer authentication., _record(), _text(), _year(), _normalized(), Conservative deterministic match assessment for source records. (+4 more)

### Community 142 - "Classifier Workflow"
Cohesion: 0.22
Nodes (13): Benchmark Variants, Broken vs Straight Beat Classifier, Classifier Workflow, Collect Labels, Local Music Library, Music Attribute Classifiers, Personal Music Classifiers, Production Readiness (+5 more)

### Community 143 - "test_api_evaluation.py"
Cohesion: 0.41
Nodes (12): _client(), ndarray, Path, TestClient, test_evaluation_api_rejects_unselected_and_legacy_database(), test_evaluation_feedback_does_not_touch_audio_path(), test_evaluation_feedback_endpoints_validate_and_preserve_seed_scope(), test_evaluation_summary_keeps_feedback_in_library_and_sessions_in_sidecar() (+4 more)

### Community 144 - "wave_tags.py"
Cohesion: 0.17
Nodes (14): Frame, _AudioWithId3Tags, _genre_frame_text(), _Id3Tags, Path, Protocol, _replace_id3_genre(), _require_readable_wave_audio() (+6 more)

### Community 145 - "formatHumanDate"
Cohesion: 0.23
Nodes (13): formatHumanDate(), formatMetricDelta(), formatMetricPercent(), metricNumberText(), metricPercentText(), parseTrainingDate(), refreshTrainingInformation(), renderTrainingDynamicsLine() (+5 more)

### Community 146 - "run-vale.mjs"
Cohesion: 0.20
Nodes (11): baseValeArgs, collectMarkdownFiles(), docsRoot, markdownFiles, repoRoot, resolveVale(), runVale(), scriptDir (+3 more)

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

### Community 151 - "connect_evaluation_sidecar"
Cohesion: 0.35
Nodes (11): _apply_schema(), _configure_connection(), connect_evaluation_sidecar(), create_evaluation_sidecar_schema(), _creation_lock_path(), _enforce_wal(), Connection, Path (+3 more)

### Community 152 - "track_views.py"
Cohesion: 0.27
Nodes (11): _active_sonara_rows(), _analysis_target(), load_all_transition_tracks(), _load_transition_tracks(), load_transition_tracks_for_ids(), load_transition_tracks_for_targets(), TrackIdentity, Identity-bound typed track views for evaluation workflows. (+3 more)

### Community 153 - "test_api_dialog.py"
Cohesion: 0.32
Nodes (11): _add_track(), _ffmpeg(), fixture, Path, test_choose_folder_endpoint_allows_cancel(), test_choose_folder_endpoint_reports_unavailable_dialog(), test_choose_folder_endpoint_returns_selected_path(), test_create_app_requires_ffmpeg() (+3 more)

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

### Community 161 - "Workflows"
Cohesion: 0.25
Nodes (9): Workflows, Backed-Up Database Optimization, Explicit Single-Library Migration, Maintain a Library Safely, Bounded Reanalysis Pilot, Dependent Classifier Refresh, Legacy Split-Storage Migration, Reanalyze SONARA Data (+1 more)

### Community 162 - "run_server_launcher.py"
Cohesion: 0.36
Nodes (8): Popen, build_frontend_command(), build_server_command(), frontend_directory(), main(), Path, resolve_npm_executable(), stop_process()

### Community 163 - "Unified SQLite Music Library"
Cohesion: 0.44
Nodes (9): CLAP Text-to-Audio and Audio-to-Audio Search, Explicit Backup-First Legacy Database Migration, MAEST Genre and Audio Embedding, MERT Audio Embedding, Separated Model Evidence Sources, MuQ Audio Embedding, SONARA Audio Features, Unified SQLite Music Library (+1 more)

### Community 164 - "ExportTrackRow"
Cohesion: 0.29
Nodes (10): FastAPI, Path, register_tags_export_routes(), export_tracks(), Path, Playlist export for typed library rows., _safe_filename(), _write_csv() (+2 more)

### Community 165 - "workbook_bridge.mjs"
Cohesion: 0.28
Nodes (7): artifactToolPath, buildWorkbook(), main(), require, artifactToolPath, execFile, require

### Community 166 - "CLAP Query Workflow"
Cohesion: 0.29
Nodes (8): CLAP Query Workflow Agent Interface, CLAP Prompting Reference, Deterministic 10-Second Audio Segmentation, LAION-CLAP Music Configuration, Audio Read-Only CLAP Search Boundary, CLAP Query Workflow, Stored CLAP Database Seed Search, Temporary CLAP Audio Analysis Search

### Community 167 - "DJ Track Similarity Agent Instructions"
Cohesion: 0.36
Nodes (8): Local-First Safety Documentation Language, Active-Development Operating Model, Executable Sources as Authority, Graphify Codebase Query Workflow, Local-First Safety Baseline, Direct Main-Branch Development Workflow, DJ Track Similarity Agent Instructions, Risk-Scoped Verification Routing

### Community 168 - "Russian Project Overview"
Cohesion: 0.25
Nodes (8): Accepted Project Vocabulary, Report-First Maintenance Tools, Rhythm Lab Personal Classifiers, Russian CLAP Text Search Explanation, Russian Multi-Model Similarity Explanation, Russian Project Overview, Russian Report-First Helper Tools, Russian Rhythm Lab Explanation

### Community 169 - "Temporary Current Set"
Cohesion: 0.36
Nodes (8): Temporary Current Set, Export a Playlist Preview, Local Path Export Privacy, M3U and CSV Playlist Export, Rhythm Lab Collection Save, Build Crates for Later Listening, Crate-Building Workflow, Crate as a Reviewed Pool

### Community 170 - "rank_maest_genres"
Cohesion: 0.36
Nodes (6): rank_genres(), rank_maest_genres(), Turn MAEST genre logits, already activated by the model adapter, into labels., Average MAEST genre scores from each track's analysis windows, then rank., test_rank_genres_orders_scores_and_limits_results(), test_rank_maest_genres_averages_each_tracks_windows_before_top_k()

### Community 171 - "Response"
Cohesion: 0.25
Nodes (3): OAuth token requests must send fields as a form, not URL query data., Response, test_post_form_json_uses_urlencoded_post_body()

### Community 172 - "Codebase Documentation Writer"
Cohesion: 0.29
Nodes (7): Documentation Writer Agent Interface, Codebase Documentation Writer, Documentation Verification Workflow, Maintained Documentation Surface, Source-Grounded Documentation, VitePress Documentation Information Architecture, VitePress Documentation Pointer

### Community 173 - "Audio Online Metadata Workbook Layout"
Cohesion: 0.38
Nodes (7): Metadata XLSX Genres, Styles, and Tags Layout, MAEST Last Column with Top-Three Genres, Source Columns with Semicolon-Delimited Values, Metadata Sources as Columns Layout, Track Fields as Rows Layout, Track Name Field Addition, Audio Online Metadata Workbook Layout

### Community 175 - "libraryView.test.mjs"
Cohesion: 0.62
Nodes (6): loadExportViewModule(), loadLibraryViewModule(), loadPlaylistViewModule(), loadSyncopatedRhythmModule(), transpile(), writeTranspiledModule()

### Community 176 - "searchPlaylistLayout.test.mjs"
Cohesion: 0.29
Nodes (3): panelSource, styles, trackPanelSource

### Community 177 - "themeMode.test.mjs"
Cohesion: 0.29
Nodes (4): appSource, srcDir, styles, themePath

### Community 178 - "Local-First DJ Library Workbench"
Cohesion: 0.29
Nodes (7): Browser-Local Current Set, Listening-Led Ranking Signals, Local-First DJ Library Workbench, Russian Project Limitations, Russian Local-First Workbench Description, DJ Set Dramaturgy, Three-Layer Set Compatibility Model

### Community 179 - "test_classifier_manifest.py"
Cohesion: 0.71
Nodes (6): _manifest_payload(), Path, test_manifest_derives_input_families_from_ordered_feature_names(), test_manifest_rejects_duplicate_feature_names(), test_muq_manifest_checks_current_embedding_dimension(), _write_manifest()

### Community 180 - "test_export.py"
Cohesion: 0.52
Nodes (6): Path, TrackIdentity, _scan_track(), test_export_endpoint_writes_current_track_list_without_saving_playlist(), test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(), test_saved_playlist_endpoint_is_absent()

### Community 181 - "test_config.py"
Cohesion: 0.33
Nodes (6): CaptureFixture, Path, Prevent silently sending a credential to an unimplemented service., Prevent OAuth session material from leaking into normal CLI output., test_load_config_rejects_unknown_configured_source(), test_save_auth_data_persists_session_without_printing_secret()

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

### Community 188 - "User Guide"
Cohesion: 0.40
Nodes (5): Listening-Led Shortlisting, DJ Library UI Workbench, User Guide, Outcome-Oriented Workflow Routing, Preview-First Working Habit

### Community 189 - "config.mts"
Cohesion: 0.40
Nodes (4): commonTheme, englishNav, englishSidebar, SidebarSection

### Community 190 - "test_qa_database_script.py"
Cohesion: 0.70
Nodes (4): _load_script(), Path, test_qa_database_allows_future_library_tables(), test_qa_database_checks_library_and_optional_evaluation()

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

### Community 224 - "DatabaseValidationJobManager"
Cohesion: 0.26
Nodes (6): DatabaseValidationJobManager, DatabaseValidationJobStatus, MonkeyPatch, Path, test_job_keeps_ok_events_for_ui_without_writing_them_to_file_log(), test_manager_allows_only_one_queued_or_running_validation()

### Community 225 - "register_library_routes"
Cohesion: 0.21
Nodes (13): HTTPException, current_classifier_specifications(), query_classifier_min_scores(), valid_classifier_min_scores(), _classifier_info_by_key(), _classifier_manifest_error_text(), _require_known_classifier(), _require_scoring_compatible_classifier() (+5 more)

### Community 226 - "validate_maest_analysis_row"
Cohesion: 0.22
Nodes (12): MaestAnalysisRow, Explicitly repair MAEST syncopated-rhythm flags from stored genres., has_maest_syncopated_rhythm(), parse_maest_genres_json(), Canonical semantic validation for persisted MAEST analysis rows., Return whether MAEST genre labels indicate a syncopated rhythm style., Validate one complete MAEST analysis row against writer semantics., Parse canonical MAEST genre JSON without silently dropping entries. (+4 more)

### Community 227 - "api_routes_evaluation.py"
Cohesion: 0.29
Nodes (11): _inline_score_profile_payload(), Any, FastAPI, register_evaluation_routes(), _score_profile_from_request(), _score_profile_from_source_profile(), _score_profile_name(), _utc_timestamp() (+3 more)

### Community 228 - "test_benchmark_search.py"
Cohesion: 0.35
Nodes (10): CompletedProcess, parametrize, Path, _run_benchmark(), _run_benchmark_raw(), test_benchmark_search_keep_db_preserves_current_bundle(), test_benchmark_search_rejects_invalid_vector_backend(), test_benchmark_search_rejects_output_that_overlaps_keep_db() (+2 more)

### Community 229 - "test_classifier_jobs.py"
Cohesion: 0.35
Nodes (10): _insert_present_classifier_inputs(), _insert_track(), _mert_output(), MonkeyPatch, Path, Create more persisted classifier inputs than one job batch holds., _requirements(), _score_count() (+2 more)

### Community 230 - "model_validator"
Cohesion: 0.22
Nodes (3): EvaluationPairFeedbackRequest, model_validator, ReferenceCompareRequest

### Community 231 - "_parse_source_contribution"
Cohesion: 0.25
Nodes (9): _optional_finite_float(), _optional_positive_int(), _parse_source_contribution(), _source_contributions(), _source_payload(), SourceContribution, _transition_risk(), _optimizer_example_for_missing_source_test() (+1 more)

### Community 232 - "test_database_validation.py"
Cohesion: 0.53
Nodes (8): Path, test_validate_database_cli_uses_concise_human_messages(), test_validator_reports_corrupt_embedding_payload(), test_validator_reports_each_track_and_does_not_mutate_database(), test_validator_reports_invalid_classifier_probabilities(), test_validator_reports_non_finite_sonara_feature_vector(), test_validator_warns_when_stored_track_path_is_missing(), _track()

### Community 233 - "_library_with_maest_candidate"
Cohesion: 0.61
Nodes (7): _library_with_maest_candidate(), _make_tagged_wave(), Path, test_genre_tag_apply_rejects_cross_catalog_candidate_before_source_write(), test_genre_tag_apply_rejects_stale_files_before_source_write(), test_genre_tag_apply_requires_readback_before_recording_self_write(), test_genre_tag_job_uses_current_candidate_and_preserves_tags()

### Community 234 - "test_reference_compare_uses_current_outputs_and_current_summaries"
Cohesion: 0.43
Nodes (7): _insert_track(), _mert_output(), _mert_vector(), ndarray, Path, _sonara_row(), test_reference_compare_uses_current_outputs_and_current_summaries()

### Community 235 - "register_server_routes"
Cohesion: 0.38
Nodes (4): FastAPI, register_server_routes(), test_shutdown_route_requires_explicit_action_header(), test_shutdown_route_schedules_shutdown_after_acknowledgement()

### Community 236 - "db_schema.py"
Cohesion: 0.38
Nodes (6): insert_library(), Connection, Bootstrap and minimal identity checks for a single library database., Initialize the one metadata row of a freshly created library., _roots_json(), _utc_timestamp()

### Community 237 - "_client"
Cohesion: 0.60
Nodes (6): _client(), MonkeyPatch, Path, TestClient, test_sonara_analysis_api_queues_without_release_preflight(), test_sonara_status_endpoint_is_neutral_and_release_routes_are_removed()

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

### Community 251 - "test_evaluation_optimizer_e2e.py"
Cohesion: 0.70
Nodes (4): _build_weighted_feedback_fixture(), _classifier_adjusted_event_count(), EvaluationRepository, test_weighted_feedback_optimizer_profile_save_e2e_fixture()

## Ambiguous Edges - Review These
- `Recording Indicator` → `Rhythm Lab Favicon`  [AMBIGUOUS]
  tools/rhythm-lab/rhythm_lab/static/favicon.svg · relation: references

## Knowledge Gaps
- **301 isolated node(s):** `SidebarSection`, `englishNav`, `englishSidebar`, `commonTheme`, `name` (+296 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `ClassifierScoreWrite` (4× useful, score=3.998200986)
- `AnalysisOutput` (4× useful, score=3.997349676)
- `ClassifierSpecification` (2× useful, score=1.999297715)
- `.save_classifier_scores()` (2× useful, score=1.999060467)
- `_upsert_classifier_score()` (2× useful, score=1.999060467)
- `_validate_classifier_score()` (2× useful, score=1.999060467)
- `ClassifierScoreRecord` (2× useful, score=1.999017723)
- `table_for_output()` (2× useful, score=1.998887278)
- `_classifier_feature_vector_from_row()` (2× useful, score=1.998887278)
- `_classifier_input_query_parts()` (2× useful, score=1.998887278)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Recording Indicator` and `Rhythm Lab Favicon`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `LibraryDatabase` connect `LibraryDatabase` to `dj_track_similarity/cli.py`, `FileTags`, `run_report`, `db_analysis.py`, `recorded_sessions.py`, `test_api_sonara_search.py`, `SourceDatabase`, `test_api_reference_compare.py`, `classifier_scoring.py`, `EmbeddingTrackIdentity`, `track_models.py`, `JobStore`, `test_api_runtime.py`, `test_api_evaluation.py`, `reports.py`, `score_profiles.py`, `db_library_queries.py`, `track_views.py`, `evaluation/ablation.py`, `test_api_dialog.py`, `risk_sweep.py`, `build_report_payload`, `test_evaluation_cli.py`, `TrackPathRecord`, `source_profile.py`, `SimilaritySearch`, `test_repair_audio_metadata.py`, `test_break_energy.py`, `weighted_candidates.py`, `TrackIdentity`, `database.py`, `analysis_model_runners.py`, `test_audio_dedup.py`, `calibration.py`, `create_app`, `EvaluationRepository`, `score_profile_optimizer.py`, `test_export.py`, `benchmark_search.py`, `SonaraSimilaritySearch`, `test_analysis_orchestration.py`, `classifier_production.py`, `test_qa_database_script.py`, `ScanJobManager`, `rhythm_lab/cli.py`, `AnalysisTarget`, `scan_library`, `test_classifier_scoring.py`, `candidates.py`, `seed_sampling.py`, `project_clap_search.py`, `main`, `Path`, `RepairError`, `DatabaseValidator`, `DatabaseValidationJobManager`, `storage_database_paths`, `api_routes_evaluation.py`, `test_classifier_jobs.py`, `AppDatabaseState`, `_parse_source_contribution`, `test_database_validation.py`, `test_evaluation_seed_sampling.py`, `_library_with_maest_candidate`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `main`, `PresetConfig`, `_add_track`, `test_api_tracks.py`, `ExactVectorSearchBackend`, `tests/test_cli.py`, `build_weighted_candidate_pool`, `TrackRecord`, `FileRepairResult`, `test_api_database_selection.py`, `test_api_rhythm_lab.py`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `AnalysisOutput` connect `AnalysisOutput` to `db_analysis.py`, `AnalysisCandidate`, `test_api_sonara_search.py`, `sonara_features.py`, `test_api_reference_compare.py`, `classifier_scoring.py`, `db_analysis_candidates.py`, `JobStore`, `ann_index.py`, `api_schemas.py`, `test_consumers.py`, `db_library_queries.py`, `test_evaluation_cli.py`, `SimilaritySearch`, `sonara_similarity_scoring.py`, `test_break_energy.py`, `sonara_storage.py`, `EvaluationRepository`, `analysis_model_runners.py`, `current_embedding_spec`, `create_app`, `AnalysisJobManager`, `benchmark_search.py`, `SonaraSimilaritySearch`, `test_analysis_orchestration.py`, `classifier_production.py`, `analysis_models.py`, `_Repository`, `AnalysisTarget`, `test_classifier_scoring.py`, `MaestWindowContext`, `candidates.py`, `AnalysisVectorRow`, `LibraryDatabase`, `test_classifier_jobs.py`, `test_evaluation_seed_sampling.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `_add_track`, `ExactVectorSearchBackend`, `artifact_io.py`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `AnalysisTarget` connect `AnalysisTarget` to `AnalysisOutput`, `FileTags`, `db_analysis.py`, `AnalysisCandidate`, `test_api_sonara_search.py`, `sonara_features.py`, `test_api_reference_compare.py`, `classifier_scoring.py`, `db_analysis_candidates.py`, `JobStore`, `ann_index.py`, `test_api_evaluation.py`, `test_consumers.py`, `track_views.py`, `db_migration.py`, `test_evaluation_cli.py`, `SimilaritySearch`, `sonara_similarity_scoring.py`, `test_break_energy.py`, `sonara_storage.py`, `SonaraFeatureRow`, `EvaluationRepository`, `analysis_model_runners.py`, `current_embedding_spec`, `create_app`, `benchmark_search.py`, `SonaraSimilaritySearch`, `test_analysis_orchestration.py`, `analysis_models.py`, `_Repository`, `tempo_resolution.py`, `compute_transition_diagnostics`, `test_classifier_scoring.py`, `MaestWindowContext`, `candidates.py`, `AnalysisVectorRow`, `LibraryDatabase`, `test_classifier_jobs.py`, `_library_with_maest_candidate`, `test_evaluation_seed_sampling.py`, `test_reference_compare_uses_current_outputs_and_current_summaries`, `_add_track`, `ExactVectorSearchBackend`, `artifact_io.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 70 inferred relationships involving `LibraryDatabase` (e.g. with `run_source_file_search()` and `BenchmarkConfig`) actually correct?**
  _`LibraryDatabase` has 70 INFERRED edges - model-reasoned connections that need verification._
- **Are the 79 inferred relationships involving `AnalysisOutput` (e.g. with `BenchmarkConfig` and `AnalysisJobManager`) actually correct?**
  _`AnalysisOutput` has 79 INFERRED edges - model-reasoned connections that need verification._
- **Are the 74 inferred relationships involving `AnalysisTarget` (e.g. with `BenchmarkConfig` and `ClassifierScoreRecord`) actually correct?**
  _`AnalysisTarget` has 74 INFERRED edges - model-reasoned connections that need verification._
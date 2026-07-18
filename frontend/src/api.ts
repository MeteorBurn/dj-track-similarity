export type Track = {
  id: number;
  path: string;
  size: number;
  mtime: number;
  artist?: string | null;
  title?: string | null;
  album?: string | null;
  bpm?: number | null;
  musical_key?: string | null;
  energy?: number | null;
  duration?: number | null;
  liked: boolean;
  metadata?: Record<string, unknown> | null;
  genres?: string[] | null;
  genre_scores?: Record<string, number> | null;
  classifier_scores?: Record<string, {
    score: number;
    label: string;
    confidence: number;
    probabilities?: Record<string, number>;
    feature_set?: string;
    model_id?: string;
    analyzed_at?: string;
  }> | null;
  analyses?: string[] | null;
  embedding_model?: string | null;
  embedding_dim?: number | null;
};

export type SonaraFeaturePayload = {
  value?: unknown;
  type?: string;
  shape?: number[];
  size?: number;
  dtype?: string;
  summary?: Record<string, unknown>;
  storage?: string;
  length?: number;
  fields?: Record<string, SonaraFeaturePayload>;
};

export type SonaraCurves = Record<string, SonaraFeaturePayload>;

export type SearchResult = {
  position?: number;
  track: Track;
  score: number;
  score_breakdown?: Record<string, number> | null;
  reason?: string;
  sonara_groups?: Record<string, number>;
  classifier_scores?: Record<string, number>;
  transition?: {
    from_track_id?: number | null;
    bpm_delta?: number | null;
    key_relation?: string;
    confidence: number;
  };
};

export type HybridSearchSource = "mert" | "maest" | "sonara" | "clap";
export type ReferenceCompareModel = "clap" | "mert" | "muq" | "maest" | "sonara";
export type ReferenceCompareVerdict = "mood" | "palette" | "instruments" | "groove" | "genre" | "transition" | "miss";
export type ReferenceComparePayload = {
  seed_track_id: number;
  models?: ReferenceCompareModel[];
  limit?: number;
};
export type ReferenceCompareGroup = {
  model: ReferenceCompareModel;
  available: boolean;
  reason?: string | null;
  results: SearchResult[];
};
export type ReferenceCompareResponse = {
  seed_track_id: number;
  groups: ReferenceCompareGroup[];
};
export type ReferenceCompareVerdictPayload = {
  seed_track_id: number;
  candidate_track_id: number;
  model: ReferenceCompareModel;
  verdict: ReferenceCompareVerdict;
  notes?: string | null;
};
export type ReferenceCompareVerdictResult = ReferenceCompareVerdictPayload & {
  id: number;
  source: string;
  rating: number;
};
export type HybridMatchAxis = "groove" | "density" | "texture" | "mood" | "tonal" | "vocalness" | "energy_flow" | "novelty";
export type HybridClassifierSignalRole = "preference_boost" | "preference_penalty" | "risk_penalty" | "context_modifier";
export type HybridClassifierSignal = {
  role: HybridClassifierSignalRole;
  axis: HybridMatchAxis;
  label?: string | null;
  description?: string | null;
  enabled_by_default?: boolean | null;
  default_preference?: number | null;
  default_risk_weight?: number | null;
  allowed_modes?: string[] | null;
  missing_score_policy?: string | null;
};

export type HybridSearchPayload = {
  seed_track_ids: number[];
  sources?: HybridSearchSource[];
  weights?: Record<string, number> | null;
  score_profile?: EvaluationScoreProfile | Record<string, unknown> | null;
  per_source?: number;
  limit?: number;
  rrf_k?: number;
  random_seed?: number;
  transition_risk_weight?: number;
  transition_risk_version?: "v1" | "v2";
  classifier_preferences?: Record<string, number>;
  classifier_risk_weights?: Record<string, number>;
  include_diagnostics?: boolean;
  record_session?: boolean;
};

export type EvaluationPairReasonTag =
  | "good_groove"
  | "good_density"
  | "good_texture"
  | "good_mood"
  | "good_tonal"
  | "too_vocal"
  | "bad_density"
  | "bad_tonal"
  | "too_obvious"
  | "interesting_adjacent"
  | "wrong_energy"
  | "wrong_texture"
  | "bad_transition_risk";

export type EvaluationPairFeedbackState = {
  state: "rated" | "mixed";
  source: string;
  seed_track_ids: number[];
  candidate_track_id: number;
  rating: 0 | 1 | 2 | 3 | null;
  reason_tags: EvaluationPairReasonTag[];
  notes?: string | null;
  per_seed?: Array<{
    id: number;
    seed_track_id: number;
    candidate_track_id: number;
    rating: 0 | 1 | 2 | 3;
    reason_tags: EvaluationPairReasonTag[];
    notes?: string | null;
    source: string;
    updated_at?: string | null;
  }>;
};

export type HybridSearchResult = {
  track: Track;
  score: number;
  total_score: number;
  calibrated_score?: null;
  adjusted_score: number;
  transition_risk?: number | null;
  transition_risk_penalty: number;
  transition_risk_weight: number;
  raw_rrf_score: number;
  rank: number;
  score_breakdown: Record<string, { rank: number; weight: number; contribution: number; score?: number }>;
  risk_breakdown: Record<string, number | null>;
  source_support: Record<string, {
    available: boolean;
    rank?: number | null;
    score?: number | null;
    weight?: number | null;
    contribution?: number | null;
    best_seed_track_id?: number | null;
    best_rank?: number | null;
    supporting_seed_track_ids?: number[];
  }>;
  classifier_support: Record<string, {
    available: boolean;
    score?: number | null;
    preference?: number | null;
    risk_weight?: number | null;
    score_contribution?: number | null;
    risk_contribution?: number | null;
    fresh?: boolean | null;
    stale?: boolean | null;
    stored_model_id?: string | null;
    current_model_id?: string | null;
    manifest_status?: string | null;
    production_status?: string | null;
    role?: HybridClassifierSignalRole | string | null;
    axis?: HybridMatchAxis | string | null;
    label?: string | null;
    description?: string | null;
    missing_score_policy?: string | null;
    hybrid_signal_source?: string | null;
  }>;
  match_character: Record<HybridMatchAxis, number>;
  warnings: string[];
  explanation: string[];
  transition_diagnostics: Record<string, unknown>;
  diagnostics: Record<string, unknown>;
  feedback?: EvaluationPairFeedbackState | null;
};

export type HybridSearchResponse = {
  results: HybridSearchResult[];
  warnings: string[];
  weights_used: Record<string, number>;
  sources: HybridSearchSource[];
  limitations: string[];
  diagnostics: Record<string, unknown>;
  session_id?: number | null;
};

export type TrackPage = {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
};

export type GenreTagApplyResult = {
  track_id: number;
  path: string;
  tags: Record<string, string>;
  status: "applied" | "skipped" | "failed";
  message: string;
  error?: string | null;
};

export type LibrarySummary = {
  tracks: number;
  sonara: number;
  maest: number;
  mert: number;
  muq: number;
  clap: number;
  liked: number;
  classifiers: number;
};

export type AnalysisModel = "sonara" | "maest" | "mert" | "muq" | "clap";

export type SonaraSearchMode = "balanced" | "vibe" | "sound" | "dj_transition" | "custom";

export type SetBuilderSeedMode = "manual" | "auto";
export type SetBuilderMode = "similar_crate" | "weird_adjacent" | "balanced_set" | "discovery";
export type SetBuilderEnergyCurve = "warmup" | "balanced" | "peak" | "wave";
export type SetBuilderBpmMode = "general" | "low_to_high" | "high_to_low";
export type SetBuilderBpmChange = "slow" | "medium" | "fast";
export type SetBuilderClassifierFlow = "flat" | "rise" | "fall";

export type SonaraMixerWeights = {
  timbre: number;
  rhythm: number;
  dynamics: number;
  harmonic: number;
  tempo: number;
};

export type SonaraModifiers = {
  energy: number;
  valence: number;
  acousticness: number;
  brightness: number;
  rhythm_density: number;
  dynamic_range: number;
  loudness: number;
  vocalness: number;
};

export type ScanStats = {
  job_id?: string;
  state?: string;
  root?: string;
  total?: number;
  processed?: number;
  added: number;
  updated: number;
  unchanged: number;
  skipped: number;
  failed?: number;
  current_path?: string | null;
  avg_seconds_per_track?: number | null;
  events?: Array<{ timestamp: number; level: string; message: string; path?: string | null }>;
  cancel_requested?: boolean;
  workers?: number;
};

export type AnalysisJobStatus = {
  job_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "failed";
  adapter_name: string;
  embedding_key: string;
  models?: AnalysisModel[];
  classifier_keys?: string[];
  current_model?: string | null;
  model_progress?: Partial<Record<string, {
    total: number;
    processed: number;
    analyzed: number;
    failed: number;
    skipped: number;
    current_path?: string | null;
  }>>;
  model_name?: string | null;
  device?: string | null;
  device_requested: "auto" | "cpu" | "cuda";
  total: number;
  processed: number;
  analyzed: number;
  failed: number;
  skipped?: number;
  current_path?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  avg_seconds_per_track?: number | null;
  errors: Array<{ track_id: number; path: string; error: string; model?: string | null }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null; track_id?: number | null; model?: string | null }>;
  cancel_requested: boolean;
  workers: number;
  track_batch_size?: number;
  inference_batch_size?: number;
  top_k?: number;
};

export type PromotedClassifier = {
  classifier_key: string;
  name: string;
  artifact_prefix: string;
  positive_label?: string | null;
  label_order?: string[];
  model_path: string;
  metadata_path: string;
  manifest_status?: string;
  manifest_errors?: string[];
  manifest_warnings?: string[];
  is_scoring_compatible?: boolean;
  manifest_version?: number | null;
  score_semantics?: string;
  calibration_status?: string;
  production_status?: string;
  model_id?: string | null;
  artifact_hash?: string | null;
  promoted_at?: string | null;
  calibration?: Record<string, unknown>;
  has_calibrated_probability?: boolean;
  required_inputs?: string[];
  hybrid_signal?: HybridClassifierSignal | null;
  hybrid_signal_source?: string | null;
};

export type GenreTagJobStatus = {
  job_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "failed";
  total: number;
  processed: number;
  applied: number;
  skipped: number;
  failed: number;
  current_path?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  avg_seconds_per_track?: number | null;
  errors: Array<{ track_id: number; path: string; error: string }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null; track_id?: number | null }>;
  cancel_requested: boolean;
};

export type AudioDedupPreset = "safe" | "balanced" | "aggressive";

export type AudioDedupJobStatus = {
  job_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "failed";
  root: string;
  path_contains: string[];
  preset: AudioDedupPreset;
  min_score?: number | null;
  min_similarity?: number | null;
  limit_groups?: number | null;
  apply: boolean;
  total: number;
  processed: number;
  groups: number;
  safe_candidates: number;
  deleted: number;
  skipped: number;
  failed: number;
  current_path?: string | null;
  current_step?: string | null;
  json_path?: string | null;
  xlsx_path?: string | null;
  log_path?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  avg_seconds_per_item?: number | null;
  errors: Array<{ error: string }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null }>;
  cancel_requested: boolean;
};

export type AudioDedupJobPayload = {
  root: string;
  path_contains?: string[];
  preset?: AudioDedupPreset;
  min_score?: number | null;
  min_similarity?: number | null;
  limit_groups?: number | null;
  out_dir?: string | null;
  apply?: boolean;
  confirmation?: string | null;
};

export type AudioDoctorSourceMode = "db" | "folder";
export type AudioDoctorKeepId3 = "first" | "last" | "none";

export type AudioDoctorJobStatus = {
  job_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "failed";
  source_mode: AudioDoctorSourceMode;
  db_path: string;
  folder?: string | null;
  db_roots: string[];
  file_root?: string | null;
  keep_id3: AudioDoctorKeepId3;
  limit?: number | null;
  workers: number;
  reasons: string[];
  apply: boolean;
  total: number;
  processed: number;
  ok: number;
  notice: number;
  repairable: number;
  repaired: number;
  suspicious: number;
  tag_error: number;
  failed: number;
  skipped_state: number;
  skipped_reason: number;
  missing_db_files: number;
  current_path?: string | null;
  current_step?: string | null;
  json_path?: string | null;
  xlsx_path?: string | null;
  log_path?: string | null;
  state_path?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  avg_seconds_per_item?: number | null;
  errors: Array<{ error: string }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null }>;
  cancel_requested: boolean;
};

export type AudioDoctorJobPayload = {
  source_mode: AudioDoctorSourceMode;
  folder?: string | null;
  db_roots?: string[];
  file_root?: string | null;
  keep_id3?: AudioDoctorKeepId3;
  limit?: number | null;
  workers?: number;
  reasons?: string[];
  out_dir?: string | null;
  state_path?: string | null;
  apply?: boolean;
  confirmation?: string | null;
};

export type AnalysisResetResult = {
  adapter: string;
  tracks_updated: number;
  embeddings_deleted: number;
  classifier_scores_deleted?: number;
};

export type ClassifierResetResult = {
  classifiers: string[];
  scores_deleted: number;
};

export type DatabaseClearResult = {
  tracks_deleted: number;
  embeddings_deleted: number;
};

export type DatabaseSelection = {
  path: string | null;
  selected: boolean;
  music_root?: string | null;
};

export type RhythmLabLaunchResult = {
  url: string;
  already_running: boolean;
  managed?: boolean;
  pid?: number;
  source_db?: string | null;
};

export type RhythmLabStatus = {
  url: string;
  running: boolean;
  managed: boolean;
  stopped?: boolean;
};

export type ServerShutdownResult = {
  status: "shutdown_requested";
};

export type SetBuilderGeneratePayload = {
  seed_mode: SetBuilderSeedMode;
  seed_track_ids: number[];
  auto_seed_count: number;
  mode: SetBuilderMode;
  limit: number;
  diversity: number;
  energy_curve: SetBuilderEnergyCurve;
  bpm_mode: SetBuilderBpmMode;
  bpm_change: SetBuilderBpmChange;
  bpm_start?: number;
  bpm_target?: number;
  classifier_preferences?: Record<string, number>;
  classifier_flows?: Record<string, SetBuilderClassifierFlow>;
  random_seed?: number;
};

export type SetBuilderGenerateResult = {
  mode: SetBuilderMode;
  seed_mode: SetBuilderSeedMode;
  seed_track_ids: number[];
  coverage: {
    tracks: number;
    eligible_tracks: number;
    missing_mert: number;
    missing_maest: number;
    missing_clap: number;
    missing_sonara: number;
  };
  items: SearchResult[];
};

export type EvaluationSummary = {
  schema_version: number;
  counts: {
    search_sessions: number;
    search_result_events: number;
    track_pair_feedback: number;
    transition_feedback: number;
    calibration_runs: number;
  };
};

export type EvaluationPairFeedbackPayload = {
  session_id?: number | null;
  seed_track_ids: number[];
  candidate_track_id: number;
  rating: 0 | 1 | 2 | 3;
  reason_tags?: EvaluationPairReasonTag[];
  notes?: string | null;
  source?: string;
};

export type EvaluationTransitionFeedbackPayload = {
  outgoing_track_id: number;
  incoming_track_id: number;
  rating: 0 | 1 | 2 | 3;
  risk_tags?: string[];
  notes?: string | null;
  source?: string;
};

export type EvaluationScoreProfile = {
  name: string;
  profile_kind: "unsupervised_source_profile";
  weight_kind: "unsupervised_internal_profile";
  sources: string[];
  weights: Record<string, number>;
  created_at: string;
  source_report_summary: Record<string, unknown>;
  limitations: string[];
  version: number;
};

export type EvaluationSourceProfilePayload = {
  seed_track_ids?: number[] | null;
  sample_count?: number;
  sources?: string[];
  per_source?: number;
  top_k?: number[];
  random_seed?: number;
  profile_name?: string | null;
  include_profile?: boolean;
};

export type EvaluationSourceProfileResult = {
  source_profile: Record<string, unknown>;
  score_profile?: EvaluationScoreProfile | null;
};

export type EvaluationApplyScoreProfilePayload = {
  profile?: EvaluationScoreProfile | Record<string, unknown> | null;
  weights?: Record<string, number> | null;
  name?: string | null;
  k?: number[];
  rrf_k?: number;
};

export type EvaluationWeightedCandidatesPayload = {
  profile?: EvaluationScoreProfile | Record<string, unknown> | null;
  weights?: Record<string, number> | null;
  name?: string | null;
  seed_track_ids?: number[] | null;
  sample_count?: number;
  sources?: string[] | null;
  per_source?: number;
  random_seed?: number;
  rrf_k?: number;
  transition_risk_weight?: number;
  record_session?: boolean;
  limit_per_seed?: number;
};

export type EvaluationWeightedCandidateRow = {
  seed_track_id: number;
  candidate_track_id: number;
  profile_rank: number;
  profile_score: number;
  adjusted_score: number;
  raw_rrf_score: number;
  transition_risk: number | null;
  transition_risk_penalty: number;
  transition_risk_weight: number;
  rating: "";
  reason_tags: "";
  notes: "";
  source: string;
  seed_artist: string;
  seed_title: string;
  candidate_artist: string;
  candidate_title: string;
  candidate_album: string;
  candidate_bpm: string;
  candidate_musical_key: string;
  candidate_energy: string;
  source_count: number;
  sources_json: string;
  sources: Record<string, { rank: number; score: number }>;
  score_profile_name: string;
  score_profile_weights_json: string;
  score_profile_weights: Record<string, number>;
};

export type EvaluationWeightedCandidatesResult = {
  score_profile: EvaluationScoreProfile;
  seed_track_ids: number[];
  sources: string[];
  per_source: number;
  random_seed: number;
  rrf_k: number;
  transition_risk_weight: number;
  limit_per_seed: number;
  rows_total: number;
  rows_returned: number;
  rows: EvaluationWeightedCandidateRow[];
  warnings: string[];
  session_ids: number[];
  record_session: boolean;
};

export type EvaluationPairFeedbackResult = Record<string, unknown> & {
  ids: number[];
  seed_track_ids: number[];
  candidate_track_id: number;
  rating: 0 | 1 | 2 | 3;
  reason_tags: EvaluationPairReasonTag[];
  notes?: string | null;
  source: string;
  session_id?: number | null;
};

export type EvaluationTransitionFeedbackResult = Record<string, unknown> & { id: number; rating: number; source: string };

export type EvaluationLatestReports = {
  status: "ok" | "no_persisted_reports";
  summary: string;
  calibration_runs: Array<{
    id: number;
    profile_name: string;
    search_mode: string;
    config: Record<string, unknown>;
    metrics: Record<string, unknown>;
    created_at: string;
  }>;
};

export type RhythmLabCollectionSaveResult = {
  id: number;
  name: string;
  source: string;
  track_count: number;
  updated_at: string;
};

export { api } from "./apiClient";

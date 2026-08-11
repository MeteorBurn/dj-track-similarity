export type EmbeddingSource = "mert" | "maest" | "muq" | "clap";
export type AnalysisModel = "sonara" | EmbeddingSource;
export type SonaraStatusOutput = {
  output_kind: "core";
  present_count: number;
  missing_count: number;
};

export type SonaraStatus = {
  catalog_uuid: string;
  total_tracks: number;
  outputs: SonaraStatusOutput[];
};

export type AnalysisCoverage = {
  sonara_core: boolean;
  maest_analysis: boolean;
  maest_embedding: boolean;
  mert: boolean;
  muq: boolean;
  clap: boolean;
};

export type ClassifierScoreSummary = {
  classifier_key: string;
  score: number;
  predicted_class: string;
  score_bucket: "low" | "medium" | "high";
  confidence: number;
};

export type Track = {
  track_id: number;
  catalog_uuid: string;
  track_uuid: string;
  content_generation: number;
  file_path: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  tag_bpm: number | null;
  tag_key: string | null;
  audio_duration_seconds: number | null;
  liked: boolean;
  analysis_coverage: AnalysisCoverage;
  classifier_scores: ClassifierScoreSummary[];
};

export type TrackMutationIdentity = {
  catalog_uuid: string;
  track_uuid: string;
  expected_content_generation: number;
};

export type TrackIdentity = Pick<
  Track,
  "track_id" | "catalog_uuid" | "track_uuid" | "content_generation"
>;

export interface FileTechnical {
    file_size_bytes: number;
    file_modified_ns: number;
    audio_format: string | null;
    sample_rate_hz: number | null;
    channel_count: number | null;
    bit_rate_bps: number | null;
    bit_depth: number | null;
    audio_duration_seconds: number | null;
    last_scanned_at: string;
    missing_since: string | null;
}

export interface FileTags {
    title: string | null;
    artist: string | null;
    album: string | null;
    tag_bpm: number | null;
    tag_key: string | null;
    comment: string | null;
    year: number | null;
    label: string | null;
    country: string | null;
    track_number: string | null;
    genres: string[];
    tags_read_at: string;
}

export interface SonaraCore {
    detected_bpm: number | null;
    raw_bpm: number | null;
    bpm_confidence: number | null;
    onset_density_per_second: number | null;
    beat_count: number | null;
    tempo_variability: number | null;
    beat_grid_offset_seconds: number | null;
    beat_grid_stability: number | null;
    bpm_candidates: Record<string, unknown>[];
    detected_key_name: string | null;
    detected_key_camelot: string | null;
    key_confidence: number | null;
    predominant_chord: string | null;
    chord_changes_per_second: number | null;
    key_candidates: Record<string, unknown>[];
    energy_score: number | null;
    energy_level: number | null;
    danceability_score: number | null;
    valence_score: number | null;
    acousticness_score: number | null;
    dissonance_score: number | null;
    spectral_centroid_hz: number | null;
    spectral_bandwidth_hz: number | null;
    spectral_rolloff_hz: number | null;
    spectral_flatness: number | null;
    zero_crossing_rate: number | null;
    rms_mean: number | null;
    rms_max: number | null;
    integrated_loudness_lufs: number | null;
    dynamic_range_db: number | null;
    true_peak_dbtp: number | null;
    replay_gain_db: number | null;
    max_momentary_loudness_lufs: number | null;
    loudness_range_lu: number | null;
    analyzed_duration_seconds: number | null;
    intro_end_seconds: number | null;
    outro_start_seconds: number | null;
    leading_silence_seconds: number | null;
    trailing_silence_seconds: number | null;
    energy_curve_hop_seconds: number | null;
    energy_curve_sample_count: number | null;
    energy_curve_min: number | null;
    energy_curve_max: number | null;
    energy_curve_mean: number | null;
    energy_curve_stddev: number | null;
    vocal_probability: number | null;
    mood_happy_score: number | null;
    mood_aggressive_score: number | null;
    mood_relaxed_score: number | null;
    mood_sad_score: number | null;
    aggression_score: number | null;
    aggression_confidence: number | null;
    aggression_forcefulness: number | null;
    aggression_harshness: number | null;
    aggression_tension: number | null;
    aggression_rhythm: number | null;
    vector_summaries: Array<{ vector_type: string; dim: number }>;
    analyzed_at: string;
}

export interface Maest {
    syncopated_rhythm: boolean | null;
    genres: Array<{ rank: number; genre_name: string; score: number }>;
    analyzed_at: string;
}

export interface EmbeddingSummary {
    analysis_family: EmbeddingSource;
    dim: number;
    normalization: string;
    analyzed_at: string;
}

export interface ClassifierScoreDetail {
    classifier_key: string;
    score: number;
    predicted_class: string;
    score_bucket: "low" | "medium" | "high";
    confidence: number;
    probabilities: Record<string, number>;
    feature_set: string;
    feature_names: string[];
    positive_label: string;
    analyzed_at: string;
}

export type TrackSummary = Track;

export interface TrackDetail extends TrackSummary {
    file: FileTechnical;
    file_tags: FileTags | null;
    sonara_core: SonaraCore | null;
    maest: Maest | null;
    embeddings: EmbeddingSummary[];
    classifier_scores_detail: ClassifierScoreDetail[];
}

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

export type EmbeddingSearchPayload = {
  analysis_family: EmbeddingSource;
  seed_track_ids: number[];
  limit: number;
  min_similarity?: number | null;
  epsilon?: number | null;
  noise?: number;
};

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
  seed: TrackIdentity;
  candidate: TrackIdentity;
  model: ReferenceCompareModel;
  verdict: ReferenceCompareVerdict;
  notes?: string | null;
};
export type ReferenceCompareVerdictResult = {
  id: number;
  seed_track_id: number;
  candidate_track_id: number;
  model: ReferenceCompareModel;
  verdict: ReferenceCompareVerdict;
  source: string;
  rating: number;
  notes?: string | null;
};
export type TrackPage = {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
};

export type GenreTagApplyResult = {
  catalog_uuid: string;
  track_id: number;
  track_uuid: string;
  content_generation: number;
  file_path: string;
  tags: Record<string, string>;
  status: "applied" | "skipped" | "failed";
  message: string;
  error?: string | null;
};

export type LibrarySummary = {
  tracks: number;
  sonara: number;
  maest_analysis: number;
  maest_embedding: number;
  mert: number;
  muq: number;
  clap: number;
  liked: number;
  classifiers: number;
};

export type SonaraSearchMode = "balanced" | "vibe" | "sound" | "dj_transition" | "custom";

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
  aggression: number;
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
  models?: AnalysisModel[];
  classifier_keys?: string[];
  required_families?: string[];
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
  batch_size?: number;
  track_batch_size?: number;
  inference_batch_size?: number;
  sonara_batch_size?: number;
  top_k?: number;
  readiness?: Record<string, { candidates: number; ready: number; not_ready: number; selected: number }>;
  blockers?: Record<string, string[]>;
  not_ready?: number;
};

export type AnalysisPipelineStatus = {
  job_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "failed";
  order: Array<"sonara" | "ml" | "classifiers">;
  stages: Record<string, { name: string; state: string; child_job_id?: string | null; error?: string | null }>;
  current_stage?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  cancel_requested: boolean;
};

export type PromotedClassifier = {
  classifier_key: string;
  name: string;
  artifact_prefix: string;
  positive_label?: string | null;
  negative_label?: string | null;
  label_order?: string[];
  model_path: string;
  metadata_path: string;
  manifest_status?: string;
  manifest_errors?: string[];
  manifest_warnings?: string[];
  is_scoring_compatible?: boolean;
  profile_name?: string | null;
  profile_description?: string | null;
  profile_type?: string | null;
  feature_set?: string | null;
  feature_names?: string[];
  feature_count?: number | null;
  score_semantics?: string;
  calibration_status?: string;
  production_status?: string;
  artifact_hash?: string | null;
  promoted_at?: string | null;
  calibration?: Record<string, unknown>;
  trained_label_counts?: Record<string, number>;
  has_calibrated_probability?: boolean;
  required_inputs?: string[];
  scored_tracks?: number;
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

export type AnalysisResetResult = {
  core_rows_deleted: number;
  artifact_rows_deleted: number;
  classifier_rows_deleted: number;
};

export type ClassifierResetResult = AnalysisResetResult;

export type DatabaseClearResult = {
  tracks_deleted: number;
  embeddings_deleted: number;
  artifacts_deleted: number;
  evaluation_rows_deleted: number;
};

export type DatabaseSelection = {
  path: string | null;
  artifacts_path: string | null;
  evaluation_path: string | null;
  catalog_uuid: string | null;
  selected: boolean;
};

export type RhythmLabSourceBinding = {
  catalog_uuid: string;
  database_path: string;
};

export type RhythmLabStatus = {
  running: boolean;
  managed: boolean;
  url: string;
  source?: RhythmLabSourceBinding | null;
};

export type RhythmLabLaunchResult = RhythmLabStatus & {
  already_running: boolean;
  pid?: number | null;
  source: RhythmLabSourceBinding | null;
};

export type ServerShutdownResult = {
  status: "shutdown_requested";
};

export type RhythmLabCollectionSaveResult = {
  id: number;
  name: string;
  source: string;
  track_count: number;
  updated_at: string;
};

export { api } from "./apiClient";

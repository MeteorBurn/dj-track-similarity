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
  clap: number;
  liked: number;
  classifiers: number;
};

export type AnalysisModel = "sonara" | "maest" | "mert" | "clap";

export type SonaraSearchMode = "balanced" | "vibe" | "sound" | "dj_transition" | "custom";

export type SetBuilderSeedMode = "manual" | "auto";
export type SetBuilderMode = "similar_crate" | "weird_adjacent" | "balanced_set" | "discovery";
export type SetBuilderEnergyCurve = "warmup" | "balanced" | "peak" | "wave";
export type SetBuilderBpmMode = "general" | "low_to_high" | "high_to_low";
export type SetBuilderBpmChange = "slow" | "medium" | "fast";

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

export type AnalysisResetResult = {
  adapter: string;
  tracks_updated: number;
  embeddings_deleted: number;
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
  classifier_targets?: Record<string, number>;
  classifier_avoid?: Record<string, number>;
  classifier_curves?: Record<string, { start: number; end: number }>;
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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  currentDatabase: () => request<DatabaseSelection>("/api/database/current"),
  switchDatabase: (path: string) =>
    request<DatabaseSelection>("/api/database/switch", {
      method: "POST",
      body: JSON.stringify({ path })
    }),
  chooseDatabase: () =>
    request<DatabaseSelection>("/api/database/dialog", {
      method: "POST",
      body: JSON.stringify({})
    }),
  tracks: (params: { query?: string; searchMode?: "like" | "fts"; preset?: string; liked?: boolean; classifierMinScores?: Record<string, number>; limit?: number; offset?: number; includeMetadata?: boolean } = {}) => {
    const search = new URLSearchParams();
    if (params.query) search.set("q", params.query);
    if (params.searchMode) search.set("search_mode", params.searchMode);
    if (params.preset) search.set("preset", params.preset);
    if (params.liked) search.set("liked", "true");
    if (params.classifierMinScores && Object.keys(params.classifierMinScores).length) {
      search.set("classifier_min_scores", JSON.stringify(params.classifierMinScores));
    }
    if (params.limit != null) search.set("limit", String(params.limit));
    if (params.offset != null) search.set("offset", String(params.offset));
    search.set("include_metadata", params.includeMetadata ? "true" : "false");
    return request<TrackPage>(`/api/tracks?${search.toString()}`);
  },
  filteredTracks: (payload: { query?: string; searchMode?: "like" | "fts"; preset?: string; liked?: boolean; classifierMinScores?: Record<string, number> }) =>
    request<{ items: Track[]; total: number }>("/api/tracks/filtered", {
      method: "POST",
      body: JSON.stringify({
        query: payload.query || "",
        search_mode: payload.searchMode || "like",
        preset: payload.preset || "all",
        liked: payload.liked || false,
        classifier_min_scores: payload.classifierMinScores || {}
      })
    }),
  track: (trackId: number) => request<Track>(`/api/tracks/${trackId}`),
  setTrackLiked: (trackId: number, liked: boolean) =>
    request<Track>(`/api/tracks/${trackId}/liked`, {
      method: "POST",
      body: JSON.stringify({ liked })
    }),
  librarySummary: () => request<LibrarySummary>("/api/library/summary"),
  resetAnalysis: (adapter: "sonara" | "maest" | "mert" | "clap") =>
    request<AnalysisResetResult>("/api/analysis/reset", {
      method: "POST",
      body: JSON.stringify({ adapter })
    }),
  scan: (root: string, workers: number) =>
    request<ScanStats>("/api/library/scan", {
      method: "POST",
      body: JSON.stringify({ root, workers })
    }),
  refreshTags: (workers: number) =>
    request<ScanStats>("/api/library/tags/refresh", {
      method: "POST",
      body: JSON.stringify({ workers })
    }),
  clearDatabase: () =>
    request<DatabaseClearResult>("/api/database/clear", {
      method: "POST",
      body: JSON.stringify({})
    }),
  scanJob: (jobId: string) => request<ScanStats>(`/api/library/scan/jobs/${jobId}`),
  latestScanJob: () => request<ScanStats | null>("/api/library/scan/jobs/latest"),
  cancelScanJob: (jobId: string) =>
    request<ScanStats>(`/api/library/scan/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  chooseFolder: () =>
    request<{ path: string | null }>("/api/dialog/folder", {
      method: "POST",
      body: JSON.stringify({})
    }),
  launchRhythmLab: () =>
    request<RhythmLabLaunchResult>("/api/rhythm-lab/launch", {
      method: "POST",
      body: JSON.stringify({})
    }),
  stopRhythmLab: () =>
    request<RhythmLabStatus>("/api/rhythm-lab/stop", {
      method: "POST",
      body: JSON.stringify({})
    }),
  audioDedupJobStart: (payload: AudioDedupJobPayload) =>
    request<AudioDedupJobStatus>("/api/audio-dedup/jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  latestAudioDedupJob: () => request<AudioDedupJobStatus | null>("/api/audio-dedup/jobs/latest"),
  audioDedupJob: (jobId: string) => request<AudioDedupJobStatus>(`/api/audio-dedup/jobs/${jobId}`),
  cancelAudioDedupJob: (jobId: string) =>
    request<AudioDedupJobStatus>(`/api/audio-dedup/jobs/${jobId}/cancel`, {
      method: "POST"
    }),
  audioDedupXlsxUrl: (jobId: string) => `/api/audio-dedup/jobs/${encodeURIComponent(jobId)}/report/xlsx`,
  analysisJobStart: (payload: {
    models?: AnalysisModel[];
    classifier_keys?: string[];
    limit?: number | null;
    device?: "auto" | "cpu" | "cuda";
    top_k?: number;
    track_batch_size?: number;
    inference_batch_size?: number;
  } = {}) =>
    request<AnalysisJobStatus>("/api/analysis/jobs", {
      method: "POST",
      body: JSON.stringify({
        models: payload.models,
        classifier_keys: payload.classifier_keys ?? [],
        limit: payload.limit ?? null,
        device: payload.device ?? "auto",
        top_k: payload.top_k ?? 3,
        track_batch_size: payload.track_batch_size ?? 4,
        inference_batch_size: payload.inference_batch_size ?? 24
      })
    }),
  analysisJob: (jobId: string) => request<AnalysisJobStatus>(`/api/analysis/jobs/${jobId}`),
  latestAnalysisJob: () => request<AnalysisJobStatus | null>("/api/analysis/jobs/latest"),
  cancelAnalysisJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/analysis/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  analyzeClassifier: (classifier: string, limit?: number) =>
    request<AnalysisJobStatus>(`/api/classifiers/${classifier}/analyze`, {
      method: "POST",
      body: JSON.stringify({ limit: limit || null })
    }),
  resetClassifiers: (classifiers: string[]) =>
    request<ClassifierResetResult>("/api/classifiers/reset", {
      method: "POST",
      body: JSON.stringify({ classifiers })
    }),
  classifierJob: (classifier: string, jobId: string) => request<AnalysisJobStatus>(`/api/classifiers/${classifier}/analyze/jobs/${jobId}`),
  latestClassifierJob: (classifier: string) => request<AnalysisJobStatus | null>(`/api/classifiers/${classifier}/analyze/jobs/latest`),
  cancelClassifierJob: (classifier: string, jobId: string) =>
    request<AnalysisJobStatus>(`/api/classifiers/${classifier}/analyze/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  classifiers: () => request<PromotedClassifier[]>("/api/classifiers"),
  search: (payload: {
    seed_track_ids: number[];
    limit: number;
    bpm_tolerance?: number | null;
    key_compatibility?: string | null;
    energy_min?: number | null;
    energy_max?: number | null;
    min_similarity?: number | null;
    epsilon?: number | null;
    noise?: number;
  }) =>
    request<SearchResult[]>("/api/search", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  sonaraSearch: (payload: {
    seed_track_ids: number[];
    limit: number;
    mode: SonaraSearchMode;
    mixer_weights?: SonaraMixerWeights | null;
    modifiers?: SonaraModifiers | null;
    min_similarity?: number | null;
  }) =>
    request<SearchResult[]>("/api/search/sonara", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  textSearch: (payload: {
    query: string;
    positive_queries?: string[];
    negative_queries?: string[];
    adaptive_contrast?: boolean;
    preset?: string | null;
    limit: number;
    min_similarity?: number | null;
    device?: "auto" | "cpu" | "cuda";
  }) =>
    request<SearchResult[]>("/api/search/text", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  setBuilderGenerate: (payload: SetBuilderGeneratePayload) =>
    request<SetBuilderGenerateResult>("/api/set-builder/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  exportPlaylist: (name: string, track_ids: number[], output_dir: string, format: "m3u" | "csv") =>
    request<{ path: string }>("/api/export", {
      method: "POST",
      body: JSON.stringify({ name, track_ids, output_dir, format })
    }),
  genreTagJobStart: () =>
    request<GenreTagJobStatus>("/api/tags/genres/jobs", {
      method: "POST",
      body: JSON.stringify({})
    }),
  genreTagJobLatest: () => request<GenreTagJobStatus | null>("/api/tags/genres/jobs/latest"),
  genreTagJob: (jobId: string) => request<GenreTagJobStatus>(`/api/tags/genres/jobs/${jobId}`),
  cancelGenreTagJob: (jobId: string) =>
    request<GenreTagJobStatus>(`/api/tags/genres/jobs/${jobId}/cancel`, {
      method: "POST"
    })
};

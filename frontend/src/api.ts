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
  metadata?: Record<string, unknown> | null;
  genres?: string[] | null;
  genre_scores?: Record<string, number> | null;
  analyses?: string[] | null;
  embedding_model?: string | null;
  embedding_dim?: number | null;
};

export type SearchResult = {
  track: Track;
  score: number;
  score_breakdown?: Record<string, number> | null;
};

export type TrackPage = {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
};

export type TagPreview = {
  track_id: number;
  path: string;
  tags: Record<string, string>;
};

export type GenreTagApplyResult = TagPreview & {
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
  errors: Array<{ track_id: number; path: string; error: string }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null; track_id?: number | null }>;
  cancel_requested: boolean;
  workers: number;
  batch_size: number;
  top_k?: number;
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
  adapter: string;
  tracks_updated: number;
  embeddings_deleted: number;
};

export type DatabaseClearResult = {
  tracks_deleted: number;
  embeddings_deleted: number;
  playlists_deleted: number;
  playlist_tracks_deleted: number;
};

export type DatabaseSelection = {
  path: string | null;
  selected: boolean;
};

export type LibraryRelocationResult = {
  old_root: string;
  new_root: string;
  dry_run: boolean;
  tracks_matched: number;
  tracks_updated: number;
  missing_files: Array<{ track_id: number; path: string }>;
  conflicts: Array<{ track_id: number; old_path: string; new_path: string; existing_track_id: number | null }>;
  changes: Array<{ track_id: number; old_path: string; new_path: string }>;
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
  tracks: (params: { query?: string; preset?: string; limit?: number; offset?: number; includeMetadata?: boolean } = {}) => {
    const search = new URLSearchParams();
    if (params.query) search.set("q", params.query);
    if (params.preset) search.set("preset", params.preset);
    if (params.limit != null) search.set("limit", String(params.limit));
    if (params.offset != null) search.set("offset", String(params.offset));
    search.set("include_metadata", params.includeMetadata ? "true" : "false");
    return request<TrackPage>(`/api/tracks?${search.toString()}`);
  },
  track: (trackId: number) => request<Track>(`/api/tracks/${trackId}`),
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
  relocateLibrary: (old_root: string, new_root: string, apply = false) =>
    request<LibraryRelocationResult>("/api/library/relocate", {
      method: "POST",
      body: JSON.stringify({ old_root, new_root, apply })
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
  analyze: (adapter: "mert" | "clap", limit?: number, device: "auto" | "cpu" | "cuda" = "auto", batch_size = 4) =>
    request<AnalysisJobStatus>("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ adapter, limit: limit || null, device, batch_size })
    }),
  analyzeSonara: (limit?: number, batch_size = 1) =>
    request<AnalysisJobStatus>("/api/sonara/analyze", {
      method: "POST",
      body: JSON.stringify({ limit: limit || null, batch_size })
    }),
  sonaraJob: (jobId: string) => request<AnalysisJobStatus>(`/api/sonara/analyze/jobs/${jobId}`),
  latestSonaraJob: () => request<AnalysisJobStatus | null>("/api/sonara/analyze/jobs/latest"),
  cancelSonaraJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/sonara/analyze/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  analyzeJob: (jobId: string) => request<AnalysisJobStatus>(`/api/analyze/jobs/${jobId}`),
  latestAnalyzeJob: () => request<AnalysisJobStatus | null>("/api/analyze/jobs/latest"),
  cancelAnalyzeJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/analyze/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  analyzeGenres: (limit?: number, device: "auto" | "cpu" | "cuda" = "auto", top_k = 3, batch_size = 4) =>
    request<AnalysisJobStatus>("/api/genres/analyze", {
      method: "POST",
      body: JSON.stringify({ limit: limit || null, device, top_k, batch_size })
    }),
  genreJob: (jobId: string) => request<AnalysisJobStatus>(`/api/genres/analyze/jobs/${jobId}`),
  latestGenreJob: () => request<AnalysisJobStatus | null>("/api/genres/analyze/jobs/latest"),
  cancelGenreJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/genres/analyze/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  search: (payload: {
    seed_track_ids: number[];
    lookback_track_ids?: number[];
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
    lookback_track_ids?: number[];
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
  textSearch: (payload: { query: string; limit: number; min_similarity?: number | null; device?: "auto" | "cpu" | "cuda" }) =>
    request<SearchResult[]>("/api/search/text", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createPlaylist: (name: string, track_ids: number[]) =>
    request<{ id: number; name: string; track_ids: number[] }>("/api/playlists", {
      method: "POST",
      body: JSON.stringify({ name, track_ids })
    }),
  exportPlaylist: (playlist_id: number, output_dir: string, format: "m3u" | "csv") =>
    request<{ path: string }>("/api/export", {
      method: "POST",
      body: JSON.stringify({ playlist_id, output_dir, format })
    }),
  tagPreview: (track_ids: number[]) =>
    request<TagPreview[]>("/api/tags/preview", {
      method: "POST",
      body: JSON.stringify({ track_ids })
    }),
  tagApply: (track_ids: number[]) =>
    request<TagPreview[]>("/api/tags/apply", {
      method: "POST",
      body: JSON.stringify({ track_ids })
    }),
  genreTagApply: (track_ids?: number[]) =>
    request<GenreTagApplyResult[]>("/api/tags/genres/apply", {
      method: "POST",
      body: JSON.stringify(track_ids == null ? {} : { track_ids })
    }),
  genreTagJobStart: (track_ids?: number[]) =>
    request<GenreTagJobStatus>("/api/tags/genres/jobs", {
      method: "POST",
      body: JSON.stringify(track_ids == null ? {} : { track_ids })
    }),
  genreTagJobLatest: () => request<GenreTagJobStatus | null>("/api/tags/genres/jobs/latest"),
  genreTagJob: (jobId: string) => request<GenreTagJobStatus>(`/api/tags/genres/jobs/${jobId}`),
  cancelGenreTagJob: (jobId: string) =>
    request<GenreTagJobStatus>(`/api/tags/genres/jobs/${jobId}/cancel`, {
      method: "POST"
    })
};

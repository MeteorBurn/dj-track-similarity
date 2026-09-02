import type {
  AnalysisJobStatus,
  AnalysisPipelineRequest,
  AnalysisPipelineStatus,
  AnalysisModel,
  AnalysisResetResult,
  AudioDedupDeleteRequest,
  AudioDedupDeleteResult,
  AudioDedupGroupFilters,
  AudioDedupGroupPage,
  AudioDedupJobStatus,
  AudioDedupReportSummary,
  AudioDedupScanRequest,
  ClassifierResetResult,
  DatabaseClearResult,
  DatabaseOptimizationJobStatus,
  DatabaseSelection,
  DatabaseValidationJobStatus,
  EmbeddingRandomTrackPayload,
  EmbeddingSearchPayload,
  GenreTagJobStatus,
  LibrarySummary,
  PromotedClassifier,
  ReferenceComparePayload,
  ReferenceCompareResponse,
  ReferenceCompareVerdictPayload,
  ReferenceCompareVerdictResult,
  RhythmLabCollectionSaveResult,
  RhythmLabLaunchResult,
  RhythmLabStatus,
  ScanRequest,
  ScanStats,
  SearchResult,
  ServerShutdownResult,
  SonaraMixerWeights,
  SonaraModifiers,
  SonaraStatus,
  SonaraSearchMode,
  Track,
  TrackDeleteResult,
  TrackDetail,
  TrackIdentity,
  TrackPage
} from "./api";

type TrackQueryParams = {
  query?: string;
  searchMode?: "like" | "fts";
  preset?: string;
  liked?: boolean;
  classifierMinScores?: Record<string, number>;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

type FilteredTracksPayload = {
  query?: string;
  searchMode?: "like" | "fts";
  preset?: string;
  liked?: boolean;
  classifierMinScores?: Record<string, number>;
};

type SonaraSearchPayload = {
  seed_track_ids: number[];
  limit: number;
  mode: SonaraSearchMode;
  mixer_weights?: SonaraMixerWeights | null;
  modifiers?: SonaraModifiers | null;
  min_similarity?: number | null;
};

type SonaraRandomTrackPayload = {
  exclude_track_ids: number[];
};

type TextSearchPayload = {
  positive_queries: string[];
  analysis_family?: "clap" | "mulan";
  negative_queries?: string[];
  negative_weight?: number;
  limit: number;
  min_similarity?: number | null;
  device?: "auto" | "cpu" | "cuda";
  /** Each selected label's own bank, so the server can report which of them a
   * hit belongs to. The merged bank alone cannot say. */
  preset_banks?: { key: string; positive_queries: string[] }[];
};

type TextSearchWarmupPayload = {
  analysis_family: "clap" | "mulan";
  device?: "auto" | "cpu" | "cuda";
};

type TextSearchWarmupResult = {
  analysis_family: "clap" | "mulan";
  device: string;
  seconds: number;
};

type TextSearchFeedbackPayload = {
  track_uuid: string;
  preset_keys: string[];
  analysis_family: "clap" | "mulan";
  verdict: -1 | 0 | 1;
  preset_scores?: Record<string, number>;
};

type TextSearchFeedbackResult = {
  presets: number;
  verdict: number;
};

type TextSearchFeedbackLookupPayload = {
  track_uuids: string[];
  preset_keys: string[];
  analysis_family: "clap" | "mulan";
};

type TextSearchFeedbackLookupResult = {
  verdicts: Record<string, -1 | 1>;
};

export type TextPresetVerdictCounts = { relevant: number; irrelevant: number };

type TextSearchFeedbackSummaryResult = {
  presets: Record<string, Partial<Record<"clap" | "mulan", TextPresetVerdictCounts>>>;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function responseErrorMessage(text: string, fallback: string): string {
  if (!text) return fallback;
  try {
    const payload: unknown = JSON.parse(text);
    if (
      typeof payload === "object"
      && payload !== null
      && "detail" in payload
      && typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
  } catch {
    // Plain-text errors remain valid API error messages.
  }
  return text;
}

async function requestOnce<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(
      response.status,
      responseErrorMessage(text, response.statusText),
    );
  }
  return response.json() as Promise<T>;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

// A pooled connection can be closed between two polls, so the next request
// fails before it reaches the server. Reading again immediately opens a fresh
// connection instead of surfacing that as a transfer error.
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = (options?.method ?? "GET").toUpperCase();
  const retryable = method === "GET" || method === "HEAD";
  try {
    return await requestOnce<T>(path, options);
  } catch (error) {
    if (!retryable || error instanceof ApiError || isAbortError(error)) throw error;
    if (options?.signal?.aborted) throw error;
    return requestOnce<T>(path, options);
  }
}

const databaseApi = {
  currentDatabase: () => request<DatabaseSelection>("/api/database/current"),
  chooseDatabase: () =>
    request<DatabaseSelection>("/api/database/dialog", {
      method: "POST",
      body: JSON.stringify({})
    }),
  clearDatabase: () =>
    request<DatabaseClearResult>("/api/database/clear", {
      method: "POST",
      body: JSON.stringify({})
    })
};

const libraryApi = {
  deleteTrack: (track: TrackIdentity) =>
    request<TrackDeleteResult>(`/api/tracks/${track.track_id}`, {
      method: "DELETE",
      body: JSON.stringify({
        catalog_uuid: track.catalog_uuid,
        track_uuid: track.track_uuid,
      }),
    }),
  tracks: (params: TrackQueryParams = {}) => {
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
    return request<TrackPage>(`/api/tracks?${search.toString()}`, {
      signal: params.signal,
    });
  },
  filteredTracks: (payload: FilteredTracksPayload) =>
    request<Track[]>("/api/tracks/filtered", {
      method: "POST",
      body: JSON.stringify({
        query: payload.query || "",
        search_mode: payload.searchMode || "like",
        preset: payload.preset || "all",
        liked: payload.liked || false,
        classifier_min_scores: payload.classifierMinScores || {}
      })
    }),
  track: (trackId: number, options?: { signal?: AbortSignal }) =>
    request<TrackDetail>(`/api/tracks/${trackId}`, {
      signal: options?.signal,
    }),
  revealTrackFile: (trackId: number) =>
    request<{ path: string }>(`/api/tracks/${trackId}/reveal`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  setTrackLiked: (track: Track, liked: boolean) =>
    request<Track>(`/api/tracks/${track.track_id}/liked`, {
      method: "POST",
      body: JSON.stringify({
        catalog_uuid: track.catalog_uuid,
        track_uuid: track.track_uuid,
        liked,
      })
    }),
  librarySummary: () => request<LibrarySummary>("/api/library/summary"),
  scan: (payload: ScanRequest) =>
    request<ScanStats>("/api/library/scan", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  refreshTags: (workers: number) =>
    request<ScanStats>("/api/library/tags/refresh", {
      method: "POST",
      body: JSON.stringify({ workers })
    }),
  scanJob: (jobId: string) => request<ScanStats>(`/api/library/scan/jobs/${jobId}`),
  latestScanJob: () => request<ScanStats | null>("/api/library/scan/jobs/latest"),
  cancelScanJob: (jobId: string) =>
    request<ScanStats>(`/api/library/scan/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  startDatabaseOptimization: () => request<DatabaseOptimizationJobStatus>("/api/database/optimization/jobs", { method: "POST", body: JSON.stringify({}) }),
  databaseOptimizationJob: (jobId: string) => request<DatabaseOptimizationJobStatus>(`/api/database/optimization/jobs/${jobId}`),
  latestDatabaseOptimizationJob: () => request<DatabaseOptimizationJobStatus | null>("/api/database/optimization/jobs/latest"),
  startDatabaseValidation: () => request<DatabaseValidationJobStatus>("/api/database/validation/jobs", { method: "POST", body: JSON.stringify({}) }),
  databaseValidationJob: (jobId: string) => request<DatabaseValidationJobStatus>(`/api/database/validation/jobs/${jobId}`),
  latestDatabaseValidationJob: () => request<DatabaseValidationJobStatus | null>("/api/database/validation/jobs/latest"),
  cancelDatabaseValidation: (jobId: string) =>
    request<DatabaseValidationJobStatus>(`/api/database/validation/jobs/${jobId}/cancel`, {
      method: "POST"
    })
};

const shellApi = {
  chooseFolder: () =>
    request<{ path: string | null }>("/api/dialog/folder", {
      method: "POST",
      body: JSON.stringify({})
    }),
  rhythmLabStatus: () => request<RhythmLabStatus>("/api/rhythm-lab/status"),
  launchRhythmLab: () =>
    request<RhythmLabLaunchResult>("/api/rhythm-lab/launch", {
      method: "POST",
      body: JSON.stringify({})
    }),
  shutdownServer: () =>
    request<ServerShutdownResult>("/api/server/shutdown", {
      method: "POST",
      headers: { "X-DJ-Track-Similarity-Action": "shutdown-server" },
      body: JSON.stringify({})
    })
};

const analysisApi = {
  sonaraStatus: () => request<SonaraStatus>("/api/analysis/sonara/status"),
  resetAnalysis: (analysisFamily: AnalysisModel) =>
    request<AnalysisResetResult>("/api/analysis/reset", {
      method: "POST",
      body: JSON.stringify({ analysis_family: analysisFamily })
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
  analysisPipelineStart: (payload: AnalysisPipelineRequest) => request<AnalysisPipelineStatus>("/api/analysis/pipelines", { method: "POST", body: JSON.stringify(payload) }),
  analysisPipeline: (jobId: string) => request<AnalysisPipelineStatus>(`/api/analysis/pipelines/${jobId}`),
  latestAnalysisPipeline: () => request<AnalysisPipelineStatus | null>("/api/analysis/pipelines/latest"),
  cancelAnalysisPipeline: (jobId: string) => request<AnalysisPipelineStatus>(`/api/analysis/pipelines/${jobId}/cancel`, { method: "POST" }),
  resetClassifier: (classifierKey: string) =>
    request<ClassifierResetResult>("/api/classifiers/reset", {
      method: "POST",
      body: JSON.stringify({ classifier_key: classifierKey })
    }),
  classifierJob: (classifier: string, jobId: string) => request<AnalysisJobStatus>(`/api/classifiers/${classifier}/analyze/jobs/${jobId}`),
  latestClassifierJob: (classifier: string) => request<AnalysisJobStatus | null>(`/api/classifiers/${classifier}/analyze/jobs/latest`),
  cancelClassifierJob: (classifier: string, jobId: string) =>
    request<AnalysisJobStatus>(`/api/classifiers/${classifier}/analyze/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({})
    }),
  classifiers: () => request<PromotedClassifier[]>("/api/classifiers")
};

const searchApi = {
  search: (payload: EmbeddingSearchPayload, options?: { signal?: AbortSignal }) =>
    request<SearchResult[]>("/api/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  sonaraSearch: (payload: SonaraSearchPayload, options?: { signal?: AbortSignal }) =>
    request<SearchResult[]>("/api/search/sonara", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  randomSonaraTrack: (payload: SonaraRandomTrackPayload, options?: { signal?: AbortSignal }) =>
    request<Track>("/api/search/sonara/random-track", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  randomEmbeddingTrack: (payload: EmbeddingRandomTrackPayload, options?: { signal?: AbortSignal }) =>
    request<Track>("/api/search/random-track", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  textSearch: (payload: TextSearchPayload, options?: { signal?: AbortSignal }) =>
    request<SearchResult[]>("/api/search/text", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  textSearchWarmup: (payload: TextSearchWarmupPayload, options?: { signal?: AbortSignal }) =>
    request<TextSearchWarmupResult>("/api/search/text/warmup", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  textSearchFeedback: (payload: TextSearchFeedbackPayload) =>
    request<TextSearchFeedbackResult>("/api/search/text/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  textSearchFeedbackLookup: (
    payload: TextSearchFeedbackLookupPayload,
    options?: { signal?: AbortSignal },
  ) =>
    request<TextSearchFeedbackLookupResult>("/api/search/text/feedback/lookup", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  textSearchFeedbackSummary: (options?: { signal?: AbortSignal }) =>
    request<TextSearchFeedbackSummaryResult>("/api/search/text/feedback/summary", {
      signal: options?.signal,
    })
};

const referenceCompareApi = {
  referenceCompare: (payload: ReferenceComparePayload) =>
    request<ReferenceCompareResponse>("/api/reference/compare", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  referenceCompareVerdict: (payload: ReferenceCompareVerdictPayload) =>
    request<ReferenceCompareVerdictResult>("/api/reference/compare/verdict", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};

const playlistApi = {
  exportPlaylist: (name: string, track_ids: number[], output_dir: string, format: "m3u" | "csv") =>
    request<{ path: string }>("/api/export", {
      method: "POST",
      body: JSON.stringify({ name, track_ids, output_dir, format })
    }),
  saveRhythmLabCollection: (name: string, tracks: Track[], mode: "append" | "replace" = "append") =>
    request<RhythmLabCollectionSaveResult>("/api/rhythm-lab/collections", {
      method: "POST",
      body: JSON.stringify({
        name,
        tracks: tracks.map((track) => ({
          track_id: track.track_id,
          catalog_uuid: track.catalog_uuid,
          track_uuid: track.track_uuid,
        })),
        source: "main_ui_playlist",
        mode,
      })
    })
};

const tagApi = {
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

const audioDedupApi = {
  audioDedupStart: (payload: AudioDedupScanRequest) =>
    request<AudioDedupJobStatus>("/api/audio-dedup/jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  audioDedupJob: (jobId: string) => request<AudioDedupJobStatus>(`/api/audio-dedup/jobs/${jobId}`),
  latestAudioDedupJob: () => request<AudioDedupJobStatus | null>("/api/audio-dedup/jobs/latest"),
  cancelAudioDedupJob: (jobId: string) =>
    request<AudioDedupJobStatus>(`/api/audio-dedup/jobs/${jobId}/cancel`, { method: "POST" }),
  audioDedupReports: () => request<AudioDedupReportSummary[]>("/api/audio-dedup/reports"),
  audioDedupGroups: (reportId: string, filters: AudioDedupGroupFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.offset !== undefined) params.set("offset", String(filters.offset));
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    for (const value of filters.confidence ?? []) params.append("confidence", value);
    if (filters.min_fingerprint !== undefined && filters.min_fingerprint !== null) {
      params.set("min_fingerprint", String(filters.min_fingerprint));
    }
    if (filters.fake_bitrate_only) params.set("fake_bitrate_only", "true");
    if (filters.path_contains) params.set("path_contains", filters.path_contains);
    const query = params.toString();
    return request<AudioDedupGroupPage>(
      `/api/audio-dedup/reports/${encodeURIComponent(reportId)}/groups${query ? `?${query}` : ""}`
    );
  },
  audioDedupDelete: (reportId: string, payload: AudioDedupDeleteRequest) =>
    request<AudioDedupDeleteResult>(
      `/api/audio-dedup/reports/${encodeURIComponent(reportId)}/delete`,
      { method: "POST", body: JSON.stringify(payload) }
    ),
  audioDedupXlsxUrl: (reportId: string) =>
    `/api/audio-dedup/reports/${encodeURIComponent(reportId)}/xlsx`
};

export const api = {
  ...databaseApi,
  ...libraryApi,
  ...shellApi,
  ...analysisApi,
  ...searchApi,
  ...referenceCompareApi,
  ...playlistApi,
  ...tagApi,
  ...audioDedupApi
};

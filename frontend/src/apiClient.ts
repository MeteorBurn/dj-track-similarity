import type {
  AnalysisJobStatus,
  AnalysisPipelineStatus,
  AnalysisModel,
  AnalysisResetResult,
  AudioDedupJobPayload,
  AudioDedupJobStatus,
  AudioDoctorJobPayload,
  AudioDoctorJobStatus,
  ClassifierResetResult,
  DatabaseClearResult,
  DatabaseSelection,
  EmbeddingSearchPayload,
  EvaluationApplyScoreProfilePayload,
  EvaluationLatestReports,
  EvaluationPairFeedbackPayload,
  EvaluationPairFeedbackResult,
  EvaluationSourceProfilePayload,
  EvaluationSourceProfileResult,
  EvaluationSummary,
  EvaluationTransitionFeedbackPayload,
  EvaluationTransitionFeedbackResult,
  EvaluationWeightedCandidatesPayload,
  EvaluationWeightedCandidatesResult,
  GenreTagJobStatus,
  HybridSearchPayload,
  HybridSearchResponse,
  LibrarySummary,
  PromotedClassifier,
  ReferenceComparePayload,
  ReferenceCompareResponse,
  ReferenceCompareVerdictPayload,
  ReferenceCompareVerdictResult,
  RhythmLabCollectionSaveResult,
  RhythmLabLaunchResult,
  RhythmLabStopResult,
  RhythmLabStatus,
  ScanStats,
  SearchResult,
  ServerShutdownResult,
  SetBuilderGeneratePayload,
  SetBuilderGenerateResult,
  SonaraTimeline,
  SonaraMixerWeights,
  SonaraModifiers,
  SonaraOutput,
  SonaraStatus,
  SonaraSearchMode,
  Track,
  TrackDetail,
  TrackPage
} from "./api";

const DEFAULT_SONARA_OUTPUTS = ["core"] as const;

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

type AnalysisJobStartPayload = {
  models?: AnalysisModel[];
  limit?: number | null;
  device?: "auto" | "cpu" | "cuda";
  top_k?: number;
  track_batch_size?: number;
  inference_batch_size?: number;
  sonara_batch_size?: number;
  sonara_outputs?: SonaraOutput[];
};

type SonaraSearchPayload = {
  seed_track_ids: number[];
  limit: number;
  mode: SonaraSearchMode;
  mixer_weights?: SonaraMixerWeights | null;
  modifiers?: SonaraModifiers | null;
  min_similarity?: number | null;
};

type TextSearchPayload = {
  query: string;
  positive_queries?: string[];
  negative_queries?: string[];
  adaptive_contrast?: boolean;
  preset?: string | null;
  limit: number;
  min_similarity?: number | null;
  device?: "auto" | "cpu" | "cuda";
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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
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

const databaseApi = {
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
  clearDatabase: () =>
    request<DatabaseClearResult>("/api/database/clear", {
      method: "POST",
      body: JSON.stringify({})
    })
};

const libraryApi = {
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
  sonaraTimeline: (trackId: number) => request<SonaraTimeline>(`/api/tracks/${trackId}/sonara-timeline`),
  setTrackLiked: (track: Track, liked: boolean) =>
    request<Track>(`/api/tracks/${track.track_id}/liked`, {
      method: "POST",
      body: JSON.stringify({
        catalog_uuid: track.catalog_uuid,
        track_uuid: track.track_uuid,
        expected_content_generation: track.content_generation,
        liked,
      })
    }),
  librarySummary: () => request<LibrarySummary>("/api/library/summary"),
  scan: (root: string, workers: number, limit?: number) =>
    request<ScanStats>("/api/library/scan", {
      method: "POST",
      body: JSON.stringify({ root, workers, limit: limit ?? null })
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
    })
};

const shellApi = {
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
  rhythmLabStatus: () => request<RhythmLabStatus>("/api/rhythm-lab/status"),
  stopRhythmLab: () =>
    request<RhythmLabStopResult>("/api/rhythm-lab/stop", {
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

const helperToolsApi = {
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
  audioDoctorJobStart: (payload: AudioDoctorJobPayload) =>
    request<AudioDoctorJobStatus>("/api/audio-doctor/jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  latestAudioDoctorJob: () => request<AudioDoctorJobStatus | null>("/api/audio-doctor/jobs/latest"),
  audioDoctorJob: (jobId: string) => request<AudioDoctorJobStatus>(`/api/audio-doctor/jobs/${jobId}`),
  cancelAudioDoctorJob: (jobId: string) =>
    request<AudioDoctorJobStatus>(`/api/audio-doctor/jobs/${jobId}/cancel`, {
      method: "POST"
    }),
  audioDoctorXlsxUrl: (jobId: string) => `/api/audio-doctor/jobs/${encodeURIComponent(jobId)}/report/xlsx`
};

const analysisApi = {
  sonaraStatus: () => request<SonaraStatus>("/api/analysis/sonara/status"),
  resetAnalysis: (analysisFamily: AnalysisModel) =>
    request<AnalysisResetResult>("/api/analysis/reset", {
      method: "POST",
      body: JSON.stringify({ analysis_family: analysisFamily })
    }),
  analysisJobStart: (payload: AnalysisJobStartPayload = {}) => {
    const sonaraOnly = payload.models?.length === 1 && payload.models[0] === "sonara";
    const body = sonaraOnly
      ? {
          models: payload.models,
          limit: payload.limit ?? null,
          sonara_batch_size: payload.sonara_batch_size ?? 8,
          sonara_outputs: payload.sonara_outputs ?? [...DEFAULT_SONARA_OUTPUTS]
        }
      : {
          models: payload.models,
          limit: payload.limit ?? null,
          device: payload.device ?? "auto",
          top_k: payload.top_k ?? 3,
          track_batch_size: payload.track_batch_size ?? 8,
          inference_batch_size: payload.inference_batch_size ?? 16
        };
    return request<AnalysisJobStatus>("/api/analysis/jobs", {
      method: "POST",
      body: JSON.stringify(body)
    });
  },
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
  analyzeClassifiers: (classifierKeys: string[] = [], limit?: number) =>
    request<AnalysisJobStatus>("/api/classifiers/analyze", {
      method: "POST",
      body: JSON.stringify({ classifier_keys: classifierKeys, limit: limit || null })
    }),
  aggregateClassifierJob: (jobId: string) => request<AnalysisJobStatus>(`/api/classifiers/analyze/jobs/${jobId}`),
  latestAggregateClassifierJob: () => request<AnalysisJobStatus | null>("/api/classifiers/analyze/jobs/latest"),
  cancelAggregateClassifierJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/classifiers/analyze/jobs/${jobId}/cancel`, { method: "POST" }),
  analysisPipelineStart: (payload: {
    stages: Array<"sonara" | "ml" | "classifiers">;
    limit?: number | null;
    sonara: { outputs: SonaraOutput[]; batch_size: number };
    ml: { models: AnalysisModel[]; device: "auto" | "cpu" | "cuda"; top_k: number; track_batch_size: number; inference_batch_size: number };
    classifiers: { classifier_keys: string[] };
  }) => request<AnalysisPipelineStatus>("/api/analysis/pipelines", { method: "POST", body: JSON.stringify(payload) }),
  analysisPipeline: (jobId: string) => request<AnalysisPipelineStatus>(`/api/analysis/pipelines/${jobId}`),
  latestAnalysisPipeline: () => request<AnalysisPipelineStatus | null>("/api/analysis/pipelines/latest"),
  cancelAnalysisPipeline: (jobId: string) => request<AnalysisPipelineStatus>(`/api/analysis/pipelines/${jobId}/cancel`, { method: "POST" }),
  resetClassifiers: (classifierKeys: string[]) =>
    request<ClassifierResetResult>("/api/classifiers/reset", {
      method: "POST",
      body: JSON.stringify({ classifier_keys: classifierKeys })
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
  textSearch: (payload: TextSearchPayload, options?: { signal?: AbortSignal }) =>
    request<SearchResult[]>("/api/search/text", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  hybridSearch: (payload: HybridSearchPayload, options?: { signal?: AbortSignal }) =>
    request<HybridSearchResponse>("/api/search/hybrid", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  setBuilderGenerate: (payload: SetBuilderGeneratePayload, options?: { signal?: AbortSignal }) =>
    request<SetBuilderGenerateResult>("/api/set-builder/generate", {
      method: "POST",
      body: JSON.stringify(payload),
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

const evaluationApi = {
  evaluationSummary: () => request<EvaluationSummary>("/api/evaluation/summary"),
  evaluationPairFeedback: (payload: EvaluationPairFeedbackPayload) =>
    request<EvaluationPairFeedbackResult>("/api/evaluation/feedback/pair", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  evaluationTransitionFeedback: (payload: EvaluationTransitionFeedbackPayload) =>
    request<EvaluationTransitionFeedbackResult>("/api/evaluation/feedback/transition", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  evaluationSourceProfile: (payload: EvaluationSourceProfilePayload = {}) =>
    request<EvaluationSourceProfileResult>("/api/evaluation/run/source-profile", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  evaluationApplyScoreProfile: (payload: EvaluationApplyScoreProfilePayload) =>
    request<Record<string, unknown>>("/api/evaluation/run/apply-score-profile", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  evaluationWeightedCandidates: (payload: EvaluationWeightedCandidatesPayload) =>
    request<EvaluationWeightedCandidatesResult>("/api/evaluation/run/weighted-candidates", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  evaluationLatestReports: () => request<EvaluationLatestReports>("/api/evaluation/reports/latest")
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
          content_generation: track.content_generation,
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

export const api = {
  ...databaseApi,
  ...libraryApi,
  ...shellApi,
  ...helperToolsApi,
  ...analysisApi,
  ...searchApi,
  ...referenceCompareApi,
  ...evaluationApi,
  ...playlistApi,
  ...tagApi
};

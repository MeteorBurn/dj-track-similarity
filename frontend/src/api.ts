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
  embedding_model?: string | null;
  embedding_dim?: number | null;
};

export type SearchResult = {
  track: Track;
  score: number;
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
  model_name?: string | null;
  device?: string | null;
  device_requested: "auto" | "cpu" | "cuda";
  total: number;
  processed: number;
  analyzed: number;
  failed: number;
  current_path?: string | null;
  started_at?: number | null;
  finished_at?: number | null;
  avg_seconds_per_track?: number | null;
  errors: Array<{ track_id: number; path: string; error: string }>;
  events: Array<{ timestamp: number; level: string; message: string; path?: string | null; track_id?: number | null }>;
  cancel_requested: boolean;
  workers: number;
  batch_size: number;
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
  tracks: () => request<Track[]>("/api/tracks"),
  scan: (root: string, workers: number) =>
    request<ScanStats>("/api/library/scan", {
      method: "POST",
      body: JSON.stringify({ root, workers })
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
  analyze: (adapter: "mert" | "fake", limit?: number, device: "auto" | "cpu" | "cuda" = "auto", batch_size = 4) =>
    request<AnalysisJobStatus>("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ adapter, limit: limit || null, device, batch_size })
    }),
  analyzeJob: (jobId: string) => request<AnalysisJobStatus>(`/api/analyze/jobs/${jobId}`),
  latestAnalyzeJob: () => request<AnalysisJobStatus | null>("/api/analyze/jobs/latest"),
  cancelAnalyzeJob: (jobId: string) =>
    request<AnalysisJobStatus>(`/api/analyze/jobs/${jobId}/cancel`, {
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
    request<Array<{ track_id: number; path: string; tags: Record<string, string> }>>("/api/tags/preview", {
      method: "POST",
      body: JSON.stringify({ track_ids })
    }),
  tagApply: (track_ids: number[]) =>
    request<Array<{ track_id: number; path: string; tags: Record<string, string> }>>("/api/tags/apply", {
      method: "POST",
      body: JSON.stringify({ track_ids })
    })
};

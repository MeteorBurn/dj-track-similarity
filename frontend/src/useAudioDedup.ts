import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { ApiError } from "./apiClient";
import type {
  AudioDedupDeleteResult,
  AudioDedupDeletionMode,
  AudioDedupGroupPage,
  AudioDedupJobStatus,
  AudioDedupReportSummary,
  AudioDedupScanRequest
} from "./api";
import {
  buildDeleteRequest,
  reconcileReportId,
  setGroupSelection,
  suggestedGroupSelection,
  toggleFileSelection
} from "./audioDedupView";
import type { DedupSelection } from "./audioDedupView";

const jobPollIntervalMs = 1200;
const activeJobStates = ["queued", "running"];
const groupPageSize = 25;

export type AudioDedupFilters = {
  confidence: string[];
  minFingerprint: number | null;
  fakeBitrateOnly: boolean;
  pathContains: string;
};

export const emptyAudioDedupFilters: AudioDedupFilters = {
  confidence: [],
  minFingerprint: null,
  fakeBitrateOnly: false,
  pathContains: ""
};

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function isMissingReport(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

export function useAudioDedup({ open }: { open: boolean }) {
  const [job, setJob] = useState<AudioDedupJobStatus | null>(null);
  const [reports, setReports] = useState<AudioDedupReportSummary[]>([]);
  const [reportId, setReportId] = useState<string | null>(null);
  const [page, setPage] = useState<AudioDedupGroupPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<AudioDedupFilters>(emptyAudioDedupFilters);
  const [selection, setSelection] = useState<DedupSelection>({});
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const groupRequestRef = useRef(0);
  const reportIdRef = useRef<string | null>(null);

  /**
   * Move the review to another report, or to none at all.
   *
   * A report is a file on disk that can be deleted between two visits to this
   * dialog, so a selection outlives what it points at. Switching starts a fresh
   * review and abandons the page still in flight for the previous report:
   * otherwise its "unknown report" answer lands as an error over a picker that
   * has already moved on.
   */
  const selectReportId = useCallback((next: string | null) => {
    if (reportIdRef.current === next) return;
    reportIdRef.current = next;
    groupRequestRef.current += 1;
    setReportId(next);
    setOffset(0);
    setSelection({});
    setLoadingGroups(false);
    setError(null);
  }, []);

  const refreshReports = useCallback(async () => {
    try {
      const listing = await api.audioDedupReports();
      setReports(listing);
      selectReportId(reconcileReportId(listing, reportIdRef.current));
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [selectReportId]);

  useEffect(() => {
    if (!open) return;
    void refreshReports();
    void api
      .latestAudioDedupJob()
      .then((latest) => setJob(latest))
      .catch(() => undefined);
  }, [open, refreshReports]);

  useEffect(() => {
    if (!job || !activeJobStates.includes(job.state)) return;
    const timer = window.setInterval(() => {
      void api
        .audioDedupJob(job.job_id)
        .then((next) => {
          setJob(next);
          if (next.state === "completed") {
            void refreshReports();
            if (next.report_id) selectReportId(next.report_id);
          }
        })
        .catch((cause) => setError(errorText(cause)));
    }, jobPollIntervalMs);
    return () => window.clearInterval(timer);
  }, [job, refreshReports, selectReportId]);

  const loadGroups = useCallback(
    async (targetReportId: string, targetOffset: number, targetFilters: AudioDedupFilters) => {
      const token = groupRequestRef.current + 1;
      groupRequestRef.current = token;
      setLoadingGroups(true);
      try {
        const next = await api.audioDedupGroups(targetReportId, {
          offset: targetOffset,
          limit: groupPageSize,
          confidence: targetFilters.confidence,
          min_fingerprint: targetFilters.minFingerprint,
          fake_bitrate_only: targetFilters.fakeBitrateOnly,
          path_contains: targetFilters.pathContains
        });
        if (groupRequestRef.current !== token) return;
        setPage(next);
        setError(null);
      } catch (cause) {
        if (groupRequestRef.current !== token) return;
        // The report was deleted since it was listed. Re-reading the listing
        // drops it from the picker, which is the state to show instead of an
        // error about an id nobody can choose any more.
        if (isMissingReport(cause)) void refreshReports();
        else setError(errorText(cause));
      } finally {
        if (groupRequestRef.current === token) setLoadingGroups(false);
      }
    },
    [refreshReports]
  );

  useEffect(() => {
    if (!open || !reportId) {
      setPage(null);
      return;
    }
    void loadGroups(reportId, offset, filters);
  }, [open, reportId, offset, filters, loadGroups]);

  const startScan = useCallback(async (request: AudioDedupScanRequest) => {
    setBusy(true);
    setError(null);
    try {
      setJob(await api.audioDedupStart(request));
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }, []);

  const cancelScan = useCallback(async () => {
    if (!job) return;
    try {
      setJob(await api.cancelAudioDedupJob(job.job_id));
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [job]);

  const applyFilters = useCallback((next: AudioDedupFilters) => {
    setFilters(next);
    setOffset(0);
  }, []);

  const toggleFile = useCallback((groupId: number, trackId: number) => {
    setSelection((current) => toggleFileSelection(current, groupId, trackId));
  }, []);

  const setGroup = useCallback((groupId: number, trackIds: number[]) => {
    setSelection((current) => setGroupSelection(current, groupId, trackIds));
  }, []);

  const selectSuggestedOnPage = useCallback(() => {
    setSelection((current) => {
      let next = current;
      for (const group of page?.groups ?? []) {
        next = setGroupSelection(next, group.group_id, suggestedGroupSelection(group));
      }
      return next;
    });
  }, [page]);

  const clearSelection = useCallback(() => setSelection({}), []);

  const deleteSelected = useCallback(
    async (deletionMode: AudioDedupDeletionMode): Promise<AudioDedupDeleteResult | null> => {
      if (!reportId) return null;
      const built = buildDeleteRequest(page?.groups ?? [], selection, deletionMode);
      if (!built.ok) {
        setError(built.error);
        return null;
      }
      setBusy(true);
      setError(null);
      try {
        const result = await api.audioDedupDelete(reportId, built.payload);
        setSelection({});
        await loadGroups(reportId, offset, filters);
        return result;
      } catch (cause) {
        setError(errorText(cause));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [filters, loadGroups, offset, page, reportId, selection]
  );

  const scanRunning = useMemo(
    () => Boolean(job && activeJobStates.includes(job.state)),
    [job]
  );

  return {
    job,
    scanRunning,
    reports,
    reportId,
    page,
    offset,
    pageSize: groupPageSize,
    filters,
    selection,
    loadingGroups,
    busy,
    error,
    setError,
    startScan,
    cancelScan,
    refreshReports,
    selectReport: selectReportId,
    applyFilters,
    setOffset,
    toggleFile,
    setGroup,
    selectSuggestedOnPage,
    clearSelection,
    deleteSelected
  };
}

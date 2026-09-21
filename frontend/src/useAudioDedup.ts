import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { ApiError } from "./apiClient";
import { errorText } from "./errors";
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
  invertPageSelection,
  reconcileReportId,
  selectFolderOnPage,
  setGroupSelection,
  suggestedGroupSelection,
  toggleFileSelection
} from "./audioDedupView";
import type { DedupSelection } from "./audioDedupView";

const groupPageSize = 100;

export type AudioDedupFilters = {
  confidence: string[];
  minFingerprint: number | null;
  pathContains: string;
};

export const emptyAudioDedupFilters: AudioDedupFilters = {
  confidence: [],
  minFingerprint: null,
  pathContains: ""
};

/**
 * The boundary a group page is read with.
 *
 * The report's own boundary is the one its search mode qualified groups by, so
 * it holds everywhere except in manual review: that filter exists to go through
 * what the tool would not decide alone, and there a reviewer may dig with a
 * boundary of their own.
 */
export function effectiveFingerprintFloor(
  filters: AudioDedupFilters,
  reportFloor: number | null
): number | null {
  if (filters.confidence.includes("review") && filters.minFingerprint !== null) {
    return filters.minFingerprint;
  }
  return reportFloor;
}

function isMissingReport(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

/**
 * The review half of Audio Dedup: reports, paging, filters and selection.
 *
 * The scan job itself is owned by `useJobState`, like every other long stage,
 * so it survives a closed dialog and reaches the top bar and the unified log.
 * This hook only reads the job it is handed and hands back the one it starts.
 */
export function useAudioDedup({
  open,
  databaseIdentity,
  job,
  setJob
}: {
  open: boolean;
  databaseIdentity: string | null;
  job: AudioDedupJobStatus | null;
  setJob: (job: AudioDedupJobStatus) => void;
}) {
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
  const handledJobIdRef = useRef<string | null>(null);

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

  /**
   * Another library means other track ids, so nothing of the review survives a
   * database switch: the marked copies, the page they were marked on and the
   * report they came from all belong to the database that was open when they
   * were read. Drop them before the effect below re-reads the listing, so it
   * reconciles from a clean slate instead of keeping the previous report.
   */
  useEffect(() => {
    selectReportId(null);
  }, [databaseIdentity, selectReportId]);

  useEffect(() => {
    // A closed dialog has nothing to show a report on, and jumping there would
    // move the picker and reload the listing behind the user's back. Re-opening
    // re-reads the listing and catches up with whatever the scan produced.
    if (!open) return;
    void refreshReports();
    // A scan that finished while the dialog was closed still owes the user the
    // report it produced, and only a completed scan carries a report id. Doing
    // it once per scan is what lets a deliberately chosen older report survive
    // a close and a re-open: an unconditional jump would reselect on every open
    // and take the reviewer's marked copies with it.
    if (!job?.report_id || handledJobIdRef.current === job.job_id) return;
    handledJobIdRef.current = job.job_id;
    selectReportId(job.report_id);
  }, [databaseIdentity, job?.job_id, job?.report_id, open, refreshReports, selectReportId]);

  /**
   * The fingerprint boundary the review filters by.
   *
   * Each search mode has its own: the SONARA scan clusters above 0.30, the
   * candidate modes review above 0.45. The report carries the one its run used,
   * so the review reads it off the report instead of asking for a number that
   * only means something next to the mode that produced it.
   */
  const fingerprintFloor = useMemo(
    () => reports.find((report) => report.report_id === reportId)?.fingerprint_min_similarity ?? null,
    [reportId, reports]
  );

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
          min_fingerprint: effectiveFingerprintFloor(targetFilters, fingerprintFloor),
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
    [fingerprintFloor, refreshReports]
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
  }, [setJob]);

  const cancelScan = useCallback(async () => {
    if (!job) return;
    try {
      setJob(await api.cancelAudioDedupJob(job.job_id));
    } catch (cause) {
      setError(errorText(cause));
    }
  }, [job, setJob]);

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

  const invertSelectionOnPage = useCallback(() => {
    setSelection((current) => invertPageSelection(page?.groups ?? [], current));
  }, [page]);

  const markFolderOnPage = useCallback((path: string) => {
    setSelection((current) => selectFolderOnPage(page?.groups ?? [], current, path));
  }, [page]);

  const deleteSelected = useCallback(
    async (deletionMode: AudioDedupDeletionMode): Promise<AudioDedupDeleteResult | null> => {
      if (!reportId) return null;
      // The applied filter, not the draft in the field: it is the one the page
      // on screen was read under, and the server re-checks the request against it.
      const built = buildDeleteRequest(
        page?.groups ?? [],
        selection,
        deletionMode,
        filters.pathContains
      );
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

  /**
   * Delete the report currently under review.
   *
   * Only the report files go: the copies they describe stay on disk. The
   * refreshed listing decides what to review next, because reconcileReportId
   * falls back to the newest report once the current one is gone.
   */
  const deleteReport = useCallback(async (): Promise<boolean> => {
    if (!reportId) return false;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAudioDedupReport(reportId);
      await refreshReports();
      return true;
    } catch (cause) {
      setError(errorText(cause));
      return false;
    } finally {
      setBusy(false);
    }
  }, [refreshReports, reportId]);

  return {
    reports,
    reportId,
    page,
    offset,
    pageSize: groupPageSize,
    filters,
    fingerprintFloor,
    selection,
    loadingGroups,
    busy,
    error,
    startScan,
    cancelScan,
    selectReport: selectReportId,
    deleteReport,
    applyFilters,
    setOffset,
    toggleFile,
    setGroup,
    selectSuggestedOnPage,
    invertSelectionOnPage,
    markFolderOnPage,
    clearSelection,
    deleteSelected
  };
}

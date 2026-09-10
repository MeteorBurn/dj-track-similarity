import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type {
  ReferenceCompareGroup,
  ReferenceCompareModel,
  ReferenceCompareResponse,
  ReferenceCompareVerdict,
  SearchResult,
  TrackIdentity,
  TrackSummary,
} from "./api";
import { ResultRow } from "./TrackRows";
import { seedEmbeddingFamilyPresentation } from "./searchSurfaceState";
import { displayTrack } from "./trackDisplay";
import type { useActivityLog } from "./useActivityLog";
import { errorText } from "./errors";

type ReferenceComparePanelProps = {
  seedTracks: TrackSummary[];
  onActivity?: ReturnType<typeof useActivityLog>["appendActivity"];
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  previewTrackId: number | null;
  onSeed: (track: TrackSummary) => void;
  onToggleLiked: (track: TrackSummary) => void;
  onTogglePlaylist: (track: TrackSummary) => void;
  onPreview: (track: TrackSummary) => void;
  onSeekPreview: (track: TrackSummary, seconds: number) => void;
  onDetails: (track: TrackSummary) => void;
};

const referenceCompareModels: ReferenceCompareModel[] = ["sonara", "maest", "mert", "clap", "muq", "mulan"];
const referenceCompareTimeoutMs = 120_000;
const verdictTimeoutMs = 30_000;

type PendingLabRequest = {
  controller: AbortController;
  deadline: ReturnType<typeof setTimeout> | null;
  startedAt: number;
};

const referenceCompareVerdictOptions: Array<{ value: ReferenceCompareVerdict; label: string; hint: string }> = [
  { value: "mood", label: "Mood", hint: "Similar atmosphere and emotion." },
  { value: "palette", label: "Palette", hint: "Similar timbre and sound texture." },
  { value: "instruments", label: "Instruments", hint: "Similar instruments and sound sources." },
  { value: "groove", label: "Groove", hint: "Similar rhythmic feel." },
  { value: "transition", label: "Transition", hint: "Works next to the reference in a set." },
  { value: "miss", label: "Miss", hint: "Does not fit the reference." },
];

export function ReferenceComparePanel({
  seedTracks,
  onActivity,
  busy,
  seedSet,
  playlistSet,
  playingTrackId,
  previewTrackId,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onSeekPreview,
  onDetails,
}: ReferenceComparePanelProps) {
  const [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [compare, setCompare] = useState<ReferenceCompareResponse | null>(null);
  const [savedVerdicts, setSavedVerdicts] = useState<Record<string, ReferenceCompareVerdict>>({});
  const [verdictErrors, setVerdictErrors] = useState<Record<string, string>>({});
  const [savingVerdicts, setSavingVerdicts] = useState<Record<string, boolean>>({});
  const latestCompareRequestRef = useRef(0);
  const compareRequestRef = useRef<PendingLabRequest | null>(null);
  const verdictRequestsRef = useRef<Record<string, PendingLabRequest>>({});
  const referenceTrack = seedTracks[0] ?? null;
  const referenceIdentity = referenceTrackIdentityKey(referenceTrack);
  const activeReferenceIdentityRef = useRef(referenceIdentity);
  const canCompare = Boolean(referenceTrack) && !busy && !loading;

  useEffect(() => {
    activeReferenceIdentityRef.current = referenceIdentity;
    latestCompareRequestRef.current += 1;
    setCompare(null);
    setSavedVerdicts({});
    setVerdictErrors({});
    setSavingVerdicts({});
    setError("");
    setStatus("");
    setElapsedSeconds(0);
    setLoading(false);
    return () => {
      latestCompareRequestRef.current += 1;
      const request = compareRequestRef.current;
      compareRequestRef.current = null;
      if (request) {
        abortLabRequest(request);
        onActivity?.("info", "LAB comparison dismissed", "Stopped waiting after the reference changed or LAB closed.");
      }
      abortVerdictRequests();
    };
  }, [referenceIdentity]);

  useEffect(() => {
    if (!loading) return;
    const interval = setInterval(() => {
      const request = compareRequestRef.current;
      if (request) setElapsedSeconds(Math.floor((Date.now() - request.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [loading]);

  function abortVerdictRequests() {
    const requests = verdictRequestsRef.current;
    verdictRequestsRef.current = {};
    Object.values(requests).forEach(abortLabRequest);
  }

  function cancelReferenceCompare(reason: "cancel" | "timeout", request = compareRequestRef.current) {
    if (!request || compareRequestRef.current !== request) return;
    latestCompareRequestRef.current += 1;
    compareRequestRef.current = null;
    abortLabRequest(request);
    setLoading(false);
    const message = reason === "timeout"
      ? "Timed out waiting for comparison results. Try again."
      : "Stopped waiting for comparison results.";
    setError(reason === "timeout" ? message : "");
    setStatus(reason === "cancel" ? message : "");
    onActivity?.(reason === "timeout" ? "error" : "info", "LAB comparison wait ended", message);
  }

  async function runReferenceCompare() {
    if (!referenceTrack || busy || compareRequestRef.current) return;
    const requestId = latestCompareRequestRef.current + 1;
    latestCompareRequestRef.current = requestId;
    const requestedIdentity = referenceIdentity;
    const requestedTrackId = referenceTrack.track_id;
    const request: PendingLabRequest = { controller: new AbortController(), deadline: null, startedAt: Date.now() };
    compareRequestRef.current = request;
    request.deadline = setTimeout(() => cancelReferenceCompare("timeout", request), referenceCompareTimeoutMs);
    const isCurrent = () => compareRequestRef.current === request && referenceCompareRequestIsCurrent(
      requestId,
      latestCompareRequestRef.current,
      requestedIdentity,
      activeReferenceIdentityRef.current,
    );
    abortVerdictRequests();
    setLoading(true);
    setElapsedSeconds(0);
    setStatus("Waiting for model results.");
    setError("");
    setCompare(null);
    setSavedVerdicts({});
    setSavingVerdicts({});
    setVerdictErrors({});
    onActivity?.("info", "LAB comparison started", `${displayTrack(referenceTrack)}; ${normalizeLimit(limit)} candidates per model.`);
    try {
      const response = await api.referenceCompare({
        seed_track_id: requestedTrackId,
        models: referenceCompareModels,
        limit: normalizeLimit(limit),
      }, {
        signal: request.controller.signal,
      });
      if (!isCurrent()) return;
      if (!referenceCompareResponseIsCurrent(
        requestId,
        latestCompareRequestRef.current,
        requestedIdentity,
        activeReferenceIdentityRef.current,
        requestedTrackId,
        response.seed_track_id,
      )) throw new Error("The comparison returned a different reference. Try again.");
      const restoredVerdicts: Record<string, ReferenceCompareVerdict> = {};
      for (const group of response.groups) {
        for (const result of group.results) {
          if (result.saved_verdict) {
            restoredVerdicts[verdictKey(group.model, result.track)] = result.saved_verdict;
          }
        }
      }
      setCompare(response);
      setSavedVerdicts(restoredVerdicts);
      const availableGroups = response.groups.filter((group) => group.available);
      const candidateCount = availableGroups.reduce((total, group) => total + group.results.length, 0);
      const outcome = `${candidateCount} candidates from ${availableGroups.length} models.`;
      setStatus(outcome);
      onActivity?.("ok", "LAB comparison completed", `${outcome} ${((Date.now() - request.startedAt) / 1000).toFixed(1)} s.`);
    } catch (caught) {
      if (!isCurrent()) return;
      const message = errorText(caught);
      setError(message);
      setStatus("");
      onActivity?.("error", "LAB comparison failed", message);
    } finally {
      clearLabDeadline(request);
      if (isCurrent()) {
        compareRequestRef.current = null;
        setLoading(false);
      }
    }
  }

  async function saveVerdict(group: ReferenceCompareGroup, result: SearchResult, verdict: ReferenceCompareVerdict) {
    if (!referenceTrack || busy || compareRequestRef.current) return;
    const key = verdictKey(group.model, result.track);
    if (verdictRequestsRef.current[key]) return;
    const comparisonId = latestCompareRequestRef.current;
    const requestedIdentity = referenceIdentity;
    const request: PendingLabRequest = { controller: new AbortController(), deadline: null, startedAt: Date.now() };
    verdictRequestsRef.current[key] = request;
    const isCurrent = () => verdictRequestsRef.current[key] === request
      && comparisonId === latestCompareRequestRef.current
      && requestedIdentity === activeReferenceIdentityRef.current;
    request.deadline = setTimeout(() => {
      if (!isCurrent()) return;
      delete verdictRequestsRef.current[key];
      abortLabRequest(request);
      const message = "Timed out waiting for save confirmation.";
      setVerdictErrors((current) => ({ ...current, [key]: message }));
      setSavingVerdicts((current) => ({ ...current, [key]: false }));
      onActivity?.("error", "LAB verdict save unconfirmed", `${displayTrack(result.track)}: ${message}`);
    }, verdictTimeoutMs);
    setVerdictErrors((current) => ({ ...current, [key]: "" }));
    setSavingVerdicts((current) => ({ ...current, [key]: true }));
    try {
      await api.referenceCompareVerdict({
        seed: trackIdentityPayload(referenceTrack),
        candidate: trackIdentityPayload(result.track),
        model: group.model,
        verdict,
      }, {
        signal: request.controller.signal,
      });
      if (!isCurrent()) return;
      setSavedVerdicts((current) => ({ ...current, [key]: verdict }));
    } catch (caught) {
      if (!isCurrent()) return;
      const message = errorText(caught);
      setVerdictErrors((current) => ({ ...current, [key]: `Save not confirmed: ${message}` }));
      onActivity?.("error", "LAB verdict save unconfirmed", `${displayTrack(result.track)}: ${message}`);
    } finally {
      clearLabDeadline(request);
      if (isCurrent()) {
        delete verdictRequestsRef.current[key];
        setSavingVerdicts((current) => ({ ...current, [key]: false }));
      }
    }
  }

  const groups = compare ? orderedReferenceCompareGroups(compare) : [];

  return (
    <div className="reference-compare-panel">
      <div className="reference-compare-header">
        <div className="reference-compare-heading">
          <strong>Model Listening Lab</strong>
          <span title={referenceTrack ? displayTrack(referenceTrack) : undefined}>
            {referenceTrack ? `Reference: ${displayTrack(referenceTrack)}` : "Select a seed track to compare models."}
          </span>
        </div>
        <div className="reference-compare-controls">
          <label title="Candidates per model.">
            Limit
            <input
              type="number"
              min={1}
              max={100}
              value={limit}
              disabled={loading}
              onChange={(event) => setLimit(Number(event.target.value))}
              onBlur={() => setLimit(normalizeLimit(limit))}
            />
          </label>
          <button
            className="reference-compare-run-button"
            title="Find candidates for the first seed track."
            type="button"
            disabled={!canCompare}
            onClick={() => void runReferenceCompare()}
          >
            <Search size={16} />
            {loading ? "Comparing…" : "Compare models"}
          </button>
          {loading ? (
            <button
              className="reference-compare-cancel-button"
              title="Stop waiting for these results. Server work may continue."
              type="button"
              onClick={() => cancelReferenceCompare("cancel")}
            >
              <X size={14} />
              Cancel
            </button>
          ) : null}
        </div>
      </div>
      <span className="reference-compare-hint">Uses the first seed. Scores are model-specific. Choose one verdict per candidate.</span>
      {status ? (
        <div className="reference-compare-status">
          <span role="status">{status}</span>
          {loading ? <span aria-hidden="true">{elapsedSeconds} s</span> : null}
        </div>
      ) : null}
      {error ? <span className="reference-compare-error" role="alert">{error}</span> : null}
      {compare ? (
        <div className="reference-compare-grid" aria-label="Reference compare model groups">
          {groups.map((group) => (
            <ReferenceCompareGroupCard
              key={group.model}
              group={group}
              savedVerdicts={savedVerdicts}
              verdictErrors={verdictErrors}
              savingVerdicts={savingVerdicts}
              busy={busy}
              seedSet={seedSet}
              playlistSet={playlistSet}
              playingTrackId={playingTrackId}
              previewTrackId={previewTrackId}
              onSeed={onSeed}
              onToggleLiked={onToggleLiked}
              onTogglePlaylist={onTogglePlaylist}
              onPreview={onPreview}
              onSeekPreview={onSeekPreview}
              onDetails={onDetails}
              onVerdict={(result, verdict) => void saveVerdict(group, result, verdict)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ReferenceCompareGroupCard({
  group,
  savedVerdicts,
  verdictErrors,
  savingVerdicts,
  busy,
  seedSet,
  playlistSet,
  playingTrackId,
  previewTrackId,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onSeekPreview,
  onDetails,
  onVerdict,
}: {
  group: ReferenceCompareGroup;
  savedVerdicts: Record<string, ReferenceCompareVerdict>;
  verdictErrors: Record<string, string>;
  savingVerdicts: Record<string, boolean>;
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  previewTrackId: number | null;
  onSeed: (track: TrackSummary) => void;
  onToggleLiked: (track: TrackSummary) => void;
  onTogglePlaylist: (track: TrackSummary) => void;
  onPreview: (track: TrackSummary) => void;
  onSeekPreview: (track: TrackSummary, seconds: number) => void;
  onDetails: (track: TrackSummary) => void;
  onVerdict: (result: SearchResult, verdict: ReferenceCompareVerdict) => void;
}) {
  const modelLabel = referenceCompareModelLabel(group.model);
  return (
    <section className={`reference-compare-group ${group.available ? "" : "missing"}`}>
      <div className="reference-compare-group-title">
        <strong>{modelLabel}</strong>
        <span className="reference-compare-count">{group.available ? `${group.results.length} candidates` : "Unavailable"}</span>
      </div>
      {!group.available ? <span className="reference-compare-empty">{group.reason || "No results available for this model."}</span> : null}
      {group.results.map((result) => {
        const key = verdictKey(group.model, result.track);
        const saving = savingVerdicts[key] === true;
        return (
          <div className="reference-compare-result" key={trackIdentityKey(result.track)}>
            <ResultRow
              track={result.track}
              score={result.score}
              scoreBreakdown={result.score_breakdown}
              playingTrackId={playingTrackId}
              previewTrackId={previewTrackId}
              isSeed={seedSet.has(result.track.track_id)}
              inPlaylist={playlistSet.has(result.track.track_id)}
              onSeed={onSeed}
              onToggleLiked={onToggleLiked}
              onTogglePlaylist={onTogglePlaylist}
              onPreview={onPreview}
              onSeekPreview={onSeekPreview}
              onDetails={onDetails}
            />
            <div
              className="reference-compare-verdicts"
              role="group"
              aria-busy={saving}
              aria-label={`Listening verdict for ${displayTrack(result.track)} via ${modelLabel}`}
            >
              {referenceCompareVerdictOptions.map((option) => {
                const active = savedVerdicts[key] === option.value;
                return (
                  <button
                    className={`reference-compare-verdict-button ${active ? "active" : ""}`}
                    key={option.value}
                    type="button"
                    aria-pressed={active}
                    disabled={saving || busy}
                    title={option.hint}
                    onClick={() => onVerdict(result, option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
            {saving || savedVerdicts[key] ? (
              <span className="reference-compare-save-status" role="status">{saving ? "Saving…" : "Saved"}</span>
            ) : null}
            {verdictErrors[key] ? <span className="reference-compare-error" role="alert">{verdictErrors[key]}</span> : null}
          </div>
        );
      })}
      {group.available && group.results.length === 0 ? (
        <span className="reference-compare-empty">No candidates for this model.</span>
      ) : null}
    </section>
  );
}

export function orderedReferenceCompareGroups(response: ReferenceCompareResponse): ReferenceCompareGroup[] {
  const returnedGroups = new Map(response.groups.map((group) => [group.model, group]));
  return referenceCompareModels.map((model) => returnedGroups.get(model) ?? {
    model,
    available: false,
    reason: `The backend did not return ${referenceCompareModelLabel(model)} availability for this request.`,
    results: [],
  });
}

export function referenceTrackIdentityKey(track: TrackSummary | null) {
  return track ? trackIdentityKey(track) : "none";
}

export function referenceCompareRequestIsCurrent(
  requestId: number,
  latestRequestId: number,
  requestedIdentity: string,
  activeIdentity: string,
) {
  return requestId === latestRequestId && requestedIdentity === activeIdentity;
}

export function referenceCompareResponseIsCurrent(
  requestId: number,
  latestRequestId: number,
  requestedIdentity: string,
  activeIdentity: string,
  requestedTrackId: number,
  responseTrackId: number,
) {
  return referenceCompareRequestIsCurrent(requestId, latestRequestId, requestedIdentity, activeIdentity)
    && requestedTrackId === responseTrackId;
}

function trackIdentityPayload(track: TrackSummary): TrackIdentity {
  return {
    track_id: track.track_id,
    catalog_uuid: track.catalog_uuid,
    track_uuid: track.track_uuid,
  };
}

function trackIdentityKey(track: TrackSummary) {
  return `${track.catalog_uuid}:${track.track_uuid}:${track.track_id}`;
}

function verdictKey(model: ReferenceCompareModel, track: TrackSummary) {
  return `${model}:${trackIdentityKey(track)}`;
}

function normalizeLimit(value: number) {
  if (!Number.isFinite(value)) return 8;
  return Math.min(100, Math.max(1, Math.trunc(value)));
}

function referenceCompareModelLabel(model: ReferenceCompareModel) {
  if (model === "clap" || model === "sonara") return model.toUpperCase();
  return seedEmbeddingFamilyPresentation[model].label;
}

function clearLabDeadline(request: PendingLabRequest) {
  if (request.deadline !== null) clearTimeout(request.deadline);
  request.deadline = null;
}

function abortLabRequest(request: PendingLabRequest) {
  clearLabDeadline(request);
  request.controller.abort();
}

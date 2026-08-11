import { Search } from "lucide-react";
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
import { displayTrack } from "./trackDisplay";

type ReferenceComparePanelProps = {
  seedTracks: TrackSummary[];
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  previewTrackId: number | null;
  previewCurrentTime: number;
  previewDuration: number;
  onSeed: (track: TrackSummary) => void;
  onToggleLiked: (track: TrackSummary) => void;
  onTogglePlaylist: (track: TrackSummary) => void;
  onPreview: (track: TrackSummary) => void;
  onSeekPreview: (track: TrackSummary, seconds: number) => void;
  onDetails: (track: TrackSummary) => void;
};

const referenceCompareModels: ReferenceCompareModel[] = ["clap", "mert", "muq", "maest", "sonara"];

const referenceCompareVerdictOptions: Array<{ value: ReferenceCompareVerdict; label: string }> = [
  { value: "mood", label: "Mood" },
  { value: "palette", label: "Palette" },
  { value: "instruments", label: "Instruments" },
  { value: "groove", label: "Groove" },
  { value: "genre", label: "Genre" },
  { value: "transition", label: "Transition" },
  { value: "miss", label: "Miss" },
];

export function ReferenceComparePanel({
  seedTracks,
  busy,
  seedSet,
  playlistSet,
  playingTrackId,
  previewTrackId,
  previewCurrentTime,
  previewDuration,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onSeekPreview,
  onDetails,
}: ReferenceComparePanelProps) {
  const [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [compare, setCompare] = useState<ReferenceCompareResponse | null>(null);
  const [savedVerdicts, setSavedVerdicts] = useState<Record<string, ReferenceCompareVerdict>>({});
  const [verdictNotes, setVerdictNotes] = useState<Record<string, string>>({});
  const [savingVerdicts, setSavingVerdicts] = useState<Record<string, boolean>>({});
  const latestCompareRequestRef = useRef(0);
  const latestVerdictRequestRef = useRef<Record<string, number>>({});
  const referenceTrack = seedTracks[0] ?? null;
  const referenceIdentity = referenceTrackIdentityKey(referenceTrack);
  const activeReferenceIdentityRef = useRef(referenceIdentity);
  const canCompare = Boolean(referenceTrack) && !busy && !loading;

  useEffect(() => {
    activeReferenceIdentityRef.current = referenceIdentity;
    latestCompareRequestRef.current += 1;
    latestVerdictRequestRef.current = {};
    setCompare(null);
    setSavedVerdicts({});
    setVerdictNotes({});
    setSavingVerdicts({});
    setError("");
    setLoading(false);
  }, [referenceIdentity]);

  async function runReferenceCompare() {
    if (!referenceTrack) return;
    const requestId = latestCompareRequestRef.current + 1;
    latestCompareRequestRef.current = requestId;
    const requestedIdentity = referenceIdentity;
    const requestedTrackId = referenceTrack.track_id;
    setLoading(true);
    setError("");
    setSavedVerdicts({});
    try {
      const response = await api.referenceCompare({
        seed_track_id: requestedTrackId,
        models: referenceCompareModels,
        limit: normalizeLimit(limit),
      });
      if (!referenceCompareResponseIsCurrent(
        requestId,
        latestCompareRequestRef.current,
        requestedIdentity,
        activeReferenceIdentityRef.current,
        requestedTrackId,
        response.seed_track_id,
      )) return;
      setCompare(response);
    } catch (caught) {
      if (!referenceCompareRequestIsCurrent(
        requestId,
        latestCompareRequestRef.current,
        requestedIdentity,
        activeReferenceIdentityRef.current,
      )) return;
      if (caught instanceof Error) {
        setError(caught.message);
        return;
      }
      throw caught;
    } finally {
      if (referenceCompareRequestIsCurrent(
        requestId,
        latestCompareRequestRef.current,
        requestedIdentity,
        activeReferenceIdentityRef.current,
      )) {
        setLoading(false);
      }
    }
  }

  async function saveVerdict(group: ReferenceCompareGroup, result: SearchResult, verdict: ReferenceCompareVerdict) {
    if (!referenceTrack) return;
    const key = verdictKey(group.model, result.track);
    const requestId = (latestVerdictRequestRef.current[key] ?? 0) + 1;
    latestVerdictRequestRef.current[key] = requestId;
    const requestedIdentity = referenceIdentity;
    setError("");
    setSavingVerdicts((current) => ({ ...current, [key]: true }));
    try {
      await api.referenceCompareVerdict({
        seed: trackIdentityPayload(referenceTrack),
        candidate: trackIdentityPayload(result.track),
        model: group.model,
        verdict,
        notes: verdictNotes[key]?.trim() || null,
      });
      if (!referenceCompareRequestIsCurrent(
        requestId,
        latestVerdictRequestRef.current[key] ?? 0,
        requestedIdentity,
        activeReferenceIdentityRef.current,
      )) return;
      setSavedVerdicts((current) => ({ ...current, [key]: verdict }));
    } catch (caught) {
      if (!referenceCompareRequestIsCurrent(
        requestId,
        latestVerdictRequestRef.current[key] ?? 0,
        requestedIdentity,
        activeReferenceIdentityRef.current,
      )) return;
      if (caught instanceof Error) {
        setError(caught.message);
        return;
      }
      throw caught;
    } finally {
      if (referenceCompareRequestIsCurrent(
        requestId,
        latestVerdictRequestRef.current[key] ?? 0,
        requestedIdentity,
        activeReferenceIdentityRef.current,
      )) {
        setSavingVerdicts((current) => ({ ...current, [key]: false }));
      }
    }
  }

  const groups = compare ? orderedReferenceCompareGroups(compare) : [];

  return (
    <div className="reference-compare-panel">
      <div className="reference-compare-header">
        <div>
          <strong>Model Listening Lab</strong>
          <span>{referenceTrack ? `Reference: ${displayTrack(referenceTrack)}` : "Select one seed track to compare model ears."}</span>
        </div>
        <label title="How many candidates to show per model.">
          Limit
          <input
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            onBlur={() => setLimit(normalizeLimit(limit))}
          />
        </label>
        <button
          className="reference-compare-run-button"
          title="Compare CLAP, MERT, MuQ, MAEST, and SONARA candidates for the first selected seed."
          type="button"
          disabled={!canCompare}
          onClick={() => void runReferenceCompare()}
        >
          <Search size={17} />
          {loading ? "Comparing..." : "Compare models"}
        </button>
      </div>
      {error ? <span className="reference-compare-error">{error}</span> : null}
      {compare ? (
        <div className="reference-compare-grid" aria-label="Reference compare model groups">
          {groups.map((group) => (
            <ReferenceCompareGroupCard
              key={group.model}
              group={group}
              savedVerdicts={savedVerdicts}
              verdictNotes={verdictNotes}
              savingVerdicts={savingVerdicts}
              seedSet={seedSet}
              playlistSet={playlistSet}
              playingTrackId={playingTrackId}
              previewTrackId={previewTrackId}
              previewCurrentTime={previewCurrentTime}
              previewDuration={previewDuration}
              onSeed={onSeed}
              onToggleLiked={onToggleLiked}
              onTogglePlaylist={onTogglePlaylist}
              onPreview={onPreview}
              onSeekPreview={onSeekPreview}
              onDetails={onDetails}
              onNotesChange={(result, notes) => {
                const key = verdictKey(group.model, result.track);
                setVerdictNotes((current) => ({ ...current, [key]: notes }));
              }}
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
  verdictNotes,
  savingVerdicts,
  seedSet,
  playlistSet,
  playingTrackId,
  previewTrackId,
  previewCurrentTime,
  previewDuration,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onSeekPreview,
  onDetails,
  onNotesChange,
  onVerdict,
}: {
  group: ReferenceCompareGroup;
  savedVerdicts: Record<string, ReferenceCompareVerdict>;
  verdictNotes: Record<string, string>;
  savingVerdicts: Record<string, boolean>;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  previewTrackId: number | null;
  previewCurrentTime: number;
  previewDuration: number;
  onSeed: (track: TrackSummary) => void;
  onToggleLiked: (track: TrackSummary) => void;
  onTogglePlaylist: (track: TrackSummary) => void;
  onPreview: (track: TrackSummary) => void;
  onSeekPreview: (track: TrackSummary, seconds: number) => void;
  onDetails: (track: TrackSummary) => void;
  onNotesChange: (result: SearchResult, notes: string) => void;
  onVerdict: (result: SearchResult, verdict: ReferenceCompareVerdict) => void;
}) {
  return (
    <section className={`reference-compare-group ${group.available ? "" : "missing"}`}>
      <div className="reference-compare-group-title">
        <strong>{group.model.toUpperCase()}</strong>
        <span>{group.available ? `${group.results.length} candidates` : group.reason}</span>
      </div>
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
              previewCurrentTime={previewCurrentTime}
              previewDuration={previewDuration}
              isSeed={seedSet.has(result.track.track_id)}
              inPlaylist={playlistSet.has(result.track.track_id)}
              onSeed={onSeed}
              onToggleLiked={onToggleLiked}
              onTogglePlaylist={onTogglePlaylist}
              onPreview={onPreview}
              onSeekPreview={onSeekPreview}
              onDetails={onDetails}
            />
            <label className="reference-compare-notes">
              Notes
              <textarea
                value={verdictNotes[key] ?? ""}
                maxLength={1000}
                rows={2}
                disabled={saving}
                onChange={(event) => onNotesChange(result, event.target.value)}
                placeholder={`Listening notes for ${group.model.toUpperCase()}`}
              />
            </label>
            <div
              className="reference-compare-verdicts"
              role="group"
              aria-busy={saving}
              aria-label={`Verdicts for ${displayTrack(result.track)} via ${group.model}`}
            >
              {referenceCompareVerdictOptions.map((option) => {
                const active = savedVerdicts[key] === option.value;
                return (
                  <button
                    className={`reference-compare-verdict-button ${active ? "active" : ""}`}
                    key={option.value}
                    type="button"
                    aria-pressed={active}
                    disabled={saving}
                    title={`Mark ${displayTrack(result.track)} as ${option.label} for ${group.model.toUpperCase()}`}
                    onClick={() => onVerdict(result, option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
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
    reason: `The backend did not return ${model.toUpperCase()} availability for this request.`,
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
    content_generation: track.content_generation,
  };
}

function trackIdentityKey(track: TrackSummary) {
  return `${track.catalog_uuid}:${track.track_uuid}:${track.content_generation}:${track.track_id}`;
}

function verdictKey(model: ReferenceCompareModel, track: TrackSummary) {
  return `${model}:${trackIdentityKey(track)}`;
}

function normalizeLimit(value: number) {
  if (!Number.isFinite(value)) return 8;
  return Math.min(100, Math.max(1, Math.trunc(value)));
}

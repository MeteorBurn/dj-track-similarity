import { Search } from "lucide-react";
import { useState } from "react";
import { api } from "./api";
import type { ReferenceCompareGroup, ReferenceCompareResponse, ReferenceCompareVerdict, SearchResult, Track } from "./api";
import { ResultRow } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

type ReferenceComparePanelProps = {
  seedTracks: Track[];
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  onSeed: (track: Track) => void;
  onToggleLiked: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
};

const referenceCompareVerdictOptions: Array<{ value: ReferenceCompareVerdict; label: string }> = [
  { value: "mood", label: "Mood" },
  { value: "palette", label: "Palette" },
  { value: "instruments", label: "Instruments" },
  { value: "groove", label: "Groove" },
  { value: "genre", label: "Genre" },
  { value: "transition", label: "Transition" },
  { value: "miss", label: "Miss" }
];

export function ReferenceComparePanel({
  seedTracks,
  busy,
  seedSet,
  playlistSet,
  playingTrackId,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onDetails
}: ReferenceComparePanelProps) {
  const [limit, setLimit] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [compare, setCompare] = useState<ReferenceCompareResponse | null>(null);
  const [savedVerdicts, setSavedVerdicts] = useState<Record<string, ReferenceCompareVerdict>>({});
  const referenceTrack = seedTracks[0] ?? null;
  const canCompare = Boolean(referenceTrack) && !busy && !loading;

  async function runReferenceCompare() {
    if (!referenceTrack) return;
    setLoading(true);
    setError("");
    setSavedVerdicts({});
    try {
      const response = await api.referenceCompare({ seed_track_id: referenceTrack.id, limit });
      setCompare(response);
    } catch (caught) {
      if (caught instanceof Error) {
        setError(caught.message);
        return;
      }
      throw caught;
    } finally {
      setLoading(false);
    }
  }

  async function saveVerdict(group: ReferenceCompareGroup, result: SearchResult, verdict: ReferenceCompareVerdict) {
    if (!referenceTrack) return;
    const key = verdictKey(group, result);
    setError("");
    try {
      await api.referenceCompareVerdict({
        seed_track_id: referenceTrack.id,
        candidate_track_id: result.track.id,
        model: group.model,
        verdict,
        notes: ""
      });
      setSavedVerdicts((current) => ({ ...current, [key]: verdict }));
    } catch (caught) {
      if (caught instanceof Error) {
        setError(caught.message);
        return;
      }
      throw caught;
    }
  }

  return (
    <div className="reference-compare-panel">
      <div className="reference-compare-header">
        <div>
          <strong>Model Listening Lab</strong>
          <span>{referenceTrack ? `Reference: ${displayTrack(referenceTrack)}` : "Select one seed track to compare model ears."}</span>
        </div>
        <label title="How many candidates to show per model.">
          Limit
          <input type="number" min={1} max={100} value={limit} onChange={(event) => setLimit(Number(event.target.value))} />
        </label>
        <button className="reference-compare-run-button" title="Compare CLAP, MERT, MuQ, MAEST, and SONARA candidates for the first selected seed." type="button" disabled={!canCompare} onClick={() => void runReferenceCompare()}>
          <Search size={17} />
          {loading ? "Comparing..." : "Compare models"}
        </button>
      </div>
      {error ? <span className="reference-compare-error">{error}</span> : null}
      {compare ? (
        <div className="reference-compare-grid" aria-label="Reference compare model groups">
          {compare.groups.map((group) => (
            <ReferenceCompareGroupCard
              key={group.model}
              group={group}
              savedVerdicts={savedVerdicts}
              seedSet={seedSet}
              playlistSet={playlistSet}
              playingTrackId={playingTrackId}
              onSeed={onSeed}
              onToggleLiked={onToggleLiked}
              onTogglePlaylist={onTogglePlaylist}
              onPreview={onPreview}
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
  seedSet,
  playlistSet,
  playingTrackId,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onDetails,
  onVerdict
}: {
  group: ReferenceCompareGroup;
  savedVerdicts: Record<string, ReferenceCompareVerdict>;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  onSeed: (track: Track) => void;
  onToggleLiked: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
  onVerdict: (result: SearchResult, verdict: ReferenceCompareVerdict) => void;
}) {
  return (
    <section className={`reference-compare-group ${group.available ? "" : "missing"}`}>
      <div className="reference-compare-group-title">
        <strong>{group.model.toUpperCase()}</strong>
        <span>{group.available ? `${group.results.length} candidates` : group.reason}</span>
      </div>
      {group.results.map((result) => (
        <div className="reference-compare-result" key={result.track.id}>
          <ResultRow
            track={result.track}
            score={result.score}
            scoreBreakdown={result.score_breakdown}
            playingTrackId={playingTrackId}
            isSeed={seedSet.has(result.track.id)}
            inPlaylist={playlistSet.has(result.track.id)}
            onSeed={onSeed}
            onToggleLiked={onToggleLiked}
            onTogglePlaylist={onTogglePlaylist}
            onPreview={onPreview}
            onDetails={onDetails}
          />
          <div className="reference-compare-verdicts" role="group" aria-label={`Verdicts for ${displayTrack(result.track)} via ${group.model}`}>
            {referenceCompareVerdictOptions.map((option) => {
              const active = savedVerdicts[verdictKey(group, result)] === option.value;
              return (
                <button
                  className={`reference-compare-verdict-button ${active ? "active" : ""}`}
                  key={option.value}
                  type="button"
                  aria-pressed={active}
                  title={`Mark ${displayTrack(result.track)} as ${option.label} for ${group.model.toUpperCase()}`}
                  onClick={() => onVerdict(result, option.value)}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {group.available && group.results.length === 0 ? <span className="reference-compare-empty">No candidates for this model.</span> : null}
    </section>
  );
}

function verdictKey(group: ReferenceCompareGroup, result: SearchResult) {
  return `${group.model}:${result.track.id}`;
}

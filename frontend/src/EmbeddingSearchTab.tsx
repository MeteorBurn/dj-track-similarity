import { Search, Shuffle } from "lucide-react";
import type { EmbeddingSource } from "./api";
import {
  seedEmbeddingFamilies,
  seedEmbeddingFamilyPresentation,
  type SeedEmbeddingFamily
} from "./searchSurfaceState";

const modelHelp = "Embedding family used for seed-to-track similarity search. MERT, MuQ, and MuQ-MuLan stay separate score spaces.";

export function EmbeddingSearchTab({
  analysisFamily,
  onAnalysisFamilyChange,
  currentEmbeddingCount,
  busy,
  randomTrackBusy,
  pending,
  error,
  limit,
  limitHelp,
  onLimitChange,
  onSearch,
  onAddRandomTrack
}: {
  analysisFamily: SeedEmbeddingFamily;
  onAnalysisFamilyChange: (value: SeedEmbeddingFamily) => void;
  currentEmbeddingCount: number;
  busy: boolean;
  randomTrackBusy: boolean;
  pending: boolean;
  error: string;
  limit: number;
  limitHelp: string;
  onLimitChange: (value: number) => void;
  onSearch: (analysisFamily: EmbeddingSource) => Promise<void>;
  onAddRandomTrack: () => void;
}) {
  const label = seedEmbeddingFamilyPresentation[analysisFamily].label;
  const missingReason = currentEmbeddingCount > 0
    ? ""
    : `No current ${label} embeddings are available in the selected catalog. Run ${label} analysis first.`;
  const requestTitle = missingReason || `Find acoustically similar tracks with current ${label} embeddings.`;
  const randomTrackTitle = missingReason || `Add a random track with a current ${label} embedding as a seed.`;

  return (
    <>
      <div className="embedding-random-track-action">
        <button
          className="embedding-random-track-button"
          title={randomTrackTitle}
          disabled={randomTrackBusy || Boolean(missingReason)}
          onClick={onAddRandomTrack}
          type="button"
        >
          <Shuffle size={15} />
          Add Random Track
        </button>
      </div>
      <div className="search-filter-grid embedding-search-grid">
        <label title={modelHelp}>
          Model
          <select
            className="embedding-model-select"
            value={analysisFamily}
            title={seedEmbeddingFamilyPresentation[analysisFamily].title}
            onChange={(event) => onAnalysisFamilyChange(event.target.value as SeedEmbeddingFamily)}
          >
            {seedEmbeddingFamilies.map((family) => (
              <option key={family} value={family} title={seedEmbeddingFamilyPresentation[family].title}>
                {seedEmbeddingFamilyPresentation[family].label}
              </option>
            ))}
          </select>
        </label>
        <label title={limitHelp}>
          Limit
          <input
            type="number"
            value={limit}
            min={1}
            max={500}
            title={limitHelp}
            onChange={(event) => {
              if (Number.isFinite(event.currentTarget.valueAsNumber)) {
                onLimitChange(Math.round(Math.max(1, Math.min(500, event.currentTarget.valueAsNumber))));
              }
            }}
          />
        </label>
      </div>
      <button
        className="embedding-search-button"
        title={requestTitle}
        disabled={busy || pending || Boolean(missingReason)}
        onClick={() => void onSearch(analysisFamily)}
        type="button"
      >
        <Search size={17} />
        {pending ? "Searching..." : "Search"}
      </button>
      {missingReason ? <span className="embedding-search-requirement">{missingReason}</span> : null}
      {error ? <span className="embedding-search-requirement error">{error}</span> : null}
    </>
  );
}

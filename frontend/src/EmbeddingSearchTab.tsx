import { Search } from "lucide-react";
import type { EmbeddingSource } from "./api";

export function EmbeddingSearchTab({
  analysisFamily,
  currentEmbeddingCount,
  busy,
  pending,
  error,
  limit,
  limitHelp,
  onLimitChange,
  onSearch
}: {
  analysisFamily: EmbeddingSource;
  currentEmbeddingCount: number;
  busy: boolean;
  pending: boolean;
  error: string;
  limit: number;
  limitHelp: string;
  onLimitChange: (value: number) => void;
  onSearch: (analysisFamily: EmbeddingSource) => Promise<void>;
}) {
  const label = analysisFamily.toUpperCase();
  const missingReason = currentEmbeddingCount > 0
    ? ""
    : `No current ${label} embeddings are available in the selected catalog. Run ${label} analysis first.`;
  const requestTitle = missingReason || `Find acoustically similar tracks with current ${label} embeddings.`;

  return (
    <>
      <div className="search-filter-grid embedding-search-grid">
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
        {pending ? `${label} searching...` : `${label} search`}
      </button>
      {missingReason ? <span className="embedding-search-requirement">{missingReason}</span> : null}
      {error ? <span className="embedding-search-requirement error">{error}</span> : null}
    </>
  );
}

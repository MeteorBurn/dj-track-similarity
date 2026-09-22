import { CircleAlert, Pause, Play, Star, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type {
  ClusterMapCluster,
  ClusterMapFeatureValue,
  ClusterMapPoint,
  ClusterMapResponse,
  EmbeddingLayersResponse,
  Track,
} from "./api";
import { ClusterMapPlot, OrbitSkeleton, clusterLetter, clusterName, clusterSlot } from "./ClusterMapPlot";
import { formatMaestGenreLabel } from "./maestGenres";
import { seedSearchModelPresentation, tabAfterKey } from "./searchSurfaceState";
import { formatSonaraCoreValue, sonaraCoreFeatureGroups } from "./TrackMetadataDialog";
import { displayTrack } from "./trackDisplay";
import type { ClusterMapEntry } from "./useClusterMap";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

type RailTab = "clusters" | "anomalies" | "layer";
type LayerRow = EmbeddingLayersResponse["layers"][number];
type Candidate = { point: ClusterMapPoint; rank: number };
type MapView = {
  seeds: ClusterMapPoint[];
  candidates: Candidate[];
  members: Candidate[][];
  outside: Candidate[];
  flagged: Candidate[];
  medianSimilarity: number | null;
};

const railTabs: readonly RailTab[] = ["clusters", "anomalies", "layer"];
const CLOSEST_MEMBERS = 4;
const DRIFT_SHOWN = 5;
// SONARA labels that name a component rather than a feature read under their group title.
const groupScopedLabels = new Set(["Score", "Rhythm", "Level"]);
const FOCUSABLE = [
  "button:not([disabled]):not([tabindex='-1'])",
  "summary",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(", ");

/** The cluster map of one REFERENCE search. It stays mounted while its build is
 * cached, so a closed map keeps its zoom, tab and isolated cluster. */
export function ClusterMapDialog({
  entry,
  open,
  layerState,
  playingTrackId,
  onPreview,
  onClose,
  onRetry,
}: {
  entry: ClusterMapEntry;
  open: boolean;
  layerState: EmbeddingLayerState;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
  onClose: () => void;
  onRetry: () => void;
}) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const pressedOnBackdrop = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [tab, setTab] = useState<RailTab>("clusters");
  const [isolated, setIsolated] = useState<number | null>(null);
  const { payload, response } = entry;
  const view = useMemo(() => (response ? mapView(response) : null), [response]);
  const layer = payload.layer ?? null;
  const layerRow = layer === null ? null : layerState.layers?.find((row) => row.layer === layer) ?? null;
  const seedCount = payload.seed_track_ids.length;
  const summary = view
    ? [
      plural(seedCount, "reference track"),
      plural(view.candidates.length, "candidate"),
      view.medianSimilarity === null ? "" : `median similarity ${view.medianSimilarity.toFixed(3)}`,
    ].filter(Boolean).join(" · ")
    : `${plural(seedCount, "reference track")} · up to ${plural(payload.limit, "candidate")}`;

  useEffect(() => {
    if (!open) return undefined;
    sectionRef.current?.focus({ preventScroll: true });
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      requestClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  function requestClose() {
    const active = document.activeElement;
    const restoreFocus = !active || active === document.body || Boolean(sectionRef.current?.contains(active));
    onCloseRef.current();
    if (restoreFocus) document.getElementById("cluster-map-button")?.focus();
  }

  function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const section = event.currentTarget;
    const focusable = [...section.querySelectorAll<HTMLElement>(FOCUSABLE)]
      .filter((element) => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === section)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function selectTabByKey(event: KeyboardEvent<HTMLButtonElement>) {
    const target = tabAfterKey(railTabs, tab, event.key);
    if (!target) return;
    event.preventDefault();
    setTab(target);
    document.getElementById(`cluster-map-tab-${target}`)?.focus();
  }

  return (
    <div
      className="cluster-map-backdrop"
      role="presentation"
      data-open={open ? "true" : "false"}
      inert={!open}
      onPointerDown={(event) => {
        pressedOnBackdrop.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        // A pan or selection that merely ends on the backdrop must not close the map.
        const fromBackdrop = pressedOnBackdrop.current && event.target === event.currentTarget;
        pressedOnBackdrop.current = false;
        if (fromBackdrop) requestClose();
      }}
    >
      <section
        ref={sectionRef}
        className="cluster-map-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cluster-map-title"
        aria-describedby="cluster-map-summary"
        aria-busy={entry.status === "loading" || undefined}
        tabIndex={-1}
        onKeyDown={keepFocusInside}
      >
        <header className="cluster-map-header">
          <div className="cluster-map-heading">
            <h2 id="cluster-map-title">Cluster map</h2>
            <span className="cluster-map-chip">{seedSearchModelPresentation[payload.analysis_family].label}</span>
            {layer !== null ? (
              <span className="cluster-map-chip" title={[layerRow?.source, layerState.note].filter(Boolean).join("\n") || undefined}>
                L{layer}{layerState.layers ? ` / ${layerState.layers.length}` : ""}
              </span>
            ) : null}
            {layerRow?.label ? <span className="cluster-map-layer-hint">{layerRow.label}</span> : null}
          </div>
          <p id="cluster-map-summary" className="cluster-map-summary">{summary}</p>
          <button className="icon-button cluster-map-close-button" type="button" title="Закрыть" aria-label="Закрыть" onClick={requestClose}>
            <X size={16} />
          </button>
        </header>
        {entry.status === "loading" ? (
          <div className="cluster-map-body">
            <p className="cluster-map-status" role="status">Building the cluster map…</p>
            <div className="cluster-map-kpis" aria-hidden="true">
              {[0, 1, 2, 3].map((tile) => (
                <div key={tile} className="cluster-map-kpi">
                  <span className="cluster-map-skeleton-line" />
                  <span className="cluster-map-skeleton-line is-value" />
                </div>
              ))}
            </div>
            <div className="cluster-map-main" aria-hidden="true">
              <div className="cluster-map-figure">
                <div className="cluster-map-plot-frame"><OrbitSkeleton /></div>
              </div>
              <div className="cluster-map-rail">
                {[0, 1, 2].map((card) => (
                  <div key={card} className="cluster-map-card">
                    <span className="cluster-map-skeleton-line" />
                    <span className="cluster-map-skeleton-line is-wide" />
                    <span className="cluster-map-skeleton-line is-wide" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : entry.status === "error" ? (
          <div className="cluster-map-body">
            <div className="cluster-map-error" role="alert">
              <CircleAlert size={18} aria-hidden="true" />
              <div>
                <strong>Could not build the cluster map</strong>
                <p>{entry.error}</p>
              </div>
              <button type="button" title="Build the cluster map again" onClick={onRetry}>Retry</button>
            </div>
          </div>
        ) : response && view ? (
          <div className="cluster-map-body">
            <KpiRow response={response} view={view} />
            <div className="cluster-map-main">
              <figure className="cluster-map-figure">
                <figcaption>Candidates orbit the reference core: the closer a point, the more similar the track. Click a point to preview it.</figcaption>
                <ClusterMapPlot
                  mapKey={entry.key}
                  points={response.points}
                  center={response.candidates_center}
                  clusterCount={response.clusters.length}
                  isolated={isolated}
                  playingTrackId={playingTrackId}
                  featureLabel={featureLabel}
                  onPreview={onPreview}
                />
                {response.clusters.length === 0 ? (
                  <p className="cluster-map-note">HDBSCAN found no clusters among these candidates.</p>
                ) : null}
                <div className="cluster-map-legend">
                  {response.clusters.map((_, cluster) => (
                    <button
                      key={cluster}
                      type="button"
                      className="cluster-map-legend-chip"
                      data-slot={clusterSlot(cluster)}
                      aria-pressed={isolated === cluster}
                      aria-label={`Cluster ${clusterLetter(cluster)}, ${plural(view.members[cluster].length, "candidate")}`}
                      title={isolated === cluster ? "Show every cluster" : `Show only cluster ${clusterLetter(cluster)}`}
                      onClick={() => setIsolated(isolated === cluster ? null : cluster)}
                    >
                      <span className="cluster-map-dot" />
                      {clusterLetter(cluster)}
                      <span className="cluster-map-legend-count">{view.members[cluster].length}</span>
                    </button>
                  ))}
                  {view.outside.length ? (
                    <span className="cluster-map-key" data-slot="other">
                      <span className="cluster-map-dot" aria-hidden="true" />
                      Outside clusters · {view.outside.length}
                    </span>
                  ) : null}
                  <span className="cluster-map-key">
                    <span className="cluster-map-key-core" aria-hidden="true" />
                    Core · {view.seeds.length}
                  </span>
                  <span className="cluster-map-key" title="The candidates' centre of mass; its distance from the core shows how far the search drifts">
                    <Star className="cluster-map-key-center" size={12} aria-hidden="true" />
                    Candidates center
                  </span>
                  <span className="cluster-map-key">
                    <span className="cluster-map-key-ring" aria-hidden="true" />
                    Stands out · {view.flagged.length}
                  </span>
                </div>
              </figure>
              <aside className="cluster-map-rail" aria-label="Map details">
                <div className="search-tabs cluster-map-tabs" role="tablist" aria-label="Detail views">
                  {railTabs.map((name) => (
                    <button
                      key={name}
                      id={`cluster-map-tab-${name}`}
                      className={`model-search-tab ${tab === name ? "active" : ""}`}
                      title={railTabTitle(name, layer)}
                      role="tab"
                      aria-selected={tab === name}
                      aria-controls={`cluster-map-panel-${name}`}
                      tabIndex={tab === name ? 0 : -1}
                      type="button"
                      onClick={() => setTab(name)}
                      onKeyDown={selectTabByKey}
                    >
                      {name === "clusters" ? "Clusters" : name === "anomalies" ? "Anomalies" : layer !== null ? "Layer" : "Model"}
                    </button>
                  ))}
                </div>
                <div
                  id={`cluster-map-panel-${tab}`}
                  className="cluster-map-tab-panel"
                  role="tabpanel"
                  aria-labelledby={`cluster-map-tab-${tab}`}
                >
                  {tab === "clusters" ? (
                    <ClustersPanel
                      response={response}
                      view={view}
                      isolated={isolated}
                      playingTrackId={playingTrackId}
                      onPreview={onPreview}
                    />
                  ) : tab === "anomalies" ? (
                    <AnomaliesPanel view={view} playingTrackId={playingTrackId} onPreview={onPreview} />
                  ) : (
                    <LayerPanel
                      response={response}
                      isolated={isolated}
                      layer={layer}
                      layerRow={layerRow}
                      note={layerState.note}
                    />
                  )}
                </div>
              </aside>
            </div>
          </div>
        ) : null}
        <footer className="cluster-map-footer">Scores rank candidates; the final pick is made by ear.</footer>
      </section>
    </div>
  );
}

function KpiRow({ response, view }: { response: ClusterMapResponse; view: MapView }) {
  const total = view.candidates.length;
  const clusterCount = response.clusters.length;
  const percent = (count: number) => `${Math.round((count / total) * 100)}%`;
  return (
    <dl className="cluster-map-kpis">
      <div className="cluster-map-kpi">
        <dt>Separation</dt>
        <dd className="cluster-map-kpi-value">{response.silhouette === null ? "—" : response.silhouette.toFixed(2)}</dd>
        <dd className="cluster-map-kpi-note">silhouette, from −1 to 1</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>Clusters</dt>
        <dd className="cluster-map-kpi-value">{clusterCount}</dd>
        <dd className="cluster-map-kpi-note">{view.outside.length ? `${plural(view.outside.length, "candidate")} outside` : "every candidate in one"}</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>In cluster A</dt>
        <dd className="cluster-map-kpi-value">{clusterCount ? percent(view.members[0].length) : "—"}</dd>
        <dd className="cluster-map-kpi-note">nearest to the references</dd>
      </div>
      <div className="cluster-map-kpi">
        <dt>Anomalies</dt>
        <dd className="cluster-map-kpi-value">{view.flagged.length}</dd>
        <dd className="cluster-map-kpi-note">
          {view.flagged.length ? (
            <>
              <TriangleAlert size={13} aria-hidden="true" />
              stand out
            </>
          ) : "none stand out"}
        </dd>
      </div>
    </dl>
  );
}

function ClustersPanel({ response, view, isolated, playingTrackId, onPreview }: {
  response: ClusterMapResponse;
  view: MapView;
  isolated: number | null;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  return (
    <div className="cluster-map-cards">
      <article className="cluster-map-card cluster-map-core-card">
        <header className="cluster-map-card-head">
          <span className="cluster-map-key-core" aria-hidden="true" />
          <h3>Core</h3>
          <span className="cluster-map-card-meta">{plural(view.seeds.length, "reference track")}</span>
        </header>
        <TrackList
          items={view.seeds.map((point) => ({ point, meta: `${point.similarity.toFixed(3)} to core` }))}
          playingTrackId={playingTrackId}
          onPreview={onPreview}
        />
      </article>
      {response.clusters.map((cluster, index) => {
        const members = view.members[index];
        const representative = view.candidates.find(({ point }) => point.track.track_id === cluster.representative_track_id);
        return (
          <article
            key={index}
            className="cluster-map-card"
            data-slot={clusterSlot(index)}
            data-active={isolated === index || undefined}
            data-dimmed={(isolated !== null && isolated !== index) || undefined}
          >
            <header className="cluster-map-card-head">
              <span className="cluster-map-dot" aria-hidden="true" />
              <h3>Cluster {clusterLetter(index)}</h3>
              <span className="cluster-map-card-meta">
                {plural(members.length, "candidate")} · median {cluster.median_similarity.toFixed(3)}
              </span>
            </header>
            {representative ? (
              <div className="cluster-map-field">
                <span className="cluster-map-field-label">Representative</span>
                <TrackList
                  items={[{ point: representative.point, meta: `#${representative.rank} · ${representative.point.similarity.toFixed(3)}` }]}
                  playingTrackId={playingTrackId}
                  onPreview={onPreview}
                />
              </div>
            ) : null}
            <p className="cluster-map-glue" title="Standard deviation of the SONARA groups inside this cluster, in library σ">
              {glueLine(cluster)}
            </p>
            {cluster.maest_genres.length ? (
              <p className="cluster-map-genres" title="MAEST genres: each genre's share of the cluster's summed genre scores">
                {cluster.maest_genres
                  .map((genre) => `${formatMaestGenreLabel(genre.genre_name)} ${Math.round(genre.share * 100)}%`)
                  .join(" · ")}
              </p>
            ) : null}
            <MemberList members={members} playingTrackId={playingTrackId} onPreview={onPreview} />
          </article>
        );
      })}
      {view.outside.length ? (
        <article className="cluster-map-card" data-slot="other">
          <header className="cluster-map-card-head">
            <span className="cluster-map-dot" aria-hidden="true" />
            <h3>Outside clusters</h3>
            <span className="cluster-map-card-meta">{plural(view.outside.length, "candidate")}</span>
          </header>
          <MemberList members={view.outside} playingTrackId={playingTrackId} onPreview={onPreview} />
        </article>
      ) : null}
    </div>
  );
}

function AnomaliesPanel({ view, playingTrackId, onPreview }: {
  view: MapView;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  if (!view.flagged.length) {
    return <div className="empty-state">IsolationForest finds no candidate whose SONARA profile stands out.</div>;
  }
  const rows = [...view.flagged].sort((left, right) => left.point.outlier_score - right.point.outlier_score);
  return (
    <>
      <p className="cluster-map-anomaly-summary">{anomalySummary(view.flagged)}</p>
      <ul className="cluster-map-anomalies">
        {rows.map(({ point, rank }) => {
          const name = displayTrack(point.track);
          return (
            <li key={point.track.track_id} className="cluster-map-anomaly">
              <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
              <div className="cluster-map-anomaly-title">
                <strong title={name}>{name}</strong>
                <span className="cluster-map-anomaly-meta" data-slot={clusterSlot(point.cluster)}>
                  <span className="cluster-map-dot" aria-hidden="true" />
                  {clusterName(point.cluster)} · #{rank} · {point.similarity.toFixed(3)}
                </span>
              </div>
              <span className="cluster-map-anomaly-score" title="IsolationForest score: the lower, the more unusual">
                {point.outlier_score.toFixed(2)}
              </span>
              <div className="cluster-map-reasons">
                {point.outlier_features.map((item) => (
                  <span key={item.feature} className="cluster-map-reason" title="Distance from the map's mean, in library σ">
                    {featureValueText(item)}
                  </span>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function LayerPanel({ response, isolated, layer, layerRow, note }: {
  response: ClusterMapResponse;
  isolated: number | null;
  layer: number | null;
  layerRow: LayerRow | null;
  note: string | null;
}) {
  const subject = layer !== null ? "layer" : "model";
  const clusterIndex = isolated ?? 0;
  const cluster = response.clusters[clusterIndex];
  const widest = cluster ? Math.max(...cluster.profile.map((spread) => spread.std), 1e-9) : 1;
  return (
    <div className="cluster-map-layer">
      {layer !== null ? (
        <div className="cluster-map-layer-about">
          <h3>L{layer}{layerRow?.label ? ` · ${layerRow.label}` : ""}</h3>
          {layerRow?.source ? <p className="cluster-map-prose">{layerRow.source}</p> : null}
          {note ? <p className="cluster-map-prose">{note}</p> : null}
        </div>
      ) : null}
      <div className="cluster-map-focus">
        <h3>{cluster ? `Glue of cluster ${clusterLetter(clusterIndex)}` : "Glue"}</h3>
        <p className="cluster-map-prose">
          The spread of each SONARA group inside the cluster, in library σ. The {subject} holds the group with the smallest
          spread and ignores the one with the largest. Pick a cluster in the legend to see its glue.
        </p>
        {cluster ? cluster.profile.map((spread, position) => (
          <div
            key={spread.group}
            className="cluster-map-focus-row"
            data-holds={position === 0 || undefined}
            title={`${groupLabel(spread.group)}: std ${spread.std.toFixed(2)}`}
          >
            <span className="cluster-map-focus-label">{groupLabel(spread.group)}</span>
            <span className="cluster-map-focus-track">
              <span className="cluster-map-focus-bar" style={{ left: 0, width: `${(spread.std / widest) * 100}%` }} />
            </span>
            <span className="cluster-map-focus-value">{spread.std.toFixed(2)}</span>
          </div>
        )) : <div className="empty-state">No cluster to profile: HDBSCAN found none in this search.</div>}
      </div>
      <div className="cluster-map-focus">
        <h3>Drift from the references</h3>
        <p className="cluster-map-prose">
          The candidates' mean minus the references' mean, in library σ: where this {subject} pulls the search.
        </p>
        <div className="cluster-map-reasons">
          {response.drift.slice(0, DRIFT_SHOWN).map((item) => (
            <span key={item.feature} className="cluster-map-reason">
              {`${featureLabel(item.feature)} ${item.delta > 0 ? "+" : ""}${item.delta.toFixed(2)}σ`}
            </span>
          ))}
        </div>
      </div>
      <div className="cluster-map-focus">
        <h3>Separation</h3>
        <p className="cluster-map-prose">
          The silhouette of the HDBSCAN clusters, measured on the directions in which the candidates differ from the
          core: near 1 the clusters are distinct, near 0 they overlap.
        </p>
      </div>
      <p className="cluster-map-prose">
        Distance from the centre is exact (1 − similarity to the core); the angle only approximates the direction of
        difference and keeps {Math.round(response.angle_variance_kept * 100)}% of it.
      </p>
      <p className="cluster-map-prose">
        Each map covers one model and layer; switch Model or Layer in the panel and open the map again to compare.
      </p>
    </div>
  );
}

function MemberList({ members, playingTrackId, onPreview }: {
  members: Candidate[];
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const line = ({ point, rank }: Candidate) => ({ point, meta: `#${rank} · ${point.similarity.toFixed(3)}` });
  return (
    <>
      <TrackList items={members.slice(0, CLOSEST_MEMBERS).map(line)} playingTrackId={playingTrackId} onPreview={onPreview} />
      {members.length > CLOSEST_MEMBERS ? (
        <details className="cluster-map-more">
          <summary>Show all {members.length}</summary>
          <TrackList items={members.slice(CLOSEST_MEMBERS).map(line)} playingTrackId={playingTrackId} onPreview={onPreview} />
        </details>
      ) : null}
    </>
  );
}

function TrackList({ items, playingTrackId, onPreview }: {
  items: { point: ClusterMapPoint; meta: string }[];
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  return (
    <ul className="cluster-map-track-list">
      {items.map(({ point, meta }) => {
        const name = displayTrack(point.track);
        return (
          <li key={point.track.track_id}>
            <div className="cluster-map-track">
              <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
              <span className="cluster-map-track-name" title={name}>{name}</span>
              <span className="cluster-map-track-meta">{meta}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function PlayButton({ track, playingTrackId, onPreview }: {
  track: Track;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const playing = playingTrackId === track.track_id;
  const name = displayTrack(track);
  return (
    <button
      className="icon-button cluster-map-play-button"
      data-playing={playing || undefined}
      title={playing ? "Pause preview" : "Preview"}
      aria-label={`${playing ? "Pause" : "Preview"} ${name}`}
      type="button"
      onClick={() => onPreview(track)}
    >
      {playing ? <Pause size={13} /> : <Play size={13} />}
    </button>
  );
}

function mapView(response: ClusterMapResponse): MapView {
  const seeds: ClusterMapPoint[] = [];
  const candidates: Candidate[] = [];
  for (const point of response.points) {
    if (point.seed) seeds.push(point);
    else candidates.push({ point, rank: candidates.length + 1 });
  }
  return {
    seeds,
    candidates,
    members: response.clusters.map((_, cluster) => candidates.filter(({ point }) => point.cluster === cluster)),
    outside: candidates.filter(({ point }) => point.cluster === -1),
    flagged: candidates.filter(({ point }) => point.outlier),
    medianSimilarity: median(candidates.map(({ point }) => point.similarity)),
  };
}

function median(values: number[]) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function railTabTitle(tab: RailTab, layer: number | null) {
  if (tab === "clusters") return "The core and each cluster: representative, glue, genres and closest tracks";
  if (tab === "anomalies") return "Candidates whose SONARA profile IsolationForest finds unusual";
  return layer !== null
    ? "What holds this layer's clusters together, and where it pulls the search"
    : "What holds this model's clusters together, and where it pulls the search";
}

function glueLine(cluster: ClusterMapCluster) {
  const glue = cluster.profile[0];
  const ignored = cluster.profile[cluster.profile.length - 1];
  if (!glue || !ignored) return "";
  return `Glue: ${groupLabel(glue.group)} (std ${glue.std.toFixed(2)}) · Ignored: ${groupLabel(ignored.group)} (std ${ignored.std.toFixed(2)})`;
}

function anomalySummary(flagged: Candidate[]) {
  const counts = new Map<string, number>();
  for (const { point } of flagged) {
    for (const item of point.outlier_features) {
      const key = featureLabel(item.feature);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return [...counts]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([key, count]) => `${key} ×${count}`)
    .join(" · ");
}

function featureValueText(item: ClusterMapFeatureValue) {
  return `${featureLabel(item.feature)} ${formatFeatureValue(item.feature, item.value)} (${item.delta > 0 ? "+" : ""}${item.delta.toFixed(1)}σ)`;
}

function groupLabel(group: string) {
  return group.charAt(0).toUpperCase() + group.slice(1);
}

function sonaraFeature(feature: string) {
  for (const group of sonaraCoreFeatureGroups) {
    const descriptor = group.features.find((candidate) => candidate.key === feature);
    if (descriptor) return { key: descriptor.key, label: descriptor.label, group: group.title };
  }
  return null;
}

/** SONARA labels and units come from the track metadata dialog; `mfcc_N` is an MFCC coefficient. */
function featureLabel(feature: string) {
  const mfcc = /^mfcc_(\d+)$/.exec(feature);
  if (mfcc) return `MFCC ${mfcc[1]}`;
  const descriptor = sonaraFeature(feature);
  if (!descriptor) return feature.replaceAll("_", " ");
  return groupScopedLabels.has(descriptor.label)
    ? `${descriptor.group} ${descriptor.label.toLowerCase()}`
    : descriptor.label;
}

function formatFeatureValue(feature: string, value: number) {
  const descriptor = sonaraFeature(feature);
  return descriptor ? formatSonaraCoreValue(descriptor.key, value) : value.toFixed(2);
}

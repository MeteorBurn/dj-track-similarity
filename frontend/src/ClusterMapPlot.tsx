import { useState } from "react";
import type { ClusterMapPoint, ClusterMapResponse } from "./api";
import { displayTrack } from "./trackDisplay";

const SIZE = 600;
const CENTRE = SIZE / 2;
const RADIUS = 236;
// Room beside the circle for the longest facet labels.
const MARGIN = 90;
// The facet band outside the face. Its 6-unit stroke (styles.css) ends in 3-unit
// round caps, so each arc stops 3 + 3 units short of its sector edges and
// neighbouring segments keep a visible 6-unit gap.
const RIM = RADIUS + 7;
const RIM_TRIM = (3 + 3) / RIM;
// Two ring labels in one column need a fixed 12-unit box each (no DOM measuring) plus a 1-unit gap.
const RING_LABEL_SPACING = 12 + 1;
// Below this share concentration the angle stands for no single facet.
export const DIFFUSE_FOCUS = 0.35;

/** Every channel has one job: radius is the exact SONARA distance D (or one
 * facet of it), angle is which facets make that distance, the number is the
 * model's rank. Distances between candidates are not drawn. */
export function ClusterMapPlot({ response, facet, selectedTrackId, onSelect }: {
  response: ClusterMapResponse;
  /** null: the combined distance; otherwise the index of one facet. */
  facet: number | null;
  selectedTrackId: number | null;
  onSelect: (trackId: number) => void;
}) {
  const [hover, setHover] = useState<{ point: ClusterMapPoint; x: number; y: number } | null>(null);
  const facets = response.facets;
  const rings = facet === null ? response.reference.rings : response.reference.facet_rings[facet];
  const value = (point: ClusterMapPoint) => (facet === null ? point.evidence.distance : point.evidence.facet_distance[facet]);
  const measured = response.points.filter((point) => value(point) !== null);
  const typical = rings.find((ring) => ring.percentile === 50)?.distance ?? 1;
  const edge = Math.max(typical * 1.08, ...measured.map((point) => (value(point) ?? 0) * 1.04));
  const radius = (distance: number) => RADIUS * Math.min(distance, edge) / edge;
  const at = (r: number, angle: number): [number, number] => [CENTRE + r * Math.cos(angle), CENTRE + r * Math.sin(angle)];
  const anchor = (index: number) => -Math.PI / 2 + 2 * Math.PI * index / facets.length;
  const half = Math.PI / facets.length;
  const candidates = measured.filter((point) => !point.seed).sort((a, b) => (value(b) ?? 0) - (value(a) ?? 0));
  const seeds = measured.filter((point) => point.seed);
  // Ring labels stand in two columns at the top of the vertical axis: the 50% label
  // first on the right, then inner to outer, each on the first side where it clears
  // the labels already there. A label that clears neither is left out; its ring stays.
  const typicalFirst = [...rings.filter((ring) => ring.percentile === 50), ...rings.filter((ring) => ring.percentile !== 50)];
  const ringLabels: { percentile: number; y: number; side: "start" | "end" }[] = [];
  for (const ring of typicalFirst) {
    const y = CENTRE - radius(ring.distance) - 3;
    const side = (["start", "end"] as const).find((key) =>
      ringLabels.every((label) => label.side !== key || Math.abs(label.y - y) >= RING_LABEL_SPACING));
    if (side) ringLabels.push({ percentile: ring.percentile, y, side });
  }

  return (
    <div className="cluster-map-plot-frame">
      <svg className="cluster-map-plot" viewBox={`${-MARGIN} 0 ${SIZE + 2 * MARGIN} ${SIZE}`} role="img"
        aria-label={facet === null ? "Кандидаты вокруг референсов по итоговому расстоянию SONARA" : `Кандидаты по грани «${facets[facet].label}»`}>
        <circle cx={CENTRE} cy={CENTRE} r={RADIUS} className="cluster-map-face" />
        {facets.map((item, index) => {
          const [x1, y1] = at(RADIUS, anchor(index) - half);
          const [x2, y2] = at(RADIUS, anchor(index) + half);
          return <path key={item.key} d={`M${CENTRE},${CENTRE} L${x1},${y1} A${RADIUS},${RADIUS} 0 0 1 ${x2},${y2} Z`}
            className="cluster-map-sector" data-facet={index} data-active={facet === index || undefined} />;
        })}
        {facets.map((item, index) => {
          const [sx, sy] = at(RADIUS, anchor(index) - half);
          const [ax1, ay1] = at(RIM, anchor(index) - half + RIM_TRIM);
          const [ax2, ay2] = at(RIM, anchor(index) + half - RIM_TRIM);
          const [lx, ly] = at(RADIUS + 28, anchor(index));
          const cos = Math.cos(anchor(index));
          return <g key={item.key}>
            <line x1={CENTRE} y1={CENTRE} x2={sx} y2={sy} className="cluster-map-spoke" />
            <path d={`M${ax1},${ay1} A${RIM},${RIM} 0 0 1 ${ax2},${ay2}`} className="cluster-map-rim"
              data-muted={(facet !== null && facet !== index) || undefined} style={{ stroke: `var(--cluster-f${index})` }} />
            <text x={lx} y={ly + 4} className="cluster-map-sector-label" data-facet={index}
              textAnchor={Math.abs(cos) < 0.3 ? "middle" : cos > 0 ? "start" : "end"}>{item.label}</text>
          </g>;
        })}
        {rings.map((ring) => <circle key={ring.percentile} cx={CENTRE} cy={CENTRE} r={radius(ring.distance)}
          className="cluster-map-ring" data-typical={ring.percentile === 50 || undefined} />)}
        {facet === null && response.reference.core_distance > 0
          ? <circle cx={CENTRE} cy={CENTRE} r={radius(response.reference.core_distance)} className="cluster-map-core" /> : null}
        {ringLabels.map((label) => <text key={label.percentile} x={label.side === "start" ? CENTRE + 3 : CENTRE - 3} y={label.y}
          textAnchor={label.side} className="cluster-map-ring-label" data-typical={label.percentile === 50 || undefined}>{label.percentile}%</text>)}
        {seeds.map((point) => {
          const [x, y] = at(radius(value(point) ?? 0), point.evidence.angle);
          return <path key={point.track.track_id} className="cluster-map-reference" d={star(x, y, 12)}
            onMouseEnter={() => setHover({ point, x, y })} onMouseLeave={() => setHover(null)} />;
        })}
        {candidates.map((point) => {
          const [x, y] = at(radius(value(point) ?? 0), point.evidence.angle);
          const selected = point.track.track_id === selectedTrackId;
          return <g key={point.track.track_id} className="cluster-map-candidate" data-selected={selected || undefined}
            data-diffuse={point.evidence.focus < DIFFUSE_FOCUS || undefined} role="button" tabIndex={0}
            aria-label={`#${point.rank} ${displayTrack(point.track)}`}
            onClick={() => onSelect(point.track.track_id)}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(point.track.track_id); } }}
            onMouseEnter={() => setHover({ point, x, y })} onMouseLeave={() => setHover(null)}>
            {selected ? <circle cx={x} cy={y} r={20} className="cluster-map-dot-halo" /> : null}
            <circle cx={x} cy={y} r={selected ? 14 : 11.5} className="cluster-map-dot" />
            <text x={x} y={y + 3.5} textAnchor="middle">{point.rank}</text>
          </g>;
        })}
      </svg>
      {hover ? <HoverCard response={response} point={hover.point} x={hover.x} y={hover.y} /> : null}
    </div>
  );
}

function HoverCard({ response, point, x, y }: { response: ClusterMapResponse; point: ClusterMapPoint; x: number; y: number }) {
  const top = point.evidence.facet_share.map((share, index) => [share, index] as const).sort((a, b) => b[0] - a[0]).slice(0, 2);
  const left = x / SIZE > 0.6;
  return <div className="cluster-map-tooltip" role="tooltip"
    style={{ left: `${(x + MARGIN) / (SIZE + 2 * MARGIN) * 100}%`, top: `${y / SIZE * 100}%`, translate: left ? "calc(-100% - 14px) 10px" : "14px 10px" }}>
    <span className="cluster-map-tooltip-name"><strong>{point.seed ? "★ референс" : `#${point.rank}`}</strong> {displayTrack(point.track)}</span>
    <span className="cluster-map-tooltip-line">ближе к референсам {percent(point.evidence.percentile)} библиотеки · D {point.evidence.distance?.toFixed(2) ?? "—"}</span>
    {point.seed ? null : <span className="cluster-map-tooltip-line">вклад: {top.map(([share, index]) => `${response.facets[index].label} ${Math.round(share * 100)}%`).join(", ")}</span>}
  </div>;
}

export function percent(value: number | null | undefined, digits = 0) {
  return value === null || value === undefined ? "—" : `${value.toFixed(digits)}%`;
}

function star(x: number, y: number, r: number) {
  let path = "";
  for (let i = 0; i < 10; i += 1) {
    const angle = -Math.PI / 2 + i * Math.PI / 5;
    const size = i % 2 ? r * 0.45 : r;
    path += `${i ? "L" : "M"}${(x + size * Math.cos(angle)).toFixed(1)},${(y + size * Math.sin(angle)).toFixed(1)}`;
  }
  return `${path}Z`;
}

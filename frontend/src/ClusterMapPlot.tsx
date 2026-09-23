import { useState } from "react";
import type { ClusterMapPoint, ClusterMapResponse } from "./api";
import { displayTrack } from "./trackDisplay";

const SIZE = 600;
const CENTRE = SIZE / 2;
const RADIUS = 236;
// Room beside the circle for the longest facet labels.
const MARGIN = 90;
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

  return (
    <div className="cluster-map-plot-frame">
      <svg className="cluster-map-plot" viewBox={`${-MARGIN} 0 ${SIZE + 2 * MARGIN} ${SIZE}`} role="img"
        aria-label={facet === null ? "Кандидаты вокруг референсов по итоговому расстоянию SONARA" : `Кандидаты по грани «${facets[facet].label}»`}>
        {facets.map((item, index) => {
          const [x1, y1] = at(RADIUS, anchor(index) - half);
          const [x2, y2] = at(RADIUS, anchor(index) + half);
          const [lx, ly] = at(RADIUS + 20, anchor(index));
          const cos = Math.cos(anchor(index));
          return <g key={item.key}>
            <path d={`M${CENTRE},${CENTRE} L${x1},${y1} A${RADIUS},${RADIUS} 0 0 1 ${x2},${y2} Z`}
              className="cluster-map-sector" data-facet={index} data-active={facet === index || undefined} />
            <text x={lx} y={ly + 4} className="cluster-map-sector-label" data-facet={index}
              textAnchor={Math.abs(cos) < 0.3 ? "middle" : cos > 0 ? "start" : "end"}>{item.label}</text>
          </g>;
        })}
        {rings.map((ring) => <g key={ring.percentile}>
          <circle cx={CENTRE} cy={CENTRE} r={radius(ring.distance)} className="cluster-map-ring" data-typical={ring.percentile === 50 || undefined} />
          <text x={CENTRE + 3} y={CENTRE - radius(ring.distance) - 3} className="cluster-map-ring-label">{ring.percentile}%</text>
        </g>)}
        {facet === null && response.reference.core_distance > 0
          ? <circle cx={CENTRE} cy={CENTRE} r={radius(response.reference.core_distance)} className="cluster-map-core" /> : null}
        {seeds.map((point) => {
          const [x, y] = at(radius(value(point) ?? 0), point.evidence.angle);
          return <path key={point.track.track_id} className="cluster-map-reference" d={star(x, y, 10)}
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
            <circle cx={x} cy={y} r={selected ? 13 : 10.5} />
            <text x={x} y={y + 3.5} textAnchor="middle">{point.rank}</text>
            {(value(point) ?? 0) > edge ? <text x={x} y={y - 15} textAnchor="middle" className="cluster-map-clipped">↗</text> : null}
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

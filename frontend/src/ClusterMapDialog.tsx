import { CircleAlert, Pause, Play, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { api, type ClusterMapBands, type ClusterMapPoint, type ClusterMapResponse, type Track } from "./api";
import { pluralRu } from "./audioDedupView";
import { ClusterMapPlot, DIFFUSE_FOCUS, percent } from "./ClusterMapPlot";
import { isAbortError } from "./errors";
import { seedSearchModelPresentation, tabAfterKey } from "./searchSurfaceState";
import { displayTrack } from "./trackDisplay";
import type { ClusterMapEntry } from "./useClusterMap";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

type RailTab = "candidate" | "output" | "method";
const railTabs: readonly RailTab[] = ["candidate", "output", "method"];
const railLabels: Record<RailTab, string> = { candidate: "Кандидат", output: "Выдача", method: "Метод" };
const bandLabels = ["Бас и бочка, 20–150 Гц", "Низкая середина, 150–600 Гц", "Середина, 0,6–3 кГц", "Верх, 3–11 кГц"];
// Fixed reading rules, identical for every output: a facet is kept when at most
// 10% of the library is closer to the references, and differs past 50%.
const KEPT = 10;
const DIFFERS = 50;
const FOCUSABLE = "button:not([disabled]):not([tabindex='-1']), summary, [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

/** One in-memory model ranking, explained by SONARA alone around its references. */
export function ClusterMapDialog({ entry, open, layerState, playingTrackId, onPreview, onClose, onRetry }: {
  entry: ClusterMapEntry;
  open: boolean;
  layerState: EmbeddingLayerState;
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
  onClose: () => void;
  onRetry: () => void;
}) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const pressedOnBackdrop = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [tab, setTab] = useState<RailTab>("candidate");
  const [facet, setFacet] = useState<number | null>(null);
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const [sort, setSort] = useState<"rank" | "distance">("rank");
  const { payload, response } = entry;
  const candidates = useMemo(() => response?.points.filter((point) => !point.seed) ?? [], [response]);
  const seeds = useMemo(() => response?.points.filter((point) => point.seed) ?? [], [response]);
  const selected = candidates.find((point) => point.track.track_id === selectedTrackId) ?? null;
  const layer = payload.layer ?? null;
  const layerRow = layerState.layers?.find((row) => row.layer === layer);
  const seedCount = payload.seed_track_ids.length;
  const summaryText = `${seedCount} ${pluralRu(seedCount, "референс", "референса", "референсов")} · ${response ? candidates.length : `до ${payload.limit}`} кандидатов`;

  useEffect(() => {
    if (!open) return;
    sectionRef.current?.focus({ preventScroll: true });
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      requestClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  useEffect(() => { panelRef.current?.scrollTo({ top: 0 }); }, [selectedTrackId, tab]);

  function requestClose() {
    const active = document.activeElement;
    const restoreFocus = !active || active === document.body || Boolean(sectionRef.current?.contains(active));
    onCloseRef.current();
    if (restoreFocus) document.getElementById("cluster-map-button")?.focus();
  }

  function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return;
    const section = event.currentTarget;
    const focusable = [...section.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((element) => element.getClientRects().length > 0);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) { event.preventDefault(); return; }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === section)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
  }

  function selectTabByKey(event: KeyboardEvent<HTMLButtonElement>) {
    const target = tabAfterKey(railTabs, tab, event.key);
    if (!target) return;
    event.preventDefault();
    setTab(target);
    document.getElementById(`cluster-map-tab-${target}`)?.focus();
  }

  function selectCandidate(trackId: number) {
    setSelectedTrackId(trackId);
    setTab("candidate");
    // In the one-column layout the evidence sits below the map.
    requestAnimationFrame(() => panelRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }

  return (
    <div className="cluster-map-backdrop" role="presentation" data-open={open ? "true" : "false"} inert={!open}
      onPointerDown={(event) => { pressedOnBackdrop.current = event.target === event.currentTarget; }}
      onClick={(event) => {
        const fromBackdrop = pressedOnBackdrop.current && event.target === event.currentTarget;
        pressedOnBackdrop.current = false;
        if (fromBackdrop) requestClose();
      }}>
      <section ref={sectionRef} className="cluster-map-dialog" role="dialog" aria-modal="true" aria-labelledby="cluster-map-title"
        aria-describedby="cluster-map-summary" aria-busy={entry.status === "loading" || undefined} tabIndex={-1} onKeyDown={keepFocusInside}>
        <header className="cluster-map-header">
          <div className="cluster-map-heading">
            <h2 id="cluster-map-title">Карта выдачи</h2>
            <span className="cluster-map-chip">{seedSearchModelPresentation[payload.analysis_family].label}</span>
            {layer !== null ? <span className="cluster-map-chip" title={[layerRow?.source, layerState.note].filter(Boolean).join("\n") || undefined}>L{layer}</span> : null}
            {layerRow?.label ? <span className="cluster-map-layer-hint">{layerRow.label}</span> : null}
          </div>
          <p id="cluster-map-summary" className="cluster-map-summary">{summaryText} · свойства по SONARA вокруг референсов</p>
          <div className="cluster-map-header-actions">
            {entry.status === "ready" ? <button type="button" title="Повторить поиск и расчёт по текущим данным библиотеки" onClick={onRetry}><RotateCcw size={13} />Пересчитать</button> : null}
            <button className="icon-button" type="button" title="Закрыть" aria-label="Закрыть" onClick={requestClose}><X size={16} /></button>
          </div>
        </header>
        {entry.status === "loading" ? (
          <div className="cluster-map-body"><p className="cluster-map-status" role="status">
            Измеряем выдачу по SONARA. Первая карта в библиотеке сначала калибрует шкалы по выборке библиотеки — это до минуты.
          </p></div>
        ) : entry.status === "error" ? (
          <div className="cluster-map-body"><div className="cluster-map-error" role="alert">
            <CircleAlert size={18} aria-hidden="true" /><div><strong>Не удалось построить карту</strong><p>{entry.error}</p></div>
            <button type="button" onClick={onRetry}>Повторить</button>
          </div></div>
        ) : response ? (
          <div className="cluster-map-body">
            <div className="cluster-map-main">
              <figure className="cluster-map-figure">
                <div className="cluster-map-figure-head">
                  <label className="cluster-map-facet-select">Радиус
                    <select value={facet ?? ""} onChange={(event) => setFacet(event.target.value === "" ? null : Number(event.target.value))}>
                      <option value="">все грани — итоговое расстояние</option>
                      {response.facets.map((item, index) => <option key={item.key} value={index}>только «{item.label}»</option>)}
                    </select>
                  </label>
                  <span className="cluster-map-status">дальше {KEPT}% ближайших треков библиотеки: {candidates.filter((point) => (point.evidence.percentile ?? 0) > KEPT).length} из {candidates.length}</span>
                </div>
                <ClusterMapPlot response={response} facet={facet} selectedTrackId={selected?.track.track_id ?? null} onSelect={selectCandidate} />
                <figcaption className="cluster-map-legend">
                  {facet === null
                    ? <>Радиус — расстояние SONARA до медианы референсов, та же величина, что раскладывается в объяснении. Угол — какие грани дают это расстояние. Кольца — доля библиотеки, которая ближе к референсам; пунктир 50% — обычный трек. ★ — референсы, голубой круг — типичный референс, число — место в выдаче модели, пунктирная обводка — причина размыта по граням. Расстояния между кандидатами карта не показывает.</>
                    : <>Радиус — расстояние только по грани «{response.facets[facet].label}»: 1 = обычный трек библиотеки на этой грани. Угол прежний.</>}
                </figcaption>
                <FacetTable response={response} seeds={seeds} candidates={candidates} sort={sort} onSort={setSort}
                  selectedTrackId={selected?.track.track_id ?? null} onSelect={selectCandidate} />
              </figure>
              <aside className="cluster-map-rail" aria-label="Подробности">
                <div className="search-tabs cluster-map-tabs" role="tablist" aria-label="Разделы карты">
                  {railTabs.map((name) => <button key={name} id={`cluster-map-tab-${name}`} className={`model-search-tab ${tab === name ? "active" : ""}`}
                    role="tab" aria-selected={tab === name} aria-controls={`cluster-map-panel-${name}`} tabIndex={tab === name ? 0 : -1}
                    type="button" onClick={() => setTab(name)} onKeyDown={selectTabByKey}>{railLabels[name]}</button>)}
                </div>
                <div ref={panelRef} id={`cluster-map-panel-${tab}`} className="cluster-map-tab-panel" role="tabpanel" aria-labelledby={`cluster-map-tab-${tab}`}>
                  {tab === "candidate"
                    ? selected
                      ? <CandidatePanel key={selected.track.track_id} response={response} point={selected} seeds={seeds} playingTrackId={playingTrackId} onPreview={onPreview} />
                      : <EmptyCandidate candidates={candidates} onSelect={selectCandidate} />
                    : tab === "output"
                      ? <OutputPanel response={response} seeds={seeds} candidates={candidates} onSelect={selectCandidate} />
                      : <MethodPanel response={response} />}
                </div>
              </aside>
            </div>
          </div>
        ) : null}
        <footer className="cluster-map-footer">Карта считается только по измерениям SONARA; модель задаёт лишь состав и порядок выдачи. Музыкальный смысл закономерностей подтверждает слух.</footer>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ shared bits

function FacetDot({ index }: { index: number }) {
  return <span className="cluster-map-facet-dot" style={{ background: `var(--cluster-f${index})` }} aria-hidden="true" />;
}

function PercentCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <td className="cluster-map-cell">—</td>;
  const close = value <= 50;
  const strength = Math.round(Math.abs(50 - value) / 50 * (close ? 78 : 70));
  return <td className="cluster-map-cell" data-strong={strength > 45 || undefined}
    style={{ background: `color-mix(in srgb, var(${close ? "--cluster-kept" : "--cluster-differs"}) ${strength}%, var(--surface-muted))` }}>
    {value.toFixed(0)}</td>;
}

function verdict(value: number | null | undefined): [string, "kept" | "differs" | ""] {
  if (value === null || value === undefined) return ["нет данных", ""];
  if (value <= KEPT) return ["сохраняется", "kept"];
  if (value < DIFFERS) return ["частично", ""];
  return ["отличается", "differs"];
}

function signed(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(digits)}`;
}

function formatValue(unit: string, value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  if (unit === "Гц") return `${value.toFixed(0)} Гц`;
  if (unit === "доля") return `${(value * 100).toFixed(1)}%`;
  if (unit === "LUFS" || unit === "LU" || unit === "дБ") return `${value.toFixed(1)} ${unit}`;
  if (unit === "уд/мин") return value.toFixed(1);
  return value.toFixed(Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 3);
}

function minutes(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function PlayButton({ track, playingTrackId, onPreview }: { track: Track; playingTrackId: number | null; onPreview: (track: Track) => void }) {
  const playing = playingTrackId === track.track_id;
  const action = playing ? "Пауза" : "Прослушать";
  return <button className="icon-button cluster-map-play-button" data-playing={playing || undefined} title={action} aria-label={`${action}: ${displayTrack(track)}`} type="button" onClick={() => onPreview(track)}>{playing ? <Pause size={13} /> : <Play size={13} />}</button>;
}

function FacetTable({ response, seeds, candidates, sort, onSort, selectedTrackId, onSelect }: {
  response: ClusterMapResponse;
  seeds: ClusterMapPoint[];
  candidates: ClusterMapPoint[];
  sort: "rank" | "distance";
  onSort: (sort: "rank" | "distance") => void;
  selectedTrackId: number | null;
  onSelect: (trackId: number) => void;
}) {
  const rows = sort === "rank" ? candidates : [...candidates].sort((a, b) => (a.evidence.distance ?? Infinity) - (b.evidence.distance ?? Infinity));
  const row = (point: ClusterMapPoint) => <tr key={point.track.track_id} data-seed={point.seed || undefined}
    data-selected={point.track.track_id === selectedTrackId || undefined} onClick={point.seed ? undefined : () => onSelect(point.track.track_id)}>
    <td className="cluster-map-cell-rank">{point.seed ? "★" : point.rank}</td>
    <td className="cluster-map-cell-name" title={displayTrack(point.track)}>{displayTrack(point.track)}</td>
    {point.evidence.facet_percentile.map((value, index) => <PercentCell key={index} value={value} />)}
    <PercentCell value={point.evidence.percentile} />
  </tr>;
  return <section className="cluster-map-facet-table">
    <div className="cluster-map-facet-table-head">
      <h3>Грани по кандидатам</h3>
      <span className="cluster-map-status">сколько библиотеки ближе к референсам, %</span>
      <span className="cluster-map-sort" role="group" aria-label="Порядок строк">
        <button type="button" aria-pressed={sort === "rank"} onClick={() => onSort("rank")} title="Порядок модели">ранг</button>
        <button type="button" aria-pressed={sort === "distance"} onClick={() => onSort("distance")} title="По расстоянию SONARA">SONARA</button>
      </span>
    </div>
    <div className="cluster-map-table-scroll"><table>
      <thead><tr><th>#</th><th>Трек</th>{response.facets.map((item, index) => <th key={item.key} title={item.label}><FacetDot index={index} />{item.label.split(" ")[0]}</th>)}<th>Итог</th></tr></thead>
      <tbody>{seeds.map(row)}{rows.map(row)}</tbody>
    </table></div>
  </section>;
}

// ------------------------------------------------------------------ charts

type Series = { x: number[]; y: number[]; kind: "candidate" | "reference" };

function LineChart({ series, xMax, yMin, yMax, shades = [], yDigits = 1 }: {
  series: Series[]; xMax: number; yMin: number; yMax: number; shades?: [number, number][]; yDigits?: number;
}) {
  const width = 320, height = 112, left = 32, bottom = 16, top = 6, right = 6;
  const plotW = width - left - right, plotH = height - bottom - top;
  const x = (value: number) => left + value / (xMax || 1) * plotW;
  const y = (value: number) => top + (1 - (Math.min(yMax, Math.max(yMin, value)) - yMin) / (yMax - yMin || 1)) * plotH;
  return <svg viewBox={`0 0 ${width} ${height}`} className="cluster-map-chart" aria-hidden="true">
    {shades.map(([a, b], index) => <rect key={index} x={x(a)} y={top} width={Math.max(1, x(b) - x(a))} height={plotH} className="cluster-map-chart-shade" />)}
    <line x1={left} y1={top + plotH} x2={left + plotW} y2={top + plotH} className="cluster-map-chart-axis" />
    {[yMin, (yMin + yMax) / 2, yMax].map((value) => <text key={value} x={left - 3} y={y(value) + 3} textAnchor="end" className="cluster-map-chart-tick">{value.toFixed(yDigits)}</text>)}
    {[0, 0.25, 0.5, 0.75, 1].map((share) => <text key={share} x={x(xMax * share)} y={height - 4} textAnchor="middle" className="cluster-map-chart-tick">{minutes(xMax * share)}</text>)}
    {series.map((item, index) => <polyline key={index} className={`cluster-map-chart-${item.kind}`} fill="none"
      points={item.y.map((value, i) => `${x(item.x[i]).toFixed(1)},${y(value).toFixed(1)}`).join(" ")} />)}
  </svg>;
}

function ProfileChart({ labels, candidate, references, band, digits = 1 }: {
  labels: string[]; candidate: (number | null)[]; references: (number | null)[][]; band: [number, number][]; digits?: number;
}) {
  const width = 320, height = 118, left = 34, bottom = 18, top = 6, right = 6;
  const values = [...candidate, ...references.flat(), ...band.flat()].filter((v): v is number => v !== null && Number.isFinite(v));
  let low = Math.min(...values), high = Math.max(...values);
  const pad = (high - low) * 0.08 || 1; low -= pad; high += pad;
  const plotW = width - left - right, plotH = height - bottom - top;
  const x = (i: number) => left + (labels.length === 1 ? plotW / 2 : i / (labels.length - 1) * plotW);
  const y = (v: number) => top + (1 - (v - low) / (high - low)) * plotH;
  const line = (row: (number | null)[]) => row.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ");
  return <svg viewBox={`0 0 ${width} ${height}`} className="cluster-map-chart" aria-hidden="true">
    <polygon className="cluster-map-chart-band" points={`${band.map(([, hi], i) => `${x(i)},${y(hi)}`).join(" ")} ${band.map(([lo], i) => `${x(i)},${y(lo)}`).reverse().join(" ")}`} />
    <line x1={left} y1={top + plotH} x2={left + plotW} y2={top + plotH} className="cluster-map-chart-axis" />
    {[low + pad, high - pad].map((v) => <text key={v} x={left - 3} y={y(v) + 3} textAnchor="end" className="cluster-map-chart-tick">{v.toFixed(digits)}</text>)}
    {labels.map((label, i) => <text key={label + i} x={x(i)} y={height - 5} textAnchor="middle" className="cluster-map-chart-tick">{label}</text>)}
    {references.map((row, index) => <polyline key={index} className="cluster-map-chart-reference" fill="none" points={line(row)} />)}
    <polyline className="cluster-map-chart-candidate" fill="none" points={line(candidate)} />
    {candidate.map((v, i) => (v === null ? null : <circle key={i} cx={x(i)} cy={y(v)} r={2.4} className="cluster-map-chart-dot" />))}
  </svg>;
}

/** Library normal scores: band p5–p95, darker IQR; reference ticks; the candidate dot. */
function Strip({ candidate, references }: { candidate: number | null; references: (number | null)[] }) {
  const width = 150, x = (z: number) => 4 + (Math.max(-3, Math.min(3, z)) + 3) / 6 * (width - 8);
  return <svg viewBox={`0 0 ${width} 18`} width={width} height={18} className="cluster-map-strip" aria-hidden="true">
    <rect x={x(-1.645)} y={5} width={x(1.645) - x(-1.645)} height={8} rx={2} className="cluster-map-strip-library" />
    <rect x={x(-0.674)} y={5} width={x(0.674) - x(-0.674)} height={8} className="cluster-map-strip-iqr" />
    <line x1={x(0)} x2={x(0)} y1={3} y2={15} className="cluster-map-strip-median" />
    {references.map((z, i) => (z === null ? null : <line key={i} x1={x(z)} x2={x(z)} y1={2} y2={16} className="cluster-map-strip-reference" />))}
    {candidate === null ? null : <circle cx={x(candidate)} cy={9} r={4} className="cluster-map-strip-candidate" />}
  </svg>;
}

function Chart({ title, note, aside, children }: { title: string; note?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return <div className="cluster-map-chart-card">
    <div className="cluster-map-chart-caption"><span>{title}</span>{aside ? <span>{aside}</span> : null}</div>
    {children}
    {note ? <p className="cluster-map-note">{note}</p> : null}
  </div>;
}

// ------------------------------------------------------------------ candidate tab

function EmptyCandidate({ candidates, onSelect }: { candidates: ClusterMapPoint[]; onSelect: (id: number) => void }) {
  const far = [...candidates].sort((a, b) => (b.evidence.distance ?? -1) - (a.evidence.distance ?? -1))[0];
  return <div className="empty-state cluster-map-empty">
    <p>Выберите кандидата на карте или в таблице граней — здесь появится, чем он похож на референсы и чем отличается.</p>
    {far ? <button type="button" onClick={() => onSelect(far.track.track_id)}>Открыть самого далёкого: #{far.rank} {displayTrack(far.track)}</button> : null}
  </div>;
}

function CandidatePanel({ response, point, seeds, playingTrackId, onPreview }: {
  response: ClusterMapResponse; point: ClusterMapPoint; seeds: ClusterMapPoint[]; playingTrackId: number | null; onPreview: (track: Track) => void;
}) {
  const { evidence } = point;
  const nearest = seeds.find((seed) => seed.track.track_id === evidence.nearest_reference_id);
  const groups: Record<"kept" | "differs" | "", number[]> = { kept: [], differs: [], "": [] };
  evidence.facet_percentile.forEach((value, index) => groups[verdict(value)[1]].push(index));
  const top = evidence.contribution.map((value, index) => [value, index] as const).sort((a, b) => b[0] - a[0]).slice(0, 8);
  const byShare = evidence.facet_share.map((value, index) => [value, index] as const).sort((a, b) => b[0] - a[0]);
  const facetChips = (indexes: number[], kind: string) => indexes.length
    ? indexes.map((index) => <span key={index} className="cluster-map-reason" data-kind={kind || undefined}><FacetDot index={index} />{response.facets[index].label} · {percent(evidence.facet_percentile[index])}</span>)
    : <span className="cluster-map-note">—</span>;
  return <div className="cluster-map-candidate-panel">
    <header className="cluster-map-card-head"><PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
      <h3>#{point.rank} · {displayTrack(point.track)}</h3></header>
    <dl className="cluster-map-kpis">
      <div className="cluster-map-kpi"><dt>Библиотеки ближе</dt><dd className="cluster-map-kpi-value">{percent(evidence.percentile, 1)}</dd><dd className="cluster-map-kpi-note">к референсам, чем этот трек</dd></div>
      <div className="cluster-map-kpi"><dt>Расстояние D</dt><dd className="cluster-map-kpi-value">{evidence.distance?.toFixed(2) ?? "—"}</dd><dd className="cluster-map-kpi-note">типичный референс {response.reference.core_distance.toFixed(2)} · обычный трек {response.reference.rings.find((ring) => ring.percentile === 50)?.distance.toFixed(2)}</dd></div>
      <div className="cluster-map-kpi"><dt>Модель</dt><dd className="cluster-map-kpi-value">{point.similarity?.toFixed(3) ?? "—"}</dd><dd className="cluster-map-kpi-note">сходство, медиана библиотеки {response.library_similarity.toFixed(3)} — только происхождение</dd></div>
    </dl>
    {nearest ? <p className="cluster-map-prose">Ближайший референс по SONARA: <strong>{displayTrack(nearest.track)}</strong> · D {evidence.nearest_distance?.toFixed(2)}</p> : null}

    <section className="cluster-map-section"><h4>Что сохраняется и что отличается <small>— доля библиотеки, которая ближе к референсам по грани</small></h4>
      <div className="cluster-map-verdicts">
        <span className="cluster-map-note">сохраняется ≤{KEPT}%</span><div className="cluster-map-reasons">{facetChips(groups.kept, "kept")}</div>
        <span className="cluster-map-note">частично</span><div className="cluster-map-reasons">{facetChips(groups[""], "")}</div>
        <span className="cluster-map-note">отличается ≥{DIFFERS}%</span><div className="cluster-map-reasons">{facetChips(groups.differs, "differs")}</div>
      </div>
    </section>

    <section className="cluster-map-section"><h4>Из чего сложилось расстояние <small>— точные доли D², сумма 100%</small></h4>
      <div className="cluster-map-stack">{evidence.facet_share.map((share, index) => <span key={index} title={`${response.facets[index].label} ${Math.round(share * 100)}%`}
        style={{ width: `${share * 100}%`, background: `var(--cluster-f${index})` }} />)}</div>
      <div className="cluster-map-reasons">{byShare.map(([share, index]) => <span key={index} className="cluster-map-reason"><FacetDot index={index} />{response.facets[index].label} {Math.round(share * 100)}%</span>)}</div>
      <DescriptorTable response={response} point={point} seeds={seeds} indexes={top.map(([, index]) => index)} withFacet />
      <p className="cluster-map-note">Δ — отклонение от медианы референсов в σ библиотеки. «Реже» — у какой доли библиотеки отклонение от референсов ещё больше: 5% значит, что так отличается лишь каждый двадцатый трек.</p>
    </section>

    <MoodSection response={response} point={point} />
    <TimeEvidence response={response} point={point} seeds={seeds} />

    <section className="cluster-map-section"><h4>Все грани</h4>
      {byShare.map(([share, index]) => {
        const [label, kind] = verdict(evidence.facet_percentile[index]);
        const facet = response.facets[index];
        return <details key={facet.key} className="cluster-map-descriptors">
          <summary><FacetDot index={index} /><strong>{facet.label}</strong> <span className="cluster-map-reason" data-kind={kind || undefined}>{label}</span>
            <span className="cluster-map-note">ближе {percent(evidence.facet_percentile[index])} библиотеки · вклад {Math.round(share * 100)}% · вес {facet.weight}</span></summary>
          <p className="cluster-map-note">{facet.description}</p>
          <DescriptorTable response={response} point={point} seeds={seeds}
            indexes={response.descriptors.flatMap((item, j) => (item.facet === index ? [j] : []))} />
        </details>;
      })}
    </section>
    <Reliability response={response} point={point} seeds={seeds} />
  </div>;
}

function DescriptorTable({ response, point, seeds, indexes, withFacet = false }: {
  response: ClusterMapResponse; point: ClusterMapPoint; seeds: ClusterMapPoint[]; indexes: number[]; withFacet?: boolean;
}) {
  return <div className="cluster-map-table-scroll"><table className="cluster-map-descriptor-table">
    <thead><tr><th>Признак</th><th>кандидат · референсы · библиотека</th><th>Δ, σ</th><th>реже</th><th>вклад</th></tr></thead>
    <tbody>{indexes.map((j) => {
      const item = response.descriptors[j];
      const references = seeds.map((seed) => seed.values[j]).filter((v): v is number => v !== null);
      const range = !references.length ? "—" : references.length === 1 ? formatValue(item.unit, references[0])
        : `${formatValue(item.unit, Math.min(...references))} … ${formatValue(item.unit, Math.max(...references))}`;
      const delta = point.evidence.delta[j];
      return <tr key={item.key} data-major={point.evidence.contribution[j] > 0.08 || undefined}>
        <td>{withFacet ? <FacetDot index={item.facet} /> : null}{item.label}{item.note ? <small>{item.note}</small> : null}</td>
        <td><Strip candidate={point.scores[j]} references={seeds.map((seed) => seed.scores[j])} />
          <small>{formatValue(item.unit, point.values[j])} · реф. {range} · библ. {formatValue(item.unit, item.library_quantiles[2])}</small></td>
        <td className="cluster-map-number">{signed(delta)}<small>{delta === null ? "" : delta > 0.25 ? "выше" : delta < -0.25 ? "ниже" : "как у реф."}</small></td>
        <td className="cluster-map-number">{percent(point.evidence.rarity[j])}</td>
        <td className="cluster-map-number">{percent(point.evidence.contribution[j] * 100, 1)}</td>
      </tr>;
    })}</tbody>
  </table></div>;
}

function MoodSection({ response, point }: { response: ClusterMapResponse; point: ClusterMapPoint }) {
  const index = (key: string) => response.descriptors.findIndex((item) => item.key === key);
  const cue = (key: string, invert = false) => { const d = point.evidence.delta[index(key)]; return d === null || d === undefined ? null : invert ? -d : d; };
  const lines: { name: string; cues: [string, string, boolean?][]; up: string; down: string; caveat: string }[] = [
    { name: "Возбуждение", cues: [["energy_p50", "энергия"], ["lufs", "громкость"], ["onset_density", "плотность атак"]],
      up: "энергичнее референсов", down: "спокойнее референсов", caveat: "Громкость зависит и от мастеринга; атаки добавляют и хэты." },
    { name: "Светлость ↔ тёмность", cues: [["mode_chroma", "мажорность хромы"], ["minor_share", "минорные аккорды", true], ["centroid", "яркость"]],
      up: "светлее (мажорнее, ярче)", down: "темнее (минорнее, глуше)", caveat: "Лад ≠ настроение: весёлый минорный хаус звучит светло; аккорды SONARA шумные." },
    { name: "Напряжение", cues: [["dissonance", "диссонанс"], ["flatness", "шумность"], ["contrast_7", "верхний контраст"]],
      up: "напряжённее", down: "мягче", caveat: "Шумность высока и у мягких хэтов — это спектр, а не эмоция." },
  ];
  return <section className="cluster-map-section cluster-map-mood"><h4>Настроение <small>— прочтение измерений, не измерение</small></h4>
    {lines.map((line) => {
      const values = line.cues.map(([key, label, invert]) => [label, cue(key, invert)] as const);
      const known = values.map(([, v]) => v).filter((v): v is number => v !== null);
      const mean = known.reduce((a, b) => a + b, 0) / (known.length || 1);
      const agree = known.length >= 2 && known.every((v) => Math.sign(v) === Math.sign(mean));
      const reading = !known.length ? "нет данных"
        : agree ? (Math.abs(mean) >= 0.5 ? (mean > 0 ? line.up : line.down) : "близко к референсам")
          : known.every((v) => Math.abs(v) < 0.5) ? "близко к референсам" : "признаки расходятся — вывода нет";
      return <div key={line.name} className="cluster-map-mood-row">
        <div><strong>{line.name}</strong><small>{line.caveat}</small></div>
        <div><div className="cluster-map-reasons">{values.map(([label, v]) => <span key={label} className="cluster-map-reason">{label} {signed(v)}σ</span>)}</div>
          <p className="cluster-map-prose">Прочтение: <strong>{reading}</strong> <small>(вывод — только когда все признаки в одну сторону и в среднем ≥ 0,5σ)</small></p></div>
      </div>;
    })}
    <p className="cluster-map-note">Эвристики SONARA Mood, Perceptual, Aggression и Vocalness в расчёт не входят. Прямого измерения настроения в данных нет.</p>
  </section>;
}

function breakSpans(energy: number[], hop: number): [number, number][] {
  const width = Math.max(1, Math.round(8 / hop));
  if (energy.length < width) return [];
  const smooth = energy.slice(0, energy.length - width + 1).map((_, i) => energy.slice(i, i + width).reduce((a, b) => a + b, 0) / width);
  const sorted = [...smooth].sort((a, b) => a - b);
  const threshold = 0.75 * sorted[Math.floor(0.95 * (sorted.length - 1))];
  const spans: [number, number][] = [];
  let start: number | null = null;
  [...smooth, Infinity].forEach((value, i) => {
    if (value < threshold && start === null) start = i;
    else if (value >= threshold && start !== null) { if ((i - start) * hop >= 8) spans.push([start * hop, i * hop]); start = null; }
  });
  return spans;
}

function TimeEvidence({ response, point, seeds }: { response: ClusterMapResponse; point: ClusterMapPoint; seeds: ClusterMapPoint[] }) {
  const [bands, setBands] = useState<Record<number, ClusterMapBands> | null>(null);
  const [bandsState, setBandsState] = useState<"idle" | "loading" | "failed">("idle");
  const tracks = [point, ...seeds];
  const index = (key: string) => response.descriptors.findIndex((item) => item.key === key);
  const unit = (key: string) => response.descriptors[index(key)].unit;
  const curves = point.curves;
  const refCurves = seeds.map((seed) => seed.curves).filter((c): c is NonNullable<typeof c> => c !== null);

  function loadBands() {
    const controller = new AbortController();
    setBandsState("loading");
    api.clusterMapBands(tracks.map((item) => item.track.track_id).slice(0, 16), { signal: controller.signal })
      .then((rows) => {
        const current = Object.fromEntries(rows.filter((row) => tracks.some((item) => item.track.track_id === row.track_id && item.track.track_uuid === row.track_uuid)).map((row) => [row.track_id, row]));
        setBands(current);
        setBandsState(rows.length ? "idle" : "failed");
      })
      .catch((cause: unknown) => { if (!isAbortError(cause)) setBandsState("failed"); });
  }

  if (!curves) return <section className="cluster-map-section"><h4>По ходу трека</h4><p className="cluster-map-note">У кандидата нет SONARA Timeline — временные доказательства недоступны.</p></section>;
  const energyMax = Math.max(...[curves, ...refCurves].map((c) => c.energy.length * c.energy_hop));
  const spans = breakSpans(curves.energy, curves.energy_hop);
  const loudAll = [curves, ...refCurves].flatMap((c) => c.loudness).filter((v) => v > -70);
  const loudMax = Math.max(...[curves, ...refCurves].map((c) => c.loudness.length * c.loudness_hop));
  const tempoAll = [curves, ...refCurves].flatMap((c) => c.tempo_values);
  const tempoMax = Math.max(...[curves, ...refCurves].map((c) => c.tempo_times[c.tempo_times.length - 1] ?? 0));
  const durationMax = Math.max(...tracks.map((item) => item.curves?.duration ?? 1));
  const profile = (keys: string[], scale = 1) => ({
    candidate: keys.map((key) => { const v = point.values[index(key)]; return v === null ? null : v * scale; }),
    references: seeds.map((seed) => keys.map((key) => { const v = seed.values[index(key)]; return v === null ? null : v * scale; })),
    band: keys.map((key) => { const q = response.descriptors[index(key)].library_quantiles; return [(q[1] ?? 0) * scale, (q[3] ?? 0) * scale] as [number, number]; }),
    share: keys.reduce((sum, key) => sum + point.evidence.contribution[index(key)], 0),
  });
  const groove = profile(["phase_on", "phase_e", "phase_and", "phase_a"], 100);
  const contrast = profile(Array.from({ length: 7 }, (_, i) => `contrast_${i + 1}`));
  const mfcc = profile(Array.from({ length: 12 }, (_, i) => `mfcc_${i + 1}`));
  const intervals = profile(Array.from({ length: 12 }, (_, i) => `interval_${i}`), 100);
  const pitch = profile(Array.from({ length: 12 }, (_, i) => `pitch_${i}`), 100);
  const breakShare = index("break_share"), minorShare = index("minor_share");

  return <section className="cluster-map-section"><h4>По ходу трека <small>— полное покрытие; у каждого трека своя ось времени</small></h4>
    <div className="cluster-map-chart-legend"><span data-kind="candidate">кандидат</span><span data-kind="reference">референсы</span><span data-kind="band">библиотека p25–p75</span><span data-kind="shade">брейки кандидата</span></div>
    <div className="cluster-map-charts">
      <Chart title="Энергия по времени" aside={`брейки ${formatValue("доля", point.values[breakShare])}`}
        note={<>Брейки кандидата: {spans.length ? spans.map(([a, b]) => `${minutes(a)}–${minutes(b)}`).join(", ") : "нет участков ниже 75% пика дольше 8 с"}. У референсов: {seeds.map((seed) => formatValue("доля", seed.values[breakShare])).join(" / ")} времени.</>}>
        <LineChart xMax={energyMax} yMin={0} yMax={1} shades={spans} series={[
          ...refCurves.map((c): Series => ({ kind: "reference", x: c.energy.map((_, i) => i * c.energy_hop), y: c.energy })),
          { kind: "candidate", x: curves.energy.map((_, i) => i * curves.energy_hop), y: curves.energy },
        ]} />
      </Chart>
      {loudAll.length ? <Chart title="Громкость, LUFS" aside={`LRA ${formatValue(unit("loudness_range"), point.values[index("loudness_range")])}`}>
        <LineChart xMax={loudMax} yMin={Math.floor(Math.min(...loudAll) / 3) * 3} yMax={Math.ceil(Math.max(...loudAll) / 3) * 3} yDigits={0} series={[
          ...refCurves.map((c): Series => ({ kind: "reference", x: c.loudness.map((_, i) => i * c.loudness_hop), y: c.loudness })),
          { kind: "candidate", x: curves.loudness.map((_, i) => i * curves.loudness_hop), y: curves.loudness },
        ]} />
      </Chart> : null}
      {tempoAll.length ? <Chart title="Темп по битам, уд/мин" aside={point.bpm_confidence !== null && point.bpm_confidence < 0.45 ? `⚠ BPM ненадёжен (${point.bpm_confidence.toFixed(2)})` : `уверенность ${point.bpm_confidence?.toFixed(2) ?? "—"}`}
        note={`Вес темпа в итоге ${response.facets.find((item) => item.key === "tempo")?.weight}; SONARA сворачивает октавы в диапазон библиотеки.`}>
        <LineChart xMax={tempoMax} yMin={Math.floor(Math.min(...tempoAll) - 2)} yMax={Math.ceil(Math.max(...tempoAll) + 2)} yDigits={0} series={[
          ...refCurves.map((c): Series => ({ kind: "reference", x: c.tempo_times, y: c.tempo_values })),
          { kind: "candidate", x: curves.tempo_times, y: curves.tempo_values },
        ]} />
      </Chart> : null}
      <Chart title="Грув: где внутри доли стоят атаки, %" aside={`вклад ${percent(groove.share * 100, 1)}`} note="Онсеты SONARA против сетки битов; кадр 23 мс — 1/16 различима, свинг нет.">
        <ProfileChart labels={["доля", "2-я 1/16", "«и»", "4-я 1/16"]} candidate={groove.candidate} references={groove.references} band={groove.band} digits={0} />
      </Chart>
      <Chart title="Лад аккордов по времени" aside="1-я строка — кандидат"
        note={<>Минорных аккордов: кандидат {formatValue("доля", point.values[minorShare])}, референсы {seeds.map((seed) => formatValue("доля", seed.values[minorShare])).join(" / ")}. Тоника по хроме {point.tonic} {point.tonic_mode === "minor" ? "минор" : "мажор"}; ключ SONARA {point.key_camelot ?? "—"} (уверенность {point.key_confidence?.toFixed(2) ?? "—"}).</>}>
        <svg viewBox={`0 0 320 ${tracks.length * 13 + 14}`} className="cluster-map-chart" aria-hidden="true">
          {tracks.map((item, row) => (item.curves?.mode_runs ?? []).map(([a, b, minor], i) => <rect key={`${row}-${i}`} x={a / durationMax * 320} y={row * 13}
            width={Math.max(0.5, (b - a) / durationMax * 320)} height={9} className="cluster-map-mode" data-minor={minor || undefined} data-reference={row > 0 || undefined} />))}
          <text x={0} y={tracks.length * 13 + 10} className="cluster-map-chart-tick">0:00</text>
          <text x={320} y={tracks.length * 13 + 10} textAnchor="end" className="cluster-map-chart-tick">{minutes(durationMax)}</text>
        </svg>
        <div className="cluster-map-chart-legend"><span data-kind="minor">минор</span><span data-kind="major">мажор</span></div>
      </Chart>
      <Chart title="Спектральный контраст по 7 полосам, дБ" aside={`вклад ${percent(contrast.share * 100, 1)}`} note="Полоса 1 — низ, 7 — верх; среднее по всему треку.">
        <ProfileChart labels={["1", "2", "3", "4", "5", "6", "7"]} candidate={contrast.candidate} references={contrast.references} band={contrast.band} digits={0} />
      </Chart>
      <Chart title="Тембр: MFCC 1–12" aside={`вклад ${percent(mfcc.share * 100, 1)}`}>
        <ProfileChart labels={Array.from({ length: 12 }, (_, i) => String(i + 1))} candidate={mfcc.candidate} references={mfcc.references} band={mfcc.band} digits={0} />
      </Chart>
      <Chart title="Тональный профиль от тоники, %" aside={`вклад ${percent(intervals.share * 100, 1)}`} note="Хрома, повёрнутая к собственной тонике: лад и ступени без привязки к высоте.">
        <ProfileChart labels={["I", "♭II", "II", "♭III", "III", "IV", "♯IV", "V", "♭VI", "VI", "♭VII", "VII"]} candidate={intervals.candidate} references={intervals.references} band={intervals.band} digits={0} />
      </Chart>
      <Chart title="Классы высот, %" aside={`вклад ${percent(pitch.share * 100, 1)}`}>
        <ProfileChart labels={["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]} candidate={pitch.candidate} references={pitch.references} band={pitch.band} digits={0} />
      </Chart>
      {bands ? bandLabels.map((label, band) => {
        const own = bands[point.track.track_id];
        const refs = seeds.map((seed) => bands[seed.track.track_id]).filter((row): row is ClusterMapBands => Boolean(row));
        if (!own) return null;
        const xMax = Math.max(...[own, ...refs].map((row) => row.bands[band].length * row.hop_seconds));
        return <Chart key={label} title={`Полоса: ${label}, дБ`} aside="по аудио, вне расчёта">
          <LineChart xMax={xMax} yMin={-45} yMax={0} yDigits={0} series={[
            ...refs.map((row): Series => ({ kind: "reference", x: row.bands[band].map((_, i) => i * row.hop_seconds), y: row.bands[band] })),
            { kind: "candidate", x: own.bands[band].map((_, i) => i * own.hop_seconds), y: own.bands[band] },
          ]} />
        </Chart>;
      }) : null}
    </div>
    {bands ? <p className="cluster-map-note">Полосы посчитаны по аудио (SONARA mel, окна 2 с, 0 дБ — самое громкое окно трека). По библиотеке они не откалиброваны и в расстояние не входят.</p>
      : <p className="cluster-map-note">
        <button type="button" disabled={bandsState === "loading"} onClick={loadBands}>{bandsState === "loading" ? "Читаем аудио…" : "Показать полосы по времени"}</button>{" "}
        {bandsState === "failed" ? "Аудио недоступно — полос нет." : "Читает аудио кандидата и референсов (только чтение), несколько секунд."}
      </p>}
  </section>;
}

function Reliability({ response, point, seeds }: { response: ClusterMapResponse; point: ClusterMapPoint; seeds: ClusterMapPoint[] }) {
  const notes: string[] = [];
  if (point.bpm_confidence !== null && point.bpm_confidence < 0.45) notes.push(`BPM кандидата ненадёжен (уверенность ${point.bpm_confidence.toFixed(2)}).`);
  const shaky = seeds.filter((seed) => seed.bpm_confidence !== null && seed.bpm_confidence < 0.45);
  if (shaky.length) notes.push(`BPM ненадёжен у референса: ${shaky.map((seed) => displayTrack(seed.track)).join(", ")}.`);
  const missing = response.descriptors.filter((_, j) => point.scores[j] === null).map((item) => item.label);
  if (missing.length) notes.push(`Нет измерения: ${missing.join(", ")} — грань посчитана по остальным признакам.`);
  if (point.evidence.focus < DIFFUSE_FOCUS) notes.push(`Угол точки условен: вклад размазан по граням (сосредоточенность ${point.evidence.focus.toFixed(2)}).`);
  if (point.key_confidence !== null && point.key_confidence < 0.5) notes.push(`Тональность SONARA неуверенная (${point.key_confidence.toFixed(2)}); лад держится на хроме и аккордах.`);
  return <section className="cluster-map-section"><h4>Достоверность</h4>
    {notes.length ? notes.map((note) => <p key={note} className="cluster-map-coverage">{note}</p>) : <p className="cluster-map-note">Особых оговорок нет.</p>}
  </section>;
}

// ------------------------------------------------------------------ output tab

function OutputPanel({ response, seeds, candidates, onSelect }: {
  response: ClusterMapResponse; seeds: ClusterMapPoint[]; candidates: ClusterMapPoint[]; onSelect: (id: number) => void;
}) {
  const { summary, facets, descriptors, reference } = response;
  const order = summary.preservation.map((item, index) => ({ ...item, index })).sort((a, b) => (a.median ?? 999) - (b.median ?? 999));
  const reading = (item: (typeof order)[number]): [string, string] => item.median === null ? ["нет данных", ""]
    : item.median <= KEPT && (item.q ?? 1) < 0.01 ? ["сильно сохраняется", "kept"]
      : item.median <= 25 && (item.q ?? 1) < 0.01 ? ["сохраняется", "kept"]
        : (item.p ?? 0) > 0.99 ? ["дальше случайного", "differs"]
          : (item.q ?? 1) < 0.05 ? ["слабо сохраняется", ""] : ["как случайный трек", "random"];
  const outside = [...candidates].filter((point) => (point.evidence.percentile ?? 0) > KEPT)
    .sort((a, b) => (b.evidence.distance ?? 0) - (a.evidence.distance ?? 0));
  return <div className="cluster-map-output">
    <section className="cluster-map-section"><h4>Какие свойства сохраняет выдача <small>— медиана по {summary.candidate_count} {pluralRu(summary.candidate_count, "кандидату", "кандидатам", "кандидатам")}; 50% — как у случайного трека</small></h4>
      <div className="cluster-map-table-scroll"><table className="cluster-map-descriptor-table">
        <thead><tr><th>Грань</th><th>библиотеки ближе (медиана)</th><th>q</th><th>вывод</th></tr></thead>
        <tbody>{order.map((item) => {
          const [label, kind] = reading(item);
          return <tr key={item.index}><td><FacetDot index={item.index} />{facets[item.index].label}</td>
            <td><div className="cluster-map-meter"><i style={{ width: `${item.median ?? 0}%`, background: `var(--cluster-f${item.index})` }} /><b /></div><small>{percent(item.median, 1)}</small></td>
            <td className="cluster-map-number">{item.q === null ? "—" : item.q < 0.001 ? "<0,001" : item.q.toFixed(3)}</td>
            <td><span className="cluster-map-reason" data-kind={kind || undefined}>{label}</span></td></tr>;
        })}</tbody>
      </table></div>
      <p className="cluster-map-note">Случайная выборка легла бы равномерно по 0–100%. Малая доля — модель по этой грани действительно тянет к референсам. q — поправка Бенджамини–Хохберга по граням. Грани коррелируют (см. «Метод»): сохранение тембра частично тянет за собой спектр.</p>
    </section>

    <section className="cluster-map-section"><h4>Держит ли порядок модели свойство глубже <small>— топ-{summary.depth} той же выдачи</small></h4>
      <div className="cluster-map-table-scroll"><table>
        <thead><tr><th>ранги</th>{facets.map((item, index) => <th key={item.key} title={item.label}><FacetDot index={index} />{item.label.split(" ")[0]}</th>)}<th>Итог</th></tr></thead>
        <tbody>{summary.gradient.map((bin) => <tr key={bin.first}><td className="cluster-map-cell-rank">{bin.first}–{bin.last}</td>
          {bin.facet_percentile.map((value, index) => <PercentCell key={index} value={value} />)}<PercentCell value={bin.percentile} /></tr>)}</tbody>
      </table></div>
      <p className="cluster-map-note">Связь «сходство модели ↔ близость SONARA» в топ-{summary.depth} (Спирмен): итог {signed(summary.rank_correlation)}; {summary.facet_rank_correlation.map((value, index) => `${facets[index].label.split(" ")[0]} ${signed(value)}`).join(", ")}. Около нуля — порядок модели по этой грани SONARA не следует.</p>
    </section>

    <section className="cluster-map-section"><h4>Общий сдвиг всей выдачи <small>— куда кандидаты согласованно уходят от референсов</small></h4>
      {summary.shifts.length ? <div className="cluster-map-table-scroll"><table className="cluster-map-descriptor-table">
        <thead><tr><th>Признак</th><th>референсы · медиана кандидатов</th><th>Δ</th><th>с одной стороны</th><th>куда</th></tr></thead>
        <tbody>{summary.shifts.map((shift) => {
          const item = descriptors[shift.descriptor];
          const centre = reference.centre[shift.descriptor];
          return <tr key={item.key}><td><FacetDot index={item.facet} />{item.label}</td>
            <td><Strip candidate={centre === null ? null : centre + shift.median} references={seeds.map((seed) => seed.scores[shift.descriptor])} /></td>
            <td className="cluster-map-number">{signed(shift.median)}σ</td><td className="cluster-map-number">{percent(shift.same_side * 100)}</td>
            <td>{shift.median > 0 ? "выше" : "ниже"}<small>{shift.toward_library ? "к обычному треку библиотеки" : "прочь от библиотеки"}</small></td></tr>;
        })}</tbody>
      </table></div> : <p className="cluster-map-note">Согласованного сдвига нет.</p>}
      <p className="cluster-map-note">Правило: |медиана Δ| ≥ 0,5σ и знаковый тест p &lt; 0,01. «К обычному треку» — кандидаты просто менее особенные, чем референсы (так сдвинулась бы и случайная выборка); «прочь от библиотеки» — модель уводит выдачу в свою сторону.</p>
    </section>

    <section className="cluster-map-section"><h4>Отдельные отклонения <small>— кандидаты, у которых больше {KEPT}% библиотеки ближе к референсам</small></h4>
      {outside.length ? <ul className="cluster-map-outliers">{outside.map((point) => {
        const [share, index] = point.evidence.facet_share.map((value, i) => [value, i] as const).sort((a, b) => b[0] - a[0])[0];
        return <li key={point.track.track_id}><button type="button" onClick={() => onSelect(point.track.track_id)}>
          <strong>#{point.rank} {displayTrack(point.track)}</strong>
          <span>ближе {percent(point.evidence.percentile, 1)} библиотеки · главное: <FacetDot index={index} />{facets[index].label} {Math.round(share * 100)}%</span>
        </button></li>;
      })}</ul> : <p className="cluster-map-note">Все кандидаты среди {KEPT}% ближайших к референсам треков библиотеки.</p>}
    </section>
  </div>;
}

// ------------------------------------------------------------------ method tab

function MethodPanel({ response }: { response: ClusterMapResponse }) {
  const { facets, descriptors, reference } = response;
  return <div className="cluster-map-output">
    <section className="cluster-map-section"><h4>Как считается карта</h4>
      <ol className="cluster-map-method">
        <li><strong>Кандидаты</strong> — ровно выдача поиска: модель и слой задают только состав и порядок. Их имя и оценки в расчёт SONARA не входят.</li>
        <li><strong>Признаки</strong> — только измерения SONARA по всему треку: Core и Timeline (биты, онсеты, энергия, громкость, аккорды, сегменты). Mood, Perceptual, Aggression и Vocalness не читаются.</li>
        <li><strong>Шкалы</strong> — QuantileTransformer по фиксированной выборке {response.background_count.toLocaleString("ru-RU")} из {response.library_count.toLocaleString("ru-RU")} треков библиотеки: 1 = одна σ библиотеки. Выдача в обучении шкал не участвует и не может подтвердить сама себя.</li>
        <li><strong>Центр</strong> — медиана референсов по каждому признаку: одна ошибка детекции у одного референса центр не сдвигает.</li>
        <li><strong>Грань</strong> — взвешенное среднее квадратов Δ её признаков; вес ∝ 1 / Σρ² корреляций внутри грани, поэтому почти одинаковые признаки делят один голос. Затем грань делится на значение обычного трека библиотеки.</li>
        <li><strong>Итог</strong> D = √(Σ W·грань² / ΣW); веса граней заданы заранее и одинаковы для всех моделей и слоёв: {facets.map((item) => `${item.label} ${item.weight}`).join(", ")}.</li>
        <li><strong>Объяснение</strong> — точное разложение того же D² на вклады признаков; радиус точки — тот же D. «Библиотеки ближе» — перцентиль D среди выборки библиотеки для этих же референсов.</li>
        <li><strong>Угол</strong> — доли вклада граней (RadViz) с фиксированными секторами. Это единственное условное место карты.</li>
        <li><strong>Сохранение грани</strong> — медиана перцентилей кандидатов против равномерного распределения, z-тест среднего, поправка Бенджамини–Хохберга.</li>
      </ol>
    </section>
    <section className="cluster-map-section"><h4>Структура граней в библиотеке <small>— PCA, доля дисперсии</small></h4>
      <div className="cluster-map-table-scroll"><table className="cluster-map-descriptor-table">
        <thead><tr><th>Грань</th><th>PC1</th><th>PC2</th><th>PC3</th></tr></thead>
        <tbody>{facets.map((item, index) => <tr key={item.key}><td><FacetDot index={index} />{item.label}</td>
          {[0, 1, 2].map((k) => <td key={k} className="cluster-map-number">{item.explained_variance[k] === undefined ? "—" : percent(item.explained_variance[k] * 100)}</td>)}</tr>)}</tbody>
      </table></div>
      <p className="cluster-map-note">Веса признаков внутри граней: {descriptors.map((item) => `${item.label} ${Math.round(item.weight * 100)}%`).join(" · ")}.</p>
    </section>
    <section className="cluster-map-section"><h4>Насколько грани независимы <small>— корреляция расстояний граней по библиотеке</small></h4>
      <div className="cluster-map-table-scroll"><table>
        <thead><tr><th />{facets.map((item, index) => <th key={item.key} title={item.label}><FacetDot index={index} />{item.label.split(" ")[0]}</th>)}</tr></thead>
        <tbody>{reference.facet_correlation.map((row, i) => <tr key={i}><td className="cluster-map-cell-name"><FacetDot index={i} />{facets[i].label}</td>
          {row.map((value, k) => <td key={k} className="cluster-map-cell" style={i === k ? undefined : { background: `color-mix(in srgb, var(--accent) ${Math.round(Math.max(0, value) * 80)}%, var(--surface-muted))` }}>{i === k ? "" : value.toFixed(2)}</td>)}</tr>)}</tbody>
      </table></div>
      <p className="cluster-map-note">От 0,5 и выше две грани во многом меряют одно. Гармония и высота обе опираются на хрому.</p>
    </section>
    <section className="cluster-map-section"><h4>Чего данные не позволяют</h4>
      <ul className="cluster-map-method">
        <li><strong>Настроение</strong> прямо не измерено — только прочтение физических признаков с оговорками.</li>
        <li><strong>Темп</strong>: SONARA сворачивает BPM в диапазон библиотеки и ошибается в октаве; вес снижен, центр — медиана.</li>
        <li><strong>Полосы по времени</strong> в базе не хранятся: их кривые читаются из аудио по запросу и в расстояние не входят; текстура в расчёте — средний контраст 7 полос.</li>
        <li><strong>Грув</strong>: сетка кадров 23 мс — 1/16 различима, микротайминг и свинг нет.</li>
        <li><strong>Аккорды</strong> SONARA шумные, поэтому лад опирается ещё и на хрому. <strong>Вокал</strong> не оценивается.</li>
      </ul>
    </section>
  </div>;
}

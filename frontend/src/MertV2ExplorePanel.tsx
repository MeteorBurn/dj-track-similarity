import { useEffect, useId, useRef, useState } from "react";
import { LocateFixed, Map, Maximize, Minus, Plus, RefreshCw } from "lucide-react";
import type { Track } from "./api";
import { TrackList } from "./TrackRows";
import { displayTrack } from "./trackDisplay";
import { useMertV2Explorer } from "./useMertV2Explorer";
import { MertV2LayerSelect } from "./MertV2LayerSelect";
import type { MertV2LayerState } from "./useMertV2Layers";

type Props = {
  layerState: MertV2LayerState;
  databaseIdentity: string | null;
  catalogUuid: string | null;
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  playingTrackId: number | null;
  previewTrackId: number | null;
  onSeed: (track: Track) => void;
  onToggleLiked: (track: Track) => Promise<Track | null>;
  onTogglePlaylist: (track: Track) => void;
  onAddTracks: (tracks: Track[]) => void;
  onPreview: (track: Track) => void;
  onSeekPreview: (track: Track, seconds: number) => void;
  onDetails: (track: Track) => void;
};

const initialView = { scale: 1, x: 0, y: 0 };
const clampOffset = (value: number, scale: number) => Math.max(1 - scale, Math.min(0, value));

function zoomView(view: typeof initialView, factor: number, x = 0.5, y = 0.5) {
  const scale = Math.max(1, Math.min(8, view.scale * factor));
  return { scale, x: clampOffset(x - (x - view.x) * scale / view.scale, scale), y: clampOffset(y - (y - view.y) * scale / view.scale, scale) };
}

export function MertV2ExplorePanel(props: Props) {
  const map = useMertV2Explorer(props.databaseIdentity, props.catalogUuid, props.layerState.layer);
  const [clusterCount, setClusterCount] = useState(8);
  const [group, setGroup] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [showRepresentatives, setShowRepresentatives] = useState(false);
  const [view, setView] = useState(initialView);
  const [panning, setPanning] = useState(false);
  const plotRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: number; x: number; y: number; view: typeof initialView } | null>(null);
  const dragged = useRef(false);
  const clipId = useId();
  useEffect(() => {
    setGroup(null);
    setSelectedId(null);
    setPage(0);
    setView(initialView);
    drag.current = null;
    setPanning(false);
  }, [props.layerState.layer]);
  const points = map.data?.points ?? [];
  const hasPoints = points.length > 0;
  useEffect(() => {
    const plot = plotRef.current;
    if (!plot) return;
    function wheel(event: WheelEvent) {
      event.preventDefault();
      if (drag.current) return;
      const rect = plot!.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, ((event.clientX - rect.left) / rect.width - 0.06) / 0.88));
      const y = Math.max(0, Math.min(1, ((event.clientY - rect.top) / rect.height - 0.09) / 0.82));
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      setView(current => zoomView(current, Math.exp(-Math.max(-200, Math.min(200, delta)) * 0.005), x, y));
    }
    plot.addEventListener("wheel", wheel, { passive: false });
    return () => plot.removeEventListener("wheel", wheel);
  }, [hasPoints]);
  const representatives = (map.data?.clusters ?? [])
    .filter(cluster => group === null || cluster.id === group)
    .flatMap(cluster => {
      const point = points.find(point => point.track.track_id === cluster.representative_track_id && point.cluster === cluster.id);
      return point ? [point] : [];
    });
  const members = points.filter(point => group === null || point.cluster === group);
  const selected = members.find(point => point.track.track_id === selectedId);
  const visible = selected ? [selected] : members.slice(page * 20, (page + 1) * 20);
  const { minX, maxX, minY, maxY } = points.reduce((bounds, point) => ({
    minX: Math.min(bounds.minX, point.x), maxX: Math.max(bounds.maxX, point.x),
    minY: Math.min(bounds.minY, point.y), maxY: Math.max(bounds.maxY, point.y),
  }), { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity });
  const x = (value: number) => `${6 + ((maxX === minX ? 0.5 : (value - minX) / (maxX - minX)) * view.scale + view.x) * 88}%`;
  const y = (value: number) => `${9 + ((maxY === minY ? 0.5 : (maxY - value) / (maxY - minY)) * view.scale + view.y) * 82}%`;
  const axisX = (edge: number) => (minX + (edge - view.x) / view.scale * (maxX - minX)).toFixed(2);
  const axisY = (edge: number) => (maxY - (edge - view.y) / view.scale * (maxY - minY)).toFixed(2);
  const groupTitle = group === null ? "Вся коллекция" : `Группа ${group + 1}`;

  function selectGroup(value: number | null) {
    setGroup(value);
    setSelectedId(null);
    setPage(0);
  }

  function act(track: Track, callback: (current: Track) => void) {
    const current = map.currentTrack(track);
    if (current && !props.busy) callback(current);
  }

  return <div className="mert-map-panel">
    <header className="mert-map-header">
      <div className="mert-map-heading"><Map size={18} aria-hidden="true" /><div><h3>Карта звучания</h3><small>MERT-v2 L{props.layerState.layer}</small></div></div>
      <div className="mert-map-controls mert-map-build-controls">
        <label>Группы<input type="number" min={1} max={32} value={clusterCount} onChange={event => {
          if (Number.isFinite(event.currentTarget.valueAsNumber)) setClusterCount(Math.max(1, Math.min(32, Math.round(event.currentTarget.valueAsNumber))));
        }} /></label>
        <button type="button" disabled={props.busy || map.pending || !props.catalogUuid || !props.layerState.trackCount} onClick={() => {
          selectGroup(null);
          setView(initialView);
          void map.buildMap(clusterCount);
        }}><RefreshCw size={14} aria-hidden="true" />{map.pending ? "Построение…" : map.data ? "Перестроить" : "Построить карту"}</button>
      </div>
    </header>
    <MertV2LayerSelect state={props.layerState} />
    {map.error ? <p role="alert" className="error">{map.error}</p> : null}
    <section className="mert-map-chart" aria-label="Распределение треков по звучанию">
      {map.data && points.length ? <>
        <div className="mert-map-group-picker">
          <label>Группа<select data-tone={group === null ? "all" : group % 8} value={group ?? "all"} onChange={event => selectGroup(event.target.value === "all" ? null : Number(event.target.value))}>
            <option value="all" data-tone="all">Все · {points.length}</option>
            {map.data.clusters.map(cluster => <option key={cluster.id} value={cluster.id} data-tone={cluster.id % 8}>Группа {cluster.id + 1} · {cluster.count}</option>)}
          </select></label>
          <button type="button" className="mert-map-representatives-toggle" aria-pressed={showRepresentatives} onClick={() => setShowRepresentatives(value => !value)}>
            <LocateFixed size={14} aria-hidden="true" />Представители групп
          </button>
          <div className="mert-map-navigation" role="group" aria-label="Масштаб карты">
            <button type="button" aria-label="Уменьшить карту" title="Уменьшить" disabled={view.scale <= 1} onClick={() => setView(current => zoomView(current, 1 / 1.5))}><Minus size={14} aria-hidden="true" /></button>
            <output aria-label="Текущий масштаб">{Math.round(view.scale * 100)}%</output>
            <button type="button" aria-label="Увеличить карту" title="Увеличить" disabled={view.scale >= 8} onClick={() => setView(current => zoomView(current, 1.5))}><Plus size={14} aria-hidden="true" /></button>
            <button type="button" aria-label="Сбросить вид карты" title="Показать всю карту" onClick={() => setView(initialView)}><Maximize size={14} aria-hidden="true" /></button>
          </div>
        </div>
        <svg ref={plotRef} className={`mert-map-plot ${panning ? "panning" : ""}`} role="img" aria-label="Карта звучания MERT-v2. Колесо — масштаб, перетаскивание — перемещение. Выбор трека также доступен в списке под картой."
          onPointerDown={event => {
            if (event.button !== 0 || !event.isPrimary) return;
            dragged.current = false;
            drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, view };
          }}
          onPointerMove={event => {
            const start = drag.current;
            if (!start || start.id !== event.pointerId) return;
            const dx = event.clientX - start.x, dy = event.clientY - start.y;
            if (!dragged.current && Math.hypot(dx, dy) < 4) return;
            dragged.current = true;
            event.currentTarget.setPointerCapture(event.pointerId);
            setPanning(true);
            const rect = event.currentTarget.getBoundingClientRect();
            setView({ scale: start.view.scale, x: clampOffset(start.view.x + dx / (rect.width * 0.88), start.view.scale), y: clampOffset(start.view.y + dy / (rect.height * 0.82), start.view.scale) });
          }}
          onPointerUp={() => { drag.current = null; setPanning(false); }}
          onPointerCancel={() => { drag.current = null; dragged.current = true; setPanning(false); }}
          onLostPointerCapture={() => { drag.current = null; setPanning(false); }}
          onPointerLeave={() => { if (!dragged.current) drag.current = null; }}
          onClickCapture={event => { if (dragged.current) { event.preventDefault(); event.stopPropagation(); } }}>
          <defs><clipPath id={clipId}><rect x="3%" y="6%" width="94%" height="88%" /></clipPath></defs>
          <g className="mert-map-grid" aria-hidden="true">
            {[0, 1, 2, 3, 4].map(tick => <g key={tick}>
              <line x1={`${6 + tick * 22}%`} x2={`${6 + tick * 22}%`} y1="9%" y2="91%" />
              <line x1="6%" x2="94%" y1={`${9 + tick * 20.5}%`} y2={`${9 + tick * 20.5}%`} />
            </g>)}
          </g>
          <g className="mert-map-axis" aria-hidden="true">
            <text x="6%" y="98%">{axisX(0)}</text><text x="50%" y="98%" textAnchor="middle">PC1</text><text x="94%" y="98%" textAnchor="end">{axisX(1)}</text>
            <text x="6%" y="5%">PC2 {axisY(0)} / {axisY(1)}</text>
          </g>
          <g clipPath={`url(#${clipId})`}>
          {points.map(point => <circle key={point.track.track_uuid} cx={x(point.x)} cy={y(point.y)} r={point.track.track_id === selectedId ? 4 : 2.5}
            data-tone={point.cluster % 8}
            className={`mert-map-point ${group !== null && point.cluster !== group ? "muted" : ""} ${point.track.track_id === selectedId ? "selected" : ""}`}
            onClick={() => { selectGroup(point.cluster); setSelectedId(point.track.track_id); }}>
            <title>{displayTrack(point.track)} · Группа {point.cluster + 1}</title>
          </circle>)}
          {showRepresentatives ? representatives.map(point => <g key={point.track.track_uuid} className="mert-map-representative-marker" data-tone={point.cluster % 8} aria-hidden="true">
            <rect x={x(point.x)} y={y(point.y)} width={12} height={12} rx={2} transform="translate(-6 -6)" />
            <text x={x(point.x)} y={y(point.y)} dx={10} dy={-8}>{point.cluster + 1}</text>
          </g>) : null}
          {selected ? <circle className="mert-map-selection-ring" cx={x(selected.x)} cy={y(selected.y)} r={8} /> : null}
          </g>
        </svg>
        <div className="mert-map-chart-meta" role="status">
          <span>{map.data.eligible_count} треков / {map.data.cluster_count} групп</span>
          <span>Колесо — масштаб · Потяните карту для перемещения</span>
          <span title="Доля дисперсии исходных признаков, сохранённая двумя компонентами PCA">PCA {(map.data.projection.explained_variance_ratio.reduce((a, b) => a + b, 0) * 100).toFixed(1)}%</span>
        </div>
      </> : <div className="mert-map-empty" role="status">
        <Map size={28} strokeWidth={1.2} aria-hidden="true" />
        <strong>{map.pending ? "Строим карту коллекции" : map.data ? "Нет доступных эмбеддингов MERT-v2" : "Карта коллекции"}</strong>
        <span>{map.pending ? "Сравниваем сохранённые признаки треков." : map.data ? "Выберите базу с готовыми эмбеддингами." : "Постройте карту, чтобы увидеть группы похожего звучания."}</span>
      </div>}
    </section>
    <small className="mert-map-note">PCA приблизительно передаёт расстояния. Группы отражают звучание, а не жанры.</small>
    {showRepresentatives && representatives.length ? <section className="mert-map-representatives" aria-label="Представители групп">
      <div className="mert-map-selection-copy"><strong>Представители групп</strong><small>Треки, ближайшие к центрам групп по исходным эмбеддингам.</small></div>
      {representatives.map(point => <button type="button" key={point.track.track_uuid} className="mert-map-representative" data-tone={point.cluster % 8}
        disabled={props.busy} title={displayTrack(point.track)} onClick={() => act(point.track, current => { selectGroup(point.cluster); setSelectedId(current.track_id); })}>
        <span className="mert-map-representative-dot" aria-hidden="true" /><span>Группа {point.cluster + 1}</span><strong>{displayTrack(point.track)}</strong>
      </button>)}
    </section> : null}
    {map.data && points.length ? <>
        <div className="mert-map-member-header">
          <div className="mert-map-selection-copy"><strong>{selected ? displayTrack(selected.track) : groupTitle}</strong><span>{selected ? groupTitle : `${members.length} треков`}</span></div>
          <button type="button" disabled={props.busy || !members.some(point => !props.playlistSet.has(point.track.track_id))} onClick={() => {
            const tracks = members.map(point => map.currentTrack(point.track)).filter((track): track is Track => track !== null);
            if (tracks.length) props.onAddTracks(tracks);
          }}><Plus size={14} aria-hidden="true" />{group === null ? "Все в сет" : "Группу в сет"}</button>
        </div>
        <label>Трек<select value={selected?.track.track_id ?? "all"} onChange={event => { setSelectedId(event.target.value === "all" ? null : Number(event.target.value)); setPage(0); }}>
          <option value="all">Все треки группы</option>
          {members.map(point => <option key={point.track.track_uuid} value={point.track.track_id}>{displayTrack(point.track)}</option>)}
        </select></label>
        <TrackList tracks={visible.map(point => point.track)} startIndex={selected ? 0 : page * 20} seedSet={props.seedSet} playlistSet={props.playlistSet}
          playingTrackId={props.playingTrackId} previewTrackId={props.previewTrackId}
          onSeed={track => act(track, props.onSeed)} onTogglePlaylist={track => act(track, props.onTogglePlaylist)}
          onPreview={track => act(track, props.onPreview)} onDetails={track => act(track, props.onDetails)}
          onSeekPreview={(track, seconds) => act(track, current => props.onSeekPreview(current, seconds))}
          onToggleLiked={track => act(track, current => { void props.onToggleLiked(current).then(updated => { if (updated) map.updateTrack(updated); }).catch(() => {}); })} />
        {!selected && members.length > 20 ? <div className="mert-map-controls mert-map-pagination">
          <button type="button" disabled={page === 0} onClick={() => setPage(value => value - 1)}>Prev</button>
          <span>{page * 20 + 1}–{Math.min(members.length, (page + 1) * 20)} / {members.length}</span>
          <button type="button" disabled={(page + 1) * 20 >= members.length} onClick={() => setPage(value => value + 1)}>Next</button>
        </div> : null}
    </> : null}
  </div>;
}

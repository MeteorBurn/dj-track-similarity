import { CircleAlert, Pause, Play, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { ClusterMapDeviation, ClusterMapPoint, ClusterMapResponse, Track } from "./api";
import { pluralRu } from "./audioDedupView";
import { ClusterMapPlot, MapSkeleton } from "./ClusterMapPlot";
import { seedSearchModelPresentation, tabAfterKey } from "./searchSurfaceState";
import { formatSonaraCoreValue, sonaraCoreFeatureGroups } from "./TrackMetadataDialog";
import { displayTrack } from "./trackDisplay";
import type { ClusterMapEntry } from "./useClusterMap";
import type { EmbeddingLayerState } from "./useEmbeddingLayers";

type RailTab = "tracks" | "summary";
type Candidate = { point: ClusterMapPoint; rank: number };
const railTabs: readonly RailTab[] = ["tracks", "summary"];
const vectorLabels: Record<string, string> = { chroma: "Хрома", mfcc: "MFCC · тембр", spectral_contrast: "Спектральный контраст" };
const groupLabels: Record<string, string> = { rhythm: "Ритм", dynamics: "Динамика", spectral: "Спектр", tonal: "Тональность", timbral: "Тембр" };
const FOCUSABLE = "button:not([disabled]):not([tabindex='-1']), summary, [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

/** One cached model ranking, checked independently against physical SONARA descriptors. */
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
  const [tab, setTab] = useState<RailTab>("tracks");
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const { payload, response } = entry;
  const { seeds, candidates } = useMemo(() => ({
    seeds: response?.points.filter((point) => point.seed) ?? [],
    candidates: response?.points.filter((point) => !point.seed).map((point, index) => ({ point, rank: index + 1 })) ?? [],
  }), [response]);
  const selected = candidates.find(({ point }) => point.track.track_id === selectedTrackId) ?? candidates[0] ?? null;
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

  useEffect(() => { panelRef.current?.scrollTo({ top: 0 }); }, [selectedTrackId]);

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

  function selectCandidate(trackId: number) { setSelectedTrackId(trackId); setTab("tracks"); }

  function preview(track: Track) { selectCandidate(track.track_id); onPreview(track); }

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
            <h2 id="cluster-map-title">Проверка выдачи</h2>
            <span className="cluster-map-chip">{seedSearchModelPresentation[payload.analysis_family].label}</span>
            {layer !== null ? <span className="cluster-map-chip" title={[layerRow?.source, layerState.note].filter(Boolean).join("\n") || undefined}>L{layer}</span> : null}
            {layerRow?.label ? <span className="cluster-map-layer-hint">{layerRow.label}</span> : null}
          </div>
          <p id="cluster-map-summary" className="cluster-map-summary">{summaryText} · независимая проверка SONARA</p>
          <div className="cluster-map-header-actions">
            {entry.status === "ready" ? <button type="button" title="Повторить поиск и проверку по текущим данным библиотеки" onClick={onRetry}><RotateCcw size={13} />Пересчитать</button> : null}
            <button className="icon-button" type="button" title="Закрыть" aria-label="Закрыть" onClick={requestClose}><X size={16} /></button>
          </div>
        </header>
        {entry.status === "loading" ? (
          <div className="cluster-map-body"><p className="cluster-map-status" role="status">Проверяем физические признаки кандидатов относительно каждого референса…</p><div className="cluster-map-plot-frame"><MapSkeleton /></div></div>
        ) : entry.status === "error" ? (
          <div className="cluster-map-body"><div className="cluster-map-error" role="alert">
            <CircleAlert size={18} aria-hidden="true" /><div><strong>Не удалось проверить выдачу</strong><p>{entry.error}</p></div>
            <button type="button" onClick={onRetry}>Повторить</button>
          </div></div>
        ) : response ? (
          <div className="cluster-map-body">
            <p className="cluster-map-coverage"><strong>Рисунок ударных пока не проверен.</strong> Отметки показывают отклонения сводных аудиопризнаков.</p>
            <KpiRow response={response} />
            {response.calibration.descriptor_count < response.calibration.total_descriptors ? (
              <p className="cluster-map-coverage" role="status">Неполные данные референсов: доступны {response.calibration.descriptor_count} из {response.calibration.total_descriptors} признаков. Отсутствующие измерения не подтверждают сходство.</p>
            ) : null}
            <div className="cluster-map-main">
              <figure className="cluster-map-figure">
                <figcaption>Правее — больше сходство по модели. Выше — больше расхождение физических признаков SONARA с ближайшим референсом относительно библиотеки. Клик выберет и воспроизведёт трек.</figcaption>
                <ClusterMapPlot mapKey={entry.key} points={response.points} librarySimilarity={response.library_similarity} totalDescriptors={response.calibration.total_descriptors}
                  selectedTrackId={selected?.point.track.track_id ?? null} playingTrackId={playingTrackId}
                  describePoint={pointDescription} onSelect={selectCandidate} onPreview={onPreview} />
                <div className="cluster-map-legend">
                  <span className="cluster-map-key"><span className="cluster-map-swatch is-neutral" aria-hidden="true" />Без отметки по сводным признакам</span>
                  <span className="cluster-map-key"><span className="cluster-map-key-exception" aria-hidden="true" />Проверить на слух</span>
                  <span className="cluster-map-key"><X size={12} aria-hidden="true" />Неполная проверка</span>
                  <span className="cluster-map-key"><span className="cluster-map-key-typical" aria-hidden="true" />Медиана модели в библиотеке · {response.library_similarity.toFixed(3)}</span>
                </div>
                <p className="cluster-map-prose">P80 означает: 80 % сравнимых треков библиотеки ближе к референсам по SONARA. Это не вероятность ошибки модели. Цвет отмечает сильное физическое отклонение, отдельно от процентиля.</p>
                {response.summary.compared_count < candidates.length ? <p className="cluster-map-coverage">Без общей оценки SONARA: {candidates.length - response.summary.compared_count}. Они остаются в списке; на графике показаны только измеренные кандидаты.</p> : null}
              </figure>
              <aside className="cluster-map-rail" aria-label="Подробности проверки">
                <div className="search-tabs cluster-map-tabs" role="tablist" aria-label="Разделы проверки">
                  {railTabs.map((name) => <button key={name} id={`cluster-map-tab-${name}`} className={`model-search-tab ${tab === name ? "active" : ""}`}
                    role="tab" aria-selected={tab === name} aria-controls={`cluster-map-panel-${name}`} tabIndex={tab === name ? 0 : -1}
                    type="button" onClick={() => setTab(name)} onKeyDown={selectTabByKey}>{name === "tracks" ? "Треки" : "Сводка выдачи"}</button>)}
                </div>
                <div ref={panelRef} id={`cluster-map-panel-${tab}`} className="cluster-map-tab-panel" role="tabpanel" aria-labelledby={`cluster-map-tab-${tab}`}>
                  {tab === "tracks" ? <>
                    {selected ? <CandidateDetails candidate={selected} seeds={seeds} calibration={response.calibration} playingTrackId={playingTrackId} onPreview={preview} /> : <p className="empty-state">Кандидатов для проверки нет.</p>}
                    <CandidateList candidates={candidates} selectedTrackId={selected?.point.track.track_id ?? null} playingTrackId={playingTrackId} totalDescriptors={response.calibration.total_descriptors} onSelect={selectCandidate} onPreview={preview} />
                    <ReferenceList seeds={seeds} playingTrackId={playingTrackId} onPreview={onPreview} />
                  </> : <SummaryPanel response={response} />}
                </div>
              </aside>
            </div>
          </div>
        ) : null}
        <footer className="cluster-map-footer">SONARA описывает физические отличия; жанр, инструменты и музыкальную уместность подтверждает прослушивание.</footer>
      </section>
    </div>
  );
}

function KpiRow({ response }: { response: ClusterMapResponse }) {
  const { summary, calibration } = response;
  return <dl className="cluster-map-kpis">
    <div className="cluster-map-kpi"><dt>Проверить на слух</dt><dd className="cluster-map-kpi-value">{summary.requires_listening_count} / {summary.candidate_count}</dd><dd className="cluster-map-kpi-note">сильные отклонения от диапазона референсов</dd></div>
    <div className="cluster-map-kpi"><dt>Медиана расхождения</dt><dd className="cluster-map-kpi-value">{summary.median_percentile === null ? "—" : `P${summary.median_percentile.toFixed(1)}`}</dd><dd className="cluster-map-kpi-note">общая оценка: {summary.compared_count} / {summary.candidate_count}</dd></div>
    <div className="cluster-map-kpi"><dt>Общий сдвиг</dt><dd className="cluster-map-kpi-value">{summary.coherent_drift ? "Есть" : calibration.descriptor_count < calibration.total_descriptors ? "Неполная проверка" : summary.compared_count < 3 ? "Мало данных" : "Не выявлен"}</dd><dd className="cluster-map-kpi-note">по {calibration.descriptor_count} / {calibration.total_descriptors} физическим признакам</dd></div>
  </dl>;
}

function CandidateList({ candidates, selectedTrackId, playingTrackId, totalDescriptors, onSelect, onPreview }: {
  candidates: Candidate[];
  selectedTrackId: number | null;
  playingTrackId: number | null;
  totalDescriptors: number;
  onSelect: (trackId: number) => void;
  onPreview: (track: Track) => void;
}) {
  return <section className="cluster-map-list"><h3>Кандидаты · порядок модели</h3><ul className="cluster-map-anomalies">
    {candidates.map(({ point, rank }) => <li key={point.track.track_id} className="cluster-map-anomaly" data-selected={point.track.track_id === selectedTrackId || undefined}>
      <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} />
      <button className="cluster-map-select-track" type="button" aria-pressed={point.track.track_id === selectedTrackId} onClick={() => onSelect(point.track.track_id)} title={`Выбрать: ${displayTrack(point.track)}`}>
        <strong>{displayTrack(point.track)}</strong><span>#{rank} · модель {point.similarity.toFixed(3)} · {point.sonara.percentile === null ? "SONARA —" : `SONARA P${point.sonara.percentile.toFixed(1)}`}</span>
      </button>
      <div className="cluster-map-reasons"><span className="cluster-map-reason" data-departure={point.sonara.requires_listening === true || undefined}>{statusText(point, totalDescriptors)}</span></div>
    </li>)}
  </ul></section>;
}

function CandidateDetails({ candidate, seeds, calibration, playingTrackId, onPreview }: {
  candidate: Candidate;
  seeds: ClusterMapPoint[];
  calibration: ClusterMapResponse["calibration"];
  playingTrackId: number | null;
  onPreview: (track: Track) => void;
}) {
  const { point, rank } = candidate;
  const nearest = seeds.find((seed) => seed.track.track_id === point.sonara.nearest_reference_id);
  const departures = point.sonara.deviations.filter((item) => item.departure === true);
  return <article className="cluster-map-card cluster-map-candidate-details" aria-label="Выбранный кандидат">
    <header className="cluster-map-card-head"><PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} /><h3>#{rank} · {displayTrack(point.track)}</h3></header>
    <p className="cluster-map-prose">{statusText(point, calibration.total_descriptors)}. {point.sonara.distance === null ? "Общее расхождение неизвестно." : `Расхождение ${point.sonara.distance.toFixed(2)} IQR · ${point.sonara.percentile === null ? "процентиль неизвестен" : `P${point.sonara.percentile.toFixed(1)}`}.`}</p>
    {nearest ? <p className="cluster-map-prose">Ближайший референс по SONARA: <strong>{displayTrack(nearest.track)}</strong></p> : null}
    <div className="cluster-map-reference-scores"><h4>Сходство модели с каждым референсом</h4>
      {point.reference_similarities.map((item) => <div key={item.track_id}><span title={referenceName(seeds, item.track_id)}>{referenceName(seeds, item.track_id)}</span><strong>{item.similarity.toFixed(3)}</strong></div>)}
    </div>
    {departures.length ? <div className="cluster-map-reasons">{departures.map((item) => <span key={item.descriptor} className="cluster-map-reason" data-departure>{deviationDescription(item)}</span>)}</div> : null}
    <details className="cluster-map-descriptors"><summary>Все физические признаки · {point.sonara.descriptor_count} / {calibration.total_descriptors}</summary>
      <p className="cluster-map-prose">Сравнение с диапазоном всех референсов. Сильное отклонение — более {calibration.departure_threshold} IQR за его пределами. IQR — межквартильный размах признака в библиотеке. Порог служит ориентиром для прослушивания, а не уверенностью.</p>
      <dl>{[...point.sonara.deviations].sort((left, right) => (right.envelope_distance ?? -1) - (left.envelope_distance ?? -1)).map((item) => <div key={item.descriptor} data-departure={item.departure === true || undefined}>
        <dt>{descriptorLabel(item.descriptor)}</dt>
        <dd>{item.available ? deviationDescription(item) : "Нет измерения или данных референсов"}</dd>
        {item.value !== null ? <dd className="cluster-map-descriptor-values">Трек: {formatDescriptor(item.descriptor, item.value)} · референсы: {referenceRange(item)}</dd> : null}
        {item.available ? <dd className="cluster-map-descriptor-values">До ближайшего референса по признаку: {numberOrDash(item.distance)} IQR · {item.percentile === null ? "процентиль неизвестен" : `P${item.percentile.toFixed(1)}`}</dd> : null}
      </div>)}</dl>
    </details>
  </article>;
}

function SummaryPanel({ response }: { response: ClusterMapResponse }) {
  const { calibration, summary } = response;
  return <div className="cluster-map-layer">
    <section className="cluster-map-layer-about"><h3>Независимая база сравнения</h3>
      <p className="cluster-map-prose">Нормализация SONARA по библиотеке: {calibration.library_count} треков, {calibration.complete_library_count} с полным набором измерений. Доступны {calibration.descriptor_count} / {calibration.total_descriptors} признаков референсов. При смене модели или слоя база сравнения остаётся той же.</p>
      <p className="cluster-map-prose">Каждый кандидат сравнивается с отдельными референсами. Общая дистанция — до ближайшего из них; сильное отклонение признака — выход за диапазон всех референсов.</p>
    </section>
    <section className="cluster-map-focus"><h3>Систематические отличия выдачи</h3>
      <p className="cluster-map-prose">Общий сдвиг требует не менее трёх сравнений, согласованного направления у большинства и величины более {calibration.drift_threshold} IQR. Это описание физических отличий, а не оценка музыкальной уместности.</p>
      <ul className="cluster-map-summary-descriptors">{[...summary.descriptors].sort((left, right) => Number(right.coherent_drift) - Number(left.coherent_drift) || (right.coherent_shift_distance ?? -1) - (left.coherent_shift_distance ?? -1)).map((item) => <li key={item.descriptor} data-drift={item.coherent_drift || undefined}>
        <div><strong>{descriptorLabel(item.descriptor)}</strong><span>{groupLabels[item.group] ?? item.group}</span></div>
        <p>{item.compared_count === 0 ? "Недостаточно измерений" : <>{item.coherent_drift ? "Общий сдвиг" : "Без подтверждённого общего сдвига"} · {item.compared_count} сравнений</>}</p>
        {item.compared_count > 0 ? <p>Сильных отклонений: {item.departure_count}{item.below_count !== null && item.above_count !== null ? <><br />За диапазоном референсов: ниже {item.below_count} · выше {item.above_count}</> : null}<br />Одно направление: {item.direction_count} / {item.compared_count}<br />Медиана выхода: {numberOrDash(item.median_envelope_distance)} IQR · общий сдвиг: {numberOrDash(item.coherent_shift_distance)} IQR{item.median_delta_iqr !== null ? ` · Δ ${signed(item.median_delta_iqr)} IQR` : ""}</p> : null}
      </li>)}</ul>
    </section>
    <p className="cluster-map-prose">Пороговые отметки помогают выбрать треки для прослушивания. Отсутствие отметки не доказывает сходство; неизвестные признаки остаются неизвестными.</p>
  </div>;
}

function ReferenceList({ seeds, playingTrackId, onPreview }: { seeds: ClusterMapPoint[]; playingTrackId: number | null; onPreview: (track: Track) => void }) {
  return <section className="cluster-map-card"><h3>Референсы</h3><ul className="cluster-map-track-list">{seeds.map((point) => <li key={point.track.track_id}><div className="cluster-map-track">
    <PlayButton track={point.track} playingTrackId={playingTrackId} onPreview={onPreview} /><span className="cluster-map-track-name" title={displayTrack(point.track)}>{displayTrack(point.track)}</span>
  </div></li>)}</ul></section>;
}

function PlayButton({ track, playingTrackId, onPreview }: { track: Track; playingTrackId: number | null; onPreview: (track: Track) => void }) {
  const playing = playingTrackId === track.track_id;
  const action = playing ? "Пауза" : "Прослушать";
  return <button className="icon-button cluster-map-play-button" data-playing={playing || undefined} title={action} aria-label={`${action}: ${displayTrack(track)}`} type="button" onClick={() => onPreview(track)}>{playing ? <Pause size={13} /> : <Play size={13} />}</button>;
}

function statusText(point: ClusterMapPoint, total: number) {
  const status = point.sonara.requires_listening === true ? "Проверить на слух" : !point.sonara.available || point.sonara.requires_listening === null || point.sonara.descriptor_count < total ? "Неполная проверка" : "Без отметки по сводным признакам";
  return point.sonara.descriptor_count < total ? `${status} · признаки ${point.sonara.descriptor_count}/${total}` : status;
}

function pointDescription(point: ClusterMapPoint) {
  const departures = point.sonara.deviations.filter((item) => item.departure === true);
  return departures.length ? departures.slice(0, 2).map(deviationDescription).join(" · ") : "Физические измерения и сравнение с референсами — в карточке трека.";
}

function referenceName(seeds: ClusterMapPoint[], trackId: number) {
  const seed = seeds.find((point) => point.track.track_id === trackId);
  return seed ? displayTrack(seed.track) : `Референс #${trackId}`;
}

function descriptorLabel(descriptor: string) {
  if (vectorLabels[descriptor]) return vectorLabels[descriptor];
  for (const group of sonaraCoreFeatureGroups) {
    const found = group.features.find((feature) => feature.key === descriptor);
    if (found) return found.label;
  }
  return descriptor;
}

function formatDescriptor(descriptor: string, value: number) {
  for (const group of sonaraCoreFeatureGroups) {
    const found = group.features.find((feature) => feature.key === descriptor);
    if (found) return formatSonaraCoreValue(found.key, value);
  }
  return value.toFixed(2);
}

function referenceRange(item: ClusterMapDeviation) {
  if (item.reference_min === null || item.reference_max === null) return "—";
  return item.reference_min === item.reference_max ? formatDescriptor(item.descriptor, item.reference_min)
    : `${formatDescriptor(item.descriptor, item.reference_min)}…${formatDescriptor(item.descriptor, item.reference_max)}`;
}

function deviationDescription(item: ClusterMapDeviation) {
  const label = descriptorLabel(item.descriptor);
  if (!item.available) return `${label}: нет измерения`;
  const direction = item.delta_iqr === null ? "отклонение" : item.delta_iqr > 0 ? "выше референсов" : item.delta_iqr < 0 ? "ниже референсов" : "в диапазоне";
  return `${label}: ${direction} · ${numberOrDash(item.envelope_distance)} IQR`;
}

function numberOrDash(value: number | null) { return value === null ? "—" : value.toFixed(2); }
function signed(value: number) { return `${value > 0 ? "+" : ""}${value.toFixed(2)}`; }

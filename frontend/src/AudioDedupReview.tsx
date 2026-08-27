import { AlertTriangle, Crown, Pause, Play, Trash2 } from "lucide-react";
import type { AudioDedupFile, AudioDedupGroup, AudioDedupSearchMode } from "./api";
import {
  confidenceLabel,
  copyDetailReasons,
  copyStatusLine,
  fileQualityLine,
  fileSpecLine,
  fileSpectralBadge,
  formatSimilarity,
  groupFingerprintLine,
  groupSurvivesSelection,
  suggestedGroupSelection
} from "./audioDedupView";

function FileCard({
  file,
  searchMode,
  selected,
  playing,
  onToggle,
  onPreview
}: {
  file: AudioDedupFile;
  searchMode: AudioDedupSearchMode | "";
  selected: boolean;
  playing: boolean;
  onToggle: () => void;
  onPreview: () => void;
}) {
  const status = copyStatusLine(file, searchMode);
  const details = copyDetailReasons(file, searchMode);
  const spectral = fileSpectralBadge(file);
  const quality = fileQualityLine(file);
  const isKeeper = file.role === "keeper";
  const className = [
    "dedup-copy",
    isKeeper ? "dedup-copy-keeper" : "",
    selected ? "dedup-copy-doomed" : "",
    file.stale ? "dedup-copy-stale" : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={className}>
      <header className="dedup-copy-head">
        <button
          className="icon-button dedup-play-button"
          type="button"
          title={file.playable ? "Прослушать копию" : "Файл недоступен для прослушивания"}
          aria-label={playing ? "Пауза" : "Прослушать копию"}
          disabled={!file.playable}
          onClick={onPreview}
        >
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <div className="dedup-copy-identity">
          <span className="dedup-copy-name" title={file.file_name}>
            {file.file_name}
          </span>
          {file.artist || file.title ? (
            <span className="dedup-copy-artist">
              {[file.artist, file.title].filter(Boolean).join(" — ")}
            </span>
          ) : null}
        </div>
        <span className={`dedup-role ${isKeeper ? "dedup-role-keep" : "dedup-role-copy"}`}>
          {isKeeper ? <Crown size={12} /> : null}
          {isKeeper ? "оставить" : "копия"}
        </span>
      </header>

      <p className="dedup-copy-path">{file.path}</p>

      <div className="dedup-copy-specs">
        <span className="dedup-spec-main">{fileSpecLine(file)}</span>
        <span className={`dedup-spectral dedup-spectral-${spectral.tone}`}>
          {spectral.tone === "warn" ? <AlertTriangle size={12} /> : null}
          {spectral.text}
        </span>
        {quality ? <span className="dedup-spec-muted">{quality}</span> : null}
      </div>

      {file.stale && file.stale_reason ? (
        <p className="dedup-copy-stale-note">Отчёт устарел: {file.stale_reason}</p>
      ) : null}

      {status ? <p className="dedup-copy-status">{status}</p> : null}

      {details.length > 0 ? (
        <div className="dedup-copy-details">
          <span className="dedup-copy-details-title">Подробности:</span>
          <ul>
            {details.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <button
        className={`dedup-copy-action ${selected ? "selected" : ""}`}
        type="button"
        aria-pressed={selected}
        title={selected ? "Оставить эту копию" : "Пометить копию на удаление"}
        onClick={onToggle}
      >
        <Trash2 size={14} />
        {selected ? "Помечена на удаление" : "Удалить эту копию"}
      </button>
    </article>
  );
}

export function AudioDedupGroupCard({
  group,
  searchMode,
  selectedTrackIds,
  playingTrackId,
  onToggleFile,
  onSetGroup,
  onPreview
}: {
  group: AudioDedupGroup;
  searchMode: AudioDedupSearchMode | "";
  selectedTrackIds: number[];
  playingTrackId: number | null;
  onToggleFile: (groupId: number, trackId: number) => void;
  onSetGroup: (groupId: number, trackIds: number[]) => void;
  onPreview: (file: AudioDedupFile) => void;
}) {
  const survives = groupSurvivesSelection(group, selectedTrackIds);
  const fingerprintLine = groupFingerprintLine(group);

  return (
    <section className={`dedup-group ${selectedTrackIds.length > 0 ? "has-selection" : ""}`}>
      <header className="dedup-group-head">
        <span className="dedup-group-id">#{group.group_id}</span>
        <span className={`dedup-chip dedup-chip-${group.confidence || "review"}`}>
          {confidenceLabel(group.confidence)}
        </span>
        <span className="dedup-chip dedup-chip-score" title="Точный матч отпечатков SONARA">
          отпечаток {formatSimilarity(group.fingerprint_similarity)}
        </span>
        <span className="dedup-group-count">{group.files.length} копии</span>
        {fingerprintLine ? (
          <span className="dedup-group-fingerprint">{fingerprintLine}</span>
        ) : null}
        {group.suspected_transcode_count > 0 ? (
          <span className="dedup-chip dedup-chip-warn">
            <AlertTriangle size={12} />
            фейк-битрейт {group.suspected_transcode_count}
          </span>
        ) : null}
        <div className="dedup-group-actions">
          <button
            className="dedup-ghost-button"
            type="button"
            title="Пометить всё, кроме предложенной к сохранению копии"
            onClick={() => onSetGroup(group.group_id, suggestedGroupSelection(group))}
          >
            По рекомендации
          </button>
          <button
            className="dedup-ghost-button"
            type="button"
            title="Снять пометки в этой группе"
            disabled={selectedTrackIds.length === 0}
            onClick={() => onSetGroup(group.group_id, [])}
          >
            Снять
          </button>
        </div>
      </header>

      {!survives ? (
        <p className="dedup-group-warning">
          <AlertTriangle size={13} />
          Помечены все копии группы. Оставьте хотя бы одну — иначе удаление будет отклонено.
        </p>
      ) : null}

      <div className="dedup-copies">
        {group.files.map((file) => (
          <FileCard
            key={file.track_id}
            file={file}
            searchMode={searchMode}
            selected={selectedTrackIds.includes(file.track_id)}
            playing={playingTrackId === file.track_id}
            onToggle={() => onToggleFile(group.group_id, file.track_id)}
            onPreview={() => onPreview(file)}
          />
        ))}
      </div>
    </section>
  );
}

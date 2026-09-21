import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  AudioLines,
  Check,
  CopyX,
  Download,
  FileSpreadsheet,
  Loader2,
  Search,
  SlidersHorizontal,
  Trash2,
  X
} from "lucide-react";
import { api } from "./api";
import type {
  AudioDedupDeletionMode,
  AudioDedupFile,
  AudioDedupJobStatus,
  AudioDedupSearchMode
} from "./api";
import { AudioDedupGroupCard } from "./AudioDedupReview";
import { ConfirmationDialog } from "./dialogs";
import {
  audioDedupFakeBitrateDescription,
  audioDedupModeDescription,
  audioDedupModeLabel,
  helpText
} from "./helpText";
import {
  confidenceLabel,
  copiesWord,
  dedupConfidenceOptions,
  fingerprintBandText,
  formatBytes,
  pluralRu,
  scanStagePosition,
  scanStateLabel,
  scanStepLabel,
  selectionSummary
} from "./audioDedupView";
import { useAudioDedup } from "./useAudioDedup";
import type { AudioDedupFilters } from "./useAudioDedup";
import { useConfirmation } from "./useConfirmation";
import { formatEta } from "./trackDisplay";

function scanRunning(job: AudioDedupJobStatus) {
  return job.state === "running" || job.state === "queued";
}

/**
 * Where the run is: which stage of how many, and how far into that stage.
 *
 * The bar underneath measures the current step alone, so the percent belongs
 * beside the stage it describes rather than beside the totals.
 */
function scanStageText(job: AudioDedupJobStatus, progressPercent: number) {
  if (!scanRunning(job)) return scanStateLabel(job.state);
  const parts: string[] = [];
  const stage = scanStagePosition(job);
  if (stage) parts.push(`этап ${stage.index}/${stage.total}`);
  parts.push(job.current_step ? scanStepLabel(job.current_step) : "подготовка");
  // A step that counts nothing — reading the database, writing the report —
  // has no share to report, and 0% would read as a stalled one.
  if (job.total > 0) parts.push(`${Math.round(progressPercent)}%`);
  return parts.join(" · ");
}

/** What the run has counted so far, or what it left behind once it is over. */
function scanMetaText(
  job: AudioDedupJobStatus,
  elapsedSeconds: number | null,
  etaSeconds: number | null
) {
  const parts: string[] = [];
  if (scanRunning(job)) {
    if (job.total > 0) parts.push(`${job.processed}/${job.total}`);
    if (elapsedSeconds != null) parts.push(`прошло ${formatEta(elapsedSeconds)}`);
    if (etaSeconds != null) parts.push(`осталось ~${formatEta(etaSeconds)}`);
  } else {
    parts.push(
      `${job.groups} ${pluralRu(job.groups, "группа", "группы", "групп")}`,
      // Every group member other than the suggested keeper: the tool deletes
      // none of them by itself, so this is the whole pile waiting for a decision.
      `${job.duplicate_copies} ${copiesWord(job.duplicate_copies)} на разбор`
    );
    if (elapsedSeconds != null) parts.push(`заняло ${formatEta(elapsedSeconds)}`);
  }
  return parts.join(" · ");
}

export function AudioDedupDialog({
  open,
  databaseIdentity,
  job,
  jobRunning,
  onJobChange,
  playingTrackId,
  onPreview,
  onClose,
  onDeleted
}: {
  open: boolean;
  databaseIdentity: string | null;
  job: AudioDedupJobStatus | null;
  jobRunning: boolean;
  onJobChange: (job: AudioDedupJobStatus) => void;
  playingTrackId: number | null;
  onPreview: (file: AudioDedupFile) => void;
  onClose: () => void;
  onDeleted: (message: string) => void;
}) {
  const dedup = useAudioDedup({ open, databaseIdentity, job, setJob: onJobChange });
  const [searchMode, setSearchMode] = useState<AudioDedupSearchMode>(job?.search_mode ?? "fingerprint_scan");
  const [detectFakeBitrate, setDetectFakeBitrate] = useState(job?.detect_fake_bitrate ?? false);
  const displayedSearchMode = jobRunning && job ? job.search_mode : searchMode;
  const displayedDetectFakeBitrate = jobRunning && job ? job.detect_fake_bitrate : detectFakeBitrate;
  const [deletionMode, setDeletionMode] = useState<AudioDedupDeletionMode>("trash");
  const [draftFilters, setDraftFilters] = useState<AudioDedupFilters>(dedup.filters);
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);
  const { confirmation, requestConfirmation, confirmPendingAction, cancelConfirmation } =
    useConfirmation();

  useEffect(() => {
    // A closed dialog owns no key: without this the listener would answer
    // Escape anywhere in the app by closing a dialog that is not on screen.
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // Escape answers whatever is on top: the delete prompt first, the dialog after.
      if (confirmation) cancelConfirmation();
      else onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cancelConfirmation, confirmation, onClose, open]);

  // The job poll lands every 1.2s and a step can sit silent for much longer, so
  // the elapsed time keeps its own second instead of stepping in poll-sized jumps.
  useEffect(() => {
    if (!open || !jobRunning) return;
    setNowSeconds(Date.now() / 1000);
    const timer = window.setInterval(() => setNowSeconds(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [jobRunning, open]);

  const activeReport = useMemo(
    () => dedup.reports.find((report) => report.report_id === dedup.reportId) ?? null,
    [dedup.reports, dedup.reportId]
  );
  const summary = useMemo(
    () => selectionSummary(dedup.page?.groups ?? [], dedup.selection),
    [dedup.page, dedup.selection]
  );
  // Manual review is the one filter that goes through what the tool would not
  // decide by itself, so it is the one that hands the boundary back.
  const manualConfidence = draftFilters.confidence.includes("review");
  // Every filter narrows one report, so without a report there is nothing to
  // narrow, and a running scan is about to replace what the row would read.
  const filtersDisabled = !activeReport || jobRunning;
  const pageSelectionDisabled = !dedup.page?.groups.length || dedup.loadingGroups || dedup.busy || jobRunning;
  const fingerprintBand = fingerprintBandText(draftFilters.confidence[0] ?? "", activeReport);
  const canDelete = summary.files > 0 && !dedup.busy;
  // The filter the page on screen was read under, which is what the counts
  // below it describe. The field may already hold a different draft.
  const appliedPathFilter = dedup.filters.pathContains.trim();
  const selectionText =
    `${summary.files} ${copiesWord(summary.files)}`
    + ` в ${summary.groups} ${pluralRu(summary.groups, "группе", "группах", "группах")}`;

  if (!open) return null;

  const progressPercent = job && job.total > 0 ? Math.min(100, (job.processed / job.total) * 100) : 0;
  const elapsedSeconds =
    job?.started_at == null ? null : Math.max(0, (job.finished_at ?? nowSeconds) - job.started_at);
  // Only the step in flight has a measured rate, and only it can be extrapolated:
  // the steps that follow count other things at other speeds.
  const etaSeconds =
    job && jobRunning && job.step_seconds_per_unit && job.total > job.processed
      ? (job.total - job.processed) * job.step_seconds_per_unit
      : null;

  function updateFilters(next: AudioDedupFilters) {
    setDraftFilters(next);
    // Confidence and the fingerprint floor read the report the reviewer already
    // has, so they apply at once. The folder filter does not travel with them:
    // it waits for its own button, and half-typed text is not a request.
    dedup.applyFilters({ ...next, pathContains: dedup.filters.pathContains });
  }

  function requestReportDelete() {
    if (!activeReport) return;
    requestConfirmation({
      title: "Удалить отчёт?",
      message:
        `${activeReport.generated_at.replace("T", " ")} · `
        + `${activeReport.group_count} `
        + `${pluralRu(activeReport.group_count, "группа", "группы", "групп")}. `
        + "Будут удалены файлы отчёта: JSON, XLSX и лог. Сами копии на диске останутся.",
      onConfirm: () => void dedup.deleteReport()
    });
  }

  function requestDelete() {
    requestConfirmation({
      title:
        deletionMode === "trash"
          ? "Удалить помеченные копии в корзину?"
          : "Удалить помеченные копии безвозвратно?",
      message:
        `${selectionText} · ${formatBytes(summary.bytes)}. `
        + (deletionMode === "trash"
          ? "Файлы уйдут в корзину, их строки будут удалены из базы."
          : "Файлы будут стёрты с диска мимо корзины, их строки будут удалены из базы."),
      onConfirm: () => void runDelete()
    });
  }

  async function runDelete() {
    const result = await dedup.deleteSelected(deletionMode);
    if (!result) return;
    const target = deletionMode === "trash" ? "в корзину" : "безвозвратно";
    const parts = [`Удалено ${target}: ${result.deleted_track_ids.length}`];
    if (result.skipped.length > 0) parts.push(`пропущено ${result.skipped.length}`);
    if (result.failed.length > 0) parts.push(`с ошибкой ${result.failed.length}`);
    onDeleted(parts.join(", "));
  }

  return (
    <div className="dedup-backdrop" onClick={onClose} role="presentation">
      <section
        className="dedup-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dedup-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="dedup-title">
          <div className="dedup-title-copy">
            <h2 id="dedup-title">
              <CopyX size={18} />
              Дубликаты
            </h2>
            <span>
              Отчёт строится без изменений на диске. Удаление выполняется только по вашему выбору
              и подтверждению.
            </span>
          </div>
          <button
            className="icon-button dedup-close-button"
            title="Закрыть"
            aria-label="Закрыть"
            type="button"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <div className="dedup-body">
          <section className="dedup-section">
            <div className="dedup-section-title">
              <Search size={13} />
              Поиск
            </div>
            <div className="dedup-scan-grid">
              <label className="dedup-control dedup-mode-control">
                <span>Режим</span>
                <select
                  name="dedup-search-mode"
                  value={displayedSearchMode}
                  disabled={jobRunning}
                  onChange={(event) => setSearchMode(event.target.value as AudioDedupSearchMode)}
                >
                  <option value="fingerprint_scan">
                    {audioDedupModeLabel.fingerprint_scan}
                  </option>
                  <option value="fingerprint_lsh">
                    {audioDedupModeLabel.fingerprint_lsh}
                  </option>
                </select>
              </label>
              <button
                className={`dedup-toggle ${displayedDetectFakeBitrate ? "active" : ""}`}
                name="dedup-detect-fake-bitrate"
                role="switch"
                aria-checked={displayedDetectFakeBitrate}
                disabled={jobRunning}
                onClick={() => setDetectFakeBitrate(!detectFakeBitrate)}
                type="button"
              >
                <span className="dedup-toggle-checkbox" aria-hidden="true">
                  {displayedDetectFakeBitrate ? <Check size={11} strokeWidth={2.6} /> : null}
                </span>
                <AudioLines size={15} />
                Анализ спектрограммы
              </button>
              {jobRunning ? (
                <button
                  className="dedup-secondary-button dedup-run-button"
                  type="button"
                  onClick={() => void dedup.cancelScan()}
                >
                  Остановить
                </button>
              ) : (
                <button
                  className="dedup-primary-button dedup-run-button"
                  type="button"
                  disabled={dedup.busy}
                  title="Искать дубликаты по всей базе"
                  onClick={() =>
                    void dedup.startScan({
                      search_mode: searchMode,
                      detect_fake_bitrate: detectFakeBitrate
                    })
                  }
                >
                  <Search size={15} />
                  Искать дубликаты
                </button>
              )}
            </div>
            {/* What each control actually does, on screen rather than in a
                tooltip: these are the two choices made before a long run. */}
            <div className="dedup-scan-notes">
              <p className="dedup-mode-description">
                <b>{audioDedupModeLabel[displayedSearchMode]}.</b> {audioDedupModeDescription[displayedSearchMode]}
              </p>
              {displayedDetectFakeBitrate ? (
                <p className="dedup-mode-description">
                  <b>Анализ спектрограммы:</b> {audioDedupFakeBitrateDescription}
                </p>
              ) : null}
            </div>
            {/* The status belongs at the bar it describes: the stage the run is
                on, how far into that stage, and what it has counted. */}
            {job ? (
              <div className="dedup-progress">
                <div className="dedup-progress-status">
                  <span>{scanStageText(job, progressPercent)}</span>
                  <span>{scanMetaText(job, elapsedSeconds, etaSeconds)}</span>
                </div>
                {jobRunning ? (
                  <div className="dedup-progress-track">
                    <div
                      className="dedup-progress-fill"
                      style={{ transform: `scaleX(${progressPercent / 100})` }}
                    />
                  </div>
                ) : null}
              </div>
            ) : null}
            {job?.error ? <p className="dedup-alert">{job.error}</p> : null}
          </section>

          <section className="dedup-section">
            <div className="dedup-section-title">
              <SlidersHorizontal size={13} />
              Отчёт и фильтры
              {activeReport ? (
                <span className="dedup-section-counter">
                  {activeReport.group_count}{" "}
                  {pluralRu(activeReport.group_count, "группа", "группы", "групп")} ·{" "}
                  {activeReport.candidate_count} {copiesWord(activeReport.candidate_count)} на
                  разбор
                  {activeReport.fake_bitrate_candidate_count > 0
                    ? ` · фейк-битрейт ${activeReport.fake_bitrate_candidate_count}`
                    : ""}
                </span>
              ) : null}
            </div>
            <div className="dedup-report-row">
              <label className="dedup-control dedup-control-grow">
                <span>Отчёт</span>
                <select
                  name="dedup-report"
                  value={dedup.reportId ?? ""}
                  disabled={dedup.reports.length === 0}
                  onChange={(event) => dedup.selectReport(event.target.value)}
                >
                  {dedup.reports.length === 0 ? (
                    <option value="">Отчётов пока нет — запустите поиск</option>
                  ) : null}
                  {dedup.reports.map((report) => (
                    <option key={report.report_id} value={report.report_id}>
                      {report.generated_at.replace("T", " ")} ·{" "}
                      {report.search_mode ? audioDedupModeLabel[report.search_mode] : "режим неизвестен"} ·{" "}
                      {report.group_count}{" "}
                      {pluralRu(report.group_count, "группа", "группы", "групп")}
                    </option>
                  ))}
                </select>
              </label>
              {activeReport?.has_xlsx ? (
                <a
                  className="dedup-secondary-button dedup-xlsx-link"
                  href={api.audioDedupXlsxUrl(activeReport.report_id)}
                  title="Скачать XLSX отчёта"
                >
                  <FileSpreadsheet size={15} />
                  XLSX
                  <Download size={13} />
                </a>
              ) : null}
              {activeReport ? (
                <button
                  className="icon-button intent-remove"
                  type="button"
                  disabled={dedup.busy}
                  title="Удалить отчёт"
                  aria-label="Удалить отчёт"
                  onClick={requestReportDelete}
                >
                  <Trash2 size={15} />
                </button>
              ) : null}
            </div>
            <div className="dedup-filter-row">
              <label className="dedup-control">
                <span>Уверенность</span>
                <select
                  name="dedup-confidence"
                  title={helpText.audioDedupConfidence}
                  disabled={filtersDisabled}
                  value={draftFilters.confidence[0] ?? ""}
                  onChange={(event) =>
                    updateFilters({
                      ...draftFilters,
                      confidence: event.target.value ? [event.target.value] : []
                    })
                  }
                >
                  <option value="">любая</option>
                  {dedupConfidenceOptions.map((value) => (
                    <option key={value} value={value}>
                      {confidenceLabel(value)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="dedup-control dedup-fingerprint-control">
                <span>Отпечаток</span>
                <input
                  name="dedup-min-fingerprint"
                  title={helpText.audioDedupFingerprintFloor}
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  placeholder={fingerprintBand}
                  disabled={filtersDisabled || !manualConfidence}
                  value={manualConfidence ? draftFilters.minFingerprint ?? "" : ""}
                  onChange={(event) =>
                    updateFilters({
                      ...draftFilters,
                      minFingerprint: event.target.value === "" ? null : Number(event.target.value)
                    })
                  }
                />
              </label>
              <label className="dedup-control dedup-control-grow">
                <span>Корень папки</span>
                <input
                  name="dedup-path-contains"
                  value={draftFilters.pathContains}
                  title={helpText.audioDedupPathFilter}
                  disabled={filtersDisabled}
                  placeholder="Часть пути папки: Abstracted или M:\Volumes\Abstracted"
                  onChange={(event) =>
                    setDraftFilters({ ...draftFilters, pathContains: event.target.value })
                  }
                  // Typing asks for nothing: the report is filtered when the
                  // reviewer says so, by the button or by Enter in the field.
                  onKeyDown={(event) => {
                    if (event.key === "Enter") dedup.applyFilters(draftFilters);
                  }}
                />
              </label>
              <div className="dedup-path-actions">
                <button
                  className="dedup-secondary-button"
                  type="button"
                  title={helpText.audioDedupPathFilter}
                  disabled={filtersDisabled}
                  onClick={() => dedup.applyFilters(draftFilters)}
                >
                  Применить фильтр
                </button>
                <button
                  className="dedup-secondary-button"
                  type="button"
                  title="Отметить на странице файлы с указанной частью пути, не меняя фильтр"
                  disabled={pageSelectionDisabled || !draftFilters.pathContains.trim()}
                  onClick={() => dedup.markFolderOnPage(draftFilters.pathContains)}
                >
                  Отметить папку
                </button>
              </div>
              <button
                className="dedup-secondary-button"
                type="button"
                title={helpText.audioDedupMarkCandidates}
                disabled={!dedup.page || dedup.page.groups.length === 0}
                onClick={dedup.selectSuggestedOnPage}
              >
                Отметить кандидатов
              </button>
              <button
                className="dedup-secondary-button"
                type="button"
                title="Поменять помеченные и непомеченные файлы на текущей странице"
                disabled={pageSelectionDisabled}
                onClick={dedup.invertSelectionOnPage}
              >
                Инвертировать выбор
              </button>
              <button
                className="dedup-ghost-button"
                type="button"
                disabled={summary.files === 0}
                onClick={dedup.clearSelection}
              >
                Снять всё
              </button>
            </div>
            {/* What the applied filter caught, across the whole report rather
                than the page: the reach of «mp3» is worth seeing before
                anything is marked. */}
            {appliedPathFilter && dedup.page ? (
              <p className="dedup-filter-summary">
                Фильтр «{appliedPathFilter}»: {dedup.page.filtered_copies}{" "}
                {copiesWord(dedup.page.filtered_copies)} в {dedup.page.filtered_groups}{" "}
                {pluralRu(dedup.page.filtered_groups, "группе", "группах", "группах")}
              </p>
            ) : null}
          </section>

          {dedup.error ? (
            <p className="dedup-alert">
              <AlertTriangle size={13} />
              {dedup.error}
            </p>
          ) : null}

          <div className="dedup-groups">
            {dedup.loadingGroups ? (
              <p className="dedup-loading">
                <Loader2 size={15} />
                Загрузка групп…
              </p>
            ) : null}
            {!dedup.loadingGroups && dedup.page && dedup.page.groups.length === 0 ? (
              <p className="empty-state">
                {dedup.page.total_groups === 0
                  ? "В этом отчёте нет групп дубликатов."
                  : "Под фильтры не попала ни одна группа."}
              </p>
            ) : null}
            {!dedup.loadingGroups && !dedup.page ? (
              <p className="empty-state">
                Выберите отчёт или запустите поиск, чтобы начать разбор.
              </p>
            ) : null}
            {dedup.page?.groups.map((group) => (
              <AudioDedupGroupCard
                key={group.group_id}
                group={group}
                selectedTrackIds={dedup.selection[group.group_id] ?? []}
                playingTrackId={playingTrackId}
                onToggleFile={dedup.toggleFile}
                onSetGroup={dedup.setGroup}
                onPreview={onPreview}
              />
            ))}
          </div>

          {dedup.page && dedup.page.filtered_groups > dedup.pageSize ? (
            <div className="dedup-paging">
              <button
                className="dedup-ghost-button"
                type="button"
                disabled={dedup.offset === 0}
                onClick={() => dedup.setOffset(Math.max(0, dedup.offset - dedup.pageSize))}
              >
                Назад
              </button>
              <span>
                {dedup.offset + 1}–{Math.min(dedup.offset + dedup.pageSize, dedup.page.filtered_groups)}{" "}
                из {dedup.page.filtered_groups}
              </span>
              <button
                className="dedup-ghost-button"
                type="button"
                disabled={dedup.offset + dedup.pageSize >= dedup.page.filtered_groups}
                onClick={() => dedup.setOffset(dedup.offset + dedup.pageSize)}
              >
                Вперёд
              </button>
            </div>
          ) : null}
        </div>

        <footer className="dedup-footer">
          <div className="dedup-footer-summary">
            {summary.files > 0 ? (
              <>
                <strong>{summary.files}</strong> {copiesWord(summary.files)} в {summary.groups}{" "}
                {pluralRu(summary.groups, "группе", "группах", "группах")} ·{" "}
                {formatBytes(summary.bytes)}
              </>
            ) : (
              <span className="dedup-footer-idle">Ничего не помечено на удаление</span>
            )}
          </div>
          <label className="dedup-control">
            <span>Куда</span>
            <select
              name="dedup-deletion-mode"
              value={deletionMode}
              onChange={(event) => setDeletionMode(event.target.value as AudioDedupDeletionMode)}
            >
              <option value="trash">В корзину</option>
              <option value="permanent">Безвозвратно</option>
            </select>
          </label>
          <button
            className="dedup-delete-button"
            type="button"
            disabled={!canDelete}
            title={
              summary.files === 0
                ? "Пометьте копии на удаление"
                : `Удалить ${summary.files} ${pluralRu(summary.files, "копию", "копии", "копий")}`
            }
            onClick={requestDelete}
          >
            <Trash2 size={15} />
            Удалить помеченное
          </button>
        </footer>

        {confirmation && (
          <ConfirmationDialog
            request={confirmation}
            onConfirm={confirmPendingAction}
            onCancel={cancelConfirmation}
          />
        )}
      </section>
    </div>
  );
}

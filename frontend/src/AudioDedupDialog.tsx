import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CopyCheck,
  Download,
  FileSpreadsheet,
  FolderOpen,
  Loader2,
  Search,
  SlidersHorizontal,
  Trash2,
  X
} from "lucide-react";
import { api } from "./api";
import type { AudioDedupDeletionMode, AudioDedupFile, AudioDedupSearchMode } from "./api";
import { AudioDedupGroupCard } from "./AudioDedupReview";
import { ConfirmationDialog } from "./dialogs";
import { helpText } from "./helpText";
import {
  confidenceLabel,
  copiesWord,
  dedupConfidenceOptions,
  formatBytes,
  pluralRu,
  selectionSummary
} from "./audioDedupView";
import { useAudioDedup } from "./useAudioDedup";
import type { AudioDedupFilters } from "./useAudioDedup";
import { useConfirmation } from "./useConfirmation";
import { errorText } from "./errors";

export function AudioDedupDialog({
  open,
  playingTrackId,
  onPreview,
  onClose,
  onDeleted
}: {
  open: boolean;
  playingTrackId: number | null;
  onPreview: (file: AudioDedupFile) => void;
  onClose: () => void;
  onDeleted: (message: string) => void;
}) {
  const dedup = useAudioDedup({ open });
  const [root, setRoot] = useState("");
  const [searchMode, setSearchMode] = useState<AudioDedupSearchMode>("fingerprint_scan");
  const [detectFakeBitrate, setDetectFakeBitrate] = useState(false);
  const [deletionMode, setDeletionMode] = useState<AudioDedupDeletionMode>("trash");
  const [draftFilters, setDraftFilters] = useState<AudioDedupFilters>(dedup.filters);
  const { confirmation, requestConfirmation, confirmPendingAction, cancelConfirmation } =
    useConfirmation();

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // Escape answers whatever is on top: the delete prompt first, the dialog after.
      if (confirmation) cancelConfirmation();
      else onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [cancelConfirmation, confirmation, onClose]);

  const activeReport = useMemo(
    () => dedup.reports.find((report) => report.report_id === dedup.reportId) ?? null,
    [dedup.reports, dedup.reportId]
  );
  const summary = useMemo(
    () => selectionSummary(dedup.page?.groups ?? [], dedup.selection),
    [dedup.page, dedup.selection]
  );
  // A report written without a search root has no boundary to delete inside, and
  // the delete endpoint refuses it. Say so here instead of letting the reviewer
  // mark copies and collect a 400.
  const rootlessReport = activeReport !== null && !activeReport.root;
  const canDelete = summary.files > 0 && !dedup.busy && !rootlessReport;
  const selectionText =
    `${summary.files} ${copiesWord(summary.files)}`
    + ` в ${summary.groups} ${pluralRu(summary.groups, "группе", "группах", "группах")}`;

  if (!open) return null;

  const job = dedup.job;
  const progressPercent = job && job.total > 0 ? Math.min(100, (job.processed / job.total) * 100) : 0;

  function updateFilters(next: AudioDedupFilters) {
    setDraftFilters(next);
    dedup.applyFilters(next);
  }

  async function chooseRoot() {
    try {
      const selected = await api.chooseFolder();
      if (selected.path) setRoot(selected.path);
    } catch (error) {
      dedup.setError(errorText(error));
    }
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
              <CopyCheck size={18} />
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
              {job ? (
                <span className="dedup-section-counter">
                  {job.state === "running" || job.state === "queued"
                    ? `${job.current_step ?? "подготовка"} · ${job.processed}/${job.total}`
                    : `${job.state} · ${job.groups} `
                      + pluralRu(job.groups, "группа", "группы", "групп")}
                </span>
              ) : null}
            </div>
            <div className="dedup-scan-grid">
              <label className="dedup-control dedup-control-grow">
                <span>Корень поиска</span>
                <div className="dedup-path-row">
                  <input
                    name="dedup-root"
                    value={root}
                    title={helpText.audioDedupDedupRoot}
                    disabled={dedup.scanRunning}
                    onChange={(event) => setRoot(event.target.value)}
                  />
                  <button
                    className="icon-button"
                    type="button"
                    title="Выбрать папку"
                    aria-label="Выбрать папку"
                    disabled={dedup.scanRunning}
                    onClick={() => void chooseRoot()}
                  >
                    <FolderOpen size={16} />
                  </button>
                </div>
              </label>
            </div>
            <div className="dedup-scan-grid">
              <label className="dedup-control">
                <span>Режим</span>
                <select
                  name="dedup-search-mode"
                  value={searchMode}
                  title={helpText.audioDedupSearchMode[searchMode]}
                  disabled={dedup.scanRunning}
                  onChange={(event) => setSearchMode(event.target.value as AudioDedupSearchMode)}
                >
                  <option value="fingerprint_scan">Fingerprints</option>
                  <option value="fingerprint_lsh">Fingerprints + LSH</option>
                  <option value="embedding">Fingerprints + Embeddings</option>
                </select>
              </label>
              <label
                className={`dedup-toggle ${dedup.scanRunning ? "disabled" : ""}`}
                title={helpText.audioDedupDetectFakeBitrate}
              >
                <input
                  name="dedup-detect-fake-bitrate"
                  type="checkbox"
                  checked={detectFakeBitrate}
                  disabled={dedup.scanRunning}
                  onChange={(event) => setDetectFakeBitrate(event.target.checked)}
                />
                <span>Определение поддельного битрейта</span>
              </label>
            </div>
            <div className="dedup-scan-grid">
              {dedup.scanRunning ? (
                <button
                  className="dedup-secondary-button"
                  type="button"
                  onClick={() => void dedup.cancelScan()}
                >
                  Остановить
                </button>
              ) : (
                <button
                  className="dedup-primary-button"
                  type="button"
                  disabled={dedup.busy}
                  onClick={() =>
                    void dedup.startScan({
                      root: root.trim(),
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
            {dedup.scanRunning ? (
              <div className="dedup-progress">
                <div className="dedup-progress-track">
                  <div
                    className="dedup-progress-fill"
                    style={{ transform: `scaleX(${progressPercent / 100})` }}
                  />
                </div>
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
                  {activeReport.candidate_count} {copiesWord(activeReport.candidate_count)}
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
                      {report.generated_at.replace("T", " ")} · {report.root || "вся база"} ·{" "}
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
            </div>
            <div className="dedup-filter-row">
              <label className="dedup-control">
                <span>Уверенность</span>
                <select
                  name="dedup-confidence"
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
              <label className="dedup-control dedup-control-narrow">
                <span>Отпечаток ≥</span>
                <input
                  name="dedup-min-fingerprint"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  placeholder="0.45"
                  value={draftFilters.minFingerprint ?? ""}
                  onChange={(event) =>
                    updateFilters({
                      ...draftFilters,
                      minFingerprint: event.target.value === "" ? null : Number(event.target.value)
                    })
                  }
                />
              </label>
              <label className="dedup-toggle" title={helpText.audioDedupFakeBitrate}>
                <input
                  name="dedup-fake-bitrate-only"
                  type="checkbox"
                  checked={draftFilters.fakeBitrateOnly}
                  onChange={(event) =>
                    updateFilters({
                      ...draftFilters,
                      fakeBitrateOnly: event.target.checked
                    })
                  }
                />
                <span>Только фейк-битрейт</span>
              </label>
              <label className="dedup-control dedup-control-grow">
                <span>Путь содержит</span>
                <input
                  name="dedup-path-contains"
                  value={draftFilters.pathContains}
                  placeholder="vinyl"
                  onChange={(event) =>
                    setDraftFilters({ ...draftFilters, pathContains: event.target.value })
                  }
                  onBlur={() => dedup.applyFilters(draftFilters)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") dedup.applyFilters(draftFilters);
                  }}
                />
              </label>
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
                className="dedup-ghost-button"
                type="button"
                disabled={summary.files === 0}
                onClick={dedup.clearSelection}
              >
                Снять всё
              </button>
            </div>
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
                searchMode={dedup.page?.search_mode ?? ""}
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
            {rootlessReport ? (
              <span className="dedup-footer-idle">
                Отчёт по всей базе: удалять можно только из отчёта с корнем поиска
              </span>
            ) : summary.files > 0 ? (
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
              rootlessReport
                ? "Отчёт построен по всей базе. Удаление держится внутри корня поиска, поэтому повторите поиск, указав корень."
                : summary.files === 0
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

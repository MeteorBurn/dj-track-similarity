import { useEffect } from "react";
import { X } from "lucide-react";
import type { AnalysisJobStatus, GenreTagJobStatus, ScanStats } from "./api";
import type { ConfirmationRequest } from "./confirmation";
import type { ActivityEvent } from "./jobUi";
import { UnifiedLog } from "./jobUi";

export function LogFrameDialog({
  processLogKind,
  scanJob,
  analysisJob,
  genreTagJob,
  activityLog,
  onClose
}: {
  processLogKind: "scan" | "analysis" | "genre_tags";
  scanJob: ScanStats | null;
  analysisJob: AnalysisJobStatus | null;
  genreTagJob: GenreTagJobStatus | null;
  activityLog: ActivityEvent[];
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="log-frame-backdrop" onClick={onClose}>
      <section className="log-frame-dialog" role="dialog" aria-modal="true" aria-labelledby="log-frame-title" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title log-frame-title">
          <div>
            <h2 id="log-frame-title">Лог</h2>
            <span>События интерфейса, сканирования, анализа и записи жанров</span>
          </div>
          <button className="icon-button close-log-frame-button" title="Закрыть лог" aria-label="Закрыть лог" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>
        <div className="log-frame-content">
          <UnifiedLog
            processKind={processLogKind}
            scanJob={scanJob}
            analysisJob={analysisJob}
            genreTagJob={genreTagJob}
            events={activityLog}
            className="log-frame-panel"
          />
        </div>
      </section>
    </div>
  );
}

export function ConfirmationDialog({
  request,
  onConfirm,
  onCancel
}: {
  request: ConfirmationRequest;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="confirmation-backdrop" role="presentation">
      <div className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmation-title">
        <h2 id="confirmation-title">{request.title}</h2>
        <p>{request.message}</p>
        <div className="confirmation-actions">
          <button className="confirmation-cancel-button" title="Отменить действие" type="button" onClick={onCancel}>Нет</button>
          <button className="confirmation-confirm-button" title="Подтвердить действие" type="button" onClick={onConfirm}>Да</button>
        </div>
      </div>
    </div>
  );
}

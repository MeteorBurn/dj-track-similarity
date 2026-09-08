import type { TextSearchExecution } from "./api";

const feedbackReasons: Record<TextSearchExecution["feedback"]["reason"], string> = {
  not_requested: "Персонализация выключена",
  schema_unavailable: "Хранилище оценок недоступно: требуется обновление библиотеки",
  insufficient_relevant: "Недостаточно пригодных оценок этого запроса",
  invalid_centroid: "История оценок не дала пригодной поправки",
  applied: "Персонализация по оценкам этого запроса применена",
};

export function TextExecutionDetails({ execution }: { execution: TextSearchExecution }) {
  const context = execution.query_context;
  return <details className="text-prompt-hint">
    <summary>Выполненный запрос · доступно треков: {execution.eligible_count} · {feedbackReasons[execution.feedback.reason]}</summary>
    <div>Модель: {context.analysis_family} · Limit: {execution.limit} · вес negatives: {context.negative_weight}</div>
    <div>Пригодная история: +{execution.feedback.usable_relevant_count} / −{execution.feedback.usable_irrelevant_count}</div>
    {execution.feedback_capability !== "ready" ? <div>Запись оценок недоступна до обновления библиотеки.</div> : null}
    <div>Prompt</div><pre style={{ whiteSpace: "pre-wrap" }}>{context.positive_queries.join("\n")}</pre>
    {context.negative_queries.length ? <><div>Negatives</div><pre style={{ whiteSpace: "pre-wrap" }}>{context.negative_queries.join("\n")}</pre></> : null}
  </details>;
}

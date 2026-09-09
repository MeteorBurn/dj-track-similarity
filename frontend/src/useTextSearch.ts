import { useEffect, useRef, useState } from "react";
import { api, type Track, type TextSearchExecution } from "./api";
import { composePromptBanks, presetByKey } from "./textPromptPresets";
import { buildTextSearchArms, settleTextSearchArm, type TextFamily, type TextSearchArm } from "./textSearchExecution";
import type { SearchRequestLifecycle, SearchNotice } from "./useSearchRequests";
import type { SearchFiltersState } from "./SearchPlaylistPanel";
import type { useActivityLog } from "./useActivityLog";

type Verdicts = Partial<Record<TextFamily, Record<string, 1 | -1>>>;
type Options = {
  databasePath: string | null; databaseCatalogUuid: string | null;
  embeddingCounts?: Record<TextFamily, number>;
  filters: SearchFiltersState; analysisDevice: "auto" | "cpu" | "cuda";
  setNotice: (notice: SearchNotice) => void;
  appendActivity: ReturnType<typeof useActivityLog>["appendActivity"];
};

export function useTextSearch({ databasePath, databaseCatalogUuid,
  filters, analysisDevice, setNotice, appendActivity, embeddingCounts }: Options) {
  const [selectedPresetKeys, setSelectedPresetKeys] = useState<string[]>([]);
  const [textCompareModels, setTextCompareModels] = useState(false);
  const [textUseNegativePrompt, setTextUseNegativePrompt] = useState(false);
  const [textEmbeddingFamily, setTextEmbeddingFamily] = useState<TextFamily>("mulan");
  const [textModelLoadingLabel, setTextModelLoadingLabel] = useState<string | null>(null);
  const [textComparison, setTextComparison] = useState<TextSearchArm[] | null>(null);
  const [textFeedbackVerdicts, setTextFeedbackVerdicts] = useState<Verdicts>({});
  const [executions, setExecutions] = useState<Partial<Record<TextFamily, TextSearchExecution>>>({});
  const [feedbackPending, setFeedbackPending] = useState<Record<string, boolean>>({});
  const [feedbackReady, setFeedbackReady] = useState<Record<string, boolean>>({});
  const revisions = useRef<Record<string, number>>({});
  const pending = useRef(new Set<string>());
  const touched = useRef(new Set<string>());
  const executionRef = useRef(executions);
  executionRef.current = executions;
  const generation = useRef(0);
  const inputKey = JSON.stringify([databasePath, databaseCatalogUuid, selectedPresetKeys, textCompareModels,
    textUseNegativePrompt, textEmbeddingFamily, filters.limit, analysisDevice]);
  const currentInput = useRef(inputKey);
  // Invalidate synchronously at render, before any old async completion can publish.
  if (currentInput.current !== inputKey) {
    currentInput.current = inputKey;
    generation.current += 1;
  }
  useEffect(() => {
    setTextComparison(null); setExecutions({}); setTextFeedbackVerdicts({});
    setTextModelLoadingLabel(null); setFeedbackPending({}); setFeedbackReady({});
    revisions.current = {}; pending.current.clear(); touched.current.clear();
  }, [inputKey]);
  useEffect(() => () => { generation.current += 1; }, []);
  function cancelTextSearch() {
    generation.current += 1;
    executionRef.current = {};
    setTextModelLoadingLabel(null); setTextComparison(null); setExecutions({});
    setTextFeedbackVerdicts({}); setFeedbackPending({}); setFeedbackReady({});
    revisions.current = {}; pending.current.clear(); touched.current.clear();
  }

  const banks = composePromptBanks(selectedPresetKeys, textEmbeddingFamily);
  const textQuery = banks.positiveText;
  const textNegativeQuery = banks.negativeText;
  const promptNegativeWeight = banks.negativeWeight;
  function clearPromptPresets() { setSelectedPresetKeys([]); }
  function togglePromptPreset(key: string) {
    const preset = presetByKey(key);
    if (!preset) return;
    setSelectedPresetKeys((current) => current.includes(key)
      ? current.filter((item) => item !== key)
      : [...current.filter((item) => presetByKey(item)?.axis !== preset.axis), key]);
  }
  function changeTextEmbeddingFamily(model: TextFamily) {
    setTextEmbeddingFamily(model);
  }

  async function handleTextSearch(requests: SearchRequestLifecycle) {
    if (!textQuery.trim()) { setNotice({ kind: "error", text: "Выберите метку для поиска" }); return; }
    const runGeneration = ++generation.current;
    const ticket = requests.beginGenericSearchRequest();
    const isCurrent = () => generation.current === runGeneration && requests.genericSearchRequestIsCurrent(ticket);
    let arms = buildTextSearchArms({ family: textEmbeddingFamily, compare: textCompareModels,
      keys: selectedPresetKeys, useNegative: textUseNegativePrompt, limit: filters.limit,
      device: analysisDevice, comparisonId: crypto.randomUUID() });
    setTextComparison(textCompareModels ? arms : null); setExecutions({}); setTextFeedbackVerdicts({});
    revisions.current = {}; touched.current.clear(); pending.current.clear(); setFeedbackPending({}); setFeedbackReady({});
    requests.commitGenericSearchResults(ticket, "text", []);
    appendActivity("info", "Text search запущен", textCompareModels ? "A/B" : textEmbeddingFamily);
    try {
      // Keep model loading sequential, but commit each arm independently.
      for (const arm of [...arms]) {
        if (!isCurrent()) return;
        setTextModelLoadingLabel(arm.label);
        try {
          if (embeddingCounts && embeddingCounts[arm.family] === 0) throw new Error(`${arm.label}: нет сохранённых embeddings, требуется анализ.`);
          const response = await api.textSearch(arm.payload, { signal: ticket.controller.signal });
          if (!isCurrent()) return;
          arms = settleTextSearchArm(arms, { family: arm.family, response });
          setExecutions((previous) => ({ ...previous, [arm.family]: response.execution }));
          if (response.execution.feedback_capability === "ready" && response.results.length) {
            const runId = response.execution.run_id;
            void api.textSearchFeedbackLookup({ run_id: runId, track_uuids: response.results.map((row) => row.track.track_uuid) },
              { signal: ticket.controller.signal }).then((stored) => {
              if (!isCurrent()) return;
              setFeedbackReady((old) => ({ ...old, [runId]: true }));
              setTextFeedbackVerdicts((previous) => {
                const familyVerdicts = { ...previous[arm.family] };
                for (const [uuid, entry] of Object.entries(stored.verdicts)) {
                  const key = `${runId}:${uuid}`;
                  if (touched.current.has(key)) continue;
                  revisions.current[key] = entry.revision;
                  if (entry.verdict) familyVerdicts[uuid] = entry.verdict;
                  else delete familyVerdicts[uuid];
                }
                return { ...previous, [arm.family]: familyVerdicts };
              });
            }).catch(() => {
              if (isCurrent()) setNotice({ kind: "error", text: "Не удалось прочитать оценки запроса. Повторите поиск перед новой оценкой." });
            });
          }
        } catch (error) {
          if (!isCurrent()) return;
          arms = settleTextSearchArm(arms, { family: arm.family,
            error: error instanceof Error ? error.message : String(error) });
        }
        if (!isCurrent()) return;
        setTextComparison(textCompareModels ? [...arms] : null);
        requests.commitGenericSearchResults(ticket, "text", arms.find((item) => item.status === "success")?.results ?? []);
      }
      const successes = arms.filter((arm) => arm.status === "success");
      const message = arms.map((arm) => `${arm.label}: ${arm.status === "success" ? arm.results.length : arm.error}`).join(" · ");
      setNotice({ kind: successes.length ? "ok" : "error", text: message });
      appendActivity(successes.length ? "ok" : "error", "Text search завершён", message);
    } finally {
      if (isCurrent()) setTextModelLoadingLabel(null);
      requests.finishGenericSearchRequest(ticket);
    }
  }

  async function handleTextResultFeedback(track: Track, verdict: 1 | -1, family: TextFamily) {
    const execution = executionRef.current[family];
    if (!execution || execution.feedback_capability !== "ready" || !feedbackReady[execution.run_id]) return;
    const key = `${execution.run_id}:${track.track_uuid}`;
    if (pending.current.has(key)) return;
    const runGeneration = generation.current;
    pending.current.add(key); touched.current.add(key); setFeedbackPending((old) => ({ ...old, [key]: true }));
    const next = textFeedbackVerdicts[family]?.[track.track_uuid] === verdict ? 0 : verdict;
    try {
      const stored = await api.textSearchFeedback({ run_id: execution.run_id, track_uuid: track.track_uuid,
        verdict: next, expected_revision: revisions.current[key] ?? 0 });
      if (generation.current !== runGeneration) return;
      revisions.current[key] = stored.revision;
      setTextFeedbackVerdicts((previous) => {
        const values = { ...previous[family] };
        if (stored.verdict) values[track.track_uuid] = stored.verdict; else delete values[track.track_uuid];
        return { ...previous, [family]: values };
      });
    } catch (error) {
      if (generation.current !== runGeneration) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: `${message}. Повторите поиск, чтобы обновить контекст оценок.` });
      appendActivity("error", "Оценка запроса не записана", message);
      // A stale revision or expired context must be refreshed by a new search.
      setExecutions((old) => { const updated = { ...old }; delete updated[family]; return updated; });
    } finally {
      if (generation.current === runGeneration) {
        pending.current.delete(key);
        setFeedbackPending((old) => { const updated = { ...old }; delete updated[key]; return updated; });
      }
    }
  }
  return { selectedPresetKeys,
    textFeedbackContext: executions[textEmbeddingFamily] ?? null, executions, feedbackPending, feedbackReady,
    textFeedbackVerdicts, textCompareModels, setTextCompareModels, textModelLoadingLabel, textComparison,
    textQuery, textNegativeQuery, promptNegativeWeight, textUseNegativePrompt, setTextUseNegativePrompt, textEmbeddingFamily,
    cancelTextSearch, clearPromptPresets, togglePromptPreset, changeTextEmbeddingFamily, handleTextSearch, handleTextResultFeedback };
}

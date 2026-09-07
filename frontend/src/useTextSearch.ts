import { useEffect, useState } from "react";
import { api, type Track, type SearchResult } from "./api";
import {
  composePromptBanks,
  modelAdvice,
  presetByKey,
  promptQueriesFromText,
  resolvePromptVariants,
} from "./textPromptPresets";
import type { SearchRequestLifecycle, SearchNotice } from "./useSearchRequests";
import type { SearchFiltersState } from "./SearchPlaylistPanel";
import type { useActivityLog } from "./useActivityLog";

type TextEmbeddingFamily = "clap" | "mulan";
type TextVerdictsByFamily = Partial<Record<TextEmbeddingFamily, Record<string, 1 | -1>>>;
type TextPresetTally = Record<
  string,
  Partial<Record<TextEmbeddingFamily, { relevant: number; irrelevant: number }>>
>;
type TextComparisonColumn = {
  family: TextEmbeddingFamily;
  label: string;
  results: SearchResult[];
};
type TextSearchOptions = {
  databasePath: string | null;
  databaseCatalogUuid: string | null;
  textQuery: string;
  setTextQuery: (value: string) => void;
  filters: SearchFiltersState;
  analysisDevice: "auto" | "cpu" | "cuda";
  setNotice: (notice: SearchNotice) => void;
  appendActivity: ReturnType<typeof useActivityLog>["appendActivity"];
};

export function useTextSearch({
  databasePath,
  databaseCatalogUuid,
  textQuery,
  setTextQuery,
  filters,
  analysisDevice,
  setNotice,
  appendActivity,
}: TextSearchOptions) {
  const [selectedPresetKeys, setSelectedPresetKeys] = useState<string[]>([]);
  // Snapshot of the presets that built the last text search: verdicts credit
  // the bank that actually ranked the list, not whatever the picker holds now.
  const [textFeedbackContext, setTextFeedbackContext] = useState<{
    presetKeys: string[];
    family: "clap" | "mulan";
  } | null>(null);
  // Keyed by model, because A/B shows one track in two lists at once and a
  // verdict belongs to the model that ranked it, not to the track.
  const [textFeedbackVerdicts, setTextFeedbackVerdicts] = useState<TextVerdictsByFamily>({});
  // How well each selected label matched a track on its own, as the search
  // reported it. A verdict then lands on the label that earned it instead of
  // being split evenly across everything that happened to be selected.
  const [textPresetScores, setTextPresetScores] = useState<Record<string, Record<string, Record<string, number>>>>({});
  // Both models run against the same bank, each keeping its own ranked list.
  // Turned on deliberately: it is two searches and two sets of weights resident,
  // which is a price worth paying to settle a model, not to run a search.
  const [textCompareModels, setTextCompareModels] = useState(false);
  // Model names the running text search is loading into memory first, or null.
  const [textModelLoadingLabel, setTextModelLoadingLabel] = useState<string | null>(null);
  const [textComparison, setTextComparison] = useState<TextComparisonColumn[] | null>(null);
  // What has been said about each label so far, per model. The picker holds 240
  // of them, and the ones worth comparing models on are the ones where a model
  // misses — a label nobody has judged has nothing to say either way.
  const [textPresetTally, setTextPresetTally] = useState<TextPresetTally>({});
  // Let the accumulated verdicts pull the query. Off by default and never in
  // A/B: the offsets live in each model's own space, so a comparison running
  // under them would measure the clicks rather than the models.
  const [textUseFeedback, setTextUseFeedback] = useState(false);
  const [promptNegativeWeight, setPromptNegativeWeight] = useState<number | null>(null);
  const [textNegativeQuery, setTextNegativeQuery] = useState("");
  const [textUseNegativePrompt, setTextUseNegativePrompt] = useState(true);
  const [textEmbeddingFamily, setTextEmbeddingFamily] = useState<"clap" | "mulan">("mulan");

  function applyPromptPresets(keys: string[], model: "clap" | "mulan" = textEmbeddingFamily) {
    const banks = composePromptBanks(keys, model);
    setSelectedPresetKeys(keys);
    setTextEmbeddingFamily(model);
    setTextQuery(banks.positiveText);
    setTextNegativeQuery(banks.negativeText);
    setPromptNegativeWeight(banks.negativeWeight);
  }

  function togglePromptPreset(key: string) {
    const keys = selectedPresetKeys.includes(key)
      ? selectedPresetKeys.filter((item) => item !== key)
      : [...selectedPresetKeys, key];
    // Where the measurement points at one model the selection follows it, so
    // the choice stops being a switch to remember. Where it points at two, or
    // at none, the current model stands and the tab says which case it is.
    const advice = modelAdvice(keys);
    applyPromptPresets(keys, advice.kind === "single" ? advice.model : textEmbeddingFamily);
  }

  function changeTextEmbeddingFamily(model: "clap" | "mulan") {
    setTextEmbeddingFamily(model);
    // Preset wording and hard-negative weight are calibrated per family, so a
    // selected bank has to be rebuilt when the model changes under it.
    if (selectedPresetKeys.length) applyPromptPresets(selectedPresetKeys, model);
  }
  // The tally belongs to the open library, so it is read when one is chosen
  // and cleared when none is.
  useEffect(() => {
    if (!databasePath) {
      setTextPresetTally({});
      return;
    }
    refreshTextPresetTally();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [databasePath, databaseCatalogUuid]);

  function presetBanksFor(family: TextEmbeddingFamily) {
    return selectedPresetKeys
      .map((key) => {
        const preset = presetByKey(key);
        if (!preset) return null;
        const queries = resolvePromptVariants(preset.positive, family);
        return queries.length ? { key, positive_queries: queries } : null;
      })
      .filter((bank): bank is { key: string; positive_queries: string[] } => bank !== null);
  }

  function familyLabel(family: TextEmbeddingFamily) {
    return family === "mulan" ? "MuQ-MuLan" : "CLAP";
  }

  async function handleTextSearch(requests: SearchRequestLifecycle) {
    const { beginGenericSearchRequest, genericSearchRequestIsCurrent, commitGenericSearchResults, finishGenericSearchRequest } = requests;
    const prompt = textQuery.trim();
    if (!prompt) {
      setNotice({ kind: "error", text: `Введите текстовый запрос для ${familyLabel(textEmbeddingFamily)}` });
      return;
    }
    const families: TextEmbeddingFamily[] = textCompareModels
      ? ["mulan", "clap"]
      : [textEmbeddingFamily];
    // Each model reads its own wording. There is no neutral text to compare on:
    // the vocabulary carries per-model variants precisely because the two towers
    // were trained on different language, so one shared bank would test whichever
    // model it was not written for on prose that suits it worse. What ships is a
    // model together with its own bank, and that is the pair worth comparing.
    //
    // A hand-edited field is the exception: once the text stops matching what the
    // selection composes, it is the question being asked, and both models get it.
    const composedForTab = selectedPresetKeys.length
      ? composePromptBanks(selectedPresetKeys, textEmbeddingFamily)
      : null;
    const bankIsUnedited =
      composedForTab !== null
      && composedForTab.positiveText === textQuery
      && composedForTab.negativeText === textNegativeQuery;
    const queriesFor = (family: TextEmbeddingFamily) => {
      if (!bankIsUnedited || family === textEmbeddingFamily) {
        return promptQueriesFromText(prompt, textNegativeQuery, textUseNegativePrompt);
      }
      const banks = composePromptBanks(selectedPresetKeys, family);
      return promptQueriesFromText(banks.positiveText, banks.negativeText, textUseNegativePrompt);
    };
    const weightFor = (family: TextEmbeddingFamily) =>
      bankIsUnedited && family !== textEmbeddingFamily
        ? composePromptBanks(selectedPresetKeys, family).negativeWeight
        : promptNegativeWeight;
    const label = textCompareModels ? "A/B" : familyLabel(textEmbeddingFamily);
    const ticket = beginGenericSearchRequest();
    appendActivity("info", `${label} search запущен`, prompt);
    try {
      // The first search after an idle period pays the weight load. Ask what is
      // resident and say so while it waits, instead of a silent minute.
      const resident = await api
        .textSearchWarmupStatus({ signal: ticket.controller.signal })
        .then((status) => new Set(status.loaded.map((entry) => entry.analysis_family)))
        .catch(() => null);
      if (!genericSearchRequestIsCurrent(ticket)) return;
      const pending = resident ? families.filter((family) => !resident.has(family)) : [];
      if (pending.length) {
        const pendingLabel = pending.map(familyLabel).join(" и ");
        setTextModelLoadingLabel(pendingLabel);
        appendActivity("info", `${pendingLabel} загружается в память`, "Первый поиск ждёт веса");
      }
      const columns: TextComparisonColumn[] = [];
      for (const family of families) {
        const presetBanks = presetBanksFor(family);
        const { positiveQueries, negativeQueries } = queriesFor(family);
        const familyNegativeWeight = weightFor(family);
        const value = await api.textSearch({
          analysis_family: family,
          positive_queries: positiveQueries,
          negative_queries: negativeQueries,
          ...(presetBanks.length ? { preset_banks: presetBanks } : {}),
          ...(textUseFeedback && !textCompareModels && presetBanks.length
            ? { use_feedback: true }
            : {}),
          ...(negativeQueries.length && familyNegativeWeight !== null
            ? { negative_weight: familyNegativeWeight }
            : {}),
          limit: filters.limit,
          device: analysisDevice
        }, {
          signal: ticket.controller.signal,
        });
        if (!genericSearchRequestIsCurrent(ticket)) return;
        columns.push({ family, label: familyLabel(family), results: value });
      }

      // The first column also feeds the shared result list, so preview, the
      // set and everything else keeps working off one source in both modes.
      if (!commitGenericSearchResults(ticket, "text", columns[0].results)) return;
      const presetKeys = [...selectedPresetKeys];
      setTextComparison(textCompareModels ? columns : null);
      setTextFeedbackContext(presetKeys.length ? { presetKeys, family: textEmbeddingFamily } : null);
      setTextFeedbackVerdicts({});
      setTextPresetScores(
        Object.fromEntries(
          columns.map((column) => [
            column.family,
            Object.fromEntries(
              column.results
                .filter((result) => result.preset_scores)
                .map((result) => [result.track.track_uuid, result.preset_scores as Record<string, number>])
            )
          ])
        )
      );
      // What you already said about a track outlives the search that showed
      // it. Without this the same row comes back unmarked in the next search
      // and invites a second, blinder vote on top of the first.
      if (presetKeys.length) {
        for (const column of columns) {
          if (!column.results.length) continue;
          void api
            .textSearchFeedbackLookup({
              track_uuids: column.results.map((result) => result.track.track_uuid),
              preset_keys: presetKeys,
              analysis_family: column.family
            }, { signal: ticket.controller.signal })
            .then((stored) => {
              if (!genericSearchRequestIsCurrent(ticket)) return;
              setTextFeedbackVerdicts((previous) => ({ ...previous, [column.family]: stored.verdicts }));
            })
            .catch(() => {
              // A missing history is not a failed search: the rows simply show
              // unmarked, which is what they showed before this call existed.
            });
        }
      }
      const found = columns.map((column) => `${column.label} ${column.results.length}`).join(" · ");
      appendActivity("ok", `${label} search завершен`, `Найдено: ${found}`);
      setNotice({ kind: "ok", text: `Найдено: ${found}` });
    } catch (error) {
      if (!genericSearchRequestIsCurrent(ticket) || isAbortError(error)) return;
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", `${label} search недоступен`, message);
    } finally {
      setTextModelLoadingLabel(null);
      finishGenericSearchRequest(ticket);
    }
  }

  function refreshTextPresetTally() {
    void api
      .textSearchFeedbackSummary()
      .then((summary) => setTextPresetTally(summary.presets))
      .catch(() => {
        // A library with no verdicts yet simply shows none.
      });
  }

  async function handleTextResultFeedback(
    track: Track,
    verdict: 1 | -1,
    family: TextEmbeddingFamily
  ) {
    if (!textFeedbackContext) return;
    // A verdict belongs to the model whose list it was cast in: in A/B the same
    // track sits in both, and the two answers may honestly differ.
    const current = textFeedbackVerdicts[family]?.[track.track_uuid];
    const next: -1 | 0 | 1 = current === verdict ? 0 : verdict;
    try {
      const measured = textPresetScores[family]?.[track.track_uuid];
      await api.textSearchFeedback({
        track_uuid: track.track_uuid,
        preset_keys: textFeedbackContext.presetKeys,
        analysis_family: family,
        verdict: next,
        ...(measured ? { preset_scores: measured } : {})
      });
      setTextFeedbackVerdicts((previous) => {
        const forFamily = { ...(previous[family] ?? {}) };
        if (next === 0) delete forFamily[track.track_uuid];
        else forFamily[track.track_uuid] = next;
        return { ...previous, [family]: forFamily };
      });
      refreshTextPresetTally();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNotice({ kind: "error", text: message });
      appendActivity("error", "Preset feedback не записан", message);
    }
  }

  return {
    selectedPresetKeys,
    textFeedbackContext,
    textFeedbackVerdicts,
    textCompareModels,
    setTextCompareModels,
    textModelLoadingLabel,
    textComparison,
    textPresetTally,
    textUseFeedback,
    setTextUseFeedback,
    promptNegativeWeight,
    textNegativeQuery,
    setTextNegativeQuery,
    textUseNegativePrompt,
    setTextUseNegativePrompt,
    textEmbeddingFamily,
    applyPromptPresets,
    togglePromptPreset,
    changeTextEmbeddingFamily,
    handleTextSearch,
    handleTextResultFeedback,
  };
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

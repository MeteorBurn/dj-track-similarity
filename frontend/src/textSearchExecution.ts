import type { SearchResult, TextSearchExecution } from "./api";
import type { TextSearchPayload } from "./apiClient";
import { composePromptBanks, presetByKey, promptQueriesFromText, resolvePromptVariants } from "./textPromptPresets";

export type TextFamily = "clap" | "mulan";
export type TextSearchArm = {
  family: TextFamily;
  label: string;
  payload: TextSearchPayload;
  status: "pending" | "success" | "error";
  results: SearchResult[];
  execution?: TextSearchExecution;
  error?: string;
};

export function buildTextSearchArms(input: {
  family: TextFamily; compare: boolean;
  keys: string[]; useNegative: boolean; limit: number;
  device: "auto" | "cpu" | "cuda"; comparisonId: string;
}): TextSearchArm[] {
  const families: TextFamily[] = input.compare ? ["mulan", "clap"] : [input.family];
  return families.map((family) => {
    const composed = composePromptBanks(input.keys, family);
    const queries = promptQueriesFromText(
      composed.positiveText,
      composed.negativeText,
      input.useNegative,
    );
    const weight = composed.negativeWeight;
    return {
      family, label: family === "clap" ? "CLAP" : "MuQ-MuLan", status: "pending", results: [],
      payload: {
        analysis_family: family, positive_queries: queries.positiveQueries,
        negative_queries: queries.negativeQueries,
        ...(queries.negativeQueries.length && weight !== null ? { negative_weight: weight } : {}),
        preset_banks: input.keys.flatMap((key) => {
          const preset = presetByKey(key);
          return preset ? [{ key, positive_queries: [...resolvePromptVariants(preset.positive, family)] }] : [];
        }),
        input_mode: "preset", comparison_mode: input.compare ? "product_ab" : "single",
        ...(input.compare ? { comparison_id: input.comparisonId } : {}),
        use_feedback: true,
        limit: input.limit, device: input.device,
      },
    };
  });
}

export function settleTextSearchArm(
  arms: TextSearchArm[],
  completion: { family: TextFamily; response?: { results: SearchResult[]; execution: TextSearchExecution }; error?: string },
): TextSearchArm[] {
  return arms.map((arm) => arm.family !== completion.family ? arm : completion.response
    ? { ...arm, status: "success", ...completion.response }
    : { ...arm, status: "error", error: completion.error, results: [] });
}

import type { AnalysisModel, AnalysisPipelineStage } from "./api";

export type AnalysisSelection = AnalysisModel;

// The library-panel checkbox set: DATABASE (load tracks) plus every analysis
// model. DATABASE is not an AnalysisModel — it has no backend analysis job —
// so it only exists at this frontend selection layer.
export type StageSelection = "database" | AnalysisSelection;

export const audioAnalysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "muq", "mulan", "clap"];
export const mlAnalysisModelOrder: AnalysisModel[] = ["maest", "mert", "muq", "mulan", "clap"];
export const analysisSelectionOrder: AnalysisSelection[] = [...audioAnalysisModelOrder];
export const defaultStageSelections: StageSelection[] = ["sonara"];

export function analysisStartBlockedByMissingSonara(
  selections: readonly AnalysisSelection[],
  currentSonaraTrackCount: number
) {
  if (currentSonaraTrackCount > 0 || selections.includes("sonara")) {
    return false;
  }
  return selections.some((selection) => selection !== "sonara");
}

export const analysisModelLabels: Record<AnalysisModel, string> = {
  sonara: "SONARA",
  maest: "MAEST",
  mert: "MERT",
  muq: "MuQ",
  mulan: "MuQ-MuLan",
  clap: "CLAP"
};

function trackWord(count: number) {
  const tail = count % 100;
  if (tail >= 11 && tail <= 14) return "треков";
  const last = count % 10;
  if (last === 1) return "трек";
  if (last >= 2 && last <= 4) return "трека";
  return "треков";
}

export function describeAnalysisStart(
  order: readonly AnalysisPipelineStage[],
  mlModels: readonly AnalysisModel[],
  limit?: number
) {
  const stages = order.map((stage) => {
    if (stage === "sonara") return "SONARA";
    if (stage === "classifiers") return "классификаторы";
    if (!mlModels.length) return "ML-модели";
    return `модели ${mlModels.map((model) => analysisModelLabels[model]).join(", ")}`;
  });
  const scope = limit && limit > 0 ? `${limit} ${trackWord(limit)}` : "вся библиотека";
  return `Анализ запущен: ${stages.join(", затем ")} · ${scope}`;
}

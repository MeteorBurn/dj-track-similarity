import type { AnalysisModel } from "./api";

export type AnalysisSelection = AnalysisModel | "classifiers";

export const audioAnalysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "muq", "clap"];
export const mlAnalysisModelOrder: AnalysisModel[] = ["maest", "mert", "muq", "clap"];
export const analysisSelectionOrder: AnalysisSelection[] = [...audioAnalysisModelOrder, "classifiers"];
export const defaultAnalysisSelections: AnalysisSelection[] = [...mlAnalysisModelOrder];

export function isAudioAnalysisModel(model: AnalysisSelection): model is AnalysisModel {
  return model !== "classifiers";
}

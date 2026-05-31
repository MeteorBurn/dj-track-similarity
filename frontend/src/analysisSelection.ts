import type { AnalysisModel } from "./api";

export type AnalysisSelection = AnalysisModel | "classifiers";

export const audioAnalysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "clap"];
export const defaultAnalysisSelections: AnalysisSelection[] = [...audioAnalysisModelOrder];

export function isAudioAnalysisModel(model: AnalysisSelection): model is AnalysisModel {
  return model !== "classifiers";
}

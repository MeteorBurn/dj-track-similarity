import type { AnalysisModel } from "./api";

export type AnalysisSelection = AnalysisModel;

export const audioAnalysisModelOrder: AnalysisModel[] = ["sonara", "maest", "mert", "muq", "mulan", "clap"];
export const mlAnalysisModelOrder: AnalysisModel[] = ["maest", "mert", "muq", "mulan", "clap"];
export const analysisSelectionOrder: AnalysisSelection[] = [...audioAnalysisModelOrder];
export const defaultAnalysisSelections: AnalysisSelection[] = ["sonara"];

export function analysisStartBlockedByMissingSonara(
  selections: readonly AnalysisSelection[],
  currentSonaraTrackCount: number
) {
  if (currentSonaraTrackCount > 0 || selections.includes("sonara")) {
    return false;
  }
  return selections.some((selection) => selection !== "sonara");
}

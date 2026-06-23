export const setBuilderDefaultDiversity = 0.35;
export const setBuilderDefaultFlow = "flat" as const;

export type SetBuilderClassifierFlow = "flat" | "rise" | "fall";

export type SetBuilderSliderState = {
  diversity: number;
  classifierPreferences: Record<string, number>;
  classifierFlows: Record<string, SetBuilderClassifierFlow>;
};

export function resetSetBuilderSliders(): SetBuilderSliderState {
  return {
    diversity: setBuilderDefaultDiversity,
    classifierPreferences: {},
    classifierFlows: {},
  };
}

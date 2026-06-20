export const setBuilderDefaultDiversity = 0.35;
export const setBuilderDefaultCurve = { start: 0.5, end: 0.5 } as const;

export type SetBuilderClassifierCurve = {
  start: number;
  end: number;
};

export type SetBuilderSliderState = {
  diversity: number;
  classifierTargets: Record<string, number>;
  classifierAvoid: Record<string, number>;
  classifierCurves: Record<string, SetBuilderClassifierCurve>;
};

export function resetSetBuilderSliders(): SetBuilderSliderState {
  return {
    diversity: setBuilderDefaultDiversity,
    classifierTargets: {},
    classifierAvoid: {},
    classifierCurves: {},
  };
}

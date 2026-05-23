import { formatMaestGenreLabel } from "./maestGenres";

export { formatMaestGenreLabel };

export const SYNCOPATED_RHYTHM_LABEL = "syncopated rhythm";

export function hasMaestSyncopatedRhythm(metadata: Record<string, unknown> | null | undefined) {
  return metadata?.maest_syncopated_rhythm === true;
}

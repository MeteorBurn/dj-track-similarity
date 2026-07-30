import type { TrackDetail } from "./api";
import { formatMaestGenreLabel } from "./maestGenres";

export { formatMaestGenreLabel };

export const SYNCOPATED_RHYTHM_LABEL = "syncopated rhythm";

export function hasMaestSyncopatedRhythm(track: TrackDetail) {
  return track.maest?.syncopated_rhythm === true;
}

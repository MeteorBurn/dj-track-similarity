import type { TrackDetailV7 } from "./api";
import { formatMaestGenreLabel } from "./maestGenres";

export { formatMaestGenreLabel };

export const SYNCOPATED_RHYTHM_LABEL = "syncopated rhythm";

export function hasMaestSyncopatedRhythm(track: TrackDetailV7) {
  return track.maest?.syncopated_rhythm === true;
}

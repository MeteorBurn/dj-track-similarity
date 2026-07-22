import { Track, TrackDetailV7 } from "./api";
import { formatMaestGenreLabel } from "./maestGenres";

export { formatMaestGenreLabel };

export const SYNCOPATED_RHYTHM_LABEL = "syncopated rhythm";

export function hasMaestSyncopatedRhythm(track: Track | TrackDetailV7) {
  if ("maest" in track) {
    return track.maest?.syncopated_rhythm === true;
  }
  return track.metadata?.maest_syncopated_rhythm === true;
}

import { formatMaestGenreLabel } from "./maestGenres";

export { formatMaestGenreLabel };

export const SYNCOPATED_RHYTHM_LABEL = "syncopated rhythm";

const syncopatedRhythmGenres = [
  "Breakbeat",
  "Breakcore",
  "Breaks",
  "Progressive Breaks",
  "Broken Beat",
  "Drum n Bass",
  "Jungle",
  "Halftime",
  "Juke",
  "UK Garage",
  "Speed Garage",
  "Bassline",
  "Electro"
].map((genre) => genre.toLowerCase());

export function hasSyncopatedRhythm(genres: string[] | null | undefined) {
  return (genres || []).some(isSyncopatedRhythmGenre);
}

export function isSyncopatedRhythmGenre(label: string) {
  const normalized = formatMaestGenreLabel(label).toLowerCase().replace(/\s+/g, " ").trim();
  return syncopatedRhythmGenres.some((genre) => normalized.includes(genre));
}
